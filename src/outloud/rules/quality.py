"""Source-comparison rules: when the original is at hand, the output must not have lost what it had.

These run only with --source. They are the checks that caught every
content-loss bug a validator passed: structure that vanished, characters
that vanished, pages that no longer look the same.
"""

from __future__ import annotations

import collections

from ..model import Document
from ..registry import finding, rule
from .tagging import _TEXT_FLAGS
from ._common import words


def _counts(doc: Document) -> dict[str, int]:
    c: dict[str, int] = collections.Counter()
    for el in doc.elements:
        if el.is_heading:
            c["heading"] += 1
        elif el.type in ("Table", "L", "Figure", "Formula", "Link", "Note"):
            c[el.type] += 1
    return c


@rule("SEM-001")
def structure_regression(doc: Document):
    src = Document(doc.source)
    try:
        if src.struct_root is None:
            return
        a, b = _counts(src), _counts(doc)
        lost = {k: (a[k], b.get(k, 0)) for k in a if b.get(k, 0) < a[k]}
        if lost:
            desc = ", ".join(f"{k}: {x} to {y}" for k, (x, y) in lost.items())
            yield finding("SEM-001", f"the output has less structure than the source ({desc})", evidence=desc)
    finally:
        src.close()


@rule("SEM-002")
def text_fidelity(doc: Document):
    try:
        import pymupdf as fitz  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        try:
            import fitz  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return
    src = fitz.open(doc.source)
    out = doc.fitz()
    try:
        n = min(len(src), len(out))
        lost_total, src_total = 0, 0
        worst = None
        for i in range(n):
            a = collections.Counter(w.lower() for w in words(src[i].get_text(flags=_TEXT_FLAGS)) if len(w) >= 3)
            b = collections.Counter(w.lower() for w in words(out[i].get_text(flags=_TEXT_FLAGS)) if len(w) >= 3)
            lost = sum(max(0, a[w] - b.get(w, 0)) for w in a)
            total = sum(a.values())
            lost_total += lost
            src_total += total
            if total and lost / total > 0.02 and (worst is None or lost > worst[1]):
                worst = (i + 1, lost, total, [w for w in a if b.get(w, 0) < a[w]][:6])
        if src_total and lost_total / src_total > 0.02:
            page, lost, total, sample_words = worst or (None, lost_total, src_total, [])
            yield finding("SEM-002", f"{lost_total} of {src_total} words in the source's text layer are missing from the output",
                          page=page, evidence=", ".join(sample_words), count=lost_total)
        if len(src) != len(out):
            yield finding("SEM-002", f"page count changed: source has {len(src)}, output has {len(out)}")
    finally:
        src.close()


@rule("SEM-003")
def visual_fidelity(doc: Document):
    try:
        import pymupdf as fitz  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        try:
            import fitz  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return
    src = fitz.open(doc.source)
    out = doc.fitz()
    try:
        n = min(len(src), len(out), 80)
        worst = None
        for i in range(n):
            pa = src[i].get_pixmap(dpi=30, colorspace=fitz.csGRAY, alpha=False)
            pb = out[i].get_pixmap(dpi=30, colorspace=fitz.csGRAY, alpha=False)
            if pa.width != pb.width or pa.height != pb.height:
                worst = (i + 1, 1.0)
                break
            sa, sb = pa.samples, pb.samples
            diff = sum(abs(x - y) for x, y in zip(sa, sb)) / (255.0 * len(sa) or 1)
            if diff > 0.006 and (worst is None or diff > worst[1]):
                worst = (i + 1, diff)
        if worst:
            page, diff = worst
            yield finding("SEM-003", f"page {page} renders differently from the source (mean intensity difference {diff:.3f})", page=page)
    finally:
        src.close()

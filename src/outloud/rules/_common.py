"""Helpers shared by rule modules."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

from ..model import Document, StructElem

WORD_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def element_text(doc: Document, el: StructElem, include_children: bool = True) -> str:
    """The text a reader gets from an element: its marked content, in order, with descendants."""
    parts: list[str] = []
    nodes = [el] + (list(el.descendants()) if include_children else [])
    for n in nodes:
        for r in n.mcrefs:
            if r.page is None:
                continue
            pc = doc.content(r.page)
            t = pc.mcid_text.get((r.stream, r.mcid))
            if t is None and r.stream is not None:
                # a form's private MCID space may have been flattened to the page
                t = pc.mcid_text.get((None, r.mcid))
            if t:
                parts.append(t)
    return " ".join(parts)


def element_bbox(doc: Document, el: StructElem) -> Optional[tuple]:
    box = None
    for n in [el] + list(el.descendants()):
        for r in n.mcrefs:
            if r.page is None:
                continue
            b = doc.content(r.page).mcid_bbox.get((r.stream, r.mcid))
            if b is None:
                continue
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return box


def element_page(el: StructElem) -> Optional[int]:
    """1-based page for a finding, from the element or its first content."""
    if el.page is not None:
        return el.page + 1
    for r in el.mcrefs:
        if r.page is not None:
            return r.page + 1
    for c in el.descendants():
        if c.page is not None:
            return c.page + 1
    return None


def norm(s: str) -> str:
    """Compatibility-normalised text: ligature and presentation forms become their letters ("ﬁve" -> "five")."""
    return unicodedata.normalize("NFKC", s or "")


def words(s: str) -> list[str]:
    return WORD_RE.findall(norm(s))


def has_content(doc: Document, el: StructElem) -> bool:
    if el.mcrefs or el.objrs or el.alt or el.actual_text:
        return True
    return any(c.mcrefs or c.objrs or c.alt or c.actual_text for c in el.descendants())


def sample(items: Iterable[str], n: int = 3, width: int = 60) -> str:
    out = []
    for s in items:
        s = " ".join(str(s).split())
        out.append(s[:width] + ("…" if len(s) > width else ""))
        if len(out) >= n:
            break
    return "; ".join(out)


def box(page_index: Optional[int], bbox: Optional[tuple]) -> Optional[dict]:
    if page_index is None or not bbox:
        return None
    x0, y0, x1, y1 = bbox
    if x1 - x0 < 0.5 or y1 - y0 < 0.5:
        x1, y1 = x0 + max(x1 - x0, 2.0), y0 + max(y1 - y0, 2.0)
    return {"page": page_index + 1, "x0": round(x0, 1), "y0": round(y0, 1), "x1": round(x1, 1), "y1": round(y1, 1)}


def element_box(doc: Document, el: StructElem) -> Optional[dict]:
    """A highlight box for an element: its Layout /BBox if it has one, else the union of its content."""
    bb = el.attr("BBox", "Layout")
    pg = element_page(el)
    if isinstance(bb, list) and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb) and pg:
        return box(pg - 1, tuple(float(v) for v in bb))
    b = element_bbox(doc, el)
    page_index = None
    for n in [el] + list(el.descendants()):
        for r in n.mcrefs:
            if r.page is not None:
                page_index = r.page
                break
        if page_index is not None:
            break
    return box(page_index, b)


def boxes_for(doc: Document, elements: Iterable[StructElem], limit: int = 40) -> list[dict]:
    out = []
    for el in elements:
        b = element_box(doc, el)
        if b:
            out.append(b)
        if len(out) >= limit:
            break
    return out


def run_boxes(page_index: int, runs: Iterable, limit: int = 40) -> list[dict]:
    out = []
    for r in runs:
        b = box(page_index, r.bbox)
        if b:
            out.append(b)
        if len(out) >= limit:
            break
    return out

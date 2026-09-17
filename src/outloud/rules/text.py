"""Text rules: can every glyph on the page become a character, and does the font travel with the file."""

from __future__ import annotations

import collections

from ..model import Document
from ..registry import finding, rule
from ._common import run_boxes


def _touch_all_pages(doc: Document) -> None:
    for p in doc.pages:
        doc.content(p.index)


@rule("TXT-001")
def embedded(doc: Document):
    _touch_all_pages(doc)
    bad = [f for f in doc.fonts.values() if not f.embedded and f.codes_shown]
    if bad:
        names = sorted({f.base_font for f in bad})
        yield finding("TXT-001", f"{len(bad)} font(s) used on the page are not embedded", count=len(bad),
                      evidence=", ".join(names[:6]), page=min(min(f.pages) for f in bad) + 1)


@rule("TXT-002")
def mappable(doc: Document):
    _touch_all_pages(doc)
    bad = [f for f in doc.fonts.values() if f.codes_shown and not f.has_tounicode and not f.encoding_map]
    for f in bad:
        yield finding("TXT-002", f"font {f.base_font} ({f.subtype}) has no /ToUnicode and no readable encoding; its text cannot be extracted",
                      page=min(f.pages) + 1, evidence=f.base_font, location={"codes_shown": len(f.codes_shown)})


@rule("TXT-003")
def unmapped_codes(doc: Document):
    _touch_all_pages(doc)
    for f in doc.fonts.values():
        if not f.unmapped_codes or not (f.has_tounicode or f.encoding_map):
            continue
        share = len(f.unmapped_codes) / max(1, len(f.codes_shown))
        yield finding("TXT-003", f"font {f.base_font}: {len(f.unmapped_codes)} of {len(f.codes_shown)} code(s) shown have no Unicode mapping",
                      page=min(f.pages) + 1, evidence=", ".join(hex(c) for c in sorted(f.unmapped_codes)[:8]),
                      severity=None if share >= 0.05 or len(f.unmapped_codes) >= 5 else "warning")


@rule("TXT-007")
def cid_to_gid(doc: Document):
    import pikepdf  # noqa: PLC0415

    seen: set[tuple] = set()
    for f in doc.fonts.values():
        if f.subtype != "Type0" or not f.embedded or f.key in seen:
            continue
        seen.add(f.key)
        try:
            fd = doc.pdf.get_object(f.key) if isinstance(f.key, tuple) and len(f.key) == 2 and isinstance(f.key[0], int) else None
        except Exception:  # noqa: BLE001
            fd = None
        if not isinstance(fd, pikepdf.Dictionary):
            continue
        desc = fd.get("/DescendantFonts")
        if not isinstance(desc, pikepdf.Array) or not len(desc):
            continue
        cid = desc[0]
        if not isinstance(cid, pikepdf.Dictionary) or str(cid.get("/Subtype")) != "/CIDFontType2":
            continue
        if cid.get("/CIDToGIDMap") is None:
            yield finding("TXT-007", f"font {f.base_font}: embedded CIDFontType2 has no /CIDToGIDMap",
                          page=(min(f.pages) + 1) if f.pages else None, evidence=f.base_font)


@rule("TXT-004")
def mapping_quality(doc: Document):
    _touch_all_pages(doc)
    for f in doc.fonts.values():
        if not f.has_tounicode or not f.codes_shown:
            continue
        shown = {c: ord(u[0]) for c, u in f.cmap.items() if c in f.codes_shown and u}
        if len(shown) < 4:
            continue
        targets = collections.Counter(u for u in shown.values() if u != 32)
        collisions = [(u, n) for u, n in targets.items() if n >= 5]
        control = [c for c, u in shown.items() if u < 32 and u not in (9, 10, 13)]
        pua = [c for c, u in shown.items() if 0xE000 <= u <= 0xF8FF]
        problems = []
        if collisions:
            u, n = max(collisions, key=lambda x: x[1])
            problems.append(f"{n} different codes all map to U+{u:04X} {chr(u)!r}")
        if control:
            problems.append(f"{len(control)} code(s) map to control characters")
        if pua:
            problems.append(f"{len(pua)} code(s) map to the private-use area")
        if problems:
            yield finding("TXT-004", f"font {f.base_font}: " + "; ".join(problems), page=min(f.pages) + 1, evidence=f.base_font)


@rule("TXT-005")
def notdef_glyph(doc: Document):
    for page in doc.pages:
        n = doc.content(page.index).notdef_shown
        if n:
            yield finding("TXT-005", f"{n} glyph(s) shown are glyph 0 (.notdef) of a composite font", page=page.number, count=n)


@rule("TXT-006")
def tounicode_noncharacters(doc: Document):
    _touch_all_pages(doc)
    for f in doc.fonts.values():
        if not f.has_tounicode or not f.codes_shown:
            continue
        bad = sorted(c for c, t in f.cmap.items() if c in f.codes_shown and t and ord(t[0]) in (0, 0xFEFF, 0xFFFE))
        if bad:
            yield finding("TXT-006", f"font {f.base_font}: {len(bad)} code(s) shown map to U+0000, U+FEFF or U+FFFE", page=min(f.pages) + 1,
                          count=len(bad), evidence=", ".join(hex(c) for c in bad[:6]))


@rule("TXT-010")
def invisible_text(doc: Document):
    for page in doc.pages:
        pc = doc.content(page.index)
        chars = sum(len(r.text) for r in pc.runs if r.text.strip())
        if chars < 40:
            continue
        invisible = sum(len(r.text) for r in pc.runs if r.text.strip() and r.render_mode == 3)
        if invisible / chars < 0.9:
            continue
        page_area = page.width * page.height or 1.0
        carried = False
        for img in pc.images:
            w = img.bbox[2] - img.bbox[0]
            h = img.bbox[3] - img.bbox[1]
            if w * h / page_area < 0.5 or w <= 0:
                continue
            dpi = img.width_px / (w / 72.0)
            if dpi >= 100:
                carried = True
                break
        if not carried:
            yield finding("TXT-010", "the page's text is invisible (render mode 3) and no image of at least 100 dpi carries the glyphs; the page renders blank",
                          page=page.number, location={"invisible_chars": invisible, "images": len(pc.images)})


@rule("TXT-011")
def form_text_untagged(doc: Document):
    if doc.struct_root is None:
        return
    for page in doc.pages:
        pc = doc.content(page.index)
        runs = [r for r in pc.untagged_runs() if r.in_form]
        if runs:
            yield finding("TXT-011", f"{len(runs)} text run(s) inside a form XObject are neither tagged nor artifacts",
                          page=page.number, count=len(runs), evidence=" ".join(r.text for r in runs[:3])[:90], boxes=run_boxes(page.index, runs))

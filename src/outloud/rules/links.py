"""Link, annotation and form rules: can a reader find, name and follow what the page links to."""

from __future__ import annotations

import re

from ..model import Document
from ..registry import finding, rule
from ._common import boxes_for, run_boxes, element_page, element_text, sample

URI_RE = re.compile(r"(https?://\S+|www\.[a-z0-9\-]+\.[a-z]{2,}\S*|[\w.+-]+@[\w-]+\.[\w.-]+\.?)", re.I)
F_PRINT, F_HIDDEN, F_NOVIEW = 4, 2, 32
def _annot_boxes(annots, limit: int = 40) -> list[dict]:
    out = []
    for a in annots[:limit]:
        x0, y0, x1, y1 = min(a.rect[0], a.rect[2]), min(a.rect[1], a.rect[3]), max(a.rect[0], a.rect[2]), max(a.rect[1], a.rect[3])
        out.append({"page": a.page + 1, "x0": round(x0, 1), "y0": round(y0, 1), "x1": round(x1, 1), "y1": round(y1, 1)})
    return out


_INTERNAL_ID = re.compile(r"^(text|check|check ?box|signature|button|radio|combo|list|field|date|fill|name|untitled)[ _\-]?\d*$", re.I)


@rule("LNK-001")
def link_annotation_outside_link(doc: Document):
    if doc.struct_root is None:
        return
    bad = []
    for a in doc.annotations:
        if a.subtype != "Link" or a.hidden:
            continue
        owners = doc.objr_owners.get(a.objgen, [])
        if not owners or not any(o.type == "Link" for o in owners):
            bad.append(a)
    if bad:
        yield finding("LNK-001", f"{len(bad)} link annotation(s) are not inside a /Link structure element", page=bad[0].page + 1,
                      count=len(bad), location={"rect": [round(v, 1) for v in bad[0].rect]}, boxes=_annot_boxes(bad))


@rule("LNK-002")
def annotation_without_contents(doc: Document):
    bad = []
    for a in doc.annotations:
        if a.hidden or a.subtype in ("Widget", "Popup"):
            continue
        if (a.contents or "").strip():
            continue
        owners = doc.objr_owners.get(a.objgen, [])
        if any((o.alt or "").strip() for o in owners):
            continue
        bad.append(a)
    if bad:
        kinds = sorted({a.subtype for a in bad})
        yield finding("LNK-002", f"{len(bad)} annotation(s) have no /Contents and no /Alt on their element ({', '.join(kinds)})",
                      page=bad[0].page + 1, count=len(bad), location={"rect": [round(v, 1) for v in bad[0].rect]}, boxes=_annot_boxes(bad))


@rule("LNK-003")
def link_element_unnamed(doc: Document):
    bad = []
    for el in doc.elements_of("Link"):
        if (el.alt or "").strip():
            continue
        if element_text(doc, el).strip():
            continue
        bad.append(el)
    if bad:
        yield finding("LNK-003", f"{len(bad)} /Link element(s) have no text and no /Alt", page=element_page(bad[0]), count=len(bad),
                      location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("LNK-004")
def annotation_flags(doc: Document):
    no_print = [a for a in doc.annotations if not a.hidden and not (a.flags & F_PRINT) and a.subtype != "Popup"]
    noview = [a for a in doc.annotations if (a.flags & F_NOVIEW) and not (a.flags & F_HIDDEN)]
    if no_print:
        yield finding("LNK-004", f"{len(no_print)} annotation(s) lack the Print flag; print and screen differ", page=no_print[0].page + 1,
                      count=len(no_print), boxes=_annot_boxes(no_print))
    if noview:
        yield finding("LNK-004", f"{len(noview)} annotation(s) are NoView: present to readers but not on screen", page=noview[0].page + 1,
                      count=len(noview), boxes=_annot_boxes(noview))


@rule("LNK-005")
def tabs_structure_order(doc: Document):
    import pikepdf  # noqa: PLC0415

    pages_with = {a.page for a in doc.annotations}
    bad = []
    for page in doc.pages:
        if page.index not in pages_with:
            continue
        tabs = page.obj.get("/Tabs")
        if not (isinstance(tabs, pikepdf.Name) and str(tabs) == "/S"):
            bad.append(page)
    if bad:
        yield finding("LNK-005", f"{len(bad)} page(s) with annotations do not set /Tabs /S", page=bad[0].number, count=len(bad),
                      evidence=", ".join(str(p.number) for p in bad[:8]))


@rule("LNK-006")
def annotation_outside_annot(doc: Document):
    if doc.struct_root is None:
        return
    bad = []
    for a in doc.annotations:
        if a.subtype in ("Link", "Widget", "PrinterMark", "Popup") or a.hidden:
            continue
        owners = doc.objr_owners.get(a.objgen, [])
        if not any(o.type == "Annot" for o in owners):
            bad.append(a)
    if bad:
        kinds = sorted({a.subtype for a in bad})
        yield finding("LNK-006", f"{len(bad)} annotation(s) are not inside an /Annot structure element ({', '.join(kinds)})", page=bad[0].page + 1,
                      count=len(bad), boxes=_annot_boxes(bad))


@rule("FRM-003")
def widget_outside_form(doc: Document):
    if doc.struct_root is None:
        return
    bad = [a for a in doc.annotations if a.subtype == "Widget" and not a.hidden
           and not any(o.type == "Form" for o in doc.objr_owners.get(a.objgen, []))]
    if bad:
        yield finding("FRM-003", f"{len(bad)} form field widget(s) are not inside a /Form structure element", page=bad[0].page + 1, count=len(bad), boxes=_annot_boxes(bad))


@rule("LNK-010")
def unlinked_uris(doc: Document):
    for page in doc.pages:
        pc = doc.content(page.index)
        links = [a for a in doc.annotations if a.page == page.index and a.subtype == "Link"]
        hits = []
        hit_runs = []
        for r in pc.runs:
            if not r.text.strip() or r.artifact:
                continue
            m = URI_RE.search(r.text)
            if not m:
                continue
            covered = False
            for a in links:
                x0, y0, x1, y1 = min(a.rect[0], a.rect[2]), min(a.rect[1], a.rect[3]), max(a.rect[0], a.rect[2]), max(a.rect[1], a.rect[3])
                if r.bbox[2] > x0 and r.bbox[0] < x1 and r.bbox[3] > y0 and r.bbox[1] < y1:
                    covered = True
                    break
            if not covered:
                hits.append(m.group(1).rstrip(".,;)"))
                hit_runs.append(r)
        if hits:
            uniq = list(dict.fromkeys(hits))
            yield finding("LNK-010", f"{len(uniq)} address(es) or URL(s) are printed as text with no link annotation over them",
                          page=page.number, count=len(uniq), evidence=sample(uniq, 3, 40), boxes=run_boxes(page.index, hit_runs))


@rule("FRM-001")
def field_without_name(doc: Document):
    bad = [a for a in doc.annotations if a.subtype == "Widget" and not a.hidden and not (a.field_tu or "").strip()]
    if bad:
        yield finding("FRM-001", f"{len(bad)} form field(s) have no /TU name for readers", page=bad[0].page + 1, count=len(bad),
                      evidence=sample((a.field_t or "?" for a in bad), 4, 20), boxes=_annot_boxes(bad))


@rule("FRM-002")
def field_name_is_id(doc: Document):
    bad = [a for a in doc.annotations if a.subtype == "Widget" and (a.field_tu or "").strip()
           and (_INTERNAL_ID.match(a.field_tu.strip()) or (a.field_t and a.field_tu.strip() == a.field_t.strip() and _INTERNAL_ID.match(a.field_t.strip())))]
    if bad:
        yield finding("FRM-002", f"{len(bad)} form field(s) have a /TU that is an internal id rather than a name", page=bad[0].page + 1,
                      count=len(bad), evidence=sample((a.field_tu for a in bad), 4, 20), boxes=_annot_boxes(bad))

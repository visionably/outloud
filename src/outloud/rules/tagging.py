"""Tagging rules: is every piece of painted content owned by exactly one element, and does the tag tell the truth."""

from __future__ import annotations

import collections
import re

import pikepdf

from ..model import STANDARD_TYPES, Document
from ..registry import finding, rule

try:  # PyMuPDF's flag constants; the fallback values are the documented ones
    import pymupdf as _fitz
    _TEXT_FLAGS = _fitz.TEXT_PRESERVE_LIGATURES | _fitz.TEXT_PRESERVE_WHITESPACE | _fitz.TEXT_MEDIABOX_CLIP
except Exception:  # noqa: BLE001
    _TEXT_FLAGS = 1 | 2 | 64

_DENSE_PATHS = 1000   # painted paths per page above which MuPDF text extraction is skipped
from ._common import boxes_for, run_boxes, box, element_bbox, element_page, element_text, has_content, norm, sample, words

GROUPING_TYPES = {"Document", "Part", "Art", "Sect", "Div", "TOC", "Index", "NonStruct", "Private",
                  "THead", "TBody", "TFoot", "L", "LI", "Table", "TR", "TD", "TH", "Form", "Figure", "Formula", "Link"}
_NUMBERISH = re.compile(r"^[\s\d.,/\-–—()•·|:%$€₹£]*$")


def line_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", text.lower())).strip()


def furniture_keys(doc: Document) -> set[str]:
    """Normalised text lines that recur on three or more pages: running heads, folios."""
    pages_by_key: dict[str, set[int]] = collections.defaultdict(set)
    for page in doc.pages:
        for ln in doc.content(page.index).lines:
            key = line_key(ln.text)
            if len(key) >= 4:
                pages_by_key[key].add(page.index)
    n = len(doc.pages)
    need = 3 if n >= 6 else max(2, n)
    return {k for k, pgs in pages_by_key.items() if len(pgs) >= need}


def _blob(texts) -> str:
    return re.sub(r"\s+", "", norm(" ".join(texts)).lower())


@rule("TAG-001")
def untagged_content(doc: Document):
    if doc.struct_root is None:
        return   # DOC-002 already says everything is untagged
    for page in doc.pages:
        pc = doc.content(page.index)
        runs = [r for r in pc.untagged_runs() if not r.in_form]
        imgs = [i for i in pc.images if i.mcid is None and not i.artifact and not i.in_form]
        paths = [p for p in pc.paths if p.mcid is None and not p.artifact and (p.filled or p.stroked)]
        if not runs and not imgs and not paths:
            continue
        parts = []
        if runs:
            parts.append(f"{len(runs)} text run(s)")
        if imgs:
            parts.append(f"{len(imgs)} image(s)")
        if paths:
            parts.append(f"{len(paths)} drawn path(s)")
        sev = None if (runs or imgs) else "warning"
        yield finding("TAG-001", f"{', '.join(parts)} painted outside any structure element or artifact",
                      page=page.number, severity=sev, count=len(runs) + len(imgs) + (1 if paths and not runs and not imgs else 0),
                      evidence=sample((r.text for r in runs), 3) or (imgs[0].name if imgs else None),
                      location={"untagged_text_runs": len(runs), "untagged_images": len(imgs), "untagged_paths": len(paths)}, boxes=run_boxes(page.index, runs) + [box(page.index, i.bbox) for i in imgs[:10] if box(page.index, i.bbox)])


@rule("TAG-002")
def artifacted_prose(doc: Document):
    if doc.struct_root is None:
        return
    furniture = furniture_keys(doc)
    for page in doc.pages:
        pc = doc.content(page.index)
        hits = []
        hit_lines = []
        for ln in pc.lines:
            if ln.artifact_share < 0.8:
                continue
            text = ln.text
            if line_key(text) in furniture or _NUMBERISH.match(text):
                continue
            ws = words(text)
            lower = sum(1 for w in ws if w[:1].islower())
            if len(ws) >= 8 and lower >= 4:
                hits.append(text)
                hit_lines.append(ln)
        if hits:
            yield finding("TAG-002", f"{len(hits)} line(s) of prose are marked /Artifact and will be skipped by every reader",
                          page=page.number, count=len(hits), evidence=sample(hits, 2, 90), boxes=[box(page.index, l.bbox) for l in hit_lines[:40] if box(page.index, l.bbox)])


@rule("TAG-003")
def silent_words(doc: Document):
    if doc.struct_root is None:
        return
    try:
        fz = doc.fitz()
    except Exception:  # noqa: BLE001
        return
    furniture = furniture_keys(doc)
    alt_by_page: dict[int, list[str]] = collections.defaultdict(list)
    for el in doc.elements:
        pg = el.page
        if pg is None:
            for r in el.mcrefs:
                if r.page is not None:
                    pg = r.page
                    break
        if pg is not None:
            for v in (el.alt, el.actual_text):
                if v:
                    alt_by_page[pg].append(v)
    for page in doc.pages:
        pc = doc.content(page.index)
        announced = _blob([r.text for r in pc.runs if r.tagged and not r.artifact] + alt_by_page.get(page.index, []))
        elsewhere = _blob([r.text for r in pc.runs if not r.tagged or r.artifact])   # TAG-001 / TAG-002 territory
        lines = []
        inv = None
        if len(pc.paths) > _DENSE_PATHS:
            # MuPDF's text device slows to seconds on a page with thousands of vector paths (a
            # chart drawn stroke by stroke): 12 s for one page of a 101-page file. The walker
            # already has every painted run of such a page, so use its lines, in PDF space.
            lines = [(ln.text, ln.bbox) for ln in pc.lines]
        else:
            try:
                fpage = fz[page.index]
                inv = ~fpage.transformation_matrix
                for blk in fpage.get_text("dict", flags=_TEXT_FLAGS).get("blocks", []):
                    for ln in blk.get("lines", []):
                        lines.append(("".join(sp.get("text", "") for sp in ln.get("spans", [])), ln.get("bbox")))
            except Exception:  # noqa: BLE001
                continue
        missing: list[str] = []
        missing_boxes: list[dict] = []
        for line, lb in lines:
            if line_key(line) in furniture:
                continue
            found_here = False
            for w in words(line):
                lw = w.lower()
                if len(lw) < 3 or lw in announced or lw in elsewhere:
                    continue
                missing.append(w)
                found_here = True
            if found_here and lb:
                if inv is None:
                    b = box(page.index, lb)
                else:
                    try:
                        import pymupdf as _fz  # noqa: PLC0415
                    except ImportError:  # pragma: no cover
                        import fitz as _fz  # noqa: PLC0415
                    r = _fz.Rect(lb) * inv
                    b = box(page.index, (min(r.x0, r.x1), min(r.y0, r.y1), max(r.x0, r.x1), max(r.y0, r.y1)))
                if b:
                    missing_boxes.append(b)
        if len(missing) >= 3:
            uniq = list(dict.fromkeys(missing))
            yield finding("TAG-003", f"{len(uniq)} word(s) printed on the page are announced by no structure element",
                          page=page.number, count=len(uniq), evidence=sample(uniq, 8, 30), boxes=missing_boxes[:40])


@rule("TAG-004")
def nested_artifacts(doc: Document):
    """Only marked content that a structure element actually claims counts as
    tagged: an orphan MCID inside an artifact is just an artifact, which is
    also how veraPDF reads it."""
    for page in doc.pages:
        events = doc.content(page.index).nesting_events
        claimed = [(s, m) for s, m in events if doc.mc_owners.get((page.index, s, m))]
        if claimed:
            yield finding("TAG-004", f"{len(claimed)} marked-content sequence(s) nest tagged content and artifacts inside each other",
                          page=page.number, count=len(claimed), evidence=f"MCID {claimed[0][1]}")


@rule("TAG-023")
def missing_parent_entry(doc: Document):
    bad = [el for el in doc.elements if el.obj.get("/P") is None]
    if bad:
        yield finding("TAG-023", f"{len(bad)} structure element(s) have no /P entry", page=element_page(bad[0]), count=len(bad),
                      location={"first": bad[0].path})


@rule("TAG-040")
def reference_xobjects(doc: Document):
    hits = []
    seen = set()

    def scan(res, page_no, depth=0):
        if not isinstance(res, pikepdf.Dictionary) or depth > 6:
            return
        xobjs = res.get("/XObject")
        if not isinstance(xobjs, pikepdf.Dictionary):
            return
        for name, xo in xobjs.items():
            if not isinstance(xo, pikepdf.Stream):
                continue
            og = xo.objgen
            if og in seen:
                continue
            seen.add(og)
            if str(xo.get("/Subtype")) == "/Form":
                if xo.get("/Ref") is not None:
                    hits.append((page_no, name))
                scan(xo.get("/Resources"), page_no, depth + 1)

    for page in doc.pages:
        scan(page.obj.get("/Resources"), page.number)
    if hits:
        yield finding("TAG-040", f"{len(hits)} reference XObject(s) import content from another file", page=hits[0][0], count=len(hits),
                      evidence=hits[0][1])


@rule("TAG-010")
def unmapped_types(doc: Document):
    counts: dict[str, int] = collections.Counter()
    first_page: dict[str, int] = {}
    for el in doc.elements:
        if el.type_raw in STANDARD_TYPES:
            continue
        resolved, circular = doc.resolve_type(el.type_raw)
        if resolved not in STANDARD_TYPES and not circular:
            counts[el.type_raw] += 1
            first_page.setdefault(el.type_raw, element_page(el) or 0)
    for t, n in counts.items():
        yield finding("TAG-010", f"structure type /{t} is not standard and /RoleMap does not map it to a standard type ({n} element(s))",
                      page=first_page.get(t) or None, count=n, evidence=t)


@rule("TAG-011")
def circular_rolemap(doc: Document):
    for t in doc.role_map_raw:
        _, circular = doc.resolve_type(t)
        if circular:
            yield finding("TAG-011", f"/RoleMap entry for /{t} loops back on itself", evidence=t)


@rule("TAG-012")
def remapped_standard(doc: Document):
    for t, target in doc.role_map_raw.items():
        if t in STANDARD_TYPES and target != t:
            yield finding("TAG-012", f"/RoleMap remaps the standard type /{t} to /{target}", evidence=f"{t} -> {target}")


@rule("TAG-020")
def empty_elements(doc: Document):
    by_type: dict[str, list] = collections.defaultdict(list)
    for el in doc.elements:
        if el.type in GROUPING_TYPES or el.type not in STANDARD_TYPES:
            continue
        if not has_content(doc, el):
            by_type[el.type].append(el)
    for t, els in by_type.items():
        yield finding("TAG-020", f"{len(els)} empty /{t} element(s): no content, children, /Alt or /ActualText",
                      page=element_page(els[0]), count=len(els), location={"first": els[0].path})


@rule("TAG-021")
def dangling_pages(doc: Document):
    bad_pg = 0
    no_page = 0
    first = None
    for el in doc.elements:
        pg = el.obj.get("/Pg")
        if isinstance(pg, pikepdf.Dictionary) and pg.objgen not in doc.page_index:
            bad_pg += 1
            first = first or el.path
        for r in el.mcrefs:
            if r.page is None:
                no_page += 1
                first = first or el.path
    if bad_pg:
        yield finding("TAG-021", f"{bad_pg} element(s) have a /Pg that is not a page of this document", count=bad_pg, location={"first": first})
    if no_page:
        yield finding("TAG-021", f"{no_page} marked-content reference(s) have no page (no /Pg on the element or any ancestor)",
                      count=no_page, location={"first": first})


@rule("TAG-022")
def shared_mcids(doc: Document):
    dupes = [(k, els) for k, els in doc.mc_owners.items() if len(els) > 1]
    if dupes:
        (page, _stream, mcid), els = dupes[0]
        yield finding("TAG-022", f"{len(dupes)} marked-content id(s) are claimed by more than one structure element",
                      page=(page + 1) if page is not None else None, count=len(dupes),
                      evidence=f"MCID {mcid}: " + " and ".join(e.path for e in els[:2]), boxes=boxes_for(doc, [e for _, els in dupes[:20] for e in els]))


@rule("TAG-030")
def page_figure(doc: Document):
    for el in doc.elements_of("Figure"):
        pg = el.page
        if pg is None:
            continue
        page = doc.pages[pg]
        fig_box = None
        bb = el.attr("BBox", "Layout")
        if isinstance(bb, list) and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb):
            fig_box = tuple(float(v) for v in bb)
        if fig_box is None:
            fig_box = element_bbox(doc, el)
        if fig_box is None:
            continue
        area = max(0.0, fig_box[2] - fig_box[0]) * max(0.0, fig_box[3] - fig_box[1])
        if page.width * page.height <= 0 or area / (page.width * page.height) < 0.85:
            continue
        pc = doc.content(pg)
        tagged_words = sum(len(words(r.text)) for r in pc.runs if r.tagged and not r.artifact and r.render_mode != 3)
        if tagged_words >= 20:
            yield finding("TAG-030", "a /Figure covers the whole page while the page carries tagged text: the scan is described as a picture",
                          page=page.number, evidence=(el.alt or "")[:80], location={"element": el.path}, boxes=[box(pg, fig_box)])


def _letters(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s or "").lower())


@rule("TAG-031")
def alt_hides_content(doc: Document):
    """Compared on letters, not words: text merged from glyph-per-operator
    streams or OCR layers may carry no word boundaries at all."""
    for el in doc.elements:
        if el.type in ("Figure", "Formula") or not (el.alt or el.actual_text):
            continue
        content = _letters(element_text(doc, el))
        if len(content) < 60:
            continue
        rep = _letters(el.actual_text or el.alt or "")
        if len(rep) < 0.35 * len(content):
            yield finding("TAG-031", f"/{el.type} replaces {len(content)} characters of content with {len(rep)} of alternative text",
                          page=element_page(el), evidence=element_text(doc, el)[:100], location={"element": el.path, "replacement": (el.actual_text or el.alt or "")[:80]}, boxes=boxes_for(doc, [el]))


@rule("TAG-032")
def actualtext_coverage(doc: Document):
    """Letters of the content that the /ActualText does not carry, measured
    by sequence similarity so that word boundaries do not matter."""
    import difflib  # noqa: PLC0415

    for el in doc.elements:
        if not el.actual_text or el.type == "Formula":
            continue
        content = _letters(element_text(doc, el))
        if len(content) < 12:
            continue
        rep = _letters(el.actual_text)
        if rep == content or content in rep:
            continue
        ratio = difflib.SequenceMatcher(None, content, rep, autojunk=False).ratio()
        if ratio < 0.6:
            yield finding("TAG-032", f"/ActualText on /{el.type} matches only {round(ratio * 100)}% of the text it replaces",
                          page=element_page(el), evidence=element_text(doc, el)[:80], location={"element": el.path, "replacement": el.actual_text[:80]}, boxes=boxes_for(doc, [el]))

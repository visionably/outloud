"""The document model: pages, structure tree, fonts, annotations, metadata.

Built once per file from pikepdf objects and shared by every rule. Rules
never touch pikepdf directly for structure; they read the model, which has
already resolved the things that are easy to get wrong: role-mapped types,
inherited /Pg, marked-content references with their stream, attributes
split by owner, fonts with their Unicode mapping and embedding status.

Page content (the text runs and images actually painted) is parsed lazily
by `content.py` and cached on the model, because several rules need it and
one pass over each content stream is enough.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Optional

import pikepdf

from . import fonts as fontmod

# ISO 32000-1 standard structure types (Tables 10.20 to 10.25). PDF/UA-1 is
# built on PDF 1.7, so this is the set an element must be, or map to.
STANDARD_TYPES = frozenset("""
Document Part Art Sect Div BlockQuote Caption TOC TOCI Index NonStruct Private
P H H1 H2 H3 H4 H5 H6 L LI Lbl LBody Table TR TH TD THead TBody TFoot
Span Quote Note Reference BibEntry Code Link Annot Ruby RB RT RP Warichu WT WP
Figure Formula Form
""".split())

HEADING_RE = re.compile(r"^H([1-9]\d*)$")


@dataclass
class Page:
    index: int                # 0-based
    number: int               # 1-based, for people
    obj: pikepdf.Object
    objgen: tuple
    width: float
    height: float
    rotate: int
    mediabox: tuple


@dataclass
class MCRef:
    """A marked-content reference: (page, stream, mcid).

    `stream` is None for content in the page's own stream and the objgen of
    a form XObject for content inside that form (an /MCR with /Stm).
    """

    page: Optional[int]
    stream: Optional[tuple]
    mcid: int


@dataclass
class StructElem:
    obj: pikepdf.Object
    objgen: tuple
    type_raw: str             # as written, without the slash
    type: str                 # after role mapping, or type_raw if unmapped
    parent: Optional["StructElem"]
    depth: int
    order: int                # document-order index
    page: Optional[int]       # resolved /Pg (0-based), inherited from ancestors
    children: list["StructElem"] = field(default_factory=list)
    mcrefs: list[MCRef] = field(default_factory=list)
    objrs: list[tuple] = field(default_factory=list)   # annotation objgens via /OBJR
    alt: Optional[str] = None
    actual_text: Optional[str] = None
    lang: Optional[str] = None
    id: Optional[str] = None
    attrs: dict = field(default_factory=dict)          # owner -> {key: value}

    @property
    def is_heading(self) -> bool:
        return self.type == "H" or bool(HEADING_RE.match(self.type))

    @property
    def heading_level(self) -> Optional[int]:
        m = HEADING_RE.match(self.type)
        return int(m.group(1)) if m else None

    @property
    def path(self) -> str:
        parts = []
        node = self
        while node is not None:
            parts.append(node.type_raw)
            node = node.parent
        return "/".join(reversed(parts))

    def attr(self, key: str, owner: Optional[str] = None):
        if owner:
            return self.attrs.get(owner, {}).get(key)
        for vals in self.attrs.values():
            if key in vals:
                return vals[key]
        return None

    def descendants(self):
        stack = list(reversed(self.children))
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    # /NonStruct groups content without structural meaning: ISO 32000 says a
    # reader treats its children as children of its parent. Structural rules
    # (a cell must be in a row, an item in a list) therefore look through it.
    @property
    def logical_parent(self) -> Optional["StructElem"]:
        node = self.parent
        while node is not None and node.type == "NonStruct":
            node = node.parent
        return node

    @property
    def logical_children(self) -> list["StructElem"]:
        out: list[StructElem] = []
        for c in self.children:
            if c.type == "NonStruct":
                out.extend(c.logical_children)
            else:
                out.append(c)
        return out


@dataclass
class Annotation:
    page: int
    objgen: tuple
    subtype: str
    contents: Optional[str]
    flags: int
    rect: tuple
    field_tu: Optional[str] = None
    field_t: Optional[str] = None
    field_ft: Optional[str] = None
    has_alt: bool = False
    hidden: bool = False


def _str(v) -> Optional[str]:
    if v is None:
        return None
    try:
        return str(v)
    except Exception:  # noqa: BLE001
        return None


def _name(v) -> Optional[str]:
    if isinstance(v, pikepdf.Name):
        return str(v)[1:]
    return None


class Document:
    """Everything the rules need to know about one PDF, resolved once."""

    def __init__(self, path: str, source: Optional[str] = None):
        self.path = path
        self.source = source
        self.pdf = pikepdf.open(path)
        self._content_cache: dict[int, object] = {}
        self._fitz = None

    # ── pages ─────────────────────────────────────────────────────────────

    @cached_property
    def pages(self) -> list[Page]:
        out = []
        for i, p in enumerate(self.pdf.pages):
            obj = p.obj
            mb = [float(v) for v in (p.mediabox if p.mediabox is not None else [0, 0, 612, 792])]
            cb = p.get("/CropBox")
            box = [float(v) for v in cb] if cb is not None and len(cb) == 4 else mb
            w, h = abs(box[2] - box[0]), abs(box[3] - box[1])
            rot = int(p.get("/Rotate", 0) or 0) % 360
            out.append(Page(i, i + 1, obj, obj.objgen, w, h, rot, tuple(box)))
        return out

    @cached_property
    def page_index(self) -> dict[tuple, int]:
        return {p.objgen: p.index for p in self.pages}

    # ── catalog-level facts ───────────────────────────────────────────────

    @property
    def root(self):
        return self.pdf.Root

    @cached_property
    def mark_info(self) -> dict:
        mi = self.root.get("/MarkInfo")
        if not isinstance(mi, pikepdf.Dictionary):
            return {}
        return {k[1:]: bool(v) for k, v in mi.items() if isinstance(v, (bool, pikepdf.Object))}

    @cached_property
    def lang(self) -> Optional[str]:
        return _str(self.root.get("/Lang"))

    @cached_property
    def display_doc_title(self) -> Optional[bool]:
        vp = self.root.get("/ViewerPreferences")
        if not isinstance(vp, pikepdf.Dictionary) or "/DisplayDocTitle" not in vp:
            return None
        return bool(vp.get("/DisplayDocTitle"))

    @cached_property
    def xmp(self) -> dict[str, str]:
        """The few XMP properties the rules care about, as plain strings."""
        out: dict[str, str] = {}
        try:
            # update_docinfo=False: by default pikepdf copies XMP values into the Info
            # dictionary when the context closes, which would hide a disagreement
            # between the two titles (DOC-015) and falsify DOC-010's evidence.
            with self.pdf.open_metadata(update_docinfo=False) as meta:
                for key in ("dc:title", "pdfuaid:part", "pdfuaid:conformance", "dc:language", "xmp:CreatorTool", "pdf:Producer"):
                    try:
                        v = meta.get(key)
                    except Exception:  # noqa: BLE001
                        v = None
                    if v is not None:
                        out[key] = str(v)
        except Exception:  # noqa: BLE001
            pass
        if "pdfuaid:part" not in out:
            # pikepdf's XMP wrapper does not know every namespace; read the raw packet.
            try:
                md = self.root.get("/Metadata")
                raw = md.read_bytes().decode("utf-8", "replace") if md is not None else ""
                m = re.search(r"pdfuaid:part\s*(?:=\s*\"|>)\s*(\d+)", raw)
                if m:
                    out["pdfuaid:part"] = m.group(1)
                if "dc:title" not in out:
                    m = re.search(r"<dc:title>.*?<rdf:li[^>]*>(.*?)</rdf:li>", raw, re.S)
                    if m:
                        out["dc:title"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            except Exception:  # noqa: BLE001
                pass
        return out

    @cached_property
    def info_title(self) -> Optional[str]:
        try:
            info = self.pdf.docinfo
            return _str(info.get("/Title")) if info is not None else None
        except Exception:  # noqa: BLE001
            return None

    @property
    def title(self) -> Optional[str]:
        return self.xmp.get("dc:title") or self.info_title

    @cached_property
    def permissions(self):
        try:
            return self.pdf.allow
        except Exception:  # noqa: BLE001
            return None

    # ── structure tree ────────────────────────────────────────────────────

    @cached_property
    def struct_root(self):
        r = self.root.get("/StructTreeRoot")
        return r if isinstance(r, pikepdf.Dictionary) else None

    @cached_property
    def role_map_raw(self) -> dict[str, str]:
        if self.struct_root is None:
            return {}
        rm = self.struct_root.get("/RoleMap")
        if not isinstance(rm, pikepdf.Dictionary):
            return {}
        out = {}
        for k, v in rm.items():
            n = _name(v)
            if n is not None:
                out[k[1:]] = n
        return out

    def resolve_type(self, t: str) -> tuple[str, bool]:
        """(resolved type, circular?) following /RoleMap until a standard type or a loop."""
        seen = [t]
        cur = t
        while cur not in STANDARD_TYPES and cur in self.role_map_raw:
            cur = self.role_map_raw[cur]
            if cur in seen:
                return t, True
            seen.append(cur)
        return cur, False

    @cached_property
    def elements(self) -> list[StructElem]:
        """Every structure element in document order, with parents resolved."""
        root = self.struct_root
        if root is None:
            return []
        out: list[StructElem] = []
        seen: set[tuple] = set()
        counter = 0

        def walk(node, parent: Optional[StructElem], depth: int, page: Optional[int]):
            nonlocal counter
            if not isinstance(node, pikepdf.Dictionary) or depth > 60:
                return
            og = node.objgen
            if og != (0, 0):
                if og in seen:
                    return
                seen.add(og)
            s = node.get("/S")
            el: Optional[StructElem] = None
            if s is not None:
                pg = node.get("/Pg")
                if isinstance(pg, pikepdf.Dictionary):
                    page = self.page_index.get(pg.objgen, page)
                traw = _name(s) or str(s)
                tres, _ = self.resolve_type(traw)
                el = StructElem(node, og, traw, tres, parent, depth, counter, page)
                counter += 1
                el.alt = _str(node.get("/Alt"))
                el.actual_text = _str(node.get("/ActualText"))
                el.lang = _str(node.get("/Lang"))
                el.id = _str(node.get("/ID"))
                el.attrs = self._attributes(node)
                if parent is not None:
                    parent.children.append(el)
                out.append(el)
            kids = node.get("/K")
            items = kids if isinstance(kids, pikepdf.Array) else ([kids] if kids is not None else [])
            for kid in items:
                if isinstance(kid, int) or (isinstance(kid, pikepdf.Object) and kid.__class__.__name__ == "Integer"):
                    if el is not None:
                        el.mcrefs.append(MCRef(page, None, int(kid)))
                elif isinstance(kid, pikepdf.Dictionary):
                    kt = _name(kid.get("/Type"))
                    if kt == "MCR":
                        if el is None:
                            continue
                        kpg = kid.get("/Pg")
                        kidx = self.page_index.get(kpg.objgen, page) if isinstance(kpg, pikepdf.Dictionary) else page
                        stm = kid.get("/Stm")
                        stm_og = stm.objgen if isinstance(stm, pikepdf.Object) and stm.objgen != (0, 0) else None
                        try:
                            el.mcrefs.append(MCRef(kidx, stm_og, int(kid.get("/MCID"))))
                        except Exception:  # noqa: BLE001
                            pass
                    elif kt == "OBJR":
                        if el is None:
                            continue
                        obj = kid.get("/Obj")
                        if isinstance(obj, pikepdf.Object) and obj.objgen != (0, 0):
                            el.objrs.append(obj.objgen)
                    else:
                        walk(kid, el if el is not None else parent, depth + 1 if el is not None else depth, page)

        walk(root, None, 0, None)
        return out

    def _attributes(self, node) -> dict:
        a = node.get("/A")
        items = a if isinstance(a, pikepdf.Array) else ([a] if a is not None else [])
        out: dict = {}
        for it in items:
            if isinstance(it, pikepdf.Dictionary):
                owner = _name(it.get("/O")) or "?"
                d = out.setdefault(owner, {})
                for k, v in it.items():
                    if k == "/O":
                        continue
                    key = k[1:]
                    if isinstance(v, pikepdf.Name):
                        d[key] = str(v)[1:]
                    elif isinstance(v, pikepdf.Array):
                        d[key] = [(_name(x) if isinstance(x, pikepdf.Name) else (str(x) if isinstance(x, pikepdf.String) else (float(x) if isinstance(x, (int, float, pikepdf.Object)) and not isinstance(x, pikepdf.Dictionary) else None))) for x in v]
                    elif isinstance(v, pikepdf.String):
                        d[key] = str(v)
                    else:
                        try:
                            d[key] = float(v) if not isinstance(v, bool) else v
                        except Exception:  # noqa: BLE001
                            d[key] = _str(v)
        return out

    @cached_property
    def mc_owners(self) -> dict[tuple, list[StructElem]]:
        """(page, stream, mcid) -> the elements that claim it. More than one is a defect."""
        out: dict[tuple, list[StructElem]] = {}
        for el in self.elements:
            for r in el.mcrefs:
                out.setdefault((r.page, r.stream, r.mcid), []).append(el)
        return out

    @cached_property
    def objr_owners(self) -> dict[tuple, list[StructElem]]:
        out: dict[tuple, list[StructElem]] = {}
        for el in self.elements:
            for og in el.objrs:
                out.setdefault(og, []).append(el)
        return out

    def elements_of(self, *types: str) -> list[StructElem]:
        want = set(types)
        return [e for e in self.elements if e.type in want]

    # ── fonts ─────────────────────────────────────────────────────────────

    @cached_property
    def fonts(self) -> dict[tuple, "fontmod.FontInfo"]:
        """Every font resource reachable from a page, keyed by objgen (or (page, name) for direct dicts)."""
        return fontmod.collect_fonts(self)

    # ── annotations ───────────────────────────────────────────────────────

    @cached_property
    def annotations(self) -> list[Annotation]:
        out = []
        for page in self.pages:
            annots = page.obj.get("/Annots")
            if not isinstance(annots, pikepdf.Array):
                continue
            for a in annots:
                if not isinstance(a, pikepdf.Dictionary):
                    continue
                sub = _name(a.get("/Subtype")) or "?"
                if sub == "Popup":
                    continue
                try:
                    rect = tuple(float(v) for v in a.get("/Rect", [0, 0, 0, 0]))
                except Exception:  # noqa: BLE001
                    rect = (0.0, 0.0, 0.0, 0.0)
                flags = int(a.get("/F", 0) or 0)
                ann = Annotation(page.index, a.objgen, sub, _str(a.get("/Contents")), flags, rect)
                ann.hidden = bool(flags & 2) or bool(flags & 32)
                if sub == "Widget":
                    node = a
                    hops = 0
                    while isinstance(node, pikepdf.Dictionary) and hops < 8:
                        if ann.field_tu is None and node.get("/TU") is not None:
                            ann.field_tu = _str(node.get("/TU"))
                        if ann.field_t is None and node.get("/T") is not None:
                            ann.field_t = _str(node.get("/T"))
                        if ann.field_ft is None and node.get("/FT") is not None:
                            ann.field_ft = _name(node.get("/FT"))
                        node = node.get("/Parent")
                        hops += 1
                out.append(ann)
        return out

    # ── page content (lazy, cached) ──────────────────────────────────────

    def content(self, page_index: int):
        from . import content as contentmod

        if page_index not in self._content_cache:
            self._content_cache[page_index] = contentmod.parse_page(self, self.pages[page_index])
        return self._content_cache[page_index]

    def fitz(self):
        """A PyMuPDF handle, opened on first use, for text words and rendering."""
        if self._fitz is None:
            try:
                import pymupdf as fitz  # noqa: PLC0415
            except ImportError:  # pragma: no cover
                import fitz  # noqa: PLC0415

            self._fitz = fitz.open(self.path)
        return self._fitz

    def close(self):
        try:
            self.pdf.close()
        except Exception:  # noqa: BLE001
            pass
        if self._fitz is not None:
            try:
                self._fitz.close()
            except Exception:  # noqa: BLE001
                pass

"""A small builder for tagged-PDF fixtures, written with pikepdf from nothing.

Each fixture is a real tagged PDF: marked content in the page stream, a
structure tree with a parent tree, an embedded subset TrueType font with a
/ToUnicode CMap, XMP metadata with dc:title and pdfuaid:part, /Lang and
/DisplayDocTitle. Every knob that a rule tests can be turned off or bent, so
a test reads as "this file has exactly one thing wrong, and the rule says so".

The builder is deliberately not general: it lays text out in a single
column, top to bottom, one block per marked-content sequence.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Optional

import pikepdf
from fontTools import subset
from fontTools.ttLib import TTFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Verdana.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def find_font() -> Optional[str]:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


@dataclass
class Block:
    kind: str                       # P | H1..H6 | H | Figure | Table | L | Link | Note | Reference | Formula | Artifact | Untagged | Form | Raw
    text: str = ""
    alt: Optional[str] = None
    actual_text: Optional[str] = None
    rows: list = field(default_factory=list)      # for tables: list of list of (kind, text)
    items: list = field(default_factory=list)     # for lists
    attrs: dict = field(default_factory=dict)     # extra attributes: Scope, Headers, ID, Lang, ...
    type_raw: Optional[str] = None                # override the /S name (for role-map tests)
    mcid_twice: bool = False                      # reference the same MCID from two elements
    no_lbody: bool = False
    li_outside: bool = False
    caption: Optional[str] = None
    url: Optional[str] = None
    contents: Optional[str] = None                # link annotation /Contents (None = omit)
    in_link_element: bool = True
    flags: int = 4
    render_mode: int = 0
    size: float = 11.0
    no_af: bool = True
    header_row: bool = True
    scope: Optional[str] = "Column"
    headers_ids: bool = False
    empty_th: bool = False
    y_band: Optional[str] = None                  # "top" | "bottom" for furniture placement


class Fixture:
    def __init__(self, title: Optional[str] = "A well-formed fixture", lang: Optional[str] = "en", marked: bool = True,
                 tagged: bool = True, display_title: bool = True, ua_part: bool = True, embed_font: bool = True,
                 suspects: bool = False, role_map: Optional[dict] = None, info_title: Optional[str] = None,
                 tounicode: bool = True, tounicode_collide: bool = False, encrypt_no_access: bool = False,
                 widths: tuple = (612, 792), no_tabs: bool = False, oc_config_no_name: bool = False, oc_as: bool = False,
                 no_cidtogid: bool = False, outlines: bool = False):
        self.title, self.lang, self.marked, self.tagged = title, lang, marked, tagged
        self.display_title, self.ua_part, self.embed_font, self.suspects = display_title, ua_part, embed_font, suspects
        self.role_map, self.info_title, self.tounicode, self.tounicode_collide = role_map or {}, info_title, tounicode, tounicode_collide
        self.encrypt_no_access = encrypt_no_access
        self.no_tabs = no_tabs
        self.oc_config_no_name, self.oc_as, self.no_cidtogid, self.outlines = oc_config_no_name, oc_as, no_cidtogid, outlines
        self.width, self.height = widths
        self.pages: list[list[Block]] = [[]]

    # ── authoring ─────────────────────────────────────────────────────────

    def page(self) -> "Fixture":
        if self.pages[-1]:
            self.pages.append([])
        return self

    def add(self, block: Block) -> "Fixture":
        self.pages[-1].append(block)
        return self

    def p(self, text: str, **kw) -> "Fixture":
        return self.add(Block("P", text, **kw))

    def h(self, level: int, text: str, **kw) -> "Fixture":
        return self.add(Block(f"H{level}" if level else "H", text, **kw))

    def figure(self, alt: Optional[str] = "A grey square, used as a sample image", **kw) -> "Fixture":
        return self.add(Block("Figure", alt=alt, **kw))

    def table(self, rows: list[list[str]], **kw) -> "Fixture":
        return self.add(Block("Table", rows=rows, **kw))

    def list(self, items: list[str], **kw) -> "Fixture":
        return self.add(Block("L", items=items, **kw))

    def link(self, text: str, url: str = "https://example.org/", contents: Optional[str] = "example.org", **kw) -> "Fixture":
        return self.add(Block("Link", text, url=url, contents=contents, **kw))

    def artifact(self, text: str, **kw) -> "Fixture":
        return self.add(Block("Artifact", text, **kw))

    def untagged(self, text: str, **kw) -> "Fixture":
        return self.add(Block("Untagged", text, **kw))

    def formula(self, text: str, alt: Optional[str] = "x squared", **kw) -> "Fixture":
        return self.add(Block("Formula", text, alt=alt, **kw))

    def note(self, text: str, **kw) -> "Fixture":
        return self.add(Block("Note", text, **kw))

    def reference(self, text: str, **kw) -> "Fixture":
        return self.add(Block("Reference", text, **kw))

    def form_text(self, text: str, tagged: bool = False, **kw) -> "Fixture":
        return self.add(Block("Form", text, attrs={"tagged": tagged}, **kw))

    # ── font ──────────────────────────────────────────────────────────────

    def _make_font(self, pdf: pikepdf.Pdf, all_text: str):
        """An embedded, subset TrueType as a Type0/Identity-H font, or plain Helvetica when embedding is off."""
        if not self.embed_font:
            f = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/Font"), Subtype=pikepdf.Name("/Type1"),
                                                     BaseFont=pikepdf.Name("/Helvetica"), Encoding=pikepdf.Name("/WinAnsiEncoding")))
            self._encode = lambda s: s.encode("cp1252", "replace")
            return f
        path = find_font()
        if path is None:
            raise RuntimeError("no TrueType font found to embed; add one to FONT_CANDIDATES")
        tt = TTFont(path)
        chars = sorted(set(all_text) | set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,:;-()/?!@'\"•"))
        opts = subset.Options(); opts.retain_gids = False; opts.notdef_outline = True; opts.name_IDs = ["*"]
        sub = subset.Subsetter(opts); sub.populate(text="".join(chars)); sub.subset(tt)
        cmap = tt.getBestCmap()
        gid_of = {ch: tt.getGlyphID(name) for ch, name in ((c, cmap.get(ord(c))) for c in chars) if name}
        upem = tt["head"].unitsPerEm
        hmtx = tt["hmtx"].metrics
        order = tt.getGlyphOrder()
        buf = io.BytesIO(); tt.save(buf); font_bytes = buf.getvalue()
        w_array = pikepdf.Array()
        for gid, name in enumerate(order):
            w_array.append(gid); w_array.append(pikepdf.Array([round(hmtx[name][0] * 1000.0 / upem)]))
        # ToUnicode
        lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap", "/CMapName /Adobe-Identity-UCS def",
                 "/CMapType 2 def", "1 begincodespacerange", "<0000> <FFFF>", "endcodespacerange"]
        entries = []
        for ch, gid in gid_of.items():
            target = ord(ch)
            if self.tounicode_collide and ch.isalpha():
                target = ord("x")
            entries.append(f"<{gid:04X}> <{target:04X}>")
        for i in range(0, len(entries), 100):
            chunk = entries[i:i + 100]
            lines.append(f"{len(chunk)} beginbfchar"); lines.extend(chunk); lines.append("endbfchar")
        lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
        tu = pdf.make_indirect(pikepdf.Stream(pdf, "\n".join(lines).encode("ascii")))
        bbox = tt["head"]
        desc = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name("/FontDescriptor"), FontName=pikepdf.Name("/AAAAAA+Fixture"), Flags=32,
            FontBBox=pikepdf.Array([int(bbox.xMin * 1000 / upem), int(bbox.yMin * 1000 / upem), int(bbox.xMax * 1000 / upem), int(bbox.yMax * 1000 / upem)]),
            ItalicAngle=0, Ascent=int(tt["hhea"].ascent * 1000 / upem), Descent=int(tt["hhea"].descent * 1000 / upem),
            CapHeight=700, StemV=80, FontFile2=pdf.make_indirect(pikepdf.Stream(pdf, font_bytes, Length1=len(font_bytes)))))
        cid = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name("/Font"), Subtype=pikepdf.Name("/CIDFontType2"), BaseFont=pikepdf.Name("/AAAAAA+Fixture"),
            CIDSystemInfo=pikepdf.Dictionary(Registry=pikepdf.String("Adobe"), Ordering=pikepdf.String("Identity"), Supplement=0),
            FontDescriptor=desc, DW=500, W=w_array))
        if not self.no_cidtogid:
            cid.CIDToGIDMap = pikepdf.Name("/Identity")
        font = pikepdf.Dictionary(Type=pikepdf.Name("/Font"), Subtype=pikepdf.Name("/Type0"), BaseFont=pikepdf.Name("/AAAAAA+Fixture"),
                                  Encoding=pikepdf.Name("/Identity-H"), DescendantFonts=pikepdf.Array([cid]))
        if self.tounicode:
            font.ToUnicode = tu
        self._gid_of = gid_of
        self._encode = lambda s: b"".join((gid_of.get(c, 0)).to_bytes(2, "big") for c in s)
        return pdf.make_indirect(font)

    # ── building ──────────────────────────────────────────────────────────

    def build(self, path: str) -> str:
        pdf = pikepdf.new()
        all_text = "".join(b.text + (b.alt or "") + "".join(c for r in b.rows for c in (x if isinstance(x, str) else x[1] for x in r)) + "".join(b.items)
                           for pg in self.pages for b in pg)
        font = self._make_font(pdf, all_text)
        image = pdf.make_indirect(pikepdf.Stream(pdf, bytes([128, 128, 128] * 4), Type=pikepdf.Name("/XObject"), Subtype=pikepdf.Name("/Image"),
                                                 Width=2, Height=2, ColorSpace=pikepdf.Name("/DeviceRGB"), BitsPerComponent=8))
        struct_root = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/StructTreeRoot")))
        document = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/StructElem"), S=pikepdf.Name("/Document"), P=struct_root, K=pikepdf.Array()))
        struct_root.K = pikepdf.Array([document])
        nums = pikepdf.Array()
        next_parent = 0
        pending_links: list = []

        for page_blocks in self.pages:
            page = pdf.add_blank_page(page_size=(self.width, self.height))
            page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font), XObject=pikepdf.Dictionary(Im1=image))
            ops: list[str] = []
            mcid = 0
            parents = pikepdf.Array()
            y = self.height - 72
            annots = pikepdf.Array()

            def elem(kind: str, parent, page_obj, **kw):
                d = pikepdf.Dictionary(Type=pikepdf.Name("/StructElem"), S=pikepdf.Name("/" + kind), P=parent, Pg=page_obj, K=pikepdf.Array())
                for k, v in kw.items():
                    if v is not None:
                        d["/" + k] = v
                e = pdf.make_indirect(d)
                parent.K.append(e)
                return e

            def text_ops(s: str, x: float, yy: float, size: float, mode: int = 0) -> str:
                hexs = self._encode(s).hex()
                return f"BT /F1 {size} Tf {mode} Tr 1 0 0 1 {x} {yy} Tm <{hexs}> Tj ET"

            def show(el, s: str, x: float, yy: float, size: float = 11.0, mode: int = 0, twice: bool = False):
                nonlocal mcid
                m = mcid; mcid += 1
                ops.append(f"/{el.S.__str__()[1:] if el is not None else 'P'} <</MCID {m}>> BDC {text_ops(s, x, yy, size, mode)} EMC")
                if el is not None:
                    el.K.append(m); parents.append(el)
                    if twice:
                        el2 = elem("Span", el.P if el.P is not None else document, page.obj)
                        el2.K.append(m)
                return m

            for b in page_blocks:
                size = b.size
                if b.y_band == "top":
                    yy = self.height - 30
                elif b.y_band == "bottom":
                    yy = 30
                else:
                    yy = y; y -= size * 1.8
                if b.kind in ("P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "Note", "Reference", "Formula", "Code", "Span") or (b.type_raw and b.kind == "P"):
                    kind = b.type_raw or b.kind
                    e = elem(kind, document, page.obj, Alt=pikepdf.String(b.alt) if b.alt is not None else None,
                             ActualText=pikepdf.String(b.actual_text) if b.actual_text is not None else None,
                             ID=pikepdf.String(b.attrs["ID"]) if "ID" in b.attrs else None,
                             Lang=pikepdf.String(b.attrs["Lang"]) if "Lang" in b.attrs else None)
                    if b.kind == "Note" and "ID" not in b.attrs and not b.attrs.get("no_id"):
                        e.ID = pikepdf.String(f"note-{mcid}")
                    if b.kind == "Formula" and not b.no_af:
                        e.AF = pikepdf.Array()
                    if b.kind == "Note" and b.attrs.get("lbl"):
                        lbl = elem("Lbl", e, page.obj); show(lbl, b.attrs["lbl"], 72, yy, size)
                        show(e, b.text, 90, yy, size, b.render_mode, b.mcid_twice)
                    elif b.text:
                        show(e, b.text, 72, yy, size, b.render_mode, b.mcid_twice)
                    # an empty block is an element with no content at all, as real files have them
                elif b.kind == "Artifact":
                    ops.append(f"/Artifact BMC {text_ops(b.text, 72, yy, size)} EMC")
                elif b.kind == "Untagged":
                    ops.append(text_ops(b.text, 72, yy, size))
                elif b.kind == "Figure":
                    e = elem("Figure", document, page.obj, Alt=pikepdf.String(b.alt) if b.alt is not None else None)
                    if b.caption:
                        cap = elem("Caption", e, page.obj)
                    m = mcid; mcid += 1
                    w = b.attrs.get("width", 120); hgt = b.attrs.get("height", 60)
                    ops.append(f"/Figure <</MCID {m}>> BDC q {w} 0 0 {hgt} 72 {yy - hgt + size} cm /Im1 Do Q EMC")
                    e.K.append(m); parents.append(e)
                    e.A = pikepdf.Dictionary(O=pikepdf.Name("/Layout"), BBox=pikepdf.Array([72, yy - hgt + size, 72 + w, yy + size]))
                    if b.caption:
                        show(cap, b.caption, 72, yy - hgt - 4, 9)
                        y -= hgt + 14
                    else:
                        y -= hgt
                elif b.kind == "Table":
                    t = elem("Table", document, page.obj)
                    ids = {}
                    for ri, row in enumerate(b.rows):
                        tr = elem("TR", t, page.obj)
                        x = 72
                        for ci, cell in enumerate(row):
                            ck, ctext = (cell if isinstance(cell, tuple) else (("TH" if (ri == 0 and b.header_row) else "TD"), cell))
                            attrs = {}
                            if ck == "TH" and b.scope:
                                attrs["Scope"] = pikepdf.Name("/" + b.scope)
                            c = elem(ck, tr, page.obj)
                            if attrs:
                                c.A = pikepdf.Dictionary(O=pikepdf.Name("/Table"), **attrs)
                            if b.headers_ids:
                                if ck == "TH":
                                    c.ID = pikepdf.String(f"h{ri}c{ci}"); ids[ci] = f"h{ri}c{ci}"
                                elif ci in ids:
                                    c.A = pikepdf.Dictionary(O=pikepdf.Name("/Table"), Headers=pikepdf.Array([pikepdf.String(ids[ci])]))
                            if ctext and not (b.empty_th and ck == "TH"):
                                show(c, ctext, x, yy, size)
                            x += 110
                        yy -= size * 1.6; y -= size * 1.6
                    if b.attrs.get("stray_child"):
                        stray = elem(b.attrs["stray_child"], t, page.obj)
                        show(stray, "A stray element inside the table", 72, yy, size)
                        yy -= size * 1.6; y -= size * 1.6
                elif b.kind == "L":
                    lst = elem("L", document, page.obj)
                    for it in b.items:
                        li = elem("LI", lst if not b.li_outside else document, page.obj)
                        lbl = elem("Lbl", li, page.obj); show(lbl, "•", 72, yy, size)
                        if b.no_lbody:
                            show(li, it, 86, yy, size)
                        else:
                            body = elem("LBody", li, page.obj); show(body, it, 86, yy, size)
                        yy -= size * 1.6; y -= size * 1.6
                elif b.kind == "Link":
                    e = elem("Link", document, page.obj, Alt=pikepdf.String(b.alt) if b.alt is not None else None) if b.in_link_element else elem("P", document, page.obj)
                    if b.text:
                        show(e, b.text, 72, yy, size)
                    wtext = 6 * len(b.text) * size / 11.0
                    annot = pikepdf.Dictionary(Type=pikepdf.Name("/Annot"), Subtype=pikepdf.Name("/Link"), Rect=pikepdf.Array([72, yy - 3, 72 + wtext, yy + size]),
                                               F=b.flags, A=pikepdf.Dictionary(S=pikepdf.Name("/URI"), URI=pikepdf.String(b.url or "https://example.org/")),
                                               Border=pikepdf.Array([0, 0, 0]))
                    if b.contents is not None:
                        annot.Contents = pikepdf.String(b.contents)
                    annot = pdf.make_indirect(annot)
                    annot.P = page.obj
                    annots.append(annot)
                    if b.in_link_element:
                        e.K.append(pikepdf.Dictionary(Type=pikepdf.Name("/OBJR"), Obj=annot, Pg=page.obj))
                        pending_links.append((annot, e))
                    else:
                        pending_links.append((annot, None))
                elif b.kind == "Form":
                    form = pdf.make_indirect(pikepdf.Stream(pdf, b"", Type=pikepdf.Name("/XObject"), Subtype=pikepdf.Name("/Form"),
                                                            BBox=pikepdf.Array([0, 0, 400, 20]), Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))))
                    inner = text_ops(b.text, 0, 4, size)
                    if b.attrs.get("tagged"):
                        e = elem("P", document, page.obj)
                        m = mcid; mcid += 1
                        e.K.append(m); parents.append(e)
                        ops.append(f"/P <</MCID {m}>> BDC q 1 0 0 1 72 {yy} cm /Fx{mcid} Do Q EMC")
                    else:
                        ops.append(f"q 1 0 0 1 72 {yy} cm /Fx{mcid} Do Q")
                    form.write(inner.encode("latin-1"))
                    page.Resources.XObject[f"/Fx{mcid}"] = form
                elif b.kind == "Raw":
                    ops.append(b.text)
                    if "claim_mcid" in b.attrs:
                        e = elem("P", document, page.obj)
                        e.K.append(int(b.attrs["claim_mcid"])); parents.append(e)
            page.Contents = pdf.make_indirect(pikepdf.Stream(pdf, "\n".join(ops).encode("latin-1")))
            if annots:
                page.Annots = annots
                if not self.no_tabs:
                    page.Tabs = pikepdf.Name("/S")
            page.StructParents = next_parent
            nums.append(next_parent); nums.append(pdf.make_indirect(parents)); next_parent += 1
            for annot, e in pending_links:
                if e is not None:
                    annot.StructParent = next_parent
                    nums.append(next_parent); nums.append(e); next_parent += 1
            pending_links = []

        struct_root.ParentTree = pdf.make_indirect(pikepdf.Dictionary(Nums=nums))
        struct_root.ParentTreeNextKey = next_parent
        if self.role_map:
            struct_root.RoleMap = pikepdf.Dictionary({"/" + k: pikepdf.Name("/" + v) for k, v in self.role_map.items()})
        if self.tagged:
            pdf.Root.StructTreeRoot = struct_root
        mi = pikepdf.Dictionary()
        if self.marked:
            mi.Marked = True
        if self.suspects:
            mi.Suspects = True
        if len(mi):
            pdf.Root.MarkInfo = mi
        if self.lang is not None:
            pdf.Root.Lang = pikepdf.String(self.lang)
        if self.display_title:
            pdf.Root.ViewerPreferences = pikepdf.Dictionary(DisplayDocTitle=True)
        if self.info_title is not None:
            pdf.docinfo["/Title"] = self.info_title
        if self.oc_config_no_name or self.oc_as:
            ocg = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/OCG"), Name=pikepdf.String("Layer 1")))
            d = pikepdf.Dictionary() if self.oc_config_no_name else pikepdf.Dictionary(Name=pikepdf.String("Default"))
            if self.oc_as:
                d.AS = pikepdf.Array([pikepdf.Dictionary(Event=pikepdf.Name("/View"), OCGs=pikepdf.Array([ocg]), Category=pikepdf.Array([pikepdf.Name("/View")]))])
            pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=pikepdf.Array([ocg]), D=d)
        if self.outlines:
            first = pdf.make_indirect(pikepdf.Dictionary(Title=pikepdf.String("Start"), Dest=pikepdf.Array([pdf.pages[0].obj, pikepdf.Name("/Fit")])))
            ol = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/Outlines"), First=first, Last=first, Count=1))
            first.Parent = ol
            pdf.Root.Outlines = ol
        xmp = ['<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>',
               '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
               '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">']
        if self.title is not None:
            xmp.append(f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{self.title}</rdf:li></rdf:Alt></dc:title>')
        if self.ua_part:
            xmp.append('<pdfuaid:part>1</pdfuaid:part>')
        xmp += ['<pdf:Producer>outloud fixture builder</pdf:Producer></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>']
        pdf.Root.Metadata = pdf.make_indirect(pikepdf.Stream(pdf, "\n".join(xmp).encode("utf-8"), Type=pikepdf.Name("/Metadata"), Subtype=pikepdf.Name("/XML")))
        if self.encrypt_no_access:
            pdf.save(path, encryption=pikepdf.Encryption(owner="owner", user="", R=4, allow=pikepdf.Permissions(accessibility=False, extract=False)))
        else:
            pdf.save(path)
        return path


def clean() -> Fixture:
    """A fixture that should pass every rule: the baseline every negative test bends."""
    fx = Fixture()
    fx.h(1, "Annual water quality report")
    fx.p("This report describes the quality of drinking water supplied to the town during the year, and what was measured each month.")
    fx.h(2, "How the samples were taken")
    fx.p("Samples were collected at the treatment works and at six points in the distribution network, then tested within a day.")
    fx.figure(alt="A map of the six sampling points along the river and the treatment works")
    fx.table([["Month", "Samples", "Passed"], ["January", "24", "24"], ["February", "22", "21"]])
    fx.list(["Chlorine residual", "Turbidity", "Coliform bacteria"])
    fx.link("Read the full method", contents="Read the full method")
    fx.formula("E = mc2", alt="E equals m c squared")
    return fx

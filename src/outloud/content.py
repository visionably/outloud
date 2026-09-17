"""The content-stream walker: what a page paints, where, and under which tag.

Every rule that compares the tags with the page needs the same three
things about each piece of painted text: its characters (decoded through
the font), its position on the page (through the text and transformation
matrices), and the marked-content sequence it sits in (through the BDC/EMC
nesting, including a /Artifact wrapper). Images and filled rectangles are
recorded the same way. Form XObjects are walked in place, with their
/Matrix applied, because their text is the page's text too; content inside
a form inherits any marked content open around the Do that draws it, and a
form's own BDC/MCID sequences are keyed by the form's stream.

Positions are in the page's user space (origin bottom-left, PDF's own
frame). Glyph advances use the font's /Widths or /W, so bounding boxes are
close to what a viewer draws; they are not exact for Type3 fonts or
vertical writing, which is acceptable for the questions the rules ask.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pikepdf

from .fonts import FontInfo, font_info

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mul(a: Matrix, b: Matrix) -> Matrix:
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


@dataclass
class Marked:
    """One open marked-content sequence."""

    tag: str
    mcid: Optional[int]
    stream: Optional[tuple]   # None = page stream; objgen of the form otherwise
    artifact: bool


@dataclass
class TextRun:
    text: str
    bbox: tuple                     # x0, y0, x1, y1 in page user space
    mcid: Optional[int]
    stream: Optional[tuple]
    artifact: bool
    tag: Optional[str]              # innermost marked-content tag, e.g. "P", "Artifact", or None
    font: Optional[FontInfo]
    size: float
    render_mode: int
    in_form: bool
    order: int                      # paint order on the page

    @property
    def tagged(self) -> bool:
        return self.mcid is not None

    @property
    def key(self) -> Optional[tuple]:
        return None if self.mcid is None else (self.stream, self.mcid)


@dataclass
class ImageDraw:
    name: str
    bbox: tuple
    mcid: Optional[int]
    stream: Optional[tuple]
    artifact: bool
    width_px: int
    height_px: int
    in_form: bool
    order: int


@dataclass
class PathDraw:
    bbox: tuple
    mcid: Optional[int]
    artifact: bool
    kind: str                       # "rect" | "line" | "path"
    stroked: bool
    filled: bool
    order: int


@dataclass
class PageContent:
    page: int
    runs: list[TextRun] = field(default_factory=list)
    images: list[ImageDraw] = field(default_factory=list)
    paths: list[PathDraw] = field(default_factory=list)
    mcid_text: dict = field(default_factory=dict)       # (stream, mcid) -> text
    mcid_bbox: dict = field(default_factory=dict)       # (stream, mcid) -> bbox
    paint_order: list = field(default_factory=list)     # (stream, mcid) in first-paint order
    parse_error: Optional[str] = None
    lines: list = field(default_factory=list)           # Line objects, top of page first
    raw_run_count: int = 0
    nesting_events: list = field(default_factory=list)  # (stream, mcid) involved in an Artifact/MCID nesting
    notdef_shown: int = 0                               # glyph 0 of a composite font shown

    @property
    def text(self) -> str:
        return " ".join(r.text for r in self.runs if r.text.strip())

    def untagged_runs(self) -> list[TextRun]:
        return [r for r in self.runs if r.mcid is None and not r.artifact and r.text.strip()]

    def artifact_runs(self) -> list[TextRun]:
        return [r for r in self.runs if r.artifact and r.text.strip()]


def _union(a: Optional[tuple], b: tuple) -> tuple:
    if a is None:
        return b
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


class _State:
    __slots__ = ("ctm", "font", "size", "tc", "tw", "tz", "tl", "ts", "tr")

    def __init__(self, ctm: Matrix):
        self.ctm = ctm
        self.font: Optional[FontInfo] = None
        self.size = 0.0
        self.tc = 0.0
        self.tw = 0.0
        self.tz = 1.0
        self.tl = 0.0
        self.ts = 0.0
        self.tr = 0

    def copy(self) -> "_State":
        s = _State(self.ctm)
        s.font, s.size, s.tc, s.tw, s.tz, s.tl, s.ts, s.tr = self.font, self.size, self.tc, self.tw, self.tz, self.tl, self.ts, self.tr
        return s


class _Walker:
    def __init__(self, doc, page):
        self.doc = doc
        self.page = page
        self.out = PageContent(page.index)
        self.order = 0
        self.font_cache: dict[tuple, FontInfo] = {}

    # ── fonts ─────────────────────────────────────────────────────────────

    def font_for(self, res, name: str) -> Optional[FontInfo]:
        fonts = res.get("/Font") if isinstance(res, pikepdf.Dictionary) else None
        if not isinstance(fonts, pikepdf.Dictionary):
            return None
        font = fonts.get(name)
        if not isinstance(font, pikepdf.Dictionary):
            return None
        key = font.objgen if font.objgen != (0, 0) else (self.page.index, name)
        fi = self.doc.fonts.get(key)
        if fi is None:
            fi = self.font_cache.get(key)
            if fi is None:
                fi = font_info(font, key)
                self.font_cache[key] = fi
        fi.pages.add(self.page.index)
        return fi

    # ── marked content ────────────────────────────────────────────────────

    @staticmethod
    def current(mstack: list[Marked]) -> tuple[Optional[int], Optional[tuple], bool, Optional[str]]:
        mcid, stream, artifact, tag = None, None, False, None
        for m in mstack:
            if m.artifact:
                artifact = True
            if m.mcid is not None:
                mcid, stream = m.mcid, m.stream
            tag = m.tag
        return mcid, stream, artifact, tag

    # ── text ──────────────────────────────────────────────────────────────

    def show(self, st: _State, tm: Matrix, raw_items, mstack, in_form) -> Matrix:
        """Decode and place one Tj/TJ; returns the advanced text matrix.

        Two things about real files shape this: the font size is often 1 with
        the real scale carried by Tm, so the run's size is the rendered size
        (text-space size times the matrix scale); and TeX, many typesetters
        and OCR layers make word gaps with TJ adjustments instead of space
        glyphs, so an adjustment that moves the pen more than an eighth of an
        em becomes a space in the text.
        """
        fi = st.font
        size = st.size
        m_full = mul(tm, st.ctm)
        scale = (m_full[0] * m_full[0] + m_full[1] * m_full[1]) ** 0.5 or 1.0
        eff_size = abs(size) * scale
        pieces = []
        x_adv = 0.0
        bbox: Optional[tuple] = None
        for item in raw_items:
            if isinstance(item, pikepdf.String):
                raw = bytes(item)
                text = fi.decode(raw) if fi is not None else raw.decode("latin-1", "replace")
                codes = list(raw) if (fi is None or fi.code_width <= 1) else [
                    int.from_bytes(raw[i:i + fi.code_width], "big") for i in range(0, len(raw) - (fi.code_width - 1), fi.code_width)]
                start = x_adv
                if fi is not None and fi.code_width == 2 and 0 in codes:
                    self.out.notdef_shown += codes.count(0)
                for code in codes:
                    w0 = (fi.width_of(code) if fi is not None else 500.0) / 1000.0
                    adv = (w0 * size + st.tc + (st.tw if code == 32 and (fi is None or fi.code_width == 1) else 0.0)) * st.tz
                    x_adv += adv
                pieces.append(text)
                # box in text space: from start to x_adv, ascent/descent scaled by size
                asc = (fi.ascent if fi else 0.9) * size
                desc = (fi.descent if fi else -0.2) * size
                m = mul(tm, st.ctm)
                corners = [apply(m, start, desc + st.ts), apply(m, x_adv, desc + st.ts), apply(m, start, asc + st.ts), apply(m, x_adv, asc + st.ts)]
                xs = [c[0] for c in corners]
                ys = [c[1] for c in corners]
                bbox = _union(bbox, (min(xs), min(ys), max(xs), max(ys)))
            else:
                try:
                    adj = float(item)
                except Exception:  # noqa: BLE001
                    continue
                x_adv -= adj / 1000.0 * size * st.tz
                if adj <= -130 and pieces and not pieces[-1].endswith(" "):
                    pieces.append(" ")
        text = "".join(pieces)
        if text:
            mcid, stream, artifact, tag = self.current(mstack)
            run = TextRun(text, bbox or (0, 0, 0, 0), mcid, stream, artifact, tag, fi, eff_size, st.tr, in_form, self.order)
            self.order += 1
            self.out.runs.append(run)
            if mcid is not None:
                key = (stream, mcid)
                self.out.mcid_text[key] = self.out.mcid_text.get(key, "") + text
                self.out.mcid_bbox[key] = _union(self.out.mcid_bbox.get(key), run.bbox)
                if key not in self.out.paint_order:
                    self.out.paint_order.append(key)
        return mul((1.0, 0.0, 0.0, 1.0, x_adv, 0.0), tm)

    # ── the walk ──────────────────────────────────────────────────────────

    def walk(self, stream_obj, res, ctm: Matrix, mstack: list[Marked], stream_key: Optional[tuple], in_form: bool, depth: int, seen: set):
        if depth > 12:
            return
        try:
            ops = pikepdf.parse_content_stream(stream_obj)
        except Exception as exc:  # noqa: BLE001
            if self.out.parse_error is None:
                self.out.parse_error = f"{type(exc).__name__}: {exc}"[:160]
            return
        st = _State(ctm)
        gs_stack: list[_State] = []
        tm = tlm = IDENTITY
        local_depth = 0    # BDC/BMC opened inside this stream, so EMC cannot pop the caller's
        path_pts: list[tuple] = []
        path_kind = "path"
        path_ops = 0
        for operands, operator in ops:
            op = str(operator)
            try:
                # Ordered by frequency: a glyph-per-operator page is thousands of
                # Tm/Tj pairs wrapped in BDC/EMC, and the chain is walked per operator.
                if op == "Tj":
                    if operands:
                        tm = self.show(st, tm, [operands[0]], mstack, in_form)
                elif op == "Tm":
                    if len(operands) == 6:
                        tm = tlm = (float(operands[0]), float(operands[1]), float(operands[2]), float(operands[3]), float(operands[4]), float(operands[5]))
                elif op == "TJ":
                    if operands:
                        arr = operands[0]
                        items = list(arr) if isinstance(arr, pikepdf.Array) else [arr]
                        tm = self.show(st, tm, items, mstack, in_form)
                elif op == "BDC" or op == "BMC":
                    tag = str(operands[0])[1:] if operands else "?"
                    mcid = None
                    if op == "BDC" and len(operands) >= 2:
                        props = operands[1]
                        if isinstance(props, pikepdf.Name):
                            props = (res.get("/Properties") or {}).get(str(props)) if isinstance(res, pikepdf.Dictionary) else None
                        if isinstance(props, pikepdf.Dictionary) and props.get("/MCID") is not None:
                            try:
                                mcid = int(props.get("/MCID"))
                            except Exception:  # noqa: BLE001
                                mcid = None
                    if mcid is not None and any(m.artifact for m in mstack):
                        self.out.nesting_events.append((stream_key, mcid))
                    elif tag == "Artifact":
                        outer = next((m for m in reversed(mstack) if m.mcid is not None), None)
                        if outer is not None:
                            self.out.nesting_events.append((outer.stream, outer.mcid))
                    mstack.append(Marked(tag, mcid, stream_key if mcid is not None else None, tag == "Artifact"))
                    local_depth += 1
                elif op == "EMC":
                    if local_depth > 0 and mstack:
                        mstack.pop()
                        local_depth -= 1
                elif op == "Td" or op == "TD":
                    if len(operands) == 2:
                        tx, ty = float(operands[0]), float(operands[1])
                        if op == "TD":
                            st.tl = -ty
                        tm = tlm = mul((1.0, 0.0, 0.0, 1.0, tx, ty), tlm)
                elif op == "q":
                    gs_stack.append(st.copy())
                elif op == "Q":
                    if gs_stack:
                        st = gs_stack.pop()
                elif op == "cm" and len(operands) == 6:
                    st.ctm = mul(tuple(float(v) for v in operands), st.ctm)
                elif op == "BT":
                    tm = tlm = IDENTITY
                elif op == "ET":
                    pass
                elif op == "Tf" and len(operands) >= 2:
                    st.font = self.font_for(res, str(operands[0]))
                    st.size = float(operands[1])
                elif op == "Tc" and operands:
                    st.tc = float(operands[0])
                elif op == "Tw" and operands:
                    st.tw = float(operands[0])
                elif op == "Tz" and operands:
                    st.tz = float(operands[0]) / 100.0
                elif op == "TL" and operands:
                    st.tl = float(operands[0])
                elif op == "Ts" and operands:
                    st.ts = float(operands[0])
                elif op == "Tr" and operands:
                    st.tr = int(operands[0])
                elif op == "T*":
                    tm = tlm = mul((1.0, 0.0, 0.0, 1.0, 0.0, -st.tl), tlm)
                elif op == "'" and operands:
                    tm = tlm = mul((1.0, 0.0, 0.0, 1.0, 0.0, -st.tl), tlm)
                    tm = self.show(st, tm, [operands[-1]], mstack, in_form)
                elif op == '"' and len(operands) == 3:
                    st.tw, st.tc = float(operands[0]), float(operands[1])
                    tm = tlm = mul((1.0, 0.0, 0.0, 1.0, 0.0, -st.tl), tlm)
                    tm = self.show(st, tm, [operands[2]], mstack, in_form)
                elif op == "Do" and operands:
                    name = str(operands[0])
                    xobjs = res.get("/XObject") if isinstance(res, pikepdf.Dictionary) else None
                    xo = xobjs.get(name) if isinstance(xobjs, pikepdf.Dictionary) else None
                    if isinstance(xo, pikepdf.Stream):
                        sub = str(xo.get("/Subtype"))
                        if sub == "/Image":
                            mcid, stream, artifact, _tag = self.current(mstack)
                            corners = [apply(st.ctm, 0, 0), apply(st.ctm, 1, 0), apply(st.ctm, 0, 1), apply(st.ctm, 1, 1)]
                            bbox = (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))
                            self.out.images.append(ImageDraw(name[1:], bbox, mcid, stream, artifact,
                                                             int(xo.get("/Width", 0) or 0), int(xo.get("/Height", 0) or 0), in_form, self.order))
                            self.order += 1
                            if mcid is not None:
                                key = (stream, mcid)
                                self.out.mcid_bbox[key] = _union(self.out.mcid_bbox.get(key), bbox)
                                if key not in self.out.paint_order:
                                    self.out.paint_order.append(key)
                        elif sub == "/Form":
                            og = xo.objgen
                            if og in seen:
                                continue
                            seen.add(og)
                            mtx = xo.get("/Matrix")
                            fm = tuple(float(v) for v in mtx) if isinstance(mtx, pikepdf.Array) and len(mtx) == 6 else IDENTITY
                            fres = xo.get("/Resources") if xo.get("/Resources") is not None else res
                            self.walk(xo, fres, mul(fm, st.ctm), mstack, og if og != (0, 0) else stream_key, True, depth + 1, seen)
                            seen.discard(og)
                elif op in ("m", "l") and len(operands) == 2:
                    path_pts.append(apply(st.ctm, float(operands[0]), float(operands[1])))
                    path_ops += 1
                elif op == "re" and len(operands) == 4:
                    x, y, w, h = (float(v) for v in operands)
                    for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                        path_pts.append(apply(st.ctm, px, py))
                    path_kind = "rect" if path_ops == 0 else "path"
                    path_ops += 1
                elif op in ("c", "v", "y"):
                    pts = [float(v) for v in operands]
                    for i in range(0, len(pts) - 1, 2):
                        path_pts.append(apply(st.ctm, pts[i], pts[i + 1]))
                    path_kind = "path"
                    path_ops += 1
                elif op in ("S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n"):
                    if path_pts and op != "n":
                        xs = [p[0] for p in path_pts]
                        ys = [p[1] for p in path_pts]
                        bbox = (min(xs), min(ys), max(xs), max(ys))
                        kind = path_kind
                        if kind == "path" and path_ops <= 2 and len(path_pts) == 2:
                            kind = "line"
                        mcid, _stream, artifact, _tag = self.current(mstack)
                        stroked = op in ("S", "s", "B", "B*", "b", "b*")
                        filled = op in ("f", "F", "f*", "B", "B*", "b", "b*")
                        self.out.paths.append(PathDraw(bbox, mcid, artifact, kind, stroked, filled, self.order))
                        self.order += 1
                    path_pts, path_kind, path_ops = [], "path", 0
                elif op == "W" or op == "W*":
                    pass
            except Exception:  # noqa: BLE001 — one bad operator must not lose the page
                continue
        # a stream that opened marked content and never closed it: close it here
        while local_depth > 0 and mstack:
            mstack.pop()
            local_depth -= 1


def _same_line(a: TextRun, b: TextRun) -> bool:
    size = max(a.size, b.size, 1.0)
    ay = (a.bbox[1] + a.bbox[3]) / 2.0
    by = (b.bbox[1] + b.bbox[3]) / 2.0
    return abs(ay - by) <= 0.5 * size


def merge_runs(runs: list[TextRun]) -> list[TextRun]:
    """Join glyph-by-glyph text operators into word- and line-sized runs.

    Chrome, Skia, many PDF printers and every OCR layer write one Tj per
    glyph, so a "run" would otherwise be a single character and no rule could
    find a word. Adjacent runs on one baseline with the same tag, font, size
    and render mode become one run; a horizontal gap wider than a quarter em
    becomes a space so words stay separable.
    """
    out: list[TextRun] = []
    for r in runs:
        if out:
            p = out[-1]
            same_key = (p.mcid, p.stream, p.artifact, p.tag, p.font is r.font, round(p.size, 2), p.render_mode, p.in_form) == \
                       (r.mcid, r.stream, r.artifact, r.tag, True, round(r.size, 2), r.render_mode, r.in_form)
            if same_key and _same_line(p, r):
                size = max(p.size, 1.0)
                gap = r.bbox[0] - p.bbox[2]
                # A negative gap is a glyph whose advance the width table
                # overstated (a ligature with no /W entry); as long as the run
                # still moves rightward it is the same word. A gap wider than
                # 1.2 em is a jump to another column and stays separate.
                if r.bbox[0] >= p.bbox[0] - 0.1 * size and gap <= 1.2 * size:
                    sep = " " if gap > 0.13 * size and not p.text.endswith(" ") and not r.text.startswith(" ") else ""
                    p.text = p.text + sep + r.text
                    p.bbox = (min(p.bbox[0], r.bbox[0]), min(p.bbox[1], r.bbox[1]), max(p.bbox[2], r.bbox[2]), max(p.bbox[3], r.bbox[3]))
                    continue
        out.append(TextRun(r.text, r.bbox, r.mcid, r.stream, r.artifact, r.tag, r.font, r.size, r.render_mode, r.in_form, r.order))
    return out


@dataclass
class Line:
    """Runs that share a baseline, left to right: what a sighted reader sees as one line."""

    runs: list[TextRun]

    @property
    def text(self) -> str:
        parts = []
        for i, r in enumerate(self.runs):
            if i and parts:
                gap = r.bbox[0] - self.runs[i - 1].bbox[2]
                if gap > 0.15 * max(r.size, 1.0) and not parts[-1].endswith(" ") and not r.text.startswith(" "):
                    parts.append(" ")
            parts.append(r.text)
        return "".join(parts)

    @property
    def bbox(self) -> tuple:
        return (min(r.bbox[0] for r in self.runs), min(r.bbox[1] for r in self.runs),
                max(r.bbox[2] for r in self.runs), max(r.bbox[3] for r in self.runs))

    @property
    def artifact_share(self) -> float:
        total = sum(len(r.text) for r in self.runs) or 1
        return sum(len(r.text) for r in self.runs if r.artifact) / total

    @property
    def tagged_share(self) -> float:
        total = sum(len(r.text) for r in self.runs) or 1
        return sum(len(r.text) for r in self.runs if r.tagged and not r.artifact) / total


def lines_of(runs: list[TextRun]) -> list[Line]:
    """Group runs into lines by baseline, top of page first, left to right within a line."""
    items = [r for r in runs if r.text.strip()]
    items.sort(key=lambda r: (-(r.bbox[1] + r.bbox[3]) / 2.0, r.bbox[0]))
    lines: list[list[TextRun]] = []
    for r in items:
        if lines and _same_line(lines[-1][-1], r) and abs(((lines[-1][-1].bbox[1] + lines[-1][-1].bbox[3]) / 2) - ((r.bbox[1] + r.bbox[3]) / 2)) <= 0.5 * max(r.size, 1.0):
            lines[-1].append(r)
        else:
            lines.append([r])
    out = []
    for ln in lines:
        ln.sort(key=lambda r: r.bbox[0])
        out.append(Line(ln))
    return out


def parse_page(doc, page) -> PageContent:
    w = _Walker(doc, page)
    res = page.obj.get("/Resources")
    if not isinstance(res, pikepdf.Dictionary):
        res = pikepdf.Dictionary()
    w.walk(page.obj, res, IDENTITY, [], None, False, 0, set())
    pc = w.out
    pc.raw_run_count = len(pc.runs)
    pc.runs = merge_runs(pc.runs)
    # Rebuild the per-MCID text from merged runs so evidence reads as words.
    texts: dict = {}
    for r in pc.runs:
        if r.mcid is not None:
            key = (r.stream, r.mcid)
            prev = texts.get(key)
            texts[key] = r.text if prev is None else (prev + ("" if prev.endswith(" ") or r.text.startswith(" ") else " ") + r.text)
    pc.mcid_text = texts
    pc.lines = lines_of(pc.runs)
    return pc

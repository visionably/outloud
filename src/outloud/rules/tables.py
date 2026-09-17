"""Table rules: can a reader tell which header each cell belongs to, and is the grid the one on the page."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Document, StructElem
from ..registry import finding, rule
from ._common import boxes_for, box, element_bbox, element_page, element_text, sample, words

ROW_GROUPS = {"THead", "TBody", "TFoot"}


@dataclass
class Cell:
    el: StructElem
    kind: str            # TH | TD
    text: str
    colspan: int = 1
    rowspan: int = 1
    scope: str | None = None
    headers: list = field(default_factory=list)
    id: str | None = None


@dataclass
class Grid:
    table: StructElem
    rows: list[list[Cell]]

    @property
    def cells(self):
        return [c for r in self.rows for c in r]

    def row_widths(self) -> list[int]:
        """Columns occupied per row once spans are applied."""
        widths = []
        carry: dict[int, int] = {}   # column -> remaining rowspan
        for row in self.rows:
            col = 0
            occupied = 0
            for c in row:
                while carry.get(col, 0) > 0:
                    col += 1
                    occupied += 1
                col += c.colspan
                occupied += c.colspan
                if c.rowspan > 1:
                    for k in range(col - c.colspan, col):
                        carry[k] = c.rowspan
            for k in list(carry):
                carry[k] -= 1
                if carry[k] <= 0:
                    del carry[k]
            widths.append(occupied + sum(1 for k, v in carry.items() if k >= col and v > 0))
        return widths


def _int(v, default=1) -> int:
    try:
        return max(1, int(float(v)))
    except Exception:  # noqa: BLE001
        return default


def grid_of(doc: Document, table: StructElem) -> Grid:
    rows: list[list[Cell]] = []

    def rows_under(node):
        for ch in node.logical_children:
            if ch.type == "TR":
                yield ch
            elif ch.type in ROW_GROUPS:
                yield from rows_under(ch)

    for tr in rows_under(table):
        cells = []
        for ch in tr.logical_children:
            if ch.type in ("TH", "TD"):
                headers = ch.attr("Headers", "Table")
                cells.append(Cell(ch, ch.type, " ".join(element_text(doc, ch).split()),
                                  _int(ch.attr("ColSpan", "Table")), _int(ch.attr("RowSpan", "Table")),
                                  ch.attr("Scope", "Table"), list(headers) if isinstance(headers, list) else [], ch.id))
        rows.append(cells)
    return Grid(table, rows)


def grids(doc: Document):
    return [grid_of(doc, t) for t in doc.elements_of("Table")]


@rule("TBL-001")
def no_headers(doc: Document):
    for g in grids(doc):
        cells = g.cells
        if not cells:
            continue
        if not any(c.kind == "TH" for c in cells) and not any(c.headers for c in cells):
            if len(cells) >= 2:
                yield finding("TBL-001", f"a table of {len(g.rows)} row(s) and {len(cells)} cell(s) has no header cell",
                              page=element_page(g.table), evidence=sample((c.text for c in cells if c.text), 3, 30),
                              location={"element": g.table.path}, boxes=boxes_for(doc, [g.table]))


@rule("TBL-002")
def headers_without_scope(doc: Document):
    for g in grids(doc):
        cells = g.cells
        referenced = {h for c in cells for h in c.headers}
        loose = [c for c in cells if c.kind == "TH" and not c.scope and (c.id is None or c.id not in referenced)]
        if loose and len(g.rows) > 1:
            yield finding("TBL-002", f"{len(loose)} header cell(s) carry no /Scope and are not referenced by any /Headers",
                          page=element_page(g.table), count=len(loose), evidence=sample((c.text for c in loose if c.text), 3, 30),
                          location={"element": g.table.path}, boxes=boxes_for(doc, [c.el for c in loose]))


@rule("TBL-003")
def cells_outside_rows(doc: Document):
    bad_cells = [el for el in doc.elements if el.type in ("TH", "TD") and (el.logical_parent is None or el.logical_parent.type != "TR")]
    bad_rows = [el for el in doc.elements if el.type == "TR" and (el.logical_parent is None or el.logical_parent.type not in ROW_GROUPS | {"Table"})]
    if bad_cells:
        yield finding("TBL-003", f"{len(bad_cells)} table cell(s) are not inside a /TR", page=element_page(bad_cells[0]),
                      count=len(bad_cells), location={"first": bad_cells[0].path}, boxes=boxes_for(doc, bad_cells))
    if bad_rows:
        yield finding("TBL-003", f"{len(bad_rows)} /TR element(s) are not inside a /Table", page=element_page(bad_rows[0]),
                      count=len(bad_rows), location={"first": bad_rows[0].path}, boxes=boxes_for(doc, bad_rows))


_TABLE_KIDS = {"TR", "THead", "TBody", "TFoot", "Caption"}


@rule("TBL-005")
def misnested(doc: Document):
    for t in doc.elements_of("Table"):
        kids = t.logical_children
        problems = []
        strays = [k for k in kids if k.type not in _TABLE_KIDS]
        if strays:
            problems.append(f"{len(strays)} child element(s) that are not rows, row groups or a caption ({', '.join(sorted({k.type for k in strays})[:4])})")
        heads = [k for k in kids if k.type == "THead"]
        foots = [k for k in kids if k.type == "TFoot"]
        bodies = [k for k in kids if k.type == "TBody"]
        if len(heads) > 1:
            problems.append(f"{len(heads)} THead groups")
        if len(foots) > 1:
            problems.append(f"{len(foots)} TFoot groups")
        if (heads or foots) and not bodies:
            problems.append("a THead or TFoot with no TBody")
        caps = [i for i, k in enumerate(kids) if k.type == "Caption"]
        if len(caps) > 1 or (caps and caps[0] not in (0, len(kids) - 1)):
            problems.append("a Caption that is not the first or last child")
        group_strays = [g for g in kids if g.type in ("THead", "TBody", "TFoot") for c in g.logical_children if c.type != "TR"]
        if group_strays:
            problems.append(f"{len(group_strays)} non-row child(ren) inside a row group")
        if problems:
            yield finding("TBL-005", "table has " + "; ".join(problems), page=element_page(t), location={"element": t.path},
                          boxes=boxes_for(doc, [t]), evidence=sample((k.type for k in strays), 3, 20) if strays else None)


@rule("TBL-004")
def irregular(doc: Document):
    for g in grids(doc):
        if len(g.rows) < 2:
            continue
        widths = g.row_widths()
        if len(set(widths)) > 1:
            yield finding("TBL-004", f"rows occupy different numbers of columns ({min(widths)} to {max(widths)}); the grid does not close",
                          page=element_page(g.table), evidence=", ".join(map(str, widths[:12])), location={"element": g.table.path}, boxes=boxes_for(doc, [g.table]))


@rule("TBL-010")
def shredded_headers(doc: Document):
    for g in grids(doc):
        cells = g.cells
        th = [c for c in cells if c.kind == "TH"]
        td = [c for c in cells if c.kind == "TD"]
        if len(cells) < 6 or not th:
            continue
        header_rows = [r for r in g.rows if r and all(c.kind == "TH" for c in r)]
        single = [c for r in header_rows for c in r if c.text and len(words(c.text)) == 1]
        filled = [c for r in header_rows for c in r if c.text]
        reasons = []
        if len(th) > len(td) and td:
            reasons.append(f"{len(th)} header cells against {len(td)} data cells")
        if len(header_rows) > 3:
            reasons.append(f"{len(header_rows)} header rows")
        if filled and len(single) / len(filled) >= 0.8 and len(header_rows) >= 3:
            reasons.append("header rows of single words")
        if len(reasons) >= 1 and (len(header_rows) > 3 or len(th) > len(td)):
            yield finding("TBL-010", "header cells look shredded: " + "; ".join(reasons), page=element_page(g.table),
                          evidence=sample((c.text for c in single), 6, 16), location={"element": g.table.path}, boxes=boxes_for(doc, [g.table]))


@rule("TBL-011")
def silent_headers(doc: Document):
    for g in grids(doc):
        by_id = {c.id: c for c in g.cells if c.id}
        silent_cells = []
        for c in g.cells:
            if c.kind != "TD" or not c.headers:
                continue
            refs = [by_id.get(h) for h in c.headers]
            refs = [r for r in refs if r is not None]
            if refs and all(not r.text for r in refs):
                silent_cells.append(c.el)
        silent = len(silent_cells)
        if silent:
            yield finding("TBL-011", f"{silent} data cell(s) are associated only with empty header cells", page=element_page(g.table),
                          count=silent, location={"element": g.table.path}, boxes=boxes_for(doc, silent_cells))


@rule("TBL-012")
def mostly_empty(doc: Document):
    for g in grids(doc):
        cells = g.cells
        if len(cells) < 6:
            continue
        empty = sum(1 for c in cells if not c.text)
        if empty / len(cells) > 0.6:
            yield finding("TBL-012", f"{empty} of {len(cells)} cells are empty; this may not be a table", page=element_page(g.table),
                          location={"element": g.table.path}, boxes=boxes_for(doc, [g.table]))


@rule("TBL-013")
def split_tables(doc: Document):
    tables = doc.elements_of("Table")
    for a, b in zip(tables, tables[1:]):
        if a.logical_parent is not b.logical_parent or a.page != b.page or a.page is None:
            continue
        sibs = a.logical_parent.logical_children if a.logical_parent else []
        try:
            ia, ib = sibs.index(a), sibs.index(b)
        except ValueError:
            continue
        if ib != ia + 1:
            continue
        ba, bb = element_bbox(doc, a), element_bbox(doc, b)
        if not ba or not bb:
            continue
        v_overlap = min(ba[3], bb[3]) - max(ba[1], bb[1])
        height = min(ba[3] - ba[1], bb[3] - bb[1]) or 1.0
        gap = max(bb[0] - ba[2], ba[0] - bb[2])
        if v_overlap / height >= 0.5 and gap < 24:
            yield finding("TBL-013", "two tables sit side by side on one page with no text between them; one table may have been split",
                          page=a.page + 1, location={"first": a.path, "second": b.path}, boxes=boxes_for(doc, [a, b]))


@rule("TBL-014")
def drawn_grid_untagged(doc: Document):
    for page in doc.pages:
        pc = doc.content(page.index)
        hz, vt = [], []
        for p in pc.paths:
            if not p.stroked and not p.filled:
                continue
            w, h = p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]
            if h <= 2.5 and w >= 40:
                hz.append(p.bbox)
            elif w <= 2.5 and h >= 12:
                vt.append(p.bbox)
        if len(hz) < 3 or len(vt) < 3:
            continue
        # A grid is lines that CROSS: keep horizontals crossed by two or more
        # verticals and verticals crossing two or more horizontals, so a chart's
        # gridlines beside a table do not stretch the region over the chart.
        def crosses(h, v):
            return h[0] - 1 <= v[0] <= h[2] + 1 and v[1] - 1 <= h[1] <= v[3] + 1
        hz_k = [h for h in hz if sum(1 for v in vt if crosses(h, v)) >= 2]
        vt_k = [v for v in vt if sum(1 for h in hz_k if crosses(h, v)) >= 2]
        if len(hz_k) < 3 or len(vt_k) < 3:
            continue
        x0 = min(b[0] for b in hz_k); x1 = max(b[2] for b in hz_k)
        y0 = min(b[1] for b in vt_k); y1 = max(b[3] for b in vt_k)
        if x1 - x0 < 100 or y1 - y0 < 30:
            continue
        inside = [ln for ln in pc.lines if x0 - 2 <= ln.bbox[0] and ln.bbox[2] <= x1 + 2 and y0 - 2 <= ln.bbox[1] and ln.bbox[3] <= y1 + 2]
        if len(inside) < 4 or sum(len(words(ln.text)) for ln in inside) < 8:
            continue
        covered = False
        for t in doc.elements_of("Table"):
            if t.page != page.index:
                continue
            tb = element_bbox(doc, t)
            if not tb:
                continue
            ix = max(0.0, min(tb[2], x1) - max(tb[0], x0)); iy = max(0.0, min(tb[3], y1) - max(tb[1], y0))
            if ix * iy / ((x1 - x0) * (y1 - y0)) >= 0.5:
                covered = True
                break
        if not covered and any(ln.tagged_share > 0 for ln in inside):
            yield finding("TBL-014", f"a ruled grid ({len(hz_k)} horizontal, {len(vt_k)} vertical lines) holds {len(inside)} line(s) of text that no /Table covers",
                          page=page.number, evidence=sample((ln.text for ln in inside), 3, 40), boxes=[box(page.index, (x0, y0, x1, y1))])


@rule("TBL-015")
def collapsed_rows(doc: Document):
    for g in grids(doc):
        if len(g.rows) < 3:
            continue
        maxcols = max(len(r) for r in g.rows)
        if maxcols < 3:
            continue
        multi = sum(1 for r in g.rows if sum(1 for c in r if c.text) >= 2)
        collapsed = [r for r in g.rows if len(r) == 1 and r[0].text and len(words(r[0].text)) >= 4 and r[0].colspan < maxcols]
        if multi >= 2 and len(collapsed) >= 2:
            yield finding("TBL-015", f"{len(collapsed)} row(s) put all their content in a single cell while other rows have several",
                          page=element_page(g.table), count=len(collapsed), evidence=sample((r[0].text for r in collapsed), 2, 60),
                          location={"element": g.table.path}, boxes=boxes_for(doc, [r[0].el for r in collapsed]))

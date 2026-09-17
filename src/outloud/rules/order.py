"""Reading-order rules: the tag tree says one order, the content stream paints another."""

from __future__ import annotations

from bisect import bisect_left

from ..model import Document
from ..registry import finding, rule


def _longest_increasing(seq: list[int]) -> int:
    tails: list[int] = []
    for v in seq:
        i = bisect_left(tails, v)
        if i == len(tails):
            tails.append(v)
        else:
            tails[i] = v
    return len(tails)


@rule("ORD-001")
def physical_vs_logical(doc: Document):
    if doc.struct_root is None:
        return
    logical: dict[int, list[tuple]] = {}
    for el in doc.elements:
        for r in el.mcrefs:
            if r.page is None:
                continue
            logical.setdefault(r.page, []).append((r.stream, r.mcid))
    worst = None
    scrambled = 0
    for page in doc.pages:
        want = logical.get(page.index) or []
        if len(want) < 4:
            continue
        pc = doc.content(page.index)
        rank = {k: i for i, k in enumerate(want)}
        painted = [rank[k] for k in pc.paint_order if k in rank]
        if len(painted) < 4:
            continue
        in_place = _longest_increasing(painted)
        share = in_place / len(painted)
        if share < 0.8:
            scrambled += 1
            if worst is None or share < worst[1]:
                worst = (page.number, share, len(painted) - in_place, len(painted))
    if scrambled:
        page, share, moved, total = worst
        yield finding("ORD-001", f"{scrambled} page(s) paint tagged content out of tag-tree order; worst is page {page}, "
                                 f"where {moved} of {total} sequences are out of place ({round(share * 100)}% in order)",
                      page=page, count=scrambled)

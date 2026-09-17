"""Pagination rules: running heads and folios belong in artifacts, not in the reading order."""

from __future__ import annotations

import collections
import re

from ..model import Document
from ..registry import finding, rule
from ._common import box, sample

_BARE_NUMBER = re.compile(r"^\s*(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?\s*$", re.I)


@rule("PAG-001")
def furniture_tagged(doc: Document):
    if doc.struct_root is None or len(doc.pages) < 3:
        return
    pages_by_key: dict[str, set[int]] = collections.defaultdict(set)
    samples: dict[str, str] = {}
    sboxes: dict[str, dict] = {}
    nboxes: list[dict] = []
    number_pages: set[int] = set()
    for page in doc.pages:
        h = page.height or 792.0
        pc = doc.content(page.index)
        for ln in pc.lines:
            if ln.tagged_share < 0.8:
                continue
            lb = ln.bbox
            if not (lb[1] >= 0.88 * h or lb[3] <= 0.12 * h):
                continue
            text = ln.text.strip()
            if _BARE_NUMBER.match(text):
                number_pages.add(page.index)
                b = box(page.index, ln.bbox)
                if b:
                    nboxes.append(b)
                continue
            key = re.sub(r"\s+", " ", re.sub(r"\d+", "", text.lower())).strip()
            if len(key) >= 4:
                pages_by_key[key].add(page.index)
                samples.setdefault(key, text)
                b = box(page.index, ln.bbox)
                if b:
                    sboxes.setdefault(key, b)
    n = len(doc.pages)
    need = 3 if n >= 6 else n
    furniture = [k for k, pgs in pages_by_key.items() if len(pgs) >= need]
    if furniture:
        yield finding("PAG-001", f"{len(furniture)} running header or footer line(s) are tagged as content on {need} or more pages",
                      count=len(furniture), evidence=sample((samples[k] for k in furniture), 3, 50),
                      page=min(min(pages_by_key[k]) for k in furniture) + 1, boxes=[sboxes[k] for k in furniture if sboxes.get(k)][:40])
    if len(number_pages) >= need:
        yield finding("PAG-001", f"page numbers are tagged as content on {len(number_pages)} of {n} pages", count=len(number_pages),
                      page=min(number_pages) + 1, boxes=nboxes[:40])

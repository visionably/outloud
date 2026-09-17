"""Navigation rules: can a reader get around a long document without reading every line."""

from __future__ import annotations

import pikepdf

from ..model import Document
from ..registry import finding, rule

LONG_DOCUMENT_PAGES = 10


def _outline_count(doc: Document, limit: int = 3) -> int:
    ol = doc.root.get("/Outlines")
    if not isinstance(ol, pikepdf.Dictionary):
        return 0
    n = 0
    node = ol.get("/First")
    seen: set[tuple] = set()
    while isinstance(node, pikepdf.Dictionary) and n < limit:
        og = node.objgen
        if og in seen:
            break
        seen.add(og)
        n += 1
        node = node.get("/Next")
    return n


@rule("NAV-001")
def bookmarks(doc: Document):
    if len(doc.pages) < LONG_DOCUMENT_PAGES:
        return
    if _outline_count(doc) == 0:
        yield finding("NAV-001", f"a {len(doc.pages)}-page document has no bookmarks (no /Outlines entries)")

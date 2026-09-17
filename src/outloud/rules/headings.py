"""Heading rules: does the outline a reader navigates hold together, and are its entries really headings."""

from __future__ import annotations

import re

from ..model import Document
from ..registry import finding, rule
from ._common import boxes_for, element_page, element_text, words

_SALUTATION = re.compile(r"^(dear|hi|hello|to whom it may concern|yours (faithfully|sincerely|truly)|regards|sincerely|best regards|thank you)\b", re.I)
_REFNUM = re.compile(r"^(ref(erence)?\.?|no\.?|file)\s*[:#]?\s*[\w/\-]*\d[\w/\-]*$|^[\w/\-]*\d[\w/\-]*$", re.I)
_SENTENCE_END = re.compile(r"[.!?](\s|$)")


def _headings(doc: Document):
    return [(el, el.heading_level) for el in doc.elements if el.is_heading]


@rule("HDG-001")
def skipped_levels(doc: Document):
    prev = 0
    hits = []
    for el, lvl in _headings(doc):
        if lvl is None:
            continue
        if prev and lvl > prev + 1:
            hits.append((prev, lvl, el))
        prev = lvl
    if hits:
        p, l, el = hits[0]
        yield finding("HDG-001", f"{len(hits)} heading jump(s) skip a level; the first is H{p} followed by H{l}",
                      page=element_page(el), count=len(hits), evidence=element_text(doc, el)[:80], location={"element": el.path}, boxes=boxes_for(doc, [h[2] for h in hits]))


@rule("HDG-002")
def first_is_h1(doc: Document):
    for el, lvl in _headings(doc):
        if lvl is None:
            return
        if lvl > 1:
            yield finding("HDG-002", f"the first heading in the document is H{lvl}, not H1",
                          page=element_page(el), evidence=element_text(doc, el)[:80], location={"element": el.path}, boxes=boxes_for(doc, [el]))
        return


@rule("HDG-003")
def mixed_heading_kinds(doc: Document):
    hs = _headings(doc)
    if any(l is None for _, l in hs) and any(l is not None for _, l in hs):
        yield finding("HDG-003", "the document uses both unnumbered /H and numbered /H1-/H6 headings")


@rule("HDG-005")
def multiple_h_children(doc: Document):
    bad = [el for el in doc.elements if sum(1 for c in el.logical_children if c.type == "H") > 1]
    if bad:
        yield finding("HDG-005", f"{len(bad)} element(s) have more than one unnumbered /H child", page=element_page(bad[0]), count=len(bad),
                      location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("HDG-010")
def heading_sanity(doc: Document):
    for el, _lvl in _headings(doc):
        text = " ".join(element_text(doc, el).split())
        if not text:
            continue
        reason = None
        if text[:1].islower() and re.search(r"[,;]$", text):
            reason = "a mid-sentence fragment"
        elif _SALUTATION.match(text):
            reason = "a salutation or closing"
        elif _REFNUM.match(text) and len(words(text)) <= 2:
            reason = "a reference number"
        if reason:
            yield finding("HDG-010", f"/{el.type} text reads as {reason}", page=element_page(el), evidence=text[:80],
                          location={"element": el.path}, boxes=boxes_for(doc, [el]))


@rule("HDG-011")
def heading_is_paragraph(doc: Document):
    for el, _lvl in _headings(doc):
        text = " ".join(element_text(doc, el).split())
        if len(words(text)) >= 25 and len(_SENTENCE_END.findall(text)) >= 2:
            yield finding("HDG-011", f"/{el.type} runs to {len(words(text))} words and several sentences",
                          page=element_page(el), evidence=text[:80], location={"element": el.path}, boxes=boxes_for(doc, [el]))


@rule("HDG-012")
def no_headings(doc: Document):
    if doc.struct_root is None or len(doc.pages) < 5 or _headings(doc):
        return
    total = 0
    for p in doc.pages:
        total += sum(len(words(r.text)) for r in doc.content(p.index).runs if r.tagged and not r.artifact)
        if total > 400:
            break
    if total >= 200:
        yield finding("HDG-012", f"a {len(doc.pages)}-page document has no heading at all")

"""Figure rules: does every picture have words, and are the words a description."""

from __future__ import annotations

import re

from ..model import Document
from ..registry import finding, rule
from ._common import boxes_for, element_page, element_text, sample, words

_PLACEHOLDER = re.compile(
    r"^\s*(image|picture|photo|graphic|figure|img|pic|logo|icon|screenshot|chart|diagram|untitled|no description)?\s*[-_ ]?\d*\s*$"
    r"|\.(png|jpe?g|gif|bmp|tiff?|svg|eps|webp)$|^img[_\-]?\d+|^\d+$|\\[a-z]+\{|<math|^\s*[\[({]",
    re.I)


@rule("FIG-001")
def no_alt(doc: Document):
    bad = [el for el in doc.elements_of("Figure") if el.alt is None and el.actual_text is None]
    if bad:
        yield finding("FIG-001", f"{len(bad)} /Figure element(s) have no /Alt and no /ActualText", page=element_page(bad[0]),
                      count=len(bad), location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("FIG-002")
def blank_alt(doc: Document):
    bad = [el for el in doc.elements_of("Figure") if el.alt is not None and not el.alt.strip() and not (el.actual_text or "").strip()]
    if bad:
        yield finding("FIG-002", f"{len(bad)} /Figure element(s) have an empty /Alt", page=element_page(bad[0]), count=len(bad),
                      location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("FIG-010")
def placeholder_alt(doc: Document):
    hits = []
    for el in doc.elements_of("Figure"):
        alt = (el.alt or "").strip()
        if alt and _PLACEHOLDER.search(alt):
            hits.append((el, alt))
    if hits:
        yield finding("FIG-010", f"{len(hits)} figure(s) carry placeholder alternative text", page=element_page(hits[0][0]),
                      count=len(hits), evidence=sample((a for _, a in hits), 4, 30), location={"first": hits[0][0].path}, boxes=boxes_for(doc, [e for e, _ in hits]))


@rule("FIG-011")
def alt_repeats_caption(doc: Document):
    for el in doc.elements_of("Figure"):
        alt = " ".join((el.alt or "").split()).lower()
        if not alt:
            continue
        caps = [c for c in el.logical_children if c.type == "Caption"]
        if el.logical_parent is not None:
            caps += [c for c in el.logical_parent.logical_children if c.type == "Caption"]
        for cap in caps:
            ct = " ".join(element_text(doc, cap).split()).lower()
            if ct and ct == alt:
                yield finding("FIG-011", "the figure's alternative text is identical to its caption; the reader hears it twice",
                              page=element_page(el), evidence=alt[:80], location={"element": el.path}, boxes=boxes_for(doc, [el]))
                break


@rule("FIG-012")
def alt_not_language(doc: Document):
    hits = []
    for el in doc.elements_of("Figure"):
        alt = (el.alt or "").strip()
        if not alt or _PLACEHOLDER.search(alt):
            continue
        letters = sum(ch.isalpha() for ch in alt)
        ws = words(alt)
        if letters / max(1, len(alt)) < 0.5 or (len(set(w.lower() for w in ws)) == 1 and len(ws) >= 3) or (len(ws) <= 1 and len(alt) > 30):
            hits.append((el, alt))
    if hits:
        yield finding("FIG-012", f"{len(hits)} figure(s) have alternative text that does not read as language", page=element_page(hits[0][0]),
                      count=len(hits), evidence=sample((a for _, a in hits), 3, 40), location={"first": hits[0][0].path}, boxes=boxes_for(doc, [e for e, _ in hits]))

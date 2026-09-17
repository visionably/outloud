"""Notes, references and formulae: the small structures that most often go silent."""

from __future__ import annotations

import collections
import re

from ..model import Document
from ..registry import finding, rule
from ._common import boxes_for, element_page, element_text, words

_MARKER = re.compile(r"^\s*[\[(]?\s*([0-9]{1,3}|[ivxlc]{1,6}|[a-z]|[*†‡§¶#]+)\s*[\])]?\s*$", re.I)
_LATEX = re.compile(r"\\[a-zA-Z]+|\^\{|_\{|\$[^$]+\$|<math|<mrow|<mi>")


@rule("NOTE-001")
def note_without_id(doc: Document):
    bad = [el for el in doc.elements_of("Note") if not (el.id or "").strip()]
    if bad:
        yield finding("NOTE-001", f"{len(bad)} /Note element(s) have no /ID", page=element_page(bad[0]), count=len(bad),
                      location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("NOTE-004")
def duplicate_note_ids(doc: Document):
    seen: dict[str, int] = {}
    for el in doc.elements_of("Note"):
        if el.id:
            seen[el.id] = seen.get(el.id, 0) + 1
    dup = [k for k, n in seen.items() if n > 1]
    if dup:
        yield finding("NOTE-004", f"{len(dup)} /Note id(s) are used by more than one note", count=len(dup), evidence=", ".join(dup[:4]))


@rule("NOTE-002")
def dangling_reference(doc: Document):
    notes = doc.elements_of("Note")
    labels = set()
    for n in notes:
        for c in n.children:
            if c.type == "Lbl":
                labels.add(re.sub(r"[^\w*†‡§¶#]", "", element_text(doc, c).lower()))
        t = element_text(doc, n).strip()
        m = re.match(r"^([\[(]?[\w*†‡§¶#]{1,4}[\])]?)", t)
        if m:
            labels.add(re.sub(r"[^\w*†‡§¶#]", "", m.group(1).lower()))
    bad = []
    for r in doc.elements_of("Reference"):
        if any(c.type == "Link" or c.objrs for c in [r] + list(r.descendants())):
            continue
        txt = element_text(doc, r)
        key = re.sub(r"[^\w*†‡§¶#]", "", txt.lower())
        if key and key in labels:
            continue
        if _MARKER.match(txt) or not txt.strip():
            bad.append((r, txt))
    if bad:
        yield finding("NOTE-002", f"{len(bad)} /Reference element(s) point at no note or link", page=element_page(bad[0][0]), count=len(bad),
                      evidence="; ".join(t.strip()[:12] for _, t in bad[:4]), location={"first": bad[0][0].path}, boxes=boxes_for(doc, [r for r, _ in bad]))


@rule("NOTE-003")
def note_shape(doc: Document):
    notes = doc.elements_of("Note")
    if not notes:
        return
    unlabelled = [n for n in notes if not any(c.type == "Lbl" for c in n.children)
                  and not _MARKER.match(element_text(doc, n).strip()[:6] or "") and not re.match(r"^\s*[\[(]?[\w*†‡§¶#]{1,4}[\])]?[\s.:)-]", element_text(doc, n))]
    if unlabelled:
        yield finding("NOTE-003", f"{len(unlabelled)} note(s) have no label; a reader cannot tell which reference they answer",
                      page=element_page(unlabelled[0]), count=len(unlabelled), evidence=element_text(doc, unlabelled[0])[:60], boxes=boxes_for(doc, unlabelled))
    note_texts = collections.Counter(" ".join(element_text(doc, n).split()).lower() for n in notes)
    p_texts = {" ".join(element_text(doc, p, include_children=False).split()).lower() for p in doc.elements_of("P")}
    dup = [t for t in note_texts if len(t) >= 20 and t in p_texts]
    if dup:
        yield finding("NOTE-003", f"{len(dup)} note(s) are tagged twice, once as /Note and again as a /P", count=len(dup), evidence=dup[0][:60])


@rule("MATH-001")
def formula_without_alt(doc: Document):
    bad = [el for el in doc.elements_of("Formula") if not (el.alt or "").strip() and not (el.actual_text or "").strip()
           and el.obj.get("/AF") is None]
    if bad:
        yield finding("MATH-001", f"{len(bad)} /Formula element(s) have no /Alt, /ActualText or associated MathML", page=element_page(bad[0]),
                      count=len(bad), evidence=element_text(doc, bad[0])[:60], location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("MATH-010")
def formula_alt_is_source(doc: Document):
    bad = [el for el in doc.elements_of("Formula") if _LATEX.search(el.alt or "")]
    if bad:
        yield finding("MATH-010", f"{len(bad)} formula(e) have alternative text that is LaTeX or MathML source, not speech",
                      page=element_page(bad[0]), count=len(bad), evidence=(bad[0].alt or "")[:60], location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("MATH-011")
def formula_hides_prose(doc: Document):
    for el in doc.elements_of("Formula"):
        text = element_text(doc, el)
        tw = [w for w in words(text) if len(w) >= 3]
        if len(tw) < 10:
            continue
        rep = words((el.actual_text or "") + " " + (el.alt or ""))
        if len(rep) < 0.3 * len(tw):
            yield finding("MATH-011", f"a /Formula covers {len(tw)} words of text but its alternative has {len(rep)}; prose is hidden as an equation",
                          page=element_page(el), evidence=text[:90], location={"element": el.path}, boxes=boxes_for(doc, [el]))

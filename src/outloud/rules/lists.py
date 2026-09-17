"""List rules: is each item inside a list, does it have a body, and are sub-lists nested where they belong."""

from __future__ import annotations

from ..model import Document
from ..registry import finding, rule
from ._common import boxes_for, element_page


@rule("LST-001")
def item_outside_list(doc: Document):
    bad = [el for el in doc.elements if el.type == "LI" and (el.logical_parent is None or el.logical_parent.type != "L")]
    if bad:
        yield finding("LST-001", f"{len(bad)} /LI element(s) are not children of an /L", page=element_page(bad[0]), count=len(bad),
                      location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("LST-002")
def item_without_body(doc: Document):
    bad = [el for el in doc.elements if el.type == "LI" and not any(c.type == "LBody" for c in el.logical_children)]
    if bad:
        yield finding("LST-002", f"{len(bad)} /LI element(s) have no /LBody", page=element_page(bad[0]), count=len(bad),
                      location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("LST-003")
def foreign_children(doc: Document):
    bad = []
    for el in doc.elements_of("L"):
        for c in el.logical_children:
            if c.type not in ("LI", "L", "Caption"):
                bad.append(c)
    if bad:
        yield finding("LST-003", f"{len(bad)} child element(s) of a list are not list items", page=element_page(bad[0]), count=len(bad),
                      evidence="/" + bad[0].type, location={"first": bad[0].path}, boxes=boxes_for(doc, bad))


@rule("LST-004")
def sublist_beside_item(doc: Document):
    bad = [el for el in doc.elements_of("L") if el.logical_parent is not None and el.logical_parent.type == "LI"]
    if bad:
        yield finding("LST-004", f"{len(bad)} nested list(s) sit directly inside /LI instead of inside its /LBody", page=element_page(bad[0]),
                      count=len(bad), location={"first": bad[0].path}, boxes=boxes_for(doc, bad))

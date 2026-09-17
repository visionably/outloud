"""Criteria: the rule results rolled up the way people ask for them.

Two frameworks, both shown as a list of criteria with a status each, the way
PAC's two tabs do:

* **PDF/UA-1** — the 31 checkpoints of the Matterhorn Protocol 1.1, which
  organise every requirement of ISO 14289-1. A checkpoint's status comes
  from the conformance rules that test it; semantic rules mapped to the same
  checkpoint are reported beside it as "beyond the protocol", because a
  validator would not count them.
* **WCAG 2.2, levels A and AA** — all 55 success criteria. A criterion's
  status comes from every rule mapped to it, conformance and semantic alike,
  because WCAG asks whether the alternative is *equivalent* and the
  relationships *conveyed*, not whether the key exists. Criteria that no
  rule can test are marked as needing a person, with a note on what to look
  at, and criteria that do not apply to this file (no forms, no media) are
  marked not applicable, so the list is honest about what was tested.

Statuses, in order of severity:
    fail            an error-level finding on a mapped rule
    warning         warning-level findings only
    pass            every mapped rule ran and found nothing
    not-applicable  the file has nothing the criterion is about
    manual          no automated rule; a person has to look
    not-tested      rules exist but did not run (planned, crashed, needs --source)
"""

from __future__ import annotations

from typing import Iterable, Optional

from .findings import ERROR, INFO, WARNING

# ── PDF/UA-1: Matterhorn Protocol 1.1 checkpoints ────────────────────────

MATTERHORN: list[tuple[str, str]] = [
    ("01", "Real content tagged"), ("02", "Role mapping"), ("03", "Flickering"), ("04", "Color and contrast"),
    ("05", "Sound"), ("06", "Metadata"), ("07", "Dictionary"), ("08", "OCR validation"), ("09", "Appropriate tags"),
    ("10", "Character mappings"), ("11", "Declared natural language"), ("12", "Stretchable characters"),
    ("13", "Graphics"), ("14", "Headings"), ("15", "Tables"), ("16", "Lists"), ("17", "Mathematical expressions"),
    ("18", "Page headers and footers"), ("19", "Notes and references"), ("20", "Optional content"),
    ("21", "Embedded files"), ("22", "Article threads"), ("23", "Digital signatures"), ("24", "Non-interactive forms"),
    ("25", "XFA"), ("26", "Security"), ("27", "Navigation"), ("28", "Annotations"), ("29", "Actions"),
    ("30", "XObjects"), ("31", "Fonts"),
]

# Checkpoints the protocol itself marks as human judgement, with what to look at.
MATTERHORN_MANUAL: dict[str, str] = {
    "03": "Look for content that flashes or blinks (animations, multimedia).",
    "04": "Check that colour is not the only carrier of meaning and that text contrast is sufficient.",
    "05": "Check that any sound has a text equivalent and does not play unprompted.",
    "08": "For scanned pages, check that the OCR text matches the printed words.",
    "09": "Read the tags against the page: are the types right and is the order the one a person would read?",
    "12": "Check that stretched characters (long braces, rules built from glyphs) are artifacts or have alternatives.",
    "22": "Article threads, if present, must follow the reading order.",
    "23": "Digital signature fields must be tagged like other form fields and describe themselves.",
    "24": "Printed forms to fill by hand must be tagged so the fields and their labels are read together.",
    "29": "Actions triggered by the document must not change it without the reader's control.",
}

# Which document feature a checkpoint is about; a checkpoint whose feature
# the file does not have is not applicable rather than passed.
MATTERHORN_REQUIRES: dict[str, str] = {
    "03": "media", "05": "media", "08": "scanned", "12": "text", "13": "figures", "14": "headings", "15": "tables",
    "16": "lists", "17": "formulas", "18": "pages3", "19": "notes", "20": "oc", "21": "embedded", "22": "threads",
    "23": "signatures", "24": "text", "25": "acroform", "26": "encrypted", "28": "annots", "29": "actions", "30": "xobjects",
}

# ── WCAG 2.2, levels A and AA ────────────────────────────────────────────
# (id, name, level, requires, note). `requires` names the document feature
# without which the criterion is not applicable ("never": it cannot apply to
# a static document). `note` is what a person should look at when no rule
# tests the criterion.

WCAG22: list[tuple[str, str, str, Optional[str], Optional[str]]] = [
    ("1.1.1", "Non-text Content", "A", None, None),
    ("1.2.1", "Audio-only and Video-only (Prerecorded)", "A", "media", "Embedded audio or video needs a transcript or description."),
    ("1.2.2", "Captions (Prerecorded)", "A", "media", "Embedded video with speech needs captions."),
    ("1.2.3", "Audio Description or Media Alternative (Prerecorded)", "A", "media", "Embedded video needs an audio description or a text alternative."),
    ("1.2.4", "Captions (Live)", "AA", "never", "A document carries no live media."),
    ("1.2.5", "Audio Description (Prerecorded)", "AA", "media", "Embedded video needs an audio description."),
    ("1.3.1", "Info and Relationships", "A", None, None),
    ("1.3.2", "Meaningful Sequence", "A", None, None),
    ("1.3.3", "Sensory Characteristics", "A", None, "Instructions must not rely on shape, size, position or colour alone ('the box on the right')."),
    ("1.3.4", "Orientation", "AA", "never", "A document does not lock the display orientation."),
    ("1.3.5", "Identify Input Purpose", "AA", "forms", "Fields that collect personal data should say what they collect in a way software can read."),
    ("1.4.1", "Use of Color", "A", None, "Meaning carried by colour alone (a red figure, a coloured link) must also be carried another way."),
    ("1.4.2", "Audio Control", "A", "media", "Audio that starts on its own must be stoppable."),
    ("1.4.3", "Contrast (Minimum)", "AA", None, "Text needs 4.5:1 contrast against its background (3:1 for large text). Not measured yet."),
    ("1.4.4", "Resize Text", "AA", None, "Viewers zoom a PDF; check that text is real text, not an image, so it stays sharp."),
    ("1.4.5", "Images of Text", "AA", None, "Pictures of text should be real text unless the picture is essential."),
    ("1.4.10", "Reflow", "AA", None, "A tagged document reflows in viewers that support it; check tables and figures survive."),
    ("1.4.11", "Non-text Contrast", "AA", None, "Form field borders, icons and chart elements need 3:1 contrast."),
    ("1.4.12", "Text Spacing", "AA", None, "Content must survive wider letter, word and line spacing where the viewer applies it."),
    ("1.4.13", "Content on Hover or Focus", "AA", "annots", "Pop-up notes and tooltips must be dismissable and hoverable."),
    ("2.1.1", "Keyboard", "A", "interactive", "Every link and field must be reachable and usable from the keyboard."),
    ("2.1.2", "No Keyboard Trap", "A", "interactive", "Focus must be able to leave every field."),
    ("2.1.4", "Character Key Shortcuts", "A", "actions", "Single-key shortcuts in document scripts must be remappable."),
    ("2.2.1", "Timing Adjustable", "A", "actions", "Time limits set by document scripts must be adjustable."),
    ("2.2.2", "Pause, Stop, Hide", "A", "media", "Moving or blinking content must be pausable."),
    ("2.3.1", "Three Flashes or Below Threshold", "A", "media", "Nothing may flash more than three times a second."),
    ("2.4.1", "Bypass Blocks", "A", None, None),
    ("2.4.2", "Page Titled", "A", None, None),
    ("2.4.3", "Focus Order", "A", "annots", None),
    ("2.4.4", "Link Purpose (In Context)", "A", "links", None),
    ("2.4.5", "Multiple Ways", "AA", None, None),
    ("2.4.6", "Headings and Labels", "AA", None, None),
    ("2.4.7", "Focus Visible", "AA", "interactive", "The viewer shows focus; check that fields and links do not hide it."),
    ("2.4.11", "Focus Not Obscured (Minimum)", "AA", "interactive", "A focused field must not be hidden behind other content."),
    ("2.5.1", "Pointer Gestures", "A", "actions", "Document scripts must not require multi-point or path gestures."),
    ("2.5.2", "Pointer Cancellation", "A", "actions", "Actions must complete on release, not press."),
    ("2.5.3", "Label in Name", "A", "forms", "A field's accessible name (/TU) must contain its visible label."),
    ("2.5.4", "Motion Actuation", "A", "never", "A document takes no motion input."),
    ("2.5.7", "Dragging Movements", "AA", "actions", "Document scripts must not require dragging."),
    ("2.5.8", "Target Size (Minimum)", "AA", "interactive", "Links and fields should be at least 24 by 24 points, or spaced apart."),
    ("3.1.1", "Language of Page", "A", None, None),
    ("3.1.2", "Language of Parts", "AA", "struct", "Passages in another language need /Lang on their element."),
    ("3.2.1", "On Focus", "A", "forms", "Focusing a field must not trigger a change."),
    ("3.2.2", "On Input", "A", "forms", "Changing a field must not trigger an unexpected change."),
    ("3.2.3", "Consistent Navigation", "AA", "pages3", "Repeated navigation (running heads, page furniture) should be in the same order on every page."),
    ("3.2.4", "Consistent Identification", "AA", None, "The same thing should be named the same way throughout."),
    ("3.2.6", "Consistent Help", "A", "forms", "Help for filling the form should be in the same place on every page."),
    ("3.3.1", "Error Identification", "A", "forms", "Validation errors must be described in text."),
    ("3.3.2", "Labels or Instructions", "A", "forms", None),
    ("3.3.3", "Error Suggestion", "AA", "forms", "Where an error is known, suggest the fix."),
    ("3.3.4", "Error Prevention (Legal, Financial, Data)", "AA", "forms", "Submissions with legal or financial effect must be reversible, checked or confirmable."),
    ("3.3.7", "Redundant Entry", "A", "forms", "Do not ask for the same information twice in one form."),
    ("3.3.8", "Accessible Authentication (Minimum)", "AA", "forms", "No cognitive function test to sign or submit."),
    ("4.1.2", "Name, Role, Value", "A", None, None),
    ("4.1.3", "Status Messages", "AA", "actions", "Messages from document scripts must reach assistive technology."),
]

STATUS_ORDER = ["fail", "warning", "pass", "not-applicable", "manual", "not-tested"]
_OUTCOME_RANK = {"fail": 0, "warning": 1, "pass": 2, "info": 2, "not-applicable": 3, "not-run": 5}


def _has(features: dict, requires: Optional[str]) -> Optional[bool]:
    """True/False when the document's features answer `requires`; None when the requirement is unknown."""
    if not requires:
        return True
    if requires == "never":
        return False
    return any(bool(features.get(alt)) for alt in requires.split("|"))


def rollup(outcomes: Iterable[str]) -> Optional[str]:
    """The status of a set of rule outcomes; None when the set is empty."""
    ranks = [_OUTCOME_RANK.get(o, 5) for o in outcomes]
    if not ranks:
        return None
    best = min(ranks)
    if best == 0:
        return "fail"
    if best == 1:
        return "warning"
    if best == 2:
        return "pass"
    if best == 3:
        return "not-applicable"
    return "not-tested"


def evaluate(result, rules: dict) -> dict:
    """Build {"pdfua1": [...], "wcag22": [...]} from a Result and the catalogue.

    Each row: id, name, (level), status, rules: [{id, title, layer, outcome, findings}],
    errors, warnings, note. Rows are in framework order; callers sort by
    status if they want the failures first.
    """
    runs = {r.rule: r for r in result.runs}
    features = result.stats.get("features", {})
    counts: dict[str, dict] = {}
    for f in result.findings:
        c = counts.setdefault(f.rule, {"error": 0, "warning": 0, "info": 0})
        c[f.severity] = c.get(f.severity, 0) + f.count

    def rule_row(meta):
        run = runs.get(meta.id)
        outcome = run.outcome if run is not None else "not-run"
        c = counts.get(meta.id, {})
        return {"id": meta.id, "title": meta.title, "layer": meta.layer, "outcome": outcome,
                "errors": c.get("error", 0), "warnings": c.get("warning", 0), "info": c.get("info", 0)}

    def summarise(rows: list[dict]) -> dict:
        return {"errors": sum(r["errors"] for r in rows), "warnings": sum(r["warnings"] for r in rows)}

    pdfua = []
    for cid, name in MATTERHORN:
        mapped = [m for m in rules.values() if m.matterhorn == cid]
        conf = [rule_row(m) for m in mapped if m.layer == "conformance"]
        sem = [rule_row(m) for m in mapped if m.layer != "conformance"]
        status = rollup(r["outcome"] for r in conf)
        note = None
        semantic_only = False
        if status is None and sem and any(r["outcome"] not in ("not-run",) for r in sem):
            # The protocol has no machine test here, but outloud's semantic rules do; say so.
            status = rollup(r["outcome"] for r in sem)
            semantic_only = True
            note = MATTERHORN_MANUAL.get(cid)
        if status is None or status == "not-tested" and not any(r["outcome"] != "not-run" for r in conf):
            applies = _has(features, MATTERHORN_REQUIRES.get(cid))
            if applies is False:
                status, note = "not-applicable", None
            elif cid in MATTERHORN_MANUAL:
                status, note = "manual", MATTERHORN_MANUAL[cid]
            elif status is None:
                status, note = "manual", "No automated test yet."
        row = {"id": cid, "name": name, "status": status, "rules": conf, "semantic": sem, "note": note, "semantic_only": semantic_only}
        row.update(summarise(conf))
        row["semantic_status"] = rollup(r["outcome"] for r in sem)
        pdfua.append(row)

    wcag = []
    for sid, name, level, requires, note in WCAG22:
        mapped = [rule_row(m) for m in rules.values() if sid in (m.wcag or [])]
        status = rollup(r["outcome"] for r in mapped)
        applies = _has(features, requires)
        row_note = None
        if applies is False:
            # Nothing in the file for this criterion to be about, whatever the rules said.
            status = "not-applicable"
            row_note = note if requires == "never" else None
        elif status is None:
            status, row_note = "manual", note or "No automated test; a person has to look."
        elif status == "not-applicable" and note:
            row_note = note
        elif status == "pass" and note:
            row_note = note   # rules passed, but the criterion has aspects a person still checks
        row = {"id": sid, "name": name, "level": level, "status": status, "rules": mapped, "note": row_note}
        row.update(summarise(mapped))
        wcag.append(row)

    return {"pdfua1": pdfua, "wcag22": wcag}


def tally(rows: list[dict]) -> dict[str, int]:
    out = {s: 0 for s in STATUS_ORDER}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


def tally_line(rows: list[dict]) -> str:
    t = tally(rows)
    parts = []
    labels = {"fail": "fail", "warning": "warning", "pass": "pass", "not-applicable": "not applicable", "manual": "need a person", "not-tested": "not tested"}
    for s in STATUS_ORDER:
        if t.get(s):
            parts.append(f"{t[s]} {labels[s]}")
    return " · ".join(parts) if parts else "nothing evaluated"

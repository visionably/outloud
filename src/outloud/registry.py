"""The rule registry: catalogue metadata joined to rule functions.

A rule is a plain function `fn(doc) -> iterable of Finding` registered under
an id from `rules/catalogue.yaml`. The catalogue is the authority on what a
rule claims and how severe it is; the function only decides whether the
claim holds for this document. Keeping the two apart means the docs are
generated from data that cannot drift from the code, and a rule that exists
in the catalogue but has no function is reported as "not implemented"
rather than silently absent.
"""

from __future__ import annotations

import importlib
import pkgutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

import yaml

from .findings import Finding, Result, RuleRun

CATALOGUE_PATH = Path(__file__).parent / "rules" / "catalogue.yaml"


@dataclass
class RuleMeta:
    id: str
    group: str
    title: str
    claim: str
    layer: str
    severity: str
    clause: Optional[str] = None
    matterhorn: Optional[str] = None
    status: str = "active"
    requires: Optional[str] = None   # a document feature the rule is about (see FEATURES); absent = not applicable
    verapdf: bool = True          # False: veraPDF's UA-1 profile has no test for this
    wcag: list = field(default_factory=list)   # WCAG 2.2 success criteria the rule tests, e.g. ["1.3.1", "2.4.6"]
    fix: Optional[str] = None     # what to change, in one sentence
    fn: Optional[Callable] = field(default=None, repr=False)


_CATALOGUE: dict[str, RuleMeta] = {}
_LOADED = False


def load_catalogue() -> dict[str, RuleMeta]:
    global _LOADED
    if _LOADED:
        return _CATALOGUE
    data = yaml.safe_load(CATALOGUE_PATH.read_text(encoding="utf-8")) or {}
    for group, rules in data.items():
        for r in rules or []:
            meta = RuleMeta(
                id=r["id"], group=group, title=r["title"], claim=r["claim"], layer=r["layer"],
                severity=r["severity"], clause=str(r["clause"]) if r.get("clause") is not None else None,
                matterhorn=str(r["matterhorn"]) if r.get("matterhorn") is not None else None,
                status=r.get("status", "active"), requires=r.get("requires"),
                verapdf=str(r.get("verapdf", "yes")).lower() not in ("no", "false"),
                wcag=[str(x) for x in (r.get("wcag") or [])], fix=r.get("fix"),
            )
            if meta.id in _CATALOGUE:
                raise ValueError(f"duplicate rule id in catalogue: {meta.id}")
            _CATALOGUE[meta.id] = meta
    _LOADED = True
    return _CATALOGUE


def rule(rule_id: str):
    """Register `fn` as the implementation of catalogue rule `rule_id`."""

    def deco(fn):
        cat = load_catalogue()
        if rule_id not in cat:
            raise KeyError(f"rule {rule_id} is not in the catalogue; add it there first")
        if cat[rule_id].fn is not None:
            raise ValueError(f"rule {rule_id} registered twice")
        cat[rule_id].fn = fn
        fn.rule_id = rule_id
        return fn

    return deco


def import_rule_modules() -> None:
    """Import every module under outloud.rules so their @rule decorators run."""
    from . import rules as pkg

    for mod in pkgutil.iter_modules(pkg.__path__):
        if not mod.name.startswith("_"):
            importlib.import_module(f"{pkg.__name__}.{mod.name}")


def all_rules() -> list[RuleMeta]:
    import_rule_modules()
    return list(load_catalogue().values())


# What a document has, so that a rule about tables is "not applicable" on a
# file without tables rather than "passed". Each entry: a predicate over the
# Document and the phrase reports use when the feature is absent.
_MEDIA = {"Screen", "RichMedia", "Movie", "Sound", "3D"}


def _embedded_files(doc) -> bool:
    import pikepdf  # noqa: PLC0415

    names = doc.root.get("/Names")
    if not isinstance(names, pikepdf.Dictionary):
        return False
    return isinstance(names.get("/EmbeddedFiles"), pikepdf.Dictionary)


def _actions(doc) -> bool:
    import pikepdf  # noqa: PLC0415

    names = doc.root.get("/Names")
    if isinstance(names, pikepdf.Dictionary) and names.get("/JavaScript") is not None:
        return True
    if doc.root.get("/OpenAction") is not None or doc.root.get("/AA") is not None:
        return True
    return any(a.subtype == "Widget" for a in doc.annotations)


def _has_xobject(doc, subtype: str) -> bool:
    import pikepdf  # noqa: PLC0415

    for page in doc.pages:
        res = page.obj.get("/Resources")
        xo = res.get("/XObject") if isinstance(res, pikepdf.Dictionary) else None
        if not isinstance(xo, pikepdf.Dictionary):
            continue
        for _name, x in xo.items():
            try:
                if str(x.get("/Subtype")) == "/" + subtype:
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


FEATURES: dict[str, tuple[Callable, str]] = {
    "source": (lambda d: getattr(d, "source", None) is not None, "needs --source"),
    "struct": (lambda d: d.struct_root is not None, "no structure tree"),
    "text": (lambda d: bool(d.fonts), "no text"),
    "fonts": (lambda d: bool(d.fonts), "no fonts"),
    "headings": (lambda d: any(e.is_heading for e in d.elements), "no headings"),
    "tables": (lambda d: bool(d.elements_of("Table", "TR", "TH", "TD")), "no tables"),
    "lists": (lambda d: bool(d.elements_of("L", "LI", "LBody")), "no lists"),
    "figures": (lambda d: bool(d.elements_of("Figure")), "no figures"),
    "formulas": (lambda d: bool(d.elements_of("Formula")), "no formulae"),
    "notes": (lambda d: bool(d.elements_of("Note", "Reference")), "no notes or references"),
    "links": (lambda d: bool(d.elements_of("Link")) or any(a.subtype == "Link" for a in d.annotations), "no links"),
    "annots": (lambda d: bool(d.annotations), "no annotations"),
    "forms": (lambda d: any(a.subtype == "Widget" for a in d.annotations) or d.root.get("/AcroForm") is not None, "no form fields"),
    "acroform": (lambda d: d.root.get("/AcroForm") is not None, "no interactive form"),
    "interactive": (lambda d: bool(d.annotations), "nothing interactive"),
    "media": (lambda d: any(a.subtype in _MEDIA for a in d.annotations), "no audio, video or multimedia"),
    "actions": (_actions, "no scripts or actions"),
    "encrypted": (lambda d: bool(d.pdf.is_encrypted), "not encrypted"),
    "oc": (lambda d: d.root.get("/OCProperties") is not None, "no optional content"),
    "embedded": (_embedded_files, "no embedded files"),
    "threads": (lambda d: d.root.get("/Threads") is not None, "no article threads"),
    "signatures": (lambda d: any(a.field_ft == "Sig" for a in d.annotations), "no signature fields"),
    "xobjects": (lambda d: _has_xobject(d, "Form"), "no form XObjects"),
    "scanned": (lambda d: _has_xobject(d, "Image"), "no page images"),
    "lang": (lambda d: bool((d.lang or "").strip()), "no /Lang to test"),
    "title": (lambda d: bool((d.title or "").strip()), "no title to test"),
    "pages3": (lambda d: len(d.pages) >= 3, "fewer than three pages"),
}


def features(doc) -> dict[str, bool]:
    """Every feature flag for `doc`; a predicate that raises counts as present so no rule is silently skipped."""
    out: dict[str, bool] = {}
    for name, (pred, _why) in FEATURES.items():
        try:
            out[name] = bool(pred(doc))
        except Exception:  # noqa: BLE001
            out[name] = True
    return out


def applicable(requires: Optional[str], feats: dict[str, bool]) -> tuple[bool, Optional[str]]:
    """(applies?, reason when it does not). `requires` may list alternatives with '|'."""
    if not requires:
        return True, None
    alts = requires.split("|")
    if any(feats.get(a, True) for a in alts):
        return True, None
    why = FEATURES.get(alts[0], (None, f"no {alts[0]}"))[1]
    return False, why


_SEV_RANK = {"error": 0, "warning": 1, "info": 2}


def _outcome(found: list[Finding]) -> str:
    if not found:
        return "pass"
    worst = min(_SEV_RANK.get(f.severity, 2) for f in found)
    return {0: "fail", 1: "warning", 2: "info"}[worst]


def run_rules(doc, result: Result, only: Optional[set[str]] = None, skip: Optional[set[str]] = None,
              layers: Optional[set[str]] = None, feats: Optional[dict[str, bool]] = None) -> None:
    """Run every applicable rule on `doc`, appending findings and run records to `result`.

    A rule whose `requires` feature the document lacks is recorded as not
    applicable and not run. A rule that raises is recorded as crashed with the
    exception text and the check continues: one broken rule must not hide the
    other forty.
    """
    if feats is None:
        feats = features(doc)
    for meta in all_rules():
        if only and meta.id not in only:
            continue
        if skip and meta.id in skip:
            continue
        if layers and meta.layer not in layers:
            continue
        if meta.status == "planned" or meta.fn is None:
            result.runs.append(RuleRun(meta.id, "not-implemented", outcome="not-run"))
            continue
        ok, why = applicable(meta.requires, feats)
        if not ok:
            if meta.requires == "source":
                result.runs.append(RuleRun(meta.id, "skipped", why, outcome="not-run"))
            else:
                result.runs.append(RuleRun(meta.id, "not-applicable", why, outcome="not-applicable"))
            continue
        t0 = time.perf_counter()
        try:
            found = list(meta.fn(doc) or ())
        except Exception as exc:  # noqa: BLE001 — a rule must not take the run down
            result.runs.append(RuleRun(meta.id, "crashed", f"{type(exc).__name__}: {exc}"[:200],
                                       seconds=time.perf_counter() - t0, outcome="not-run"))
            continue
        for f in found:
            f.rule = meta.id
            if f.severity is None:
                f.severity = meta.severity
        result.findings.extend(found)
        result.runs.append(RuleRun(meta.id, "ran", findings=sum(f.count for f in found),
                                   seconds=time.perf_counter() - t0, outcome=_outcome(found)))


def finding(meta_or_id, message: str, page: Optional[int] = None, severity: Optional[str] = None,
            **kw) -> Finding:
    """Convenience used by rule modules: severity defaults to the catalogue's."""
    rid = meta_or_id if isinstance(meta_or_id, str) else meta_or_id.id
    sev = severity or load_catalogue()[rid].severity
    return Finding(rule=rid, severity=sev, message=message, page=page, **kw)

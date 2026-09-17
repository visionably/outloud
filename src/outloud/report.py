"""Outputs: terminal, JSON, SARIF and HTML from the same Result objects."""

from __future__ import annotations

import datetime as _dt
import html
import json
import os
from typing import Iterable

from . import __version__
from .criteria import STATUS_ORDER, WCAG22, tally_line
from .findings import ERROR, INFO, WARNING, Result
from .registry import all_rules, load_catalogue

_STATUS_MARK = {"fail": "FAIL", "warning": "WARN", "pass": "PASS", "not-applicable": "N/A", "manual": "PERSON", "not-tested": "-"}
_OUTCOME_MARK = {"fail": "fail", "warning": "warning", "pass": "pass", "info": "info", "not-applicable": "n/a", "not-run": "not run"}

SARIF_LEVEL = {ERROR: "error", WARNING: "warning", INFO: "note"}
_VERDICT_MARK = {"pass": "PASS", "review": "REVIEW", "fail": "FAIL", "unreadable": "UNREADABLE"}


# ── terminal ──────────────────────────────────────────────────────────────

def one_line(r: Result) -> str:
    name = os.path.basename(r.path)
    if r.error:
        return f"{_VERDICT_MARK['unreadable']:<10} {name}: {r.error}"
    pages = r.stats.get("pages", "?")
    return (f"{_VERDICT_MARK[r.verdict]:<10} {name}: {r.errors} error(s), {r.warnings} warning(s), {r.infos} info"
            f"  [{pages} page(s), {r.seconds:.2f}s]")


def terminal(r: Result, verbose: bool = True, show_info: bool = True) -> str:
    lines = [one_line(r)]
    if r.error or not verbose:
        return "\n".join(lines)
    cat = load_catalogue()
    for f in r.sorted_findings():
        if f.severity == INFO and not show_info:
            continue
        meta = cat.get(f.rule)
        where = f"p.{f.page}" if f.page else "doc"
        head = f"  {f.severity.upper():<7} {f.rule:<9} {where:<6} {f.message}"
        if f.count > 1 and str(f.count) not in f.message:
            head += f" (x{f.count})"
        lines.append(head)
        if f.evidence:
            lines.append(f"          evidence: {f.evidence}")
        if meta and meta.clause:
            std = f"ISO 14289-1 {meta.clause}" + (f", Matterhorn {meta.matterhorn}" if meta.matterhorn else "")
        elif meta:
            std = "semantic check, no validator tests this"
        else:
            std = ""
        if meta and meta.wcag:
            std += " · WCAG " + ", ".join(meta.wcag)
        if meta:
            lines.append(f"          {meta.title} — {std}")
        if meta and meta.fix:
            lines.append(f"          fix: {meta.fix}")
    crashed = [x for x in r.runs if x.status == "crashed"]
    for x in crashed:
        lines.append(f"  CRASH   {x.rule:<9} {x.reason}")
    if r.criteria:
        lines.append(f"  PDF/UA-1 checkpoints: {tally_line(r.criteria['pdfua1'])}")
        lines.append(f"  WCAG 2.2 A/AA:        {tally_line(r.criteria['wcag22'])}")
    return "\n".join(lines)


def criteria_table(r: Result, framework: str = "both") -> str:
    """The criteria view for the terminal: one line per checkpoint or success criterion, with the rules behind it."""
    if r.error or not r.criteria:
        return ""
    out: list[str] = []

    def rules_text(rows: list[dict]) -> str:
        """Failing and warning rules by id; the rest as counts, so a criterion with fifty rules stays one line."""
        if not rows:
            return ""
        groups: dict[str, list[str]] = {}
        for x in rows:
            groups.setdefault(x["outcome"], []).append(x["id"])
        parts = []
        for o in ("fail", "warning", "info"):
            if o in groups:
                parts.append(f"{', '.join(groups[o])} {_OUTCOME_MARK[o]}")
        for o in ("pass", "not-applicable", "not-run"):
            if o in groups:
                ids = groups[o]
                parts.append(f"{', '.join(ids)} {_OUTCOME_MARK[o]}" if len(ids) <= 6 else f"{len(ids)} rules {_OUTCOME_MARK[o]}")
        return " · ".join(parts)

    if framework in ("both", "pdfua1"):
        out.append(f"PDF/UA-1 · Matterhorn Protocol 1.1 checkpoints — {tally_line(r.criteria['pdfua1'])}")
        for row in r.criteria["pdfua1"]:
            sem = row.get("semantic") or []
            if row.get("semantic_only"):
                detail = rules_text(sem) + " (semantic, beyond the protocol)"
            else:
                detail = rules_text(row["rules"]) or (row["note"] or "")
            line = f"  {_STATUS_MARK[row['status']]:<7} {row['id']} {row['name']:<28} {detail}"
            hits = [x for x in sem if x["outcome"] in ("fail", "warning")]
            if hits and not row.get("semantic_only"):
                line += f"   [beyond the protocol: {', '.join(x['id'] + ' ' + _OUTCOME_MARK[x['outcome']] for x in hits)}]"
            out.append(line.rstrip())
    if framework == "both":
        out.append("")
    if framework in ("both", "wcag22"):
        out.append(f"WCAG 2.2, levels A and AA — {tally_line(r.criteria['wcag22'])}")
        for row in r.criteria["wcag22"]:
            detail = rules_text(row["rules"]) or (row["note"] or "")
            out.append(f"  {_STATUS_MARK[row['status']]:<7} {row['id']:<7} {row['name']} ({row['level']})  {detail}".rstrip())
    return "\n".join(out)


def batch_table(results: list[Result]) -> str:
    width = max((len(os.path.basename(r.path)) for r in results), default=10)
    out = [f"{'file':<{width}}  {'verdict':<10} {'errors':>6} {'warnings':>8} {'pages':>5} {'seconds':>7}"]
    for r in results:
        out.append(f"{os.path.basename(r.path):<{width}}  {r.verdict:<10} {r.errors:>6} {r.warnings:>8} {str(r.stats.get('pages', '?')):>5} {r.seconds:>7.2f}")
    n = len(results)
    passed = sum(1 for r in results if r.verdict == "pass")
    review = sum(1 for r in results if r.verdict == "review")
    failed = sum(1 for r in results if r.verdict == "fail")
    unread = sum(1 for r in results if r.verdict == "unreadable")
    out.append(f"{n} file(s): {passed} pass, {review} review, {failed} fail, {unread} unreadable; {sum(r.seconds for r in results):.1f}s total")
    return "\n".join(out)


# ── JSON ──────────────────────────────────────────────────────────────────

def to_json(results: Iterable[Result]) -> str:
    results = list(results)
    payload = {
        "tool": {"name": "outloud", "version": __version__},
        "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "results": [r.to_dict() for r in results],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ── SARIF 2.1.0 ───────────────────────────────────────────────────────────

def to_sarif(results: Iterable[Result]) -> str:
    rules_meta = all_rules()
    taxa = [{"id": sid, "name": name, "shortDescription": {"text": f"{sid} {name} (Level {level})"}} for sid, name, level, _req, _note in WCAG22]
    taxon_index = {t["id"]: i for i, t in enumerate(taxa)}
    rules = []
    for m in rules_meta:
        props = {"layer": m.layer, "group": m.group, "severity": m.severity, "wcag": list(m.wcag)}
        if m.clause:
            props["iso14289-1"] = m.clause
        if m.matterhorn:
            props["matterhorn"] = m.matterhorn
        entry = {
            "id": m.id,
            "name": m.title.replace(" ", ""),
            "shortDescription": {"text": m.title},
            "fullDescription": {"text": m.claim},
            "defaultConfiguration": {"level": SARIF_LEVEL.get(m.severity, "warning")},
            "properties": props,
        }
        if m.fix:
            entry["help"] = {"text": m.fix}
        rels = [{"target": {"id": sc, "index": taxon_index[sc], "toolComponent": {"name": "WCAG 2.2"}}, "kinds": ["relevant"]}
                for sc in m.wcag if sc in taxon_index]
        if rels:
            entry["relationships"] = rels
        rules.append(entry)
    sarif_results = []
    for r in results:
        uri = r.path if r.path.startswith(("file:", "http")) else "file://" + os.path.abspath(r.path)
        if r.error:
            sarif_results.append({
                "ruleId": "OUTLOUD-UNREADABLE", "level": "error",
                "message": {"text": f"file could not be checked: {r.error}"},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}],
            })
            continue
        for f in r.sorted_findings():
            loc = {"physicalLocation": {"artifactLocation": {"uri": uri}}}
            if f.page:
                loc["logicalLocations"] = [{"name": f"page {f.page}", "kind": "page"}]
            text = f.message + (f" Evidence: {f.evidence}" if f.evidence else "")
            props = {"page": f.page, "count": f.count}
            props.update({k: v for k, v in f.location.items()})
            sarif_results.append({
                "ruleId": f.rule, "level": SARIF_LEVEL.get(f.severity, "warning"),
                "message": {"text": text}, "locations": [loc], "properties": props,
            })
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "outloud", "version": __version__,
                                "informationUri": "https://github.com/superzackx/outloud", "rules": rules}},
            "taxonomies": [{"name": "WCAG 2.2", "version": "2.2", "organization": "W3C",
                            "informationUri": "https://www.w3.org/TR/WCAG22/", "taxa": taxa}],
            "results": sarif_results,
        }],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ── HTML ──────────────────────────────────────────────────────────────────

_CSS = """
:root{--ink:#1a1a1a;--muted:#5b5852;--rule:#d9d5ce;--bg:#f6f4ef;--err:#b3261e;--warn:#9a6a00;--info:#3a5a8c;--pass:#2c6e49}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:64rem;margin:0 auto;padding:2rem 1.25rem 4rem}
h1{font-size:1.6rem;margin:0 0 .25rem}h2{font-size:1.15rem;margin:2rem 0 .5rem;border-bottom:1px solid var(--rule);padding-bottom:.25rem}
.sub{color:var(--muted);font-size:.9rem}
.verdict{display:inline-block;padding:.15rem .6rem;border-radius:.2rem;font-weight:700;letter-spacing:.04em;color:#fff}
.v-pass{background:var(--pass)}.v-review{background:var(--warn)}.v-fail{background:var(--err)}.v-unreadable{background:#555}
table{border-collapse:collapse;width:100%;font-size:.92rem}th,td{text-align:left;vertical-align:top;padding:.45rem .5rem;border-bottom:1px solid var(--rule)}
th{color:var(--muted);font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em}
.sev{font-weight:700;text-transform:uppercase;font-size:.78rem}.sev-error{color:var(--err)}.sev-warning{color:var(--warn)}.sev-info{color:var(--info)}
.ev{color:var(--muted);font-family:ui-monospace,Menlo,monospace;font-size:.82rem;white-space:pre-wrap}
.rule{font-family:ui-monospace,Menlo,monospace;font-size:.82rem}
details{margin:.4rem 0}summary{cursor:pointer;color:var(--muted)}
.counts span{display:inline-block;margin-right:1rem}
.wrap{overflow-x:auto}
.fix{color:var(--muted);font-size:.85rem}
.st{display:inline-block;min-width:4.2rem;text-align:center;padding:.05rem .4rem;border-radius:.2rem;font-size:.72rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#fff}
.st-fail{background:var(--err)}.st-warning{background:var(--warn)}.st-pass{background:var(--pass)}.st-not-applicable{background:#8a877f}.st-manual{background:var(--info)}.st-not-tested{background:#bbb;color:#333}
.crit td:first-child{white-space:nowrap}
"""


def _criteria_html(r: Result) -> str:
    if not r.criteria:
        return ""
    parts = []

    def rules_cell(rows: list[dict]) -> str:
        if not rows:
            return ""
        return ", ".join(f"<span class='rule'>{html.escape(x['id'])}</span> {html.escape(_OUTCOME_MARK[x['outcome']])}" for x in rows)

    parts.append(f"<h3>PDF/UA-1 · Matterhorn Protocol 1.1 checkpoints</h3><p class='sub'>{html.escape(tally_line(r.criteria['pdfua1']))}</p>")
    parts.append("<div class='wrap'><table class='crit'><tr><th>Status</th><th>Checkpoint</th><th>Rules</th><th>Beyond the protocol</th></tr>")
    for row in r.criteria["pdfua1"]:
        sem = [x for x in (row.get("semantic") or []) if x["outcome"] in ("fail", "warning", "info")]
        detail = rules_cell(row["rules"]) or html.escape(row["note"] or "")
        parts.append(f"<tr><td><span class='st st-{row['status']}'>{html.escape(_STATUS_MARK[row['status']])}</span></td><td>{row['id']} {html.escape(row['name'])}</td>"
                     f"<td>{detail}</td><td>{rules_cell(sem)}</td></tr>")
    parts.append("</table></div>")
    parts.append(f"<h3>WCAG 2.2, levels A and AA</h3><p class='sub'>{html.escape(tally_line(r.criteria['wcag22']))}</p>")
    parts.append("<div class='wrap'><table class='crit'><tr><th>Status</th><th>Success criterion</th><th>Level</th><th>Rules, or what a person checks</th></tr>")
    for row in r.criteria["wcag22"]:
        detail = rules_cell(row["rules"])
        if row["note"]:
            detail += ("<br>" if detail else "") + f"<span class='sub'>{html.escape(row['note'])}</span>"
        parts.append(f"<tr><td><span class='st st-{row['status']}'>{html.escape(_STATUS_MARK[row['status']])}</span></td><td>{row['id']} {html.escape(row['name'])}</td>"
                     f"<td>{row['level']}</td><td>{detail}</td></tr>")
    parts.append("</table></div>")
    return "".join(parts)



def to_html(results: Iterable[Result]) -> str:
    results = list(results)
    cat = load_catalogue()
    parts = [f"<!doctype html><meta charset='utf-8'><title>outloud report</title><style>{_CSS}</style><main>"]
    parts.append(f"<h1>outloud report</h1><p class='sub'>outloud {__version__} · {html.escape(_dt.datetime.now().strftime('%d %B %Y, %H:%M'))} · {len(results)} file(s)</p>")
    if len(results) > 1:
        parts.append("<h2>Summary</h2><div class='wrap'><table><tr><th>File</th><th>Verdict</th><th>Errors</th><th>Warnings</th><th>Pages</th><th>Seconds</th></tr>")
        for r in results:
            parts.append(f"<tr><td><a href='#{html.escape(os.path.basename(r.path))}'>{html.escape(os.path.basename(r.path))}</a></td>"
                         f"<td><span class='verdict v-{r.verdict}'>{r.verdict}</span></td><td>{r.errors}</td><td>{r.warnings}</td>"
                         f"<td>{r.stats.get('pages', '')}</td><td>{r.seconds:.2f}</td></tr>")
        parts.append("</table></div>")
    for r in results:
        name = html.escape(os.path.basename(r.path))
        parts.append(f"<h2 id='{name}'>{name} <span class='verdict v-{r.verdict}'>{r.verdict}</span></h2>")
        if r.error:
            parts.append(f"<p>Could not be checked: {html.escape(r.error)}</p>")
            continue
        parts.append(f"<p class='counts'><span><b>{r.errors}</b> error(s)</span><span><b>{r.warnings}</b> warning(s)</span><span><b>{r.infos}</b> info</span>"
                     f"<span>{r.stats.get('pages', '?')} page(s)</span><span>{r.stats.get('elements', '?')} structure element(s)</span><span>{r.seconds:.2f}s</span></p>")
        fs = r.sorted_findings()
        if not fs:
            parts.append("<p>No findings.</p>")
        else:
            parts.append("<div class='wrap'><table><tr><th>Severity</th><th>Rule</th><th>Page</th><th>Finding</th><th>Evidence</th></tr>")
            for f in fs:
                meta = cat.get(f.rule)
                title = html.escape(meta.title if meta else f.rule)
                std = ""
                if meta and meta.clause:
                    std = f"<br><span class='sub'>ISO 14289-1 {html.escape(meta.clause)}" + (f", Matterhorn {html.escape(meta.matterhorn)}" if meta.matterhorn else "") + "</span>"
                elif meta:
                    std = "<br><span class='sub'>semantic check</span>"
                if meta and meta.wcag:
                    std += f"<span class='sub'> · WCAG {html.escape(', '.join(meta.wcag))}</span>"
                if meta and meta.fix:
                    std += f"<br><span class='fix'>Fix: {html.escape(meta.fix)}</span>"
                parts.append(f"<tr><td><span class='sev sev-{f.severity}'>{f.severity}</span></td><td class='rule'>{f.rule}<br><span class='sub'>{title}</span></td>"
                             f"<td>{f.page or ''}</td><td>{html.escape(f.message)}{std}</td><td class='ev'>{html.escape(f.evidence or '')}</td></tr>")
            parts.append("</table></div>")
        parts.append(_criteria_html(r))
        ran = [x for x in r.runs if x.status == "ran"]
        na = [x for x in r.runs if x.status == "not-applicable"]
        skipped = [x for x in r.runs if x.status not in ("ran", "not-applicable")]
        parts.append(f"<details><summary>{len(ran)} rule(s) ran, {len(na)} not applicable to this file, {len(skipped)} did not run</summary><ul>")
        for x in na + skipped:
            parts.append(f"<li class='rule'>{x.rule}: {x.status}{(' — ' + html.escape(x.reason)) if x.reason else ''}</li>")
        parts.append("</ul></details>")
    parts.append("<h2>About</h2><p class='sub'>outloud tests PDF/UA-1 conformance (ISO 14289-1, Matterhorn Protocol 1.1 checkpoints), maps every rule to WCAG 2.2, and adds semantic checks that a validator cannot make: "
                 "whether the tags match what the page paints and whether the words a reader is given are the words a person would use. "
                 "It is an evaluation, not a certification. Rules marked semantic are heuristics; each names what it saw so a person can judge.</p></main>")
    return "".join(parts)


def rules_table() -> str:
    """Plain-text listing of the catalogue, for --list-rules."""
    lines = [f"{'id':<9} {'layer':<12} {'severity':<8} {'clause':<9} {'mh':<3} {'wcag':<18} {'status':<12} title"]
    for m in all_rules():
        status = m.status if m.fn is None or m.status == "planned" else "implemented"
        lines.append(f"{m.id:<9} {m.layer:<12} {m.severity:<8} {(m.clause or '-'):<9} {(m.matterhorn or '-'):<3} {(', '.join(m.wcag) or '-'):<18} {status:<12} {m.title}")
    return "\n".join(lines)

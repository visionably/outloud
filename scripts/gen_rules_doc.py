#!/usr/bin/env python3
"""Generate docs/RULES.md from the catalogue and the registry, so the documentation cannot drift from the code."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outloud.criteria import MATTERHORN, WCAG22  # noqa: E402
from outloud.registry import all_rules  # noqa: E402

GROUP_TITLES = {
    "document": "Document", "tagging": "Tagging", "text": "Text and fonts", "headings": "Headings", "tables": "Tables",
    "lists": "Lists", "figures": "Figures", "links": "Links, annotations and forms", "forms": "Forms", "notes": "Notes and references",
    "math": "Mathematics", "order": "Reading order", "navigation": "Navigation", "pagination": "Pagination",
    "quality": "Source comparison (needs --source)",
}


def main() -> None:
    rules = all_rules()
    out = ["# outloud rules", "",
           "Every rule outloud can run, generated from `src/outloud/rules/catalogue.yaml` by `scripts/gen_rules_doc.py`.", "",
           "**Layers.** *Conformance* rules test a requirement of ISO 14289-1 (PDF/UA-1), the same requirements the "
           "Matterhorn Protocol lists and that veraPDF and PAC test; the clause and checkpoint are given. *Semantic* rules test "
           "what a conformant file can still get wrong: whether the tags match the page and whether the words a reader is given "
           "are the words a person would use. No validator tests these; each names its evidence so a person can judge.", "",
           "**Severity.** *error*: a screen-reader user loses content or cannot proceed. *warning*: content is reachable but degraded "
           "or misleading. *info*: worth a look, not counted in the verdict.", "",
           "**Criteria.** Every rule names the Matterhorn Protocol 1.1 checkpoint and the WCAG 2.2 success criteria it tests; "
           "`outloud file.pdf --criteria` rolls the results up per checkpoint and per criterion. *Requires* names the document "
           "feature the rule is about: a file without it gets *not applicable* for the rule, not *pass*.", ""]
    implemented = sum(1 for r in rules if r.fn is not None and r.status != "planned")
    out.append(f"{len(rules)} rules in the catalogue, {implemented} implemented, {len(rules) - implemented} planned.")
    out.append("")
    by_group: dict[str, list] = {}
    for r in rules:
        by_group.setdefault(r.group, []).append(r)
    for group, items in by_group.items():
        out.append(f"## {GROUP_TITLES.get(group, group.title())}")
        out.append("")
        out.append("| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for r in items:
            std = f"ISO 14289-1 {r.clause}" if r.clause else "—"
            if r.matterhorn:
                std += f", Matterhorn {r.matterhorn}"
            status = "planned" if r.status == "planned" or r.fn is None else "implemented"
            wcag = ", ".join(r.wcag) if r.wcag else "—"
            req = r.requires or "—"
            out.append(f"| **{r.id}** {r.title} | {r.layer} | {r.severity} | {std} | {wcag} | {req} | {status} | {r.claim} | {r.fix or ''} |")
        out.append("")
    # criteria indexes
    out.append("## Matterhorn Protocol 1.1 checkpoints")
    out.append("")
    out.append("| Checkpoint | Conformance rules | Semantic rules (beyond the protocol) |")
    out.append("|---|---|---|")
    for cid, name in MATTERHORN:
        conf = [r.id for r in rules if r.matterhorn == cid and r.layer == "conformance"]
        sem = [r.id for r in rules if r.matterhorn == cid and r.layer != "conformance"]
        out.append(f"| {cid} {name} | {', '.join(conf) or '—'} | {', '.join(sem) or '—'} |")
    out.append("")
    out.append("## WCAG 2.2 success criteria (A and AA)")
    out.append("")
    out.append("| Criterion | Level | Rules | When no rule applies |")
    out.append("|---|---|---|---|")
    for sid, name, level, requires, note in WCAG22:
        mapped = [r.id for r in rules if sid in r.wcag]
        when = note or ""
        if requires == "never":
            when = "Not applicable to a document. " + (note or "")
        elif requires:
            when = f"Not applicable without {requires.replace('|', ' or ')}. " + (note or "")
        out.append(f"| {sid} {name} | {level} | {', '.join(mapped) or '—'} | {when.strip()} |")
    out.append("")
    path = Path(__file__).resolve().parents[1] / "docs" / "RULES.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path} ({len(rules)} rules)")


if __name__ == "__main__":
    main()

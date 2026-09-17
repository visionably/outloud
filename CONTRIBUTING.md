# Contributing to outloud

The most useful contribution is a PDF that outloud gets wrong: a finding that is not a defect, or a defect it passes. Open an issue with the file, or a description good enough to build a fixture from.

## Set up

```bash
git clone https://github.com/visionably/outloud && cd outloud
uv venv .venv && uv pip install -e ".[dev]"      # or: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Add a rule

A rule is three things, and a pull request needs all three.

1. **A catalogue entry** in `src/outloud/rules/catalogue.yaml`: id, title, the claim in plain words, layer (`conformance` or `semantic`), ISO 14289-1 clause, Matterhorn checkpoint, WCAG 2.2 criteria, the document feature it `requires`, severity, and a one-sentence `fix`.
2. **A function** registered with `@rule("ID")` in the matching module under `src/outloud/rules/`. It reads the `Document` model and yields `finding(...)`; give it `boxes=` whenever the defect has a place on the page.
3. **A fixture and a test**: a case in `tests/test_rules.py` that bends exactly one thing in a clean file, and the same case in `scripts/make_fixtures.py`.

Then run `scripts/gen_rules_doc.py`, and for a conformance rule run `scripts/compare_verapdf.py` on the new fixture. If veraPDF disagrees, say who is right and why in the catalogue entry; if veraPDF has no such test, mark the rule `verapdf: no`.

## Ground rules

- Conformance rules must agree with veraPDF on every fixture unless the catalogue says why not.
- Semantic rules name their evidence and prefer a warning to an error when a person could reasonably disagree.
- A rule that does not apply to a file reports *not applicable*, never *pass*.
- No network calls, no telemetry, nothing that leaves the machine.

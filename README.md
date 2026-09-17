# outloud

What a PDF says out loud. A fast, scriptable accessibility checker for the terminal: it tests PDF/UA-1 conformance the way veraPDF and PAC do, maps every rule to WCAG 2.2, and then asks the questions a validator cannot: do the tags match what the page paints, and are the words a screen reader is given the words a person would use.

Runs on macOS, Linux and Windows. One command, one file or a thousand, results as text, JSON, SARIF or HTML.

```
$ outloud report.pdf
REVIEW     report.pdf: 0 error(s), 6 warning(s), 0 info  [31 page(s), 2.94s]
  WARNING TBL-011   p.28   6 data cell(s) are associated only with empty header cells
          Data cells are headed only by silence — semantic check, no validator tests this · WCAG 1.3.1
          fix: Put the heading text in the TH cells, or point /Headers at the cells that carry it.
  PDF/UA-1 checkpoints: 16 pass · 12 not applicable · 3 need a person
  WCAG 2.2 A/AA:        1 warning · 10 pass · 27 not applicable · 17 need a person
```

That file passes veraPDF. Its appendix table has header cells with nothing in them, so a screen reader announces every value in it against silence. outloud exists for findings like that one.

## Install

```bash
pipx install outloud        # or: uv tool install outloud
outloud --version
```

From a clone:

```bash
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/outloud --list-rules
```

Python 3.10 or later. No Java, no GUI, no Windows-only anything.

## Use

```bash
outloud file.pdf                         # findings on the terminal, exit 1 if any error
outloud a.pdf b.pdf reports/             # several files; directories are searched
outloud out.pdf --source in.pdf          # also compare a remediated file with its source
outloud *.pdf --json r.json --sarif r.sarif --html r.html
outloud file.pdf --layer conformance     # only the rules a validator would run
outloud file.pdf --only TBL-011,TAG-003  # or --skip
outloud --list-rules
```

Verdicts: **pass** (nothing at error or warning level), **review** (warnings only), **fail** (at least one error), **unreadable**. `--fail-on warning` makes warnings fail the exit status; `--fail-on never` reports without failing, for dashboards.

Every finding ends with a one-line **fix**: what to change, for the person who has to. SARIF output plugs into GitHub code scanning and most CI systems, with the fix as the rule's help text and every rule related to its WCAG 2.2 criteria through a taxonomy. The HTML report is a single self-contained file.

## Pass and fail by criterion

```bash
outloud report.pdf --criteria
```

adds the two views PAC gives: every checkpoint of the **Matterhorn Protocol 1.1** (the 31 checkpoints that organise PDF/UA-1) and every **WCAG 2.2 success criterion at levels A and AA** (all 55), each with a status and the rules behind it.

```
PDF/UA-1 · Matterhorn Protocol 1.1 checkpoints — 16 pass · 12 not applicable · 3 need a person
  PASS    01 Real content tagged          9 rules pass
  PASS    02 Role mapping                 TAG-010, TAG-011, TAG-012 pass
  N/A     03 Flickering
  PERSON  04 Color and contrast           Check that colour is not the only carrier of meaning ...
  ...
  PASS    15 Tables                       TBL-001, TBL-002, TBL-003, TBL-004, TBL-005 pass   [beyond the protocol: TBL-011 warning]

WCAG 2.2, levels A and AA — 1 warning · 10 pass · 27 not applicable · 17 need a person
  PASS    1.1.1   Non-text Content (A)  9 rules pass · MATH-001, MATH-010, MATH-011 n/a
  WARN    1.3.1   Info and Relationships (A)  TBL-011 warning · 44 rules pass · 9 rules n/a
  PERSON  1.4.3   Contrast (Minimum) (AA)  Text needs 4.5:1 contrast against its background ...
  N/A     3.3.2   Labels or Instructions (A)  FRM-001, FRM-002 n/a
```

Five statuses, and the list is honest about all of them. **Fail** and **warning** come from the rules. **Pass** means every rule mapped to the criterion ran and found nothing. **Not applicable** means the file has nothing the criterion is about: no form fields, so nothing to label; no media, so nothing can flicker. Rules are marked not applicable the same way (`requires` in the catalogue), so a file without tables passes no table rule and fails none. **Need a person** names what a person still has to look at, with a sentence on what. For the PDF/UA view, a checkpoint's status comes from the conformance rules, as a validator would count it; the semantic rules mapped to the same checkpoint are shown beside it as *beyond the protocol*. For WCAG they count in full, because 1.1.1 asks whether the alternative is equivalent, not whether the key exists.

The same tables are in the JSON (`criteria`), the HTML report, and the viewer's **Criteria** tab, where clicking a criterion filters the findings to the rules behind it.

Library use:

```python
from outloud import check
result = check("report.pdf")
print(result.verdict, result.errors, result.warnings)
for f in result.sorted_findings():
    print(f.rule, f.page, f.message)
```

## See where the problems are

```bash
outloud report.pdf --view
```

opens the result in your browser: every page rendered with each finding's location outlined, a findings list that jumps to the outline when clicked (with the fix under each finding), the criteria tab with the PDF/UA-1 and WCAG 2.2 views, the logical structure tree (click an element to see where it sits on the page), and a preview of each page in the order a screen reader following the structure would read it, with artifacts shown separately as what a reader skips. It is the views PAC gives, served from a small local server that binds to localhost and stops with Ctrl+C (`--no-browser` prints the URL instead of opening a window). Nothing leaves the machine and nothing is installed beyond the package itself.

The same boxes are in the JSON and SARIF output (`boxes`, in PDF user space with a page number), so other tools can highlight them too.

## What it checks

Every rule is data in [`src/outloud/rules/catalogue.yaml`](src/outloud/rules/catalogue.yaml) and documented in [`docs/RULES.md`](docs/RULES.md), generated from it. Each rule states its claim in plain words, the ISO 14289-1 clause and Matterhorn Protocol checkpoint it rests on, the WCAG 2.2 success criteria it tests, the document feature it needs to apply, which layer it belongs to, and what to change.

**Conformance rules** test a requirement of PDF/UA-1: the document is tagged, titled and identified; every glyph maps to a character and every font is embedded; headings do not skip levels; tables have headers with scope; lists, notes, links, forms and formulae are built the way the standard says. These are the rules veraPDF and PAC run, and on them outloud is calibrated to agree with veraPDF.

**Semantic rules** test what a conformant file can still get wrong. Words printed on the page that no structure element announces. Prose marked as an artifact so readers skip it. Header cells that are empty, or shredded one word per row. Alternative text that is a file name, a caption repeated, or LaTeX source. A formula that hides a sentence. A page that paints its content in a different order from the tag tree, so Preview, Chrome and copy-paste read it differently from a screen reader. A title that is the file name. Each finding names its evidence so a person can judge it; none of them are tested by any validator.

With `--source`, three more rules compare a remediated file with its original: structure lost, text lost, pages that no longer look the same.

90 rules in the catalogue; 88 implemented; 2 planned and reported as "not run" so the gap is visible.

## How it compares

Measured on 17 September 2026 on the same machine: veraPDF 1.26.5 (`--flavour ua1`) and outloud timed per file including each tool's start-up; [pdfa11y](https://github.com/speedata/pdfa11y) (speedata's Go checker, built from its 25 July 2026 source) timed as one process over the corpus, which is how it is meant to run.

| Corpus | Files | outloud agrees with veraPDF | pdfa11y agrees with veraPDF | veraPDF | outloud | pdfa11y |
|---|---|---|---|---|---|---|
| Fixtures (one defect each, built from scratch) | 58 | 58 of 58 comparable rules | 51 | 34.5 s | 0.2 s | 0.1 s |
| Bank letters, remediated to PDF/UA-1 | 29 | 29 of 29 | 0 | 30.8 s | 6.9 s | 0.8 s |
| Bank letters, as printed by Chrome | 29 | 29 of 29 | 29 | 23.7 s | 2.4 s | 0.3 s |
| Production corpus, originals | 23 | 23 of 23 | 23 | 20.9 s | 9.8 s | 1.2 s |
| Production corpus, remediated | 21 | 21 of 21 | 1 | 20.2 s | 9.5 s | 0.4 s |

On the 21 remediated production files that veraPDF calls compliant, outloud's semantic layer still reports something on 9: silent header cells, shredded headers, actual text that does not match the glyphs, pages painted out of reading order. Those are the findings the tool is for.

pdfa11y fails every remediated file in both corpora. Its XMP reader is a regular expression that does not match a `pdfuaid:part` element carrying its own namespace declaration, which is valid RDF and what our pipeline writes; it also keys fonts by name, so two subset fonts with the same name are checked against each other's Unicode maps. Neither is a defect in the files. On the fixtures it misses a remapped standard type, a shared marked-content id and a CID font without a glyph map, and it reports a non-embedded font as a warning where the standard says shall. It is a well-built tool, and reading its code gave outloud the not-applicable outcome, the fix line on every rule and five conformance rules; the full account, disagreement by disagreement, is in [`docs/COMPARISON-pdfa11y.md`](docs/COMPARISON-pdfa11y.md).

Speed is honest rather than headline. outloud is 2 to 10 times faster than veraPDF, mostly because it has no JVM to start, and 5 to 20 times slower than pdfa11y, because the walker is Python and every glyph costs a loop iteration. A 31-page report checks in about three seconds; a 101-page journal article in under two. A compiled core is the plan once the rule set settles.

Agreement is measured on the rules both tools have. Eight of outloud's conformance rules test requirements veraPDF's profile does not (marked `verapdf: no` in the catalogue); the comparison script reports those separately rather than counting them against either tool. The scripts are [`scripts/compare_verapdf.py`](scripts/compare_verapdf.py) and [`scripts/compare_pdfa11y.py`](scripts/compare_pdfa11y.py); run them on your own files.

## How it works

`model.py` reads the file once with pikepdf and resolves what is easy to get wrong: role-mapped types, inherited page references, marked-content references inside form XObjects, attributes by owner, fonts with their Unicode mapping and embedding status. `content.py` walks each page's content stream and records every painted text run with its characters, position and marked-content tag, walking form XObjects in place. Glyph-by-glyph text operators are merged into words and lines, TJ kerning gaps become spaces, and ligatures are normalised, because otherwise no rule can find a word in a file written by Chrome, Word or TeX. Rules read that model and nothing else.

## Fixtures and tests

`tests/builder.py` constructs small tagged PDFs from nothing: a subset TrueType font with a ToUnicode CMap, marked content, a structure tree with a parent tree, XMP with `dc:title` and `pdfuaid:part`. Every negative test bends exactly one thing in a clean baseline and asserts that one rule fires. `scripts/make_fixtures.py` writes the same fixtures to `fixtures/` so you can open them, or run veraPDF on them.

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/make_fixtures.py
.venv/bin/python scripts/gen_rules_doc.py
```

## What it is not

It is an evaluation, not a certification, and not legal advice. Semantic rules are heuristics with thresholds; they name what they saw and can be wrong about what it means. The Matterhorn failure-condition ids are not yet verified against the protocol text, so the catalogue cites checkpoints only. A "pass" on a WCAG criterion means the automated rules mapped to it found nothing, not that the criterion is met; the criteria that need a person say so. It does not measure colour contrast, and it does not yet check heading levels beyond H6 or cross-page reading order (planned rules HDG-004, ORD-002). It tests PDF/UA-1 only; PDF/UA-2 files are checked against the UA-1 rules.

## Contributing

A rule is a catalogue entry plus a function plus a fixture. Add the entry to `catalogue.yaml` (id, claim, layer, clause, matterhorn, wcag, requires, severity, fix), register the function with `@rule("ID")` in the right module under `src/outloud/rules/`, add a case to `tests/test_rules.py` and `scripts/make_fixtures.py`, and run the comparison scripts against veraPDF and pdfa11y on the new fixture. If the tools disagree, say which is right and why in the catalogue entry.

## Licence

Apache 2.0. Built by [Visionably](https://visionably.ai) and released so that checking a PDF for accessibility costs nothing and runs anywhere.

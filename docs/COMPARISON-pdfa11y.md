# outloud and pdfa11y

[pdfa11y](https://github.com/speedata/pdfa11y) is speedata's open-source PDF/UA checker: a single Go binary, MIT-licensed, with 112 checks across PDF/UA-1 and PDF/UA-2, a WCAG mapping and a fix hint on every check, tri-state PASS / WARN / FAIL / not-applicable reporting, JSON, JSONL, HTML and a tagged-PDF report, and a WebAssembly build that runs in the browser. It is the closest project to outloud and this page records what we found when we read its code and ran it on our corpora on 17 September 2026 (commit of 25 July 2026, built from source with Go 1.27).

## What pdfa11y does that outloud now does too

Reading their code changed outloud. These came straight from it:

- **Tri-state results.** A rule about tables on a file without tables was "passed" in outloud 0.1; it is now *not applicable*, declared per rule as `requires` in the catalogue and evaluated once per document. pdfa11y does this per check with an explicit severity.
- **A fix on every rule.** Every pdfa11y finding carries a hint. Every outloud rule now carries a `fix` line, shown under the finding on the terminal, in the HTML, in the viewer, and as SARIF help text.
- **WCAG mapping.** pdfa11y maps each check to WCAG 2.x criteria and prints them with `--wcag`. outloud maps each rule to WCAG 2.2 and, further, rolls the results up per success criterion and per Matterhorn checkpoint (`--criteria`), which pdfa11y does not do.
- **Five conformance rules we lacked** and that veraPDF tests: optional content configurations without a name or with `/AS` (DOC-030, was planned), table sub-element nesting and row-group cardinality (TBL-005), `CIDFontType2` without `/CIDToGIDMap` (TXT-007), Info-title versus XMP-title disagreement (DOC-015, a warning veraPDF does not test), and bookmarks on long documents (NAV-001, WCAG 2.4.5, a warning).

## What pdfa11y has that outloud does not

- **PDF/UA-2.** 43 of its checks are UA-2 only (namespaces, FENote, MathML associated files, the heading model without level limits). outloud tests PDF/UA-1 only.
- **Speed.** It is a compiled binary with no rendering step. On our corpora it is 10 to 40 times faster than outloud (see the table below). outloud's walker is Python and pays per glyph.
- **JSONL streaming, a browser build, a tagged-PDF report.**
- **Per-element language checks** (UA-11-002 and friends), which PDF/UA-1 does ask for and which outloud reports only at document level.

## What outloud has that pdfa11y does not

- **The semantic layer**: 39 rules that no validator runs, on what a conformant file still gets wrong (silent header cells, shredded headers, alternative text that hides a sentence, prose tagged as a formula, pages painted out of tag order, running heads tagged as content, titles that are file names). pdfa11y checks that keys exist; outloud also reads what they say against what the page paints.
- **Word-level text**: outloud merges glyph-per-operator text into words and lines, normalises ligatures, and inserts spaces for kerning gaps, so rules can find a word in a file written by Chrome, Word or TeX. pdfa11y decodes glyphs through ToUnicode for its checks but has no word model.
- **Locations you can see**: findings carry bounding boxes and the viewer outlines them on the rendered page. pdfa11y gives a page number and a structure path.
- **Criteria roll-up**: pass, fail, warning, not applicable or needs-a-person per Matterhorn checkpoint and per WCAG 2.2 success criterion, on the terminal, in JSON and HTML, and in the viewer.
- **Source comparison** (`--source`): structure, text and appearance lost between an original and its remediated copy.

## Where they disagree, and who is right

`scripts/compare_pdfa11y.py` runs both over the same files. On our 58 one-defect fixtures they agree on 51. The seven disagreements:

| Fixture | pdfa11y | outloud | Who is right |
|---|---|---|---|
| Standard structure type remapped in /RoleMap | pass | fail (TAG-012) | outloud; ISO 14289-1 7.1 forbids it and veraPDF fails it. pdfa11y has the check (UA-31-010) but it did not fire. |
| One marked-content id claimed by two elements | pass | fail (TAG-022) | outloud; neither pdfa11y nor veraPDF tests this. |
| Table with no header cells | pass | fail (TBL-001) | outloud's reading of 7.5; veraPDF does not test it either, so it is marked `verapdf: no`. |
| Font not embedded | warning | fail (TXT-001) | outloud; 7.21.3.1 says shall, and veraPDF fails it. |
| CIDFontType2 without /CIDToGIDMap | pass | fail (TXT-007) | outloud; veraPDF fails it. pdfa11y has the check (UA-31-001) but it did not fire. |
| Link element with no text (empty page content) | fail (untagged content) | pass on conformance; LNK-003 is semantic | pdfa11y counts a content-stream scan error on an empty stream as an untagged painting operator. |
| Encrypted file with extraction permission denied | fail (language tag malformed) | info | pdfa11y reads the encrypted /Lang string without decrypting it. |

On real files the picture is one-sided. All 29 remediated bank letters and 20 of 21 remediated production files, which veraPDF and outloud both pass, **fail** in pdfa11y:

- **UA-06-003, "XMP contains no pdfuaid:part"**, on every one of them. Its XMP reader is a regular expression that wants `<pdfuaid:part>1</pdfuaid:part>` and does not match `<pdfuaid:part xmlns:pdfuaid="…">1</pdfuaid:part>`, which is valid RDF and what our pipeline writes. veraPDF parses the XML and accepts it.
- **UA-10-002, "renders codes not covered by /ToUnicode"**, on 27 letters. The letters carry two subset fonts with the same `/BaseFont` name and different CMaps; pdfa11y keys fonts by name and checks one font's codes against the other's CMap. Each font covers every code it shows.
- **UA-19-001, "Note's /Ref target has no /ID"**, on 3 production files. PDF/UA-1 requires an /ID on the Note (7.9), not on the element the Note points at; veraPDF does not test this either.
- **UA-14-001** once, for a `<scan-error>` in its own tokenizer.

None of these is a defect in the files. So on the corpora pdfa11y's verdicts agree with veraPDF on 52 of 52 files that are not PDF/UA (both fail them) and on 1 of 50 that are. outloud agrees with veraPDF on all 102.

## Numbers

Wall-clock on the same machine, 17 September 2026. pdfa11y checks a whole corpus in one process; outloud and veraPDF are timed per file including start-up, which is most of veraPDF's cost.

| Corpus | Files | pdfa11y agrees with outloud's conformance verdict | pdfa11y | outloud |
|---|---|---|---|---|
| Fixtures, one defect each | 58 | 51 | 0.1 s | 0.4 s |
| Bank letters, remediated (veraPDF: all pass) | 29 | 0 | 0.8 s | 7.9 s |
| Bank letters, as printed by Chrome (all fail) | 29 | 29 | 0.3 s | 2.9 s |
| Production originals (all fail) | 23 | 23 | 1.2 s | 11.5 s |
| Production remediated (veraPDF: all pass) | 21 | 1 | 0.4 s | 9.5 s |

The remediated-corpus figure is after the dense-page guard in TAG-003; the other outloud times were measured while a veraPDF run shared the machine, so the README table is the one to quote. The ratio is the point, not the decimals.

## What we take from it

pdfa11y is well built, and its README is honest about what it is: the machine-checkable subset of Matterhorn, scriptable and fast, next to veraPDF rather than instead of it. Its false positives on our files are parser shortcuts (a regex for XMP, fonts keyed by name, no decryption of strings, an empty stream counted as content), all fixable, and we have reported what we found rather than guessed at their roadmap. The gap it does not try to close is the one outloud exists for: whether the tags a file has are the right ones.

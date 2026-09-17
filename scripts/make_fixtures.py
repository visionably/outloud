#!/usr/bin/env python3
"""Write the fixture corpus to fixtures/: one PDF per defect, plus the clean baseline.

    python3 scripts/make_fixtures.py [outdir]

The same builder the tests use produces these, so a fixture on disk is
exactly what a test checks. Names say what is wrong: `fail-DOC-013-no-lang.pdf`
should trip DOC-013 and nothing at error level besides; `pass-clean.pdf`
should pass every rule. Run veraPDF over the folder to see where the two
agree and where a semantic rule finds what a validator cannot.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tests.builder import Block, Fixture, clean  # noqa: E402

CASES = {
    "pass-clean": lambda: clean(),
    "fail-DOC-001-not-marked": lambda: Fixture(marked=False).p("Some text."),
    "fail-DOC-002-no-struct-tree": lambda: Fixture(tagged=False).p("Some text."),
    "fail-DOC-003-suspects": lambda: Fixture(suspects=True).p("Some text."),
    "fail-DOC-010-no-title": lambda: Fixture(title=None).p("Some text."),
    "fail-DOC-011-no-display-title": lambda: Fixture(display_title=False).p("Some text."),
    "fail-DOC-012-no-pdfuaid": lambda: Fixture(ua_part=False).p("Some text."),
    "fail-DOC-013-no-lang": lambda: Fixture(lang=None).p("Some text."),
    "warn-DOC-014-bad-lang": lambda: Fixture(lang="english").p("Some text."),
    "info-DOC-020-no-extract-permission": lambda: Fixture(encrypt_no_access=True).p("Some text."),   # qpdf cannot clear the accessibility bit, so this shows the info case
    "warn-DOC-040-filename-title": lambda: Fixture(title="report_final_v2.pdf").p("Some text."),
    "fail-TAG-001-untagged-text": lambda: clean().untagged("This sentence is painted with no tag at all."),
    "fail-TAG-002-artifacted-prose": lambda: clean().artifact("This is a whole sentence of real content that someone has hidden inside an artifact so that readers skip it entirely."),
    "fail-TAG-010-unmapped-type": lambda: clean().add(Block("P", "Custom element", type_raw="Fancy")),
    "fail-TAG-011-circular-rolemap": lambda: Fixture(role_map={"A": "B", "B": "A"}).add(Block("P", "Custom", type_raw="A")),
    "fail-TAG-012-remapped-standard-type": lambda: Fixture(role_map={"P": "Div"}).p("Text"),
    "warn-TAG-020-empty-element": lambda: clean().p(""),
    "fail-TAG-022-shared-mcid": lambda: clean().add(Block("P", "Shared content", mcid_twice=True)),
    "fail-TAG-031-alt-hides-content": lambda: clean().p("A paragraph of a dozen or more words whose alternative text is a single short phrase that hides most of it.", alt="A phrase"),
    "fail-TAG-032-actualtext-coverage": lambda: clean().p("The original words: quality, distribution, treatment, network, sampling, results.", actual_text="Something different entirely here"),
    "fail-TXT-001-font-not-embedded": lambda: Fixture(embed_font=False).p("Helvetica is not embedded."),
    "fail-TXT-002-no-tounicode": lambda: Fixture(tounicode=False).p("No way back to Unicode."),
    "warn-TXT-004-tounicode-collisions": lambda: Fixture(tounicode_collide=True).p("Every letter maps to the same character."),
    "fail-TXT-011-form-text-untagged": lambda: clean().form_text("Text inside a form XObject."),
    "fail-HDG-001-skipped-level": lambda: Fixture().h(1, "Top").p("Text.").h(3, "Too deep"),
    "fail-HDG-002-first-not-h1": lambda: Fixture().h(2, "Starts at two").p("Text."),
    "fail-HDG-003-mixed-headings": lambda: Fixture().h(1, "Numbered").h(0, "Unnumbered"),
    "warn-HDG-010-heading-is-salutation": lambda: Fixture().h(1, "Dear Sir or Madam,").p("Text."),
    "fail-TBL-001-no-header-cells": lambda: Fixture().table([["a", "b"], ["c", "d"]], header_row=False),
    "fail-TBL-002-no-scope": lambda: Fixture().table([["Month", "Samples"], ["Jan", "24"]], scope=None),
    "fail-TBL-004-irregular": lambda: Fixture().table([["Month", "Samples", "Passed"], ["Jan", "24"]]),
    "fail-TBL-010-shredded-headers": lambda: Fixture().table([[("TH", "Due"), ("TH", "Date")], [("TH", "for"), ("TH", "payment")], [("TH", "of"), ("TH", "interest")], [("TH", "on"), ("TH", "bonds")], [("TD", "1 Jan"), ("TD", "2 Feb")]]),
    "warn-TBL-011-silent-headers": lambda: Fixture().table([["Month", "Samples"], ["Jan", "24"], ["Feb", "22"]], headers_ids=True, empty_th=True),
    "fail-LST-001-item-outside-list": lambda: Fixture().list(["one", "two"], li_outside=True),
    "warn-LST-002-no-lbody": lambda: Fixture().list(["one", "two"], no_lbody=True),
    "fail-FIG-001-no-alt": lambda: Fixture().figure(alt=None),
    "fail-FIG-002-blank-alt": lambda: Fixture().figure(alt="   "),
    "warn-FIG-010-placeholder-alt": lambda: Fixture().figure(alt="DSC_0042.jpg"),
    "info-FIG-011-alt-equals-caption": lambda: Fixture().figure(alt="Figure 1. The treatment works", caption="Figure 1. The treatment works"),
    "fail-LNK-001-link-outside-link-element": lambda: Fixture().link("Read more", in_link_element=False),
    "fail-LNK-002-no-contents": lambda: Fixture().link("Read more", contents=None),
    "fail-LNK-003-unnamed-link": lambda: Fixture().link("", contents="x"),
    "fail-LNK-005-no-tabs-order": lambda: Fixture(no_tabs=True).link("Read more"),
    "warn-LNK-004-no-print-flag": lambda: Fixture().link("Read more", flags=0),
    "warn-LNK-010-unlinked-uri": lambda: Fixture().p("Write to hello@example.org or visit https://example.org/help for more."),
    "fail-TAG-004-artifact-nesting": lambda: clean().add(Block("Raw", "/Artifact BMC /P <</MCID 99>> BDC BT /F1 11 Tf 1 0 0 1 72 300 Tm <0001> Tj ET EMC EMC", attrs={"claim_mcid": 99})),
    "fail-HDG-005-two-h-children": lambda: Fixture().h(0, "First").h(0, "Second"),
    "fail-NOTE-004-duplicate-note-ids": lambda: Fixture().add(Block("Note", "One.", attrs={"ID": "n1"})).add(Block("Note", "Two.", attrs={"ID": "n1"})),
    "fail-NOTE-001-note-without-id": lambda: Fixture().add(Block("Note", "A footnote.", attrs={"no_id": True})),
    "fail-MATH-001-formula-without-alt": lambda: Fixture().formula("a2 + b2 = c2", alt=None),
    "warn-MATH-010-formula-alt-is-latex": lambda: Fixture().formula("a2 + b2 = c2", alt="\\frac{a^2}{b^2}"),
    "warn-DOC-015-info-title-differs": lambda: Fixture(title="Annual report", info_title="Draft 3").p("Some text."),
    "fail-DOC-030-config-without-name": lambda: Fixture(oc_config_no_name=True).p("Some text."),
    "fail-DOC-030-oc-config-with-as": lambda: Fixture(oc_as=True).p("Some text."),
    "fail-TBL-005-stray-child": lambda: Fixture().table([["Month", "Samples"], ["Jan", "24"]], attrs={"stray_child": "P"}),
    "fail-TXT-007-no-cidtogidmap": lambda: Fixture(no_cidtogid=True).p("Text without a glyph map."),
    "warn-NAV-001-long-document-no-bookmarks": lambda: _long(Fixture()),
    "pass-NAV-001-long-document-with-bookmarks": lambda: _long(Fixture(outlines=True)),
}


_TOPICS = ["sampling", "treatment", "distribution", "results", "costs", "staffing", "complaints", "repairs", "plans", "appendix"]


def _long(fx: Fixture, pages: int = 10) -> Fixture:
    fx.h(1, "A long document about water quality")
    for i in range(pages):
        if i:
            fx.page()
        fx.p(f"This part of the report covers {_TOPICS[i % len(_TOPICS)]} in some detail.")
    return fx


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    for name, make in CASES.items():
        make().build(str(out / f"{name}.pdf"))
    print(f"wrote {len(CASES)} fixtures to {out}")


if __name__ == "__main__":
    main()

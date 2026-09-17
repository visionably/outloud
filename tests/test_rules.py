"""One test per rule: a fixture with exactly that defect must trip the rule, and the clean fixture must not."""

from __future__ import annotations

import os

import pytest

from outloud import check
from outloud.findings import ERROR, WARNING
from outloud.registry import all_rules

from .builder import Block, Fixture, clean


@pytest.fixture(scope="session")
def tmp(tmp_path_factory):
    return tmp_path_factory.mktemp("fixtures")


def run(fx: Fixture, tmp, name: str, **kw):
    path = str(tmp / f"{name}.pdf")
    fx.build(path)
    return check(path, **kw)


def rules_hit(result) -> set[str]:
    return {f.rule for f in result.findings}


def assert_hits(result, rule_id: str, severity: str | None = None):
    hits = [f for f in result.findings if f.rule == rule_id]
    assert hits, f"{rule_id} not reported; findings: {[(f.rule, f.message) for f in result.findings]}"
    if severity:
        assert hits[0].severity == severity


# ── the baseline ────────────────────────────────────────────────────────

def test_clean_fixture_passes(tmp):
    r = run(clean(), tmp, "clean")
    assert r.error is None
    assert r.errors == 0, [(f.rule, f.message) for f in r.findings if f.severity == ERROR]
    assert r.warnings == 0, [(f.rule, f.message) for f in r.findings if f.severity == WARNING]
    assert r.verdict == "pass"
    assert not [x for x in r.runs if x.status == "crashed"], [(x.rule, x.reason) for x in r.runs if x.status == "crashed"]


def test_every_catalogue_rule_ran_or_is_accounted_for(tmp):
    r = run(clean(), tmp, "clean2")
    statuses = {x.rule: x.status for x in r.runs}
    for meta in all_rules():
        assert meta.id in statuses
        assert statuses[meta.id] in ("ran", "not-implemented", "skipped", "not-applicable")


# ── document ────────────────────────────────────────────────────────────

def test_doc_001_not_marked(tmp):
    assert_hits(run(Fixture(marked=False).p("Some text."), tmp, "doc001"), "DOC-001")


def test_doc_002_no_struct_tree(tmp):
    assert_hits(run(Fixture(tagged=False).p("Some text."), tmp, "doc002"), "DOC-002")


def test_doc_003_suspects(tmp):
    assert_hits(run(Fixture(suspects=True).p("Some text."), tmp, "doc003"), "DOC-003")


def test_doc_010_no_title(tmp):
    assert_hits(run(Fixture(title=None).p("Some text."), tmp, "doc010"), "DOC-010")


def test_doc_010_info_title_only(tmp):
    r = run(Fixture(title=None, info_title="Info only").p("Some text."), tmp, "doc010b")
    assert_hits(r, "DOC-010")
    assert "Info dictionary" in [f for f in r.findings if f.rule == "DOC-010"][0].message


def test_doc_011_display_title(tmp):
    assert_hits(run(Fixture(display_title=False).p("Some text."), tmp, "doc011"), "DOC-011")


def test_doc_012_ua_part(tmp):
    assert_hits(run(Fixture(ua_part=False).p("Some text."), tmp, "doc012"), "DOC-012")


def test_doc_013_no_lang(tmp):
    assert_hits(run(Fixture(lang=None).p("Some text."), tmp, "doc013"), "DOC-013")


def test_doc_014_bad_lang(tmp):
    assert_hits(run(Fixture(lang="english").p("Some text."), tmp, "doc014"), "DOC-014")
    assert "DOC-014" not in rules_hit(run(Fixture(lang="en-IN").p("Some text."), tmp, "doc014b"))


def test_doc_020_permissions(tmp):
    assert_hits(run(Fixture(encrypt_no_access=True).p("Some text."), tmp, "doc020"), "DOC-020")


def test_doc_040_title_quality(tmp):
    assert_hits(run(Fixture(title="report_final_v2.pdf").p("Some text."), tmp, "doc040"), "DOC-040")
    assert_hits(run(Fixture(title="Microsoft Word - notes.docx").p("Some text."), tmp, "doc040b"), "DOC-040")
    assert "DOC-040" not in rules_hit(run(Fixture(title="Annual report").p("Some text."), tmp, "doc040c"))


# ── tagging ─────────────────────────────────────────────────────────────

def test_tag_001_untagged_text(tmp):
    r = run(clean().untagged("This sentence is painted with no tag at all."), tmp, "tag001")
    assert_hits(r, "TAG-001", ERROR)


def test_tag_002_artifacted_prose(tmp):
    fx = clean().artifact("This is a whole sentence of real content that someone has hidden inside an artifact so that readers skip it entirely.")
    assert_hits(run(fx, tmp, "tag002"), "TAG-002")


def test_tag_002_ignores_running_footer(tmp):
    fx = Fixture()
    for i in range(4):
        fx.page().p(f"Body text of page {i + 1}, which differs on every page of this document.")
        fx.artifact("Annual water quality report of the town council, all rights reserved by the council", y_band="bottom")
    assert "TAG-002" not in rules_hit(run(fx, tmp, "tag002b"))


def test_tag_003_silent_words_via_actualtext(tmp):
    fx = clean().p("Seventeen distinct words appear in this paragraph but the replacement says something else entirely.",
                   actual_text="Short replacement")
    r = run(fx, tmp, "tag003")
    assert "TAG-003" in rules_hit(r) or "TAG-032" in rules_hit(r)


def test_tag_010_unmapped_type(tmp):
    assert_hits(run(clean().add(Block("P", "Custom element", type_raw="Fancy")), tmp, "tag010"), "TAG-010")


def test_tag_010_role_mapped_type_is_fine(tmp):
    fx = Fixture(role_map={"Fancy": "P"}).add(Block("P", "Custom element", type_raw="Fancy"))
    assert "TAG-010" not in rules_hit(run(fx, tmp, "tag010b"))


def test_tag_011_circular_rolemap(tmp):
    fx = Fixture(role_map={"A": "B", "B": "A"}).add(Block("P", "Custom", type_raw="A"))
    assert_hits(run(fx, tmp, "tag011"), "TAG-011")


def test_tag_012_remapped_standard(tmp):
    assert_hits(run(Fixture(role_map={"P": "Div"}).p("Text"), tmp, "tag012"), "TAG-012")


def test_tag_020_empty_element(tmp):
    assert_hits(run(clean().p(""), tmp, "tag020"), "TAG-020")


def test_tag_022_shared_mcid(tmp):
    assert_hits(run(clean().add(Block("P", "Shared content", mcid_twice=True)), tmp, "tag022"), "TAG-022")


def test_tag_030_page_figure(tmp):
    fx = clean().figure(alt="Scan of the page", attrs={"width": 590, "height": 760})
    for _ in range(3):
        fx.p("Enough tagged words on this page that the figure over it is clearly a scan being described as a picture of the page.")
    assert_hits(run(fx, tmp, "tag030"), "TAG-030")


def test_tag_031_alt_hides_content(tmp):
    fx = clean().p("A paragraph of a dozen or more words whose alternative text is a single short phrase that hides most of it.", alt="A phrase")
    assert_hits(run(fx, tmp, "tag031"), "TAG-031")


def test_tag_032_actualtext_coverage(tmp):
    fx = clean().p("The original words: quality, distribution, treatment, network, sampling, results.", actual_text="Something different entirely here")
    assert_hits(run(fx, tmp, "tag032"), "TAG-032")


# ── text ────────────────────────────────────────────────────────────────

def test_txt_001_not_embedded(tmp):
    assert_hits(run(Fixture(embed_font=False).p("Helvetica is not embedded."), tmp, "txt001"), "TXT-001")


def test_txt_002_no_tounicode(tmp):
    assert_hits(run(Fixture(tounicode=False).p("No way back to Unicode."), tmp, "txt002"), "TXT-002")


def test_txt_004_collisions(tmp):
    assert_hits(run(Fixture(tounicode_collide=True).p("Every letter maps to the same character."), tmp, "txt004"), "TXT-004")


def test_txt_010_invisible_text(tmp):
    fx = Fixture()
    for _ in range(3):
        fx.add(Block("P", "Invisible text with nothing underneath it at all on this page.", render_mode=3))
    assert_hits(run(fx, tmp, "txt010"), "TXT-010")


def test_txt_011_form_text_untagged(tmp):
    assert_hits(run(clean().form_text("Text inside a form XObject."), tmp, "txt011"), "TXT-011")
    assert "TXT-011" not in rules_hit(run(clean().form_text("Tagged form text.", tagged=True), tmp, "txt011b"))


# ── headings ────────────────────────────────────────────────────────────

def test_hdg_001_skipped_level(tmp):
    assert_hits(run(Fixture().h(1, "Top").p("Text.").h(3, "Too deep"), tmp, "hdg001"), "HDG-001")


def test_hdg_002_first_not_h1(tmp):
    assert_hits(run(Fixture().h(2, "Starts at two").p("Text."), tmp, "hdg002"), "HDG-002")


def test_hdg_003_mixed(tmp):
    assert_hits(run(Fixture().h(1, "Numbered").h(0, "Unnumbered"), tmp, "hdg003"), "HDG-003")


def test_hdg_010_fragment(tmp):
    assert_hits(run(Fixture().h(1, "and then the committee decided,"), tmp, "hdg010"), "HDG-010")
    assert_hits(run(Fixture().h(1, "Dear Sir or Madam,"), tmp, "hdg010b"), "HDG-010")
    assert "HDG-010" not in rules_hit(run(Fixture().h(1, "References"), tmp, "hdg010c"))


def test_hdg_011_paragraph(tmp):
    long = "This heading is really a paragraph. It runs on for several sentences. It says far more than a heading should say, and keeps going for a while longer than that."
    assert_hits(run(Fixture().h(1, long), tmp, "hdg011"), "HDG-011")


def test_hdg_012_no_headings(tmp):
    fx = Fixture()
    for i in range(6):
        fx.page()
        for _ in range(5):
            fx.p("A long document made of paragraphs alone, with nothing for a reader to navigate by from one section to the next.")
    assert_hits(run(fx, tmp, "hdg012"), "HDG-012")


# ── tables ──────────────────────────────────────────────────────────────

def test_tbl_001_no_headers(tmp):
    assert_hits(run(Fixture().table([["a", "b"], ["c", "d"]], header_row=False), tmp, "tbl001"), "TBL-001")


def test_tbl_002_no_scope(tmp):
    assert_hits(run(Fixture().table([["Month", "Samples"], ["Jan", "24"]], scope=None), tmp, "tbl002"), "TBL-002")
    assert "TBL-002" not in rules_hit(run(Fixture().table([["Month", "Samples"], ["Jan", "24"]], scope=None, headers_ids=True), tmp, "tbl002b"))


def test_tbl_004_irregular(tmp):
    assert_hits(run(Fixture().table([["Month", "Samples", "Passed"], ["Jan", "24"]]), tmp, "tbl004"), "TBL-004")


def test_tbl_010_shredded_headers(tmp):
    rows = [[("TH", "Due"), ("TH", "Date")], [("TH", "for"), ("TH", "payment")], [("TH", "of"), ("TH", "interest")], [("TH", "on"), ("TH", "bonds")], [("TD", "1 Jan"), ("TD", "2 Feb")]]
    assert_hits(run(Fixture().table(rows), tmp, "tbl010"), "TBL-010")


def test_tbl_011_silent_headers(tmp):
    fx = Fixture().table([["Month", "Samples"], ["Jan", "24"], ["Feb", "22"]], headers_ids=True, empty_th=True)
    assert_hits(run(fx, tmp, "tbl011"), "TBL-011")


def test_tbl_012_mostly_empty(tmp):
    assert_hits(run(Fixture().table([["A", "", ""], ["", "", ""], ["", "", "x"]]), tmp, "tbl012"), "TBL-012")


def test_tbl_015_collapsed_rows(tmp):
    rows = [["Name", "Qty", "Price"], ["Apples fresh from the orchard this week"], ["Pears ripe and ready to eat now"], ["Plums", "3", "9"], ["Figs", "2", "8"]]
    assert_hits(run(Fixture().table(rows), tmp, "tbl015"), "TBL-015")


# ── lists ───────────────────────────────────────────────────────────────

def test_lst_001_item_outside_list(tmp):
    assert_hits(run(Fixture().list(["one", "two"], li_outside=True), tmp, "lst001"), "LST-001")


def test_lst_002_no_lbody(tmp):
    assert_hits(run(Fixture().list(["one", "two"], no_lbody=True), tmp, "lst002"), "LST-002")


# ── figures ─────────────────────────────────────────────────────────────

def test_fig_001_no_alt(tmp):
    assert_hits(run(Fixture().figure(alt=None), tmp, "fig001"), "FIG-001")


def test_fig_002_blank_alt(tmp):
    assert_hits(run(Fixture().figure(alt="   "), tmp, "fig002"), "FIG-002")


def test_fig_010_placeholder(tmp):
    for i, alt in enumerate(["Image", "picture 3", "DSC_0042.jpg", "12345", "\\frac{a}{b}"]):
        assert_hits(run(Fixture().figure(alt=alt), tmp, f"fig010_{i}"), "FIG-010")


def test_fig_011_alt_equals_caption(tmp):
    assert_hits(run(Fixture().figure(alt="Figure 1. The treatment works", caption="Figure 1. The treatment works"), tmp, "fig011"), "FIG-011")


def test_fig_012_not_language(tmp):
    assert_hits(run(Fixture().figure(alt="@@@@ #### $$$$ %%%% &&&&"), tmp, "fig012"), "FIG-012")


# ── links, annotations, forms ───────────────────────────────────────────

def test_lnk_001_annotation_outside_link_element(tmp):
    assert_hits(run(Fixture().link("Read more", in_link_element=False), tmp, "lnk001"), "LNK-001")


def test_lnk_002_no_contents(tmp):
    assert_hits(run(Fixture().link("Read more", contents=None), tmp, "lnk002"), "LNK-002")


def test_lnk_003_unnamed_link(tmp):
    assert_hits(run(Fixture().link("", contents="x"), tmp, "lnk003"), "LNK-003")


def test_lnk_004_no_print_flag(tmp):
    assert_hits(run(Fixture().link("Read more", flags=0), tmp, "lnk004"), "LNK-004")


def test_lnk_005_tabs_structure(tmp):
    assert_hits(run(Fixture(no_tabs=True).link("Read more"), tmp, "lnk005"), "LNK-005")
    assert "LNK-005" not in rules_hit(run(Fixture().link("Read more"), tmp, "lnk005b"))


def test_lnk_010_unlinked_uri(tmp):
    assert_hits(run(Fixture().p("Write to hello@example.org or visit https://example.org/help for more."), tmp, "lnk010"), "LNK-010")


# ── notes and math ──────────────────────────────────────────────────────

def test_note_001_no_id(tmp):
    assert_hits(run(Fixture().add(Block("Note", "A footnote.", attrs={"no_id": True})), tmp, "note001"), "NOTE-001")


def test_note_002_dangling_reference(tmp):
    assert_hits(run(Fixture().p("See the note").reference("7"), tmp, "note002"), "NOTE-002")


def test_math_001_no_alt(tmp):
    assert_hits(run(Fixture().formula("a2 + b2 = c2", alt=None), tmp, "math001"), "MATH-001")


def test_math_010_alt_is_latex(tmp):
    assert_hits(run(Fixture().formula("a2 + b2 = c2", alt="\\frac{a^2}{b^2}"), tmp, "math010"), "MATH-010")


def test_math_011_formula_hides_prose(tmp):
    text = "The committee agreed that the water samples taken during the spring months met every standard set by the council."
    assert_hits(run(Fixture().formula(text, alt="a"), tmp, "math011"), "MATH-011")


# ── pagination and order ────────────────────────────────────────────────

def test_pag_001_tagged_running_footer(tmp):
    fx = Fixture()
    for i in range(4):
        fx.page().p(f"Body text of page {i + 1}, different on every page.")
        fx.p("Town council water report, for internal circulation only", y_band="bottom")
    assert_hits(run(fx, tmp, "pag001"), "PAG-001")


def test_ord_001_paint_order(tmp):
    fx = Fixture()
    fx.h(1, "Reading order")
    for i in range(6):
        fx.p(f"Paragraph number {i + 1} of the page, in logical order.")
    path = str(tmp / "ord001.pdf")
    fx.build(path)
    # Reverse the marked-content sequences in the page stream so paint order disagrees with the tree.
    import pikepdf
    import re

    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        page = pdf.pages[0]
        data = page.Contents.read_bytes().decode("latin-1")
        seqs = re.findall(r"/\w+ <</MCID \d+>> BDC.*?EMC", data, re.S)
        page.Contents = pikepdf.Stream(pdf, "\n".join(reversed(seqs)).encode("latin-1"))
        pdf.save(path)
    assert_hits(check(path), "ORD-001")


# ── rules added from veraPDF's profile ───────────────────────────────────

def test_tag_004_nested_artifact(tmp):
    raw = "/Artifact BMC /P <</MCID 99>> BDC BT /F1 11 Tf 1 0 0 1 72 300 Tm <0001> Tj ET EMC EMC"
    assert_hits(run(clean().add(Block("Raw", raw, attrs={"claim_mcid": 99})), tmp, "tag004"), "TAG-004")


def test_hdg_005_two_h_children(tmp):
    assert_hits(run(Fixture().h(0, "First").h(0, "Second"), tmp, "hdg005"), "HDG-005")


def test_note_004_duplicate_ids(tmp):
    fx = Fixture().add(Block("Note", "One.", attrs={"ID": "n1"})).add(Block("Note", "Two.", attrs={"ID": "n1"}))
    assert_hits(run(fx, tmp, "note004"), "NOTE-004")


def test_tbl_002_is_an_error_like_verapdf(tmp):
    assert_hits(run(Fixture().table([["Month", "Samples"], ["Jan", "24"]], scope=None), tmp, "tbl002e"), "TBL-002", ERROR)


# ── source comparison ───────────────────────────────────────────────────

def test_sem_rules_need_source(tmp):
    r = run(clean(), tmp, "sem_nosource")
    skipped = {x.rule: x for x in r.runs if x.status == "skipped"}
    assert {"SEM-001", "SEM-002", "SEM-003"} <= set(skipped)


def test_sem_001_structure_regression(tmp):
    src = str(tmp / "sem_src.pdf")
    clean().build(src)
    out = str(tmp / "sem_out.pdf")
    Fixture().p("Only a paragraph survived the remediation.").build(out)
    r = check(out, source=src)
    assert_hits(r, "SEM-001")
    assert_hits(r, "SEM-002")


# ── viewer ───────────────────────────────────────────────────────────────

def test_viewer_payload_and_render(tmp):
    from outloud.model import Document
    from outloud.viewer import page_transform, payload, render_page

    fx = clean().untagged("A sentence painted with no tag, so the viewer has a box to draw.")
    path = str(tmp / "viewer.pdf")
    fx.build(path)
    r = check(path)
    doc = Document(path)
    try:
        data = payload(r, doc)
        assert data["pages"] and data["tree"] and data["findings"]
        assert any(f.get("boxes") for f in data["findings"]), "no finding carries a highlight box"
        assert 1 in data["reading"] and any(item["text"] for item in data["reading"][1])
        png = render_page(doc, 1)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        m = page_transform(doc, 1)
        assert len(m) == 6 and m[0] > 0
    finally:
        doc.close()


# ── rules added after the pdfa11y review (2026-09-17) ──────────────────

def test_doc_015_info_title_disagrees(tmp):
    assert_hits(run(Fixture(title="Annual report", info_title="Draft 3").p("Text."), tmp, "doc015"), "DOC-015", WARNING)


def test_doc_015_same_title_passes(tmp):
    assert "DOC-015" not in rules_hit(run(Fixture(title="Annual report", info_title="annual report").p("Text."), tmp, "doc015b"))


def test_doc_030_config_without_name(tmp):
    assert_hits(run(Fixture(oc_config_no_name=True).p("Text."), tmp, "doc030a"), "DOC-030", ERROR)


def test_doc_030_config_with_as(tmp):
    assert_hits(run(Fixture(oc_as=True).p("Text."), tmp, "doc030b"), "DOC-030", ERROR)


def test_tbl_005_stray_child(tmp):
    r = run(Fixture().table([["Month", "Samples"], ["Jan", "24"]], attrs={"stray_child": "P"}), tmp, "tbl005")
    assert_hits(r, "TBL-005", ERROR)


def test_txt_007_no_cidtogidmap(tmp):
    assert_hits(run(Fixture(no_cidtogid=True).p("Text without a glyph map."), tmp, "txt007"), "TXT-007", ERROR)


def test_nav_001_long_document_without_bookmarks(tmp):
    fx = Fixture()
    for i in range(10):
        fx.p(f"This part of the report covers topic {'abcdefghij'[i]} in some detail.")
        fx.page()
    assert_hits(run(fx, tmp, "nav001"), "NAV-001", WARNING)


def test_nav_001_bookmarks_present(tmp):
    fx = Fixture(outlines=True)
    for i in range(10):
        fx.p(f"This part of the report covers topic {'abcdefghij'[i]} in some detail.")
        fx.page()
    assert "NAV-001" not in rules_hit(run(fx, tmp, "nav001b"))


# ── applicability and criteria ──────────────────────────────────────────

def test_rules_are_not_applicable_without_their_feature(tmp):
    r = run(Fixture().p("Only a paragraph."), tmp, "onlyp")
    status = {x.rule: x for x in r.runs}
    assert status["TBL-002"].status == "not-applicable" and status["TBL-002"].outcome == "not-applicable"
    assert status["FIG-001"].status == "not-applicable"
    assert status["LNK-005"].status == "not-applicable"
    assert status["DOC-020"].reason == "not encrypted"
    assert status["DOC-013"].status == "ran" and status["DOC-013"].outcome == "pass"


def test_criteria_reflect_outcomes(tmp):
    r = run(clean(), tmp, "crit_clean")
    wcag = {row["id"]: row for row in r.criteria["wcag22"]}
    ua = {row["id"]: row for row in r.criteria["pdfua1"]}
    assert len(wcag) == 55 and len(ua) == 31
    assert wcag["1.1.1"]["status"] == "pass" and wcag["1.3.1"]["status"] == "pass" and wcag["2.4.2"]["status"] == "pass"
    assert wcag["1.2.4"]["status"] == "not-applicable"          # no live media in a document
    assert wcag["3.3.2"]["status"] == "not-applicable"          # the clean fixture has no form fields
    assert wcag["1.4.3"]["status"] == "manual" and wcag["1.4.3"]["note"]
    assert ua["14"]["status"] == "pass" and ua["15"]["status"] == "pass"
    assert ua["03"]["status"] == "not-applicable"               # no media, so nothing can flicker
    assert ua["09"]["status"] == "pass" and ua["09"]["semantic_only"]   # only semantic rules test it, and they passed
    r2 = run(Fixture().figure(alt=None), tmp, "crit_fig")
    wcag2 = {row["id"]: row for row in r2.criteria["wcag22"]}
    ua2 = {row["id"]: row for row in r2.criteria["pdfua1"]}
    assert wcag2["1.1.1"]["status"] == "fail" and wcag2["1.1.1"]["errors"] >= 1
    assert ua2["13"]["status"] == "fail"
    assert ua2["15"]["status"] == "not-applicable"
    assert any(x["id"] == "FIG-001" and x["outcome"] == "fail" for x in ua2["13"]["rules"])


def test_criteria_semantic_rules_count_for_wcag_but_sit_beside_pdfua(tmp):
    r = run(Fixture().figure(alt="   "), tmp, "crit_blank_alt")
    wcag = {row["id"]: row for row in r.criteria["wcag22"]}
    ua = {row["id"]: row for row in r.criteria["pdfua1"]}
    assert wcag["1.1.1"]["status"] == "fail"                    # FIG-002 is semantic and counts for WCAG
    assert ua["13"]["status"] == "pass"                         # the conformance rule FIG-001 passed
    assert ua["13"]["semantic_status"] == "fail"                # and the row says what lies beyond the protocol


def test_json_and_sarif_carry_criteria(tmp):
    import json
    from outloud.report import to_json, to_sarif
    r = run(clean(), tmp, "crit_json")
    payload = json.loads(to_json([r]))
    assert "criteria" in payload["results"][0] and "wcag22" in payload["results"][0]["criteria"]
    assert all("outcome" in x for x in payload["results"][0]["rules"])
    sarif = json.loads(to_sarif([r]))
    assert sarif["runs"][0]["taxonomies"][0]["name"] == "WCAG 2.2"
    fig = next(x for x in sarif["runs"][0]["tool"]["driver"]["rules"] if x["id"] == "FIG-001")
    assert fig["properties"]["wcag"] == ["1.1.1"] and fig["relationships"]

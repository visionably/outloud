"""Document-level rules: is the file declared tagged, titled, identified, in a language, and open to readers."""

from __future__ import annotations

import os
import re

import pikepdf

from ..model import Document
from ..registry import finding, rule

# A primary language subtag is two or three letters (ISO 639) or "x" for
# private use; BCP 47 syntax also reserves longer ones that nothing uses, so a
# word like "english" is treated as the mistake it is.
BCP47_RE = re.compile(r"^(x|[A-Za-z]{2,3})(-[A-Za-z0-9]{1,8})*$")


@rule("DOC-001")
def marked(doc: Document):
    if doc.mark_info.get("Marked") is not True:
        yield finding("DOC-001", "/MarkInfo /Marked is " + ("absent" if "Marked" not in doc.mark_info else "false")
                      + "; readers will not consult the structure tree")


@rule("DOC-002")
def struct_tree(doc: Document):
    if doc.struct_root is None:
        yield finding("DOC-002", "the catalog has no /StructTreeRoot")


@rule("DOC-003")
def suspects(doc: Document):
    if doc.mark_info.get("Suspects") is True:
        yield finding("DOC-003", "/MarkInfo /Suspects is true")


@rule("DOC-010")
def title_present(doc: Document):
    xmp_title = (doc.xmp.get("dc:title") or "").strip()
    if xmp_title:
        return
    info = (doc.info_title or "").strip()
    if info:
        yield finding("DOC-010", "XMP metadata has no dc:title (the Info dictionary's /Title is not what PDF/UA requires)",
                      evidence=info)
    else:
        yield finding("DOC-010", "no dc:title in XMP metadata and no /Title in the Info dictionary")


@rule("DOC-011")
def display_doc_title(doc: Document):
    v = doc.display_doc_title
    if v is not True:
        yield finding("DOC-011", "/ViewerPreferences /DisplayDocTitle is " + ("absent" if v is None else "false"))


@rule("DOC-012")
def ua_identifier(doc: Document):
    part = doc.xmp.get("pdfuaid:part")
    if not part:
        yield finding("DOC-012", "XMP metadata does not declare pdfuaid:part")
    elif part.strip() != "1":
        yield finding("DOC-012", f"pdfuaid:part is {part!r}; this checker tests PDF/UA-1", severity="info")


@rule("DOC-013")
def language_present(doc: Document):
    if not (doc.lang or "").strip():
        yield finding("DOC-013", "the catalog has no /Lang")


@rule("DOC-014")
def language_wellformed(doc: Document):
    lang = (doc.lang or "").strip()
    if lang and not BCP47_RE.match(lang):
        yield finding("DOC-014", f"/Lang {lang!r} is not a well-formed BCP 47 language tag", evidence=lang)


@rule("DOC-015")
def titles_agree(doc: Document):
    xmp_title = " ".join((doc.xmp.get("dc:title") or "").split())
    info = " ".join((doc.info_title or "").split())
    if xmp_title and info and xmp_title.casefold() != info.casefold():
        yield finding("DOC-015", "the Info dictionary's /Title and XMP dc:title differ", evidence=f"Info: {info[:60]!r}; XMP: {xmp_title[:60]!r}")


@rule("DOC-030")
def optional_content(doc: Document):
    """ISO 14289-1 7.10: every optional content configuration dictionary (the default /D and each entry of /Configs)
    carries a /Name, and none carries /AS. (Names on the groups themselves are ISO 32000 housekeeping, not a UA-1 test.)"""
    ocp = doc.root.get("/OCProperties")
    if not isinstance(ocp, pikepdf.Dictionary):
        return
    configs = []
    d = ocp.get("/D")
    if isinstance(d, pikepdf.Dictionary):
        configs.append(("the default configuration", d))
    alts = ocp.get("/Configs")
    if isinstance(alts, pikepdf.Array):
        for i, c in enumerate(alts):
            if isinstance(c, pikepdf.Dictionary):
                configs.append((f"alternate configuration {i + 1}", c))
    unnamed = [name for name, c in configs if not str(c.get("/Name") or "").strip()]
    if unnamed:
        yield finding("DOC-030", f"optional content configuration(s) without a /Name: {', '.join(unnamed)}", count=len(unnamed))
    with_as = [name for name, c in configs if c.get("/AS") is not None]
    if with_as:
        yield finding("DOC-030", f"optional content configuration(s) carry /AS (usage application dictionaries): {', '.join(with_as)}",
                      count=len(with_as))


@rule("DOC-020")
def permissions(doc: Document):
    if not doc.pdf.is_encrypted:
        return
    allow = doc.permissions
    if allow is None:
        return
    # Read bit 10 of /P ourselves: qpdf reports the accessibility permission as
    # always granted (PDF 2.0 deprecated the bit), but a reader that honours it
    # would still lock a screen reader out of a file whose producer cleared it.
    accessibility = getattr(allow, "accessibility", True)
    try:
        accessibility = accessibility and bool(int(doc.pdf.encryption.P) & 512)
    except Exception:  # noqa: BLE001
        pass
    if not accessibility:
        yield finding("DOC-020", "the document is encrypted and its permissions deny extraction for accessibility")
    elif not getattr(allow, "extract", True):
        yield finding("DOC-020", "the document is encrypted and denies general text extraction; accessibility extraction is allowed",
                      severity="info")


@rule("DOC-021")
def xfa(doc: Document):
    af = doc.root.get("/AcroForm")
    if isinstance(af, pikepdf.Dictionary) and af.get("/XFA") is not None:
        yield finding("DOC-021", "the interactive form dictionary carries /XFA")


@rule("DOC-031")
def embedded_files(doc: Document):
    names = doc.root.get("/Names")
    if not isinstance(names, pikepdf.Dictionary):
        return
    ef = names.get("/EmbeddedFiles")
    if not isinstance(ef, pikepdf.Dictionary):
        return
    specs = []

    def walk(node, depth=0):
        if not isinstance(node, pikepdf.Dictionary) or depth > 10:
            return
        arr = node.get("/Names")
        if isinstance(arr, pikepdf.Array):
            for i in range(1, len(arr), 2):
                if isinstance(arr[i], pikepdf.Dictionary):
                    specs.append(arr[i])
        kids = node.get("/Kids")
        if isinstance(kids, pikepdf.Array):
            for k in kids:
                walk(k, depth + 1)

    walk(ef)
    bad = []
    for s in specs:
        has_f = s.get("/F") is not None
        has_uf = s.get("/UF") is not None
        has_desc = bool(str(s.get("/Desc") or "").strip())
        if not (has_f and has_uf) or not has_desc:
            bad.append(str(s.get("/UF") or s.get("/F") or "?"))
    if bad:
        yield finding("DOC-031", f"{len(bad)} embedded file(s) lack /F and /UF names or a /Desc description",
                      count=len(bad), evidence="; ".join(bad[:3]))


_FRAGMENT_END = re.compile(r"[,;:\-–]$")
_DATE_RE = re.compile(r"^\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*$|^\s*\d{4}-\d{2}-\d{2}\s*$")


@rule("DOC-040")
def title_quality(doc: Document):
    title = (doc.title or "").strip()
    if not title:
        return
    base = os.path.basename(doc.path)
    stem = os.path.splitext(base)[0]
    low = title.lower()
    reason = None
    if re.search(r"\.(pdf|docx?|pptx?|xlsx?|indd|ai|psd)$", low):
        reason = "it is a file name"
    elif " " not in title.strip() and (low == stem.lower() or "_" in title):
        reason = "it is the file name"
    elif low.startswith("microsoft word - ") or low.startswith("microsoft powerpoint - "):
        reason = "it is the application's default window title"
    elif low in ("untitled", "untitled document", "document", "document1", "new document", "title"):
        reason = "it is a placeholder"
    elif _DATE_RE.match(title):
        reason = "it is a date"
    elif title[:1].islower() and _FRAGMENT_END.search(title):
        reason = "it reads as a mid-sentence fragment"
    elif len(title) > 200:
        reason = "it is longer than a title (over 200 characters)"
    if reason:
        yield finding("DOC-040", f"the document title is unhelpful: {reason}", evidence=title[:120])

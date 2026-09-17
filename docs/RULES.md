# outloud rules

Every rule outloud can run, generated from `src/outloud/rules/catalogue.yaml` by `scripts/gen_rules_doc.py`.

**Layers.** *Conformance* rules test a requirement of ISO 14289-1 (PDF/UA-1), the same requirements the Matterhorn Protocol lists and that veraPDF and PAC test; the clause and checkpoint are given. *Semantic* rules test what a conformant file can still get wrong: whether the tags match the page and whether the words a reader is given are the words a person would use. No validator tests these; each names its evidence so a person can judge.

**Severity.** *error*: a screen-reader user loses content or cannot proceed. *warning*: content is reachable but degraded or misleading. *info*: worth a look, not counted in the verdict.

**Criteria.** Every rule names the Matterhorn Protocol 1.1 checkpoint and the WCAG 2.2 success criteria it tests; `outloud file.pdf --criteria` rolls the results up per checkpoint and per criterion. *Requires* names the document feature the rule is about: a file without it gets *not applicable* for the rule, not *pass*.

90 rules in the catalogue, 88 implemented, 2 planned.

## Document

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **DOC-001** Document is not marked as tagged | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1 | — | implemented | The catalog's /MarkInfo dictionary must carry /Marked true; without it a reader does not consult the structure tree at all. | Set /MarkInfo << /Marked true >> in the document catalog when the file is tagged. |
| **DOC-002** No structure tree | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1, 1.3.2 | — | implemented | The catalog has no /StructTreeRoot, so the document has no logical structure for assistive technology to read. | Tag the document (export with tags from the authoring tool, or add tags in a remediation tool) so the catalog has a /StructTreeRoot. |
| **DOC-003** Structure tree is marked suspect | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1 | — | implemented | /MarkInfo /Suspects is true, declaring that the tags may not reflect the content; a conforming file must not say this. | Review the tags, then set /Suspects false or remove it. |
| **DOC-010** Document has no title | conformance | error | ISO 14289-1 7.1, Matterhorn 06 | 2.4.2 | — | implemented | The XMP metadata carries no dc:title (and the Info dictionary no /Title), so a screen reader announces the file name. | Give the document a title in its properties; the tool writes it to XMP dc:title. |
| **DOC-011** Title is not displayed | conformance | error | ISO 14289-1 7.1, Matterhorn 07 | 2.4.2 | — | implemented | /ViewerPreferences /DisplayDocTitle is absent or false, so viewers show the file name in the window title instead of the document title. | Set /ViewerPreferences << /DisplayDocTitle true >> (in Acrobat, Initial View, Show Document Title). |
| **DOC-012** No PDF/UA identification in metadata | conformance | error | ISO 14289-1 7.1, Matterhorn 06 | — | — | implemented | The XMP metadata does not declare pdfuaid:part, so the file does not claim conformance and validators do not test it as PDF/UA. | Add pdfuaid:part = 1 to the XMP metadata once the file conforms; do not claim it before. |
| **DOC-013** Document has no default language | conformance | error | ISO 14289-1 7.2, Matterhorn 11 | 3.1.1 | — | implemented | The catalog carries no /Lang, so a screen reader must guess the language of every word it reads. | Set the document language in the file's properties so the catalog carries /Lang (for example "en-IN"). |
| **DOC-014** Language tag is not well-formed | conformance | warning | ISO 14289-1 7.2, Matterhorn 11 | 3.1.1 | lang | implemented | /Lang is present but is not a usable BCP 47 tag (for example "english" or "en_US"), so readers ignore it. veraPDF accepts any syntactically valid tag, including unregistered words; this rule asks for a two- or three-letter primary subtag. | Use a BCP 47 tag such as "en", "en-GB" or "hi-IN", with a hyphen, not a language name. |
| **DOC-015** Info title disagrees with the XMP title | conformance | warning | ISO 14289-1 7.1, Matterhorn 06 | 2.4.2 | title | implemented | The Info dictionary's /Title and XMP dc:title say different things, so viewers and readers that prefer one over the other announce different titles for the same file. | Set the title once in the document properties and let the tool write both, or remove the stale /Title from the Info dictionary. |
| **DOC-020** Assistive technology is locked out by permissions | conformance | error | ISO 14289-1 7.1, Matterhorn 26 | 1.3.1 | encrypted | implemented | The document is encrypted and its permissions deny content extraction for accessibility, so a screen reader may not read it at all. | In the security settings, allow content extraction for accessibility (permission bit 10) or remove the encryption. |
| **DOC-030** Optional content configuration hides content from readers | conformance | error | ISO 14289-1 7.10, Matterhorn 20 | 1.3.1 | oc | implemented | An optional content configuration dictionary (the default /D or an alternate in /Configs) has no /Name, or carries an /AS entry that switches layers by viewer state, so content can appear to a sighted reader that assistive technology cannot account for. | Give every optional content configuration a /Name and remove its /AS entry; flatten layers that are not needed. |
| **DOC-021** Document contains an XFA form | conformance | error | ISO 14289-1 7.15, Matterhorn 25 | 4.1.2 | acroform | implemented | The interactive form dictionary carries /XFA; PDF/UA-1 forbids dynamic XFA forms, which assistive technology cannot read. | Rebuild the form as an AcroForm (no XFA) with tagged fields. |
| **DOC-031** Embedded file has no description | conformance | warning | ISO 14289-1 7.11, Matterhorn 21 | — | embedded | implemented | An embedded file specification lacks /F and /UF names or a /Desc, so a reader cannot tell what the attachment is. | Give each attachment a file name (/F and /UF) and a one-line description (/Desc). |
| **DOC-040** Title is the file name or a fragment | semantic | warning | —, Matterhorn 06 | 2.4.2 | title | implemented | dc:title is the raw file name, a mid-sentence fragment, a letterhead line or a date stamp, which is what DisplayDocTitle makes a screen reader announce. | Set a title that names the document the way a person would ("Annual report 2025", not "report_final_v2.pdf"). |

## Tagging

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **TAG-001** Content is neither tagged nor an artifact | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1, 1.3.2 | — | implemented | Text or graphics are painted outside any marked-content sequence, so a reader cannot know whether they are content or decoration; they are silently skipped. | Tag the content with a structure element, or mark it /Artifact if it is decoration or page furniture. |
| **TAG-002** Real content is marked as an artifact | semantic | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1 | — | implemented | Sentences of prose are inside /Artifact sequences, which tells every reader to skip them; artifacting is for pagination and decoration, not content. | Move the text out of the artifact into a structure element (P, H, LI) so it is read. |
| **TAG-003** Words the page prints that no element announces | semantic | warning | —, Matterhorn 01 | 1.3.1 | struct | implemented | Text visible on the page appears in no structure element's content, alternative text or actual text; whatever the reason, the reader never hears it. | Find the text on the page and make sure a structure element contains it or its alternative. |
| **TAG-004** Tagged content and artifacts are nested in each other | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1 | struct | implemented | A marked-content sequence that a structure element claims opens inside an /Artifact, or an /Artifact opens inside such a sequence, so the same glyphs are both content and decoration. veraPDF 1.26 has rules for this (7.1-1, 7.1-2) but did not flag the fixture's construction, so it is listed as not comparable. | Close the artifact before the tagged content starts, or the tagged content before the artifact; never nest one in the other. |
| **TAG-010** Non-standard structure type is not role-mapped | conformance | error | ISO 14289-1 7.1, Matterhorn 02 | 1.3.1, 4.1.2 | struct | implemented | A structure element uses a type that is not a standard PDF structure type and is not mapped to one in /RoleMap, so readers do not know what it is. | Add a /RoleMap entry mapping the custom type to the nearest standard type (P, Span, Div, H1, ...). |
| **TAG-011** Role map is circular | conformance | error | ISO 14289-1 7.1, Matterhorn 02 | 1.3.1, 4.1.2 | struct | implemented | /RoleMap maps a type to itself, directly or through other types, so resolution never reaches a standard type. | Make every /RoleMap chain end at a standard structure type. |
| **TAG-012** Standard structure type is remapped | conformance | error | ISO 14289-1 7.1, Matterhorn 02 | 1.3.1, 4.1.2 | struct | implemented | /RoleMap maps a standard structure type to a different type, which changes what every element of that type means. | Remove /RoleMap entries whose key is a standard type; only custom types may be mapped. |
| **TAG-020** Empty structure element | semantic | warning | —, Matterhorn 09 | 1.3.1 | struct | implemented | A structure element has no content, no children, no alternative text and no actual text; a reader announces its role and then nothing. | Delete the empty element, or give it the content it was meant to hold. |
| **TAG-021** Element points at a page that does not exist | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1 | struct | implemented | A structure element's /Pg or a marked-content reference points at a page object not in the page tree, so its content can never be found. | Repoint /Pg (or the /MCR's /Pg) at the page that holds the content, or remove the element if the page is gone. |
| **TAG-022** Marked content is referenced by more than one element | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1, 1.3.2 | struct | implemented | The same marked-content id on one page is claimed by two structure elements, so it is read twice or its meaning is ambiguous. | Leave each marked-content id in exactly one element's /K; give the second element its own content. |
| **TAG-023** Structure element has no parent entry | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1 | struct | implemented | A structure element dictionary lacks /P, which ISO 32000-1 requires; readers that walk upward from content cannot place it. | Set /P on every structure element to the element (or the structure tree root) that lists it in /K. |
| **TAG-040** Reference XObject | conformance | error | ISO 14289-1 7.20, Matterhorn 30 | 1.3.1 | xobjects | implemented | A form XObject carries /Ref, importing content from another file at view time; PDF/UA-1 forbids this because the imported content has no structure here. | Embed the referenced content in this file as an ordinary, tagged form XObject. |
| **TAG-030** Page-sized figure over a text layer | semantic | warning | —, Matterhorn 13 | 1.1.1, 1.3.1 | figures | implemented | A /Figure whose bounding box covers nearly the whole page sits on a page that carries tagged text; the page scan is being described as a picture before its content is read. | Mark the full-page scan image as an artifact and let the recognised text carry the content. |
| **TAG-031** Alternative text hides real content | semantic | error | — | 1.1.1 | struct | implemented | A structure element carries /Alt or /ActualText much shorter than the text it replaces, so a sentence of content is reduced to a phrase. | Remove the /Alt or /ActualText from text content, or make it say everything the text says. |
| **TAG-032** Actual text does not account for the glyphs it replaces | semantic | error | — | 1.1.1 | struct | implemented | /ActualText is set on an element whose visible words are not present in it, so those words are lost to every reader that honours the replacement. | Set /ActualText only where it repeats the visible text exactly (hyphenation, ligatures, drop caps); otherwise remove it. |

## Text and fonts

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **TXT-001** Font is not embedded | conformance | error | ISO 14289-1 7.21.3.1, Matterhorn 31 | — | fonts | implemented | A font used on the page is not embedded, so glyph shapes and, often, character mappings depend on the reader's machine. | Re-export with all fonts embedded (subset embedding is fine). |
| **TXT-002** Characters cannot be mapped to Unicode | conformance | error | ISO 14289-1 7.21.7, Matterhorn 10 | 1.3.1 | fonts | implemented | A font has no /ToUnicode CMap and no standard encoding from which text can be derived, so its glyphs are read as nothing or as replacement characters. | Add a /ToUnicode CMap to the font, or re-export from the authoring tool, which writes one. |
| **TXT-003** Glyphs map to no character | conformance | error | ISO 14289-1 7.21.7, Matterhorn 10 | 1.3.1 | fonts | implemented | Codes shown on the page are absent from the font's /ToUnicode CMap, so those glyphs are silent or wrong when read or copied. | Extend the /ToUnicode CMap to cover every code the page shows; the evidence lists the first codes. |
| **TXT-004** Unicode mapping is legal but wrong | semantic | warning | —, Matterhorn 10 | 1.3.1 | fonts | implemented | The /ToUnicode CMap maps many glyphs to the same character, to control characters, or to the private-use area, so the extracted text is not the text on the page. | Rebuild the /ToUnicode CMap from the font's own glyph names or cmap so each glyph maps to the character it draws. |
| **TXT-005** Text shows the .notdef glyph | conformance | error | ISO 14289-1 7.21.8, Matterhorn 31 | 1.3.1 | fonts | implemented | A text-showing operator references glyph 0 of a composite font, the .notdef box, so a character the author typed has no glyph and no meaning. | Find the character the font lacks and embed a font that has it, or correct the text. |
| **TXT-006** Unicode mapping to a non-character | conformance | error | ISO 14289-1 7.21.7, Matterhorn 10 | 1.3.1 | fonts | implemented | A /ToUnicode entry maps a code to U+0000, U+FEFF or U+FFFE, which are not characters; the glyph is read as nothing. | Map the code to the character it draws; a space, if the glyph is blank. |
| **TXT-007** CID font lacks a glyph map | conformance | error | ISO 14289-1 7.21.3.2, Matterhorn 31 | — | fonts | implemented | An embedded CIDFontType2 has no /CIDToGIDMap, so the mapping from character ids to glyphs in the TrueType program is undefined and text extraction can go wrong. | Set /CIDToGIDMap /Identity (or an explicit stream) on the CIDFontType2 dictionary. |
| **TXT-010** Invisible text with no raster to carry it | semantic | error | — | — | text | implemented | A page's text is almost entirely in render mode 3 (invisible) but no image of sufficient resolution underlies it; the page looks blank to a sighted reader. | Render the text visibly, or restore the page image the invisible text was meant to sit on. |
| **TXT-011** Text in a Form XObject is not tagged | conformance | error | ISO 14289-1 7.1, Matterhorn 01 | 1.3.1, 1.3.2 | xobjects | implemented | A form XObject drawn on the page contains text-showing operators with no marked content of its own and no marked content around the Do that draws it. | Wrap the Do operator in a marked-content sequence owned by a structure element, or tag the text inside the form. |

## Headings

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **HDG-001** Heading level is skipped | conformance | error | ISO 14289-1 7.4, Matterhorn 14 | 1.3.1, 2.4.6 | headings | implemented | A heading of level n is followed by a heading of level n+2 or deeper with no n+1 between, so the outline a reader navigates has a hole in it. | Use the next level down (H2 after H1), or promote the deeper heading. |
| **HDG-002** First heading is not H1 | conformance | error | ISO 14289-1 7.4, Matterhorn 14 | 1.3.1, 2.4.6 | headings | implemented | The first heading in the document is deeper than H1, so the outline starts below its top. | Tag the document's main title as H1. |
| **HDG-003** Numbered and unnumbered headings are mixed | conformance | error | ISO 14289-1 7.4, Matterhorn 14 | 1.3.1, 2.4.6 | headings | implemented | The document uses both /H and /H1 to /H6, which PDF/UA-1 forbids; a reader cannot build one outline from both. | Use H1 to H6 throughout; replace each /H with its numbered level. |
| **HDG-004** Heading deeper than H6 without the level attribute | conformance | error | ISO 14289-1 7.4, Matterhorn 14 | 1.3.1, 2.4.6 | headings | planned | A heading beyond H6 is used without being a role-mapped type carrying its level, so the reader cannot place it in the outline. | Role-map H7 and deeper to H and flatten the outline where possible. |
| **HDG-005** More than one unnumbered heading under one parent | conformance | error | ISO 14289-1 7.4.4, Matterhorn 14 | 1.3.1, 2.4.6 | headings | implemented | A structure element has two or more /H children; the unnumbered heading form allows one heading per node, so the outline is ambiguous. | Give each section (Sect, Art, Div) one /H, or switch to numbered headings. |
| **HDG-010** Heading text cannot be a heading | semantic | warning | —, Matterhorn 14 | 2.4.6 | headings | implemented | A heading's text is a mid-sentence fragment, a salutation, a closing, a classification stamp or a reference number; as an outline entry it misleads. | Retag the text as a paragraph and tag the real heading of the section instead. |
| **HDG-011** Heading is a paragraph | semantic | warning | —, Matterhorn 14 | 2.4.6 | headings | implemented | A heading runs to several sentences, so a reader navigating by headings hears a paragraph. | Keep only the heading line in the H element and tag the sentences that follow as P. |
| **HDG-012** No headings in a long document | semantic | warning | —, Matterhorn 14 | 1.3.1 | struct | implemented | A document of many pages has no heading at all, so a reader has no way to move through it except line by line. | Tag the section titles as H1 to H6 so readers can navigate by heading. |

## Tables

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **TBL-001** Table has no header cells | conformance | error | ISO 14289-1 7.5, Matterhorn 15 | 1.3.1 | tables | implemented | A /Table contains /TD cells but no /TH, so a reader hears values without knowing what column or row they belong to. | Tag the header row (or column) cells as TH with /Scope, or retag the grid as text if it is not a table. |
| **TBL-002** Header cell has no scope and no headers association | conformance | error | ISO 14289-1 7.5, Matterhorn 15 | 1.3.1 | tables | implemented | A /TH carries no /Scope attribute and no cell references it through /Headers, so a reader cannot tell which cells it heads. | Set /Scope /Column or /Row on each TH, or give cells /Headers arrays that name their TH ids. |
| **TBL-003** Cell is outside a row | conformance | error | ISO 14289-1 7.5, Matterhorn 15 | 1.3.1 | tables | implemented | A /TH or /TD is not the child of a /TR, so the table grid cannot be reconstructed. | Nest every TH and TD in a TR, and every TR in the Table (or THead, TBody, TFoot). |
| **TBL-004** Table is irregular | conformance | error | ISO 14289-1 7.5, Matterhorn 15 | 1.3.1 | tables | implemented | Rows have different cell counts once spans are applied, so the grid does not close and cells drift under the wrong headers. | Add the missing cells (empty TD is fine) or set /ColSpan and /RowSpan so every row fills the same number of columns. |
| **TBL-005** Table structure is mis-nested | conformance | error | ISO 14289-1 7.5, Matterhorn 15 | 1.3.1 | tables | implemented | A /Table has a child that is not a row, a row group or a caption, more than one THead or TFoot, a row group with no TBody, or a Caption that is not first or last, so the table model readers rely on does not hold. | Keep only TR, THead, TBody, TFoot and one Caption (first or last) directly under Table, with at most one THead and one TFoot. |
| **TBL-010** Header cells are shredded | semantic | error | —, Matterhorn 15 | 1.3.1 | tables | implemented | Wrapped column headings are tagged as several rows of one-word /TH cells; the header of one column is read as four rows of noise. | Merge the wrapped lines of each heading into one TH per column. |
| **TBL-011** Data cells are headed only by silence | semantic | warning | —, Matterhorn 15 | 1.3.1 | tables | implemented | Data cells are associated only with empty header cells, so /Headers is present but the announced header is nothing. | Put the heading text in the TH cells, or point /Headers at the cells that carry it. |
| **TBL-012** Table is mostly empty cells | semantic | warning | —, Matterhorn 15 | 1.3.1 | tables | implemented | More than six in ten cells of a table are empty, which usually means a grid asserted over content that is not tabular. | If the content is not a data table, retag it as paragraphs or a list; if it is, check the cell grid. |
| **TBL-013** One table split into several | semantic | warning | —, Matterhorn 15 | 1.3.1 | tables | implemented | Two /Table elements sit back to back on one page with no text between them and column counts that sum to one grid; a single table was split. | Merge the fragments into one Table so the header row applies to every row. |
| **TBL-014** A drawn grid that no table announces | semantic | warning | —, Matterhorn 15 | 1.3.1 | — | implemented | Ruled lines on the page form a grid of cells with text inside, but no /Table covers it; the reader gets the cells as loose paragraphs. | Tag the grid as a Table with TR, TH and TD cells. |
| **TBL-015** Row content collapsed into one cell | semantic | warning | —, Matterhorn 15 | 1.3.1 | tables | implemented | A row's entire content sits in a single cell while other rows have several, which usually means columns were merged in tagging. | Split the row into its cells, one per column, unless it is a genuine spanning row (then set /ColSpan). |

## Lists

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **LST-001** List item outside a list | conformance | error | ISO 14289-1 7.6, Matterhorn 16 | 1.3.1 | lists | implemented | An /LI is not the child of an /L, so the reader does not know it is one of a series. | Wrap the LI elements in an L element. |
| **LST-002** List item without a body | conformance | warning | ISO 14289-1 7.6, Matterhorn 16 | 1.3.1 | lists | implemented | An /LI has no /LBody; its content sits directly in the item, which most readers still voice but which breaks the label-and-body model the standard expects. | Put the item's content in an LBody child (and its bullet or number in Lbl). |
| **LST-003** List contains a non-item child | conformance | error | ISO 14289-1 7.6, Matterhorn 16 | 1.3.1 | lists | implemented | An /L has a child that is not an /LI (or a nested /L or a caption), so the list's sequence is broken. | Move the stray element out of the list, or wrap it in an LI. |
| **LST-004** Sub-list placed beside its parent item | conformance | warning | ISO 14289-1 7.6, Matterhorn 16 | 1.3.1 | lists | implemented | A nested list is a sibling of the item it belongs to rather than inside its body, so the nesting is lost. | Move the nested L inside the LBody of the item it belongs to. |

## Figures

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **FIG-001** Figure has no alternative text | conformance | error | ISO 14289-1 7.3, Matterhorn 13 | 1.1.1 | figures | implemented | A /Figure carries neither /Alt nor /ActualText, so a reader hears "figure" and nothing else. | Add /Alt describing what the image shows and why it is there; mark purely decorative images as artifacts instead. |
| **FIG-002** Alternative text is empty or whitespace | semantic | error | ISO 14289-1 7.3, Matterhorn 13 | 1.1.1 | figures | implemented | /Alt is present but contains no words; validators test only that the key exists. | Write the description into /Alt, or artifact the image if it is decorative. |
| **FIG-010** Alternative text is a placeholder | semantic | warning | —, Matterhorn 13 | 1.1.1 | figures | implemented | /Alt is the image's file name, "Image", "Picture 1", a bare number, source code or LaTeX; a person would not recognise it as a description. | Replace the placeholder with a description a person would give over the phone. |
| **FIG-011** Alternative text repeats the caption | semantic | info | —, Matterhorn 13 | 1.1.1 | figures | implemented | /Alt is the same as the figure's /Caption text, so the reader hears the caption twice and never a description. | Describe the image in /Alt; the caption already says what it is called. |
| **FIG-012** Alternative text is not language | semantic | warning | —, Matterhorn 13 | 1.1.1 | figures | implemented | /Alt is mostly symbols, digits or a single word repeated; it does not read as a sentence in any language. | Rewrite /Alt as plain words. |

## Links, annotations and forms

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **LNK-001** Link annotation is not in a Link element | conformance | error | ISO 14289-1 7.18.5, Matterhorn 28 | 1.3.1, 2.4.4 | links | implemented | A /Link annotation is not the child of a /Link structure element (through /OBJR), so a reader cannot associate the link with its text. | Create a Link structure element around the link text and add an OBJR to the annotation in its /K. |
| **LNK-002** Annotation has no description | conformance | error | ISO 14289-1 7.18.1, Matterhorn 28 | 1.1.1, 2.4.4 | annots | implemented | An annotation that is not hidden carries no /Contents (and, for a link, no alternative), so a reader cannot say what it does. | Set /Contents on the annotation to what it is or where it goes ("Annual report 2025 (PDF)"). |
| **LNK-003** Link element has no text and no alternative | semantic | error | —, Matterhorn 28 | 2.4.4, 4.1.2 | links | implemented | A /Link structure element contains no marked content and no /Alt, so the link is announced without any name. | Put the link's visible text inside the Link element, or give it /Alt. |
| **LNK-004** Annotation is hidden from readers | conformance | warning | ISO 14289-1 7.18.1, Matterhorn 28 | — | annots | implemented | An annotation's /F flags mark it Hidden or NoView while it is visible, or it lacks the Print flag, so readers and print differ from the screen. | Set the Print flag (bit 3) and clear Hidden and NoView on annotations that readers should get. |
| **LNK-006** Annotation is not inside an Annot element | conformance | error | ISO 14289-1 7.18.1, Matterhorn 28 | 1.3.1, 1.3.2 | annots | implemented | An annotation other than a link, widget or printer's mark is not the child of an /Annot structure element through /OBJR, so readers cannot place it in the reading order. | Add an Annot structure element at the right place in the reading order with an OBJR to the annotation. |
| **LNK-005** Page with annotations has no structure tab order | conformance | error | ISO 14289-1 7.18.3, Matterhorn 28 | 2.4.3 | annots | implemented | A page that carries annotations lacks /Tabs /S, so keyboard users tab through links and fields in an order unrelated to the reading order. | Set /Tabs /S on every page that has annotations. |
| **LNK-010** Address or URL is text but not a link | semantic | warning | — | — | text | implemented | An e-mail address or URL is printed on the page with no /Link annotation over it, so keyboard and screen-reader users cannot follow it. | Add a Link annotation over the address, inside a Link structure element with /Contents. |

## Forms

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **FRM-001** Form field has no name for readers | conformance | error | ISO 14289-1 7.18.1, Matterhorn 28 | 1.3.1, 3.3.2, 4.1.2 | forms | implemented | A widget annotation's field has no /TU (alternate field name), so the reader hears the internal field id or nothing. | Set /TU on the field to its visible label ("Date of birth"), which is what the reader announces. |
| **FRM-003** Form field is not inside a Form element | conformance | error | ISO 14289-1 7.18.4, Matterhorn 28 | 1.3.1, 1.3.2, 4.1.2 | forms | implemented | A widget annotation is not the child of a /Form structure element through /OBJR, so readers cannot reach the field from the reading order. | Add a Form structure element at the field's place in the reading order with an OBJR to the widget. |
| **FRM-002** Field name is the internal id | semantic | warning | —, Matterhorn 28 | 3.3.2, 4.1.2 | forms | implemented | /TU is "Text1", "Signature2" or another generated id; a reader hears the id instead of what the field is for. | Set /TU to the label a person sees next to the field. |

## Notes and references

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **NOTE-001** Note has no id | conformance | error | ISO 14289-1 7.9, Matterhorn 19 | 1.3.1 | notes | implemented | A /Note structure element carries no /ID, so references cannot target it. | Give every Note element a unique /ID. |
| **NOTE-004** Note ids are not unique | conformance | error | ISO 14289-1 7.9, Matterhorn 19 | 1.3.1 | notes | implemented | Two /Note elements share the same /ID, so a reference to that id is ambiguous. | Make each Note's /ID unique in the document. |
| **NOTE-002** Reference points nowhere | semantic | warning | —, Matterhorn 19 | 1.3.1 | notes | implemented | A /Reference element has no link or note it resolves to. | Link the Reference to its Note (a Link annotation or a matching id), or retag it as a Span. |
| **NOTE-003** Note is mis-shaped | semantic | warning | —, Matterhorn 19 | 1.3.1 | notes | implemented | A footnote is fragmented into several notes, merged with its neighbour, has no label, or is tagged twice; the reader hears it wrong or twice. | One Note per footnote, with its number in a Lbl child and its text after. |

## Mathematics

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **MATH-001** Formula has no alternative | conformance | error | ISO 14289-1 7.7, Matterhorn 17 | 1.1.1 | formulas | implemented | A /Formula element has no /Alt (and no MathML associated file), so a reader hears nothing for the equation. | Add /Alt that reads the equation aloud ("x equals minus b over 2a"), or attach MathML as an associated file. |
| **MATH-010** Formula alternative is source, not speech | semantic | warning | —, Matterhorn 17 | 1.1.1 | formulas | implemented | /Alt on a /Formula is LaTeX or MathML source ("\frac{QK^T}{...}"), which a reader voices as "backslash frac open brace". | Write /Alt as the spoken form of the equation; keep the source in MathML if you need it. |
| **MATH-011** Formula hides prose | semantic | error | —, Matterhorn 17 | 1.1.1, 1.3.1 | formulas | implemented | A /Formula covers far more text than its alternative accounts for, so a sentence of prose became "an equation". | Shrink the Formula element to the equation itself and tag the surrounding prose as P. |

## Reading order

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **ORD-001** Page paints content in a different order from the tag tree | semantic | warning | —, Matterhorn 09 | 1.3.2 | struct | implemented | The content stream draws marked content in an order that disagrees with the structure tree, so readers that follow the stream (Preview, Chrome, copy-paste) get a different reading order from readers that follow the tags. | Re-emit the page content in the order of the structure tree, or reorder the tree to match the page if the page is right. |
| **ORD-002** Structure tree order crosses pages | semantic | warning | —, Matterhorn 09 | 1.3.2 | struct | planned | A structure element's content comes from later pages before earlier ones, so the reading order runs backwards through the document. | Order the structure elements by page and position. |

## Navigation

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **NAV-001** Long document has no bookmarks | semantic | warning | —, Matterhorn 27 | 2.4.5 | — | implemented | A document of ten pages or more has no outline (/Outlines with entries), so a reader has no way to jump to a section; WCAG 2.4.5 asks for more than one way to find content in a document of this length. | Add bookmarks from the headings (most tools generate them from H1 to H3). |

## Pagination

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **PAG-001** Running header or footer is tagged as content | conformance | warning | ISO 14289-1 7.8, Matterhorn 18 | 1.3.1, 2.4.1 | pages3 | implemented | Text that recurs at the same position on most pages (a running head, a folio) is inside structure elements rather than artifacts, so the reader hears it on every page. | Mark running heads, footers and page numbers as /Artifact /Pagination. |

## Source comparison (needs --source)

| Rule | Layer | Severity | Standard | WCAG 2.2 | Requires | Status | What it claims | What to change |
|---|---|---|---|---|---|---|---|---|
| **SEM-001** Structure the source had that the output lost | semantic | error | — | 1.3.1 | source | implemented | When a source PDF is supplied, the output has fewer headings, tables, lists or figures than the source; remediation must not cost a reader structure they already had. | Compare the two structure trees and restore the elements the output dropped. |
| **SEM-002** Text the source had that the output lost | semantic | error | — | 1.3.1 | source | implemented | When a source PDF is supplied, characters present in the source's text layer are missing from the output's. | Find the pages whose text shrank and restore the runs that were dropped. |
| **SEM-003** Pages look different from the source | semantic | error | — | — | source | implemented | When a source PDF is supplied, a rendered page differs visibly from the same page in the source; tagging must not change what a sighted reader sees. | Diff the renders of the flagged pages and undo whatever the remediation changed in the appearance. |

## Matterhorn Protocol 1.1 checkpoints

| Checkpoint | Conformance rules | Semantic rules (beyond the protocol) |
|---|---|---|
| 01 Real content tagged | DOC-001, DOC-002, DOC-003, TAG-001, TAG-004, TAG-021, TAG-022, TAG-023, TXT-011 | TAG-002, TAG-003 |
| 02 Role mapping | TAG-010, TAG-011, TAG-012 | — |
| 03 Flickering | — | — |
| 04 Color and contrast | — | — |
| 05 Sound | — | — |
| 06 Metadata | DOC-010, DOC-012, DOC-015 | DOC-040 |
| 07 Dictionary | DOC-011 | — |
| 08 OCR validation | — | — |
| 09 Appropriate tags | — | TAG-020, ORD-001, ORD-002 |
| 10 Character mappings | TXT-002, TXT-003, TXT-006 | TXT-004 |
| 11 Declared natural language | DOC-013, DOC-014 | — |
| 12 Stretchable characters | — | — |
| 13 Graphics | FIG-001 | TAG-030, FIG-002, FIG-010, FIG-011, FIG-012 |
| 14 Headings | HDG-001, HDG-002, HDG-003, HDG-004, HDG-005 | HDG-010, HDG-011, HDG-012 |
| 15 Tables | TBL-001, TBL-002, TBL-003, TBL-004, TBL-005 | TBL-010, TBL-011, TBL-012, TBL-013, TBL-014, TBL-015 |
| 16 Lists | LST-001, LST-002, LST-003, LST-004 | — |
| 17 Mathematical expressions | MATH-001 | MATH-010, MATH-011 |
| 18 Page headers and footers | PAG-001 | — |
| 19 Notes and references | NOTE-001, NOTE-004 | NOTE-002, NOTE-003 |
| 20 Optional content | DOC-030 | — |
| 21 Embedded files | DOC-031 | — |
| 22 Article threads | — | — |
| 23 Digital signatures | — | — |
| 24 Non-interactive forms | — | — |
| 25 XFA | DOC-021 | — |
| 26 Security | DOC-020 | — |
| 27 Navigation | — | NAV-001 |
| 28 Annotations | LNK-001, LNK-002, LNK-004, LNK-006, LNK-005, FRM-001, FRM-003 | LNK-003, FRM-002 |
| 29 Actions | — | — |
| 30 XObjects | TAG-040 | — |
| 31 Fonts | TXT-001, TXT-005, TXT-007 | — |

## WCAG 2.2 success criteria (A and AA)

| Criterion | Level | Rules | When no rule applies |
|---|---|---|---|
| 1.1.1 Non-text Content | A | TAG-030, TAG-031, TAG-032, FIG-001, FIG-002, FIG-010, FIG-011, FIG-012, LNK-002, MATH-001, MATH-010, MATH-011 |  |
| 1.2.1 Audio-only and Video-only (Prerecorded) | A | — | Not applicable without media. Embedded audio or video needs a transcript or description. |
| 1.2.2 Captions (Prerecorded) | A | — | Not applicable without media. Embedded video with speech needs captions. |
| 1.2.3 Audio Description or Media Alternative (Prerecorded) | A | — | Not applicable without media. Embedded video needs an audio description or a text alternative. |
| 1.2.4 Captions (Live) | AA | — | Not applicable to a document. A document carries no live media. |
| 1.2.5 Audio Description (Prerecorded) | AA | — | Not applicable without media. Embedded video needs an audio description. |
| 1.3.1 Info and Relationships | A | DOC-001, DOC-002, DOC-003, DOC-020, DOC-030, TAG-001, TAG-002, TAG-003, TAG-004, TAG-010, TAG-011, TAG-012, TAG-020, TAG-021, TAG-022, TAG-023, TAG-040, TAG-030, TXT-002, TXT-003, TXT-004, TXT-005, TXT-006, TXT-011, HDG-001, HDG-002, HDG-003, HDG-004, HDG-005, HDG-012, TBL-001, TBL-002, TBL-003, TBL-004, TBL-005, TBL-010, TBL-011, TBL-012, TBL-013, TBL-014, TBL-015, LST-001, LST-002, LST-003, LST-004, LNK-001, LNK-006, FRM-001, FRM-003, NOTE-001, NOTE-004, NOTE-002, NOTE-003, MATH-011, PAG-001, SEM-001, SEM-002 |  |
| 1.3.2 Meaningful Sequence | A | DOC-002, TAG-001, TAG-022, TXT-011, LNK-006, FRM-003, ORD-001, ORD-002 |  |
| 1.3.3 Sensory Characteristics | A | — | Instructions must not rely on shape, size, position or colour alone ('the box on the right'). |
| 1.3.4 Orientation | AA | — | Not applicable to a document. A document does not lock the display orientation. |
| 1.3.5 Identify Input Purpose | AA | — | Not applicable without forms. Fields that collect personal data should say what they collect in a way software can read. |
| 1.4.1 Use of Color | A | — | Meaning carried by colour alone (a red figure, a coloured link) must also be carried another way. |
| 1.4.2 Audio Control | A | — | Not applicable without media. Audio that starts on its own must be stoppable. |
| 1.4.3 Contrast (Minimum) | AA | — | Text needs 4.5:1 contrast against its background (3:1 for large text). Not measured yet. |
| 1.4.4 Resize Text | AA | — | Viewers zoom a PDF; check that text is real text, not an image, so it stays sharp. |
| 1.4.5 Images of Text | AA | — | Pictures of text should be real text unless the picture is essential. |
| 1.4.10 Reflow | AA | — | A tagged document reflows in viewers that support it; check tables and figures survive. |
| 1.4.11 Non-text Contrast | AA | — | Form field borders, icons and chart elements need 3:1 contrast. |
| 1.4.12 Text Spacing | AA | — | Content must survive wider letter, word and line spacing where the viewer applies it. |
| 1.4.13 Content on Hover or Focus | AA | — | Not applicable without annots. Pop-up notes and tooltips must be dismissable and hoverable. |
| 2.1.1 Keyboard | A | — | Not applicable without interactive. Every link and field must be reachable and usable from the keyboard. |
| 2.1.2 No Keyboard Trap | A | — | Not applicable without interactive. Focus must be able to leave every field. |
| 2.1.4 Character Key Shortcuts | A | — | Not applicable without actions. Single-key shortcuts in document scripts must be remappable. |
| 2.2.1 Timing Adjustable | A | — | Not applicable without actions. Time limits set by document scripts must be adjustable. |
| 2.2.2 Pause, Stop, Hide | A | — | Not applicable without media. Moving or blinking content must be pausable. |
| 2.3.1 Three Flashes or Below Threshold | A | — | Not applicable without media. Nothing may flash more than three times a second. |
| 2.4.1 Bypass Blocks | A | PAG-001 |  |
| 2.4.2 Page Titled | A | DOC-010, DOC-011, DOC-015, DOC-040 |  |
| 2.4.3 Focus Order | A | LNK-005 | Not applicable without annots. |
| 2.4.4 Link Purpose (In Context) | A | LNK-001, LNK-002, LNK-003 | Not applicable without links. |
| 2.4.5 Multiple Ways | AA | NAV-001 |  |
| 2.4.6 Headings and Labels | AA | HDG-001, HDG-002, HDG-003, HDG-004, HDG-005, HDG-010, HDG-011 |  |
| 2.4.7 Focus Visible | AA | — | Not applicable without interactive. The viewer shows focus; check that fields and links do not hide it. |
| 2.4.11 Focus Not Obscured (Minimum) | AA | — | Not applicable without interactive. A focused field must not be hidden behind other content. |
| 2.5.1 Pointer Gestures | A | — | Not applicable without actions. Document scripts must not require multi-point or path gestures. |
| 2.5.2 Pointer Cancellation | A | — | Not applicable without actions. Actions must complete on release, not press. |
| 2.5.3 Label in Name | A | — | Not applicable without forms. A field's accessible name (/TU) must contain its visible label. |
| 2.5.4 Motion Actuation | A | — | Not applicable to a document. A document takes no motion input. |
| 2.5.7 Dragging Movements | AA | — | Not applicable without actions. Document scripts must not require dragging. |
| 2.5.8 Target Size (Minimum) | AA | — | Not applicable without interactive. Links and fields should be at least 24 by 24 points, or spaced apart. |
| 3.1.1 Language of Page | A | DOC-013, DOC-014 |  |
| 3.1.2 Language of Parts | AA | — | Not applicable without struct. Passages in another language need /Lang on their element. |
| 3.2.1 On Focus | A | — | Not applicable without forms. Focusing a field must not trigger a change. |
| 3.2.2 On Input | A | — | Not applicable without forms. Changing a field must not trigger an unexpected change. |
| 3.2.3 Consistent Navigation | AA | — | Not applicable without pages3. Repeated navigation (running heads, page furniture) should be in the same order on every page. |
| 3.2.4 Consistent Identification | AA | — | The same thing should be named the same way throughout. |
| 3.2.6 Consistent Help | A | — | Not applicable without forms. Help for filling the form should be in the same place on every page. |
| 3.3.1 Error Identification | A | — | Not applicable without forms. Validation errors must be described in text. |
| 3.3.2 Labels or Instructions | A | FRM-001, FRM-002 | Not applicable without forms. |
| 3.3.3 Error Suggestion | AA | — | Not applicable without forms. Where an error is known, suggest the fix. |
| 3.3.4 Error Prevention (Legal, Financial, Data) | AA | — | Not applicable without forms. Submissions with legal or financial effect must be reversible, checked or confirmable. |
| 3.3.7 Redundant Entry | A | — | Not applicable without forms. Do not ask for the same information twice in one form. |
| 3.3.8 Accessible Authentication (Minimum) | AA | — | Not applicable without forms. No cognitive function test to sign or submit. |
| 4.1.2 Name, Role, Value | A | DOC-021, TAG-010, TAG-011, TAG-012, LNK-003, FRM-001, FRM-003, FRM-002 |  |
| 4.1.3 Status Messages | AA | — | Not applicable without actions. Messages from document scripts must reach assistive technology. |

---
name: docfit-school-extract
description: Convert supplied school thesis templates, legacy Word files, PDFs, requirement docs, and sample theses into a validated docfit school package. Use when onboarding or updating a school directory, extracting fonts/margins/headings/captions/references/front matter/post-body logical pages into school.yaml, requirements.yaml with top-level checks, style_mapping.yaml, cover fragments, reference fixtures, or template-manifest-ready evidence.
---

# Docfit School Extract

## Core Rule

Do not pretend this is one-click automatic extraction. Use programs wherever
they can produce evidence, then make explicit evidence-backed judgments for the
parts that require human reasoning.

Every final school rule should answer:

- What source said this?
- Was it programmatically extracted, visibly stated, or inferred?
- What conflict or uncertainty remains?
- How did validation prove the package is usable?

Use `references/evidence-template.md` when the extraction has more than a few
rules or when sources disagree.

## Workflow

### 0. Choose Mode

For a new school, run the full extraction workflow below.

For an existing school package, first run an audit/update pass: compare
`school.yaml`, `requirements.yaml` including top-level `checks:`,
`style_mapping.yaml`, `README.md`, `reference.docx`, and `fixtures/` against the
committed upstream sources. Do not refresh tracked golden fixtures or binary
assets just because a script can generate them; refresh them only when a
rule/source mismatch was found or the user explicitly asked for fixture updates.

### 1. Inventory Sources

List all provided files and classify each one:

- official Word template
- legacy `.doc` template
- PDF/spec text
- requirement/instruction document
- accepted thesis sample
- school fixed form bundle

Preserve originals under `schools/<school-id>/upstream/`, usually
`upstream/word/`. If a legacy `.doc` must be inspected, convert it with
LibreOffice and keep both original and converted files:

```bash
soffice --headless --convert-to docx --outdir /tmp/docfit-school schools/<school-id>/upstream/word/source.doc
```

If the visible school name in the source conflicts with the directory slug,
flag it clearly in the school README and final response. Ask before renaming a
tracked school id unless the user already requested the rename.

If an official specification is not checked in, link the exact school page or
attachment in the README and ledger. Third-party templates, accepted theses, or
community LaTeX/Word projects must be labeled as visual/reference evidence, not
as normative sources, unless the school itself publishes them as official.

### 2. Extract Programmatic Evidence

Prefer deterministic tools before reasoning:

```bash
file <source>
uv run docfit features extract <source.docx>
uv run python - <<'PY'
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

path = Path("SOURCE.docx")
doc = Document(path)
print("paragraphs", len(doc.paragraphs), "tables", len(doc.tables), "sections", len(doc.sections))
for i, section in enumerate(doc.sections):
    print("section", i, section.top_margin.mm, section.bottom_margin.mm, section.left_margin.mm, section.right_margin.mm)
for i, paragraph in enumerate(doc.paragraphs):
    text = paragraph.text.strip()
    if text:
        print(f"{i:03d}", paragraph.style.style_id, paragraph.style.name, text[:160])
for style in doc.styles:
    if style.type.name != "PARAGRAPH":
        continue
    if style.name in {"Normal", "Heading 1", "Heading 2", "Heading 3", "Caption"} or not style.builtin:
        rpr = style._element.rPr
        ppr = style._element.pPr
        size = None
        fonts = None
        spacing = None
        if rpr is not None:
            sz = rpr.find(qn("w:sz"))
            if sz is not None:
                size = int(sz.get(qn("w:val"))) / 2
            rf = rpr.find(qn("w:rFonts"))
            if rf is not None:
                fonts = {k: rf.get(qn("w:" + k)) for k in ["ascii", "hAnsi", "eastAsia", "cs"]}
        if ppr is not None:
            sp = ppr.find(qn("w:spacing"))
            if sp is not None:
                spacing = {k: sp.get(qn("w:" + k)) for k in ["before", "after", "line", "lineRule"]}
        print(style.style_id, repr(style.name), "size", size, "fonts", fonts, "spacing", spacing)
PY
```

Use direct OOXML inspection when `python-docx` hides details:

```bash
unzip -p <source.docx> word/styles.xml | rg "styleId|rFonts|spacing|outlineLvl|jc"
unzip -p <source.docx> word/document.xml | rg "pgMar|pgSz|tbl|sdt|bookmark"
```

Do not treat `uv run docfit features extract` or `word/styles.xml` as the final
style oracle. Feature extraction and raw style definitions are evidence, but
official templates often contain visible examples whose paragraph or run direct
formatting intentionally overrides the named style. For visible examples,
compute the effective formatting from `docDefaults` → based-on style chain →
style `pPr/rPr` → paragraph `pPr/rPr` → run `rPr`; then record any conflict
between the raw style and the visible result. This is especially important for
TOC field result paragraphs, hyperlinks, and generated examples: inspect the
actual `word/document.xml` result paragraphs/runs, not only the `toc 1`/`toc 2`
style definitions.

When optional files may or may not exist, use `find`, arrays, or shell
`nullglob`/existence checks instead of naked globs. A failed glob should not
abort the extraction or silently skip a source class.

### 3. Resolve Conflicts Deliberately

Use this precedence for final values:

1. Visible normative school spec text.
2. Official template visible instruction text.
3. Official template effective visible examples, including paragraph/run direct
   formatting and inherited style values.
4. Official template raw OOXML styles and section properties.
5. Accepted thesis samples.
6. Conservative thesis-format heuristics.

Document any conflict. Example: if converted OOXML says `20mm` top margin but
visible text says `2.54cm`, use `25.4mm` and note why.
When a raw style and the effective visible example disagree, do not silently
choose the style definition. Add a conflict row explaining which layer supplied
the winning value and whether the renderer/test fixture must encode a direct
override.

### 4. Infer The Actual Thesis Contract

Infer and record at least these areas:

- Page: paper size, margins, gutter, header/footer distances.
- Body: CJK/Latin fonts, size, line spacing, alignment, first-line indent.
- Headings: H1/H2/H3 fonts, sizes, spacing, alignment, outline levels, numbering
  scheme, and required separator spaces.
- Abstract/keywords/TOC: title and body styles, effective TOC entry formatting
  from visible field results/examples, TOC depth, whether typed TOC lines must
  be replaced by a Word TOC field.
- Captions/tables/figures: label text, numbering pattern, reset policy, whether
  figure captions are below and table captions are above, font/alignment rules.
- References: heading style, item style, bracketed or period numbering, GB/T
  rule evidence, continuation handling.
- Formula and units: whether numbering is chapter-scoped, right-aligned,
  upright terms/operators, or manual-only.
- Front/post-body matter: cover, declarations, instructions before the TOC,
  academic achievements, task books, data-set tables, appendices, author resume,
  defense/grade forms. Keep these school-owned and outside generic body
  normalization.

### 4a. Build The Logical Page Contract

Do not let the extractor decide logical pages only from whatever content the
student source happens to contain. The target school's official template and
requirement documents own the page sequence.

Create an ordered logical-page ledger for every page-like section before and
after the main body. Include:

- `id`: stable snake-case id, for example `cover`,
  `originality_statement`, `toc`, `academic_achievements`, `author_resume`,
  `dataset`, `design_task`, `proposal`, `defense_record`, `grade_form`,
  `appendix`, or `acknowledgement`.
- `titles`: visible Chinese/English headings and aliases. Include long forms
  such as `相关的学术成果目录`, `攻读硕士学位期间取得的学术成果`,
  `作者简历及攻读硕士学位期间取得的研究成果`, and `学位论文数据集`.
- `owner`: usually `target_school_template`. Use `source_student_content` only
  for body content that should be moved into a target-owned slot.
- `position`: before cover, before TOC, between TOC and body, after references,
  after appendix, or other explicit ordering evidence.
- `status`: one of `required`, `optional`, `conditional`, or `manual_only`.
- `source_policy`: whether content is copied from the student source,
  generated from metadata, preserved as a school form, or left for manual fill.
- `empty_policy`: what happens when no student/source content exists.
- `implementation_notes`: required template slot, manifest slot, parser block
  kind, heading aliases, stop-title behavior, and validation/review checks.

Default empty-content policy:

- Required target-owned page missing content: keep the page or form shell, add a
  visible needs-human placeholder, and make strict/final validation fail or
  report the missing value.
- Optional target-owned page missing content: keep the logical page in
  draft/review output with a visible placeholder unless the official school
  source explicitly says the page should be omitted. Use a sentence like:
  `【源文档中未识别到本页内容；如学校不要求，可删除本页。】`
- Conditional page: record the condition and use the optional policy until the
  condition is known. Do not silently remove it just because the source thesis
  omitted it.
- Manual-only signed form or administrative page: keep the school-owned form
  shell or placeholder and mark it manual-only; do not normalize it as body
  prose.
- Source-school-only front matter from the input thesis: strip or ignore it
  during conversion unless it supplies metadata for the target page. This rule
  does not authorize deleting target-school logical pages.

For template-first packages, every target-owned logical page with a visible
anchor, content control, or bookmark should be represented in
`template_manifest.yaml` or an equivalent school-specific renderer contract.
Prefer an explicit empty policy such as `placeholder_review` for optional
logical pages. Use `remove_block` only when the school source says the final
document should omit that page and the README explains the decision.

Parser and renderer guidance:

- Treat logical-page headings and aliases as block starts / stop titles, not as
  ordinary body headings.
- Post-body pages such as academic achievements, author resume, thesis data
  set, appendix, and acknowledgement must stop the references block from
  swallowing them.
- Front-matter pages such as declarations, usage authorization, abstract, TOC,
  and pre-TOC instructions must not become chapter headings.
- If the runtime model lacks a block kind for a school-owned page, record the
  required new kind or school-specific mapping in `implementation_notes`; do not
  hide the page by mapping it to `UNKNOWN` without a review finding.

### 4b. Build A Page-Start Layout Contract

Do not infer a logical page's visible leading whitespace by counting empty OOXML
paragraphs alone. Natural pagination, `pageBreakBefore`, explicit page breaks,
and `nextPage` section boundaries can assign the same empty paragraph to
different visible pages in Microsoft Word and LibreOffice.

For every logical unit that starts a page, record and validate:

- `boundary_mode`: document start, `pageBreakBefore`, explicit page break, or
  `nextPage` section.
- `boundary_owner`: the exact paragraph that owns the boundary. A unit must have
  one owner; duplicated page and section breaks are forbidden.
- `first_anchor`: the first visible title, form label, or stable text anchor.
- `leading_blank_paragraphs`: only blank paragraphs visibly present after the
  boundary in the canonical renderer. Undeclared blocks between the boundary
  and first anchor are a build failure.
- `first_anchor_spacing_before`: explicit paragraph spacing that replaces
  instruction-derived or otherwise ambiguous empty paragraphs.
- Section page margins, numbering, and header/footer inheritance.
- Canonical-renderer page number and anchor offset (or an equivalent screenshot
  reference) with a small tolerance.

Prefer paragraph spacing or section geometry over editable blank paragraphs.
Keep a leading blank paragraph only when the official visible example requires
one and the canonical renderer proves that it belongs to the new page.

Renderer precedence for layout QA:

1. The renderer used by the school/user for final Word delivery (normally
   Microsoft Word; use WPS if the user explicitly treats WPS as authoritative).
2. Official PDF or screenshot evidence from that renderer.
3. LibreOffice for broad whole-document scanning.
4. Raw OOXML as structural evidence, not a visible-layout oracle.

When Word and LibreOffice disagree, do not average the coordinates and do not
mark the build accepted because one renderer passes. Record the conflict and
make the canonical renderer decisive. A final template is not accepted until
every logical-page start has been reviewed in the canonical renderer.

Cross-school examples that should be captured by this ledger:

- Nanjing Agricultural undergraduate templates may include
  `相关的学术成果目录（此项非必需项）`; this is optional, target-owned, and should
  become a review placeholder when absent.
- Beijing Jiaotong graduate templates include post-body sections such as
  appendix, author resume / research achievements, and thesis data set.
- Hunan Agricultural packages may include task book, proposal, defense record,
  and grade form pages that are school-owned administrative forms.
- Generic `致谢` and `附录` are optional in several schools, but optional does
  not automatically mean "delete during draft conversion."

Useful Chinese size conversions:

| Name | pt |
| --- | ---: |
| 一号 | 26 |
| 小二 | 18 |
| 二号 | 22 |
| 三号 | 16 |
| 小三 | 15 |
| 四号 | 14 |
| 小四 | 12 |
| 五号 | 10.5 |
| 小五 | 9 |

Treat `□` in Chinese format docs as an explicit space marker, often one Chinese
character width or two ASCII spaces. Preserve it as a requirement when it
affects heading/caption/reference parsing.

### 5. Produce Docfit Assets

Create or update:

- `schools/<school-id>/school.yaml`
- `style_mapping.yaml`
- `requirements.yaml` with top-level `checks:`
- `cover_fragment.xml` or `cover.inject: false` if the template owns cover/front
  matter
- `README.md`
- `upstream/` provenance assets
- `reference.docx`
- `fixtures/reference.docx`
- `fixtures/features.json`

For shallow packages, generate reference assets from `school.yaml`:

```bash
uv run python scripts/gen_school_reference.py <school-id>
uv run python scripts/build_golden.py <school-id>
```

For deep template-first packages, prefer a school-owned `template.docx` with
content-control or bookmark slots and a `template_manifest.yaml`. Text anchors
are only a migration bridge for existing templates.

Template-first packages may keep `template.docx` and `template_manifest.yaml`
at the school root while still generating a style `reference.docx` and
`fixtures/reference.docx` for validation. If a package intentionally omits one
of these assets, document the exception in `README.md` and make validation
commands use the actual canonical asset.

The produced assets should preserve the logical-page contract:

- `school.yaml` `sections:` should list the target school page order even for
  optional or manual-only pages.
- `requirements.yaml` should include evidence rows and checks for each
  target-owned logical page whose presence, absence, or manual-only status
  matters.
- `template_manifest.yaml` should expose target-owned logical pages as slots,
  fixed blocks, or explicit school-specific renderer responsibilities. Missing
  optional content should prefer a review-placeholder policy over silent
  deletion unless school evidence justifies deletion.
- `README.md` should state which logical pages are required, optional,
  conditional, or manual-only, and which pages are emitted as placeholders for
  student review.

### 6. Validate

Run the narrowest useful checks, then broaden if runtime assets changed:

```bash
uv run docfit schools validate <school-id>
uv run docfit schools coverage <school-id>
uv run docfit schools validate --all
uv run ruff check src/ tests/ scripts/
uv run mypy src/
uv run pytest tests/unit/test_school_coverage.py tests/integration/test_student_fixture_matrix.py
```

Use `uv run pytest` when changes touch shared runtime, school discovery, or the
student-to-target-school conversion matrix.

For deep template-first packages, validation must also include:

- A machine-readable page-start contract covering every page-owning logical
  unit, not only the page currently under review.
- A negative regression fixture proving the validator rejects one extra or one
  missing page-start line.
- Full-document rendering in LibreOffice for overflow, page count, and form
  integrity.
- A final canonical-renderer review of all logical-unit starts. Preserve
  screenshots or exported-PDF anchor measurements in the evidence ledger.

### 7. Report Back

Summarize:

- which sources were used
- which values were program-extracted
- which values were inferred and why
- the logical-page ledger, including required/optional/conditional/manual-only
  status and empty-content policy
- unresolved conflicts or manual-only requirements
- exact validation commands and outcomes
- whether the package is shallow validation-only or has a slot-based engineering
  template ready for generic rendering

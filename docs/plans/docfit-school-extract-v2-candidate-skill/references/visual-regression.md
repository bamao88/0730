# Visual regression

Use this reference to interpret `template_compare` results. The Tool identifies actual differences and
selects images; the Agent decides whether the result is semantically and visually acceptable.

## Read differences in three passes

1. Match every expected change to the operation that authorized it.
2. Investigate every unexpected structural or visual change, especially protected content, table grid, section,
   header/footer, numbering, pagination, and slot containers.
3. Inspect images at both local and page context before accepting the mutation.

An operation is not validated merely because its target changed. It is validated only when the intended
change occurred and protected surroundings did not change without explanation.

## Review scope

The comparison Tool has `mutation_review` and `final_review` modes. Mutation review selects at least:

- text clear: before/after crop and the resulting full page;
- paragraph/container removal: target page and adjacent pages;
- bounded block or table change: before/after contact sheet and boundary pages;
- section, header/footer, or pagination change: all affected section pages;
- page-count change or mapping failure: expanded pages or full-document review.

Final review is a separate call bound to the exact final snapshot and selects every `candidate_verification` page,
including when the source needs zero mutation. A complete comparison is immutable. Fetch its native images
in cursor batches until `next_cursor` is absent; transfer limits never justify missing a required page.

Ask for a broader observation only when the supplied evidence cannot resolve the visual question. Do not
replace existing candidate-verification evidence with a different backend and compare page numbers across them.

## Acceptance questions

- Is the intended instruction/example gone without erasing its surviving responsibility?
- Did protected wording, branding, declarations, headers/footers, numbering, and table geometry remain intact?
- Does cleared space still provide a usable fill boundary?
- Are page breaks, blank pages, wrapping, alignment, and whitespace plausible consequences of the change?
- Does each slot's visual location agree with its semantic role and structural locator?
- Are all unexpected differences explained by an authorized operation?

Record each comparison manifest's stable `required_image_id`, its affected pages, the final template hash,
the Agent finding, and any blocking status.
Write those dispositions directly into `artifact-decisions.yaml`; `compile_artifact_spec.py` normalizes them
as the embedded typed review record, and `template_build` emits `visual-review.json`. Review evidence from an
earlier hash cannot satisfy final build.

Tool facts use `machine_blocking: true | false`; Agent interpretation uses
`disposition: accepted | blocking | needs_edit`. An accepted disposition cannot override a machine-blocking
finding. Correct the document or decision and create a new comparison instead.

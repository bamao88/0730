# Visual regression

Use this reference to interpret `template_compare` results. The Tool identifies actual differences and
selects images; the Agent decides whether the result is semantically and visually acceptable.

## Read differences in three passes

1. Match every expected change to the operation that authorized it.
2. Investigate every unexpected structural or visual change, especially fixed content, table grid, section,
   header/footer, numbering, pagination, and slot containers.
3. Inspect images at both local and page context before accepting the mutation.

An operation is not validated merely because its target changed. It is validated only when the intended
change occurred and protected surroundings did not change without explanation.

## Review scope

The comparison Tool selects at least:

- text clear: before/after crop and the resulting full page;
- paragraph/container removal: target page and adjacent pages;
- bounded block or table change: before/after contact sheet and boundary pages;
- section, header/footer, or pagination change: all affected section pages;
- page-count change or mapping failure: expanded pages or full-document review;
- final candidate: every page of the exact final template hash.

Ask for a broader observation only when the supplied evidence cannot resolve the visual question. Do not
replace an existing authoritative rendering with a different backend and compare page numbers across them.

## Acceptance questions

- Is the intended instruction/example gone without erasing its surviving responsibility?
- Did fixed wording, branding, declarations, headers/footers, numbering, and table geometry remain intact?
- Does cleared space still provide a usable fill boundary?
- Are page breaks, blank pages, wrapping, alignment, and whitespace plausible consequences of the change?
- Does each slot's visual location agree with its semantic role and structural locator?
- Are all unexpected differences explained by an authorized operation?

Record the reviewed page/image refs, the final template hash, the Agent finding, and any blocking status.
Review evidence from an earlier hash cannot satisfy final freeze.

# Template semantics

Use this reference to decide what a visible template element means and which responsibility must survive
cleanup. Keep school-specific conclusions in the current artifact, not in this reference.

## Do not flatten different questions into one classification

Record the current visible role separately from the responsibility that must survive cleanup:

| Field | Meaning | Values |
|---|---|---|
| `observed_roles` | What the current object visibly does | `fixed_content`, `placeholder`, `instruction`, `example`, `mechanism`, `structural_container`, `unknown` |
| `responsibilities[].kind` | What the reusable interface must continue to provide | `fixed`, `fill`, `generate` |
| `responsibilities[].content_kind` | What a fill/generate responsibility carries | `scalar`, `paragraph_stream`, `composite` |
| `responsibilities[].cardinality` | How many instances the responsibility allows | independent `min` and `max` |
| `responsibilities[].condition` | When the responsibility is present | an optional, sourced condition |
| `responsibilities[].handling` | Whether fulfillment can be automated safely | `automatic`, `manual` |
| `resolution` | Whether current evidence supports the decision | `resolved`, `unresolved` |

The first two fields may contain multiple entries. Split a target when different fragments need different
operations.

`repeat`, `conditional`, and `manual` are not responsibility kinds: they are cardinality, condition, and
handling properties. `unresolved` is an evidence state. `remove` is a mutation action, not a semantic
responsibility. A disposable instruction can have no surviving responsibility after migration, while the
fill or generate responsibility it described continues at another target.

Classification is a semantic decision, not text matching. The same phrase can be fixed content in one
location and an instruction in another.

## Migrate semantics before deletion

An instruction or example can encode more than visible text. Before removing it, check whether it states or
demonstrates:

- required wording or fixed punctuation;
- placement and ordering;
- style, spacing, indentation, numbering, or section behavior;
- allowed content kind;
- minimum, maximum, or conditional cardinality;
- a generated mechanism such as a field, index, or table of contents;
- a repeated container or composite structure.

Move each surviving responsibility into the cleaned template structure, slot manifest, fixed-region record,
manual region, or gap. A removal decision references those migration destinations. If nothing survives,
record an explicit empty responsibility list with evidence and rationale. Only then may the visible
instruction/example receive a `remove_content` operation.

## Logical units and physical pages

A title page, declaration, abstract, table of contents, chapter, appendix, or reference list is a logical
unit. It may span several pages or share a page with another unit. Page boundaries can change after content
or layout edits.

Use structural objects, stable boundaries, and context to identify logical units. Use page images to verify
their appearance, never as the durable identity used for mutation or slot binding.

## Composite and generated objects

Treat the following as mechanisms rather than plain cached text:

- tables of contents and other fields;
- numbered lists and multilevel numbering;
- cross-references, captions, footnotes, and endnotes;
- repeated table rows or structured sections;
- headers, footers, page numbers, and section-linked content;
- content controls and other wrapper/container relationships.

If the reusable template must preserve the behavior, record `kind: generate` or `kind: fixed` as appropriate;
express repetition through cardinality and conditional presence through `condition`. Do not replace the
mechanism with its current display value.

## Source conflicts

Track the source of each decisive requirement. Prefer an explicitly authoritative current-task source, but
do not invent a universal priority order when the user or material has not established one.

When two sources disagree:

1. determine whether they cover the same semantic role and scope;
2. preserve both observed claims and their provenance;
3. apply an explicit task-specific precedence rule if one exists;
4. otherwise ask the user when the choice changes fixed content, slot semantics, or final appearance;
5. if work can safely continue, leave the property unresolved and prevent freeze when it is blocking.

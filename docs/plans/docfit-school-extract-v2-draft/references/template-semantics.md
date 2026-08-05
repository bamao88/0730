# Template semantics

Use this reference to decide what a visible template element means and which responsibility must survive
cleanup. Keep school-specific conclusions in the current artifact, not in this reference.

## Content responsibilities

Classify each relevant region by its downstream responsibility:

| Responsibility | Meaning |
|---|---|
| fixed | Must remain unchanged in the reusable template |
| fill | Downstream content replaces an empty or placeholder value |
| generate | A program or Word feature must generate the result |
| repeat | A structural unit may occur a task-dependent number of times |
| conditional | Presence depends on a stated condition |
| manual | Meaning is known, but safe automatic placement is not |
| remove | Content is disposable after its surviving semantics are migrated |
| unresolved | Evidence cannot yet establish the responsibility |

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
manual region, or gap. Only then may the visible instruction/example be removed.

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

If the reusable template must preserve the behavior, classify it as generate, repeat, conditional, or fixed
as appropriate. Do not replace the mechanism with its current display value.

## Source conflicts

Track the source of each decisive requirement. Prefer an explicitly authoritative current-task source, but
do not invent a universal priority order when the user or material has not established one.

When two sources disagree:

1. determine whether they cover the same semantic role and scope;
2. preserve both observed claims and their provenance;
3. apply an explicit task-specific precedence rule if one exists;
4. otherwise ask the user when the choice changes fixed content, slot semantics, or final appearance;
5. if work can safely continue, leave the property unresolved and prevent freeze when it is blocking.

# Template semantics

Use this reference to decide what a visible template element means and which responsibility must survive
cleanup. Keep school-specific conclusions in the current task artifact, not in this reusable reference.

## Keep different questions separate

| Dimension | Question | Examples |
|---|---|---|
| observed role | What does the current object visibly do? | protected text, example, instruction, placeholder, mechanism, container, unknown |
| responsibility kind | What must the reusable interface continue to provide? | protected, fill, generate |
| `field_id` | What thesis-domain meaning does a fill responsibility have? | Registry-bound semantic ID |
| template owner | How is the final template region treated? | protected, slot, remove |
| content type | What value/object does it carry? | text, rich text, section, image, table, formula, asset |
| required/cardinality | Is it required and how many values are allowed? | required boolean; one, many, optional |
| condition | When is the responsibility present? | sourced optional condition |
| handling | Can it be fulfilled safely by automation? | automatic, manual |
| resolution | Does current evidence support one decision? | resolved, unresolved |

`remove` is a template region owner and mutation operation, not a surviving semantic responsibility. `manual`
is handling, not a field type. `unresolved` is an evidence state. The same phrase can have different roles in
different places; text matching alone is not classification.

## Registry identity and template identity

Registry `field_id` says what a value means. Template `slot_id/region_id` says where one template revision
accepts or protects it. A field may map to several slots; one composite slot may have several physical component
locators. Neither identity replaces a DOCX locator or grants write permission.

Use a current snapshot execution locator for mutation and evidence. Use a persistent artifact locator plus
`template_sha256` for the final fill contract. Page numbers are human evidence only.

## Migrate semantics before deletion

Before removing an instruction/example, determine whether it encodes:

- required wording/punctuation;
- placement/order;
- value style, spacing, numbering, or section behavior;
- content type, required/cardinality, or a condition;
- a generated field/index/table-of-contents mechanism;
- a repeated or composite container.

Move each surviving responsibility into protected structure, a registered slot, generated mechanism, manual
record, or gap. A removal references those destinations. If nothing survives, record precise current-task
deletion authorization and rationale before creating `remove_content`.

## Logical units are not pages

Title pages, declarations, abstracts, contents, chapters, appendices, and references are logical units. They may
span or share pages, and pagination changes after editing. Identify them through objects, stable boundaries, and
context; use images to review appearance, never as the durable mutation/slot identity.

## Preserve mechanisms

Treat fields, indexes, numbering, cross-references, captions, footnotes, repeated structures, headers/footers,
page numbers, content controls, bookmarks, and section links as mechanisms rather than cached text. If reusable
behavior must survive, preserve the mechanism and its responsibility; do not replace it with the current display
value.

## Source conflicts

Track the source and scope of each decisive claim. When two sources disagree:

1. determine whether they cover the same semantic role and scope;
2. preserve both claims and provenance;
3. apply a current task/user precedence decision if one exists;
4. otherwise ask when the choice changes protected content, slot semantics, or final appearance;
5. keep the property unresolved and block build when safe downstream filling requires one value.

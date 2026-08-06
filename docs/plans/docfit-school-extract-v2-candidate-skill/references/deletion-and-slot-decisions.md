# Deletion and slot decisions

Use this reference after observation has produced a current snapshot and stable target candidates. The mode set
is a candidate capability inventory, not a requirement to ship every mode in one increment. Only use modes that
belong to the current approved slice and already pass the Tool / Code Gate.

## Removal is an operation

First record visible roles, surviving responsibilities, field/slot mapping, resolution, and evidence. Then
choose the physical operation. `remove_content` answers how to change the DOCX safely; it does not by itself
authorize deletion.

| Semantic case | Required treatment before removal |
|---|---|
| protected content/structure | Preserve unless current-task evidence explicitly authorizes replacement or retirement |
| fill example/placeholder | Materialize the registered slot and migrate the fill responsibility before clearing visible example text |
| instruction | Migrate every sourced constraint, or explicitly record that none survives |
| generated mechanism | Preserve the live field/index/numbering mechanism; only disposable cached/example text may be removed |
| manual responsibility | Register the manual action/region; instruction text may be removed only after the responsibility survives elsewhere |
| unknown/unresolved region | Obtain more evidence or preserve it; do not destructively remove |

Manual/gap records belong to artifact decisions, not no-op mutation actions. If responsibility moves to a new
automatic slot, `materialize_slot` appears earlier and removal references that target.

## Choose the smallest safe mode

| Mode | Use when | Required preservation check |
|---|---|---|
| `clear_text_preserve_container` | Visible text is disposable but paragraph/cell/container carries layout | Container, properties, anchors, punctuation, and neighbors remain |
| `remove_paragraph` | Entire paragraph has no surviving responsibility | Numbering, adjacent paragraphs, pagination, and section boundaries remain valid |
| `remove_table_row` | Entire row is disposable | Grid, merges, row ordering, and neighboring rows remain valid |
| `remove_table` | Entire table is disposable | Surrounding anchors, paragraphs, sections, and relationships remain valid |
| `remove_bounded_block` | Continuous logical block has unique start/end boundaries | Both boundaries and all outside fingerprints remain unchanged |
| `remove_shape` | One uniquely identified shape/text box is disposable | Other drawing relationships, anchors, z-order, and nearby content remain |

Do not target repeated text alone. Query every candidate, compare context/effective style, and use the current
snapshot's execution locator plus expected fingerprint. Split heterogeneous changes into separate operations so
comparison can account for each one.

## Materialize stable slots

An automatic slot must have:

- a registered Registry `field_id` compatible with the content type;
- a unique template-scoped `slot_id`;
- a current execution locator for safe mutation;
- `w:alias = field_id` and `w:tag = slot_id`;
- a persistent artifact locator that later resolves by content-control tag under the final template hash;
- independent required/cardinality and expected value style.

`materialize_slot` preserves the container and current visible content and does not insert placeholder text.
Example/instruction cleanup is a later `remove_content` operation.

Use component locators for one semantic slot represented by several physical elements. Use bounded start/end
locators for paragraph streams. Never use page number, temporary object ID, or an unconstrained paragraph index
as the only artifact identity.

## Manual, gap, and unregistered fields

Use manual when responsibility is known but safe automatic placement is unavailable. Use gap when current
materials do not establish a value, rule, scope, or target. Use unresolved when evidence conflicts and no
current precedence resolves it.

Do not invent a `field_id`. A required automatic slot with no registered field blocks build; otherwise record
the region in the build report with an explicit manual/gap/unresolved disposition.

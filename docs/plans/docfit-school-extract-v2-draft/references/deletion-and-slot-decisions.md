# Deletion and slot decisions

Use this reference after observation has produced a current snapshot and stable target candidates.

## Select the smallest safe deletion

| Mode | Use when | Required preservation check |
|---|---|---|
| `clear_text_preserve_container` | The text is disposable but its paragraph/run container carries layout or style | Container, properties, anchors, and neighboring content remain |
| `remove_inline_fragment` | A precise phrase inside mixed content is disposable | Surrounding runs, spacing, fields, and punctuation remain coherent |
| `remove_container` | The entire addressed paragraph/row/container has no surviving responsibility | Adjacent structure, numbering, pagination, and section boundaries remain valid |
| `remove_bounded_block` | A continuous logical block is disposable and has stable start/end boundaries | Both boundaries and outside content match expected fingerprints |
| `clear_cell_preserve_grid` | Cell content is disposable but the table layout is reusable | Grid, row height, cell properties, merges, and neighboring cells remain |
| `unwrap_control_preserve_content` | The wrapper is disposable but approved inner content must remain | Inner content, order, formatting, and anchors remain |

Do not use text alone when it appears more than once. Query all candidates, compare context and effective
formatting, and choose a stable object reference from the current snapshot. Include expected text or a
fingerprint so stale state fails closed.

Use `remove_bounded_block` only when the intended logical unit is continuous and both boundaries are
unambiguous. Split heterogeneous changes into separate operations so comparison can account for each one.

## Materialize slots without flattening responsibility

Choose the content kind from downstream behavior:

- `scalar`: one bounded value such as a title, author, identifier, or date;
- `paragraph_stream`: a variable sequence of paragraphs with controlled boundaries;
- `composite`: structured content whose internal objects or generation behavior must be preserved.

Record cardinality independently of the number of examples in the source template. `min: 0` expresses an
optional slot. An absent `max` expresses an unbounded repeated responsibility only when the evidence supports
that conclusion.

For a slot, preserve or create the smallest physical anchor that safely expresses the semantic boundary:

- an existing paragraph or run container;
- a table cell while retaining the grid;
- a start/end boundary for a paragraph stream;
- a content control, bookmark, or other uniquely resolvable anchor supported by the Tool.

## Manual regions and gaps

Use a manual region when the desired responsibility is known but placement requires human judgment or
cannot be uniquely automated. Include the affected region and the required action.

Use a gap when the current materials do not establish the responsibility, required value, scope, or safe
target. A gap is not an empty slot and must not be silently filled from convention.

An automatic slot is invalid if it is ambiguous, resolves to multiple objects, depends on a stale snapshot,
or cannot preserve its required container behavior. Downgrade it to manual/unresolved or obtain more evidence.

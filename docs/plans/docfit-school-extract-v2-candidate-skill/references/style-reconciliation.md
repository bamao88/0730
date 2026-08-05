# Style reconciliation

Use this reference when a written requirement, visible example, style label, and actual Word formatting do
not obviously agree.

## Observe effective formatting

For each semantic role, collect the applicable facts rather than relying on a style name:

- named style and its definition;
- based-on inheritance chain;
- direct run and paragraph formatting;
- numbering/list properties;
- table, cell, section, header, or footer properties when relevant;
- the final effective values resolved by the observation Tool;
- scope: the exact object, region, or logical role to which each value applies.

“标题” may appear in several places and may be text, a style name, or an instruction. Query all matching
candidates with surrounding context, style resolution, and visual location. The Tool supplies facts; the Agent
identifies the semantic title role.

## Reconcile claims property by property

Do not treat an entire style as one indivisible winner. Compare font family, size, weight, alignment,
indentation, spacing, line spacing, numbering, pagination behavior, and other relevant properties separately.

For every property, record one of:

- `observed`: effective value exists in the template;
- `required`: an authoritative current-task source states a target value;
- `aligned`: observed and required values agree;
- `conflict`: both exist and disagree;
- `unresolved`: the applicable value or scope cannot be established.

An authoritative written requirement may define the target, while the template observation explains the
physical implementation. Preserve both provenance paths. Never fill an absent value from a previous school,
general formatting knowledge, or a style name alone.

## Decide when to ask

Ask the user when a conflict changes a reusable fixed region, a high-impact semantic role, or the appearance
of many downstream documents and no explicit precedence rule resolves it.

If the conflict is non-blocking and can be represented without choosing, keep both claims and mark it in the
artifact. Freeze must remain blocked when downstream filling cannot be safe without a single resolved value.

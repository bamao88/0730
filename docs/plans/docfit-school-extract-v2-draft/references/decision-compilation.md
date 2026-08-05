# Decision compilation

Use the bundled scripts to turn Agent-authored semantic decisions into canonical, versioned Tool inputs.
The scripts make a decision structurally executable; they do not decide whether it is semantically correct.

## Shared rules

- Resolve every script path relative to the active `SKILL.md`.
- Keep inputs and outputs in the current task work directory, never beside the source template.
- Include `schema_version`, current snapshot/hash, stable decision IDs, rationale, and evidence refs.
- Write decisions in YAML or JSON for review; consume the canonical JSON emitted by the script.
- On any error, correct the decision input or obtain new evidence. Do not hand-edit canonical output to
  bypass validation.
- Compiler output is not trusted by Tools. Every consuming Tool validates schema, refs, and preconditions
  again.

## Mutation decisions

`mutation-decisions.yaml` records what the Agent has decided, not a free-form cleanup request. Each entry
contains:

- unique decision and operation IDs;
- current `snapshot_ref` and target ref;
- current `observed_roles`, surviving responsibilities, and `resolution`;
- for each responsibility, `kind: fixed | fill | generate`, required content kind for fill/generate,
  cardinality, optional condition, and `handling: automatic | manual`;
- expected text/fingerprint;
- `action: materialize_slot | register_manual_region | remove_content`; preserving a target emits no
  mutation operation;
- only for `remove_content`, one supported `removal_mode`;
- migration destination refs for every responsibility carried by removed instructions/examples, or an
  explicit empty surviving-responsibility decision with evidence and rationale;
- complete slot semantics when materializing a slot;
- rationale and supporting observation/source refs.

Run `compile_mutation_plan.py` to produce `mutation-plan.json`. Compilation rejects duplicate IDs, unknown
modes, incomplete slot semantics, cross-snapshot refs, and page/bbox/bare text used as edit identity. It also
rejects `repeat`, `conditional`, `manual`, `remove`, or `unresolved` used as a responsibility kind;
`removal_mode` on a non-removal action; removal without a mode; destructive removal of unresolved content;
removal whose surviving responsibilities have no migration destination; and removal of fixed content without
an explicit current-task authorization plus a decision that replaces, migrates, or retires that fixed
responsibility.

## Review decisions

After `template_compare`, write one decision for each required finding or image group:

- comparison finding/image refs;
- after snapshot/hash;
- `accepted`, `blocking`, or `needs_edit`;
- concise visual/semantic reason;
- affected pages or section when applicable.

Run `compile_review_record.py` to produce `review-record.json`. Compilation rejects missing required image
judgments, hash mismatch, silently cleared blocking findings, or final-page coverage assembled from different
snapshots. The script records the Agent judgment; it does not make the judgment.

## Artifact decisions

The final semantic inventory contains sources, fixed regions, slots, manual regions, gaps, style
observations/requirements/conflicts, unresolved items, and the final review record. Every ref belongs to the
same final snapshot.

Run `compile_artifact_spec.py` to produce `artifact-spec.json`. Compilation rejects duplicate slot IDs,
missing content kind/cardinality/responsibility, untraceable sources, implicit manual/gap regions, stale refs,
or a review record for another hash.

`template_build` validates this spec again and produces only a candidate. `template_freeze` independently
reopens the candidate and sources; script success has no bearing on frozen status.

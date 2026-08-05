# Decision compilation

Use the two bundled scripts to turn two Agent-authored decision files into canonical, versioned Tool inputs.
One compiler protects the DOCX mutation boundary; the other protects the candidate build boundary. The
scripts make a decision structurally executable; they do not decide whether it is semantically correct.

## Shared rules

- Resolve every script path relative to the active `SKILL.md`.
- Keep inputs and outputs in the current task work directory, never beside the source template.
- Pass the current task root explicitly with `--task-root`; pass every input/output path explicitly.
- Include `schema_version`, current snapshot/hash, stable decision IDs, rationale, and evidence refs.
- Write decisions in YAML or JSON for review; consume the canonical JSON emitted by the script.
- On any error, correct the decision input or obtain new evidence. Do not hand-edit canonical output to
  bypass validation.
- Compiler output is not trusted by Tools. Every consuming Tool validates schema, refs, and preconditions
  again.
- Exit `0` on success, `2` on decision/schema errors, and `1` on environment/I/O failures. A failed run
  leaves an existing valid output byte-for-byte unchanged and creates no partial output.

## Mutation decisions

`mutation-decisions.yaml` records what the Agent has decided, not a free-form cleanup request. Each entry
contains:

- unique decision and operation IDs;
- current `snapshot_ref` and target ref;
- current `observed_roles`, surviving responsibilities, and `resolution`;
- for each responsibility, `kind: fixed | fill | generate`, required content kind for fill/generate,
  cardinality, optional condition, and `handling: automatic | manual`;
- expected text/fingerprint;
- `action: materialize_slot | remove_content`; preserving a target, registering a manual region, or
  recording a gap emits no mutation operation;
- operation order is executable order; `depends_on` may reference only an earlier operation, and a removal
  cannot precede the slot or existing target that receives its surviving responsibility;
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
responsibility. Cyclic/forward operation dependencies and migration targets that do not already exist or
come from an earlier operation are rejected.

## Artifact decisions and embedded review record

Write `artifact-decisions.yaml` only after the final snapshot is confirmed. It contains:

- sources, fixed regions, slots, manual regions, gaps, unresolved items, and style
  observations/requirements/conflicts;
- `final_snapshot_ref` and the complete mutation/comparison evidence chain from source to final snapshot;
- for each mutation review, its mutation/comparison refs and Agent disposition;
- the final-review `comparison_ref` bound to the exact final snapshot;
- one Agent `disposition: accepted | blocking | needs_edit` and concise reason for every required finding or
  image group, including affected pages/section where applicable.

Long-document image groups are read through the comparison cursor until `next_cursor` is absent. Record refs
and dispositions, not copied image bytes or duplicated comparison payloads.

Run `compile_artifact_spec.py` to produce `artifact-spec.json`. The compiler resolves immutable evidence refs,
constructs a typed `ReviewRecordV1` internally, validates it, and embeds the normalized `review_record` in the
artifact spec. It does not emit `review-decisions.yaml` or `review-record.json`.

Compilation rejects duplicate slot IDs, missing content kind/cardinality/responsibility, untraceable sources,
implicit manual/gap regions, stale refs, incomplete mutation lineage, missing required image judgments, hash
mismatch, silently cleared machine-blocking findings, or final-page coverage assembled from different
snapshots. Tool facts use `machine_blocking`; an Agent `accepted` disposition cannot clear that property. The
compiler records Agent judgment but never makes the judgment.

`template_build` validates this spec again and produces only a candidate. `template_freeze` independently
reopens the candidate and sources; script success has no bearing on frozen status.

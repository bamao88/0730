# Decision compilation

Use the two bundled scripts to turn Agent-authored decision files into canonical, versioned Tool inputs. One
compiler protects DOCX mutation; the other protects the single artifact build. The scripts make a decision
structurally executable; they do not decide whether it is semantically or visually correct.

## Shared rules

- Resolve scripts relative to the active `SKILL.md`.
- Keep decisions and compiled outputs in the current task `work/` directory, never beside source inputs.
- Pass `--task-root`, `--input`, and a new unused `--output` explicitly.
- Include schema version, current snapshot/document hash, Registry ID/version/hash, stable IDs, rationale, and
  evidence refs.
- Write reviewable YAML/JSON decisions; only pass compiler-produced canonical JSON to Tools.
- Correct invalid decisions or collect new evidence. Never hand-edit canonical output to bypass validation.
- Tool consumers independently revalidate schema, digest, refs, Registry, document facts, and preconditions.
- Exit `0` on success, `2` on input/decision errors, and `3` on environment/I/O failures. Failure creates no
  partial output and never overwrites an existing target.
- After any decision change, compile to a new attempt path. Apply the same rule to mutate/build outputs.

## Mutation decisions

`mutation-decisions.yaml` contains:

- current snapshot/document hash and Registry binding;
- unique decision/operation IDs and task-local execution locators;
- responsibility `kind: protected | fill | generate`, content type, required/cardinality, condition, and
  automatic/manual handling;
- `materialize_slot` with registered `field_id`, stable `slot_id`, and
  `w:alias=field_id`/`w:tag=slot_id`;
- `remove_content` with one supported physical mode and either complete responsibility migration or precise
  current-task deletion authorization;
- operation order, expected post-state, rationale, and evidence refs.

Compilation rejects duplicate IDs, unknown fields/modes, cross-snapshot refs, page/bbox/bare text used as edit
identity, mismatched marker identity, forward/cyclic dependencies, deletion without authorization, and removal
before the target receiving surviving responsibility exists.

## Artifact decisions and review

Write `artifact-decisions.yaml` after selecting the final snapshot. It contains:

- Registry/marker binding and source hashes;
- protected/slot/remove regions;
- each automatic slot's `field_id`, `slot_id`, content type, required/cardinality, execution locator, persistent
  artifact locator, marker, and expected value style;
- manual/gap/unresolved records and blocking status;
- style observations, requirements, sources, conflicts, and resolution;
- complete mutation/comparison lineage;
- final `candidate_verification` comparison bound to the exact final template hash;
- an Agent disposition for every required image/finding.

Read long-document image groups through the comparison cursor until `next_cursor` is absent. Record refs,
hashes, and dispositions, not image bytes or copied comparison payloads.

`compile_artifact_spec.py` resolves evidence, builds `ReviewRecordV1`, constructs a
`docfit-template-fill-contract/v1` model, and embeds both in `artifact-spec.json`. It rejects unregistered fields,
duplicate slots, task-local refs used as persistent locators, implicit manual/gap items, blocking unresolved
items, stale lineage, missing page/image dispositions, hash mismatch, and attempts to clear a machine blocker
with an Agent `accepted` disposition.

`template_build` independently reopens sources, Registry, evidence, and the final DOCX. Script success has no
bearing on `artifact_status: built`.

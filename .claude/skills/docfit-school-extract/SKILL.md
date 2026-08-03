---
name: docfit-school-extract
description: Analyze the school templates, written requirements, official examples, and user confirmations supplied for the current thesis task. Use this Skill whenever the user asks what a thesis template requires, wants template slots or instruction text identified, needs conflicting school sources compared, or wants traceable formatting evidence prepared for a conversion. Produce task-scoped evidence only, never a persistent school package or product Knowledge update.
---

# DocFit School Extract

Interpret only the school materials supplied for the current task. Use universal DocFit
Knowledge for concepts and methods, and return traceable facts, conflicts, uncertainties,
applicability, and candidate Tool parameters that expire with the task.

## Keep school evidence task-scoped

- Record a source hash and evidence location for every school-specific conclusion.
- Distinguish observed facts from interpretations, unresolved conflicts, and user
  confirmations.
- Keep school names, templates, exact values, fixed wording, slots, and extracted
  conclusions out of product Knowledge and out of reusable profiles.
- Do not create a school directory, school package, `format-profile.yaml`, publication
  request, or automatic Knowledge promotion.
- Leave unsupported or unconfirmed matters unknown. Do not fill gaps from prior tasks,
  filenames, or universal examples.

## Inspect and interpret current materials

Use `mcp__docfit__docx_inspect` for objective template structure, effective styles,
visible objects, slots, instruction text, source hashes, risks, and opaque refs. Use
`mcp__docfit__docx_render` and `mcp__docfit__docx_visual_review` when layout, pagination,
position, or visual grouping matters. Choose only `baseline`, `edit_feedback`, or
`candidate_verification` as render intent; never select a backend or treat approximate
pages as Adobe PDF Services delivery evidence.

Select the smallest useful set of universal Knowledge documents by document ID. Each
selected logical module carries the product package version, content digest, and content.
Use it to recognize semantic roles, classify evidence, interpret conflicts, and describe
safe processing patterns. It cannot establish a school's actual rule.

Classify template text when evidence supports it:

```text
fixed_content       school wording that should remain
conditional_content wording whose presence depends on the current student/task
slot_placeholder    a location awaiting current student content
format_instruction  explanatory text that should not remain in a final thesis
```

If the classification is unsafe, preserve the text and record the uncertainty instead of
guessing or deleting it.

## Use optional read-only delegation

Analyze directly when the scope is simple, absent, mixed, or cheaper to keep in the main
context. When a bounded evidence-heavy range benefits from isolation, call the SDK
`Agent` Tool only with `subagent_type: docfit-unit-analyst`.

The Subagent inherits no parent conversation or hidden evidence. Put the analysis scope,
current document hash and refs, selected Knowledge module ID/version/digest/content,
current-task source refs, known rules, dependencies, and `requested_output:
unit_analysis_v1` directly in its prompt.

Require a return containing `status`, `confidence`, `findings`, `confirmed_rules`,
`uncertainties`, `dependencies`, `cross_unit_links`, `evidence_requests`, and
`proposed_operations`. The Subagent can inspect or read existing visual evidence only. It
cannot render, edit, validate, ask the user, call another Agent, or persist memory. Handle
missing evidence and cross-range merging in the main Agent.

Do not create fixed unit-to-Agent mappings, mandatory delegation rules, or page/object
thresholds. A composite front matter range can be analyzed as one scope without becoming
a new permanent thesis type.

## Return current-task evidence

Return a compact task artifact or response with:

```yaml
scope: current_task_only
sources:
  - sha256: ...
    location: ...
observed_facts: [...]
confirmed_rules: [...]
conflicts: [...]
uncertainties: [...]
applicability: [...]
template_text_classification: [...]
candidate_tool_parameters: [...]
evidence_requests: [...]
```

Candidate parameters are inputs for the current task's later Tool calls, not universal
defaults. If sources conflict or applicability is unclear, show both evidence paths and
ask the current user the smallest question needed to proceed.

Do not modify the template or thesis while performing extraction. If a Tool returns an
`error`, stale refs, unsupported visible objects, or untrustworthy render evidence, publish
no fabricated conclusion; report the exact capability or evidence gap.

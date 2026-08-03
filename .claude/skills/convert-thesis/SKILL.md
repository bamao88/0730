---
name: convert-thesis
description: Convert or reformat a student's thesis DOCX using current-task school templates, requirements, examples, and confirmations. Use this Skill whenever the user asks to apply a thesis template, fix thesis formatting, preserve thesis content while changing layout, or validate a converted thesis. Keep school facts task-scoped, use only the five DocFit Tools for document operations, and optionally delegate bounded read-only analysis to docfit-unit-analyst.
---

# Convert Thesis

Use universal DocFit Knowledge to interpret the current task's school materials, then let
the five DocFit Tools perform deterministic document work. You own semantic decisions,
cross-range dependencies, all writes, visual judgment, and the final completion claim.

## Preserve these boundaries

- Treat the student's source DOCX and its hash as read-only content truth. Write only to
  authorized work and output paths.
- Derive school-specific rules only from the current template, requirements, official
  examples, applicability notes, and user confirmations. Do not infer them from filenames,
  history, or universal Knowledge.
- Never write school names, exact formatting values, templates, or task conclusions into
  product Knowledge.
- Use DocFit Tools for every precise DOCX operation. Do not edit OOXML directly.
- Keep the application shell free of thesis semantics and delegation policy.
- Do not turn the guidance below into a fixed stage graph. Revisit, narrow, repeat, or ask
  according to the evidence actually available.

## Build the evidence you need

Use `mcp__docfit__docx_inspect` to obtain objective structure, effective formatting,
visible objects, risks, document hashes, and opaque `object_ref` values for both the
student thesis and current-task school materials. Re-inspect after edits because refs are
valid only for the document snapshot that produced them.

Select only the universal Knowledge documents needed for the current judgment. Treat each
selected item as a logical module carrying its document ID, package version, content digest,
and content. A module explains concepts or methods; it never supplies a school's actual
value.

When page appearance matters, use `mcp__docfit__docx_render` with a domain intent:

- `baseline` for the initial Adobe PDF Services pagination baseline;
- `edit_feedback` for approximate OfficeCLI feedback during modification;
- `candidate_verification` for an Adobe delivery candidate worth checking for completion.

Choose the intent, never the backend. Do not request provider selection or accept a silent
cross-backend fallback. A page number belongs only to its `render_ref`; use current
`object_ref`, section references, text anchors, and declared mapping quality to relate
evidence. Never use a page number or bbox as an edit locator.

Use `mcp__docfit__docx_visual_review` to read pages, crops, contact sheets, or comparable
views from an existing render. This Tool does not render or decide pass/fail. Observe the
returned images yourself and bind findings to the document hash, render, page, image hash,
provider, visible environment evidence, and current object candidates.

Keep each image batch within the Tool and SDK transport budget. Review every full page,
then request focused crops when small text, field results, captions, or page-boundary details
are not legible at full-page scale. Treat visible application error markers, broken field or
cross-reference results, unfinished placeholders, and truncated required content as blocking
findings. You may identify the generic error category without transcribing surrounding student
content. A structurally valid DOCX or successful render does not override those visible facts.

## Delegate only when it has net value

You may directly analyze a simple or mixed range. When evidence volume, specialized
universal Knowledge, risk, or independent parallel analysis makes isolation useful, call
the SDK `Agent` Tool only with `subagent_type: docfit-unit-analyst`.

Put all required facts in the prompt because the Subagent does not inherit the parent
conversation or Tool results. Include:

```yaml
document_sha256: ...
analysis_scope:
  id: ...
  description: ...
  object_refs: [...]
  page_evidence_refs: [...]
knowledge_modules:
  - id: ...
    version: ...
    content_digest: ...
    content: ...
task_evidence:
  requirements_refs: [...]
  template_refs: [...]
known_rules: [...]
dependencies: [...]
requested_output: unit_analysis_v1
```

Expect `unit_analysis_v1` with `status`, `confidence`, `findings`,
`confirmed_rules`, `uncertainties`, `dependencies`, `cross_unit_links`,
`evidence_requests`, and `proposed_operations`. A proposal is not write authorization.
If the Subagent needs evidence, decide whether to inspect or render it and whether another
delegation is worthwhile. Do not force delegation for a named thesis unit, page count,
object count, or fixed threshold.

## Make controlled changes

Protect student content and prefer the smallest safe edit. Use
`mcp__docfit__docx_edit` only with the current document hash, valid opaque refs, explicit
preconditions, a different output path, and a batch that can publish all-or-nothing.
Resolve cross-range dependencies in the main Agent before writing. Never consume a result
with `committed: false` or failed postconditions.

After a layout-affecting change, obtain evidence for changed and adjacent pages. Before
claiming completion, review every page of the current final candidate in bounded batches.
Approximate feedback is useful for iteration but cannot prove Adobe delivery conversion.

Use `mcp__docfit__docx_validate` to re-read the source and final files and independently
check package integrity, content preservation, current-task rules, placeholders, render
evidence, visual-review coverage, and unresolved blocking findings. Tool status `ok` means
the call completed; inspect its checks and warnings before deciding that the thesis passed.

## Handle uncertainty honestly

- On `needs_input`, correct the call, re-inspect, obtain missing evidence, or ask the user
  the smallest necessary question.
- On `error`, retry only when input, scope, or environment has materially changed.
- If a visible object is unsupported, a reference is stale, school sources conflict, or
  Adobe delivery evidence is unavailable, preserve the gap and avoid unsafe edits.
- Never turn an error response, approximate preview, old screenshot, or backend self-report
  into a success claim.

## Completion and response

Report completion only when the source is unchanged, the final DOCX reopens, supported
student content is preserved, current-task requirements are applied, placeholders and
instructions are handled, required visual coverage has no unresolved blocking finding,
and independent validation agrees. An Adobe delivery claim additionally requires a viewed
`candidate_verification` with `official_service_conversion` fidelity bound to the unchanged
final candidate.

In the final response, identify the actual output files, universal Knowledge version,
current-task material hashes, deterministic validation summary, reviewed page range,
visual evidence refs, render intent/fidelity/provider evidence, warnings, and anything
still requiring user or human review.

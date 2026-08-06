# DocFit Agent Guidance

## Durable project truth

- `docs/docfit-00-index.md` through `docs/docfit-06-development-roadmap.md`
  jointly form DocFit's long-term development baseline.
- Treat those seven documents as one coordinated contract. Architecture,
  directory layout, Skill/Knowledge/Tool/Eval boundaries, test strategy,
  milestone scope, and implementation must not contradict them.
- Before changing architecture, project layout, a public Tool or CLI contract,
  test tiers, or milestone scope, read `docs/docfit-00-index.md` and every
  affected document in 01–06.
- When an approved design or implementation change alters a documented claim,
  update every affected long-term document in the same change. Do not leave
  code ahead of the docs or silently work around a conflict.
- If the long-term documents disagree with each other or with the requested
  implementation, stop and reconcile the contract before coding.
- `docs/status/active/**` is compact execution state only. It may link to the
  long-term baseline but must not override it.

## Durable agent memory

- This file is the shared project-local startup memory for coding agents.
  `CLAUDE.md` imports it instead of maintaining a second copy.
- Keep stable rules and pointers here; keep current milestone evidence and
  temporary blockers in `docs/status/active/**`.
- There is currently no project Serena or gbrain memory store. Do not claim
  memory was synchronized to one unless it is actually configured and checked.

## User collaboration profile

- The user is a product manager and founder, and is the combined product and
  technical decision owner. The user understands product, business, and Agent
  systems well, but is not a programmer and is less familiar with traditional
  software-development implementation details.
- Give the user serious, professional technical material at its natural level.
  Do not dilute implementation details, architecture, failure modes, or evidence
  or rely on overly simplified analogies; the user can work with technical depth.
- In technical decisions, task summaries, reviews, and ordinary answers, add the
  relevant software-engineering system view and the key product-decision view.
  Help the user see effects on user value, scope, maintainability, architecture,
  delivery risk, operating cost, reversibility, and future options.
- Communicate as a CTO reporting to a CEO: explain the available choices,
  tradeoffs, and consequences first, then the recommended implementation path.
- Keep this additional perspective decision-useful rather than generic. Separate
  established facts, the technical recommendation, and the wider product/
  engineering implications when that distinction improves the decision.

## Collaboration and delivery discipline

- During plan or design discussion, remain read-only. Do not modify code,
  documentation, configuration, tests, generated artifacts, or repository state
  until the user explicitly asks to implement or make the change.
- After an implementation change is verified usable, immediately stage only the
  task-scoped changes, create a commit, and push the current branch. Never include
  unrelated pre-existing working-tree changes. If commit or push cannot complete,
  report the exact blocker and the remaining repository state.
- Before implementing any Agent-related fix or new capability, first locate the
  local Claude Agent SDK docs directory and read the relevant official SDK
  documentation. This is mandatory because the SDK evolves faster than model
  training knowledge. Project documents, installed type definitions, and memory
  are supplementary evidence, not substitutes for the relevant official docs.
  If the local docs directory or the relevant official documentation is missing,
  stop before coding and report the documentation gap to the user.

## Current execution boundary

- The canonical milestone contract is
  `docs/docfit-06-development-roadmap.md`.
- M0, the Provider-independent universal Knowledge Package v1, P1, M1, and M2 are
  verified. The current product-development scope is complete at the M2 `docfit convert`
  chain, including the non-Eval safety, evidence, and reporting support required by that
  chain.
- The frozen M2 baseline is recorded in the active development capsule. The post-M2 O0.0–O0.7
  privacy-safe runtime-observability prerequisite is complete; the documented next
  conversion-behavior direction is the separate O1 optimization slice, which has not started
  and is not an M3 completion claim. Before starting O1, preserve the observability contract in
  `conversion-report.json`, keep the existing deterministic and live product gates, and give
  the optimization one measured target. Ordinary unit, contract, integration, doctor, and live
  smoke gates are not M3 Eval and remain required.
- M3 Eval expansion, authorized/deidentified real-sample qualification, Gold work, and
  external manual review are explicitly outside the current development scope. Keep M3 as
  a future milestone in `docs/docfit-06-development-roadmap.md`; do not claim that it passed,
  and do not treat its deferred gates as blockers for the completed current plan. A new
  user-approved plan is required before resuming that work.
- Use `$doc-keeper` or an equivalent focused drift check after changes that may
  invalidate claims in 00–06.

## Setup and verification

```bash
uv sync --frozen
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
```

Current cumulative live Agent proof additionally requires:

```bash
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit agent-smoke --case path-tools
uv run docfit agent-smoke --case subagent
uv run docfit doctor --require agent-smoke
```

Keep API credentials only in the repository-external
`~/.config/docfit/agent.env` with mode `0600`. Never print, commit, or copy
credential values into project docs, tests, logs, or examples.

The fixed document backends are OfficeCLI 1.0.143 for inspect/edit/validate/edit feedback
and Adobe PDF Services (`pdfservices-sdk==4.2.0`) for baseline/candidate DOCX-to-PDF.
Delivery conversion must not depend on local Microsoft Word, AppleScript, GUI session
state, or local fonts. An Adobe cache miss consumes one Document Transaction; cache hits
must not repeat the API call. Treat Adobe's font environment as service-managed and opaque.
Adobe conversion uploads the complete authorized DOCX to the external service; never send
an input that is outside the current task authorization or log its document body.

## Working rules

- Preserve the five public `mcp__docfit__...` Tool names and the default-deny
  boundary for unmatched tools unless the long-term contract is explicitly revised.
- The main Agent may use path-bounded Read/Glob/Grep for project Skill references,
  product Knowledge, and the current task input/work/output roots after canonical path
  checks. It also receives trusted, auto-approved Bash and Write with no DocFit path
  gate; those tools can access any resource available to the Agent process, including
  paths and environment values outside the direct Read allowlist. This is an explicit
  trust decision, not a sandbox claim. Never print credentials or document bodies in
  logs. `docfit-unit-analyst` does not inherit Bash, Write, or the main Agent file tools.
- Communicate decisions directly and concretely. State fixed responsibilities and
  observable behavior first; do not complicate settled facts with speculative
  implementation details, unnecessary fallback scenarios, or invented status terms.
  Prefer wording such as "this Tool call fails and publishes no output" over abstract
  statements such as "the system must stop."
- Keep the product Knowledge Package universal and product-shipped. School
  requirements, templates, formatting parameters, and extracted conclusions
  remain current-task evidence and must never be auto-promoted to Knowledge.
- The conversion behavior keeps source documents read-only and uses authorized task
  directories for work/output; completion rechecks the source hash. This is a product
  rule for the trusted main Agent, not a Bash/Write filesystem sandbox.
- Do not add a second Agent loop, workflow engine, question protocol, or
  speculative Provider abstraction.
- Treat XML-like host control envelopes as orchestrator metadata unless the
  user also provides natural-language stop or redirect intent.

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

## Current execution boundary

- The canonical milestone contract is
  `docs/docfit-06-development-roadmap.md`.
- M0 and the Provider-independent universal Knowledge Package v1 are the
  currently implemented foundation. Do not enter M1 or later work without a
  newly approved Preflight.
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

Live M0 proof additionally requires:

```bash
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit doctor --require agent-smoke
```

Keep API credentials only in the repository-external
`~/.config/docfit/agent.env` with mode `0600`. Never print, commit, or copy
credential values into project docs, tests, logs, or examples.

## Working rules

- Preserve the five public `mcp__docfit__...` Tool names and the default-deny
  permission boundary unless the long-term contract is explicitly revised.
- Keep the product Knowledge Package universal and product-shipped. School
  requirements, templates, formatting parameters, and extracted conclusions
  remain current-task evidence and must never be auto-promoted to Knowledge.
- Source documents are read-only; work and output files use authorized task
  directories.
- Do not add a second Agent loop, workflow engine, question protocol, or
  speculative Provider abstraction.
- Treat XML-like host control envelopes as orchestrator metadata unless the
  user also provides natural-language stop or redirect intent.

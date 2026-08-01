# DocFit Agent SDK

DocFit is a permission-bounded Claude Agent SDK application for thesis-formatting
workflows. The Agent runtime remains at the completed **M0** boundary: it establishes an
installable Python package, a CLI, SDK and Skill discovery boundaries, five registered
DocFit Tool names, a real image smoke path, deterministic tests, and CI. A separately
approved post-M0 slice also implements the Provider-independent, product-shipped universal
Knowledge Package v1 loading and integrity boundary.

Real DOCX inspection, editing, rendering, validation, the fixed OfficeCLI / local Word
API adapters, current-task school evidence handling, and the `convert` workflow
begin in later milestones.

## Requirements

- Python 3.12 (pinned by `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- A Kimi Code or MiniMax API key only for live Agent SDK smoke checks

## Install and verify

```bash
uv sync --frozen
uv run ruff check .
uv run mypy src
uv run pytest
uv run docfit doctor
```

`docfit doctor` is the deterministic CI gate. Missing API credentials, fixed DOCX
backend configuration, or fonts are reported as `NOT_READY` but do not make that base
command fail.

## Live M0 smoke checks

Keep all local API credentials in one repository-external file:
`~/.config/docfit/agent.env`. The file must have mode `0600`; never add it to
this repository. DocFit tries every configured Kimi credential first, then
falls back to MiniMax. Process environment variables override values from the
file when a one-off local override is needed.

```dotenv
DOCFIT_AGENT_BACKEND_ORDER=kimi,minimax

DOCFIT_KIMI_API_KEY=...
DOCFIT_KIMI_API_KEY_2=...
DOCFIT_KIMI_API_KEY_BACKUP=...
DOCFIT_KIMI_BASE_URL=https://api.kimi.com/coding/
DOCFIT_KIMI_MODEL=kimi-for-coding

DOCFIT_MINIMAX_API_KEY=...
DOCFIT_MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic
DOCFIT_MINIMAX_MODEL=MiniMax-M3

# Future provider keys may be kept in this same local file.
```

After creating or editing the file:

```bash
chmod 600 ~/.config/docfit/agent.env
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit doctor --require agent-smoke
```

The three cases verify that the Agent can inspect an actual MCP Tool image, can route
`AskUserQuestion` through the CLI within the same session, and cannot execute hidden or
unregistered tools. Receipts under `.docfit/smoke/` contain metadata only and record
which backend passed; they never contain API keys.

`docfit doctor --require provider` is reserved for M1 and is expected to report
`NOT_READY` during M0.

## Test layout

- `tests/unit`: pure local logic, including bundled universal Knowledge validation
- `tests/contract`: public Tool names, schemas, and SDK permission boundaries
- `tests/integration`: CLI, real SDK, OfficeCLI, local Word API, and end-to-end integration

The coordinated long-term development baseline starts at
[`docs/docfit-00-index.md`](docs/docfit-00-index.md); the accepted milestone
contract is in
[`docs/docfit-06-development-roadmap.md`](docs/docfit-06-development-roadmap.md).

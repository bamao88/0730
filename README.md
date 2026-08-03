# DocFit Agent SDK

DocFit is a permission-bounded Claude Agent SDK application for thesis-formatting
tasks. It now includes the product-shipped universal Knowledge Package v1, two domain
Skills, one SDK-native read-only `docfit-unit-analyst`, five real DOCX Tools, fixed
OfficeCLI / Adobe PDF Services adapters, a thin `convert` product command, and a bounded core
Eval runner. The current product-development scope is complete through M2; M3 Eval expansion,
real-sample qualification, Gold, and external manual review are deferred future work.

The implemented P1 architecture is documented in
[`docs/plans/docfit-progressive-subagents.md`](docs/plans/docfit-progressive-subagents.md):
two domain Skills (`docfit-school-extract` and `convert-thesis`), one modular universal
Knowledge Package, five DocFit MCP Tools, and one SDK-wiring-level read-only
`docfit-unit-analyst`. Delegation remains a Skill-guided Agent decision; the application
shell only enforces context isolation and permissions. The five Tool names remain the only
Agent-visible document surface; no second workflow or Provider-selection layer is added.

## Requirements

- Python 3.12 (pinned by `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- OfficeCLI 1.0.143, Adobe PDF Services credentials, and Poppler for Provider gates
- A Kimi Code or MiniMax API key for live Agent SDK smoke checks and `docfit convert`

## Install and verify

```bash
uv sync --frozen
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
```

`docfit doctor` is the deterministic CI gate. Missing Agent/Adobe credentials or fixed
DOCX backend configuration is reported as `NOT_READY` but does not make that base command
fail. `docfit doctor --require provider` requires OfficeCLI, Adobe PDF Services SDK and
credentials, plus `pdftoppm`/`pdfinfo`.

## Live Agent smoke checks

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

# Adobe PDF Services service-principal bundle (never print or commit values).
DOCFIT_ADOBE_PDF_SERVICES_CLIENT_ID=...
DOCFIT_ADOBE_PDF_SERVICES_CLIENT_SECRET=...
DOCFIT_ADOBE_PDF_SERVICES_ORGANIZATION_ID=...
```

After creating or editing the file:

```bash
chmod 600 ~/.config/docfit/agent.env
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit agent-smoke --case subagent
uv run docfit doctor --require agent-smoke
```

The four cases verify that the Agent can inspect an actual MCP Tool image, can route
`AskUserQuestion` through the CLI within the same session, and cannot execute hidden or
unregistered tools. The Subagent case additionally proves that only the named read-only
Agent definition receives explicit task context, uses inspect + visual-review, and returns
`unit_analysis_v1`. Receipts under `.docfit/smoke/` contain metadata only and record
which backend passed; they never contain API keys. Starting a new runnable live attempt
invalidates that case's older PASS receipt, and only a PASS from the current attempt publishes
a new one. A command that is `NOT_READY` before any backend can run does not erase prior live
evidence; the doctor still checks current credentials and SDK version independently.

Provider installation and deterministic Tool checks:

```bash
uv run docfit doctor --require provider
uv run docfit tools inspect evals/fixtures/smoke/student.docx
```

The fixed render routes are OfficeCLI for `edit_feedback` and Adobe PDF Services for
`baseline` / `candidate_verification`. Adobe uses `pdfservices-sdk==4.2.0`; each conversion
on a cache miss consumes one Document Transaction (the development free tier is planned
against 500 transactions per month). DocFit does not require local Microsoft Word,
AppleScript, an unlocked GUI session, or a local font inventory for delivery conversion.
Adobe's server-side font environment is recorded as managed and opaque. A baseline or
candidate call uploads the complete authorized DOCX to Adobe's cloud service; do not run
that route on a document whose owner has not authorized external processing.

The locked Adobe adapter uses a 30-second connect timeout and a 120-second read/upload
timeout so real DOCX uploads are not constrained by the SDK's short defaults. These values
are evidence, not public backend-selection parameters. Public Tool schemas intentionally
avoid `oneOf` / `anyOf` / `allOf` because the configured compatible model routes do not
consume schema composition reliably. Action-specific requirements are still enforced by
the Tool runtime.

With `claude-agent-sdk==0.2.128`, the in-process MCP bridge does not preserve
`structuredContent` in the Agent-visible result. DocFit therefore mirrors the same complete
structured object as compact JSON in the first text block, followed by native image blocks.
The SDK subprocess buffer is 16 MiB, while the Tool retains its own image count and byte
budgets. Review long documents in bounded page batches; use crops from the same render ref
when small field results, captions, or page-boundary details are not legible at full-page
scale.

`uv run docfit eval --suite core` remains available as an optional bounded developer aid.
Expanding that runner into M3 Skill/E2E evaluation, Gold maintenance, real-sample
qualification, or manual delivery review is outside the current development scope and is not
a completion gate for the implemented M2 product chain.

The exploratory authorized real-sample run is retained only as historical engineering
evidence. It is not a current completion blocker and does not make M3 complete.

The public conversion command is:

```bash
uv run docfit convert \
  --input evals/fixtures/smoke/student.docx \
  --school-template evals/fixtures/smoke/school-template.docx \
  --school-requirements evals/fixtures/smoke/school-requirements.pdf \
  --output .tmp/smoke-output
```

A successful `conversion-report.json` is generated from the current Adobe candidate and the
independent final validation rerun. Intermediate Agent warnings or summaries are not replayed
as current completion facts.

## Test layout

- `tests/unit`: pure local logic, including bundled universal Knowledge validation
- `tests/contract`: public Tool names, schemas, and SDK permission boundaries
- `tests/integration`: CLI, real OfficeCLI, and thin conversion-shell integration; live SDK and
  Adobe API product gates are run separately with repository-external credentials

The coordinated long-term development baseline starts at
[`docs/docfit-00-index.md`](docs/docfit-00-index.md); the accepted milestone
contract is in
[`docs/docfit-06-development-roadmap.md`](docs/docfit-06-development-roadmap.md).

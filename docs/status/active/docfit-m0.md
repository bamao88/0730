# DocFit M0 Active Capsule

- Capsule status: DONE
- Source plan: `docs/docfit-06-development-roadmap.md`
- Latest user intent: execute and verify approved M0 only
- Current slice: M0 is complete; existing modules reside under their planned
  `app/` and `tools/` owners without compatibility shims
- Blocker fingerprint: none
- Last proven evidence: `uv sync --frozen`, lock check, build, ruff, strict mypy,
  21 tests, base doctor, all three live SDK smoke cases, and
  `docfit doctor --require agent-smoke` pass after relocation
- Completed batch: installable package and lock, CLI/doctor, permission-bounded SDK,
  project Skill, five Tool names, real image/AskUserQuestion/denied-tool smoke,
  Kimi→MiniMax Agent backend selection, one external `0600` environment file,
  tests, CI, README, migration asset inventory, repository scaffold, and canonical
  `app/` / `tools/` module ownership
- Live backend evidence: Kimi passed `image`, `ask-user`, and `denied-tools`;
  MiniMax remains the configured fallback
- Next action: no automatic continuation; prepare and approve an M1 Preflight
  before implementing real DOCX behavior
- Next proof: none for M0; the next proof contract belongs to the approved M1
  Preflight
- Stop condition: satisfied; stop before any M1 implementation
- No-touch scope: real DOCX behavior, DOCX Provider selection, School Knowledge,
  `convert`, and M1–M5
- Parked work: every capability listed in M1–M5

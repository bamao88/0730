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
- Next action: review and approve `docs/plans/docfit-m1-tools-v1.md`; do not execute
  M1 while its Preflight status is DRAFT
- Next proof: none for M0; the next proof contract is the draft M1 Preflight
- Stop condition: satisfied; stop before any M1 implementation
- No-touch scope: real DOCX behavior, OfficeCLI/local Word API adapters, product Knowledge and current-task school evidence,
  `convert`, and M1–M5
- Parked work: every capability listed in M1–M5

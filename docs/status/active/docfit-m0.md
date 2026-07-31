# DocFit M0 Active Capsule

- Capsule status: DONE
- Source plan: `docs/docfit-06-development-roadmap.md`
- Latest user intent: execute and verify approved M0 only
- Current slice: M0 deterministic and local Agent SDK product gates complete
- Blocker fingerprint: none
- Last proven evidence: Python 3.12; claude-agent-sdk 0.2.128; ruff, strict mypy
  and 21 tests pass; all three `.docfit/smoke/*.json` receipts pass;
  `docfit doctor --require agent-smoke` exits 0
- Completed batch: installable package and lock, CLI/doctor, permission-bounded SDK,
  project Skill, five Tool names, real image/AskUserQuestion/denied-tool smoke,
  Kimi→MiniMax Agent backend selection, one external `0600` environment file,
  tests, CI, README, and migration asset inventory
- Live backend evidence: Kimi passed `image` and `ask-user`; MiniMax passed
  `denied-tools` after the Kimi candidates returned non-passing SDK results
- Next action: stop; create and approve a separate M1 Preflight before development
- Next proof: none for M0
- Stop condition: satisfied; do not auto-enter M1
- No-touch scope: real DOCX behavior, DOCX Provider selection, School Knowledge,
  `convert`, and M1–M5
- Parked work: every capability listed in M1–M5

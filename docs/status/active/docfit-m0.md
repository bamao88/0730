# DocFit M0 Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/docfit-06-development-roadmap.md`
- Latest user intent: execute and verify approved M0 only
- Current slice: planned repository directory scaffold is being established before
  the existing M0 modules are relocated
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
- Next action: after the directory scaffold is accepted, adjust the existing M0
  module layout without changing public behavior, then rerun all M0 gates
- Next proof: directory-path consistency now; full deterministic and live M0 gates
  after the later module relocation
- Stop condition: finish the directory scaffold and stop before moving M0 code
- No-touch scope: real DOCX behavior, DOCX Provider selection, School Knowledge,
  `convert`, and M1–M5
- Parked work: every capability listed in M1–M5

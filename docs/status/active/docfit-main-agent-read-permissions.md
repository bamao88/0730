# DocFit Main-Agent File Permissions Active Capsule

- Capsule status: DONE
- Canonical contract: `docs/docfit-06-development-roadmap.md` section 6.7
- Completed slice: path-bounded main-Agent Read/Glob/Grep, trusted Bash/Write, and explicit progressive Skill references
- Main-Agent surface: Skill + Read/Glob/Grep + auto-approved Bash/Write + AskUserQuestion + approved Agent type + five DocFit Tools
- Subagent surface: inspect + visual-review only; no Skill, file tools including Write, Agent, user question, render/edit/validate, or Bash
- Capability proof: canonical Skill/Knowledge/current-task roots still gate direct Read/Glob/Grep; Bash/Write are auto-approved with no DocFit path hook and can access any process-accessible path/environment, so the direct Read allowlist is not a sandbox
- Deterministic proof: frozen sync, lock check, build, ruff, mypy, 312 pytest tests, and base doctor PASS on 2026-08-04
- Live proof: Kimi/Claude Agent SDK 0.2.128 case-v3 receipts freshly PASS for denied-tools and path-tools; path-tools executed Write in work/input/outside plus Bash while outside direct Read was denied. The later V2 visual migration invalidated image/subagent receipts, so overall `doctor --require agent-smoke` is now NOT_READY; that does not invalidate this capsule's read-permission evidence.
- Visual cost: no OfficeCLI or LibreOffice route invoked; zero renderer executions in this slice
- Blocker fingerprint: none
- Next action: none for this completed slice; O0.7 completed in its separate observability capsule, O1 has not started, and M3 remains deferred

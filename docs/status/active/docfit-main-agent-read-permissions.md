# DocFit Main-Agent Read Permissions Active Capsule

- Capsule status: DONE
- Canonical contract: `docs/docfit-06-development-roadmap.md` section 6.7
- Completed slice: path-bounded main-Agent Read/Glob/Grep plus explicit progressive Skill references
- Main-Agent surface: Skill + Read/Glob/Grep + AskUserQuestion + approved Agent type + five DocFit Tools
- Subagent surface: inspect + visual-review only; no Skill, file tools, Agent, user question, render/edit/validate, or Bash
- Path proof: canonical Skill/Knowledge/current-task roots allowed; outside task, `.env`, `.git`, credentials, missing paths, traversal, search-tree symlink, and escaping Skill-root symlink denied
- Deterministic proof: build, ruff, mypy, 299 pytest tests, and base doctor PASS on 2026-08-04
- Live proof: fresh Kimi/Claude Agent SDK 0.2.128 receipts PASS for image, ask-user, denied-tools, path-tools, and subagent; `doctor --require agent-smoke` PASS
- Provider cost: no OfficeCLI or Adobe route invoked; zero Adobe Document Transactions consumed by this slice
- Blocker fingerprint: none
- Next action: none for this completed slice; O0.7 completed in its separate observability capsule, O1 has not started, and M3 remains deferred

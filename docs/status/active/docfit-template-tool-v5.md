# Template Tool v5 Active Capsule

- Status: `COMPLETE`
- Canonical plan: [docfit-template-tool-v5.md](../../plans/docfit-template-tool-v5.md)
- User decision: complete the approved clean-break refactor in one coding run; do not preserve the v4 public template Tool contract.
- Root evidence: NJAU r29 showed inherited `Hyperlink` blue after direct color clearing, three parent/descendant batch overlap failures, wide-schema argument pollution, and Tool-owned fixed body semantics.
- Delivered contract: application-owned bounded orchestration; four semantic work-item Tools plus one visual-review Tool; action-partitioned edit batches; effective-format verification; normalized deletion; boundary-safe removal; idempotent page starts; fact-only structural feedback; short linked Skill references.
- Architecture boundary: Claude Agent SDK remains the Agent loop and Skill/runtime owner. DocFit owns focused document execution and mechanical feedback, not a second semantic workflow.
- Automated evidence: 124 focused Agent/workspace/v5 regressions pass; Ruff and strict Mypy pass for the changed source surface.
- Real evidence: NJAU r66 built the final template, reviewed all 13 LibreOffice-rendered pages as clean, and passed package/Registry/TOC audits. Microsoft Word then opened the exact r66 path, updated all fields, saved, closed, reopened, and retained a black, non-underlined, three-level TOC with dot leaders; Word's native pagination is 12 pages.
- Worktree rule: preserve inherited user changes and generated runs; stage only owned v5 paths/hunks.
- Product result: the Tool executes Word mechanics and returns facts; the Agent owns school-specific semantic completeness. No v4 compatibility surface is retained.

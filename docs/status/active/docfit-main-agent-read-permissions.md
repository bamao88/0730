# DocFit 主 Agent 文件权限 Active Capsule

- Capsule 状态: DONE
- 权威 contract: 根目录 `AGENTS.md` 和当前 Claude Agent SDK-native 架构指引
- 已完成切片: 路径有界的主 Agent Read/Glob/Grep、受信任 Bash/Write、显式渐进 Skill reference
- 主 Agent 能力面: Skill + Read/Glob/Grep + 自动批准 Bash/Write + AskUserQuestion + 已批准 Agent 类型 + 当前 DocFit Tool surface
- Subagent 能力面: 只有 inspect + visual-review；没有 Skill、包括 Write 在内的文件工具、Agent、用户问题、render/edit/validate 或 Bash
- 能力证据: canonical Skill/Knowledge/current-task root 仍限制直接 Read/Glob/Grep；Bash/Write 自动批准且没有 DocFit path hook，可访问进程可访问的路径和环境，所以直接 Read allowlist 不是 sandbox
- 确定性证据: frozen sync、lock check、build、ruff、mypy、312 个 pytest 测试和 base doctor 于 2026-08-04 PASS
- Live 证据: Kimi/Claude Agent SDK 0.2.128 case-v3 receipts 对 denied-tools 和 path-tools 最新 PASS；path-tools 在 work/input/outside 执行 Write 和 Bash，同时 outside 直接 Read 被拒绝。后续 V2 visual migration 使 image/subagent receipts 失效，所以整体 `doctor --require agent-smoke` 现在是 NOT_READY；这不影响本 capsule 的 read-permission 证据。
- 视觉成本: 未调用 OfficeCLI 或 LibreOffice route；本切片 renderer 执行次数为 0
- 阻塞指纹: 无
- 下一步: 本已完成切片无；O0.7 已在独立 observability capsule 完成，O1 未开始，M3 仍 deferred

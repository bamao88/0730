# DocFit LibreOffice 视觉证据 V2 Active Capsule

- Capsule status: IMPLEMENTED / DETERMINISTIC PASS / MINIMAX-M3 IMAGE PASS
- Source plan: `docs/plans/docfit-libreoffice-visual-evidence-v2.md`
- Latest user intent: 按方案实施替换式迁移；不考虑兼容，不保留旧契约、旧渲染路径或适配层
- Official Agent basis:
  - 普通客户端 Tool 的 `tool_result` 可返回原生 `image` 内容块
  - programmatic tool calling 只接受文本结果，因此 `docx_visual_review` 保持 direct client Tool
- Current slice: clean-break 迁移和应用会话根注入完成；当前配置仍使用纯文本/Tool-call 的
  `MiniMax-M2.7`，MiniMax 最新 `MiniMax-M3` 已在同一 Anthropic-compatible 接口支持
  image/video 内容块
- Last proven evidence: 三校真实 Docker 链路 3 passed；V2 targeted tests、ruff、mypy 已通过；
  MiniMax-M3 live 已实际调用 render 和 visual-review，并正确读取原生图片
- Completed slice batch: visual core、MCP/CLI、template/convert、observability、Docker/CI、
  doctor、旧代码删除、三校验收与 00–06/README 对齐
- Next slice: 将 MiniMax 默认/运行配置升级到 `MiniMax-M3`，并继续定位 M3 只读 Subagent
  未进入 child Tool 的原因；这是模型升级/Agent qualification，不是第二图片协议
- Next proof: M3 image gate 已 PASS；M3 subagent gate 只到 `Agent`、未调用 child inspect/review；
  全量回归仅剩一个与本迁移无关的
  10 ms wall-clock 观测性能断言在系统负载下抖动
- Stop condition: 确定性、真实三校服务和普通 Agent 原生图片像素验收已满足；默认模型升级
  和只读 Subagent M3 qualification 尚未完成；DocFit 的 M3 质量里程碑不在本工作包
- No-touch scope: 与本迁移无关的 Knowledge、Eval Truth 与用户临时诊断文件；不覆盖工作区已有无关修改
- Parked work: MiniMax-M3 默认模型升级与 Subagent qualification、Word 像素一致、学校补丁/兼容
  规则、Provider 平台、旧 render_ref 迁移、第二渲染器

## Evidence

- 固定镜像：`docfit-libreoffice-visual:25.2.3.2`，image ID
  `sha256:830475cabfc4c21c7628fc2fd992dff78cf36502442acf72b96ab2d6ae8afb49`；
  LibreOffice `25.2.3.2 520(Build:2)`。
- 三校真实链路、完整 M1 视觉链和 Tool contract 合并复跑 → `10 passed`。
- `uv run pytest -q tests/unit/test_visual_evidence_v2.py` → `4 passed`。
- `uv run ruff check src tests`、`uv run mypy src` → PASS（73 source files）。
- 两次 `uv run pytest -q` 均为 `334 passed, 1 failed, 1 warning`；唯一失败是既有
  `test_queue_put_p95_stays_within_synchronous_hook_budget` 被 wall-clock deadline 记录为
  15–17 ms，执行时同机存在另一个长运行 Agent。该测试隔离复跑通过，完整 observability
  runtime 文件 `16 passed`。warning 是既有 Starlette/httpx 弃用提示。
- `uv build`、`uv lock --check`、`git diff --check` → PASS。
- `uv run docfit doctor --require visual-renderer` → visual-renderer gate PASS；确认 OfficeCLI
  1.0.143、LibreOffice image ID、字体 digest 与三个 Poppler 程序。overall 的可选
  agent-smoke receipt 状态为 NOT_READY，不影响该 gate。
- 应用会话现在把 task root 直接绑定到 SDK 进程内 MCP server；Agent 不传视觉
  `task_root`，伪造其他根会被拒绝。相关 Tool/permission/template/doctor 契约测试
  `34 passed`。
- MiniMax-M2.7 live image v3：`Skill → docx_render → docx_visual_review` 均实际调用；render
  和 220 DPI 整页证据成功，但 M2.7 只向模型暴露 1819×2573 的元数据，没有图片像素，
  因而门禁按正确语义 FAIL。此前 Kimi 候选在 Tool 循环层返回 error。
- MiniMax-M3 bounded live image v3：同一 `/anthropic` 路由和同一 V2 Tool 实现下 PASS；
  `Skill → docx_render → docx_visual_review` 完整出现，模型读取联系表和 220 DPI 整页图片。
- MiniMax-M3 bounded subagent v3：父 Agent 完成 `Skill → docx_render → Agent`，但 child 未调用
  `docx_inspect`/`docx_visual_review`，因此 FAIL；这不是主 Agent image block 能力失败。
- MiniMax 当前官方 Anthropic SDK 文档确认：`MiniMax-M3` 支持 text/image/video、Tool call、
  Tool result 和 thinking；M2.7/M2.5/M2.1/M2 仅支持文本与 Tool 相关内容块。
  <https://platform.minimaxi.com/docs/api-reference/text-anthropic-api>
- 官方 Agent 依据：普通 client Tool result 支持 image blocks；programmatic tool calling
  拒绝 image/document results，因此视觉 Tool 保持 direct MCP client Tool。

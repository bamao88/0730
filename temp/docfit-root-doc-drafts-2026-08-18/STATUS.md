# DocFit 状态

状态: temp 候选稿，未替换根目录 `STATUS.md`
更新日期: 2026-08-18

本文负责回答“项目现在在哪”。它只写当前可用能力、正在推进的工作、已知问题、下一步和
恢复项目时应读取的入口。本文不写永久架构解释、完整任务历史、测试日志或旧计划正文。

## 现在可用

- Python 3.12 / uv 项目环境，入口脚本为 `uv run docfit ...`。
- `doctor`、ruff、mypy 和 pytest 基础门禁。
- 固定 Docker LibreOffice V2 视觉渲染路径，用于页面级视觉证据。
- 本地 observer，可查看脱敏后的 SDK/App/Tool 运行轨迹。
- 模板提取模块已有当前合同、模块边界、Harness loop、三工具面、Subagent closure 和发布交接设计。
- 模板提取 static Eval 可在运行完成后比较 Actual 模板产物与 Gold 模板产物。
- 用户内容提取已有 `extract-student-content`、Student Content Model 输出和 `eval-student-content` 评分入口。
- final word 生成已有独立 fill/debug 路径和 style-property closure 工作线，但完整 accepted E2E 仍未关闭。

## 并行模块状态

| 模块 | 当前状态 | 继续读取 |
| --- | --- | --- |
| 模板提取 | 架构和合同基本成形；真实 Agent / 真实学校模板仍需要最新 live evidence 和 bug closure | `docs/modules/README.md` -> 模板提取模块 |
| 用户内容提取 | Gold/Eval 入口已存在；更广泛的质量和泛化仍需继续验证 | `docs/modules/README.md` -> 用户内容提取模块 |
| final word 生成 | 当前活跃工程线；style-property closure 和完整 final-fill readiness 还未形成 accepted E2E | `docs/modules/README.md` -> final word 生成模块 |

## 当前主要工作

1. 保持三个模块并行推进，但上下文隔离。
2. 关闭模板提取 live-run blocker，用 bug evidence、确定性测试和 Skill/Tool/Harness feedback 证明修复层正确。
3. 完成 style-property closure，让 final word 生成能稳定消费模板样式合同和 Student Content Model。
4. 在 `temp/` 中先完成文档系统重组草案和根文档候选稿，再替换正式文档入口。
5. 声明真实学校/真实学生产品就绪前，先证明 final word 生成端到端链路。

## 已知问题

- 工作区有大量未提交的源码、测试、DOCX 和 `temp/**` 改动；提交时必须只 stage 本次相关文件。
- `docs/human/**` 有很多有价值讨论，但不应作为 Agent 默认上下文。
- `docs/plans/**` 和 `docs/status/active/**` 有很多阶段证据；完成项需要压缩、归档或提炼。
- `docs/docfit-00-index.md` 不应长期承担权威索引；正式整理后应由 `docs/README.md` 接管文档路由。
- `docs/runbooks/**` 和 `docs/agents/**` 尚未建立，长操作手册和 Agent runbook 暂时仍分散在 human、plans、status 中。
- `docfit convert` 和 `convert-thesis` Skill 仍是 legacy E2E 路由，不定义三个并行模块的边界。

## 下一步

1. 评审 `temp/docfit-document-system-reorganization-draft-2026-08-18.md` 和根文档候选稿。
2. 确认后第一批正式替换：`README.md`、`ARCHITECTURE.md`、`STATUS.md`、`docs/README.md`。
3. 建立 `docs/runbooks/**` 和 `docs/agents/**`，迁移长操作说明和 Agent 经验。
4. 将三份 `docs/modules/*.md` 迁移为三个模块目录，保留清晰的模块禁读边界。
5. 将长期有效的 Gold、Field Registry、Fill Contract、Style Contract 结论提炼到 `docs/contracts/**`。
6. 压缩或归档完成的 plan、active status 和 bug 记录。
7. 更新文档合同测试，防止旧权威路径、旧启动链路和 stale 断言回流。

## 恢复入口

- 项目入口：`README.md`
- 架构入口：`ARCHITECTURE.md`
- Agent 操作：`AGENTS.md`
- 文档生命周期：`docs/README.md`
- 模块路由：`docs/modules/README.md`
- 测试与 Eval：`tests/README.md`
- 当前重组草案：`temp/docfit-document-system-reorganization-draft-2026-08-18.md`

# Worktree 合并记录（2026-10-22）

目标目录：`/Volumes/ExtSSD2601/Docfit`。保留目标分支 `codex/final-word-generation`。
本次范围是合并既有工作并恢复共同开发入口，不把历史状态升级为新的产品验收。

## 合并来源

| 来源 | 提交基线 | 合并内容 |
| --- | --- | --- |
| template-extraction | `3d808767fb46ed962988e4df6482162c8a214397` | 相对目标 442 个提交的代码、Skill、文档、测试和已提交证据 |
| user-content-extraction | `894fbc829ac3e37b89cc890c95a07d7cdba1b85d` | 合同及未提交的 CLI、层级绑定修复、Gold 脚本、测试和用例清单 |
| final-generation | `98a107a1a58c8c7d785ff04eb668c9c240d4fa0c` | 合同及未提交的独立生成入口、内容分区、运输、样式与 Eval 能力 |
| harness-source-structure | `aefe34389f2c74f214595f3f4865cecfa32196cb` | 提交均已包含在模板线；补入未提交的一处 Reference 表述修订 |

旧 harness 分支的独有提交经 `git cherry` 核对，补丁均已包含在最新模板线。
`agent-output-contract-verify-head.FNwjKZ` 的提交也是模板线祖先，不重复合入。
原 worktree 保留；没有归档、清理、切换分支或改动其源码。

方法：模板线 squash，加另外两条线的工作区差异三方应用，并将旧接口适配到当前目标合同。
保留当前模板提取的来源范围 `slot_ref`、物化证明、隔离 Agent home 与工具懒加载机制。
旧学生提取文档的根入口改写不覆盖模板线上已收敛的 AGENTS、架构和索引；模块新增事实补入模块文档。

## 保留与排除

- 合并前回退分支：`codex/backup-before-port-20261022-114148`；完整清单见 `/tmp/docfit-worktree-port-20261022/manifest.json`。
- 源状态、文本补丁和应用日志保存在 `/tmp/docfit-worktree-port-20261022/`。
- 多数未提交 DOCX 只改变 OfficeCLI 自定义元数据；没有把这些差异覆盖到项目样本。
  final-generation 中另有两份重新保存的 smoke 包，可见文字与当前样本一致，继续保留模板线样本。
- 模板 worktree 中的 `temp/full-flow-id-20260922/officecli-source` 是独立工具实验仓库；其局部改动留在原位置。
- 本地补齐学生 Gold、已保存 Actual、final-generation 基础包和输入包；真实学生数据继续留在受限本地目录。
- 多 GB 的未提交渲染图、运行输出与实验目录继续留在原 worktree，没有加入新提交。
- 模板线已提交的历史证据原样保留；Markdown 换行与历史日志不做批量空白清洗。
- 更早的 final-generation 调试包只有旧 `slot_id` 和旧来源证明；基础输入检查通过不代表满足当前发布模板合同。

## 合并适配与验证边界

- 新内容分区使用当前 `slot_ref`；内容写入仍要求来源范围引用，不恢复旧槽位协议。
- 共用只读 inspection 机制沿用模板线实现，不重复引入旧快照包装。
- 校准过时测试：字段/角色错误由前置合同反馈；失败批次需完整重交；发布证明使用当前版本；
  disjoint body member 不再被旧的单成员断言误判；样本清单排除 Word 临时锁文件。
- 新分区单元测试隔离了模板发布门，只证明 placement logic/contract。真实发布合同仍由原有专门测试覆盖。

## 验证

- `uv sync --frozen`：成功，沿用锁定的 Python / SDK 依赖。
- `uv run ruff check src tests`、`uv run mypy src`、`compileall`：通过。
- 相对模板线的源码、测试、Skill 和配置 `git diff --check`：通过。历史 Markdown 与日志原样保留。
- Student 001/002/003 用例清单：源文件、Registry 与 Gold 均可定位；Student 002 输入检查通过。
- 对已保存的 `student-002-actual` 运行当前 `eval-student-content`：PASS，无 blockers。
  报告：`.tmp/port-student-002-replay/student-content-eval-report.json`。这是保存产物的离线评分回放，
  没有重新调用 Agent、重建提取产物，也不是新 E2E。
- final-generation `student-001-njau-complete-debug --checks input,style`：59 项基础绑定与样式断言通过；
  generate / quality 未运行，release 未评估，不能据此声称可发布。
- `docfit doctor`：base 门通过；Agent smoke receipts 缺失，OfficeCLI 为 1.0.144、与锁定 1.0.143
  不符，固定 Docker LibreOffice renderer 未就绪。

- 最终全仓 `uv run pytest -q`：**1623 passed, 5 skipped, 1 warning**，152.94 秒。
  日志：`/tmp/docfit-worktree-port-20261022/pytest-verified.log`；结果包含模拟 Agent、
  contract、OOXML/OfficeCLI integration 和样本 replay 测试，不等于真实 Agent E2E。
- 无新的 `E2E agent loop` 或 `product acceptance` 结论。

## 远端与回退

用户本次要求合入当前项目，没有要求推送或合入远端 main；本次仅创建本地提交。
目标原分支与原 worktree 均保留，完整提交与补丁来源可从上述回退点及来源分支追溯。


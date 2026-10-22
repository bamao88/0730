# 核心字段 ID 闭环复验 — 2026-09-11

状态：CONTINUE。原字段词表重构计划的 Phase 8 尚未完成。

## 产品结论

最新 source-entry 路径已在真实 0820 封面输入上完成 Agent → Harness 反馈 → revision →
DOCX 物化 → 发布，7 个槽的字段来源与源位置引用均闭合。单槽真实 replay 也通过。
这证明引用执行链路可用，不证明学校语义和最终版式可交付。此次封面产品验收不通过；
不能以 CLI `built` 或发布成功将原计划改成 DONE，也不能外推到三校完整矩阵。

## 验证基线与 Git

- 起点 HEAD：`cd9c2c35841c392a9545a0e400b4e6b806638025`。
- 本轮修复：`6257ff0`。修复 source-entry JSON 校验后的类型表达、CLI 分支变量复用，
  更新旧 scope/feedback/inspect 测试，确保重复覆盖测试确实到达 overlap 门禁。
- 本轮承接并验证的三份相关合同测试文件含已有迁移改动，一并提交；没有提交 DOCX、Gold、
  未审阅 human 材料或其他运行时改动。
- live/replay 运行使用的是工作目录代码，不是干净 checkout。复现还需要
  `temp/id-closure-20260911/runtime-baseline.json` 的逐文件哈希和
  `tracked-working-tree.patch`；仅 checkout `6257ff0` 不能声称复现本次结果。
- 待整理改动按路径分类见 `temp/id-closure-20260911/pending-changes.json`。
  该清单是分组，不代表所有存量改动均已审阅或可以提交。

## 四层证据

| 层级 | 结果 | 范围与限制 |
| --- | --- | --- |
| logic/contract | 通过 | 核心专项 44；相关合同与物化 replay 套件 539；最后测试文件改动复核 71。ruff 通过，mypy 110 个源码文件通过。不能将套件内 mock/合成 inventory 视为真实 replay。 |
| real replay | 通过 | 旧真实姓名槽 task input/checkpoint/judgments，重新生成当前 inventory，移除旧 resolved_spans 后重新提交判断，重新物化，槽协议通过；未伪造视觉验收，也未在该 replay 调用完整发布。 |
| E2E agent loop | 通过，限本封面 | 真实 prepare-template，MiniMax，1 个 session，1 次 Harness feedback、1 次 semantic feedback，最终 built；7 个 slot 逐项验证词表来源、accepted part、source entry 与 span。 |
| product acceptance | 不通过 | 已检查最终单页 LibreOffice 渲染与填写合同；存在下述语义/视觉问题，human signoff 未完成；不声称 Word 像素一致。 |

命令证据和输入：

- `temp/id-closure-20260911/contracts.txt`、`final-test-delta.txt`。
- `temp/id-closure-20260911/slot-replay-final/replay-proof.json`，可执行脚本 `replay.py`。
- `temp/id-closure-20260911/cover-e2e.log`、`closure-proof.json`、`render.json`。
- live 输入来自 `evals/fixtures/template-extraction/minimal-units-0820/units/01-cover/`，
  包含学校模板和要求 PDF；Registry 使用 `content-fields-v0.5.yaml`。未给 Agent 注入 Gold。
- 产物：`temp/id-closure-20260911/cover-e2e/output/final-template.docx` 和 `fill-contract.yaml`。
- 修复前相关套件：11 failed / 528 passed；修复后 539 passed。测试失败主要是过期合同断言，
  不能将测试夹具更新描述为修复了 11 个真实产品故障。

环境：启动现有 Docker Desktop，固定 LibreOffice 镜像可用。系统 OfficeCLI 是 1.0.144；
本轮从官方 v1.0.143 release 下载独立 ARM64 二进制，哈希匹配仓库锁定值
`2f158d46f9b6c5eb0dfe4eb02038114001e17acc47b67347417c56dcf9659096`，通过 task-local PATH 使用。
`doctor --require visual-renderer` PASS；overall NOT_READY 仍来自未补齐的通用 agent-smoke receipts。
未改动全局 OfficeCLI，也未修改锁定版本要求。

## 产品验收阻断与下一步最小动作

1. 中文论文题目被判断为 fixed_label；输入词表明明有对应字段，最终没有中文题目填写槽。
   责任层：Agent 学校语义判断 / Skill 指引。不能由代码按模板 wording 补造字段。
2. 导师姓名和职称被合并进姓名槽，姓名样例及英文题目也吞入格式说明。
   责任层：Agent ordered parts 语义拆分；应修字段内容边界，不放宽 Harness 来源门禁。
3. 最终页面仍显示字号说明、方框占位，班级长占位文字导致换行。
   责任层待区分：固定/样式/清理 parts 的语义选择，以及物化呈现。先以 accepted judgments
   对照产物定位；不能把视觉问题都归给 Agent，也不能用单个学校字符串规则清理。

下一轮先修复并复验这个封面的语义/呈现阻断，再扩大到正文、目录、开题报告及三校矩阵。
当前没有依据进行全矩阵产品签收。原计划保持 CONTINUE。

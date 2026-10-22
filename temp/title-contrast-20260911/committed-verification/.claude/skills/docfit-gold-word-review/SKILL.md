---
name: docfit-gold-word-review
description: 用 Word 原生批注准备、补齐或复核 DocFit Gold 文件的人工审核材料时使用；适用于 template extraction、student fill、视觉/结构 eval 等任何需要人工确认 Gold DOCX、fill contract、case metadata、hash 绑定、批注覆盖或 review 留档的任务。
---

# DocFit Gold Word 复核

用原始 Gold Word 文件自身的“批注/评论”功能给人工 reviewer 看清楚：每个可见内容块在 Gold 中是字段、保留、生成、删除、条件区、样式证据、固定对象，还是需要人工裁决。

核心原则：没有批注的可见内容就是审核缺口。不能让 reviewer 猜“这里是漏批，还是 Gold 不处理”。

## 输出形式

- 直接在待审核的 `.docx` Gold 文件里写 Word 原生批注。
- 同步更新与该 DOCX 绑定的 contract、case、receipt、approval record 或 review snapshot hash。
- 保留两层批注：
  - 对象级批注：字段槽、处理区域、逻辑页、样式缺口、删除/生成规则等语义对象。
  - 覆盖批注：正文每个可见内容块都要有处理结论；页眉/页脚用正文总览批注说明保留策略。
- 在人工复核前使用 `coverage_completed_pending_manual_recheck`，不要提前写成 reviewer 已批准新版批注。

## 必读 Reference

执行前阅读 [workflow.md](references/workflow.md)。它包含完整流程、对象类型口径、常见问题和自检门。

## 可复用脚本

`scripts/docx_comment_coverage.py` 用于审计或补齐正文可见内容块覆盖批注。

常用命令：

```bash
python3 .claude/skills/docfit-gold-word-review/scripts/docx_comment_coverage.py audit path/to/gold.docx

python3 .claude/skills/docfit-gold-word-review/scripts/docx_comment_coverage.py add path/to/gold.docx \
  --out path/to/reviewed.docx \
  --replace-existing-coverage
```

脚本只处理 Word 原生批注结构，不负责业务判断。对象级批注、字段映射、样式缺口、hash 同步和 eval 自比较仍由 Agent 按 Gold 合同完成。

## 工作顺序

1. 确认精确目标文件：Gold DOCX、对应 contract/case/receipt/review 记录、当前 hash 和 expected verdict。
2. 建立对象级批注：按 contract、field registry、logical pages、regions、style contracts、known gaps 写清字段、动作、样式和审核结论。
3. 建立全覆盖批注：用脚本覆盖正文所有可见内容块；页眉/页脚用总览批注，避免 OpenXML 校验失败。
4. 同步绑定：重算 DOCX hash；更新 contract template hash、样式集合 digest、case hash、receipt hash、review snapshot 和 approval record。
5. 自检：批注结构、覆盖缺口、Word validate、hash gate、self eval 和目标测试都通过后再交给人工复看。

## 完成门

- 正文可见内容块 `missing_body_coverage=0`。
- 页眉/页脚如果存在可见内容，必须有 summary coverage comment。
- `officecli validate` 或项目等价 Word 校验通过。
- Gold DOCX、contract、case、receipt、approval record 的 hash 一致。
- 若有 self eval，Gold 对自身比较必须 `PASS / 100.0`。
- final 回复明确说明批注数量、覆盖范围、剩余需要人工确认的问题和已跑验证。

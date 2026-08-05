# `docfit-school-extract` v2 实施草案

> 状态：设计草案，未进入生产 Skill
> 日期：2026-08-05
> 长期合同：`docs/docfit-00-index.md` 至 `docs/docfit-06-development-roadmap.md`

## 1. 目标

把当前“只读学校材料证据提取”改造成“冻结模板产物生产”能力：读取当前任务的学校
模板、书面要求和可选官方示例，在不覆盖来源文件的前提下，只发布可填写的干净模板和
绑定该模板 hash 的槽位索引。来源、manual 区域、未决项和验证摘要都属于槽位索引内容，
不形成额外交付产物。

本草案不直接替换 `.claude/skills/docfit-school-extract/**`。当前应用仍强制在
`docfit convert` 中加载两个 Skill，当前契约测试仍把学校提取锁成只读；在 Tool/App
支撑和回归门完成前切换生产 Skill，会产生无法兑现的完成声明。

## 2. 用户目标与触发边界

应触发：

- 清理、规范或冻结学校论文模板；
- 从学校模板与要求中识别固定内容、可填槽位、说明文字和人工区域；
- 为后续论文转换准备当前任务的可填写模板产物；
- 比较模板、书面要求和官方示例，并把冲突或 gap 保留在产物中。

不应触发：

- 把学生论文内容填入模板；
- 转换或排版学生论文；
- 单纯检查一份已经生成的最终论文；
- 创建跨任务学校 profile、学校 Knowledge 或模板注册表。

## 3. 输入与语义产物

输入：

- 必需：学校模板 DOCX；
- 必需：当前适用的书面要求或等价正式材料；
- 可选：官方示例、适用性说明和用户确认。

语义产物：

1. 可独立打开且不再原地修改的冻结干净模板 DOCX；
2. 绑定冻结模板精确 SHA-256 的槽位索引，其中包含固定内容边界、manual 区域、未决项、
   必要来源和验证结果。

产物只在当前任务内有效，不包含学生内容，不自动晋升为产品 Knowledge。

## 4. 拟议物理形态

以下名称和字段是实施候选，不是当前公共合同：

```text
output/template-artifact/
├── clean-template.docx
└── slot-index.json
```

`slot-index.json` 的候选最小形态：

```yaml
schema_version: 1
scope: current_task_only
template:
  path: clean-template.docx
  sha256: <frozen-template-sha256>
  source_template_sha256: <source-template-sha256>
sources:
  - source_id: <task-local-id>
    kind: template | written_requirement | official_example | user_confirmation
    sha256: <sha256-or-null>
    applicability: <scope>
fixed_regions:
  - region_id: <task-local-id>
    locator: <snapshot-bound-locator>
    expected_fingerprint: <fingerprint>
    evidence_refs: [<ref>]
slots:
  - slot_id: <task-local-id>
    locator: <snapshot-bound-locator>
    expected_content: scalar | paragraph_stream | composite | manual
    cardinality: {min: 0, max: 1}
    evidence_refs: [<ref>]
manual_regions: []
gaps: []
unresolved: []
review:
  document_sha256: <frozen-template-sha256>
  reviewed_pages: [1]
  evidence_refs: [<visual-evidence-ref>]
validation:
  document_sha256: <frozen-template-sha256>
  status: ok | blocked
  evidence_ref: <validation-ref>
```

`locator` 的首版候选由绑定冻结模板 hash 的 opaque `object_ref`、相对关系和必要前置
指纹组成。页码、bbox、颜色或单个近似文字只能作为辅助证据，不进入唯一编辑身份。
是否需要单独 `slot-index.json`，由消费者实现和 fixture 证明后再决定；首选把槽位索引
放在一个 manifest 内，避免两个 JSON 的 hash/版本漂移。

## 5. Skill 内容边界

`SKILL.md` 只说明论文模板整理任务、两个输出、通用转换规则和特殊论文部件。Agent 在
完成任务时自然理解学校材料和模板结构，不把“判断”设计成独立阶段、状态或额外产物。

hash、locator、唯一命中、原子修改、固定内容保护、验证和失败不发布由脚本、Tool 或
应用壳强制。Skill 不重复 Tool 名称、参数、错误恢复或注册时已经提供的使用说明。

## 6. 冻结点

该关系由 Tool/App 实现，不要求 Agent 在 Skill 中手工维护：

```text
最后一次模板编辑
  → 重新 inspect 最终工作副本
  → 取得最终 template SHA-256
  → 在该快照上建立槽位和固定区域 locator
  → 全页视觉检查与确定性验证
  → 发布冻结产物
```

索引生成后发生任何 DOCX 修改，都使索引、视觉证据和验证结论失效。系统必须重新取证，
不能把旧 locator 静默重绑到新快照。

## 7. 生产切换需要的原子改动

一次实施变更至少同时包含：

1. 将候选 Skill tree 迁入 `.claude/skills/docfit-school-extract/**`；
2. 让学校提取目标能够使用 `docx_edit` 创建工作副本，并使用 `docx_validate` 核对产物；
3. 实现 `template-artifact.json` 的 shape/hash/授权路径校验；
4. 实现槽位零命中、多命中、快照失效、manual/gap 与固定内容保护门；
5. 移除 `docfit convert` 对两个 Skill 同时加载的要求；
6. 让转换入口只消费通过合同的冻结模板产物，不重新读取原始学校要求；
7. 更新 Skill、Tool、CLI 与集成测试；
8. 保留源 hash、Adobe candidate、全页视觉审查和独立验证门。

如果第 2–4 项尚未实现，新 Skill 只能返回 `blocked`/能力缺口，不能把 Agent 自报的
DOCX、槽位表或视觉观察称为冻结产物。

## 8. Reference 目录方案

全新候选树位于 `docs/plans/docfit-school-extract-v2-fresh-draft/`；旧草稿保留供比较，
不在其文字和章节上继续增量修改：

```text
docfit-school-extract/
├── SKILL.md
├── references/
│   ├── index.md
│   ├── template-text.md
│   ├── front-matter-and-forms.md
│   ├── table-of-contents.md
│   └── sections-headers-footers.md
└── evals/
    └── evals.json
```

## 9. 契约测试与行为用例

生产切换时更新 `tests/contract/test_skill_contract.py`：

- 不再要求学校提取 Skill “不修改任何文档”；改为来源只读、只写工作/输出副本；
- 不断言 Skill 出现任何 Tool 名称；Tool 能力由 SDK 注册信息提供；
- 删除 `body.count("- [ ]")` 一类 checklist 形状断言；
- 断言 L0 只定义任务、两个产物、通用规则和一个特殊部件索引入口；
- 断言不出现学生内容填充、学校 Knowledge、跨任务 profile 或另一个 Skill 名称；
- 断言 `references/index.md` 中列出的部件 reference 都存在且只属于本 Skill。

首批行为用例：

| 用例 | 关键断言 |
|---|---|
| 唯一槽位与明确说明文字 | 生成冻结产物；固定内容保留；槽位绑定最终 hash |
| 两个相同占位符 | 不猜测 locator；记录 gap 或提出最小问题 |
| 红色文字但用途不明 | 不因颜色删除；保留为未知/manual |
| 模板与要求冲突 | 同时保留证据；没有裁决依据时不冻结为已确认规则 |
| 索引后模板被修改 | 旧索引、视觉与验证证据全部失效 |
| 同时提供学生论文 | 不填学生内容；只处理学校模板产物 |

改进现有 Skill 时，先保存旧 Skill snapshot，再对候选 Skill 和旧版本运行同一批用例。
主要质量目标仍是：合成 fixture 上任何未闭合的冻结产物合同都不得被接受为完成。

## 10. 完成与非目标

本草案完成只表示候选文字、目录和实施边界可供评审。它不表示：

- 生产 Skill 已替换；
- 新 schema 已成为公共合同；
- 当前 Tool 已能验证槽位唯一性或固定内容；
- 当前 `docfit convert` 已消费冻结模板产物；
- M3 Eval 或真实论文资格验证已经恢复。

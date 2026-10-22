# 问题：inspect 层缺少合并后内容对象的 canonical ID

- 状态: `OPEN / ARCHITECTURE DEBT`
- 严重度: `P1`
- 发现日期: `2026-08-27`
- 子系统: 模板提取 Word inspect、对象清单、Agent reading packet、物化目标映射
- 影响流程: `prepare-template` post-unit 语义判断与物化

## 1. 摘要

当前 Word inspect 会通过 `object_ref.object_id` 给底层可执行 DOCX 对象生成稳定 ID。
这些 ID 来自 inspect selector 返回的对象，例如 `run`、`paragraph`、`table`、`picture`、
`sdt` 或 `shape`。

但 inspect/normalize 层目前没有给“人或 Agent 读起来是一个整体”的合并后内容对象生成
canonical ID。post-unit 的 `reading_blocks` 现在承担了这部分职责的一部分：它会把多个底层
对象 ID 聚合起来，并生成一个 `block_id`。问题在于，`block_id` 是在 Agent reading packet
层生成的，而不是在 canonical Word inspect/normalize 层生成的。

这造成了边界歧义：

```text
current:
  object_ref.object_id = 底层可执行 DOCX 对象 ID
  reading_blocks[].block_id = Agent 阅读视图里的 covered_object_ids 聚合别名

desired:
  object_ref.object_id = 底层可执行 DOCX 对象 ID
  canonical_content_object_id = inspect/normalize 层生成的合并后内容对象 ID
  reading_blocks = canonical content objects 之上的 Agent 阅读视图
```

## 2. 产品影响

当前系统仍然可以把 Agent 判断追踪回可执行 DOCX 对象，因为每个 `reading_block` 都保存
`covered_object_ids`，Harness 在物化前会把 reading reference 展开回 object IDs。

真正的风险是架构边界漂移：

- Agent-facing 的 `block_id` 容易被误认为真实可执行对象 ID。
- reading packet 逻辑容易变成意外的第二套对象模型。
- materialization 和 readiness 代码可能开始依赖 reading packet 的聚合结果，而不是依赖稳定的
  inspect/normalize 合同。
- 后续学校模板可能需要比临时 `block_id -> covered_object_ids` 别名更稳定的合并对象身份。

这目前不是一个已证明的数据丢失 bug。对 `03-toc`、`04-paper-body`、`06-proposal` 和完整
HUNAU 模板做 real inspect replay 时，没有发现底层 `object_ref.object_id` 缺失或重复。当前缺口是：
合并后的可读内容对象没有 inspect 层 canonical ID。

## 3. 当前已验证事实

Word inspect 会生成底层 object refs：

```text
InspectedObject.object_ref = {
  document_sha256,
  object_id,
  expected_fingerprint,
}
```

public inspect object 暴露的是嵌套 `object_ref`，不是顶层的合并对象 ID。

post-unit reading packet 会机械地聚合 scoped objects：

```text
unit boundary start/end locator
  -> scoped inspect objects
  -> 按父 block locator 聚合 run/hyperlink/fieldSimple 等后代对象
  -> reading_blocks[].block_id
  -> reading_blocks[].covered_object_ids
```

Harness inventory 当前保存：

```text
objects[] = 从 object_ref.object_id 正规化出来的可执行对象清单
reading_blocks[] = 带 covered_object_ids 的 Agent-facing 聚合视图
```

### 3.1 当前 inspect 阶段的代码结构

当前 inspect 阶段的核心实现位于 `src/docfit/tools/inspection.py`。

流程是：

```text
inspect_document(document, office, selector)
  -> document_sha256 = sha256_file(document)
  -> raw_objects = office.query(document, selector)
  -> for raw in raw_objects:
       locator = raw["path"]
       kind = raw["type"]
       text/style/format = raw facts
       fingerprint = hash(type + text + style + format + resolved_style)
       object_id = hash(document_sha256 + locator + type)
       object_ref = {
         document_sha256,
         object_id,
         expected_fingerprint,
       }
       InspectedObject(locator, kind, text, style, format, object_ref)
```

这里生成的是底层可执行对象 ID。它的身份来自：

```text
document_sha256 + locator + type
```

它解决的是“后续修改 DOCX 时能不能稳定找到原对象、能不能发现 stale object”的问题，不解决
“哪些 run 应该合并成一个语义内容对象”的问题。

public inspect object 当前暴露结构大致是：

```json
{
  "locator": "/body/p[@paraId=0992F12C]/r[1]",
  "type": "run",
  "text": "湖南农业大学全日制普通本科生毕业论文",
  "object_ref": {
    "document_sha256": "4c05ea...",
    "object_id": "obj-e4b433ef850d80eff04f7040",
    "expected_fingerprint": "8bbb1b..."
  }
}
```

注意：这里没有“合并后整体”的顶层 ID。顶层 `object_id` 是 Harness inventory 正规化时从
`object_ref.object_id` 提升出来的，不是 inspect public object 原生字段。

### 3.2 当前 reading packet 的 merge 结构

当前 reading packet 的核心实现位于 `src/docfit/template/reading_packet.py`。

它的流程是：

```text
build_unit_reading_packet(unit, scoped_objects, coverage_object_ids)
  -> scoped_objects 来自 unit boundary 的 start_locator/end_locator 范围
  -> _group_scoped_objects(scoped_objects)
  -> _block_locator(locator)
       /body/p[1]/r[1]       -> /body/p[1]
       /body/p[1]/r[2]       -> /body/p[1]
       /body/p[1]/hyperlink  -> /body/p[1]
  -> 每个 group 生成:
       block_id
       range_id
       text
       covered_object_ids
```

真实 `object-inventory.json` 中的 reading block 示例：

```json
{
  "block_id": "u-proposal:block-0001",
  "range_id": "u-proposal:range-0001",
  "unit_id": "u-proposal",
  "text": "湖南农业大学全日制普通本科生毕业论文",
  "covered_object_ids": [
    "obj-e4b433ef850d80eff04f7040"
  ]
}
```

如果一个段落被 Word 拆成多个 run，当前结构会变成：

```text
底层 inspect objects:
  obj-a = /body/p[10]/r[1] = "毕业论文"
  obj-b = /body/p[10]/r[2] = "（设计）"
  obj-c = /body/p[10]/r[3] = "题目："
  obj-d = /body/p[10]/r[4] = "××××"

reading packet:
  block_id = u-cover:block-0003
  text = "毕业论文（设计）题目：××××"
  covered_object_ids = [obj-a, obj-b, obj-c, obj-d]
```

这说明当前 reading packet 的确在做一层 merge，但这层 merge 是 Agent-facing projection，而不是
inspect/normalize 层的 canonical object model。

### 3.3 当前 Harness 如何使用这些结构

当前 Harness 会把 Agent 的 reading references 展开回底层对象：

```text
Agent judgment:
  covered_reading_block_ids = ["u-cover:block-0003"]

Harness projection:
  u-cover:block-0003 -> [obj-a, obj-b, obj-c, obj-d]

Normalized judgment:
  covered_object_ids = [obj-a, obj-b, obj-c, obj-d]

Materialization:
  obj-* -> object_ref -> DOCX mutation target
```

因此当前链路仍然可追踪。问题不是“执行找不到对象”，而是“合并后可读对象的主身份不应该由
reading packet 临时生成”。

## 4. 目标边界

把“可读内容对象”的 merge 前移到 inspect/normalize 层。

稳定合同应该变成：

```text
raw executable object
  id: object_ref.object_id
  purpose: stale-safe DOCX mutation target and low-level evidence

canonical merged content object
  id: canonical_content_object_id
  purpose: stable semantic judgment unit, generated before Agent reading packet
  contains: covered_object_refs / covered_object_ids, text, locator span, style summary

Agent reading packet
  purpose: unit-scoped read-only projection over canonical content objects
  should not invent execution targets
```

`reading_blocks[].block_id` 可以保留为展示别名，但不能成为 canonical 语义身份或可执行身份。
如果可行，reading packet 应该直接暴露 canonical content object IDs，并让 block IDs 退化为可选或
派生字段。

迁移后的 reading packet 不是没有逻辑，而是不再拥有“主 merge 逻辑”。

它仍然应该负责：

- 根据 unit boundary 选择当前 unit 内要展示的 canonical content objects。
- 控制 Agent 输入的顺序、窗口、分页、上下文摘要和样式提示。
- 给 Agent 提供可读文本、相邻上下文、layout cues 和 coverage contract。
- 在必要时提供只读展示别名，例如 `reading_view_id` 或兼容期的 `block_id`。

它不应该再负责：

- 决定哪些 raw run/paragraph/table 是一个 canonical semantic object。
- 生成系统主对象 ID。
- 让 materializer 直接依赖 `block_id` 作为执行目标。
- 用 Agent-facing 展示切片替代 inspect/normalize 的稳定对象合同。

如果 Agent 需要在一个 canonical content object 内继续细分，应该把它表达为该 canonical object 下的
derived selection 或 subrange，而不是让 reading packet 创造新的主对象身份。

## 5. 迁移方向

1. 新增 inspect/normalize 层的 merged content object model。
2. 基于 document hash、locator span、object kinds 和 covered low-level object IDs 生成确定性的
   canonical ID。
3. 继续保留底层 `object_ref`，用于真实 DOCX mutation 和 stale fingerprint validation。
4. 调整 Harness inventory，让 `objects[]` 明确表示 canonical semantic objects；或者把 inventory
   拆成边界更清楚的几个区：

```text
canonical_content_objects[]
executable_objects[]
reading_views[]
```

5. 调整 reading packet，让它消费 canonical content objects，而不是自己独立聚合 raw inspect objects。
   reading packet 可以继续做 unit projection、分页、展示切片和上下文摘要，但这些都必须建立在
   inspect/normalize 已经确定的 canonical object 边界上。
6. 只保留足够迁移测试和 real replay fixtures 的向后兼容；不要长期保留两套平级对象模型。

## 6. 修复归属

这个问题应该在 Word inspection / normalization 边界修复，不应该在 materialization handlers 里补，
也不应该通过 Agent Skill prose 兜底。

后续如果出现相关失败，归因方式应为：

- 底层 `object_ref.object_id` 缺失：修 `docfit.tools.inspection`。
- 合并后可读对象边界错误：修 inspect/normalize 的 merged content object 层。
- Agent 引用了不存在的 block 或 canonical object：修 Harness feedback/schema 或 Agent reading packet 合同。
- Agent 绑定错 field 或 body member：修 Agent-facing schema、Skill、registry affordance 或语义示例。
- materializer 无法执行已接受的 canonical judgment：修 canonical-to-executable mapping 或对应
  materialization handler。

## 7. 验收条件

迁移完成必须同时满足：

1. real inspect replay 能输出带确定性 ID 的 canonical merged content objects。
2. 每个 canonical content object 都能映射到一个或多个底层 `object_ref`。
3. reading packet 不再拥有主要 merge 逻辑，只保留 unit projection、展示组织、分页和只读上下文构造。
4. Agent judgments 可以引用 canonical content object IDs，或者引用能确定性展开到 canonical content
   object IDs 的 reading views。
5. materialization 真实执行时仍然只通过 fresh low-level `object_ref` handles。
6. 现有 post-unit real replay cases 继续通过，至少覆盖 `03-toc`、`04-paper-body`、`06-proposal`
   和完整 HUNAU 输入。
7. 文档命名必须明确区分 executable object、canonical content object 和 Agent reading view，不能把
   三层当成同一层对象。

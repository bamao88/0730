# Agent Skill 与代码、Tool 的职责边界经验

> 文档性质：个人产品与 Agent 系统设计经验
> 记录日期：2026-08-12
> 经验来源：`docfit-school-extract` 使用南京农业大学本科毕业论文原始模板进行的真实端到端测试
> 核心结论：反复出现且确定性的步骤应下沉到代码或 Tool，Skill 保持为精简的领域判断手册。
> 实施状态：2026-08-12 已按 clean break 落地应用编排与角色化 Tool；完整真实 E2E 复验仍待完成。

本文第 2–3 节保留失败时协议作为证据；文中的“当前 Skill”均指失败快照，不代表 HEAD 的运行
合同。HEAD 已不向 Agent 暴露 cursor、document/region ref、publish 或 built/blocked 终态。

## 1. 为什么记录这条经验

在真实 Agent 工作流中，把所有规则都写进 Skill，并不等于 Agent 就会稳定执行。

Skill 中通常会混合两类完全不同的内容：

1. Agent 必须理解和判断的领域问题，例如学校固定内容、学生内容、说明文字、正文结构和视觉缺陷；
2. API 参数、对象引用、分页游标、阶段切换、重试、版本覆盖和发布门禁等确定性协议。

第二类问题如果主要依靠模型记忆和遵守，会带来几个典型后果：

- Agent 明明已经读过正确规则，仍可能构造错误参数；
- 新 SDK 会话不会天然继承上一会话对错误的理解；
- 同一种错误可能消耗完整 turn budget 后在新会话中重新发生；
- Tool 虽然可以 fail-closed，却无法阻止执行器无限续跑；
- Skill 越写越长，但稳定性、时延和成本并没有同比改善。

因此，Skill 不应成为另一个运行时。它应说明“如何判断领域问题”；代码和 Tool 应决定“流程如何推进、参数如何构造、状态是否合法以及何时必须停止”。

## 2. 本次失败案例绑定的 Skill 版本

### 2.1 发生错误时实际加载的版本

本次错误不能用模糊的“当前 Skill”指代。端到端任务执行时，Agent 实际加载的是复制进任务目录的不可变快照：

```text
任务：temp/docfit-school-extract-v2-njau-e2e-final-visual-r1
Skill 名称：docfit-school-extract
Skill 显式版本字段：无
快照路径：temp/docfit-school-extract-v2-njau-e2e-final-visual-r1/.claude/skills/docfit-school-extract/SKILL.md
快照时间：2026-08-12 15:31:56 +08:00
SHA-256：1ca57941f31f078174181f4d48617ee475345a3d5e16698dd6c7f2ddc821e851
```

本文把该快照称为：

```text
docfit-school-extract / unversioned snapshot 1ca57941
```

这是本次错误 Skill 版本的唯一精确标识。

### 2.2 与记录本文时的候选文件区分

记录本文时，仓库中的候选 Skill 已经发生后续修改：

```text
路径：docs/plans/docfit-school-extract-v2-candidate-skill/SKILL.md
SHA-256：6cb8b376bcfe21793b0f63095b10863f58970fec988cfc941dd7dc6e855c5a4a
```

后续候选文件已经增加了正文结构闭包、致谢责任核对、首次巡检调用省略 cursor 等补丁，因此它不是当时发生错误的精确版本。

同时也要注意：端到端失败并不只由 Skill 文案造成。它是 Skill 遵循不稳定、Agent-facing Tool 协议设计和执行器缺少停滞熔断共同作用的结果。记录错误版本是为了保证证据可追溯，不是把全部责任归因于一个 Markdown 文件。

## 3. 失败快照中应下沉到代码或 Tool 的内容

### 3.1 `template_edit` 的 JSON 结构规则

当前 Skill 详细规定了：

- 顶层只能有一个 `operations` 数组；
- `action`、`field_id`、`object_ref` 必须位于数组成员中；
- 一次最多包含 32 个操作；
- 不能增加额外 wrapper；
- 多处提供了完整 JSON 示例。

这些属于 Tool Schema，而不是领域知识。真实测试中，Agent 即使读过这些规则，仍多次把 `field_id` 放进 `object_ref`。

更合适的实现是：

- Schema 直接表达唯一合法结构；
- Tool 对常见错误进行确定性纠正，或者返回可执行的修正结构；
- 应用层识别同类错误的重复发生并停止无效重试；
- Skill 最多保留一句“向当前区域提交语义操作，参数以 Tool Schema 为准”。

### 3.2 cursor 和逐页批次管理

当前 Skill 要求 Agent：

- 首次调用 `template_final_review(document_ref)`；
- 得到 `next_cursor` 后原样传回；
- 循环到 `coverage_complete: true`；
- 编辑产生新 `document_ref` 后从第一页重新检查。

其中只有“必须实际查看每页图片”和“判断图片是否存在缺陷”属于 Agent 责任。

以下事项都是确定性状态，应由代码负责：

- cursor 的创建、保存和续传；
- 下一批应该返回哪些页面；
- 哪些页面已经完成检查；
- 是否存在漏页、跳页或重复覆盖；
- cursor 是否绑定当前 Word hash 和当前 render；
- 文档编辑后旧版本页面证据自动失效；
- 是否已经具备进入发布阶段的完整覆盖。

Agent-facing Tool 不应暴露 cursor。Cursor 可以继续作为底层视觉服务的内部实现，但不应成为模型需要理解和复制的协议字段。

### 3.3 阶段转换条件

当前 Skill 重复描述了以下状态条件：

```text
navigation.done
+ 无 pending_edit_intents
+ 生成内容已完成
→ 才能进入最终视觉自检
```

以及：

```text
coverage_complete
+ 精确 document_ref 匹配
+ 没有已知视觉缺陷
→ 才能发布
```

这些都是可由代码计算的布尔状态。代码状态机应直接拒绝非法阶段转换，不应要求 Agent 自己记忆并判断机械条件。

Skill 只需要解释四个阶段分别解决什么问题：

- 局部对象阶段解决语义分类；
- 收尾阶段解决生成内容和职责闭包；
- 最终视觉阶段解决整篇渲染缺陷；
- 发布阶段只交付已经通过门禁的精确版本。

### 3.4 `object_ref`、document hash 和 checkpoint 生命周期

当前 Skill 规定：

- 编辑后旧 `object_ref` 失效；
- 后续只能使用新 checkpoint 返回的引用；
- 不得复制或猜测 hash、fingerprint；
- 发布必须绑定最新精确版本。

这些都是对象身份协议，应由 Tool 和应用状态负责：

- 自动绑定当前不可变版本；
- 编辑后自动刷新或重新定位对象；
- 确定性拒绝旧引用；
- 阻止旧版本进入发布；
- 必要时直接返回当前有效对象，而不是让 Agent 搜索和拼装引用。

Skill 不需要反复教授对象引用生命周期。

### 3.5 Registry 的调用协议

当前 Skill 规定：

- 每个 `field_id` 首次使用前必须 lookup 或 search；
- 同一区域应该合并查询；
- Registry 请求是扁平结构；
- `object_id` 与 `field_id` 或 `query` 同级；
- 不得把 `object_ref` 嵌套到错误位置；
- 不得按照命名习惯猜造 field ID。

“不能猜造字段语义”是重要领域边界，应保留。但调用格式、首次使用记录和候选绑定应下沉到 Tool：

- 未经 Registry 确认的 ID 不允许提交编辑；
- 不存在的 ID 直接返回与当前对象绑定的合法候选；
- 首次使用状态写入 checkpoint；
- Agent 只需要从 Tool 给出的候选中作语义选择；
- Agent 不再承担“查询、记住字符串、再复制到另一个 Tool”的协议工作。

### 3.6 修改后的机械校验

当前 Skill 要求 Agent 查看：

- `source_unchanged`；
- `package_reopens`；
- OfficeCLI validation；
- `all_requested_effects_re_read`；
- `non_target_text_preserved`；
- 有效格式的修改前后来源；
- 修改后的局部图片。

前五项是确定性的 Tool 后置条件。Tool 应自行执行并在失败时阻止新版本提交，Agent 不需要理解或复述。

Agent 真正需要承担的是：

> 修改后的局部图片是否符合当前学校的语义责任和视觉预期。

### 3.7 TOC 的机械处理流程

当前 Skill 对目录规定了：

- 不得逐行删除目录缓存；
- 目录必须作为复合生成对象刷新；
- 标题树稳定后才能刷新；
- 刷新需要代表性 1–3 级标题；
- 必须检查 `refresh_needed`；
- Word 更新缓存和页码后需要再次验证。

可以由代码强制的部分包括：

- 禁止破坏 TOC 的局部缓存结构；
- 判断何时允许调用 `refresh_toc`；
- 把目录作为单个原子事务处理；
- 验证标题层级与对象类型；
- 更新 Word 字段缓存；
- 判断刷新后是否仍有 pending generated content。

Agent 应保留的判断只有：

- 哪些最终标题应该进入本校目录；
- 每个标题属于哪一级；
- 学校固定的目录标题、样式和版式责任是否应保留。

### 3.8 知识卡加载纪律

当前 Skill 规定：

- 任务开始时不得预读 Reference；
- 只能读取 `knowledge_signals` 命中的卡；
- 一次只读取一张；
- 不得读取未命中的卡。

领域信号和知识卡之间的映射可以保留在 Skill 中，方便解释每张卡解决什么问题。但具体允许读取哪些路径、一次允许读取几张，应由权限 Hook 或应用策略限制，不能只依靠文字纪律。

### 3.9 发布协议和 structured output

当前 Skill 详细规定了：

```yaml
status: built
artifact_path: output/final-template.docx
template_sha256: <sha256>
counts:
  slot: <count>
  remove: <count>
  manual: <count>
  gap: <count>
  unresolved: <count>
```

同时规定：

- `blocked` 时产物路径和 hash 必须为 null；
- 只能发布一次；
- 只能存在一份最终 Word；
- PNG 和 PDF 默认不对外发布；
- 最终文件不能静默覆盖。

这些属于应用输出合同，应该由代码根据真实文件、真实回执和发布事务生成，不能让 Agent 手工声明。

尤其是 `blocked`：Agent 可以报告它认为存在的语义问题，但最终是否属于不可恢复 blocker，必须由代码结合 workspace 状态验证。导航尚未完成、仍有有效对象或仍能继续查询时，不应接受终局 `blocked`。

### 3.10 重试、续跑和熔断

当前执行器会把 `max_turns` 视为“开启新会话继续”的信号，但没有充分验证应用状态是否取得进展。真实测试形成了：

```text
错误猜 cursor
→ Tool fail-closed
→ 当前会话耗尽 turns
→ 执行器启动新会话
→ 新会话重复猜 cursor
```

这类问题无法靠 Skill 自己解决。执行器必须提供：

- 相同状态连续无进展时停止；
- 单阶段最大会话数或最大成本；
- 同类 Schema 错误的次数上限；
- 明确的 `protocol_stalled` 或 `no_progress` 结果；
- 禁止无限 `max_turns → 新会话 → 重试`；
- 任何停滞都保持 fail-closed，不允许绕过视觉门禁发布。

## 4. 应继续保留在 Skill 中的内容

### 4.1 学校固定内容与学生内容的区分

Agent 必须判断一个对象究竟是：

- 学校身份和固定声明；
- 固定标签；
- 学生填写值；
- 写作说明；
- 格式示例；
- 样例论文内容；
- 条件区；
- 生成内容；
- 可重复正文结构。

这是学校模板提取的核心领域能力，不能简单下沉为机械规则。

### 4.2 原位置职责规则

同一 `field_id` 已经在其他页面存在，不代表当前页面的填写位置可以删除。

例如中文摘要页应分别核对：

- 本页论文题目；
- 固定“摘要”标题；
- 摘要正文；
- 关键词。

当前学校展示了其中哪项，清理后该位置就必须继续保留固定责任或本页填写接口。这属于页面语义责任判断，不能被字段全局唯一性替代。

### 4.3 固定具名章节与通用章节的区分

例如：

- “第一章 文献综述”可能是学校固定地标；
- “第X章（正文标题）”是通用可重复章的直接证据；
- “结论与展望”“参考文献”“附录”可能是固定后置结构。

它们在 Word 中可能都使用 Heading 样式，但语义处置完全不同。Agent 必须结合文字、局部关系和学校结构作判断。

### 4.4 `body.chapters` 的领域模型

Skill 应继续告诉 Agent：

- 正文不是一组互不相关的独立 slot；
- 标题、正文、列表、图表、公式等共同组成可重复章节能力；
- 只纳入当前学校实际展示的成员；
- 不因 Registry 存在某个字段就凭空制造 H1/H2/H3；
- 不得删除尚未纳入代表结构的唯一对象类型；
- 固定首章和末章不能替代普通中间章的可重复结构。

代码可以验证结构是否闭包、成员是否合法，但“哪些对象代表本校正文能力”仍需要 Agent 判断。

### 4.5 最终视觉检查标准

Skill 应保留精简、明确的视觉缺陷清单：

- 文字、图片、公式或内容控件是否裁切、重叠、缺失或出现错误字形；
- 表格是否断裂、越界或列宽异常；
- 图片和题注是否错位；
- 是否存在异常空白、孤立标题、重复或缺失页面；
- 页眉页脚、页码、节边界和跨页间距是否异常；
- 写作说明、格式样例、旧目录缓存和无职责残留是否仍可见。

代码负责保证每页都被提供给 Agent，Agent 负责对图片作视觉和语义判断。

## 5. 推荐的最终职责结构

精简后的 Skill 可以只保留五部分：

1. 任务目标以及局部语义判断与最终视觉检查两种角色的证据差异；
2. 对象分类和学校固定责任判断；
3. 内容槽和原位置职责；
4. 正文、目录、集合、可选区等领域模型；
5. 最终逐页视觉缺陷判断标准。

以下内容应从 Agent 的认知负担中移除，交给代码和 Tool：

- JSON 参数形状；
- cursor；
- checkpoint 和 hash 生命周期；
- 对象引用刷新；
- 批次与覆盖累计；
- Registry 调用格式；
- 机械校验；
- 重试和熔断；
- 发布事务；
- structured output 生成。

一句话概括：

> Skill 告诉 Agent 如何判断学校模板；代码决定下一步调用什么、参数怎样构造、当前状态是否允许推进，以及什么时候必须停止。

## 6. 对最终逐页巡检接口的具体建议

Agent-facing 接口不应要求 Agent 传 cursor。更合理的接口是确定性状态机：

```text
代码发现没有 pending batch
→ 返回下一批原生全页 PNG
→ 内部保存 cursor、页码和当前 hash

Agent 返回 clean
→ 代码确认上一批完成
→ 返回下一批

Agent 返回 defect
→ 停止巡检
→ 进入有界局部修复

文档产生新 hash
→ 代码废弃旧 hash 的覆盖状态
→ 新版本从第一页重新开始
```

Agent 只需要为应用绑定的每个页码返回视觉结论，例如：

```json
{
  "pages": [
    {"page": 1, "verdict": "clean", "defects": []},
    {"page": 2, "verdict": "clean", "defects": []}
  ]
}
```

或者：

```json
{
  "pages": [
    {
      "page": 8,
      "verdict": "defect",
      "defects": [
        {
          "category": "residue",
          "description": "仍有红色正文格式说明"
        }
      ]
    }
  ]
}
```

仅仅改进错误反馈，例如告诉 Agent“首次调用必须省略 cursor”，只能作为短期辅助，不能成为最终正确性保证。模型仍可能在新会话中忘记反馈或重复错误。

最终原则是：

1. 能由代码确定的流程全部代码化；
2. Agent 只负责无法稳定规则化的视觉和语义判断；
3. Tool 反馈帮助 Agent 修正领域判断，但不承担控制流正确性；
4. 状态机、版本绑定、完整覆盖和停滞熔断共同构成发布兜底。

## 7. 这条经验的产品与工程意义

这不是单纯的 Prompt 优化原则，而是 Agent 产品的系统边界：

- **用户价值**：减少长时间运行后仍无产物的情况；
- **可靠性**：确定性门禁不随模型、会话和上下文变化；
- **成本**：避免重复 Tool 调用和无进展的新会话；
- **可维护性**：Tool 协议修改不需要在 Skill 多处同步说明；
- **可测试性**：状态机、覆盖、失效和熔断可以写成确定性测试；
- **模型可替换性**：不同模型只需要完成领域判断，不必表现出完全相同的协议记忆能力；
- **未来选项**：底层视觉服务仍可使用 cursor，但可以在不影响 Skill 的情况下替换分页实现。

Skill 越接近领域判断手册，代码越接近可靠的执行状态机，整个 Agent 系统才越容易扩展和验收。

## 8. 相关材料

- [学校论文模板整理中的六类通用问题](学校论文模板整理中的六类通用问题.md)
- 候选 Skill：`docs/plans/docfit-school-extract-v2-candidate-skill/SKILL.md`
- 当前实现状态：`docs/status/active/docfit-school-extract-v2.md`
- 失败 E2E 任务：`temp/docfit-school-extract-v2-njau-e2e-final-visual-r1`
- 失败快照：`temp/docfit-school-extract-v2-njau-e2e-final-visual-r1/.claude/skills/docfit-school-extract/SKILL.md`

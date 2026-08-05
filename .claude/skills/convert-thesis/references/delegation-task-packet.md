# 论文转换的可选委派

委派只用于只读分析。在主/子 Agent 分工中，主 Agent 统一承担写入、跨范围依赖、视觉
复核、验证和交付判断；这不表示主 Agent 的物理写入只能经过某一个 SDK 工具。

## 适合拆分的范围

- 互不重叠的稳定章节；
- 独立的对象组或页面范围；
- 不依赖全局编号和分页的局部风险。

目录、节编号、页码、脚注连续性、跨页表格和学生正文到模板区域的放置属于强耦合问题，由主 Agent 统一处理。

## 任务包

每个任务包必须自包含：

```yaml
document_sha256: <current-document-hash>
analysis_scope:
  id: <unit-id>
  description: <明确的章节、对象或页面范围>
  object_refs: [<object-ref>]
  page_evidence_refs: [<existing-page-evidence-ref>]
knowledge_modules:
  - id: <knowledge-id>
    version: <version>
    content_digest: <digest>
    content: <完整模块内容>
task_evidence:
  requirement_refs: [<current-task-rule-ref>]
known_rules: [<already-confirmed-rule>]
dependencies: [<dependency>]
requested_output: unit_analysis_v1
```

子 Agent 只可检查指定文档或读取已有视觉证据；它不生成渲染、不修改或验证文档，也不询问用户。

## 返回与合并

返回必须包含 `status`、`confidence`、`findings`、`confirmed_rules`、`uncertainties`、`dependencies`、`cross_unit_links`、`evidence_requests` 和 `proposed_operations`。

主 Agent 合并时：

1. 核对文档哈希、分析范围、对象引用和证据引用。
2. 把 `proposed_operations` 视为候选操作，重新检查后才可编辑。
3. 统一处理跨范围编号、分页、目录和样式依赖。
4. 对 `needs_more_evidence` 决定是否补充证据后重新分析。
5. 不把局部 `complete` 解释为文档已经完成或可交付。

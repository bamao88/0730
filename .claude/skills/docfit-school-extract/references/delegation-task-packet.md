# 学校材料分析的可选委派

委派只用于材料量较大且分析范围能够清楚隔离的情况。简单材料直接分析，不按页数、对象数或材料类型强制拆分。

## 适合拆分的范围

- 不同来源文件；
- 互不重叠的章节或页面组；
- 独立的模板文字类别；
- 不依赖彼此结论的格式要求。

版本比较、来源优先级和跨附件冲突由主 Agent 统一处理，不拆给相互隔离的单元。

## 任务包

每个任务包必须自包含：

```yaml
document_sha256: <current-document-hash>
analysis_scope:
  id: <unit-id>
  description: <明确的材料和范围>
  object_refs: [<object-ref>]
  page_evidence_refs: [<existing-page-evidence-ref>]
knowledge_modules:
  - id: <knowledge-id>
    version: <version>
    content_digest: <digest>
    content: <完整模块内容>
task_evidence:
  source_refs: [<school-material-evidence-ref>]
known_rules: [<already-confirmed-rule>]
dependencies: [<dependency>]
requested_output: unit_analysis_v1
```

子 Agent 只可检查指定文档或读取已有视觉证据；缺少证据时返回请求，不生成新渲染，也不修改文件。

## 返回与合并

返回必须包含 `status`、`confidence`、`findings`、`confirmed_rules`、`uncertainties`、`dependencies`、`cross_unit_links`、`evidence_requests` 和 `proposed_operations`。

主 Agent 合并时：

1. 核对范围、来源哈希和证据引用仍然有效。
2. 只接收有来源引用的规则。
3. 把跨范围依赖和冲突提升到最终证据。
4. 对 `needs_more_evidence` 决定是否补充证据后重新分析。
5. 不把局部 `complete` 解释为整份材料提取完成。

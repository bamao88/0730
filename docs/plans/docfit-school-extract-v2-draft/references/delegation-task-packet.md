# 学校模板分析的可选委派

委派只用于材料量较大且局部范围能够清楚隔离的情况。简单模板直接分析，不按页数、
对象数或模板类型强制拆分。

## 可委派范围

- 独立来源文件或互不重叠的章节/页面组；
- 一个有明确边界的模板文字类别；
- 不依赖其他范围结论的槽位候选分析；
- 已有页面证据上的局部视觉 finding。

版本选择、来源优先关系、跨范围冲突、编辑、冻结和发布由主 Agent 负责。

## 任务包

```yaml
document_sha256: <current-document-hash>
analysis_scope:
  id: <unit-id>
  description: <bounded-scope>
  object_refs: [<object-ref>]
  page_evidence_refs: [<existing-page-evidence-ref>]
knowledge_modules:
  - id: <knowledge-id>
    version: <version>
    content_digest: <digest>
    content: <selected-content>
task_evidence:
  source_refs: [<current-task-source-ref>]
known_rules: []
dependencies: []
requested_output: unit_analysis_v1
```

Subagent 只使用 inspect 和 visual-review。缺少证据时返回请求，不创建 render、不修改
文档、不生成 manifest，也不把局部 `complete` 解释为模板已经冻结。

## 返回与合并

返回包含 `status`、`confidence`、`findings`、`confirmed_rules`、`uncertainties`、
`dependencies`、`cross_unit_links`、`evidence_requests` 和 `proposed_operations`。

主 Agent 重新核对文档 hash、范围和 evidence refs；只接收有当前任务来源支持的结论，
统一处理跨范围冲突，并自行决定是否编辑、补证或保留 gap。候选操作不是写入授权。

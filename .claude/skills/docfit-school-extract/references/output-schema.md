# 任务证据输出合同

输出不要求固定文件格式，但必须保留以下语义：

```yaml
scope: current_task_only
sources:
  - source_id: school-template
    kind: written_requirement | template | official_example | user_confirmation
    sha256: <source-hash>
    location: <object-ref-or-page-location>
    applicability: <适用范围>
observed_facts:
  - fact: <可直接观察的事实>
    evidence: [<source-and-location>]
confirmed_rules:
  - rule: <已确认规则>
    applies_to: <对象或范围>
    evidence: [<source-and-location>]
conflicts:
  - issue: <冲突>
    evidence: [<source-and-location>]
    resolution: <解决方式或 null>
uncertainties:
  - issue: <未知项>
    evidence_needed: <需要补充的最小证据>
applicability:
  - condition: <院系、学位、语言或材料类型条件>
    result: <适用结论>
    evidence: [<source-and-location>]
template_text_classification:
  - location: <object-ref-or-page-location>
    classification: fixed_content | conditional_content | slot_placeholder | format_instruction | unknown
    condition: <适用条件或 null>
candidate_tool_parameters:
  - target: <格式对象>
    parameter: <候选参数>
    value: <值>
    evidence: [<source-and-location>]
evidence_requests:
  - <需要补充的最小证据>
knowledge_used:
  - id: <knowledge-document-id>
    version: <package-version>
    content_digest: <digest>
```

## 发布前核验

- `scope` 是 `current_task_only`。
- 每项已确认规则至少有一条当前任务来源定位。
- 可观察事实与解释后的规则分开记录。
- 未解决冲突没有同时被写成已确认规则。
- 候选 Tool 参数仍然标记为候选。
- Knowledge 只记录方法来源，不承载学校规则。

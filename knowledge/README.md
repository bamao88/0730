# Knowledge Package

DocFit 只有一个随产品发布、面向所有学校和任务共享的通用论文格式领域知识包。
它提供统一概念、识别方法、解释原则和通用处理模式，不保存任何学校的专属要求、
模板、格式参数、固定文案或人工确认。

可执行的内置包位于：

```text
src/docfit/knowledge/package/v1/
├── manifest.yaml
├── knowledge.md
└── references/
```

本目录只作为人类入口，不再维护 `common/` 与 `schools/` 两套资产，也不接受学校
目录。学校模板、要求文件、官方示例、适用范围和 Agent 推导出的具体规则只属于
当前任务证据；它们不能因为被处理过就自动升级为长期 Knowledge。

通用 Knowledge 的变更必须去除学校名称、精确数值、模板和固定文案，并通过内容
评审、跨学校回归和 package hash/digest 验证后随新的产品版本发布。

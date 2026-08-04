# DocFit Skill 与提示词参考快照

本目录保存 2026-08-04 从本机现有资源中整理出的提示词参考。它只用于后续讨论、对照和重写，不是 DocFit 当前运行时的一部分，也不会被 Agent 自动加载。

## 收录内容

- `codex-skills/docfit-school-extract/`：本机 Codex 的学校模板证据提取 Skill 提示词、界面元数据和引用文档。
- `codex-skills/convert-thesis/`：本机 Codex 的论文转换 Skill 提示词、界面元数据和引用文档。
- `docfit-v3/prompts/`：DocFit V3 当前工作区中的 T3 层级分析提示词与 T4 页面视觉提示词。

详细来源、快照状态和 SHA-256 见 [SOURCE-MANIFEST.md](SOURCE-MANIFEST.md)。

## 范围边界

本快照只收录提示词层：`SKILL.md`、`agents/openai.yaml`、`references/*.md` 和两份 V3 prompt 资源。没有复制：

- Skill 的 Python 执行脚本、缓存和生成产物；
- 学校模板、学生论文、真实任务输入或运行输出；
- DocFit V3 平行 Agent 插件中的四个阶段 Skill；
- 当前项目的业务代码、Knowledge 或长期架构文档。

项目内当前维护的正式 Skill 仍位于 `.claude/skills/`。本目录中的内容不得覆盖正式 Skill，也不得被当成已经批准的架构合同。后续修改时，应先从这里比较可借鉴的判断入口、证据协议、错误恢复和完成条件，再按 DocFit 当前业务边界重新设计。

## 目录结构

```text
docfit-skill-prompt-reference/
├── README.md
├── SOURCE-MANIFEST.md
├── codex-skills/
│   ├── docfit-school-extract/
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml
│   │   └── references/evidence-template.md
│   └── convert-thesis/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       └── references/
│           ├── anchors.md
│           ├── library-contract.md
│           ├── ooxml-recipes.md
│           └── pitfalls.md
└── docfit-v3/
    └── prompts/
        ├── t3_hierarchical_prompt.txt
        └── t4_page_vision_prompt.txt
```

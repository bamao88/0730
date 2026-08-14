# 学校库输入契约

只在校验学校库、读取槽位或确定正文比对边界时阅读本文件。

## 目录与人类验收门

```text
library/<school_id>/<version>/
├── prefill_template.docx
├── slots.yaml
├── requirements.md
└── entry.yaml
```

四个文件缺一不可。`entry.yaml.status` 必须是 `accepted`；`pending_acceptance`、`draft`、缺失或未知状态一律停止转换。`accepted` 只能代表人已经验收过该版本，不能由本 skill 自动补写。

建议的 `entry.yaml`：

```yaml
schema_version: "1.0"
school_id: hunannongye
version: v1
status: accepted
accepted_by: human-reviewer
accepted_at: "2026-07-28"
files:
  prefill_template.docx:
    sha256: "sha256:..."
  slots.yaml:
    sha256: "sha256:..."
  requirements.md:
    sha256: "sha256:..."
source:
  template_sha256: "sha256:..."
```

兼容旧条目时，可接受以下等价形态：

```yaml
prefill_template_sha256: "sha256:..."
slots_sha256: "sha256:..."
requirements_sha256: "sha256:..."
```

转换前对三件套重新计算 SHA-256。忽略可选的 `sha256:` 前缀后逐字比较；任一不一致即停止并报告“学校库资产在验收后被修改”。

## `slots.yaml`

使用稳定的 snake_case 槽位 ID 和可见的双花括号占位符。不要用 Word 内容控件（SDT）表达槽位。

```yaml
schema_version: "1.0"
slots:
  - id: title_zh
    placeholder: "{{title_zh}}"
    required: true
    source:
      field_key: metadata.title.zh
      fallback: "学生原稿封面中的中文题名"
  - id: author
    placeholder: "{{author}}"
    required: true
    source:
      field_key: metadata.student.name
      fallback: "学生原稿封面中的姓名"
  - id: defense_date
    placeholder: "{{defense_date}}"
    required: false
    source:
      field_key: metadata.defense.date
      fallback: null
```

规则：

- `id` 必须匹配 `[a-z][a-z0-9_]*`。
- `placeholder` 必须恰好为 `{{id}}`。
- 每个槽位在前置模板中只出现一次；有意重复显示同一值时，建立不同 ID 并声明相同来源。
- `required: true` 但无法从学生原稿可靠取值时，停止并列为 `needs_review`；不得猜测。
- 保留原始值，不翻译、不改写、不规范化姓名、题名、编号或日期，除非 `requirements.md` 明确要求显示格式且原值可无损恢复。

## `requirements.md`

学校差异全部放在这里，不写进 skill。至少包含：

```markdown
# <学校>论文格式要求

## 页面与分节
...

## 前置页
...

## 正文
...

## 标题与编号
...

## 图、表、公式
...

## 参考文献
...

## 页眉页脚与页码
...

## 内容比对边界

- source_start_regex: `...`
- source_end_regex: `...`
- final_start_regex: `...`
- final_end_regex: `...`

## 模板说明文字关键词

<!-- docfit:instruction-keywords:start -->
- 请删除本行
- 此处填写
<!-- docfit:instruction-keywords:end -->
```

内容边界正则可省略；省略时 `check_content.py` 自动寻找“最后一个摘要标记后的第一个正文标题”到“参考文献末尾”。自动检测返回 `UNKNOWN` 时，必须从本节提供显式正则后重跑，不能把全文件粗略相似当作通过。

说明文字关键词附录必须存在。确实没有说明文字时保留空标记块，证明这是一项明确结论，而不是漏建。关键词应足够具体，避免使用“姓名”“日期”等可能合法出现在学生内容里的短词。

## 输入定位

按以下顺序定位库根目录：

1. 用户明确给出的 `library` 路径；
2. 当前工作区内唯一的 `library/`；
3. 当前工作区父级中唯一且包含目标学校条目的 `library/`。

找到多个候选时停止并请用户选择。不要把 skill 目录当学校库，也不要跨项目猜测同名学校条目。

版本选择规则：

- 用户指定版本时只使用该版本。
- 未指定时，只在 `entry.yaml` 明确声明 `current: true` 或学校目录存在唯一 accepted 版本时自动选择。
- 多个 accepted 版本且没有唯一 current 时停止；不要按目录名或修改时间猜“最新”。

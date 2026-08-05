# 特殊论文部件索引

只读取当前模板实际包含的部件说明。这些 reference 与论文结构对应，不与处理步骤对应。

| 模板中出现的内容 | 读取 |
|---|---|
| 模板说明、示例值、占位文字 | `.claude/skills/docfit-school-extract/references/template-text.md` |
| 封面、扉页、声明、授权页、签章表单 | `.claude/skills/docfit-school-extract/references/front-matter-and-forms.md` |
| 目录、图目录、表目录 | `.claude/skills/docfit-school-extract/references/table-of-contents.md` |
| 分节、页眉页脚、页码和分页边界 | `.claude/skills/docfit-school-extract/references/sections-headers-footers.md` |

同一区域涉及多个部件时可以同时读取相关说明。没有匹配的特殊部件时，按 `SKILL.md`
中的通用模板规则处理，不需要为了完整性加载全部 references。

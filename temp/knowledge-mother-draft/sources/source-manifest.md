# 来源清单

## S-001 · 论文模板树、内容树与确定性样式体系设计

| 字段 | 内容 |
|---|---|
| 原始路径 | `/Users/fl/Desktop/论文模板树、内容树与确定性样式体系设计.md` |
| 工作区快照 | `sources/论文模板树、内容树与确定性样式体系设计.md` |
| SHA-256 | `e5738022f135af5dc4eee07b839caaf382bee90d783a00028de12366ed0f5054` |
| 快照日期 | 2026-08-03 |
| 当前身份 | 通用领域母稿的设计来源，不是正式产品契约 |

后续如果原始文件变化，应建立新的来源条目或新快照，不覆盖这份来源记录。

## S-002 · DocFit v3 内容字段与模板槽位匹配契约

| 字段 | 内容 |
|---|---|
| 原始路径 | `/Users/fl/WXP/docfit_v3/docs/current/content-field-and-slot-contract.md` |
| SHA-256 | `c0ba0c5dc526a248599b5ae14eb45cd3925693c23ff93dea8b1f01b22ae678a5` |
| 核对日期 | 2026-08-03 |
| 吸收内容 | 语义字段与节点形态分离；原始内容与结构化视图并存；图、表、题注、资产、参考文献、附录和 unmapped 节点 |
| 明确排除 | 旧版 `StudentContentArtifact`、`ContentNode`、`TemplateSlot` 字段名、版本和公共 Schema 身份 |

## S-003 · DocFit v3 模板内容角色 ontology

| 字段 | 内容 |
|---|---|
| 原始路径 | `/Users/fl/WXP/docfit_v3/src/docfit/template_generation/ontology.yaml` |
| SHA-256 | `5c294d1f5eb55dcc12f382ac87ed351409c5832b2133188c1514514c8a1fa498` |
| 核对日期 | 2026-08-03 |
| 吸收内容 | fixed、fill、generated、instruction、manual、unknown 等概念的领域区分；unknown 默认保留 |
| 明确排除 | 旧枚举值作为新实现协议、旧 prompt 注入方式和任何运行阶段契约 |

## S-004 · DocFit v3 三份历史模板单元标准

这些材料用于发现跨样本反复出现的候选单元和“论文正文 / 伴随表单”边界，不用于保存或
复用任何学校规则。

| 原始路径 | SHA-256 |
|---|---|
| `/Users/fl/WXP/docfit_v3/standards/targets/hunannongye/v1/template_generation/t2_unit_pagination.standard.yaml` | `d89ce14e09405f6283f36692c897945a915502e85a185ba7513170be711a600c` |
| `/Users/fl/WXP/docfit_v3/standards/targets/nannong-undergraduate/v1/template_generation/t2_unit_pagination.standard.yaml` | `36c7cbb52e8cc49b3c250b55b1265e935ecdcc19b78a2ebd905b57c0bc195234` |
| `/Users/fl/WXP/docfit_v3/standards/targets/pku-graduate/v1/template_generation/t2_unit_pagination.standard.yaml` | `7410affb771fcc5eb239498e6f62b90d8aca64bca1211747310fddabb772587a` |

吸收的只有去学校化后的候选覆盖：封面、声明、摘要、目录、图表目录、正文、参考文献、
附录、成果和致谢，以及任务书、开题、答辩、审批、成绩等伴随材料的存在。具体名称、顺序、
分页、必选性、固定文字和格式全部排除。

## S-005 · 当前正式通用 Knowledge v1

| 文件 | SHA-256 |
|---|---|
| `src/docfit/knowledge/package/v1/knowledge.md` | `fa855a70c6c196814560b2760c33ac3a5084038bec1d47dfa3d47f2045f048bf` |
| `src/docfit/knowledge/package/v1/references/concepts.md` | `0c98691d39dececfff14de703653a2a4b0c8d6c2086fb8ef392cf29a358f6c52` |
| `src/docfit/knowledge/package/v1/references/recognition-methods.md` | `8f86dda68372610d1d72e5b46586365c0bd6b3b388ca228d5f2ed22d5a356365` |
| `src/docfit/knowledge/package/v1/references/interpretation-principles.md` | `5dff8768a9c9e4d1702768eabbadf4b9c8d118045039dd30076b78b34fe27802` |
| `src/docfit/knowledge/package/v1/references/processing-patterns.md` | `b89e1bdad71d70caaf58b9978f97a37715ee236eb9a58d5b89653615d74990e4` |

这些文件是当前产品边界校验来源，不是被母稿覆盖的旧版本。母稿保持工作区草稿身份，
本轮不修改正式 Knowledge v1，也不把历史学校结论写回产品包。

## 来源使用结论

| 候选内容 | 母稿处理 |
|---|---|
| 通用论文单元、字段、复合关系 | 吸收并去实现化 |
| 原始内容、规范化视图、来源追溯 | 吸收为领域原则 |
| 固定/填充/生成/说明/人工/未知 | 吸收为所有权与处置维度，不沿用旧 Schema |
| 学校名称、顺序、必选性、固定文字、格式参数 | 排除，只能是当前任务证据 |
| 旧工作流、阶段名、Agent 协议、公共数据结构 | 排除 |
| 样式角色、样式属性和默认值 | 不吸收旧样式树或“系统基础样式”兜底；母稿只固定后续样式观测、逐属性来源、确定性标准补全和 unresolved 的合同边界 |

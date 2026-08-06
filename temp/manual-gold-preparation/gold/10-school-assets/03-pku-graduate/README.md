# 北京大学研究生 Gold Word 资产

本目录保存北京大学研究生模板的派生 Gold。学校原始 Word 单独保存在 `00-inputs/`，不得用干净模板覆盖。

## Word 文件

| 角色 | 路径 | SHA-256 | 入库时间 | 状态 |
|---|---|---|---|---|
| 学校源 Word | [`../../00-inputs/schools/pku-graduate__source-template.docx`](../../00-inputs/schools/pku-graduate__source-template.docx) | `720372f4e70b75ade60a302e95abc870e47d47ac7e6cbf0e5a16ceef4d619e14` | 2026-08-04 | `hash-bound-input` |
| 可填写干净 Word | [`pku-graduate__fillable-template.docx`](pku-graduate__fillable-template.docx) | `2328d529eef8eedc110783c106d8a9dbcf54eb230f5105c4e7d3fb88c64992d8` | 2026-08-05 | `gold` |

## 逻辑分页文件

[`logical-pages/`](logical-pages/) 于 2026-08-04 以 `gold` 状态入库，保存 12 个源内容逻辑单元及 [`unit-manifest.json`](logical-pages/unit-manifest.json)。源 Word 第 2、4 个物理页属于整本双面排版的虚拟补页，不单独保存为逻辑单元。

可填写干净 Word 与源逻辑块 Gold 的职责不同：它还从源文件的说明文字和真实脚注中恢复“实名评审专家名单”条件页；普通纵向正文只保留一个完整章节示例，另保留一个横向可选分节。

## 验收证据

以下证据于 2026-08-05 入库，管理状态为 `validation-evidence`，不计入核心 Gold 文件数量：

- [Microsoft Word 验收 PDF](../../90-validation-evidence/03-pku-graduate/pku-graduate__fillable-template-word-validation.pdf)：17 页，第 13 页横向，实名模式空白页为第 4、10 页。
- [40 项验证 JSON](../../90-validation-evidence/03-pku-graduate/pku-graduate__fillable-template-verification.json)：状态 `PASS`。
- [分页独立审计](../../90-validation-evidence/03-pku-graduate/pku-graduate__pagination-audit.md)：记录 Gold 12 单元与语义干净模板的边界。

根级资产状态、候选来源和哈希绑定分别见 [`../../manifest.csv`](../../manifest.csv) 与 [`../../hash-bindings.sha256`](../../hash-bindings.sha256)。

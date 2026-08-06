# Gold 论文转换资产目录与命名规范

## 1. 范围与数量

本目录保存原始输入的字节级副本和已经确认的标准产物，不保存一般过程稿、预览件、复核件或问题报告。经 Human 明确要求进入标准资产路径、但尚未完成验收的模板，必须在 `manifest.csv` 中保持 `candidate`，不能计入已验收 Gold。交叉转换件的 Gold 表示“转换行为及预期缺失策略已经验收”，不等于论文已具备直接提交条件；若学生原稿缺少模板必填内容，标准产物仍可作为 Gold 基准，但必须在 manifest 和本 README 中标记 `document_state=review_draft`。

原始输入共 6 个：

- 3 个学校模板原件；
- 3 个学生论文原件。

外层原件保留不动，同时用规范名复制到 `gold/00-inputs/`。外层原件与 Gold 副本必须具有相同的 SHA-256。

`gold/` 最终应有 27 个核心文件：

| 资产组 | 计算方式 | 数量 |
|---|---:|---:|
| 原始输入 | 3 个学校模板 + 3 个学生论文 | 6 |
| 学校基础件 | 3 个学校 ×（逻辑单元分页文档、可填写空白模板、带样式字段映射文件） | 9 |
| 学生内容件 | 3 个学生 × 内容提取处理文档 | 3 |
| 交叉转换件 | 3 个学校 × 3 个学生 | 9 |
| 合计 |  | 27 |

`README.md`、`manifest.csv`、`hash-bindings.sha256` 和验收证据属于管理文件，不计入 27 个核心文件。

## 2. 固定项目标识

项目内部使用以下稳定 ID。ID 只用于目录、文件名和程序，不随中文显示名变化。

| school_id | 中文显示名 | 层次 |
|---|---|---|
| `hunau-undergraduate` | 湖南农业大学 | 本科 |
| `njau-undergraduate` | 南京农业大学 | 本科 |
| `pku-graduate` | 北京大学 | 研究生 |

学生统一使用 `student-001`、`student-002`、`student-003`。文件名中不写真实姓名。

## 3. 目录结构

### 3.1 入库时间与状态

下表以 `manifest.csv` 为状态真值；没有正式入库日期的项目用 `—` 表示。验收证据不属于 27 个核心文件，因此使用管理状态 `validation-evidence`。

| 目录或资产 | 已有数据 | 入库时间 | 状态 |
|---|---|---|---|
| `00-inputs/schools/` | 3 个学校源 Word | 2026-08-04 | `hash-bound-input` |
| `00-inputs/students/` | 3 个学生源 Word | 2026-08-04 | `hash-bound-input` |
| `10-school-assets/01-hunau-undergraduate/logical-pages/` | 10 个逻辑单元及 manifest | 2026-08-04 | `gold` |
| `10-school-assets/01-hunau-undergraduate/hunau-undergraduate__fillable-template.docx` | 湖南农大可填写干净 Word | — | `candidate`；已落标准路径并绑定 hash，待 Human 验收 |
| `10-school-assets/02-njau-undergraduate/logical-pages/` | 10 个逻辑单元及 manifest | 2026-08-04 | `gold` |
| `10-school-assets/02-njau-undergraduate/njau-undergraduate__fillable-template.docx` | 南京农大可填写干净 Word | — | `candidate`；已落标准路径并绑定 hash，待 Human 验收 |
| `10-school-assets/03-pku-graduate/logical-pages/` | 12 个逻辑单元及 manifest | 2026-08-04 | `gold` |
| `10-school-assets/03-pku-graduate/pku-graduate__fillable-template.docx` | 北大可填写干净 Word | 2026-08-05 | `gold` |
| `90-validation-evidence/03-pku-graduate/` | Word PDF、40 项验证 JSON、分页审计 | 2026-08-05 | `validation-evidence` |
| 三校带样式字段映射 | 尚未制作 | — | `missing` |
| `20-student-assets/` | 3 个结构化学生内容件尚未制作 | — | `missing` |
| `30-cross-conversions/02-njau-undergraduate/` | 南农 3 个学生转换基准稿 | 2026-08-05 | `gold`；文档状态均为 `review_draft` |
| 其他学校交叉转换件 | 尚未生成 | — | `missing` |

### 3.2 实际目录

方括号中的内容是入库状态和日期注释，不是文件名。

```text
gold/
├── README.md
├── manifest.csv
├── hash-bindings.sha256
├── 00-inputs/
│   ├── schools/
│   │   ├── hunau-undergraduate__source-template.docx  [hash-bound-input · 2026-08-04]
│   │   ├── njau-undergraduate__source-template.docx  [hash-bound-input · 2026-08-04]
│   │   └── pku-graduate__source-template.docx  [hash-bound-input · 2026-08-04]
│   └── students/
│       ├── student-001__source-thesis.docx  [hash-bound-input · 2026-08-04]
│       ├── student-002__source-thesis.docx  [hash-bound-input · 2026-08-04]
│       └── student-003__source-thesis.docx  [hash-bound-input · 2026-08-04]
├── 10-school-assets/
│   ├── README.md
│   ├── 01-hunau-undergraduate/
│   │   ├── hunau-undergraduate__fillable-template.docx  [candidate · hash-bound · 待验收]
│   │   └── logical-pages/  [gold · 2026-08-04]
│   ├── 02-njau-undergraduate/
│   │   ├── njau-undergraduate__fillable-template.docx  [candidate · hash-bound · 待验收]
│   │   └── logical-pages/  [gold · 2026-08-04]
│   └── 03-pku-graduate/
│       ├── README.md
│       ├── pku-graduate__fillable-template.docx  [gold · 2026-08-05]
│       └── logical-pages/  [gold · 2026-08-04]
│           ├── 01-cover.docx
│           ├── 02-copyright.docx
│           ├── 03-abstract-cn.docx
│           ├── 04-abstract-en.docx
│           ├── 05-toc.docx
│           ├── 06-list-of-figures.docx
│           ├── 07-list-of-tables.docx
│           ├── 08-body.docx
│           ├── 09-references.docx
│           ├── 10-appendix-achievements.docx
│           ├── 11-acknowledgement.docx
│           ├── 12-declarations.docx
│           └── unit-manifest.json
├── 20-student-assets/
│   ├── student-001/  [missing]
│   ├── student-002/  [missing]
│   └── student-003/  [missing]
├── 30-cross-conversions/
│   ├── 01-hunau-undergraduate/  [missing]
│   ├── 02-njau-undergraduate/  [gold · 2026-08-05；document_state=review_draft]
│   │   ├── njau-undergraduate__student-001__converted.docx
│   │   ├── njau-undergraduate__student-002__converted.docx
│   │   └── njau-undergraduate__student-003__converted.docx
│   └── 03-pku-graduate/  [missing]
└── 90-validation-evidence/
    └── 03-pku-graduate/  [validation-evidence · 2026-08-05]
        ├── pku-graduate__fillable-template-word-validation.pdf
        ├── pku-graduate__fillable-template-verification.json
        └── pku-graduate__pagination-audit.md
```

`90-validation-evidence/` 可保存 Word 验收 PDF、截图或校验 JSON，但不计入 27 个核心 Gold 文件。

`10-school-assets/<school>/logical-pages/` 保存已经确认的独立逻辑单元 Word 集合。统一的单元判断、分页控制归一化、边界空段归属和 Word 视觉验收规则见 [`10-school-assets/README.md`](10-school-assets/README.md)。

## 4. 标准文件名

### 原始输入副本

```text
<school-id>__source-template.docx
<student-id>__source-thesis.docx
```

原件继续保留外层原名；进入 Gold 的副本采用规范名，但内容必须字节级不变。

### 每个学校 3 个基础件

```text
<school-dir>/logical-pages/*.docx
<school-dir>/logical-pages/unit-manifest.json
<school-id>__fillable-template.docx
<school-id>__styled-field-mapping.xlsx
```

- `logical-pages`：学校拥有的独立逻辑单元 Word 集合；稳定文件名采用 `NN-<unit-id>.docx`，`unit-manifest.json` 绑定顺序、源块范围、页数和哈希。整个集合在资产计数中仍按一个学校基础件计；
- `fillable-template`：保留学校固定内容、提供唯一填写槽位的空白论文模板；
- `styled-field-mapping`：学生内容字段到模板槽位的映射，并同时记录目标样式、逻辑单元和填充规则。

### 每个学生 1 个内容件

```text
<student-id>__extracted-content.docx
```

此文件只保存从学生原文识别、清洗并结构化后的内容，不混入任何目标学校的固定页面。

### 学校与学生交叉转换件

```text
<school-id>__<student-id>__converted.docx
```

每个学校目录内固定有 3 个转换件，因此 3 个学校合计 9 个。

## 5. 命名规则

1. 全部使用小写 ASCII；词内用单连字符 `-`，不同维度用双下划线 `__`。
2. 扩展名小写；正式 Gold 文档使用 `.docx`，映射表使用 `.xlsx`。
3. Gold 文件名不出现“最终版、交付版、修正版、已复核、待补信息、预览、new、final、v2”等状态词。
4. 同一标准路径永远只允许一个当前 Gold；版本、审核状态、日期和 SHA-256 写入 `manifest.csv` 或版本控制，不写进文件名。
5. 过程稿放在 `gold/` 之外。若临时文件确需命名，可使用 `__work-r01`、`__review`、`__preview`，但通过验收后必须去掉状态后缀再进入 Gold。
6. PDF 只作为验收证据，不与 DOCX 核心 Gold 混放。

## 6. 哈希绑定规则

1. `manifest.csv` 的 `source_or_candidate` 记录外层原件路径，`canonical_path` 记录 Gold 副本路径。
2. `sha256` 记录外层原件与 Gold 副本共有的 SHA-256；两者不一致时绑定失败。
3. `hash-bindings.sha256` 使用标准 `shasum` 格式，保存当前实际存在的核心文件哈希。
4. 在 `gold/` 目录执行 `shasum -a 256 -c hash-bindings.sha256` 可验证文件是否被替换或修改。
5. 后续每个派生产物晋升为 Gold 时，也必须同步写入 `manifest.csv` 和 `hash-bindings.sha256`。

## 7. 现有文件如何归类

- 外层 `school-template-*.docx`：学校模板原件；保留原名，同时复制到 `00-inputs/schools/` 并绑定哈希。
- 外层 `student-content-real-student-00X.docx`：学生论文原件；保留原名，同时复制到 `00-inputs/students/` 并绑定哈希。
- 外层 `school-template-*-clean.docx`：可填写空白模板候选；验收通过后复制到对应标准路径并改为 `__fillable-template.docx`。
- 外层带“修正版、最终复核版、交付版、待补信息、预览”的文件：均视为过程件或候选件；只有被明确选中的一份才能晋升为对应的 `__converted.docx`。
- 复盘、审计、问题总结文档：属于项目资料，不属于核心 Gold。

## 8. 晋升为 Gold 的最低条件

- 文件内容与对应学校、学生 ID 一致；
- 逻辑单元分页、固定学校页面及填写槽位已经检查；
- DOCX 能正常打开，目录和页码在目标 Word 环境中更新后正常；
- 不含其他学生内容、旧模板示例、临时批注或个人元数据；
- `manifest.csv` 中状态改为 `gold`，并填写验收日期和 SHA-256；
- 标准路径中不存在第二个同类文件。

对于“输入本身缺少必填内容”的转换基准，红色必填提示是正确输出而不是转换失败。此类文件可以晋升为 Gold 基准，但 `notes` 必须记录 `document_state=review_draft`、待补单元以及是否保留批注/修订；在学生补齐内容前不得称为可直接提交的 `final`。

## 9. 当前状态

6 个原始输入已复制进 `00-inputs/`，并完成外层原件与 Gold 副本的 SHA-256 一致性绑定。`schools/` 和 `students/` 分别直接平行存放 3 个源 Word，不再按学校或学生嵌套案例子目录。北京大学源 Word 位于 `00-inputs/schools/pku-graduate__source-template.docx`，与外层原件字节级一致，SHA-256 为 `720372f4e70b75ade60a302e95abc870e47d47ac7e6cbf0e5a16ceef4d619e14`。

三所学校的逻辑单元分页集合已经晋升为 Gold：湖南农业大学本科 10 个单元、南京农业大学本科 10 个单元、北京大学研究生 12 个单元。每份 DOCX 和每个 `unit-manifest.json` 均写入 `hash-bindings.sha256`。

湖南农业大学和南京农业大学的可填写干净模板已按标准路径复制到各自 `10-school-assets/<school>/` 目录，并与外层 clean 候选完成字节级 SHA-256 绑定。两份文件仍保持 `candidate`：把文件放入 Gold 资产树不等于通过 Human 验收或自动晋升为 Gold。

北京大学研究生可填写空白模板已于 2026-08-05 晋升为 Gold，标准路径为 `10-school-assets/03-pku-graduate/pku-graduate__fillable-template.docx`。该模板从说明文字和脚注恢复实名评审条件页，普通纵向正文只保留一个完整章节示例，另保留一个横向可选分节；Microsoft Word 验收为 17 页，第 13 页横向。对应 Word PDF、40 项验证 JSON 和分页独立审计保存在 `90-validation-evidence/03-pku-graduate/`。

南京农业大学 3 份学生转换基准稿已于 2026-08-05 晋升到 `30-cross-conversions/02-njau-undergraduate/`。三份最终字节均通过 `layout_contract`、`conversion_integrity`、`internal_links`，并与 Microsoft Word 直接打开及全页复核时锁定的 SHA-256 一致。它们作为转换结果 Gold 已验收，但均保留模板缺失策略产生的待补信息，因此 `document_state=review_draft`：student-001 尚有学术成果选填及一处双语表题提示；student-002 尚缺必填致谢并有附录/成果选填提示；student-003 的致谢为 `present_but_suspicious`，同时按要求保留 9 条批注、11 个插入和 10 个删除节点。

按“逻辑分页集合计为一个学校基础件”的核心资产口径，当前已有 13/27 个**已验收**核心文件：6 个原始输入、3 个学校逻辑分页集合、1 个北大可填写模板和 3 个南农交叉转换件。湖南农大和南京农大的 2 个可填写模板虽已落入标准路径，但仍是 `candidate`，不计入这 13 个 Gold。

两份候选可填写模板、字段映射、学生内容件和其他交叉转换件仍按 `manifest.csv` 的实际状态管理。

## 10. 分页 Gold 校对集

后续学校模板提取器必须使用 `10-school-assets/README.md` 和三校 `logical-pages/unit-manifest.json` 校对逻辑单元与分页结果。核心原则如下：

1. 先判断内容所有权和逻辑单元，再判断物理分页；
2. 章节标题、自动分页和 `w:lastRenderedPageBreak` 不能单独构成单元边界；
3. 单元边界处的手动分页、段前分页和分节控制要由独立文件边界归一化；
4. `oddPage/evenPage` 是整本双面打印规则，不能成为独立单元白页；
5. 空段必须判定所有权，不能批量删除；
6. 独占页整页比较，共页单元按拥有区比较；最终真值来自 Microsoft Word。

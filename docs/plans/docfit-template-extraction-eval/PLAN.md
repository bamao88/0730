# 模板提取静态 E2E Eval 实施计划

> 状态：用户已批准开始实施；W0/G1 已完成，三校 candidate case 目录已物化，W1–W5 待继续
> 上层合同：[DESIGN.md](DESIGN.md)
> 本计划负责：实施顺序、文件责任、逐代码测试、停止门和完成证据
> 本计划不负责：重新设计模板提取流程、执行正式填写、自动批准 Gold 或宣称 M3 完成

## 0. 计划结论

本模块按一条离线、确定性的纵向链路实施：

```text
schema 与简单样本
    → 共享数据模型与输入契约
    → DOCX 共享事实分析
    → Actual—Gold 对齐
    → protected / slot / remove 断言
    → 评分与报告
    → Eval 独立 runner 与 run_eval.py
    → 三校 Gold case 接入
```

计划固定以下工程选择：

1. 所有新 Eval 代码、测试和运行产物位于 `evals/template-extraction/`；不修改
   `src/docfit/**`，也不 import `docfit` 产品包。
2. 用户入口只有 `evals/template-extraction/run_eval.py`，不扩展产品 `docfit` CLI。
3. Eval 拥有独立 `pyproject.toml` 和 `uv.lock`；Eval-only 依赖不进入产品 dependency graph。
4. Actual 模板和 Actual 填写契约由每次被测运行显式传入；case 固定引用 Gold、Registry、
   标记协议、Eval 配置和评分版本。
5. 必需文档事实由 Eval 自有 OOXML 分析层确定性读取；不调用产品 package、inspection、
   ooxml 或 OfficeCLI adapter。
6. protected、slot 和 remove 评测器只消费 Eval 共享事实，不重复解析 DOCX。
7. 分数与门禁结论分开：分数用于诊断，任何硬失败仍得到 `FAIL`。
8. 所有测试先使用极小的合成 DOCX 和 YAML/JSON 样本；不调用 Agent、Adobe、Word GUI
   或正式填写链路。
9. 每个新增代码文件至少准备 3 个测试 case。简单参数化 case 可以
   复用同一个 fixture，但每个 case 必须有独立输入变化和独立预期。

全局目标是“产品不承载 Eval 代码”。仓库当前已有 `src/docfit/evals/` 和产品
`docfit eval --suite core`，属于早期遗留边界；本模块不复用也不扩大它。把旧 core Eval
迁出会同时改变现有产品 CLI、测试和长期文档，必须用独立原子切换计划处理，不能夹带
在模板提取质量 Eval 中。因而本计划完成后，新模块已完全解耦，但仓库级旧 core 迁移仍
是一个显式后续架构事项。

## 1. 测试责任的精确定义

### 1.1 “每个代码至少 3 个测试”的口径

本计划中的“代码”包括：

- `evals/template-extraction/` 中新增的所有运行 `.py` 文件；
- 公开导出用的 `__init__.py`；
- 合成样本生成器；
- 机器消费的 schema 和评分配置。

不要求为以下内容递归增加测试：

- 测试函数自身；
- 静态 DOCX、YAML、JSON fixture 文件；
- 只包含说明文字的 README；
- 本模块完全不修改的旧代码。

如果实施时新增了本计划未列出的生产代码文件，该文件在合入前也必须登记至少 3 个
测试 case。不能通过把逻辑移动到“helper”或私有文件来绕过测试责任。

如果实施需要修改 `src/docfit/**`、产品 CLI 或产品测试，说明当前解耦合同不完整；必须
停止当前工作包并回到设计层提交用户决策，不能以“补 3 个测试”为由直接修改产品代码。

### 1.2 简单样本原则

每个样本只引入一个主要变量：

- 正例尽量只有一个受保护标签和一个填写槽；
- 反例只改变一段文字、一个属性、一个槽或一个对象；
- 不使用整份学校模板证明底层单元逻辑；
- 测试报告只断言当前模块责任，不顺带断言上游 Agent 行为；
- 测试运行不访问网络，不读取凭据，不消耗 Adobe Document Transaction。

允许一个 pytest 函数使用 3 组参数形成 3 个 case；报告中必须能看到每组独立的 case ID。

### 1.3 测试层次

| 层次 | 证明什么 | 不证明什么 |
|---|---|---|
| Unit | 单个模型、解析器、分析器、对齐器、评测器、评分器和报告器的确定性行为 | 完整 CLI 接线或三校 Gold 正确性 |
| Contract | CLI 参数、case/schema、Registry 绑定、报告 schema 和退出语义 | 复杂真实模板质量 |
| Integration | 一个最小 Actual—Gold case 能从 CLI 运行到两份报告 | 上游 Agent、Adobe、Word 视觉和填写行为 |
| School case | 三所学校的已确认 Gold 可被加载、绑定并评分 | 候选自动晋升为 Gold或 M3 完成 |

## 2. 最小样本目录

实施时新增：

```text
evals/template-extraction/fixtures/
├── build_samples.py
├── manifest.yaml
├── S00-minimal-pass/
│   ├── actual-template.docx
│   ├── actual-contract.yaml
│   ├── gold-template.docx
│   └── gold-contract.yaml
├── S01-protected-text-changed/
├── S02-protected-style-changed/
├── S03-slot-missing/
├── S04-slot-extra/
├── S05-slot-field-wrong/
├── S06-slot-boundary-wrong/
├── S07-ambiguous-anchor/
├── S08-forbidden-residue/
├── S09-protected-image-missing/
├── S10-unsupported-object/
├── S11-invalid-input/
├── S12-simple-table-structure/
└── S13-simple-formula-field-bookmark/
```

样本含义固定为：

| ID | 内容 | 唯一主要变化 | 预期 |
|---|---|---|---|
| S00 | 一个“姓名：”受保护标签、一个内容控件槽、一个最小契约 | Actual 与 Gold 完全一致 | `PASS`, 100 分 |
| S01 | 复制 S00 | Actual 把“姓名：”改成“学生：” | `protected.content` 失败 |
| S02 | 复制 S00 | Actual 槽前标签字号改变 | `protected.style` 失败 |
| S03 | 复制 S00 | Actual 删除唯一槽及契约项 | slot recall 降低并硬失败 |
| S04 | 复制 S00 | Actual 新增一个 Gold 未声明的槽 | slot precision 降低并硬失败 |
| S05 | 复制 S00 | Actual alias/contract 改成另一个已注册字段 | `slot.field_mapping` 失败 |
| S06 | 复制 S00 | Actual 槽边界吞入冒号 | `slot.boundary` 失败 |
| S07 | 两个相同“姓名：”标签 | locator 缺少可唯一化 occurrence | `AMBIGUOUS` / `UNKNOWN` |
| S08 | 复制 S00 | Actual 保留 Gold remove 声明的“请在此填写” | 禁止残留硬失败 |
| S09 | 一个受保护的一像素 PNG | Actual 删除图片关系 | `protected.object` 失败 |
| S10 | 一个 v1 暂不支持的可见对象 | 分析器只能确认存在、不能解析语义 | `UNKNOWN`，覆盖率下降 |
| S11 | 最小坏输入集合 | DOCX 缺主 part、契约缺字段、Registry hash 错误 | 输入失败且不出评分报告 |
| S12 | 一个 2×2 表格和一次简单合并 | Actual 与 Gold 相同或只移动单元格 | 结构正反例 |
| S13 | 一个最小公式、域和书签 | 分别保留或删除一个对象 | 对象分析正反例 |

`build_samples.py` 只能生成合成测试资产，不生成或更新正式 Gold。两次运行必须产生相同
canonical YAML/JSON 和相同 DOCX 事实；DOCX ZIP 元数据时间戳差异不得进入比较事实。

## 3. 工作包与实施顺序

### W0：冻结 schema、评分配置和合成样本

负责文件：

```text
evals/template-extraction/pyproject.toml
evals/template-extraction/uv.lock
evals/template-extraction/schemas/*.schema.json
evals/template-extraction/config/scoring-v1.yaml
evals/template-extraction/fixtures/build_samples.py
evals/template-extraction/fixtures/**
```

工作内容：

1. 建立 Eval 独立 Python 项目和锁文件；依赖中不得包含本地 `docfit` 产品包、Claude SDK
   或 Adobe SDK。
2. 定义 case、fill contract、Registry、Eval config 和 report schema。
3. 把设计中的八个分项、100 分权重、硬失败和 `UNKNOWN` 写入 `scoring-v1.yaml`。
4. 生成 S00–S13 的小型样本和 manifest。
5. 为每个 fixture 记录用途、预期结论和文件 hash。
6. 禁止正式代码依赖 Temp 路径；Temp 只用于以后人工准备三校 case。

退出门：

- 所有 schema 都有正例、缺字段反例和错误值反例；
- Eval lock 可独立校验，且不安装产品包或产品专属运行依赖；
- scoring-v1 八个维度齐全且权重总和为 100；
- S00–S13 可重复生成，DOCX package 可解析；
- 不含真实学生内容或学校私密信息。

### W1：共享模型与输入契约

负责文件：

```text
evals/template-extraction/template_extraction_eval/models.py
evals/template-extraction/template_extraction_eval/contracts.py
evals/template-extraction/template_extraction_eval/__init__.py
```

工作内容：

1. 定义 status、owner、dimension、locator、事实、assertion、issue、score、coverage 和 report
   模型。
2. 加载 case、Actual/Gold contract、Registry snapshot 和 scoring config。
3. 校验 `w:alias == field_id == Registry canonical field_id`。
4. 校验模板 hash、Registry ID/version/hash、schema version、唯一 slot/region ID 和定位器。
5. 返回结构化输入错误；输入失败时不生成质量分数。

退出门：

- S00 可形成完整内部模型；
- S11 的三类错误均被独立拒绝；
- 模型可以稳定序列化且不包含整篇文档正文。

### W2：共享 DOCX 事实分析

负责文件：

```text
evals/template-extraction/template_extraction_eval/facts/__init__.py
evals/template-extraction/template_extraction_eval/facts/reader.py
evals/template-extraction/template_extraction_eval/facts/content.py
evals/template-extraction/template_extraction_eval/facts/structure.py
evals/template-extraction/template_extraction_eval/facts/effective_style.py
evals/template-extraction/template_extraction_eval/facts/objects.py
```

工作内容：

1. 以只读方式解析 document、header、footer 和关系 parts。
2. 建立文本、标点、空格、换行、内容控件和非文本 token。
3. 建立 story/section/paragraph/run/table/row/cell/textbox/range 结构事实。
4. 计算 docDefaults、basedOn、命名样式、直接格式、容器和页面的有效样式。
5. 建立图片、OMML、域、书签和合并单元格事实。
6. 对不支持的可见对象显式记录 `UNKNOWN`，不静默跳过。

W2 不 import 或修改 `src/docfit/tools/package.py`、`inspection.py`、`ooxml.py` 或产品
adapter。若 Eval 自有原语不足，应在 `template_extraction_eval/facts/` 内补齐并增加对应
测试；如果只能通过修改产品代码解决，必须停止 W2 并回到设计层重新审批解耦边界。

退出门：

- 同一个分析入口同时处理 Actual 和 Gold；
- S00、S09、S12、S13 的事实可稳定序列化；
- S10 明确产生能力缺口而不是 `PASS`。

### W3：对齐与三类断言

负责文件：

```text
evals/template-extraction/template_extraction_eval/alignment.py
evals/template-extraction/template_extraction_eval/evaluators/__init__.py
evals/template-extraction/template_extraction_eval/evaluators/protected.py
evals/template-extraction/template_extraction_eval/evaluators/slots.py
evals/template-extraction/template_extraction_eval/evaluators/forbidden_residue.py
```

工作内容：

1. 先按 region_id/slot_id 对齐，再用结构路径、tag、锚点和 occurrence 验证。
2. 多个同等候选返回 `AMBIGUOUS`，不能选择第一个。
3. protected 分别输出内容、结构、样式和对象断言。
4. slots 分别输出 inventory、location、boundary、field mapping 和 value style 断言。
5. remove 只检查 Gold 明确声明的禁止残留，不能自行猜测应删除内容。

退出门：

- S01–S09 每个样本只归因到预期主维度；
- 一个错误不会因为另一维度得分高而消失；
- S07、S10 的不可判定路径保持 `UNKNOWN`。

### W4：评分与报告

负责文件：

```text
evals/template-extraction/template_extraction_eval/scoring.py
evals/template-extraction/template_extraction_eval/reporting.py
```

工作内容：

1. 实现八个固定分项和两个 50 分视角。
2. slot inventory 使用 precision、recall、F1；其他维度使用 Gold 断言通过率。
3. 实现 `analysis_coverage`、provisional score 和硬失败判定。
4. 从同一个 report model 生成 JSON 和 Markdown。
5. issue 稳定排序，默认不复制整篇正文。

退出门：

- S00 为 `PASS` 且 100 分；
- S01–S09 为 `FAIL`，分数能说明损失位置；
- S10 为 `UNKNOWN` 且 provisional；
- JSON 通过 report schema，Markdown 与 JSON 分数和 issue 数一致。

### W5：Eval 独立 runner 与入口

负责文件：

```text
evals/template-extraction/run_eval.py
evals/template-extraction/template_extraction_eval/runner.py
evals/template-extraction/README.md
evals/README.md
```

工作内容：

1. runner 只编排 W1–W4，不重复实现解析和评分。
2. `run_eval.py` 只解析独立 CLI 参数并调用同目录 runner；禁止 import `docfit`。
3. PASS 退出码为 `0`；FAIL 和 UNKNOWN 均为非零 `2`，具体状态以 JSON report 为准。
4. 输入/schema 错误输出结构化诊断，且不发布伪质量报告。
5. 默认把报告写入 `evals/template-extraction/.runs/<run-id>/<case-id>/`；显式
   `--output-dir` 时只写指定授权目录。

退出门：

- S00、S01、S10 分别走通 PASS、FAIL、UNKNOWN CLI 路径；
- `src/docfit/**` 文件 hash 和产品 CLI help 均不变化；
- 静态 import scan 证明 Eval 包不依赖 `docfit`；
- 输入文件 hash 在运行前后相同；
- 同输入重复运行的 JSON 业务内容一致，只有明确列出的 run metadata 可变化。

### W6：接入三个学校的 Gold case

负责目录：

```text
evals/template-extraction/cases/
├── 01-hunau-undergraduate/
├── 02-njau-undergraduate/
└── 03-pku-graduate/
```

工作内容：

1. 从 Temp 候选包读取 `fillable-template.docx`、`template-spec.yaml`、validation report、
   manifest 和 hash；按用户批准的最终目录先物化 case，但保持 candidate 状态。
2. 未通过 Human readiness 时，`case_status/gold_review/fill-contract.status` 必须分别为
   `candidate/candidate/candidate_pending_human_acceptance`，`expected_verdict` 固定为
   `INPUT_ERROR`；路径位于 `gold/` 不构成 Gold 晋升。
3. Human 确认后，原地把模板和契约作为 accepted Gold 冻结，并记录 reviewer、日期、
   来源 hash、Registry 绑定和已清零的 blockers；物化脚本不得覆盖 accepted case。
4. 每个 case 固定引用同一 Registry ID/version/hash 和 scoring-v1。
5. 为每校准备三个最小回归：自比较通过、单个 protected 文字变更失败、单个字段映射
   变更失败。反例使用测试副本，不修改 Gold。

进入 accepted Gold 与学校评分回归的门：

- `human_acceptance` 已确认；
- Git/CI 存储权限已明确；
- 模板无真实学生内容；
- 当前 validation report 中的失败已经修复或有明确人工裁决；
- Gold hash 与 fill contract 中的 snapshot binding 一致。

如果任一学校尚未满足进入门，最终目录可以作为 candidate 数据包存在，W0–W5 仍可用
合成样本完成；该学校不能进入评分、通过率或自比较 PASS，也不能通过降低 schema、把
`INPUT_ERROR/UNKNOWN` 改成 `PASS` 强行晋升。

退出门：

- 三个 case 均可加载并验证 Registry/hash/locator；
- 三校自比较均为 `PASS`；
- 每校两个单错误副本均在正确维度得到 `FAIL`；
- 未修改任何 Gold 文件。

### W7：全量验证、文档与生产接入裁决

工作内容：

1. 运行本模块 unit、contract、integration 和三校 case。
2. 运行项目全量 ruff、mypy、pytest、build、lock 和 doctor。
3. 更新 `evals/README.md`、本设计、受影响的 00/02/03/06 和 active capsule。
4. 删除被新模块取代的临时 Eval 依赖或重复 schema；不保留双入口和兼容副本。
5. 单独呈现 M3/真实样本/人工复核完成情况，不因本静态模块通过而宣称 M3 完成。

退出门：见第 8 节。

## 4. 逐生产代码测试矩阵

以下每个文件至少 3 个 case。实施可以增加 case，不能少于本表。

### 4.1 入口、公共 API 与核心模型

| 生产代码 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| `evals/template-extraction/run_eval.py` | `ENTRY-01` 完整参数解析并调用本地 runner | `ENTRY-02` 缺 case 或 Actual 参数被拒绝 | `ENTRY-03` 不 import `docfit`；PASS 返回 0、FAIL/UNKNOWN 返回 2 |
| `template_extraction_eval/__init__.py` | `TAPI-01` 导出 runner | `TAPI-02` 导出 report/result 类型 | `TAPI-03` import 不读取 DOCX、不创建输出目录、不加载产品包 |
| `models.py` | `MOD-01` 构造 PASS assertion/score | `MOD-02` issue 含 locator、expected、actual 并稳定序列化 | `MOD-03` UNKNOWN/provisional/coverage 组合合法，非法 status 被拒绝 |
| `contracts.py` | `CON-01` S00 case/contract/Registry 全部加载 | `CON-02` S11 缺字段或重复 ID 被拒绝 | `CON-03` Registry hash、alias/field 或 template hash 不一致被拒绝 |

### 4.2 共享事实分析代码

| 生产代码 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| `facts/__init__.py` | `FAPI-01` 导出统一 analyzer | `FAPI-02` Actual 与 Gold 使用相同入口 | `FAPI-03` import 无 Office/网络副作用 |
| `facts/reader.py` | `READ-01` 读取 document/header/footer parts | `READ-02` 正确解析内部和外部关系目标 | `READ-03` 缺主 part、坏 ZIP 或越界关系明确失败 |
| `facts/content.py` | `CONT-01` 保留中文标点、连续空格和换行 | `CONT-02` 提取 tag、alias、slot marker 和段内范围 | `CONT-03` 图片/公式/域生成非文本 token，不被当作空文本 |
| `facts/structure.py` | `STR-01` 段落与 Run 字符范围正确 | `STR-02` S12 表格、行、单元格和合并关系正确 | `STR-03` header/textbox story 与正文位置不混淆 |
| `facts/effective_style.py` | `STY-01` 直接字体/字号/粗体生效 | `STY-02` docDefaults + basedOn + named style 继承正确 | `STY-03` 段落、单元格和页面尺寸单位归一化正确 |
| `facts/objects.py` | `OBJ-01` S09 图片关系、内容 hash 和尺寸正确 | `OBJ-02` S13 公式、域和书签语义事实正确 | `OBJ-03` S12 合并关系或断裂对象关系被正确报告 |

### 4.3 对齐和业务断言代码

| 生产代码 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| `alignment.py` | `ALI-01` region_id/slot_id 精确匹配 | `ALI-02` 无 ID 时唯一结构定位器匹配 | `ALI-03` S07 重复锚点返回 AMBIGUOUS，不选第一个 |
| `evaluators/__init__.py` | `VAPI-01` 导出 protected evaluator | `VAPI-02` 导出 slot evaluator | `VAPI-03` 导出 remove evaluator 且不暴露 DOCX reader |
| `evaluators/protected.py` | `PRO-01` S00 内容/结构/样式全通过 | `PRO-02` S01 文本变化只产生内容主失败 | `PRO-03` S02/S09 样式或对象变化分别归因，不误报 slot |
| `evaluators/slots.py` | `SLOT-01` S00 槽集合、位置、字段、样式通过 | `SLOT-02` S03/S04 缺失或多余槽得到 FN/FP | `SLOT-03` S05/S06 字段或边界错误分别失败 |
| `evaluators/forbidden_residue.py` | `REM-01` 没有 Gold remove 命中时通过 | `REM-02` S08 明确禁止文字残留时失败 | `REM-03` Gold 未声明的普通文字不被自行推断为 remove |

### 4.4 评分、报告与编排代码

| 生产代码 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| `scoring.py` | `SCORE-01` S00 八个分项合计 100、结论 PASS | `SCORE-02` 一个硬失败即 FAIL 且分数仍按断言计算 | `SCORE-03` S10 coverage 下降、score provisional、结论 UNKNOWN |
| `reporting.py` | `REP-01` JSON 通过 report schema | `REP-02` Markdown 与 JSON 的状态、分数、issue 数一致 | `REP-03` issue 顺序稳定且报告不复制完整文档正文 |
| `runner.py` | `RUN-01` S00 完整链路生成两份报告 | `RUN-02` S01 或 S05 生成 FAIL 报告且输入 hash 不变 | `RUN-03` S10 保留 UNKNOWN；S11 输入错误不发布伪评分报告 |

### 4.5 合成样本生成代码

| 代码 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| `evals/template-extraction/fixtures/build_samples.py` | `FIX-01` 一次生成 manifest 列出的 S00–S13 | `FIX-02` 两次生成的规范事实和 hash 绑定一致 | `FIX-03` 所有生成 DOCX package、契约和 case schema 均有效 |

### 4.6 三校 candidate case 物化代码

| 代码 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| `evals/template-extraction/materialize_candidate_cases.py` | `CASES-01` 生成三个固定 case 目录并绑定 template/contract hash | `CASES-02` 每个 `w:tag` 与 contract locator 闭包，且 `w:alias == field_id` | `CASES-03` 拒绝覆盖 accepted case 或 accepted contract |

第 4.1–4.4 节包含 18 个 Eval 生产 Python 文件，第 4.5、4.6 节各包含 1 个生成器，合计
20 个代码文件，最低为 60 个代码 case。参数化可以减少测试函数数量，但测试报告中的
60 个 case ID 必须分别可见。

## 5. Schema 与配置测试矩阵

schema 和配置不是 Python，但它们是机器合同，同样每项至少 3 个 case。

| 资产 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| `pyproject.toml` / `uv.lock` | `ENV-01` 未安装产品 wheel 时 Eval 环境仍可独立 lock/sync 和运行 S00 | `ENV-02` dependency graph 不含本地 `docfit`、Claude SDK、Adobe SDK | `ENV-03` 产品构建不包含 `template_extraction_eval`，Eval 构建不包含 `docfit` |
| `case.schema.json` | `SCH-CASE-01` 最小合法 case | `SCH-CASE-02` 缺 Gold 引用失败 | `SCH-CASE-03` Registry ref 缺 version/hash 失败 |
| `fill-contract.schema.json` | `SCH-FILL-01` 一个 protected + 一个 slot 合法 | `SCH-FILL-02` owner 非法或 locator 缺失失败 | `SCH-FILL-03` component locator 结构错误失败 |
| `field-catalog.schema.json` | `SCH-FIELD-01` v0.1 Registry 合法 | `SCH-FIELD-02` field_id 不符合 pattern 失败 | `SCH-FIELD-03` 缺 registry_id/version 失败 |
| `eval-config.schema.json` | `SCH-CFG-01` v1 标记、容差和评分引用合法 | `SCH-CFG-02` 负容差失败 | `SCH-CFG-03` 未知 scoring_version 失败 |
| `report.schema.json` | `SCH-REP-01` PASS 报告合法 | `SCH-REP-02` UNKNOWN provisional 报告合法 | `SCH-REP-03` 缺 dimension/coverage/issues 失败 |
| `scoring-v1.yaml` | `CFG-SCORE-01` 八个维度总和 100 | `CFG-SCORE-02` 任一负权重或缺维度失败 | `CFG-SCORE-03` case 不能局部覆盖 v1 权重 |

这里最低为 21 个 environment/schema/config contract case。

## 6. 三校 case 的最低测试

每所学校各准备同样的三个简单测试，不用复杂学生论文：

| 学校 | Case 1 | Case 2 | Case 3 |
|---|---|---|---|
| 湖南农业大学本科 | `HUNAU-01` Gold 自比较 PASS | `HUNAU-02` 测试副本改单个 protected 字符后 FAIL | `HUNAU-03` 测试副本改单个 field_id/alias 后 FAIL |
| 南京农业大学本科 | `NJAU-01` Gold 自比较 PASS | `NJAU-02` 测试副本改单个 protected 字符后 FAIL | `NJAU-03` 测试副本改单个 field_id/alias 后 FAIL |
| 北京大学研究生 | `PKU-01` Gold 自比较 PASS | `PKU-02` 测试副本改单个 protected 字符后 FAIL | `PKU-03` 测试副本改单个 field_id/alias 后 FAIL |

这里最低为 9 个 school case。它们在 W6 进入门满足后才启用，不阻塞 W0–W5 的合成链路
实现。

## 7. 测试文件落位

为了让“代码 → 测试”关系可查，实施时把测试拆成：

```text
evals/template-extraction/tests/
├── unit/
│   ├── test_public_api.py
│   ├── test_models.py
│   ├── test_contracts.py
│   ├── test_alignment.py
│   ├── test_scoring.py
│   ├── test_reporting.py
│   ├── test_runner.py
│   ├── test_sample_builder.py
│   ├── facts/
│   │   ├── test_reader.py
│   │   ├── test_content.py
│   │   ├── test_structure.py
│   │   ├── test_effective_style.py
│   │   └── test_objects.py
│   └── evaluators/
│       ├── test_protected.py
│       ├── test_slots.py
│       └── test_forbidden_residue.py
├── contract/
│   └── test_eval_contract.py
└── integration/
    └── test_run_eval.py
```

`test_public_api.py` 负责三个 `__init__.py` 的导出 case；CLI 参数、退出码和 schema 放在
contract；完整最小链路放在 integration。不要为了“每文件一个测试文件”复制相同的
DOCX 构建逻辑。

## 8. 完成门

### 8.1 模块门

必须全部通过：

```bash
uv lock --project evals/template-extraction --check
uv sync --project evals/template-extraction --frozen
uv run --project evals/template-extraction pytest -q evals/template-extraction/tests/unit
uv run --project evals/template-extraction pytest -q evals/template-extraction/tests/contract
uv run --project evals/template-extraction pytest -q evals/template-extraction/tests/integration
uv run --project evals/template-extraction mypy \
  evals/template-extraction/template_extraction_eval \
  evals/template-extraction/run_eval.py
uv run --project evals/template-extraction ruff check evals/template-extraction
```

并满足：

- 20 个 Python 文件每个至少 3 个可见 case，最低 60 个；
- 1 个独立环境合同 + 5 个 schema + 1 个评分配置最低 21 个 case；
- 三校最低 9 个 case；
- S00–S13 样本生成与 manifest 一致；
- PASS、FAIL、UNKNOWN 和输入错误四条路径都有证据；
- 输入模板和契约运行前后 hash 不变；
- JSON/Markdown 同源；
- Eval 源码静态扫描不存在 `import docfit` 或 `from docfit`；
- Eval 源码不通过 subprocess 或 shell 启动产品 `docfit` CLI；
- 产品和 Eval 的构建产物均不包含对方 Python 包；
- 无网络、Adobe、Word GUI 或 Agent 依赖。

### 8.2 项目回归门

```bash
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
```

现有 `docfit eval --suite core` 必须继续通过。只有本模块确实修改 Agent、Provider 或
渲染路径时才需要对应 live gate；按当前设计不应发生这种修改。

### 8.3 文档与数据门

- `DESIGN.md`、`PLAN.md`、`evals/README.md` 和 `run_eval.py --help` 一致；
- case、report、Registry 和 scoring version 均有 hash/version 绑定；
- Temp 候选不被自动标为 Gold；
- Gold 存储与 CI 权限有明确记录；
- 不提交真实学生内容、完整运行 transcript 或凭据；
- 实施切换时同步受影响的 00–06 和 active capsule，不让代码领先于合同。

## 9. 风险、处理和停止条件

| 风险 | 当前事实 | 处理 | 停止条件 |
|---|---|---|---|
| 候选不等于 Gold | 三校 manifest 的 `human_acceptance` 仍 pending | 可按最终目录物化，但三层状态固定 candidate 且预期 `INPUT_ERROR`；W6 accepted 门仍等 Human 确认 | 未确认时禁止改为 accepted、进入评分或覆盖已验收 Gold |
| 两校 OfficeCLI schema FAIL | 湖南农大、南京农大 validation report 当前失败 | 分析具体错误并修复或记录人工裁决 | 不得删掉失败断言强行通过 |
| Registry 尚是研发快照 | v0.1 有已知字段缺口 | case 固定 ID/version/hash；不跟随 latest | hash 不一致时 case 输入失败 |
| 有效样式复杂 | Word 继承、容器和默认值容易出现两套口径 | 统一 analyzer，先用三个小样本锁定 | 不能解释继承来源时返回 UNKNOWN |
| OOXML 对象覆盖不全 | 文本框、域、公式等可能存在不支持分支 | 显式 unsupported fact 与 coverage | 可见对象被静默忽略即停止合入 |
| 独立分析器带来重复代码 | Eval 不复用产品 OOXML 实现 | 只复制必要的只读事实能力，以 schema/fixture 对齐数据合同 | 发现需要 import `docfit` 时停止并回到设计层 |
| 独立依赖增加维护面 | Eval 自有 `pyproject.toml` 与 `uv.lock` | 依赖保持最小，单独执行 frozen lock gate | Eval 依赖被加入产品项目时停止合入 |
| 测试数量膨胀 | 最低 78 个非学校 case + 9 个学校 case | 参数化复用 S00–S13，保持单变量 | 不通过合并多个错误来凑数量 |
| 分数掩盖关键问题 | 平均分可能看起来很高 | verdict 独立于 score，硬失败优先 | 任一硬失败得到 PASS 即停止合入 |

## 10. 实施批次与提交边界

建议按以下批次实施，每批保持代码、测试和文档同提交：

1. `W0`：schema、scoring config、fixture builder 和全部简单样本。
2. `W1`：models/contracts/public API 及其最低 3-case 测试。
3. `W2`：共享 facts 分析器及逐文件测试。
4. `W3`：alignment + 三类 evaluator 及逐文件测试。
5. `W4`：scoring + reporting 及逐文件测试。
6. `W5`：runner + 独立 `run_eval.py` + contract/integration 测试。
7. `W6`：三校 candidate 目录可先物化；Human readiness 通过后再原地晋升 Gold，并启用
   每校三条样本回归。
8. `W7`：全量回归、文档同步和生产接入裁决。

每批完成时更新本计划的 case 计数和证据链接。不要在最后一批才补测试，也不要先提交
没有对应测试的生产文件。

## 11. 最终交付

计划全部执行后应交付：

```text
1 个独立 Eval CLI
1 套共享 DOCX 事实分析层
2 套业务评测器 + 1 个 remove 硬失败检查
1 个版本化评分器
2 种同源报告
14 个简单合成样本
20 个逐代码测试责任，最低 60 个代码 case
21 个独立环境/schema/config case
3 所学校 × 3 个最小 case
```

最低总计为 90 个 case；它们复用 14 个小型合成样本和三个学校 Gold，不要求 90 份独立
DOCX，因此测试覆盖充足但维护成本保持可控。

产品上，这个交付只回答“生成模板和填写契约与 Gold 相比做得是否正确”。它不会把
静态高分解释为模板提取 Agent 路径正确、正式填写行为正确、视觉交付正确或 M3 已完成。

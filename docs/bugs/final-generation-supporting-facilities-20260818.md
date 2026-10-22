# Bug：final-generation 非代码生成逻辑配套设施问题

- Status: `RESOLVED_PHASE_1`
- Severity: `P0`
- Bug type: `supporting-facility: test/eval`
- Related supporting types: `supporting-facility: gold/data`, `supporting-facility: report/evidence`, `supporting-facility: docs/process`
- Discovered: `2026-08-18`
- Subsystem: `final-generation test / eval / gold / report / release gate`
- Related implementation-quality bug:
  - [final-generation E2E 成稿视觉与结构质量回归](./final-generation-e2e-visual-regressions-20260818.md)

## 1. 边界

本文只处理围绕代码生成逻辑的配套设施问题，不修正文档生成代码逻辑。

| 范围 | 属于本文 |
| --- | --- |
| 测试和 eval 的检查组合、PASS/FAIL 语义 | 是 |
| gold 文件和 case 配置是否可信、是否绑定正确版本 | 是 |
| run report、PDF、hash 和 evidence 是否绑定同一个 snapshot | 是 |
| `generate PASS`、`quality PASS`、release/pass/fail 的含义 | 是 |
| heading 编号、caption 编号、TOC 缓存、slot 残留、表格图片布局 | 否，归相关 implementation-quality bug |

核心约束：

```text
生成逻辑负责把 DOCX 做对。
配套设施负责发现问题、解释结果、固定 gold、绑定证据、判断能否发布。
两者不能混在同一个修复阶段或根因里。
```

## 2. 当前问题和失败原因

本文里的失败不是“DOCX 为什么生成坏了”，而是“坏结果为什么没有被配套设施正确发现、解释、绑定和发布控制”。

总根因：阶段一修复前，配套设施把四个不同结论压进了同一个容易误读的 PASS 语义里：

```text
流程是否跑完 != 质量是否达到 gold != 证据是否绑定同一产物 != 是否允许发布
```

具体失败原因如下：

| 设施类型 | 具体失败原因 | 导致的错误判断 | 阶段一处理状态 | 不属于本文 |
| --- | --- | --- | --- | --- |
| test/eval | release 级 case 虽然配置了 `expected.quality.gold_docx`，但历史运行和沟通里仍可能只看 `input/style/generate`；`generate` 本身只检查流程产物和基础 evidence，不检查 gold 质量 | `generate PASS` 被误读为质量达标或可发布 | 有 gold 的 case 默认检查固定为 `input,style,generate,quality`；报告单独输出 `generate_status`、`quality_status`、`release_status`、`releasable` | 不判断 TOC、heading、caption、slot 等代码怎么修 |
| gold/data | 质量结论依赖 case 里的 `expected.quality.gold_docx`；如果 gold 缺失、路径错误、版本过期或来源不清，eval 无法证明质量，或者会对比错误目标 | 没有 gold 的 case 被误当成可做质量发布；过期 gold 造成假 PASS 或假 FAIL | `quality` check 要求 repo 内有效 gold DOCX；release case 由 gold 配置显式触发 | 不把“目标版式怎么生成”推给 gold |
| report/evidence | 运行目录里可能同时存在 run report 绑定 PDF、candidate PDF、`final.pdf` 或手工/不同 renderer 导出的 PDF；人工查看和 eval 判定可能不是同一个 snapshot | 页数、视觉差异和人工观察互相对不上；无法复验同一产物 | `release_gate.final_snapshot` 绑定 DOCX/PDF 路径、sha256、renderer、`render_ref` 和 `render_document_sha256`；未绑定时 release gate FAIL | 不修复 PDF 里暴露的结构/视觉缺陷 |
| docs/process | CLI、README 和对话说明没有强制区分 `check_status`、`generate_status`、`quality_status`、`release_status`；后续 AI 容易把 PASS 当成单一成功语义 | 开发者可能去放宽门禁、换 gold 或改测试，而不是修生成逻辑 | CLI/README/本文明确：只有 `release_status=PASS` 且 `releasable=true` 才能描述为可发布 | 不承载代码逻辑修复计划 |

这四类失败只影响发现、解释、复验和发布控制；它们不会直接生成错误 DOCX。错误 DOCX 的代码根因归独立 implementation-quality bug。

实际失败链路：

1. `generate` check 成功产出 DOCX、报告和基础 evidence，并返回 PASS/COMPLETE。
2. 同一轮输出与 gold 对比后，`quality` 失败，说明成稿文本、结构、分页、slot 或视觉仍不达标。
3. 如果报告或 CLI 只突出 `generate PASS`，而没有把 `quality_status` 和 `release_status` 分开，后续 AI 会把“流程跑通”误报为“E2E 质量通过”。
4. 如果报告没有绑定唯一 final snapshot，人工查看的 PDF 可能不是 eval 判定的 PDF，质量问题会变成不可复验的争议。
5. 所以本文的修复目标不是让坏 DOCX 变好，而是让坏 DOCX 必须被稳定识别为 `quality FAIL / release FAIL`，并能追溯到同一输入、gold 和输出产物。

### 2.1 典型证据

```bash
uv run docfit eval --suite final-generation --case student-001-njau-complete-debug --checks input,style,generate,quality --output temp/final-generation-quality-compare-20260818/eval-complete-debug-quality-002 --json
```

结果：

- `input/style/generate`：PASS；
- `quality`：FAIL；
- full text similarity：`0.962531`，阈值 `>=0.99`；
- paragraph sequence similarity：`0.753165`，阈值 `>=0.95`；
- page count delta：`-3`，阈值 `0`；
- placeholder residue count：`7`，阈值 `0`；
- mean visual changed ratio：`0.196102`，阈值 `<=0.02`；
- max page visual changed ratio：`0.43453`，阈值 `<=0.08`。

这说明 `generate PASS` 只能表示流程结果满足当前 generate check，不能表示成稿质量达到 gold，也不能直接等价为可发布。本文要修的是：有 gold 时必须跑质量检查、质量失败必须阻断 release、报告必须指向同一个 final snapshot、CLI 和文档必须避免把这些状态混在一起。

## 3. 语义拆分

| 名称 | 含义 | 不能代表 |
| --- | --- | --- |
| `input` | 输入包身份、文件和 Registry 绑定可用 | 成稿质量 |
| `style` | 样式合约 occurrence 可写入并回读 | 编号、目录、分页、视觉接近 gold |
| `generate` | 生成流程产出 DOCX、报告和基础 evidence | gold 质量通过、可发布 |
| `quality` | 与 gold 做文本、结构、媒体、渲染差异检查 | 具体是哪一层代码坏了 |
| `release gate` | 综合当前要求决定是否发布 `final.docx` | 生成逻辑本身 |

## 4. 修复计划

1. 保持 `generate` 作为流程检查，不把它改名成质量检查。
2. 对有 gold 的 release 级 case，提供固定检查组合：`input,style,generate,quality`。
3. 增加或明确 release gate 语义：只有 release gate 通过时，才允许把结果声明为可发布。
4. run report 必须明确区分：
   - `generate_status`；
   - `quality_status`；
   - `release_status`。
5. 报告必须绑定同一个 final snapshot 的 DOCX/PDF，不混用 candidate PDF、手工导出 PDF 和不同 renderer 产物。
6. Gold 文件和 case 配置必须记录来源、路径、hash 或等价身份；更新 gold 时必须同步 case expectation。
7. CLI 文档必须说明哪些检查是流程检查、哪些是 gold 质量检查、哪些是 release 判定。

## 5. 验收标准

| 设施类型 | 通过标准 |
| --- | --- |
| test/eval | 带 `expected.quality.gold_docx` 的 case 不显式传 `--checks` 时，实际执行 `input,style,generate,quality`；显式只跑 `input/style/generate` 时，不能得到 release PASS |
| gold/data | `quality` 缺失或配置非法 gold 时必须失败并给出明确原因；gold 文件、case 配置和质量报告必须能追溯到同一个可复验目标 |
| report/evidence | release gate 消费的 `final_snapshot` 必须绑定本轮 DOCX、PDF、hash、renderer 和 render reference；无法绑定时必须 FAIL |
| docs/process | CLI、README 和本文都必须明确：`generate PASS` 不等于 `quality PASS`，也不等于 release PASS |
| code-logic 分离 | 本文不得把 heading、caption、TOC、slot、style、table、image 的修复实现写成验收逻辑；这些问题只在 implementation-quality bug 中处理 |

## 6. 阶段一修复记录

日期：`2026-08-18`

已完成：

- 带 `expected.quality.gold_docx` 的 release case 默认检查组合固定为
  `input,style,generate,quality`。
- eval report 顶层明确输出 `check_status`、`generate_status`、`quality_status`、
  `release_status` 和 `releasable`。
- `release_gate.final_snapshot` 记录本次 release 判定消费的 DOCX、DOCX sha256、PDF、
  PDF sha256、`render_ref`、renderer 和 `render_document_sha256`，并要求 PDF evidence
  与所选 DOCX snapshot 的 sha256 绑定。
- CLI 非 JSON 输出同时展示 checks、generate、quality 和 release 状态。
- 文档说明 `generate PASS` 不等于 `quality PASS`，也不等于 release PASS。

阶段一复验：

```bash
uv run docfit eval --suite final-generation --case student-001-njau-complete-debug --output temp/final-generation-release-gate-20260818/eval-complete-debug-default-001 --json
```

结果符合预期：

- `checks_requested`: `input,style,generate,quality`；
- `input/style/generate`: `PASS`；
- `generate_status`: `COMPLETE`；
- `quality_status`: `FAIL`；
- `release_status`: `FAIL`；
- `releasable`: `false`。

注意：阶段一只修复发布门禁和报告语义；成稿结构/视觉质量问题仍归
[final-generation E2E 成稿视觉与结构质量回归](./final-generation-e2e-visual-regressions-20260818.md)。

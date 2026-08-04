# DocFit 单元分页边界 Tool-only PoC 执行结果

> 状态：VERIFIED
> 日期：2026-08-04
> 主计划：[`docs/plans/docfit-unit-boundary-tool-poc.md`](../docs/plans/docfit-unit-boundary-tool-poc.md)
> 测试设计：[`docfit-unit-boundary-tool-poc-test-content.md`](docfit-unit-boundary-tool-poc-test-content.md)
> 结论边界：OfficeCLI 1.0.143 同引擎相对验证；不是 Word/Adobe 分页真值或 M3 Eval

## 1. 最终指标

| 指标 | 结果 | 比率 |
|---|---:|---:|
| `eligible_fixture_boundary_resolution_rate`（C1–C6） | 6 / 6 | 100.0% |
| 安全行为符合率（C7–C8） | 2 / 2 | 100.0% |
| C1–C6 双跑结构化结果一致 | 6 / 6 | 100.0% |
| 学校外部探针断言符合 | 4 / 4 | 100.0% |
| 学校外部探针双跑一致 | 4 / 4 | 100.0% |

最终可称为“准确率”的主指标是合成 fixture 的 `6 / 6 = 100.0%`。学校外部探针没有
独立人工 Gold，不进入准确率分母；其 `4 / 4` 只表示本次两个固定 hash 样本上的结构化
断言符合预期。

## 2. 合成 C1–C8

| Case | 结果 | 关键断言 |
|---|---|---|
| C1 | PASS | 保留唯一显式 page break |
| C2 | PASS | 保留 `pageBreakBefore` 与 1 个 leading block |
| C3 | PASS | 保留 next-page section 与节几何 |
| C4 | PASS | 3 个候选中唯一保留 1 个 leading、消耗 1 个 |
| C5 | PASS | 无 layout-only block 时在锚点建立唯一显式边界 |
| C6 | PASS | 精确保留 1 个 leading 与 3 个 trailing block |
| C7 | PASS | 返回 `unsupported_atomic_boundary`，无候选发布 |
| C8 | PASS | 上下文充分时唯一映射；不足时返回 `ambiguous_anchor_mapping` |

C1–C6 每个用例都独立执行两次。两次 `status`、分类、recipe、候选证据和候选内容 hash
完全一致；所有候选均满足 `mutation_bounded=true`，源文件 hash 保持不变。

## 3. 学校外部探针

外部文件只读使用；仓库不保存绝对路径、正文、锚点明文、bbox、DOCX、PDF、图片或
临时候选。

| 样本 ID | basename | source SHA-256 | Case | 脱敏结果 |
|---|---|---|---|---|
| `HNAU-LOCAL-01` | `source_template.docx` | `6d66a2926ff170055840730f9273fccccfeb45df31cc877afc013d551b12d989` | E1 | eligible；自然流；8 个候选中唯一命中 1 个；保留 2 个 leading、消耗 5 个；双跑一致 |
| `PKU-LOCAL-01` | `source_template.docx` | `720372f4e70b75ade60a302e95abc870e47d47ac7e6cbf0e5a16ceef4d619e14` | E2 | eligible；识别并原样保留 explicit section boundary；1 / 1 唯一候选；双跑一致 |
| `PKU-LOCAL-01` | `source_template.docx` | 同上 | E3-A | 重复锚点在下一锚点上下文充分时唯一映射；双跑一致 |
| `PKU-LOCAL-01` | `source_template.docx` | 同上 | E3-B | 移除消歧上下文后稳定返回 `ambiguous_anchor_mapping`；双跑一致 |

湖南农业大学源模板存在 8 个既有 Office OpenXML schema 错误。该 probe 没有把它记录成
干净文档：结果明确携带 `source_schema_invalid`。候选仍需通过 package 检查，并证明 ZIP
其他 part 逐字节不变、移除新增 `pageBreakBefore` 后 `document.xml` 与源 XML 树等价。

## 4. 外部样本推动的优化

1. **累计虚拟页码**：OfficeCLI HTML 中一个 `.page` 容器可能承载多页自然溢出内容；
   后续显式分页容器的全局页码现在按前序实际内容跨度累计。该行为只由 PoC resolver
   opt-in，现有五个公开 Tool 保持原默认 layout 路径。
2. **视觉容差校准**：同引擎 HTML 重排容差固定为 240 twips（12pt），仍小于相邻布局
   候选间距的一半；湖南农大 E1 从零命中收敛为唯一命中，不允许多解通过。
3. **既有 schema 错误基线**：干净源继续要求候选严格通过 OfficeCLI validate；既有不合规
   源只能在受控单一分页属性改动、package 完整和 mutation-bounded 全部成立时参与探针，
   且必须保留警告。
4. **失败不猜测**：在湖南农大另外三个 eligible 边界上分别验证了 3、10、19 个候选的
   零命中路径，均稳定返回 `ambiguous`，没有选择未达门限的“最近候选”。

## 5. 最终验证

```text
uv sync --frozen                                      PASS
uv lock --check                                       PASS
uv build                                              PASS
uv run ruff check .                                   PASS
uv run mypy src                                       PASS (46 source files)
uv run pytest -q tests/unit tests/integration         PASS (258 tests)
uv run docfit doctor                                  PASS (overall PASS)
git diff --check                                      PASS
```

测试仅出现 1 个既有 `StarletteDeprecationWarning`，无失败。整个 PoC 未调用 Agent、未调用
Adobe PDF Services、未消耗 Document Transaction，也未新增公开 Tool 或改变公开 JSON
schema。

## 6. 长期文档漂移审计

`doc-keeper` 对 00–06 的本次受影响声明做了聚焦审计：

| 长期文档 | 聚焦声明 | 已验证 | 漂移 | 不可验证 |
|---|---:|---:|---:|---:|
| 00 索引与总边界 | 4 | 4 | 0 | 0 |
| 01 核心架构 | 3 | 3 | 0 | 0 |
| 02 测试与迭代 | 4 | 4 | 0 | 0 |
| 03 Gold 设计 | 2 | 2 | 0 | 0 |
| 04 Skills 设计 | 2 | 2 | 0 | 0 |
| 05 Knowledge 与 Tools | 5 | 5 | 0 | 0 |
| 06 开发路线 | 4 | 4 | 0 | 0 |

审计结论：五个公开 Tool、固定后端职责、源文件只读、学校事实不进入 Knowledge、M3
仍为未来里程碑、O1 未被本 PoC 冒充启动等长期声明均保持成立。PoC 的虚拟分页测量为
内部 opt-in，没有使代码领先于 00–06，因此不修改长期合同。

## 7. 结论边界

PoC 已证明封闭合成矩阵和两个固定学校样本 hash 上的确定性边界定位与候选筛选可行。
它不证明任意学校模板、Microsoft Word 或 Adobe 转换分页准确率，也不代表 M3、Gold、
真实样本资格验证或人工交付复核完成。若正式接入 `docx_inspect`、`docx_edit`、
`docx_render` 或 `docx_validate`，仍需新计划和相应长期文档更新。

## 8. 用户复核后的独立 Word 物化闭环

用户打开首轮独立 Word 后指出：resolver 已经计算了 `leading_layout_refs` 与
`boundary_consumed_refs`，但首轮文件仍按固定块区间复制，边界 recipe 没有约束发布。
湖南农业大学诚信声明因此从锚点直接开始，页首可见空段为 0；这与用户提供的 Word 实机
证据“相邻 2 个空段中，上一页消耗 1 个、声明页保留 1 个”冲突。

本轮新增内部 `materialize_resolved_unit`，并形成红绿回归：

1. 只允许 `status=resolved` 且绑定当前 source hash 的 recipe 发布；
2. 独立文档起点成为唯一分页所有者，移除起始 `pageBreakBefore`、页内 page break 或
   不应进入下一单元的分节段；
3. 当前单元与下一单元 recipe 联合决定切点，下一单元 visible leading 不再重复留在当前
   单元末尾；
4. `boundary-consumed` 留在上一单元侧，visible leading 只进入下一单元一次；
5. 显式 next/odd-page 分节将有效节几何迁移到独立文档，不制造空白首页；
6. ambiguous / unsupported recipe 失败且不发布文件。

修正版输出位于 `temp/docfit-unit-boundary-word-output-corrected/`。本次生成 28 份单元
Word 和 2 份 Word 清单，结果如下：

| 指标 | 结果 | 比率 |
|---|---:|---:|
| DOCX package 完整且可渲染 | 30 / 30 | 100.0% |
| 两校块级相邻分区精确连续 | 2 / 2 | 100.0% |
| 湖南农大规范自然流 Gold | 1 / 1 | 100.0% |
| 北京大学显式 next/odd-page 分节结构 | 15 / 15 | 100.0% |
| 当前证据可严格计分的分页边界合同 | 16 / 16 | 100.0% |

这里的 16 / 16 不把 28 份文件全部冒充为分页 Gold。文档起点和同页语义切分不是待判定的
新页边界；仅有 OfficeCLI 辅助渲染、但没有规范 Word/WPS Gold 的其他自然流推断也不进入
准确率分母。完整逐单元状态和排除原因记录在修正版 `manifest.json`。

本次物化修复在最新工作区上的验证结果：依赖锁检查、构建、Ruff、Mypy、`git diff --check`
均通过；完整测试 315 / 315 通过，仅保留一个既有 Starlette 弃用警告；`docfit doctor`
基础检查通过。

累计 live Agent 门 `image`、`ask-user`、`denied-tools`、`path-tools`、`subagent` 已全部重新
生成当前版本 PASS 收据，`doctor --require agent-smoke` 返回 PASS。`path-tools` v3 的
当前回执证明 Kimi 在临时 smoke scope 中完成 Read/Glob/Grep 的路径门控，以及受信任
Bash/Write 的执行；这仍是独立权限证据，不改变上述分页边界分母。

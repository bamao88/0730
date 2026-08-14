# DocFit 单元分页边界 Tool-only PoC 测试内容

> 状态：VERIFIED
> 日期：2026-08-04
> 主计划：[`docs/plans/docfit-unit-boundary-tool-poc.md`](../docs/plans/docfit-unit-boundary-tool-poc.md)
> 执行结果：[`docfit-unit-boundary-tool-poc-results.md`](docfit-unit-boundary-tool-poc-results.md)
> 性质：临时测试设计；不是产品 Knowledge、M3 Eval 数据集或真实样本资格声明

## 1. 用途与边界

本文档把 PoC 的“测试内容”与实现计划分开，固定：

1. C1–C8 合成 fixture 要构造什么结构和视觉事实；
2. 湖南农业大学与北京大学本地模板如何作为探索性外部对照；
3. 哪些结果可以进入仓库，哪些内容必须仅留在授权的本地运行目录。

本文档不授权实现 PoC，不修改当前 `docfit convert` 行为，也不把两个学校的格式事实提升为
通用规则。

## 2. 测试层次

| 层次 | 输入 | 用途 | 是否进入 CI | 是否进入主指标 |
|---|---|---|---|---|
| S：合成 fixture | 无学校事实的最小 DOCX + 固定 JSON | 验证封闭算法和安全失败 | 是 | C1–C6 进入 `6 / 6` |
| E：学校外部对照 | 用户授权的本地湖南农业大学、北京大学模板 | 暴露合成数据未覆盖的真实结构 | 否 | 否，单独报告 |

学校对照不得替代合成 fixture。学校对照通过也只能支持“当前 hash 的本地样本未暴露新缺口”，
不能支持“该学校模板普遍通过”。

## 3. 合成 fixture 的共享约定

所有 fixture 只使用以下通用可见文字，避免嵌入学校、专业或个人信息：

```text
PREVIOUS_UNIT_END
UNIT_ANCHOR
UNIT_BODY
NEXT_UNIT_ANCHOR
```

共享页面条件：

- 默认使用 A4 纵向、固定页边距和单分栏；
- 只有 C3 为新节显式改变页面几何、页眉或页脚继承关系；
- 合成渲染的页面尺寸和 bbox 必须在 fixture 生成后测量，不手写与实际页面不一致的数值；
- `first_visible_anchor_ref` 与 `next_visible_anchor_ref` 都绑定 fixture 当前 hash；
- 每个成功用例运行两次，断言分类、recipe 和内容 hash 一致。

`layout-only block` 统一使用自身明确的段落样式和行高，不依赖当前机器的默认字体。这些块只为测试
布局归属而存在，不表示产品应用空段控制间距。

## 4. C1–C8 具体内容

### C1：显式 page break

- 结构：`PREVIOUS_UNIT_END` 后使用单一显式 page-break run，随后是 `UNIT_ANCHOR`。
- 模拟事实：锚点从新页正文区顶部开始，无额外页首留白。
- 断言：`explicit_page_break`；原边界是唯一所有者；不新增第二个分页机制。

### C2：`pageBreakBefore` + 一个 leading block

- 结构：锚点前有一个 layout-only 段，分页所有权由该段的 `pageBreakBefore` 承担。
- 模拟事实：新页保留一行可测量留白后出现锚点。
- 断言：`explicit_page_break_before`；该段属于 `leading_layout_refs`；边界仍只有一个所有者。

### C3：next-page section

- 结构：`PREVIOUS_UNIT_END` 所在段持有 next-page section break；新节使用与前一节不同的页边距，
  并显式设置可断言的页眉或页脚继承关系。
- 模拟事实：`UNIT_ANCHOR` 位于新节首页。
- 断言：`explicit_section_break`；原样保留新节几何和关联页眉页脚；不用普通 page break 降级。

### C4：自然流 + 两个 layout-only block

- 结构：使用确定性 filler 使上一单元接近页尾，锚点前连续放置两个 layout-only 段，不存在
  page break、`pageBreakBefore` 或 section break。
- 模拟事实：锚点位于新页，视觉上只保留一个 leading block 的高度。
- 断言：`natural_flow_with_layout_blocks`；唯一正确候选保留靠近锚点的一个 leading block，另一个进入
  `boundary_consumed_refs`。

### C5：无 layout-only block 的自然流

- 结构：使用确定性 filler 使 `UNIT_ANCHOR` 自然落到新页，锚点前无 layout-only block 和显式分页。
- 模拟事实：锚点从新页正文区顶部开始。
- 断言：`natural_flow_without_layout_blocks`；在锚点前建立一个明确边界；语义内容无删减、无重复。

### C6：同时保留 leading 与 trailing

- 结构：单元开始包含一个 leading layout-only block，`UNIT_BODY` 之后、`NEXT_UNIT_ANCHOR` 之前包含
  三个明确属于当前单元页尾的 trailing layout-only block。
- 模拟事实：首页锚点前的留白和末页内容后的留白均为必须保留的布局。
- 断言：`leading_layout_refs` 精确为 1 个，`trailing_layout_refs` 精确为 3 个；不将 trailing 误标为
  `boundary_consumed`。

### C7：混合段内边界

- 结构：`PREVIOUS_UNIT_END`、手动换行与 `UNIT_ANCHOR` 位于同一正文段内。
- 模拟事实：换行后的锚点位于新页。
- 断言：`unsupported_atomic_boundary`；不从段内切断；不发布候选或归一化产物。

### C8：重复锚点

- 结构：文档前部的目录型区域和后部正文各出现一次 `UNIT_ANCHOR`，正文锚点之后有唯一的
  `NEXT_UNIT_ANCHOR`。
- 模拟事实：bbox 指向正文页。
- 断言 A：当对象顺序、样式、下一锚点和 bbox 可形成唯一映射时，绑定正文对象。
- 断言 B：移除足以消歧的上下文后，必须返回 `ambiguous_anchor_mapping`，不自动选择第一个文字匹配。

## 5. 学校外部对照

### 5.1 样本登记

| 样本 ID | 学校 | 入库内容 | 运行时绑定 |
|---|---|---|---|
| `HNAU-LOCAL-01` | 湖南农业大学 | 仅样本 ID、basename、hash 和脱敏断言 | 执行者从用户授权的本地路径提供 |
| `PKU-LOCAL-01` | 北京大学 | 仅样本 ID、basename、hash 和脱敏断言 | 执行者从用户授权的本地路径提供 |

两个本地候选 DOCX 已于 2026-08-04 完成可读性和 OfficeCLI 1.0.143 能力发现。该发现不是转换、
候选渲染或 PoC 通过证据。

绝对路径、正文、锚点明文、原始 bbox、DOCX、PDF 和页面图片不写入本文档或仓库。同名 basename 通过
样本 ID 和运行时 hash 区分。

### 5.2 外部用例

#### E1：湖南农业大学自然流对照

- 目标：尝试为 C4 找到一个真实结构对照。
- eligible 前置：运行时确认锚点在参考渲染中从新页开始，锚点前存在 layout-only block，且无显式
  page-break 所有者。
- eligible 断言：必须得到唯一正确 recipe，或以明确的 `ambiguous` / `unsupported` 失败且不发布输出。
- 不满足前置时：记录 `not_eligible_for_C4`，不反向修改 C4 使学校样本“看起来通过”。

#### E2：北京大学分节边界对照

- 目标：尝试为 C3 找到一个页面几何、页眉页脚或页码继承发生变化的真实 section boundary。
- eligible 前置：运行时结构检查与参考渲染同时确认该边界是新页所有者。
- eligible 断言：`explicit_section_break`；新节几何和关联关系无损；不用普通 page break 替代。
- 不满足前置时：记录 `not_eligible_for_C3`。

#### E3：北京大学重复锚点对照

- 目标：尝试为 C8 选择一组同名或近似锚点，验证目录、页眉或正文间的映射消歧。
- 断言：证据足够时唯一映射；证据不足时稳定返回 `ambiguous_anchor_mapping`。
- 限制：锚点明文只存在授权的本地 fixture，入库报告仅记录脱敏锚点 ID。

#### E4：跨学校可重复性

- 对 E1–E3 中每个 eligible 用例连续运行两次。
- 断言：同一 source hash、同一输入 fixture 产生相同状态、`source_boundary_mode`、recipe 和输出内容 hash。
- 两个学校结果分开报告，不合并为“真实样本准确率”。

## 6. 运行时输入与证据

### 6.1 执行前检查

1. 将样本 ID 绑定到用户授权的本地 DOCX，对路径做 canonicalization 和授权根目录检查。
2. 只读计算 source SHA-256；所有后续 `object_ref` 都绑定该 hash。
3. 在本地授权工作目录生成含锚点明文和 bbox 的模拟 Agent JSON；该 JSON 不进入仓库。
4. 确认本轮不调用 Agent、Adobe PDF Services、Microsoft Word、AppleScript 或 GUI session。

### 6.2 允许入库的脱敏记录

```json
{
  "sample_id": "HNAU-LOCAL-01",
  "source_basename": "source_template.docx",
  "source_sha256": "<runtime-sha256>",
  "case_id": "E1",
  "eligibility": "eligible",
  "status": "resolved",
  "source_boundary_mode": "natural_flow_with_layout_blocks",
  "selected_candidate_id": "candidate-1",
  "unique_match": true,
  "repeatable": true,
  "assertions": {
    "source_unchanged": true,
    "semantic_content_preserved": true,
    "single_boundary_owner": true,
    "published_output": false
  },
  "warnings": []
}
```

上述数值仅是字段形状示例，不是已通过记录。`published_output` 在 PoC 外部对照中必须为 `false`；候选只能存在于
当次授权的临时工作目录。

不允许入库：

- 本地绝对路径或用户目录信息；
- 锚点明文、邻近正文、表格内容或文档元数据；
- DOCX、PDF、页面图片、原始 bbox 或 OfficeCLI 全文输出；
- 临时候选、未脱敏日志或可反推正文的指纹。

## 7. 执行顺序与停止条件

1. 先完成 C1–C8 的结构生成和静态断言。
2. 再完成 C1–C6 的候选渲染、唯一解与两次重复运行。
3. 确认 C7/C8 的安全失败或唯一消歧后，才能绑定学校样本。
4. 按 E1 → E2 → E3 → E4 执行，每个用例先做 eligibility 检查。
5. 最后生成合成指标报告和学校对照脱敏报告，两者分开。

出现任一下列情况，当前 Tool 调用失败且不发布输出：

- source hash 在运行期间改变；
- 路径越出授权根目录；
- 锚点无法唯一映射，且用例未明确预期 `ambiguous`；
- 需要从段落、表格、内容控件或其他原子容器内部切断；
- 零个或多个候选通过成功用例的门限；
- 无法证明源文件只读、语义内容无损或失败无发布。

## 8. 本文档的完成条件

在 PoC 实现计划获批后，执行者还需把本文档中的设计转成：

- 可重建的 C1–C8 合成 fixture 生成器；
- 每个 case 的模拟 Agent JSON 和结构/视觉断言；
- 不入库的学校样本运行配置；
- 合成指标与学校对照分离的结果汇总。

上述资产已经实现并验证。合成主指标、学校外部探针和仓库级门禁结果见
[`docfit-unit-boundary-tool-poc-results.md`](docfit-unit-boundary-tool-poc-results.md)。本文仍是
临时测试设计，不升级为产品 Knowledge、M3 Eval 数据集或任意学校模板的普遍资格声明。

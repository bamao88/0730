# DocFit 单元分页边界定位 Tool-only PoC 计划

> 状态：VERIFIED_TOOL_ONLY_POC
> 日期：2026-08-04
> 性质：M2 后工具探索计划；只验证可行性，不改变当前转换行为、五个公开 Tool 契约或里程碑完成状态
> 配套测试内容：[`temp/docfit-unit-boundary-tool-poc-test-content.md`](../../temp/docfit-unit-boundary-tool-poc-test-content.md)
> 执行结果：[`temp/docfit-unit-boundary-tool-poc-results.md`](../../temp/docfit-unit-boundary-tool-poc-results.md)

## 1. 目标

快速验证以下假设：

> 当调用者已经给出逻辑单元的首个可见文字锚点、新页事实和目标页首留白时，
> 确定性代码能够结合 DOCX 结构、渲染文字位置和节页面几何，识别来源分页机制，
> 解析准确的物理边界，并生成可重复验证的单元边界方案。

本 PoC 暂不接入 Agent。Agent 将来负责的语义与视觉输出先用固定 JSON fixture 模拟，
重点验证 Tool 是否能够完成：

1. 可见文字锚点与 DOCX `object_ref` 的绑定；
2. 页面像素位置与节页面几何的归一化；
3. 显式分页、自然流分页和不确定情况的分类；
4. 页首与页尾布局对象的无损归属；
5. 候选边界生成、临时修改、渲染测量和唯一解选择；
6. 源文件只读、失败不发布和结果可重复。

## 2. 与当前基线的关系

- 本 PoC 不恢复 M3，不建设 Gold、真实样本资格验证或外部人工复核流程。
- 不新增第六个公开 Tool，不修改现有 Tool JSON Schema，不增加 Agent loop、工作流或
  Provider 抽象。
- 不把本地近似渲染升级为 Word 或 Adobe 交付真值。
- 不调用 Agent、Claude SDK 或 Adobe PDF Services API，不消耗 Document Transaction。
- PoC 代码若执行，先作为 `src/docfit/tools/` 内部实验 helper 和单元/集成测试存在；
  在正式接入 `docx_inspect`、`docx_edit` 或 `docx_validate` 前，必须另行批准实现计划，
  并同步受影响的 00–06、README 和 active capsule。
- 学校模板、学校数值和本地手工证据保持为当前任务输入，不写入产品 Knowledge。

## 3. PoC 不回答的问题

本轮不证明：

- 任意学校、任意版本模板都能自动拆分；
- OfficeCLI 或 LibreOffice 与 Microsoft Word 分页一致；
- PDF 留白能够直接反推出 Word 中空段的个数；
- 复杂表格、浮动对象、混合段内换行、文本框和修订对象已经全部可编辑；
- 拆分后的独立 DOCX 已适合下游 Agent 或最终交付；
- 最终论文已经通过人工视觉验收。

## 4. 核心模型

### 4.1 三层定位

每个单元边界必须同时包含三层证据：

```text
语义层：哪个文字对象是单元的首个可见锚点
结构层：锚点附近有哪些空段、换行段、分页符、分节符和原子容器
视觉层：锚点位于哪个 render/page/bbox，相对正文区域顶部有多少留白
```

页面不是稳定编辑身份。最终编辑仍绑定源 DOCX hash 和 `object_ref`。

### 4.2 单元布局组成

```text
boundary
leading_layout_zone
semantic_content
trailing_layout_zone
```

- `boundary`：唯一分页所有者；可能是普通分页、`pageBreakBefore` 或 next-page section。
- `leading_layout_zone`：属于新单元页首的空段、纯换行段或锚点段前距。
- `semantic_content`：标题、正文、表格和其他可见内容。
- `trailing_layout_zone`：属于当前单元结尾、需要原样保留的空段或纯布局块。

“归一化”不表示删除全部空段。只有已经被新的显式边界替代、且不属于新单元可见
页首或旧单元保留页尾的填页对象，才可以被标记为 `boundary_consumed`。源文件本身始终
不修改。

## 5. 模拟 Agent 输入

PoC 使用固定 fixture 表达未来 Agent 的最小输出：

```json
{
  "schema_version": 1,
  "source_sha256": "<sha256>",
  "render_ref": "mock-reference-render",
  "units": [
    {
      "unit_id": "declaration",
      "first_visible_anchor_text": "原创性声明",
      "first_visible_anchor_ref": {
        "schema_version": 1,
        "document_sha256": "<sha256>",
        "object_id": "obj-...",
        "expected_fingerprint": "<sha256>"
      },
      "next_visible_anchor_ref": {
        "schema_version": 1,
        "document_sha256": "<sha256>",
        "object_id": "obj-...",
        "expected_fingerprint": "<sha256>"
      },
      "starts_on_new_page": true,
      "visual_anchor": {
        "page": 2,
        "bbox_px": [210, 180, 1320, 224],
        "page_width_px": 1191,
        "page_height_px": 1684
      }
    }
  ]
}
```

fixture 不直接声明“保留第几个空段”。它只声明语义锚点、新页事实和参考页面上的位置。
具体空段归属必须由 Tool 解析和验证。

## 6. Tool 输出草案

PoC 的内部结果不是新的公开协议，但应使用稳定、可断言的结构：

```json
{
  "status": "resolved",
  "source_sha256": "<sha256>",
  "unit_id": "declaration",
  "source_boundary_mode": "natural_flow_with_layout_blocks",
  "section_geometry": {
    "page_width_twips": 11906,
    "page_height_twips": 16838,
    "orientation": "portrait",
    "margin_top_twips": 1440,
    "margin_bottom_twips": 1440,
    "margin_left_twips": 1800,
    "margin_right_twips": 1800,
    "header_distance_twips": 720,
    "footer_distance_twips": 720
  },
  "visual_metrics": {
    "anchor_page_top_twips": 1800,
    "anchor_content_top_gap_twips": 360
  },
  "resolved_boundary": {
    "mode": "next_page",
    "insert_before_ref": "obj-empty-b",
    "leading_layout_refs": ["obj-empty-b"],
    "trailing_layout_refs": ["obj-empty-c", "obj-empty-d", "obj-empty-e"],
    "boundary_consumed_refs": ["obj-empty-a"]
  },
  "candidate_evidence": {
    "selected_candidate_id": "candidate-1",
    "unique_match": true
  },
  "warnings": []
}
```

无法得到唯一结果时返回 `ambiguous` 或 `unsupported`，不得自动选择最接近但未达到门限的
候选。

## 7. 实现切片

### T0：固定样本与预期事实

1. 使用合成 DOCX 建立最小确定性 fixture；合成 fixture 不含学校专属事实。
2. 在用户已经授权的本地目录中，把湖南农业大学和北京大学模板作为探索性外部输入；只记录
   学校样本 ID、文件 basename、运行时 hash 和断言结果，不复制 DOCX、PDF、页面图片、
   绝对路径或正文到仓库。
3. 用模拟 Agent JSON 固定：首个可见锚点、新页事实、参考 bbox 和下一单元锚点。
4. 明确每个 case 的预期 `source_boundary_mode`、leading/trailing 归属和失败语义。

### T1：有序正文块账本

实现内部 body-block ledger，至少识别：

- 顶层 `w:p`、`w:tbl`、`w:sdt` 和最终 `w:sectPr`；
- 顶层或邻近书签边界；
- 空段、仅空白文字段、仅手动换行段和混合内容段；
- 显式 page break、`pageBreakBefore` 和 section break；
- 段落有效样式、字号、行距、段前段后距和 keep 属性；
- 每个块的当前文档 hash、稳定内部引用、顺序和原子容器边界。

PoC 不允许从表格、内容控件或混合正文段内部切断。遇到不支持对象时输出
`unsupported_atomic_boundary`。

### T2：节页面几何与视觉度量

1. 解析锚点所在节的纸张、方向、页边距、装订线、页眉/页脚距离和分栏事实。
2. 使用页面图片尺寸和 OOXML 页面尺寸把 bbox 从 px 归一化为 twips。
3. 同时保存：
   - 锚点相对物理页面顶部的位置；
   - 锚点相对正文区域顶部的位置。
4. 原型优先读取带文字层 PDF 的文字 bbox；能力发现证明不可用时，fixture 直接提供 bbox。
   本轮不引入 OCR。
5. 重复标题必须结合对象顺序、邻近文字、样式和下一锚点消歧；无法唯一匹配时返回
   `ambiguous_anchor_mapping`。

### T3：来源分页机制分类

按封闭分类返回：

```text
explicit_page_break
explicit_page_break_before
explicit_section_break
natural_flow_with_layout_blocks
natural_flow_without_layout_blocks
ambiguous
unsupported
```

`natural_flow*` 只能在模拟输入已经声明 `starts_on_new_page: true`、且结构中不存在显式
分页所有者时成立。Tool 不根据标题文字自行推断语义新页。

### T4：候选边界枚举

对于锚点前 `N` 个连续 layout-only block，生成最多 `N + 1` 个候选：

```text
候选 0：不保留 leading block
候选 1：保留最靠近锚点的 1 个
...
候选 N：保留全部 N 个
```

规则：

- 页面几何相同时，优先测试最小的显式分页所有者；
- 页面几何、页眉页脚或页码继承变化时，必须使用 section boundary；
- leading/trailing layout block 原样复制，不用统一默认字号重建；
- 候选只写入临时文件；每个候选均重新打开并完成 package 基础验证；
- 候选生成不得覆盖输入文件。

### T5：本地候选测量与唯一解

本轮只做同一 OfficeCLI 环境中的相对比较：

1. 生成原始文件的本地参考渲染；
2. 生成每个候选的本地渲染；
3. 比较同一引擎中的锚点正文区相对位置、上一语义对象位置、下一锚点位置、页数和意外
   空白页；
4. 使用固定容差选择唯一候选；
5. 零个或多个候选通过时返回 `ambiguous`，不发布归一化产物。

这里的结果只证明 Tool 算法和候选筛选能够工作，不证明 Microsoft Word 或 Adobe 最终
分页一致。

### T6：结构后置条件

选中候选必须同时满足：

- 源 hash 不变；
- 单元首尾锚点仍存在且内容指纹符合预期；
- semantic content 无丢失、无重复；
- 原子容器没有被拆开；
- 分页边界只有一个所有者；
- leading/trailing layout refs 与预期归属一致；
- 页边距、纸张、方向和关联页眉页脚符合来源节；
- 输出可重新打开并通过 OfficeCLI/package 基础验证；
- 同一输入重复运行产生相同分类、方案和内容 hash。

## 8. 首批测试矩阵

| Case | 来源结构 | 模拟视觉事实 | 预期结果 |
|---|---|---|---|
| C1 | 显式 page break | 新页、无额外留白 | 保留唯一显式边界 |
| C2 | `pageBreakBefore` | 新页、一个 leading 空段 | 去重后保留正确边界和空段 |
| C3 | next-page section | 新节使用不同页边距 | 保留节几何、页眉页脚和唯一 section boundary |
| C4 | 自然流，标题前两个空段 | 新页只显示一个空行 | 一个 leading、一个 boundary-consumed |
| C5 | 自然流，无空段 | 标题自然落到新页顶部 | 在锚点前建立显式边界，不删除内容 |
| C6 | 一个 leading、三个 trailing 空段 | 首尾留白都需要保留 | 精确保留 1 + 3 布局块 |
| C7 | 标题与换行混在同一正文段 | 新页 | `unsupported`，不从段内切断 |
| C8 | 同名标题同时出现在目录和正文 | 正文页锚点 | 使用上下文唯一映射，或安全返回 ambiguous |

湖南农业大学和北京大学本地案例只作为探索性外部对照；CI 仍只使用合成
fixture。学校案例的条件、执行顺序、断言和脱敏证据格式见配套
[`PoC 测试内容`](../../temp/docfit-unit-boundary-tool-poc-test-content.md)。

## 9. 主要测量目标

本 PoC 只有一个主要量化目标：

```text
eligible_fixture_boundary_resolution_rate
= 预期成功且得到唯一正确 boundary recipe 的 eligible fixture 数
  / 预期成功的 eligible fixture 总数

目标：6 / 6
```

C7/C8 的预期安全失败不进入分母，但必须得到指定错误语义且不发布输出。

该指标只支持“封闭 fixture 上的工具算法可行”这一结论，不能外推为任意真实模板准确率。

## 10. 验证命令

PoC 实现后至少执行：

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q tests/unit tests/integration
uv run docfit doctor
git diff --check
```

如果 PoC 未修改公开行为，不要求 Agent smoke 或 Adobe live 调用。若实现意外触及公开 Tool、
convert 路由、报告 schema 或渲染路由，立即停止并重新确认范围。

## 11. 成功、失败与下一步

### PoC 成功

同时满足：

- C1–C6 得到唯一正确 recipe；
- C7/C8 按预期安全失败或消歧；
- 源文件只读、候选临时、失败无输出；
- 相同输入重复运行结果一致；
- 零 Agent 调用、零 Adobe Document Transaction；
- 本地学校案例没有进入仓库或产品 Knowledge。

成功后只形成一份实现证据与正式设计建议。是否把能力接入现有 Tool，另行决定：

- 只读定位事实适合进入 `docx_inspect` 的内部结果；
- 候选渲染继续复用 `docx_render(edit_feedback)` 的既有职责；
- 真正边界归一化如果进入产品，应作为 `docx_edit` 的受控 operation，而不是新增第六 Tool；
- 确定性后置条件适合进入 `docx_validate`。

### PoC 失败

出现以下任一情况即停止，不通过增加 Agent 轮次掩盖 Tool 缺口：

- 无法稳定列举顶层原子块或节几何；
- bbox 无法与锚点对象唯一关联；
- 候选比较在固定 fixture 上仍经常多解；
- 必须依赖 Word 桌面、AppleScript、GUI session 或第三渲染引擎；
- 必须修改公开 Tool schema 才能完成实验；
- 需要把学校模板事实持久化为产品 Knowledge；
- 候选生成无法证明内容无损或失败不发布。

失败结论必须明确落在：定位、结构分类、候选生成、渲染测量或验证中的某一责任面。

## 12. 执行确认与结论

用户于 2026-08-04 批准完成代码、测试和优化闭环，并明确允许把湖南农业大学与北京大学
本地模板用于不入库的探索性测试。PoC 已按本计划执行完成：

1. 新增内部实验 helper 和 C1–C8 合成集成测试；
2. C1–C6 唯一正确 recipe 指标为 `6 / 6`，即 `100.0%`；
3. C7/C8 的原子边界拒绝、重复锚点消歧和安全歧义结果全部符合预期；
4. 两所学校的 eligible 外部探针均按预期执行并完成双跑一致性检查；
5. 没有新增公开 Tool、修改公开 schema、调用 Agent 或消耗 Adobe Document Transaction；
6. 结果仍只证明封闭合成 fixture 上的 Tool 算法可行，不是任意真实模板准确率。

完整分母、外部探针、优化记录和验证命令见独立的
[`PoC 执行结果`](../../temp/docfit-unit-boundary-tool-poc-results.md)。正式接入现有 Tool 或
转换链仍需单独批准实现计划并同步受影响的长期文档。

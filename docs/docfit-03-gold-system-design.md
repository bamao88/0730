# DocFit Eval 数据与 Gold（03）

> 状态：最终方案
> 日期：2026-07-31

## 1. Gold 的定位

Gold 是人工确认过的参考结果或关键事实，不是独立系统。

它用于：

- 防止已知正确结果回归；
- 给复杂断言提供人工确认的参照；
- 保存真实失败修复后的预期。

它不用于：

- 规定 Agent 必须走哪条完整路径；
- 复制运行时状态；
- 重放自定义工作流阶段；
- 替代真实 Word 查看和人工判断。

Tool tests 使用普通 fixture 和期望值；Skill eval 与端到端 Eval 只有在事实断言不足时才保存 Gold 产物。

## 2. 最小形式

一个 Eval case 至少需要输入和断言。只有断言无法清楚表达时，才附参考产物。

```text
evals/e2e/hunannongye-basic-001/
├── case.yaml
├── input/
│   └── student.docx
├── expected/
│   ├── facts.yaml
│   ├── visual-findings.yaml # 可选，人工确认的页面视觉问题与 evidence 定位
│   ├── pages/               # 可选，只保存确有比较价值的参考页面
│   └── final.docx           # 可选
└── notes.md                 # 可选
```

`case.yaml` 示例：

```yaml
id: hunannongye-basic-001
skill: convert-thesis
school_knowledge:
  id: hunannongye
  version: v1
  content_digest: sha256:...
task: 按目标学校要求转换论文
assertions:
  - type: docx_opens
    path: output/final.docx
  - type: text_preserved
    expected_from: expected/facts.yaml
  - type: style_fact
    target: heading_level_1
    expected: school_profile.heading_1
  - type: text_absent
    values: ["小二黑体加粗", "在此填写"]
  - type: visual_review_coverage
    expected: all_final_pages
  - type: no_blocking_visual_findings
manual_review: [cover_page, toc_pagination]
```

用户同时提供模板和论文的用例仍属于 `convert-thesis`。测试可以断言 Agent 使用了当前模板证据且没有把它写入长期 Knowledge，但不保存固定调用轨迹或命名的中间资产。

## 3. 断言优先

优先保存稳定事实：

- 标题和章节层级；
- 学生正文关键文本；
- 表格、图片、公式及其他支持对象的数量和必要顺序；
- 目标有效样式；
- 必填字段内容；
- 页面数量或允许范围；
- 不应残留的占位符和说明文字；
- 人工确认的溢出、遮挡、空白页、孤行、图表错位和页眉页脚异常；
- 视觉 finding 所对应的文档 hash、页码、render purpose、fidelity claim、Provider、字体环境和 evidence ref；
- 需要人工检查的高风险页面。

只有以下情况保存完整 `final.docx` 或少量参考页面图片：

- 需要人工查看复杂页面；
- 结构化断言暂时覆盖不了关键差异；
- 它是已经确认的真实交付基线。

完整文件和页面图片是辅助参照，不能自动覆盖事实断言。像素差异也不能单独证明版式语义正确。不同 Provider、字体、DPI、页面尺寸或 fidelity claim 的页面不得直接做像素 Gold 比较；需要比较快速迭代渲染与 Microsoft Word 目标渲染时，保存页数、bbox、问题类别和人工结论等稳定事实。

## 4. 比较方式

| 模式 | 用途 |
|---|---|
| `exact` | 不应变化的源文件或 Knowledge 资产 |
| `normalized` | 忽略时间戳、随机 ID 后的结构化结果 |
| `set` | 标题、对象或问题集合 |
| `tolerance` | 尺寸、位置、页数等允许小范围变化的数据 |
| `fact` | Agent 结果和最终文档的关键事实 |
| `visual_fact` | 人工确认的视觉问题类别、页码、严重度和页面证据 |
| `manual` | 当前无法稳定自动判断的页面视觉 |

每条断言说明期望、实际值和证据位置。普通测试代码足够时，不设计新的断言语言。

## 5. Gold 的产生

Gold 只从已经实际运行并人工确认的结果产生：

1. 用当前 Skill、Knowledge 和 Tools 处理样本；
2. 运行确定性断言；
3. 通过 `docx_visual_review` 查看与当前文档绑定的页面图片；
4. 人工检查断言覆盖不到的关键页面，并确认或修正 Agent 的 visual findings；
5. 提取最少、稳定的事实到 `facts.yaml` 和可选 `visual-findings.yaml`；
6. 必要时保存参考 `final.docx` 或少量页面图片；
7. 记录确认人、日期、Knowledge 版本、content digest、render purpose、fidelity claim、Provider、字体环境和原因。

禁止模型仅凭自己的新输出自动更新 Gold。

## 6. Gold 的更新

回归失败时先判断：

- 实现退化：修复 Skill、Knowledge 或 Tool；
- Gold 过时：人工确认新结果后更新断言或参考产物；
- 比较方式过脆：把逐字节比较收缩为事实断言；
- 输入或 Knowledge 变更：创建新 case 或提升 case 版本。

更新时保留变更原因。版本控制历史足以满足当前阶段，不增加发布服务。

## 7. 合成样本与真实样本

合成样本适合验证单一风险：

- 重复或丢失段落；
- 跨 run 的说明文字；
- 表格、合并单元格、图片、公式；
- 域、内容控件、脚注和文本框；
- 旧目录、空附录标题和双语图题；
- 缺少摘要或参考文献；
- 占位符未清理；
- 对象引用失效和 Provider 伪成功。

真实样本适合验证组合效果和页面观感。

两者都应尽量脱敏。含真实学生内容的样本不得进入公开仓库；公开 CI 使用人工构造或获得授权的文件。

## 8. 明确不采用

当前架构不采用：

- 多层 Gold 体系；
- Stage Harness；
- 阶段输入胶囊；
- exact/comparative replay；
- trajectory Gold；
- 自动 Gold 晋升；
- Gold catalog 服务。

如果需要单工具隔离复现，直接在 Tool test 中保存输入 fixture 和期望输出，不把它升级为 Agent runtime 协议。

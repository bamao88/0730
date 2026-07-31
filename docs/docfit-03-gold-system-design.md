# DocFit Eval 数据与 Gold（03）

> 状态：最小数据设计
> 日期：2026-07-30

## 1. Gold 的定位

Gold 是人工确认过的参考结果或关键事实，不是一个独立系统。

Gold 主要服务 L3 Skill Eval 和 L4 端到端 Eval。L1/L2 的 fixture 与普通期望值放在 `tests/`，不需要升级成 Gold。

它用于：

- 防止已知正确结果回归；
- 给复杂断言提供人工确认的参照；
- 保存真实失败修复后的预期。

它不用于：

- 规定 Agent 必须走哪条完整路径；
- 复制运行时状态；
- 重放某个自定义工作流阶段；
- 替代真实 Word 查看和人工判断。

## 2. Gold 的最小形式

一个 Eval case 至少需要输入和断言。只有断言无法清楚表达时，才附参考产物。

```text
evals/e2e/l4-hunannongye-basic-001/
├── case.yaml
├── input/
│   └── student.docx
├── expected/
│   ├── facts.yaml
│   └── final.docx       # 可选
└── notes.md             # 可选
```

`case.yaml` 示例：

```yaml
id: l4-hunannongye-basic-001
level: L4
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
manual_review: [cover_page, toc_pagination]
```

每个 L3/L4 case 只声明一个主要 Skill。两个 Skill 的稳定 Gold 事实不同：

| Skill | 优先保存的事实 |
|---|---|
| `prepare-school-template` | Draft 到正式 Knowledge 的适用范围、版本、人工确认和复用所需文件 |
| `convert-thesis` | 正式 Knowledge 命中或任务级 Draft 使用、源论文 hash、内容覆盖、最终 DOCX、格式、结构、渲染与人工页面复核 |

共享模板提取能力不是第三个 Skill。它的确定性 schema、digest 和引用规则由 L1 覆盖，Tool 提取事实由 L2 覆盖，Agent 形成 Draft 的语义行为由两个 Skill 对应的 L3 case 覆盖。

用户同时提供模板和论文的转换 case 仍属于 `convert-thesis`。Gold 可以引用共享 Draft facts 和论文内容分析，但不把它们保存为第三个 Skill 或固定调用轨迹。

## 3. 断言优先

优先保存稳定事实：

- 标题和章节层级；
- 学生正文关键文本；
- 表格、图片、公式数量；
- 目标样式；
- 必填字段内容；
- 页面数量或允许范围；
- 不应残留的占位符和说明文字。

只有在以下情况下保存完整 `final.docx`：

- 需要人工查看复杂页面；
- 结构化断言暂时覆盖不了关键差异；
- 它是一个已经确认的真实交付基线。

完整文件是辅助参照，不能自动覆盖事实断言。

## 4. 比较方式

| 模式 | 用途 |
|---|---|
| `exact` | 不应变化的源文件或 Knowledge 资产 |
| `normalized` | 忽略时间戳、随机 ID 后的结构化结果 |
| `set` | 标题、对象或问题集合 |
| `tolerance` | 尺寸、位置、页数等允许小范围变化的数据 |
| `fact` | Agent 结果和最终文档的关键事实 |
| `manual` | 当前无法稳定自动判断的页面视觉 |

每条断言应说明期望、实际值和证据位置。不要为了统一而设计一门新的断言语言；普通测试代码足够时直接使用。

## 5. Gold 的产生

Gold 只从已经实际运行并人工确认的结果产生：

1. 用当前 Skill、Knowledge 和 Tools 处理样本；
2. 运行确定性断言；
3. 人工检查断言覆盖不到的关键页面；
4. 提取最少、稳定的事实到 `facts.yaml`；
5. 必要时保存参考 `final.docx`；
6. 记录确认人、日期、Knowledge 版本、content digest 和原因。

禁止模型仅凭自己的新输出自动更新 Gold。

## 6. Gold 的更新

回归失败时先判断：

- 实现退化：修复 Skill、Knowledge 或 Tool；
- Gold 过时：人工确认新结果后更新断言或参考产物；
- 比较方式过脆：把逐字节比较收缩为事实断言；
- 输入或 Knowledge digest 变更：创建新 case 或提升 case 版本。

更新 Gold 时保留变更原因。无需不可变发布服务；版本控制历史即可满足当前阶段。

## 7. 合成样本与真实样本

合成样本适合验证单一风险：

- 重复/丢失段落；
- 跨 run 的说明文字；
- 表格、图片或公式；
- 缺少摘要或参考文献；
- 占位符未清理。

真实样本适合验证组合效果和页面观感。

两者都应尽量脱敏。含真实学生内容的样本不得进入公开仓库；公开 CI 使用人工构造或获得授权的文件。

## 8. 不再采用的设计

当前架构不采用：

- 旧设计中的 G1/G2/G3/G4 四层 Gold；
- Stage Harness；
- StageExecution 输入胶囊；
- exact/comparative replay；
- trajectory Gold；
- 自动 Gold 晋升；
- Gold catalog 服务。

如果将来确有单工具隔离重放需求，直接在 L1/L2 测试中保存输入 fixture 和期望输出，不把它升级为 Agent runtime 协议。

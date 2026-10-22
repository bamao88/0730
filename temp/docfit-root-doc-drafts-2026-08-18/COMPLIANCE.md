# 根文档候选稿对照检查

状态: temp 检查记录
日期: 2026-08-18

检查对象：

- `temp/docfit-root-doc-drafts-2026-08-18/README.md`
- `temp/docfit-root-doc-drafts-2026-08-18/ARCHITECTURE.md`
- `temp/docfit-root-doc-drafts-2026-08-18/STATUS.md`

检查依据：

- `temp/docfit-document-system-reorganization-draft-2026-08-18.md` 的目标目录结构注释。
- 同一草案的“目标文档面”定义。
- 用户给出的原则：README 只回答项目是什么、怎么跑、当前主要入口；ARCHITECTURE 写系统结构；
  STATUS 写当前状态。

## 逐项结论

| 文档 | 定义 | 对照结果 | 证据 |
| --- | --- | --- | --- |
| `README.md` | 项目入口：项目是什么、怎么跑、当前主要入口 | 符合 | 只包含“这个项目是什么”“怎么跑”“当前主要入口”三节；没有放开发历史、长计划或复杂架构 |
| `ARCHITECTURE.md` | 全局架构：模块边界、数据流、关键接口、扩展点和禁区 | 符合 | 包含底层 SDK 心智模型、三模块边界、数据流、共享层、关键接口、可扩展点、禁止改变项和失败定位 |
| `STATUS.md` | 当前状态：可用能力、正在做什么、已知问题和下一步 | 符合 | 包含“现在可用”“并行模块状态”“当前主要工作”“已知问题”“下一步”“恢复入口” |

## 负面检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| README 是否塞入产品路线图 | 通过 | README 只保留当前模块摘要和运行入口，路线图留给 STATUS/计划。 |
| README 是否塞入复杂架构 | 通过 | 只提三模块，不展开 SDK/Harness/Tool 细节。 |
| ARCHITECTURE 是否写函数细节 | 通过 | 只写模块、层、接口和边界，没有函数级说明。 |
| ARCHITECTURE 是否混入任务计划 | 通过 | 不记录迁移步骤或当前 bug 执行计划。 |
| STATUS 是否写永久架构解释 | 通过 | 只引用当前架构和模块状态，不展开长期设计论证。 |
| STATUS 是否写完整测试日志 | 通过 | 只列可用验证面，不粘贴测试输出。 |
| 三份文档是否默认引导 Agent 读取 human 长文档 | 通过 | 默认入口是根文档、`docs/README.md`、`docs/modules/README.md`、`tests/README.md`。 |
| 三份文档是否把 temp 草案伪装成当前真相 | 通过 | 每份文件开头都标注 temp 候选稿；STATUS 只把 temp 草案列为当前重组草案。 |

## 正式替换前必须修正

1. 删除三份候选稿开头的 `temp 候选稿，未替换...` 状态，改成正式状态。
2. 确认正式 `docs/README.md` 是否已经接管文档生命周期规则。
3. 确认 `docs/docfit-00-index.md` 是删除、兼容跳转，还是短期保留为二级索引。
4. 用 `rg` 检查正式文档里是否仍把旧索引当作上位契约或当前权威。
5. 跑 `uv run pytest -q tests/contract/test_documentation_contract.py`。

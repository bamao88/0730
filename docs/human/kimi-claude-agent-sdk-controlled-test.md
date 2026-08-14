# Kimi 接入 Claude Agent SDK 控制变量测试记录

本文记录 2026 年 8 月 6 日针对 Kimi 调用稳定性开展的一组真实控制变量测试。测试的
目标不是评价模型回答质量，而是确认 Kimi 通过 Claude Agent SDK 完成多轮 Tool 调用时，
哪些变量会导致或避免此前日志中出现的 HTTP 400。

## 一句话结论

本轮 9 次真实 Kimi API 调用全部成功，没有复现 HTTP 400。当前测试证据不支持为了
解决 400 而把默认模型从 `kimi-for-coding` 切换为 `k3-256k`：两者成功率相同，K3 在
相同 12 步 Tool 负载下平均慢约 5.4 倍。

## 为什么这样测试

历史运行在 Kimi 后端出现过 HTTP 400，但隐私安全日志只保存了状态码，没有保存
Provider 原始错误正文。为了避免根据单条旧日志猜测原因，本次固定 API Key、endpoint、
SDK、Tool、结构化输出和提示要求，每次只改变一个变量：

- 短请求与 12 步 Tool 链；
- `kimi-for-coding` 与 `k3-256k`；
- 显式 `high`、不显式设置 effort、关闭 thinking；
- Tool Search 关闭或开启。

这种测试可以回答“某个变量单独改变时，结果是否随之改变”，但不能证明所有真实论文
转换任务都不会再次遇到 Provider 兼容问题。

## 固定测试条件

- `claude-agent-sdk==0.2.128`；
- SDK 捆绑 Claude Code `2.1.220`；
- Kimi Anthropic 兼容 endpoint：`https://api.kimi.com/coding/`；
- 同一个 Kimi Code API Key，只从仓库外权限为 `0600` 的环境文件读取；
- 每次运行使用独立的临时 Claude 配置目录；
- SDK 自动重试次数为 0，使一次 Provider 结果直接成为测试结果；
- 长负载使用同一个本地 in-process MCP 状态机 Tool；
- 长负载必须严格串行完成 12 步，每一步都依赖上一步返回的 token；
- 最终均要求返回同一个 JSON Schema 结构化结果；
- 不读取论文，不调用 OfficeCLI 或 LibreOffice，不把 Key、提示正文或 Provider 错误正文写入
  证据。

## 逐次测试记录

| # | 模型 | 负载 | effort/thinking | Tool Search | 结果 | 总耗时 | turns | 有效 Tool 步骤 | HTTP 状态 |
|---:|---|---|---|---|---|---:|---:|---:|---|
| 1 | `kimi-for-coding` | 短请求 | `high` | off | PASS | 16.886 秒 | 3 | 0 | 无错误 |
| 2 | `kimi-for-coding` | 12 步 | `high` | off | PASS | 40.218 秒 | 14 | 12 | 无错误 |
| 3 | `kimi-for-coding` | 12 步 | `high` | off | PASS | 42.641 秒 | 14 | 12 | 无错误 |
| 4 | `k3-256k` | 12 步 | `high` | off | PASS | 224.400 秒 | 14 | 12 | 无错误 |
| 5 | `k3-256k` | 12 步 | `high` | off | PASS | 221.376 秒 | 14 | 12 | 无错误 |
| 6 | `kimi-for-coding` | 12 步 | 未显式设置 | off | PASS | 52.903 秒 | 14 | 12 | 无错误 |
| 7 | `kimi-for-coding` | 12 步 | `high` | on | PASS | 46.976 秒 | 14 | 12 | 无错误 |
| 8 | `kimi-for-coding` | 12 步 | thinking off | off | PASS | 42.214 秒 | 14 | 12 | 无错误 |
| 9 | `kimi-for-coding` | 12 步 | thinking off | off | PASS | 57.419 秒 | 14 | 12 | 无错误 |

9 次结果均为 `terminal_reason=completed`，最终结构化输出均通过验证。

## 聚合结果

| 对照组 | 通过率 | 平均耗时 | 观察 |
|---|---:|---:|---|
| `kimi-for-coding`，12 步，high，Search off | 2/2 | 41.4 秒 | 当前生产配置基线通过 |
| `k3-256k`，12 步，high，Search off | 2/2 | 222.9 秒 | 通过率相同，约慢 5.4 倍 |
| `kimi-for-coding`，12 步，thinking off | 2/2 | 49.8 秒 | 当前版本未复现旧 thinking 兼容错误 |

## 各项假设的判定

### 1. 多轮 Tool 历史是否必然导致 400

否。两个模型合计 6 次完成 12 步依赖 Tool 链，没有 HTTP 400。

### 2. 换成 K3 是否能修复 400

没有证据支持。K3 和 `kimi-for-coding` 在固定长负载上都是 2/2 通过，区别主要是 K3
明显更慢。因此不能把“模型更新”当作本次问题的修复措施。

### 3. 显式 high 是否是当前可调用性的必要条件

不是。不显式设置 effort 和明确关闭 thinking 的组合也通过。项目仍应保留官方建议的
`high`，因为它能固定宿主配置并保持预期模型能力，但本轮结果不支持把它描述成解决
所有 400 的充分条件。

### 4. Tool Search 是否必然导致 400

在本次小 Tool 集下不是：Search on 组合通过。这个结论不能外推到拥有大量可搜索 Tool、
会实际生成 `tool_reference` 的会话；生产配置继续关闭 Tool Search 更稳妥。

### 5. 历史错误是否来自上下文过大

现有证据不支持。2026 年 8 月 4 日的旧失败记录只有约 6.2K 非缓存输入 Token、29.5K
缓存读取 Token 和 10 turns，明显低于 256K 上下文边界。

## 历史错误与当前结果如何同时成立

旧错误发生在 2026 年 8 月 4 日 15:59（Asia/Shanghai）。项目在同日 21:14 的提交
`919cb9d` 中才加入显式 `CLAUDE_CODE_EFFORT_LEVEL=high`，并将 HTTP 400 改为不在同一
Kimi route 上轮换 Key 重放。旧日志因此确实来自修复前代码。

不过，旧日志没有保存 Kimi 原始错误正文，而当前 SDK 和当前 Kimi 服务端即使关闭
thinking 也无法复现旧 400。严谨结论只能是：历史问题与修复时间线一致，当前受测路径
不可复现；不能进一步断言旧请求中究竟缺少了哪个字段。

## 当前建议

- 保留 `kimi-for-coding + high + Tool Search off`；
- 保留 MiniMax fallback；
- 不因本次 400 把默认模型切换为 K3；
- HTTP 400 不在同一个 name/base URL/model route 上重放；
- 若 400 再次出现，在丢弃原始错误正文前，将 Kimi 已知错误关键词归一化为隐私安全的
  原因码，例如正文过大、Token 超限、reasoning content 缺失或 Tool 名称重复；
- 将完整论文 conversion 作为单独的产品级 live gate，不与本次 SDK 控制变量实验混为
  一组。

## 原始证据与复跑入口

原始证据继续保存在 `test`，它们是本页数据的执行依据：

- [短请求基线](../../test/evidence/kimi-controlled/phase1-short.json)
- [`kimi-for-coding` 长链两次](../../test/evidence/kimi-controlled/current-long-repeat2.json)
- [`k3-256k` 长链两次](../../test/evidence/kimi-controlled/k3-long-repeat2.json)
- [默认 effort 与 Tool Search 对照](../../test/evidence/kimi-controlled/flags-one-each.json)
- [关闭 thinking 两次](../../test/evidence/kimi-controlled/thinking-off-repeat2.json)
- [控制变量测试程序](../../test/kimi_controlled_probe.py)
- [`test` 下的执行报告](../../test/KIMI-CONTROLLED-TEST-REPORT.md)

这些 JSON 只包含模型名、变量组合、状态、轮次、Tool 计数和耗时，不包含凭据、论文
内容、提示正文或 Provider 原始错误正文。

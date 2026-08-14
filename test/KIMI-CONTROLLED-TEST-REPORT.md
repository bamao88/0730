# Kimi × Claude Agent SDK 控制变量测试报告

测试日期：2026-08-06
测试性质：真实 Kimi API、隐私安全元数据、无论文内容、无 Adobe/OfficeCLI 调用
本地版本：`claude-agent-sdk==0.2.128`，捆绑 Claude Code `2.1.220`

## 结论

当前 Kimi 接入可以稳定完成短请求和 12 步依赖 Tool 链。本轮共执行 9 次 live
调用，9 次通过，未出现 HTTP 400。因此 2026-08-04 的历史错误在当前版本和当前
服务端上不可复现。

不建议仅为“解决 400”把默认模型从 `kimi-for-coding` 改成 `k3-256k`：两者在本轮
固定长链上的成功率相同，而 K3 两次平均耗时约 222.9 秒，`kimi-for-coding` 基线
两次平均约 41.4 秒，K3 约慢 5.4 倍。

## 固定条件

- 同一 Kimi Code API Key（只从仓库外 `0600` 环境文件读取，不写入测试产物）
- 同一 Anthropic 兼容 endpoint：`https://api.kimi.com/coding/`
- 同一 Claude Agent SDK 与捆绑 Claude Code
- 同一隔离配置目录、超时、零 SDK 自动重试
- 同一 in-process MCP 状态机 Tool
- 长负载均要求严格串行完成 12 次有前后令牌依赖的 Tool 调用
- 同一 JSON Schema 结构化终态

## 单变量结果

| 变量组合 | 次数 | 结果 | 平均耗时 | turns | 有效 Tool 步骤 |
|---|---:|---|---:|---:|---:|
| `kimi-for-coding`，短请求，high，Search off | 1 | PASS | 16.9 秒 | 3 | 0 |
| `kimi-for-coding`，12 步，high，Search off | 2 | 2/2 PASS | 41.4 秒 | 14 | 12 |
| `k3-256k`，12 步，high，Search off | 2 | 2/2 PASS | 222.9 秒 | 14 | 12 |
| `kimi-for-coding`，12 步，不显式设置 effort | 1 | PASS | 52.9 秒 | 14 | 12 |
| `kimi-for-coding`，12 步，thinking off | 2 | 2/2 PASS | 49.8 秒 | 14 | 12 |
| `kimi-for-coding`，12 步，high，Search on | 1 | PASS | 47.0 秒 | 14 | 12 |

所有结果的 `api_error_status` 均为空，`terminal_reason=completed`，结构化输出均通过。

## 对假设的判定

1. “只要存在长 Tool 历史就会 400”：否定。12 步链在两个模型上共 6 次通过。
2. “换成 K3 可修复 400”：没有证据支持。成功率相同，K3 仅表现为明显更慢。
3. “未显式设置 high 就必然失败”：否定。默认 effort 与 thinking off 均通过。
4. “启用 Tool Search 就必然失败”：在当前小 Tool 集上否定；Search on 通过。这个结果
   不代表包含大量可搜索 Tool 的会话不存在兼容风险。
5. “历史错误由上下文或请求体过大导致”：现有元数据不支持。旧失败只有约 6.2K
   非缓存输入 Token、29.5K 缓存读取 Token、10 turns，远低于 256K 上下文边界。

## 历史错误的边界

旧运行发生于 2026-08-04 15:59（Asia/Shanghai）。项目在同日 21:14 才提交显式
`CLAUDE_CODE_EFFORT_LEVEL=high` 以及 HTTP 400 不重放同一路由的修复，所以旧记录确实
来自修复前代码。

这只能说明时间线与历史兼容缺陷一致，不能证明具体错误字段。旧观测记录按隐私策略
没有保存 Kimi 原始错误正文；当前服务端即使明确关闭 thinking 也不再复现该 400。

## 建议

- 暂时保留 `kimi-for-coding + high + Tool Search off` 和 MiniMax fallback。
- 不因本次问题默认切换到 K3；若以后需要 K3 的模型能力，应单独评估其约 5 倍时延。
- 若 400 再次出现，在丢弃原始错误正文前，将 Kimi 官方已知关键词归一化为安全错误码，
  例如 `message_body_too_large`、`token_limit_exceeded`、
  `reasoning_content_missing`、`duplicate_tool_name`。
- 400 继续禁止同 route/key 轮换重放；429/5xx 与 400 分开处理。

## 证据

- `test/evidence/kimi-controlled/phase1-short.json`
- `test/evidence/kimi-controlled/current-long-repeat2.json`
- `test/evidence/kimi-controlled/k3-long-repeat2.json`
- `test/evidence/kimi-controlled/flags-one-each.json`
- `test/evidence/kimi-controlled/thinking-off-repeat2.json`
- 可复跑 harness：`test/kimi_controlled_probe.py`

证据只包含模型名、变量组合、结果状态、轮次、Tool 计数和耗时；不包含 Key、提示正文、
Provider 原始错误正文或论文内容。

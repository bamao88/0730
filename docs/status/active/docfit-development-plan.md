# DocFit Current Development Capsule

- Capsule status: COMPLETED
- Source plan: `docs/plans/docfit-development-plan.md`
- Child plan: `docs/plans/docfit-m1-tools-v1.md`
- Latest user intent: M3 评测不在当前开发范围；确认非评测产品面完整完成
- Current slice: M0–M2 产品链路及其非评测支撑已完成；当前计划无剩余开发项
- Completed foundation: M0、通用 Knowledge v1、P1 两个 Skill/选择性 Knowledge/唯一
  只读 Subagent；五个 Tool、M2 薄壳与 M3 core Eval 的既有实现保留
- Fixed backend contract: OfficeCLI 1.0.143 负责 inspect/edit/validate/edit feedback；
  Adobe PDF Services SDK 4.2.0 负责 baseline/candidate DOCX→PDF；无本地 Word、
  AppleScript、GUI session 或本地字体依赖
- Credential state: Adobe service-principal 三字段已从本机 SDK bundle 迁入仓库外
  `~/.config/docfit/agent.env`，mode 0600；原 bundle 保留且 mode 0600；值未输出或入库
- Quota rule: Adobe cache miss 消耗一个 Document Transaction；cache hit 不调用 API；
  开发容量按每月 500 次免费额度规划
- Current evidence: `uv sync --frozen`、lock check、sdist/wheel、ruff、strict mypy、124
  pytest、base/provider/agent-smoke doctor、真实 SDK 合成 convert 与 diff check 全部 PASS；
  core Eval 7/7（41 assertions）仅作为已存在的可选开发资产
- Adobe live proof: 合成 baseline 与 candidate 各成功生成完整 2 页 PDF/PNG，candidate
  parent ref 正确；同一 baseline 重跑 cache hit 且 render hash 不变；contact sheet 人工
  查看无 blocking finding。月度实际消耗以 Adobe 控制台为准，不从本地成功次数推算余额
- Resolved blocker: `agent_backend_multimodal_transport` 实际根因为顶层 `oneOf` 被兼容
  backend 生成为 `{"oneOf":"m0_image_smoke"}`，Tool 从未产生图片；视觉 schema 扁平化
  后 image 与只读 subagent 在 Kimi 通过，ask-user 在 MiniMax fallback 通过
- Receipt truth: 已修复“失败后旧 PASS 回执仍生效”的漏洞；当前四条回执均来自本轮真实
  SDK 会话，`doctor --require agent-smoke` 为 PASS
- Live M2 proof: MiniMax 真实 SDK convert 返回 COMPLETED；两 Skills 与五 Tool 均有调用，
  源 hash 不变，根目录 final.docx、当前 Adobe candidate PDF/ref、2 页全页 review、
  validation 均发布；candidate 绑定 final hash，errors=0、verification_gap=0、blocking=0
- Live defects fixed: 兼容 backend 不支持 JSON Schema composition；SDK MCP bridge 丢弃
  structuredContent；只读输入 mode 被 copy2 传播到编辑副本；同 route 超时重复轮换 key。
  Adobe SDK 默认写超时不足以上传复杂 DOCX；SDK 默认 1 MiB 消息 buffer 无法承载真实
  页面图片；过长小字号 image-smoke marker 导致 OCR 不稳定；无凭据 CLI 测试污染真实
  smoke 回执；成功 conversion report 重放中间 Agent 的旧 warning/summary。九项均已有
  修正和回归证明
- Deferred M3 evidence: 授权复杂样本曾完成 15 页 Adobe baseline/candidate/cache、全页 Agent
  review、页 7 局部 crop、同快照 OfficeCLI/Adobe anchor 对照和独立高风险复核；源 hash
  不变，私有正文未进入仓库。结果为 FAIL，共 6 个 blocking finding；外部人工签字为
  NOT_PERFORMED。该证据不属于当前完成门，不继续作为 blocker，也不代表 M3 通过
- Deferred scope: M3 Skill/E2E Eval、Gold、真实样本资格验证和外部人工复核；恢复时
  依据 06 第 7 节另建计划
- Stop condition: 当前计划已完成；任何第六 Tool、第三引擎、第二 Agent loop、恢复 M3
  或长期合同冲突须先请求决定
- No-touch scope: M4/M5、GUI/API/任务队列、学校规则持久化、通用 Provider 抽象

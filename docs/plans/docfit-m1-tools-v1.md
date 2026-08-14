# DocFit M1 五个 Tool 与双固定后端 Preflight

> 状态：COMPLETED，由到 M3 的统一用户目标批准并验收
> 日期：2026-08-03
> 上位契约：`docs/docfit-00-index.md`–`docs/docfit-06-development-roadmap.md`

## Plan Ledger

- Plan status: COMPLETED
- Session scope: m1-tools-v1
- Parent plan: `docs/plans/docfit-development-plan.md`
- Child plans: none
- Last updated: 2026-08-03
- Current slice: 已把错误的本地 Word/AppleScript 路径完整迁移到 Adobe PDF Services
- Fixed backends: OfficeCLI 1.0.143；Adobe PDF Services SDK 4.2.0
- No product dependency: Microsoft Word desktop、AppleScript、`osascript`、macOS GUI
  session、本地字体库存
- This child plan does not govern: M2/M3（由上位统一计划管理）、M4/M5、第三引擎、
  通用 Provider 抽象

## 已确认的证据

- 五个稳定 `mcp__docfit__...` Tool 名称、默认拒绝边界和公开 render intent 不变。
- OfficeCLI 1.0.143 负责 inspect/edit/validate/`edit_feedback`；锁定 binary hash 继续由
  doctor 验证。
- Adobe 本机 SDK bundle 包含 service-principal credential JSON 和
  `pdfservices-sdk==4.2.0` 示例；凭据已迁入仓库外 `~/.config/docfit/agent.env`，mode
  0600，值不进入仓库、日志或文档。
- Adobe PDF Services 对 DOCX→PDF 的缓存未命中按一个 Document Transaction 计；开发
  容量按每月 500 次免费额度规划。
- Poppler 只在本地把 Adobe 返回的完整 PDF 派生为逐页 PNG，不是转换 Provider。
- Adobe 未公开服务端字体库存和替代详情，因此 evidence 必须标记为
  `service-managed` / `opaque`，不得填入本地字体指纹。

## 固定实现合同

1. `docx_inspect` / `docx_edit` / `docx_validate` 和 `edit_feedback` 只走 OfficeCLI。
2. `baseline` / `candidate_verification` 只走 Adobe PDF Services；公开 schema 拒绝
   provider/backend selector，Adobe 失败不回退 OfficeCLI。
3. Adobe render ref 固定声明：
   `provider.name=adobe_pdf_services`、`provider.version=4.2.0`、
   `fidelity=official_service_conversion`、
   `conversion_profile=adobe_pdf_services_default`、`target_application=null`、
   `revision_display=document_default`。
4. 每个 Adobe cache miss 完整上传一次 DOCX、下载一次 PDF；逐页图片、contact sheet、
   crop 和 compare 均从该 PDF 本地派生。cache hit 不调用 API、不消耗额度。
5. 服务异常、凭据错误、额度耗尽、SDK 错误和无效 PDF 映射为安全 Tool failure；不打印
   Provider 原始错误体，不发布部分输出。
6. `docx_visual_review` 只读取已有 render ref，不调用 OfficeCLI 或 Adobe，不产生新
   render ref。
7. 源文档只读；工作副本、原子发布、opaque ref、parent ref、路径授权、图片预算和
   independent validation 语义保持不变。
8. Adobe SDK 使用固定 30 秒连接、120 秒读写超时；真实复杂 DOCX 上传不得受 SDK 默认
   短写超时影响，超时仍按安全 Tool failure 处理且不发布部分输出。

## Acceptance

- `uv sync --frozen`、`uv lock --check`、build、ruff、strict mypy、全测试和 base doctor
  通过。
- `docfit doctor --require provider` 对 OfficeCLI、Adobe SDK/凭据和 Poppler 返回 PASS，
  且不检查本地 Word、AppleScript、GUI session 或本地字体。
- 单元/契约测试覆盖 Adobe service-principal 调用、完整 PDF、错误不回退、三 intent、
  cache/parent ref、source hash 和无部分发布。
- 合成 baseline/candidate live 调用生成 PDF、全页 PNG 和 current render ref；cache hit
  证明不重复调用 API。
- 用户授权或脱敏样本的源 hash 前后不变，所有学生正文和凭据值都不进入日志或提交。
- 00–06、README、AGENTS、Skills、Eval、迁移清单、上位计划和 active capsule 无旧
  Word 依赖残留。

## Verification

```bash
uv sync --frozen
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
uv run docfit doctor --require provider
uv run docfit tools render evals/fixtures/smoke/student.docx \
  --intent baseline --output .tmp/smoke/render-adobe-baseline
uv run docfit tools render .tmp/smoke/edited.docx \
  --intent candidate_verification \
  --baseline-ref .tmp/smoke/render-adobe-baseline/render-ref.json \
  --output .tmp/smoke/render-adobe-candidate
```

## Stop / expansion gates

- 停止并请求决定：需要第六个公开 Tool、第三引擎、通用 Provider 注册表、第二 Agent
  loop、OfficeCLI fork、学校规则持久化或把凭据放进仓库。
- 普通可恢复错误：Adobe 网络、凭据、额度或服务失败。保留 `verification_gap`，修复后
  重跑；不新增产品状态，不改走 OfficeCLI 冒充交付证据。
- M1 完成不代表 M2/M3 完成；真实 SDK convert、复杂样本和人工高风险页面仍按 06 各自
  验收。

## Completion result

- deterministic、build、provider doctor、六条开发者 CLI 门全部通过；
- Adobe 合成 2 页和授权复杂 15 页 baseline/candidate 均成功，parent ref、source hash、
  完整 PDF/PNG、cache hit 与同一 render hash 可核对；
- OfficeCLI 只承担结构化处理和近似 edit feedback，Adobe 只承担正式 baseline/candidate，
  不存在本地 Word、AppleScript、GUI session 或本地字体依赖；
- 授权复杂样本随后在 M3 质量门被正确判为 FAIL。该质量结果不否定 M1 Tool 完成，也不
  构成 M3 完成证据。

# DocFit 学校模板提取 v2 执行胶囊

- Capsule status: `IN PROGRESS / PHASE-SEPARATED FINAL VISUAL GATE`
- Latest user decision: 不做最小闭环；提交旧基线后完整重构，不保留兼容。最终验收是重新运行
  MiniMax CLI 后只得到一份 Word，且模板清理、内容槽与可用质量相对旧运行有实质提高。
- Baseline commit: `6660d46` 保存旧 snapshot → decisions YAML → compiler → mutate → compare →
  four-file build 线路及 r6 失败证据。
- Root cause: r6 把离线 Template Truth candidate 当作 requirements，驱动 Agent 尝试完成整份
  Registry/32 槽任务；结构观察、视觉定位与 mutation 又使用不同身份，Agent 还要维护大量
  YAML/compiled/attempt 路径。结果是耗时约 27 分钟、两轮错误物化、0 个清理操作且无最终 Word。
- Approved contract: 对象判断阶段 Agent 只拿当前需要的一张页图或一个对象局部图；同一页中已判断清楚的多个
  OfficeCLI 对象可以一次 batch。snapshot-bound `object_ref` 统一用于结构、视觉和修改；已知
  `field_id` 直接提交，只有含义不确定时惰性查询 Registry；修改 Tool 原子执行 batch 并自动返回
  修改后同页图/新 `document_ref`。局部处理和生成内容收尾完成后，独立终局阶段按 cursor 检查
  最终 hash 的全部页面；内部版本和图片不对用户发布，最终 output 只允许 `final-template.docx`。
- Runtime surface: `template_open`、`template_next`、`template_search`、`template_focus`、
  `template_registry`、`template_edit`、`template_final_review`、`template_publish`。
  模板会话不开放 Bash、Write、Subagent，不存在 Agent-authored YAML、compiler、attempt path 或
  独立语义 checker。
- Mechanical feedback retained: object hash/fingerprint、Registry exact field、content-control
  alias/tag、包重开、OfficeCLI validation、batch 每项目标效果回读、非目标文字保护、修改页自动
  回传、source/Registry hash、最终 hash 全页覆盖与 no-overwrite 单 Word 原子发布；全页门只存在于
  所有内容处理完成后的终局阶段，不进入对象判断循环。
- Implemented evidence: 新 contract/Agent tests 已覆盖按需当前页图、同页最多 32 项原子 batch、
  惰性批量 Registry、可见 slot 占位、container clear/remove、修改页自动反馈、共享 object_ref、
  版本绑定、终局逐页覆盖发布门和单 Word output。漏页、旧 hash、返工后证据失效与渲染失败均有
  拒绝测试；旧 pipeline 模块、schema、compiler、permissions 和旧 contract tests 已删除。
- Real CLI r1 evidence: MiniMax 正常完成 12 个 slot、7 个整对象删除和 16 个内容清空，但旧的逐项
  Tool 调用与逐页 review 在 97 turns 触发 `max_turns`，25m07s 后未发布；Kimi fallback 随后 403。
  这证明 API 额度不是根因，根因是把逐页 review 混入逐对象循环。当前实现保留有界对象处理，
  但把全页 review 移到全部内容完成后的独立终局阶段，并由发布 Tool 对最终 hash 强制覆盖；
  等待 r2 真实质量/耗时验收。
- Official SDK basis: 保持 Claude Agent SDK 原生 Agent loop、custom in-process MCP Tools、
  permissions/hooks、Skill 与 structured output；不在其上建立第二套工作流 runtime。
- Next gate: 对 batch 改造跑全量 Ruff/mypy/pytest，真实 MiniMax 南农 r2 CLI，对最终 Word 做
  结构、页面与离线 Template Truth 对比。
- Stop condition: 未完成真实 MiniMax CLI 和最终 Word 质量对比前，不宣称重构完成或质量提高。

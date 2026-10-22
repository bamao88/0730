# Bug：docfit_apply 失败后的 no-op 与重试反馈循环不清晰

- Status: `OPEN / TRIAGED`
- Severity: `P1`
- Discovered: `2026-08-18`
- Subsystem: Template Extraction Skill、Harness feedback、`docfit_apply` Tool、Publication gate
- Affected operation: `docfit_apply(bind_field)`，尤其是学校模板中已有 content control / SDT 的填写接口

## 1. 摘要

当前失败表面表现为 Agent 反复调用 `docfit_apply`、最后 `needs_input` 或超时，但根因不是单纯
Agent 行为问题，而是四层合同没有对齐：

1. `docfit_apply` 对外允许 `bind_field` 作用在 `sdt`，但底层 `materialize_slot` 只支持
   `paragraph` 和 `run`，导致 Tool 表面能力和真实写入能力不一致。
2. Tool 把底层编辑失败原样返回，缺少 `docfit_apply` 语义下的可行动失败说明，Agent 难以判断是
   换 target、刷新证据、改字段，还是停止写入。
3. Harness completion feedback 允许 Agent 选择 `input/school-template.docx` 作为 no-op source，
   但没有提前区分“学校语义上已有可填写控件”和“已经满足 DocFit 发布协议的 final template”。
4. Skill 的主流程没有明确教 Agent：`docfit_apply` 失败后必须回到七问中的第 5 问，重新判断
   “是否仍需要写入”，并根据失败语义选择已有 SDT、改边界、刷新证据或停止。

因此 Agent 看到的是“需要 hash-bound candidate”但生成 candidate 失败，随后在 apply / check /
needs_input 之间循环。

## 2. 已观察证据

本问题来自模板提取设计 smoke，而不是最终内容准确性评测。

| Trace | 现象 | 说明 |
| --- | --- | --- |
| `temp/design-smoke-s00-20260818-006/work/.docfit/template-agent-execution.json` | 失败为 `template_agent_needs_input`，Agent 明确缺少“成功生成、hash-bound、来自授权 apply backend 的候选” | Tool 被发现并调用，Skill 已加载，但写入失败后的恢复路径不闭合 |
| `temp/design-smoke-s00-20260818-008/work/.docfit/template-agent-execution.json` | `template_agent_timeout`，trace 中出现多次 `mcp__docfit__docfit_apply` | Agent 反复尝试写入，说明反馈没有给出可收敛出口 |
| `temp/design-smoke-s00-20260818-009/work/.docfit/template-agent-execution.json` | `template_agent_timeout`，但 permission trace 显示 canonical Tool 和 Skill Reference 读取被正确授权 | 问题优先不在 Tool discovery、Skill loading 或基础权限 |

## 3. 分层问题拆解

### 3.1 Tool 合同与真实能力不一致

`docfit_apply` 的 carrier 表面允许：

```text
bind_field -> paragraph, run, sdt
```

但 `bind_field` 会映射到旧编辑动作：

```text
materialize_slot(target_ref, field_id)
```

底层物化当前只接受 `paragraph` 和 `run`。当目标本身是 `sdt` 时，底层会拒绝；当目标落在已有
content control 内时，也会拒绝。这样会产生两个后果：

- Agent 看到 `sdt` 是合法 carrier，于是合理地尝试对已有 content control 绑定字段；
- Tool 实际无法完成该写入，但失败不是以 `docfit_apply` 的业务语义返回。

这是一处明确的 Tool contract bug：公开能力面不能承诺底层不支持的 target。

### 3.2 已有 content control 的语义和发布协议没有桥接

学校模板里已有的 content control 可能确实表示“这里应填写某个字段”。但发布阶段只把带有 DocFit
显式 slot marker 的 content control 视为下游可消费 slot：

```text
tag starts with "slot."
```

这是正确的发布安全边界：不能把任意学校自带 SDT 静默解释成 DocFit Registry slot。

缺口在于中间桥接能力：

- 如果 Agent 选择已有 `sdt`，Tool 应能把它确定性地“采用/重标记”为 DocFit slot，或明确告诉
  Agent 当前不支持采用已有 SDT。
- 如果 Agent 选择包住已有 SDT 的外层 paragraph，Tool 应 fail closed，避免嵌套 SDT 或破坏学校
  原有结构，并建议先取 `target_affordance` 或选择精确 `sdt` target。

### 3.3 Harness no-op 出口不够明确

Harness completion feedback 当前允许：

```text
final_docx = input/school-template.docx
```

作为 no-op source selection。这个出口本身需要保留，因为源模板可能已经是合格 DocFit final
template。但现在缺少一个机械区分：

- **语义 no-op**：学校模板看起来已有可填写位置，但还不是 DocFit 发布协议；
- **产品 no-op**：源模板已经含有发布可识别的 DocFit slots、hash、render 和 Fill Contract
  所需证据，可以直接进入发布门。

如果 Harness 不把这个区别提前反馈给 Agent，Agent 会在“源文件看起来已经可填写”和“必须有
hash-bound candidate”之间摇摆。

### 3.4 Skill 缺少 apply 失败后的主流程恢复规则

当前 Skill 已经要求 Agent 使用七问判定壳，也写了泛化反馈处理。但对 `docfit_apply` 失败缺少
专门、短而明确的主流程规则：

- apply 失败后先回到第 5 问：是否仍需要写入？
- 如果源对象已经是 DocFit slot，优先考虑 no-op source，但必须满足发布协议；
- 如果是学校已有 SDT 但不是 DocFit slot，优先选择 SDT 采用/绑定路径；
- 如果是外层 paragraph/run 边界错误，重新取 `target_affordance`，不要重复同一 target；
- 如果 Tool 明确说当前后端不支持该写入，返回 `needs_input` 或报告当前阻断，不继续重试。

这部分必须写在主 `SKILL.md` 的流程和反馈处理里，Reference 可以展开例子，但不能把“何时看什么、
失败后如何回到哪一步”全部推给 Reference。

## 4. 根因判断

直接根因是 `docfit_apply(bind_field)` 的 Agent-visible target 合同、底层写入能力、发布 no-op
语义和 Skill 恢复指令不闭合。

本 bug 不应通过以下方式修复：

- 不新增应用拥有的语义状态机来替 Agent 决定“哪个字段该绑定哪里”；
- 不放宽发布阶段对 `slot.` marker 的要求；
- 不让 Harness 自动把学校任意 SDT 解释成 Registry slot；
- 不用更长 timeout 掩盖重复 apply。

正确方向是补齐确定性边界和 Agent 可用反馈：Tool 负责可写能力与失败语义，Harness 负责 no-op
发布可消费性，Skill 负责恢复判断路径。

## 5. 修正计划

### Step 1：先补回归测试

新增或扩展以下 contract/regression 测试，先让当前问题红灯可见：

1. `docfit_apply(bind_field)` 选择已有 `sdt` target 时，不允许落入泛化底层失败。
2. `docfit_apply(bind_field)` 选择包含已有 `sdt` 的外层 paragraph 时，必须 fail closed，并给出
   “选择已有 SDT / 取 target_affordance / 不重复同一 target”一类可行动建议。
3. Harness completion 选择 `input/school-template.docx` 时，必须区分 source 是否已经满足 DocFit
   publication slot 协议。
4. Skill contract 必须证明主 `SKILL.md` 明确包含 apply 失败后的恢复规则，而不是只在 Reference
   中展开。

### Step 2：修正 `docfit_apply` 写入语义

推荐默认修复目标：

- 支持对已有 `sdt` 执行 `bind_field` 的确定性采用：保留学校控件内容和布局承载，写入 DocFit
  `alias=field_id` 与唯一 `tag=slot.<field_id>...`，生成新的 work candidate。
- 对不安全边界 fail closed：当外层 paragraph 包含已有 SDT 且操作是 `bind_field` 时，不包裹父段落；
  返回稳定错误码和建议。
- 对底层编辑失败做 `docfit_apply` 语义包装：返回 operation、target type、target locator、
  candidate hash、失败 code、是否可重试、建议下一步，而不是让 Agent 只看到底层 `materialize_slot`
  术语。

如果短期不能支持 SDT 采用，也必须先把 `bind_field -> sdt` 从公开 carrier 移除，或返回明确的
`existing_content_control_adoption_unsupported`，避免 Agent 误以为这是可用路径。

### Step 3：收紧 Harness no-op feedback

在 completion consumability feedback 中加入机械检查：

- 当 `final_docx` 指向 `input/school-template.docx` 时，先验证源模板是否已经 publication-compatible。
- 若源模板只有学校自带 SDT、没有 DocFit `slot.` marker，返回可修复 blocker，例如
  `source_candidate_not_publishable`，建议使用 `docfit_apply(bind_field)` 采用已有 SDT 或报告当前
  写入能力阻断。
- 若源模板已经是 DocFit slot-compatible source，继续允许 no-op source selection。

这一步只检查发布协议可消费性，不判断学校语义是否正确。

### Step 4：更新 Skill 主流程

重写主 `SKILL.md` 中的少量关键句，而不是把内容堆到 Reference：

- 在“生成候选”阶段写明 apply 失败后先重答七问第 5 问。
- 在“反馈处理”里增加 `docfit_apply` 失败分支。
- 明确失败后应读取的 Reference：对象边界问题读对象边界 Reference；字段/已有控件绑定问题读
  Registry 与接口绑定 Reference。
- 明确禁止在同一 hash、同一 target、同一 operation、同一失败码下重复 apply。

Reference 只补一层展开例子，不承载主流程。

### Step 5：补 trace 可观测性

确保 smoke trace 可以看出：

- 每次 `docfit_apply` 的 operation、target type、target locator 和结果 code；
- Harness 对 source no-op 的 publishability 判断；
- Agent 是否加载了 Skill、读取了相关 Reference、调用了 canonical Tool；
- timeout 前是否存在重复同一 apply fingerprint。

这不是新增控制流，只是让下一轮设计测试能判断系统是否按计划运行。

## 6. 验证计划

### 6.1 Contract / Regression

运行目标：

```bash
uv run pytest -q tests/contract/test_docfit_apply_tool.py
uv run pytest -q tests/contract/test_publication_style_handoff.py
uv run pytest -q tests/contract/test_skill_contract.py
```

验收点：

- 选择已有 `sdt` target 的 `bind_field` 成功生成 hash-bound work candidate，或返回专门 unsupported
  失败，不再透出模糊底层错误。
- paragraph 包含已有 SDT 时不会嵌套物化；失败包含 `target_ref`、target type、locator 和下一步建议。
- source no-op 只有在源模板 publication-compatible 时才可通过 completion feedback。
- 主 Skill 明确包含 apply failure recovery、重新判断写入必要性、已有 content control 处理和禁止重复
  同失败 apply 的规则。

### 6.2 Harness Design Smoke

重新跑最小模板提取 smoke。当前不以最终 Word 准确性为第一验收，而检查系统设计行为：

```bash
uv run pytest -q tests/agent/school_extract_v2/test_agent_design_dry_run_trace.py
```

验收点：

- `skills_loaded` 包含 `docfit-school-extract`。
- Agent 上下文只包含 task startup brief、允许输入、Registry snapshot、evidence handles 和输出边界；
  不把整包 DOCX/OOXML 或 Gold 内容塞进 prompt。
- canonical Tool 调用为 `docfit_evidence`、`docfit_check`、`docfit_apply`。
- Tool failure 返回可行动 code 和 suggested actions。
- 同一 hash、同一 target、同一 operation、同一失败码不会被重复 apply 到超时。
- 若无法写入，最终是明确的 `needs_input`/blocking finding，而不是 timeout。

### 6.3 Publication / Fill Contract

运行目标：

```bash
uv run pytest -q tests/contract/test_publication_style_handoff.py
uv run pytest -q tests/integration/test_m1_tools.py::test_stateless_template_publication_binds_word_contract_and_review
```

验收点：

- 发布仍只识别 DocFit-owned `slot.` content control。
- 学校自带 SDT 不会被静默发布为 Registry slot。
- 采用已有 SDT 后生成的 candidate 可以被发布模块识别并写入 Fill Contract。

### 6.4 全量回归

修复完成后运行：

```bash
uv run pytest -q
uv run mypy src
uv run ruff check src tests
git diff --check -- docs/bugs/docfit-apply-noop-recovery-feedback-loop.md src tests .claude/skills/docfit-school-extract
```

若 `ruff check .` 仍因 `temp/` 或历史 eval artifact 报错，不把它作为本 bug 的验收门；以
`src tests` 范围为准，并在收口报告里说明。

## 7. 最终验收标准

本 bug 只有同时满足以下条件才算关闭：

1. Tool 表面能力与真实写入能力一致；`sdt` 目标不会再落入不可行动的底层失败。
2. 每个 `docfit_apply` 失败都能告诉 Agent：失败层、失败 target、是否可修复、下一步该取什么证据或
   是否停止。
3. Harness 对 source no-op 的反馈区分语义可填写和发布可消费。
4. Skill 主流程明确写出 apply 失败后的恢复路径。
5. 设计 smoke 不再因同一类不可行动 apply 失败进入重复 apply / timeout。
6. 发布协议仍保持严格：只有 DocFit-owned `slot.` 控件进入 Fill Contract。

## 8. 相关参考

- Claude Agent SDK overview: <https://code.claude.com/docs/en/agent-sdk/overview>
- Agent Skills in the SDK: <https://code.claude.com/docs/en/agent-sdk/skills>
- Skill authoring best practices: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>

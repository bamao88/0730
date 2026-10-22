# AI 参与复杂系统开发时的开发控制系统讨论稿

> 文档性质：human discussion / 对话整理，非当前操作规则
> 日期：2026-08-18
> 来源：关于 Agent 在 DocFit 多模块开发中走偏、跨层修改和故障归因不足的讨论

可以更大胆地说：现在遇到的不是“某个 Agent 不够聪明”，而是 **AI 参与复杂系统开发时缺少一套开发控制系统**。

它需要的不只是 prompt，而是一套让 Agent 不容易乱跑的“工程护栏”。

## 1. 先建立“故障分诊台”

任何失败都先进入分诊，而不是直接修代码。

```text
失败现象：
用户看到什么坏结果？

发生阶段：
输入校验 / 预处理 / 语义判断 / 映射组合 / DOCX 写入 / 输出验证 / 发布？

责任层：
Agent / Skill / Harness / Tool / Schema / App / Test / Eval / 文档？

当前阶段完成条件：
这一阶段到底只需要证明什么？

本次不改：
明确哪些层不碰。

最小修复：
只改哪一层、哪一个合同、哪一个测试。
```

这叫 **failure triage / fault isolation**，中文可以叫：**故障分诊与故障隔离**。

## 2. 给每个模块画“流水线地图”

每个模块都应该有自己的阶段地图。

例如 Final Content Fill：

```text
模板输入预处理
  检查 final-template.docx + fill-contract.yaml 是否匹配

学生内容预处理
  检查 Student Content Model 是否完整、顺序稳定、引用有效

组合计划
  决定 content_id / field_id 应进入哪个 slot / region

DOCX 物化
  真正写 Word，插入文字、图片、表格、公式、样式

最终验证
  检查输出 Word 是否完整、可打开、视觉和内容正确
```

失败时必须先定位是哪一段，而不是直接说“生成代码有问题”。

## 3. 把“动态判断”和“稳定规则”分开

产品开发中很多东西是动态的：

- 当前怀疑哪里有问题
- 某次 smoke 的结果
- 临时 blocker
- 下一步实验
- 某个方案是否值得保留

这些应该放在：

```text
docs/human/**
docs/bugs/**
docs/plans/**
docs/status/active/**
```

但稳定规则应该放在：

```text
docs/contracts/**
docs/modules/**
ARCHITECTURE.md
AGENTS.md
.claude/skills/**
tests/**
```

核心规则是：

> 动态内容不能直接变成 Agent 启动真相。它必须先被验证，再提升到合同、模块文档、Skill 或测试。

## 4. 每个阶段都要有“允许失败”和“不允许失败”

这是很关键的一点。

比如单元拆分阶段：

```text
允许进入 open_questions：
- Registry 字段还没绑定
- 视觉证据还不够
- 某个填写位置后续要确认

不允许通过：
- 单元边界为空
- 源对象没有覆盖完整
- 单元之间重叠
- 引用旧 hash
```

这能防止 Agent 把后续问题提前变成当前阶段阻断。

这个机制叫 **stage gate design**，中文可以叫：**阶段门禁设计**。

## 5. 用测试证明“它修的是对的层”

不要只问“测试过了吗”，要问：

```text
哪个测试证明输入预处理是对的？
哪个测试证明组合逻辑是对的？
哪个测试证明 DOCX 写入是对的？
哪个测试证明验证规则没有误报？
哪个测试证明完整 E2E 用户结果是对的？
```

大 E2E 只能说明整体坏了，不能说明坏在哪。
分层测试才能防止 Agent 乱改。

## 6. 给 Agent 一个强制汇报格式

以后可以要求它每次修复前必须先写：

```text
Layer attribution:
这个问题属于哪一层？

Checkpoint:
当前正在修哪个阶段？

Why not other layers:
为什么不是 Tool / Schema / App / Skill 的问题？

Minimum change:
最小改动是什么？

Blast radius:
会影响哪些模块？不会影响哪些模块？

Verification:
哪个测试证明这次改动正确？

Promotion:
如果这是动态发现，是否需要提升到 Contract / Module doc / Skill / Test？
```

如果它答不上来，就不要让它改代码。

## 7. 建议沉淀路径

可以把这套东西最终沉淀成一个通用文档，例如：

```text
docs/human/agent-development-failure-attribution-and-boundary-governance.md
```

确认后再逐步提升：

- 通用原则进 `AGENTS.md`
- 模块责任进 `docs/modules/*.md`
- 输入输出规则进 `docs/contracts/*.md`
- Agent 行为进 `.claude/skills/**`
- 可执行证明进 `tests/contract/**` 和 `tests/agent/**`

最核心的一句话是：

> Agent 不能从失败现象直接跳到代码修改。它必须先完成模块、阶段、责任层、当前 checkpoint 的归因，然后只修改能被对应测试证明的最小边界。


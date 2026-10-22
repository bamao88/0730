# DocFit Student Content Package 架构说明

> 状态：专题架构说明
> 目的：定义学生内容提取与 final-generation 之间的产品边界，而不是规定代码实现。

本文说明 Student Content 的上层产品形态：它不是单个 JSON 文件，而是一个面向下游生成的
学生内容包。这个包需要同时让系统理解“用户论文里有什么内容”，也要让 final-generation
知道“复杂对象如何无损搬运”。

## 1. 核心判断

学生内容提取不应该被设计成一个完全自由的 Agent 黑箱，也不应该被设计成由应用代码固定
判断所有论文语义。

合理架构是：

```text
学生源 Word
  -> 源事实层
  -> Skill 指导的语义 Agent
  -> 确定性校验与发布
  -> Student Content Package
  -> final-generation
```

其中：

- 源事实、顺序、locator、hash、对象载荷和发布完整性由确定性层负责；
- 标题、摘要、正文、图题、表题、公式、layout-only、不确定性和内容关系由 Agent 在
  Skill 指导下判断；
- final-generation 消费已经确认的学生内容包，不重新识别学生论文语义。

## 2. Student Content Package 是什么

Student Content Package 是学生内容提取模块给下游的 handoff。它回答三个问题：

1. 用户论文里有哪些内容；
2. 这些内容按什么顺序、层级和关系出现；
3. 表格、图片、公式等复杂对象如何从学生源 Word 搬运到目标模板。

最小可接受形态是：

```text
student-content-package/
  student-content.json
  source.docx
  manifest.json
```

其中：

- `student-content.json` 是语义清单和来源 manifest；
- `source.docx` 是绑定 hash 的学生源 Word 快照，保存复杂对象的完整 Word 本体；
- `manifest.json` 是 package 入口，说明各文件身份、schema、hash 和版本。

如果未来不希望携带完整源 Word，也可以改为对象 sidecar bundle：

```text
student-content-package/
  student-content.json
  manifest.json
  objects/
    table-001/
    image-001/
    equation-001/
```

这两种形式的产品语义相同：JSON 指向可搬运载荷，载荷负责无损复原复杂对象。

## 3. 为什么 JSON 不能单独承担全部职责

`student-content.json` 适合保存语义、顺序、关系、文本值和来源引用，但不适合直接塞入所有
表格、图片、公式的完整 OOXML、media、relationship 和依赖 part。

如果只交付 JSON，而 JSON 里只有 locator，没有源 Word 快照或对象载荷，下游就必须自行回到
外部原始文件中寻找复杂对象。这会让 handoff 依赖一个没有被 package 明确绑定的外部输入。

因此，完整 handoff 必须满足其中之一：

- package 携带可校验的源 Word 快照；
- package 携带可校验的对象载荷包；
- 两者同时存在，source snapshot 作为审计与回退来源。

## 4. 分层职责

| 层级 | 拥有的责任 | 不拥有的责任 |
| --- | --- | --- |
| 源事实层 | 从学生 Word 快照得到物理顺序、locator、对象身份、可见文本、物理类型和可搬运引用 | 判断标题、摘要、正文、图题、表题等论文语义 |
| 语义 Agent / Skill | 基于源事实和 Registry 判断字段语义、正文归属、layout-only、关系和不确定性 | 改写学生内容、私自重排源事实、绕过载荷合同搬运复杂对象 |
| 确定性校验与发布层 | 校验 hash、Registry 身份、顺序完整性、覆盖率、状态语义和 package 完整性 | 用低层代理规则替代 Agent 的领域判断 |
| final-generation | 信任已确认的语义、顺序、关系和 transport 引用，把内容放入目标模板 | 重新识别学生标题、图题、表题或正文语义 |

这个分层的核心是：**确定性层保护客观不变量，Skill 指导语义判断。**

## 5. 为什么需要 Skill，而不是继续把规则写在 prompt 里

学生内容提取涉及大量论文领域判断：

- 封面、目录、声明页、摘要、正文、参考文献如何区分；
- 什么是正文流，什么只是 layout-only；
- 图题、表题、英文题注和图片/表格之间如何建立关系；
- Word 物理拆分不合理时如何表达疑似逻辑合并；
- 遇到未知结构时如何标记不确定性，而不是猜测。

这些规则会随着真实样本、反例和复核经验持续演进。它们更适合沉淀在独立的 Agent Skill
或 Skill reference 中，而不是散落在应用代码的 prompt 字符串里。

但 Skill 化不等于把整个流程交给 Agent 自由执行。Agent 不应自己读取 Word、自己发明
source order、自己生成 locator 或自己发布最终 package。Skill 只负责指导语义判断；源事实、
载荷、hash、locator、校验、发布和失败状态仍由确定性层负责。

## 6. 如何处理原始 Word 拆分不合理

原始 Word 的物理结构经常不等于人类理解的论文逻辑结构。例如：

- 一个逻辑标题被拆成多个段落；
- 一个逻辑段落被拆成多个物理段落；
- 图片、图题、英文题注之间夹了空段或装饰段落；
- 表格标题、表格和表注没有连续出现。

架构上不应让 Agent 暗中合并、拆分或重排源对象，因为这样会破坏 source locator 和复杂对象
搬运的可追溯性。

更合理的表达方式是：

- 源事实层保留物理拆分、物理 locator 和稳定阅读顺序；
- 语义 Skill 指导 Agent 标记 logical grouping、疑似拆分、疑似连续段落、caption 关系和
  needs-review；
- 确定性发布层只在合同允许时把这些 grouping 变成下游可消费的逻辑边界；
- final-generation 使用逻辑边界组织内容，同时仍能回到物理 locator 搬运复杂对象。

这样可以同时保留两件事：

- 对 Word 对象搬运有用的物理真相；
- 对论文生成有用的逻辑内容结构。

## 7. 下游 handoff 原则

final-generation 可以依赖 Student Content Package 中已经确认的事实：

- 内容身份；
- 字段语义；
- 正文顺序；
- 正文/非正文分类；
- 内容关系；
- 文本值；
- 复杂对象 transport 引用；
- Registry 身份；
- 源文档 hash 或对象载荷 hash；
- 需要 review 或 input 的状态。

final-generation 不应重新判断：

- 哪段是标题；
- 哪段是摘要；
- 哪段是图题或表题；
- 某个表格属于正文还是 layout-only；
- 某张图片应该和哪个题注绑定；
- 学生源 Word 中相同文本附近哪个对象才是正确来源。

如果 Student Content Package 缺少必要语义或载荷，final-generation 应报告缺失输入或
需要复核，而不是回到原始 Word 重新做语义提取。

## 8. 这份文档不规定什么

本文不规定：

- 具体 JSON schema 字段名；
- 具体目录名是否必须叫 `objects/`；
- Agent batch、并发、retry、checkpoint；
- prompt 文本；
- 某个函数或模块如何实现；
- 是否必须立刻从 prompt 迁移到 Skill。

这些属于实现和迭代计划。本文只约束产品边界：Student Content 应是 package 级 handoff；
复杂对象必须有可校验载荷；语义判断应 Skill 化；确定性层保护源事实和发布合同。


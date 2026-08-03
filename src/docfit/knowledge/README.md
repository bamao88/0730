# Knowledge code boundary

本目录负责产品内置通用 Knowledge Package 的数据、加载与校验代码。

通用包位于 `package/<version>/` 并随 Python 构建产物发布。任务级学校材料、
推导规则、学生论文和中间文件不得写入本目录。

当前边界实现唯一内置包加载、不可变 manifest/document 模型、安全相对路径、
document hash 和 canonical digest 校验。包内容只接受非空 UTF-8 Markdown。

P1 已在不改 manifest/schema/package 版本的前提下，把每个已声明 document 投影为
开放、可组合的最小逻辑模块。模块复用 document ID、package version 和 document
SHA-256，并携带内容与 package digest；两个领域 Skill 可在一次委派中选择所需模块，
由主 Agent 通过 `Agent` prompt 传给通用只读 Subagent。

本目录不实现学校/版本选择、任务证据持久化、Provider 映射、学校资产写入或自动
晋升。结构校验只能证明包完整，不能代替对“内容是否真正通用”的人工评审。

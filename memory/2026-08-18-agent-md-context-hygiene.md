# 2026-08-18 Agent MD 上下文卫生

范围: 以后修改 `AGENTS.md`、`CLAUDE.md` 或 Cursor Rules。

记住: Agent MD 是每次会话默认加载的高杠杆上下文，必须短、普适、按需路由。不要写成百科、
开发历史、路线图、模块说明全集、命令大全或代码风格手册。优先写“该读哪里/不该读哪里/硬约束”，
细节用链接渐进披露。

原因: HumanLayer 的《Writing a good CLAUDE.md》强调 less is more 和 progressive disclosure；
指令越多，模型越容易整体忽略。用户也明确指出 DocFit 的 Agent MD 不能把所有内容列上去。

自检: 每次写完 Agent MD，都问四个问题：每一行是否适用于大多数任务；是否可以用链接替代正文；
是否混入产品需求、计划、历史证据或模块细节；链接目标是否当前有效。任一不通过就下沉或删除。

来源: https://www.humanlayer.dev/blog/writing-a-good-claude-md

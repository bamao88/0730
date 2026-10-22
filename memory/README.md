# DocFit 记忆

状态: future-Agent memory 索引
更新日期: 2026-08-18

`memory/**` 用来写未来 AI 需要知道的短经验，避免重复已知错误。Memory 不是项目路线图、
状态日志或任务 transcript。

条目应短、准、带日期：

```text
YYYY-MM-DD - <短标题>
范围: <模块/tool/doc 区域>
记住: <一条长期有效经验>
原因: <它避免的 bug、用户偏好或仓库约定问题>
```

保持 memory 条目很小。如果内容需要完整计划、决策记录、contract change 或 Eval，把它放到对应文档面；
只有确实有用时，再从一条短 memory 链接过去。

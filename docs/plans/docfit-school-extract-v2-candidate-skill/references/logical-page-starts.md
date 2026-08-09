# 逻辑页起点

## 判断边界

截图中的物理页、自然换行、普通空段和 `lastRenderedPageBreak` 都不能单独证明逻辑页边界。可靠信号包括目标标题的学校责任、`pageBreakBefore`、显式分页符以及 `nextPage/oddPage/evenPage` 分节。

由 Agent 判断摘要、具名章节或条件区是否必须另起一页；不要让 Tool 根据标题文字替你决定。

## 执行

确认需要时把目标段落放入：

```json
{"object_ref": {"object_id": "..."}, "mode": "new_page"}
```

Tool 会优先识别已有分页/分节边界；已有边界时返回 `already_satisfied`，不会再插入分页符或空段。没有边界时，选择稳定的 Word 表达并返回 `page_start_results`。

不要通过创建空白段来“顶到下一页”，也不要手工搬运 `sectPr`。

## 复核

- 目标确实从新逻辑页开始；
- 没有重复空白页；
- 前后页眉页脚、页码节和奇偶页设置没有变化；
- Word 保存、重开后边界仍稳定。

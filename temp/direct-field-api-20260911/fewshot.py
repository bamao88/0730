"""One prompt-only follow-up, with examples from a different form domain."""

import asyncio

import probe


async def main() -> None:
    # Establish whether the original prompt can handle the problematic items alone.
    await asyncio.gather(
        probe.run("single-zh-baseline", [6]),
        probe.run("single-advisor-baseline", [12]),
    )
    probe.SYSTEM += """
下面是其他表单的例子，只用于说明判断方式：
“艺术展报名表” → 整体 fixed_label，因为填好后表名仍保留。
“展览名称（四号宋体）” → “展览名称”是 fill_slot（展览真实名称）；“（四号宋体）”是 style_only。占位内容也可以是对待填内容的描述，不一定是×或下划线。
“策展人及职务：李某□主任” → “策展人及职务：”为 fixed_label；“李某”为 fill_slot（策展人姓名）；“□”为 spacer；“主任”为 fill_slot（策展人职务）。不同可填写含义分别输出，填写值不能吞掉标签。"""
    await asyncio.gather(*(
        probe.run(f"fewshot-{index}", [3, 4, 6, 7, 9, 10, 11, 12])
        for index in range(1, 4)
    ))


asyncio.run(main())

"""Semantic explanation only, with no schema or span bookkeeping."""

import asyncio

import probe


PROMPT = """这是学校论文封面的模板文字。请逐条简要说明：填写真实信息时，哪些原文需要被替换、分别填写什么；哪些文字应保留；哪些只是格式或排版说明。同一行如含多个含义，请分别指出。用自然语言回答即可。"""


async def main() -> None:
    await asyncio.gather(*(
        probe.run(f"natural-{index}", [3, 4, 6, 7, 9, 10, 11, 12],
                  system_prompt=PROMPT, json_output=False)
        for index in range(1, 4)
    ))


asyncio.run(main())

"""Direct API prompt kept identical; enable thinking only."""

import asyncio

import probe


async def main() -> None:
    await asyncio.gather(
        probe.run("single-zh-repeat-2", [6]),
        probe.run("single-zh-repeat-3", [6]),
    )
    await asyncio.gather(*(
        probe.run(f"adaptive-{index}", [3, 4, 6, 7, 9, 10, 11, 12], thinking="adaptive")
        for index in range(1, 4)
    ))


asyncio.run(main())

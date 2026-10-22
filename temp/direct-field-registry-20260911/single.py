"""Same complete input contract; only reduce the actual case to one source entry."""

import asyncio

import run


async def main() -> None:
    system = (run.BASE / "system-prompt.txt").read_text().removesuffix("\n")
    await asyncio.gather(*(
        run.probe.run(f"single-zh-{i}", [6], system_prompt=system)
        for i in range(1, 4)
    ))


asyncio.run(main())

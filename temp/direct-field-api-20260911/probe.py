"""Direct API diagnostic: source text only; no Agent SDK, tools, Skill or history."""

import asyncio
import json
import os
from pathlib import Path
import time

import httpx

from docfit.app.settings import iter_agent_backends


BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / "title-field-meaning-20260911/run-2/events.jsonl"
SYSTEM = """你负责把学校论文封面识别成可填写模板。按最终用途把每条原文拆成连续片段：
fixed_label：填写后仍保留的固定文字。
fill_slot：会被这篇论文的真实信息替换的内容；semantic 用简短中文说明要填写什么。
style_only：字体、字号等格式或填写方法说明。
spacer：用于对齐、留白的空格。
同一条原文可以包含多种用途或多个填写项，不能只判断整条文字。各片段 text 必须逐字复制原文，按顺序拼回原文，不遗漏、不改写。
只输出 JSON：{"items":[{"n":输入编号,"parts":[{"text":"原文片段","role":"上述用途","semantic":"填写含义，仅 fill_slot 提供"}]}]}。不输出解释。"""


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


events = [json.loads(line) for line in SOURCE.read_text().splitlines()]
packet = next(event["result"] for event in events if event["kind"] == "unit_evidence_packet")
texts = {entry["source_order"]["block"]: entry["text"] for entry in packet["evidence"]}
backend = next(item for item in iter_agent_backends() if item.name == "minimax")
BASE.chmod(0o700)
os.umask(0o077)


async def run(
    name: str, orders: list[int], *, thinking: str = "disabled",
    system_prompt: str | None = None, json_output: bool = True,
) -> None:
    folder = BASE / name
    folder.mkdir(exist_ok=False)
    user = "学校论文封面原文。模板中 □ 表示占一个字宽的空格。\n" + json.dumps(
        [{"n": index, "text": texts[index]} for index in orders], ensure_ascii=False
    )
    system = system_prompt if system_prompt is not None else SYSTEM
    request = {
        "model": backend.model,
        "max_tokens": 4000,
        "temperature": 1,
        "thinking": {"type": thinking},
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    save(folder / "request.json", request)
    started = time.perf_counter()
    result = {"run": name, "input_characters": len(system) + len(user)}
    chunks = []
    first_text = None
    try:
        usage = {}
        stop_reason = None
        returned_model = None
        stopped = False
        async with httpx.AsyncClient(timeout=90) as client:
            async with asyncio.timeout(120):
                async with client.stream(
                    "POST", backend.base_url.rstrip("/") + "/v1/messages",
                    headers={"x-api-key": backend.api_key, "anthropic-version": "2023-06-01"},
                    json={**request, "stream": True},
                ) as response:
                    result["http_status"] = response.status_code
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = json.loads(line[6:])
                        kind = data.get("type")
                        if kind == "message_start":
                            usage.update(data["message"].get("usage", {}))
                            returned_model = data["message"].get("model")
                        elif kind == "message_delta":
                            usage.update(data.get("usage", {}))
                            stop_reason = data.get("delta", {}).get("stop_reason")
                        elif kind == "message_stop":
                            stopped = True
                        elif kind == "error":
                            raise RuntimeError("API stream error")
                        chunk = ""
                        if kind == "content_block_start":
                            block = data.get("content_block", {})
                            if block.get("type") == "text":
                                chunk = block.get("text", "")
                        elif kind == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                chunk = delta.get("text", "")
                        if chunk:
                            if first_text is None:
                                first_text = time.perf_counter() - started
                            chunks.append(chunk)
        if not stopped:
            raise RuntimeError("API stream ended without message_stop")
        result.update(
            status="completed",
            seconds=round(time.perf_counter() - started, 3),
            first_text_seconds=round(first_text, 3) if first_text is not None else None,
            stop_reason=stop_reason,
            usage=usage,
            returned_model=returned_model,
        )
        answer = "".join(chunks)
        (folder / "answer.txt").write_text(answer)
        if not json_output:
            save(folder / "metrics.json", result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            return
        try:
            # Accept JSON fenced as presentation only; do not alter semantic output.
            raw = answer.strip()
            if raw.startswith("```json\n") and raw.endswith("```"):
                raw = raw[8:-3].strip()
            parsed = json.loads(raw)
            save(folder / "output.json", parsed)
            rows = parsed.get("items", [])
            result["exact_text_partition"] = {
                str(index): any(
                    row.get("n") == index
                    and "".join(part.get("text", "") for part in row.get("parts", [])) == texts[index]
                    for row in rows
                ) for index in orders
            }
        except (ValueError, AttributeError, TypeError) as error:
            result["json_error"] = type(error).__name__
    except Exception as error:
        # Exception bodies may contain transport headers: retain only safe classification.
        result.update(status="error", error_type=type(error).__name__,
                      http_status=getattr(error, "status_code", None),
                      seconds=round(time.perf_counter() - started, 3))
    save(folder / "metrics.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


async def main() -> None:
    await run("single-title", [7])
    await asyncio.gather(*(run(f"mixed-{index}", [3, 4, 6, 7, 9, 10, 11, 12]) for index in range(1, 4)))


if __name__ == "__main__":
    asyncio.run(main())

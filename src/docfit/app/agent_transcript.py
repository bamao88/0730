"""Per-query Agent transcript evidence for template extraction.

Each SDK query gets one append-only JSONL file under the task root.  The file
keeps what the bounded ``sdk_events`` trace drops: full thinking text, tool
inputs, result usage, and the thinking that was still streaming when a query
was interrupted.  It is internal evidence only; it never feeds back into an
Agent prompt and is not part of the delivered template.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

JsonObject = dict[str, Any]

TRANSCRIPT_DIRECTORY = "work/.docfit/agent-transcripts"
_TOOL_RESULT_PREVIEW_CHARS = 2000
_STREAMED_TEXT_DELTAS = {"thinking_delta": "thinking", "text_delta": "text"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value) or "query"


def request_parameters(options: ClaudeAgentOptions) -> JsonObject:
    """The model-facing knobs DocFit asked the SDK to send for this query."""

    return {
        "model": options.model,
        "thinking": options.thinking,
        "effort": options.effort,
        "max_thinking_tokens": options.max_thinking_tokens,
        "max_turns": options.max_turns,
    }


def _content_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


class AgentQueryTranscript:
    """Append-only transcript for exactly one SDK query."""

    def __init__(
        self,
        task_root: Path,
        *,
        stage: str,
        scope: str,
        query_index: int,
        prompt: str,
        options: ClaudeAgentOptions,
        metadata: JsonObject | None = None,
    ) -> None:
        directory = task_root / TRANSCRIPT_DIRECTORY / _safe_name(stage) / _safe_name(scope)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{query_index:04d}.jsonl"
        self._started = time.perf_counter()
        self._streaming: dict[int, JsonObject] = {}
        self._thinking_chars = 0
        self._thinking_ms = 0
        self._thinking_token_events = 0
        self._last_thinking_tokens: object = None
        self._usage: JsonObject | None = None
        self._closed = False
        self._write(
            {
                "kind": "query_start",
                "stage": stage,
                "scope": scope,
                "query_index": query_index,
                "started_unix_ms": _now_ms(),
                "prompt_sha256": _sha256(prompt),
                "prompt_chars": len(prompt),
                "request_parameters": request_parameters(options),
                **(metadata or {}),
            }
        )

    def _elapsed_ms(self) -> int:
        return round((time.perf_counter() - self._started) * 1000)

    def _write(self, record: JsonObject) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def record(self, message: object) -> None:
        if self._closed:
            return
        if isinstance(message, StreamEvent):
            self._record_stream(message.event)
            return
        elapsed_ms = self._elapsed_ms()
        if isinstance(message, AssistantMessage):
            blocks: list[JsonObject] = []
            for block in message.content:
                if isinstance(block, ThinkingBlock):
                    blocks.append({"type": "thinking", "text": block.thinking})
                elif isinstance(block, TextBlock):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                else:
                    blocks.append({"type": block.__class__.__name__})
            self._write(
                {
                    "kind": "assistant",
                    "elapsed_ms": elapsed_ms,
                    "model": message.model,
                    "error": getattr(message, "error", None),
                    "blocks": blocks,
                }
            )
        elif isinstance(message, UserMessage):
            if not isinstance(message.content, list):
                return
            for block in message.content:
                if not isinstance(block, ToolResultBlock):
                    continue
                text = _content_text(block.content)
                self._write(
                    {
                        "kind": "tool_result",
                        "elapsed_ms": elapsed_ms,
                        "tool_use_id": block.tool_use_id,
                        "is_error": block.is_error,
                        "content_sha256": _sha256(text),
                        "content_chars": len(text),
                        "preview": text[:_TOOL_RESULT_PREVIEW_CHARS],
                    }
                )
        elif isinstance(message, SystemMessage):
            if message.subtype == "thinking_tokens":
                # Emitted once per thinking chunk; keep the latest value only.
                self._thinking_token_events += 1
                self._last_thinking_tokens = message.data
                return
            self._write(
                {
                    "kind": "system",
                    "elapsed_ms": elapsed_ms,
                    "subtype": message.subtype,
                    "data": message.data,
                }
            )
        elif isinstance(message, ResultMessage):
            self._usage = message.usage if isinstance(message.usage, dict) else None
            output = message.structured_output
            self._write(
                {
                    "kind": "result",
                    "elapsed_ms": elapsed_ms,
                    "subtype": message.subtype,
                    "is_error": message.is_error,
                    "stop_reason": message.stop_reason,
                    "num_turns": message.num_turns,
                    "duration_ms": message.duration_ms,
                    "duration_api_ms": message.duration_api_ms,
                    "total_cost_usd": message.total_cost_usd,
                    "usage": message.usage,
                    "model_usage": message.model_usage,
                    "structured_output_sha256": (
                        _sha256(json.dumps(output, ensure_ascii=False, sort_keys=True))
                        if isinstance(output, dict)
                        else None
                    ),
                }
            )
        else:
            self._write(
                {"kind": "other", "elapsed_ms": elapsed_ms, "type": message.__class__.__name__}
            )

    def _record_stream(self, event: JsonObject) -> None:
        event_type = event.get("type")
        index = event.get("index")
        if not isinstance(index, int):
            return
        if event_type == "content_block_start":
            block = event.get("content_block")
            block_type = block.get("type") if isinstance(block, dict) else None
            self._streaming[index] = {
                "type": block_type,
                "started_ms": self._elapsed_ms(),
                "text": [],
            }
        elif event_type == "content_block_delta":
            state = self._streaming.get(index)
            delta = event.get("delta")
            if state is None or not isinstance(delta, dict):
                return
            payload_key = _STREAMED_TEXT_DELTAS.get(str(delta.get("type")))
            payload = delta.get(payload_key) if payload_key else None
            if isinstance(payload, str):
                state["text"].append(payload)
        elif event_type == "content_block_stop":
            state = self._streaming.pop(index, None)
            if state is None:
                return
            # The completed block's content arrives in the AssistantMessage;
            # only its timing is recorded here.
            stopped_ms = self._elapsed_ms()
            chars = sum(len(part) for part in state["text"])
            if state["type"] == "thinking":
                self._thinking_chars += chars
                self._thinking_ms += stopped_ms - state["started_ms"]
            self._write(
                {
                    "kind": "block_timing",
                    "block_type": state["type"],
                    "started_ms": state["started_ms"],
                    "stopped_ms": stopped_ms,
                    "streamed_chars": chars,
                }
            )

    def stats(self) -> JsonObject:
        """Compact numbers for the query's timing event."""

        stats: JsonObject = {
            "thinking_streamed_chars": self._thinking_chars,
            "thinking_streamed_ms": self._thinking_ms,
        }
        if self._last_thinking_tokens is not None:
            stats["thinking_tokens_reported"] = self._last_thinking_tokens
        return stats

    def close(self, *, status: str) -> None:
        if self._closed:
            return
        partial = [
            {
                "block_type": state["type"],
                "started_ms": state["started_ms"],
                "text": "".join(state["text"]),
            }
            for state in self._streaming.values()
            if state["text"]
        ]
        self._write(
            {
                "kind": "query_end",
                "status": status,
                "elapsed_ms": self._elapsed_ms(),
                "ended_unix_ms": _now_ms(),
                "thinking_token_events": self._thinking_token_events,
                "last_thinking_tokens": self._last_thinking_tokens,
                "usage": self._usage,
                # Blocks still streaming when the query ended, e.g. on timeout.
                "partial_blocks": partial,
                **self.stats(),
            }
        )
        self._closed = True

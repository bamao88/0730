from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from docfit.app.agent_transcript import TRANSCRIPT_DIRECTORY, AgentQueryTranscript


def _stream(event: dict[str, object]) -> StreamEvent:
    return StreamEvent(uuid="u", session_id="s", event=event)


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _transcript(tmp_path: Path) -> AgentQueryTranscript:
    return AgentQueryTranscript(
        tmp_path,
        stage="post-unit",
        scope="semantic-batch-0001/x",
        query_index=3,
        prompt="judge these entries",
        options=ClaudeAgentOptions(
            model="MiniMax-M3", thinking={"type": "adaptive"}, effort="low", max_turns=20
        ),
        metadata={"batch_id": "semantic-batch-0001"},
    )


def test_completed_query_keeps_thinking_tool_io_usage_and_request_parameters(
    tmp_path: Path,
) -> None:
    transcript = _transcript(tmp_path)
    transcript.record(
        _stream({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}})
    )
    transcript.record(
        _stream(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "entry e3 is "},
            }
        )
    )
    transcript.record(
        _stream(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "a blank line"},
            }
        )
    )
    transcript.record(SystemMessage(subtype="thinking_tokens", data={"tokens": 7}))
    transcript.record(_stream({"type": "content_block_stop", "index": 0}))
    transcript.record(
        AssistantMessage(
            content=[
                ThinkingBlock(thinking="entry e3 is a blank line", signature="sig"),
                ToolUseBlock(id="t1", name="StructuredOutput", input={"status": "complete"}),
            ],
            model="MiniMax-M3",
        )
    )
    transcript.record(
        UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="x" * 5000)])
    )
    transcript.record(
        ResultMessage(
            subtype="success",
            duration_ms=10,
            duration_api_ms=8,
            is_error=False,
            num_turns=2,
            session_id="s",
            usage={"input_tokens": 100, "output_tokens": 20},
            structured_output={"status": "complete"},
        )
    )
    transcript.close(status="response_complete")

    path = tmp_path / TRANSCRIPT_DIRECTORY / "post-unit" / "semantic-batch-0001_x" / "0003.jsonl"
    assert transcript.path == path
    records = _records(path)
    kinds = [record["kind"] for record in records]
    assert kinds == [
        "query_start", "block_timing", "assistant", "tool_result", "result", "query_end"
    ]

    start = records[0]
    assert start["request_parameters"] == {
        "model": "MiniMax-M3",
        "thinking": {"type": "adaptive"},
        "effort": "low",
        "max_thinking_tokens": None,
        "max_turns": 20,
    }
    assert start["batch_id"] == "semantic-batch-0001"
    assert "judge these entries" not in path.read_text(encoding="utf-8")

    assert records[2]["blocks"][0] == {"type": "thinking", "text": "entry e3 is a blank line"}
    assert records[2]["blocks"][1]["input"] == {"status": "complete"}
    assert records[3]["content_chars"] == 5000
    assert len(records[3]["preview"]) == 2000
    assert records[4]["usage"] == {"input_tokens": 100, "output_tokens": 20}

    end = records[-1]
    assert end["partial_blocks"] == []
    assert end["usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert end["thinking_token_events"] == 1
    assert transcript.stats()["thinking_streamed_chars"] == len("entry e3 is a blank line")
    assert transcript.stats()["thinking_tokens_reported"] == {"tokens": 7}


def test_interrupted_query_keeps_thinking_that_was_still_streaming(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path)
    transcript.record(
        _stream({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}})
    )
    transcript.record(
        _stream(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "still weighing role vs field"},
            }
        )
    )
    transcript.close(status="interrupted")
    transcript.record(_stream({"type": "content_block_stop", "index": 0}))

    records = _records(transcript.path)
    assert [record["kind"] for record in records] == ["query_start", "query_end"]
    assert records[-1]["status"] == "interrupted"
    assert records[-1]["partial_blocks"][0]["block_type"] == "thinking"
    assert records[-1]["partial_blocks"][0]["text"] == "still weighing role vs field"

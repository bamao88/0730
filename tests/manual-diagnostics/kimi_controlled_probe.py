"""Privacy-safe controlled-variable probe for Kimi through Claude Agent SDK.

The probe never reads document inputs and never writes credentials. It exercises a
small structured-output request and a 12-step stateful MCP tool chain, then records
only status, turn counts, tool counts, and timing metadata.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.settings import AgentBackend, iter_agent_backends

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = PROJECT_ROOT / "test" / "work" / "kimi-controlled"
OUTPUT_ROOT = PROJECT_ROOT / "test" / "evidence" / "kimi-controlled"
TARGET_STEPS = 12

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "const": "complete"},
        "steps_completed": {"type": "integer", "const": TARGET_STEPS},
    },
    "required": ["status", "steps_completed"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class Variant:
    name: str
    model: str
    workload: str
    effort: str | None
    tool_search: bool


@dataclass(frozen=True, slots=True)
class ProbeResult:
    variant: str
    repeat: int
    model: str
    workload: str
    effort: str | None
    tool_search: bool
    outcome: str
    is_error: bool | None
    api_error_status: int | None
    terminal_reason: str | None
    stop_reason: str | None
    subtype: str | None
    num_turns: int | None
    tool_use_count: int
    accepted_step_count: int
    structured_output_ok: bool
    duration_ms: int
    sdk_duration_ms: int | None
    sdk_api_duration_ms: int | None
    exception_type: str | None


VARIANTS = (
    Variant(
        name="current-short-high-search-off",
        model="kimi-for-coding",
        workload="short",
        effort="high",
        tool_search=False,
    ),
    Variant(
        name="current-long-high-search-off",
        model="kimi-for-coding",
        workload="long",
        effort="high",
        tool_search=False,
    ),
    Variant(
        name="k3-long-high-search-off",
        model="k3-256k",
        workload="long",
        effort="high",
        tool_search=False,
    ),
    Variant(
        name="current-long-default-effort-search-off",
        model="kimi-for-coding",
        workload="long",
        effort=None,
        tool_search=False,
    ),
    Variant(
        name="current-long-thinking-off-search-off",
        model="kimi-for-coding",
        workload="long",
        effort="none",
        tool_search=False,
    ),
    Variant(
        name="current-long-high-search-on",
        model="kimi-for-coding",
        workload="long",
        effort="high",
        tool_search=True,
    ),
)


def _kimi_backend() -> AgentBackend:
    for backend in iter_agent_backends():
        if backend.name == "kimi":
            return backend
    raise RuntimeError("kimi_backend_not_configured")


def _prompt(workload: str) -> str:
    if workload == "short":
        return (
            "This is a controlled transport probe. Do not call any tool. "
            "Return the requested structured output with status complete and "
            f"steps_completed {TARGET_STEPS}."
        )
    return (
        "This is a controlled tool-history probe. Call mcp__cv__advance exactly "
        f"{TARGET_STEPS} times, strictly sequentially. Start with step=1 and "
        "previous_token=START. After every accepted response, use its next_step and "
        "token in the following call. Do not guess or batch dependent calls. After "
        f"step {TARGET_STEPS} is accepted, return the requested structured output "
        f"with status complete and steps_completed {TARGET_STEPS}."
    )


async def _run_variant(
    backend: AgentBackend,
    variant: Variant,
    repeat: int,
) -> ProbeResult:
    accepted_steps: list[int] = []
    expected_step = 1
    expected_token = "START"

    @tool(
        "advance",
        "Advance one strictly ordered step in a controlled diagnostic state machine.",
        {
            "type": "object",
            "properties": {
                "step": {"type": "integer"},
                "previous_token": {"type": "string"},
            },
            "required": ["step", "previous_token"],
            "additionalProperties": False,
        },
    )
    async def advance(arguments: dict[str, Any]) -> dict[str, Any]:
        nonlocal expected_step, expected_token
        step = arguments.get("step")
        previous_token = arguments.get("previous_token")
        if step != expected_step or previous_token != expected_token:
            payload = {
                "accepted": False,
                "expected_step": expected_step,
                "expected_token": expected_token,
            }
        else:
            accepted_steps.append(expected_step)
            next_token = f"TOKEN-{expected_step:02d}"
            expected_step += 1
            expected_token = next_token
            payload = {
                "accepted": True,
                "completed_step": step,
                "next_step": expected_step,
                "token": next_token,
                "done": step == TARGET_STEPS,
            }
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, sort_keys=True),
                }
            ]
        }

    environment = backend.sdk_environment()
    environment.update(
        {
            "ANTHROPIC_MODEL": variant.model,
            "ANTHROPIC_DEFAULT_FABLE_MODEL": variant.model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": variant.model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": variant.model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": variant.model,
            "CLAUDE_CODE_SUBAGENT_MODEL": variant.model,
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "262144",
            "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "262144",
            "ENABLE_TOOL_SEARCH": "true" if variant.tool_search else "false",
            "API_TIMEOUT_MS": "180000",
            "CLAUDE_CODE_MAX_RETRIES": "0",
        }
    )
    if variant.effort is None:
        environment.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
    else:
        environment["CLAUDE_CODE_EFFORT_LEVEL"] = variant.effort

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    tool_use_count = 0
    result: ResultMessage | None = None
    started = time.perf_counter()
    exception_type: str | None = None
    with tempfile.TemporaryDirectory(prefix="sdk-", dir=WORK_ROOT) as config_dir:
        environment["CLAUDE_CONFIG_DIR"] = config_dir
        server = create_sdk_mcp_server(
            name="cv",
            version="1.0.0",
            tools=[advance],
        )
        options = ClaudeAgentOptions(
            tools=["mcp__cv__advance"],
            allowed_tools=["mcp__cv__advance"],
            mcp_servers={"cv": server},
            strict_mcp_config=True,
            permission_mode="default",
            setting_sources=[],
            cwd=PROJECT_ROOT,
            env=environment,
            model=variant.model,
            max_turns=20,
            output_format={"type": "json_schema", "schema": OUTPUT_SCHEMA},
            system_prompt=(
                "Follow the diagnostic prompt exactly. Do not inspect files, run shell "
                "commands, browse, or expose configuration."
            ),
        )
        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(_prompt(variant.workload))
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        tool_use_count += sum(
                            isinstance(block, ToolUseBlock) for block in message.content
                        )
                    if isinstance(message, ResultMessage):
                        result = message
        except Exception as error:  # Safe output records only the exception class.
            exception_type = type(error).__name__

    duration_ms = round((time.perf_counter() - started) * 1000)
    structured_output_ok = bool(
        result is not None
        and result.structured_output == {
            "status": "complete",
            "steps_completed": TARGET_STEPS,
        }
    )
    if exception_type is not None:
        outcome = "exception"
    elif result is None:
        outcome = "missing_result"
    elif result.is_error:
        outcome = "sdk_error"
    elif len(accepted_steps) != (0 if variant.workload == "short" else TARGET_STEPS):
        outcome = "tool_chain_incomplete"
    elif not structured_output_ok:
        outcome = "structured_output_invalid"
    else:
        outcome = "pass"

    return ProbeResult(
        variant=variant.name,
        repeat=repeat,
        model=variant.model,
        workload=variant.workload,
        effort=variant.effort,
        tool_search=variant.tool_search,
        outcome=outcome,
        is_error=result.is_error if result is not None else None,
        api_error_status=result.api_error_status if result is not None else None,
        terminal_reason=result.terminal_reason if result is not None else None,
        stop_reason=result.stop_reason if result is not None else None,
        subtype=result.subtype if result is not None else None,
        num_turns=result.num_turns if result is not None else None,
        tool_use_count=tool_use_count,
        accepted_step_count=len(accepted_steps),
        structured_output_ok=structured_output_ok,
        duration_ms=duration_ms,
        sdk_duration_ms=result.duration_ms if result is not None else None,
        sdk_api_duration_ms=result.duration_api_ms if result is not None else None,
        exception_type=exception_type,
    )


def _write_results(results: list[ProbeResult], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "privacy": "metadata_only_no_prompt_or_provider_error_body",
        "target_steps": TARGET_STEPS,
        "results": [asdict(result) for result in results],
    }
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        action="append",
        choices=[variant.name for variant in VARIANTS],
        help="Run only the named variant; repeat the option to select several.",
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_ROOT / "results.json",
    )
    arguments = parser.parse_args()
    selected = [
        variant
        for variant in VARIANTS
        if not arguments.variant or variant.name in arguments.variant
    ]
    backend = _kimi_backend()
    results: list[ProbeResult] = []
    for repeat in range(1, arguments.repeat + 1):
        for variant in selected:
            result = await _run_variant(backend, variant, repeat)
            results.append(result)
            print(json.dumps(asdict(result), sort_keys=True), flush=True)
    _write_results(results, arguments.output)
    return 0 if all(result.outcome == "pass" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

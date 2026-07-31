"""Live Claude Agent SDK smoke cases for the M0 product gate."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.agent import (
    FORBIDDEN_TOOLS,
    build_agent_options,
    project_root,
    terminal_ask_user,
)
from docfit.app.settings import AgentBackend, iter_agent_backends, redact_secrets
from docfit.tools import FULL_TOOL_NAMES
from docfit.tools.image_smoke import SMOKE_BORDER_COLOR, SMOKE_MARKER

SmokeCase = Literal["image", "ask-user", "denied-tools"]
SMOKE_CASES: tuple[SmokeCase, ...] = ("image", "ask-user", "denied-tools")


@dataclass(frozen=True)
class SmokeReport:
    case: SmokeCase
    status: Literal["PASS", "FAIL"]
    backend: str
    session_id: str | None
    tool_uses: tuple[str, ...]
    detail: str


def receipt_directory(root: Path | None = None) -> Path:
    return (root or project_root()) / ".docfit" / "smoke"


def _write_receipt(report: SmokeReport, *, root: Path | None = None) -> None:
    directory = receipt_directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        **asdict(report),
        "sdk_version": version("claude-agent-sdk"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    target = directory / f"{report.case}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


async def _collect(
    prompt: str,
    backend: AgentBackend,
    *,
    ask_user: Any = terminal_ask_user,
) -> tuple[
    ResultMessage | None, tuple[str, ...], tuple[str, ...]
]:
    result: ResultMessage | None = None
    tool_uses: list[str] = []
    session_ids: set[str] = set()
    options = build_agent_options(
        ask_user,
        agent_env=backend.sdk_environment(),
        model=backend.model,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            message_session = getattr(message, "session_id", None)
            if isinstance(message_session, str) and message_session:
                session_ids.add(message_session)
            if isinstance(message, AssistantMessage):
                tool_uses.extend(
                    block.name for block in message.content if isinstance(block, ToolUseBlock)
                )
            if isinstance(message, ResultMessage):
                result = message
    return result, tuple(tool_uses), tuple(sorted(session_ids))


async def run_image_smoke(backend: AgentBackend) -> SmokeReport:
    prompt = (
        "This is the M0 image gate. First invoke the Skill tool to load the "
        "convert-thesis Skill. Follow that Skill's image-smoke instruction. Read the "
        "marker and border color from the returned image. In your final response state "
        "only what you actually saw; do not infer text from this prompt."
    )
    result, tool_uses, session_ids = await _collect(prompt, backend)
    text = result.result if result and result.result else ""
    required_tools = {"Skill", "mcp__docfit__docx_visual_review"}
    passed = (
        result is not None
        and not result.is_error
        and SMOKE_MARKER in text
        and SMOKE_BORDER_COLOR.casefold() in text.casefold()
        and required_tools.issubset(tool_uses)
        and len(session_ids) == 1
    )
    return SmokeReport(
        case="image",
        status="PASS" if passed else "FAIL",
        backend=backend.name,
        session_id=result.session_id if result else None,
        tool_uses=tool_uses,
        detail=(
            "Agent loaded the project Skill, called the image Tool, and read the hidden marker."
            if passed
            else f"Expected image evidence was incomplete. Agent result: {text!r}"
        ),
    )


async def run_ask_user_smoke(backend: AgentBackend) -> SmokeReport:
    captured_answers: list[str] = []

    async def capture_answer(prompt: str) -> str:
        answer = await terminal_ask_user(prompt)
        captured_answers.append(answer)
        return answer

    prompt = (
        "Call AskUserQuestion once to ask for a short M0 continuation token. After the "
        "CLI returns the answer, continue this same session and include that exact token "
        "in your final response."
    )
    result, tool_uses, session_ids = await _collect(
        prompt,
        backend,
        ask_user=capture_answer,
    )
    text = result.result if result and result.result else ""
    passed = (
        result is not None
        and not result.is_error
        and len(captured_answers) == 1
        and captured_answers[0] in text
        and "AskUserQuestion" in tool_uses
        and len(session_ids) == 1
    )
    return SmokeReport(
        case="ask-user",
        status="PASS" if passed else "FAIL",
        backend=backend.name,
        session_id=result.session_id if result else None,
        tool_uses=tool_uses,
        detail=(
            "AskUserQuestion returned CLI input and the Agent continued the same session."
            if passed
            else "The AskUserQuestion CLI round trip did not produce complete evidence."
        ),
    )


async def run_denied_tools_smoke(backend: AgentBackend) -> SmokeReport:
    unregistered = "mcp__docfit__not_registered"
    prompt = (
        "Attempt to invoke each of these tools: Bash, Write, Edit, Web, WebSearch, "
        f"WebFetch, and {unregistered}. Then report which attempts were unavailable or "
        "denied. Do not substitute a registered DocFit Tool."
    )
    result, tool_uses, session_ids = await _collect(prompt, backend)
    denied_names = set(FORBIDDEN_TOOLS) | {unregistered}
    attempted_execution = denied_names.intersection(tool_uses)
    passed = (
        result is not None
        and not result.is_error
        and not attempted_execution
        and len(session_ids) == 1
        and not set(tool_uses).intersection(FULL_TOOL_NAMES)
    )
    return SmokeReport(
        case="denied-tools",
        status="PASS" if passed else "FAIL",
        backend=backend.name,
        session_id=result.session_id if result else None,
        tool_uses=tool_uses,
        detail=(
            "No forbidden or unregistered Tool execution reached the SDK."
            if passed
            else f"Unexpected Tool execution observed: {sorted(attempted_execution)}"
        ),
    )


async def run_smoke(case_name: SmokeCase, backend: AgentBackend) -> SmokeReport:
    if case_name == "image":
        return await run_image_smoke(backend)
    if case_name == "ask-user":
        return await run_ask_user_smoke(backend)
    return await run_denied_tools_smoke(backend)


async def run_smoke_with_fallback(
    case_name: SmokeCase,
    backends: tuple[AgentBackend, ...],
) -> SmokeReport:
    failures: list[str] = []
    last_report: SmokeReport | None = None
    for backend in backends:
        try:
            report = await run_smoke(case_name, backend)
        except Exception as error:
            detail = redact_secrets(f"{type(error).__name__}: {error}", backends)
            failures.append(f"{backend.name} raised {detail}")
            continue
        if report.status == "PASS":
            if failures:
                report = replace(
                    report,
                    detail=f"{report.detail} Earlier candidates failed: {'; '.join(failures)}",
                )
            return report
        last_report = report
        failures.append(f"{backend.name} returned FAIL: {report.detail}")

    detail = redact_secrets("; ".join(failures), backends)
    if last_report is not None:
        return replace(last_report, detail=f"All configured candidates failed: {detail}")
    return SmokeReport(
        case=case_name,
        status="FAIL",
        backend=backends[-1].name,
        session_id=None,
        tool_uses=(),
        detail=f"All configured candidates failed: {detail}",
    )


def smoke_main(case_name: str) -> int:
    if case_name not in SMOKE_CASES:
        raise ValueError(f"unknown smoke case: {case_name}")
    try:
        backends = tuple(iter_agent_backends())
    except Exception as error:
        print(f"NOT_READY: invalid DocFit Agent environment: {type(error).__name__}: {error}")
        return 2
    if not backends:
        print(
            "NOT_READY: no Kimi or MiniMax credential is configured in the "
            "DocFit Agent environment."
        )
        return 2
    try:
        report = asyncio.run(run_smoke_with_fallback(case_name, backends))
    except Exception as error:
        detail = redact_secrets(f"{type(error).__name__}: {error}", backends)
        print(f"FAIL: live Agent SDK smoke raised {detail}")
        return 1
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    if report.status == "PASS":
        _write_receipt(report)
        return 0
    return 1

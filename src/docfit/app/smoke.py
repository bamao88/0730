"""Live Claude Agent SDK smoke cases for the M0 product gate."""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.agent import (
    FORBIDDEN_TOOLS,
    SUBAGENT_NAME,
    UNIT_ANALYSIS_REQUIRED_FIELDS,
    PermissionAuditEvent,
    build_agent_options,
    project_root,
    terminal_ask_user,
)
from docfit.app.settings import AgentBackend, iter_agent_backends, redact_secrets
from docfit.observability.transcript import (
    SDKTranscriptManager,
    isolated_sdk_environment,
)
from docfit.tools import FULL_TOOL_NAMES
from docfit.tools.image_smoke import SMOKE_BORDER_COLOR, SMOKE_MARKER

SmokeCase = Literal["image", "ask-user", "denied-tools", "path-tools", "subagent"]
SMOKE_CASES: tuple[SmokeCase, ...] = (
    "image",
    "ask-user",
    "denied-tools",
    "path-tools",
    "subagent",
)
SMOKE_BACKEND_TIMEOUT_SECONDS = 180
SMOKE_SYSTEM_PROMPT = (
    "Execute exactly one bounded DocFit diagnostic from the user prompt. Call only the "
    "tools explicitly requested by that diagnostic, do not broaden it into a document "
    "conversion, and do not retry a Tool more than once. If requested evidence is unavailable, "
    "state that once and finish instead of attempting recovery or unrelated Tools."
)


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


def _invalidate_receipt(case_name: SmokeCase, *, root: Path | None = None) -> None:
    """Remove stale success evidence before a new live attempt starts."""
    target = receipt_directory(root) / f"{case_name}.json"
    target.unlink(missing_ok=True)
    target.with_suffix(".tmp").unlink(missing_ok=True)


async def _collect(
    prompt: str,
    backend: AgentBackend,
    *,
    ask_user: Any = terminal_ask_user,
    task_root: Path | None = None,
    permission_events: list[PermissionAuditEvent] | None = None,
) -> tuple[
    ResultMessage | None, tuple[str, ...], tuple[str, ...]
]:
    result: ResultMessage | None = None
    tool_uses: list[str] = []
    session_ids: set[str] = set()
    transcripts = SDKTranscriptManager(forbidden_roots=(project_root(),))
    with transcripts.attempt() as config_directory:
        environment = isolated_sdk_environment(
            backend.sdk_environment(),
            config_directory,
        )
        options = build_agent_options(
            ask_user,
            task_root=task_root,
            agent_env=environment,
            model=backend.model,
            permission_audit=(
                permission_events.append if permission_events is not None else None
            ),
            system_prompt=SMOKE_SYSTEM_PROMPT,
        )
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                message_session = getattr(message, "session_id", None)
                if isinstance(message_session, str) and message_session:
                    session_ids.add(message_session)
                if isinstance(message, AssistantMessage):
                    tool_uses.extend(
                        block.name
                        for block in message.content
                        if isinstance(block, ToolUseBlock)
                    )
                if isinstance(message, ResultMessage):
                    result = message
    if transcripts.summary().status != "cleaned":
        raise RuntimeError("sdk_transcript_cleanup_incomplete")
    return result, tuple(tool_uses), tuple(sorted(session_ids))


async def run_image_smoke(backend: AgentBackend) -> SmokeReport:
    prompt = (
        "This is the DocFit image gate. First invoke the Skill tool to load the "
        "convert-thesis Skill. Then call mcp__docfit__docx_visual_review with "
        '{"mode":"m0_image_smoke"}. Read the marker and border color from the returned '
        "image. In your final response state only what you actually saw; do not infer "
        "image contents from this prompt."
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
            else (
                "Expected image evidence was incomplete; "
                f"result_present={result is not None}, "
                f"result_error={result.is_error if result else None}, "
                f"marker_observed={SMOKE_MARKER in text}, "
                f"color_observed={SMOKE_BORDER_COLOR.casefold() in text.casefold()}, "
                f"required_tools_observed={required_tools.issubset(tool_uses)}, "
                f"session_count={len(session_ids)}."
            )
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
        "denied. Do not substitute a registered DocFit Tool or call Agent."
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


async def run_path_tools_smoke(backend: AgentBackend) -> SmokeReport:
    permission_events: list[PermissionAuditEvent] = []
    with tempfile.TemporaryDirectory(prefix="docfit-path-smoke-") as temporary_value:
        temporary = Path(temporary_value)
        task_root = temporary / "task"
        input_root = task_root / "input"
        work_root = task_root / "work"
        input_root.mkdir(parents=True)
        work_root.mkdir()
        read_file = input_root / "evidence.txt"
        glob_file = work_root / "DOCFIT_GLOB_ALLOWED.md"
        grep_file = task_root / "output-evidence.txt"
        outside_file = temporary / "outside-secret.txt"
        read_marker = "DOCFIT_READ_ALLOWED_7D21"
        grep_marker = "DOCFIT_GREP_ALLOWED_4C92"
        denied_canary = "DOCFIT_OUTSIDE_DENIED_9B73"
        read_file.write_text(read_marker + "\n", encoding="utf-8")
        glob_file.write_text("bounded glob evidence\n", encoding="utf-8")
        grep_file.write_text(grep_marker + "\n", encoding="utf-8")
        outside_file.write_text(denied_canary + "\n", encoding="utf-8")

        prompt = (
            "This is the DocFit path permission gate. Use Read once on "
            f"{read_file}. Use Glob once with path={work_root} and pattern=*.md. "
            f"Use Grep once with path={task_root}, pattern={grep_marker}, and "
            "output_mode=files_with_matches. "
            f"Then attempt Read on {outside_file}; it must be denied. Do not call Bash, Agent, "
            "or any DocFit MCP Tool. Report the allowed Read marker, the Glob filename, and "
            "whether the outside Read was denied. Never guess or invent the denied file content."
        )
        result, tool_uses, session_ids = await _collect(
            prompt,
            backend,
            task_root=task_root,
            permission_events=permission_events,
        )

    text = result.result if result and result.result else ""
    decisions = {(event.tool_name, event.decision) for event in permission_events}
    passed = (
        result is not None
        and not result.is_error
        and {"Read", "Glob", "Grep"}.issubset(tool_uses)
        and {("Read", "allow"), ("Glob", "allow"), ("Grep", "allow")} <= decisions
        and ("Read", "deny") in decisions
        and read_marker in text
        and glob_file.name in text
        and denied_canary not in text
        and len(session_ids) == 1
        and not set(tool_uses).intersection(FULL_TOOL_NAMES)
    )
    return SmokeReport(
        case="path-tools",
        status="PASS" if passed else "FAIL",
        backend=backend.name,
        session_id=result.session_id if result else None,
        tool_uses=tool_uses,
        detail=(
            "Read, Glob, and Grep stayed inside canonical authorized roots; "
            "an outside Read was denied."
            if passed
            else (
                "Path permission evidence was incomplete: "
                f"tools={tool_uses}, decisions={sorted(decisions)}, "
                f"session_count={len(session_ids)}, result_present={bool(text)}"
            )
        ),
    )


async def run_subagent_smoke(backend: AgentBackend) -> SmokeReport:
    permission_events: list[PermissionAuditEvent] = []
    prompt = (
        "This is the DocFit P1 Subagent gate. Load the docfit-school-extract Skill, then "
        "call Agent with subagent_type docfit-unit-analyst. Its prompt must explicitly "
        "contain document_sha256=synthetic-p1, analysis_scope=visual-smoke, one selected "
        "Knowledge module with id=recognition-methods/version=v1/content_digest="
        "sha256:synthetic/content=synthetic-universal-method, empty task evidence, and "
        "requested_output=unit_analysis_v1. Tell the Subagent to call docx_inspect once, "
        "then call docx_visual_review with mode m0_image_smoke and actually inspect the "
        "image. It must return all unit_analysis_v1 fields, using needs_more_evidence for "
        "the unavailable DOCX facts and putting the observed image marker and border color "
        "in findings. After Agent returns, include the complete structured field names and "
        "the observed marker/color in your own final response."
    )
    result, tool_uses, session_ids = await _collect(
        prompt,
        backend,
        permission_events=permission_events,
    )
    text = result.result if result and result.result else ""
    required_tools = {
        "Skill",
        "Agent",
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_visual_review",
    }
    forbidden_tools = {
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_validate",
    }
    allowed_named_subagent = any(
        event.tool_name == "Agent"
        and event.decision == "allow"
        and event.subagent_type == SUBAGENT_NAME
        for event in permission_events
    )
    passed = (
        result is not None
        and not result.is_error
        and required_tools.issubset(tool_uses)
        and not forbidden_tools.intersection(tool_uses)
        and allowed_named_subagent
        and all(field in text for field in UNIT_ANALYSIS_REQUIRED_FIELDS)
        and SMOKE_MARKER in text
        and SMOKE_BORDER_COLOR.casefold() in text.casefold()
        and len(session_ids) == 1
    )
    return SmokeReport(
        case="subagent",
        status="PASS" if passed else "FAIL",
        backend=backend.name,
        session_id=result.session_id if result else None,
        tool_uses=tool_uses,
        detail=(
            "The named read-only Subagent received explicit context, used only inspect and "
            "visual-review, returned unit_analysis_v1, and observed the image."
            if passed
            else (
                "Subagent evidence was incomplete: "
                f"tools={tool_uses}, permissions={permission_events}, "
                f"session_count={len(session_ids)}, result_present={bool(text)}"
            )
        ),
    )


async def run_smoke(case_name: SmokeCase, backend: AgentBackend) -> SmokeReport:
    if case_name == "image":
        return await run_image_smoke(backend)
    if case_name == "ask-user":
        return await run_ask_user_smoke(backend)
    if case_name == "denied-tools":
        return await run_denied_tools_smoke(backend)
    if case_name == "path-tools":
        return await run_path_tools_smoke(backend)
    return await run_subagent_smoke(backend)


async def run_smoke_with_fallback(
    case_name: SmokeCase,
    backends: tuple[AgentBackend, ...],
) -> SmokeReport:
    failures: list[str] = []
    last_report: SmokeReport | None = None
    for backend in backends:
        try:
            async with asyncio.timeout(SMOKE_BACKEND_TIMEOUT_SECONDS):
                report = await run_smoke(case_name, backend)
        except TimeoutError:
            failures.append(
                f"{backend.name} timed out after {SMOKE_BACKEND_TIMEOUT_SECONDS} seconds"
            )
            continue
        except Exception as error:
            failures.append(f"{backend.name} raised {type(error).__name__}")
            continue
        if report.status == "PASS":
            if failures:
                report = replace(
                    report,
                    detail=f"{report.detail} Earlier candidates failed: {'; '.join(failures)}",
                )
            return report
        last_report = report
        if case_name == "image" and report.detail.startswith(
            "Expected image evidence was incomplete;"
        ):
            failures.append(f"{backend.name} returned FAIL ({report.detail})")
        else:
            session_state = "present" if report.session_id else "absent"
            failures.append(
                f"{backend.name} returned FAIL "
                f"(tools={report.tool_uses}, session={session_state})"
            )

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
    selected_case = case_name
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
    # Credential/configuration readiness is checked before declaring that a
    # new live attempt has started.  A NOT_READY invocation did not test the
    # previous receipt and therefore must not erase it.
    _invalidate_receipt(selected_case)
    try:
        report = asyncio.run(run_smoke_with_fallback(selected_case, backends))
    except Exception as error:
        detail = redact_secrets(f"{type(error).__name__}: {error}", backends)
        print(f"FAIL: live Agent SDK smoke raised {detail}")
        return 1
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    if report.status == "PASS":
        _write_receipt(report)
        return 0
    return 1

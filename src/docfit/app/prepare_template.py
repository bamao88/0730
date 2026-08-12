"""Application-owned orchestration for clean school-template preparation."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from docfit.app.agent import (
    AGENT_SDK_MAX_BUFFER_BYTES,
    FORBIDDEN_TOOLS,
    build_read_path_policy,
    make_docfit_schema_version_hook,
    make_permission_callback,
    make_read_path_gate_hook,
    project_root,
    terminal_ask_user,
)
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.observability.transcript import isolated_sdk_environment
from docfit.template.workspace import TemplateWorkspaceService
from docfit.tools.runtime import JsonObject, ToolFailure, atomic_write_json, sha256_file
from docfit.tools.template_tools import (
    TEMPLATE_REVIEW_FULL_TOOL_NAMES,
    TEMPLATE_SEMANTIC_FULL_TOOL_NAMES,
    ReviewBatchState,
    SemanticWorkItemState,
    build_template_review_tool_server,
    build_template_semantic_tool_server,
)

SEMANTIC_WORK_ITEM_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["accepted", "revise", "needs_input"],
        },
        "reason": {"type": "string", "minLength": 1, "maxLength": 1000},
    },
    "required": ["status", "reason"],
    "additionalProperties": False,
}

VISUAL_REVIEW_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "minimum": 1},
                    "verdict": {"type": "string", "enum": ["clean", "defect"]},
                    "defects": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "clipping",
                                        "overlap",
                                        "missing_glyph",
                                        "table_damage",
                                        "spacing",
                                        "header_footer",
                                    ],
                                },
                                "description": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 500,
                                },
                                "repair_hint": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 500,
                                },
                            },
                            "required": ["category", "description"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["page", "verdict", "defects"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string", "minLength": 1, "maxLength": 1000},
    },
    "required": ["pages", "summary"],
    "additionalProperties": False,
}

PREPARE_TEMPLATE_SEGMENT_TIMEOUT_SECONDS = 1800
PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT = 16
PREPARE_TEMPLATE_VISUAL_TURN_LIMIT = 6
PREPARE_TEMPLATE_MAX_SEMANTIC_ATTEMPTS = 2
PREPARE_TEMPLATE_MAX_VISUAL_ATTEMPTS = 2
PREPARE_TEMPLATE_MAX_FINALIZATION_ITEMS = 8
PREPARE_TEMPLATE_MAX_VISUAL_REPAIR_CYCLES = 3

_REQUIRED_BUILT_TOOL_EVIDENCE = {
    "Skill",
    "mcp__docfit__template_get_current_work_item",
    "mcp__docfit__template_submit_current_decision",
    "mcp__docfit__template_get_review_batch",
}
_DEFAULT_REGISTRY = (
    project_root() / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
)


@dataclass(frozen=True, slots=True)
class PrepareTemplateRequest:
    school_template: Path
    output_directory: Path
    school_requirements: Path | None = None
    field_registry: Path | None = None


@dataclass(frozen=True, slots=True)
class PreparedTemplateTask:
    task_root: Path
    template_path: Path
    requirements_path: Path | None
    registry_source: Path
    template_sha256: str
    requirements_sha256: str | None
    registry_sha256: str


@dataclass(frozen=True, slots=True)
class TemplateAgentExecution:
    structured_output: JsonObject
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    session_id: str
    backend: str
    num_turns: int
    duration_ms: int
    duration_api_ms: int


@dataclass(frozen=True, slots=True)
class PrepareTemplateReport:
    status: Literal["built"]
    task_root: str
    artifact_path: str
    template_sha256: str
    counts: JsonObject
    backend: str
    session_id: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    num_turns: int
    duration_ms: int
    duration_api_ms: int


@dataclass(slots=True)
class _ExecutionMetrics:
    tool_uses: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    session_id: str = ""
    num_turns: int = 0
    duration_ms: int = 0
    duration_api_ms: int = 0

    def add_result(self, result: ResultMessage | None) -> None:
        if result is None:
            return
        self.session_id = result.session_id
        self.num_turns += result.num_turns
        self.duration_ms += result.duration_ms
        self.duration_api_ms += result.duration_api_ms


AgentRunner = Callable[[PreparedTemplateTask], Awaitable[TemplateAgentExecution]]


def _regular_input(path: Path, *, field: str, suffixes: tuple[str, ...]) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if (
        resolved.is_symlink()
        or not resolved.is_file()
        or resolved.suffix.casefold() not in suffixes
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_prepare_input",
            message=f"{field} must be a regular supported input file.",
        )
    return resolved


def prepare_template_task(request: PrepareTemplateRequest) -> PreparedTemplateTask:
    template = _regular_input(
        request.school_template,
        field="school_template",
        suffixes=(".docx",),
    )
    requirements = (
        _regular_input(
            request.school_requirements,
            field="school_requirements",
            suffixes=(".txt", ".md", ".yaml", ".yml", ".json", ".pdf", ".docx"),
        )
        if request.school_requirements is not None
        else None
    )
    registry = _regular_input(
        request.field_registry or _DEFAULT_REGISTRY,
        field="field_registry",
        suffixes=(".yaml", ".yml", ".json"),
    )
    task_root = request.output_directory.expanduser().resolve(strict=False)
    if task_root.exists():
        return _resume_prepare_template_task(
            task_root=task_root,
            template=template,
            requirements=requirements,
            registry=registry,
        )
    if task_root.parent.is_symlink() or not task_root.parent.is_dir():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_prepare_output",
            message="prepare-template requires a writable task-directory parent.",
        )
    task_root.mkdir(mode=0o700)
    try:
        input_directory = task_root / "input"
        input_directory.mkdir()
        (task_root / "work").mkdir()
        (task_root / "output").mkdir()
        template_target = input_directory / "school-template.docx"
        shutil.copyfile(template, template_target)
        template_target.chmod(0o444)
        requirements_target: Path | None = None
        if requirements is not None:
            requirements_target = (
                input_directory / f"school-requirements{requirements.suffix.lower()}"
            )
            shutil.copyfile(requirements, requirements_target)
            requirements_target.chmod(0o444)
        skill_source = project_root() / "docs/plans/docfit-school-extract-v2-candidate-skill"
        skill_target = task_root / ".claude/skills/docfit-school-extract"
        skill_target.parent.mkdir(parents=True)
        shutil.copytree(skill_source, skill_target)
        return PreparedTemplateTask(
            task_root=task_root,
            template_path=template_target,
            requirements_path=requirements_target,
            registry_source=registry,
            template_sha256=sha256_file(template_target),
            requirements_sha256=(
                sha256_file(requirements_target) if requirements_target else None
            ),
            registry_sha256=sha256_file(registry),
        )
    except BaseException:
        shutil.rmtree(task_root, ignore_errors=True)
        raise


def _resume_prepare_template_task(
    *,
    task_root: Path,
    template: Path,
    requirements: Path | None,
    registry: Path,
) -> PreparedTemplateTask:
    if task_root.is_symlink() or not task_root.is_dir():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_prepare_output",
            message="The existing prepare-template task root is not a regular directory.",
        )
    input_directory = task_root / "input"
    work_directory = task_root / "work"
    output_directory = task_root / "output"
    if any(
        path.is_symlink() or not path.is_dir()
        for path in (input_directory, work_directory, output_directory)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="prepare_checkpoint_invalid",
            message="The existing task does not contain a valid DocFit checkpoint layout.",
        )
    template_target = input_directory / "school-template.docx"
    if (
        template_target.is_symlink()
        or not template_target.is_file()
        or sha256_file(template_target) != sha256_file(template)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="prepare_source_mismatch",
            message="The existing task belongs to a different school template.",
        )
    if any(output_directory.iterdir()):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="prepare_already_published",
            message="The existing prepare-template task has already published output.",
        )
    existing_requirements = sorted(input_directory.glob("school-requirements.*"))
    requirements_target: Path | None = None
    if requirements is None:
        if existing_requirements:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="prepare_requirements_mismatch",
                message="Resume with the same school-requirements input used by this task.",
            )
    else:
        requirements_target = input_directory / f"school-requirements{requirements.suffix.lower()}"
        if (
            existing_requirements != [requirements_target]
            or requirements_target.is_symlink()
            or sha256_file(requirements_target) != sha256_file(requirements)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="prepare_requirements_mismatch",
                message="Resume with the same school-requirements input used by this task.",
            )
    skill_source = project_root() / "docs/plans/docfit-school-extract-v2-candidate-skill"
    skill_target = task_root / ".claude/skills/docfit-school-extract"
    skill_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_source, skill_target, dirs_exist_ok=True)
    return PreparedTemplateTask(
        task_root=task_root,
        template_path=template_target,
        requirements_path=requirements_target,
        registry_source=registry,
        template_sha256=sha256_file(template_target),
        requirements_sha256=(sha256_file(requirements_target) if requirements_target else None),
        registry_sha256=sha256_file(registry),
    )


def build_prepare_template_prompt(
    prepared: PreparedTemplateTask,
    *,
    role: Literal["semantic", "visual"],
) -> str:
    if role == "visual":
        return (
            "Load the docfit-school-extract Skill and follow its final visual review rules. "
            "Call template_get_review_batch once. Inspect every returned native full-page PNG "
            "at full resolution and return exactly one verdict for every supplied page number. "
            "Judge rendering defects only: clipping, overlap, missing glyphs, damaged tables, "
            "spacing drift, or header/footer misalignment. A blank page alone is not proof of "
            "a defect, and visible bracketed SDT labels are legitimate fill interfaces. Do not "
            "redo template semantics or reclassify sample text, instructions, field meaning, "
            "page intent, or pagination semantics during visual QA. Do not infer cleanliness "
            "from text or XML."
        )
    requirements = (
        f" If the current decision requires an explicit school rule, read only "
        f"{prepared.requirements_path.relative_to(prepared.task_root)}."
        if prepared.requirements_path is not None
        else " No separate school-requirements file was supplied."
    )
    return (
        "Load the docfit-school-extract Skill. Call template_get_current_work_item once and "
        "make one semantic decision that accounts for every clear responsibility in that bound "
        "local crop, not only its target anchor. Treat adjacent top-level objects as part of the "
        "decision boundary; request their field/visual context when needed and batch all clear "
        "operations into the single submission. Initial Registry candidates are intentionally "
        "target-only: for every other object you judge fillable, call "
        "template_request_current_context with that exact object_id and a field_query before "
        "submitting. An unqueried sibling never counts as having no candidate. Context may "
        "return mechanical_blank_segments: these are physical facts, "
        "not field assignments. Judge each label-separated segment independently; when one "
        "paragraph contains separate advisor-name and title blanks, they are two visible "
        "responsibilities and require separate child-run targets. "
        "Request extra context only when the supplied crop is insufficient. Select field IDs "
        "only from candidates returned during this work item, and verify the candidate's "
        "meaning, not just its lexical match. A cover submission-date field must never be reused "
        "for originality or "
        "authorization-statement signature dates; preserve those fixed physical signature/date "
        "lines unless the Registry supplies a dedicated field. Submit exactly one apply or "
        "preserve decision, inspect the "
        "changed-region image when an edit is applied, then return accepted only when that local "
        "result is correct. Before removing samples, account for every student-content "
        "responsibility visible in this item: if a fixed chapter or collection title remains, "
        "materialize one representative content interface in the same decision before removing "
        "the rest. Checkpoint materialized-field counts describe prior locations only and never "
        "satisfy another visible location in the current crop; for example, a thesis-title "
        "placeholder on an abstract page still needs its own slot even when the cover already "
        "has one. A visible student value followed by a formatting annotation is not thereby a "
        "fixed label. When a body structure is being formed, do not delete a demonstrated member "
        "type until it belongs to that structure. Return revise when the submitted edit must be "
        "discarded and retried. "
        "Use template_report_ambiguity before needs_input and name the concrete missing evidence. "
        "The application owns traversal, retries, page batching, final review, publication, and "
        "terminal status; do not try to manage any of them."
        f"{requirements}"
    )


def build_prepare_template_options(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    *,
    role: Literal["semantic", "visual"],
    mcp_server: Any,
) -> ClaudeAgentOptions:
    policy = build_read_path_policy(project=prepared.task_root, cwd=prepared.task_root)
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)
    registered = (
        TEMPLATE_SEMANTIC_FULL_TOOL_NAMES
        if role == "semantic"
        else TEMPLATE_REVIEW_FULL_TOOL_NAMES
    )
    permission_callback = make_permission_callback(
        terminal_ask_user,
        read_path_policy=policy,
        registered_tool_names=registered,
    )
    return ClaudeAgentOptions(
        tools=["Skill", "Read"],
        allowed_tools=[],
        disallowed_tools=[
            *FORBIDDEN_TOOLS,
            "AskUserQuestion",
            "Bash",
            "Write",
            "Agent",
            "Glob",
            "Grep",
        ],
        mcp_servers={"docfit": mcp_server},
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=permission_callback,
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher="mcp__docfit__.*",
                    hooks=[make_docfit_schema_version_hook()],
                ),
                HookMatcher(matcher="Read", hooks=[make_read_path_gate_hook(policy)]),
            ]
        },
        setting_sources=["project"],
        skills=["docfit-school-extract"],
        cwd=prepared.task_root,
        env=environment,
        model=backend.model,
        max_turns=(
            PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT
            if role == "semantic"
            else PREPARE_TEMPLATE_VISUAL_TURN_LIMIT
        ),
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={
            "type": "json_schema",
            "schema": (
                SEMANTIC_WORK_ITEM_OUTPUT_SCHEMA
                if role == "semantic"
                else VISUAL_REVIEW_OUTPUT_SCHEMA
            ),
        },
        system_prompt=(
            "You are DocFit's semantic template analyst. Work on exactly one application-bound "
            "local crop; its target is an anchor, not the only responsibility. Your single "
            "decision must account for every semantically clear top-level object visible in the "
            "crop. Tools execute mechanics while you own the local semantic judgment. Never "
            "leave a retained fixed student-content region with only its title: materialize one "
            "representative content interface before deleting its samples. Counts in the "
            "checkpoint are evidence about prior locations, not permission to skip a visible "
            "fillable occurrence in this crop. Initial field candidates cover only the target; "
            "query each other fillable object's own ID before claiming no field exists. Treat "
            "label-separated mechanical blank segments as separate physical evidence and decide "
            "each one, selecting separate child runs for multiple fields in one paragraph. A "
            "lexical candidate is not enough: its Registry meaning must match the local role; "
            "never use a cover date field for declaration-page signatures."
            if role == "semantic"
            else (
                "You are DocFit's independent final visual reviewer. Inspect every supplied "
                "full-page image and report page-local rendering defects precisely. Do not "
                "redo template semantics: bracketed content-control labels are expected, and a "
                "blank page alone is not a rendering defect."
            )
        ),
    )


def _agent_result_summary(value: object) -> object:
    if isinstance(value, str):
        return value[:6000]
    if not isinstance(value, list):
        return None
    summarized: list[object] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "image":
            summarized.append({"type": "image", "data": "omitted"})
            continue
        copied = dict(item)
        if isinstance(copied.get("text"), str):
            copied["text"] = copied["text"][:6000]
        summarized.append(copied)
    return summarized


def _append_agent_live_event(prepared: PreparedTemplateTask, event: JsonObject) -> None:
    path = prepared.task_root / "work/.docfit/template-agent-live.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp_unix": time.time(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


async def _run_sdk_session(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    *,
    role: Literal["semantic", "visual"],
    mcp_server: Any,
    metrics: _ExecutionMetrics,
) -> ResultMessage | None:
    options = build_prepare_template_options(
        prepared,
        backend,
        config_directory,
        role=role,
        mcp_server=mcp_server,
    )
    result: ResultMessage | None = None
    async with asyncio.timeout(PREPARE_TEMPLATE_SEGMENT_TIMEOUT_SECONDS):
        async with ClaudeSDKClient(options=options) as client:
            await client.query(build_prepare_template_prompt(prepared, role=role))
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            metrics.tool_uses.append(block.name)
                            _append_agent_live_event(
                                prepared,
                                {
                                    "event": "tool_use",
                                    "role": role,
                                    "backend": backend.name,
                                    "tool": block.name,
                                    "input": block.input,
                                },
                            )
                            if block.name == "Skill":
                                value = block.input.get("skill") or block.input.get("name")
                                if isinstance(value, str):
                                    metrics.skills.append(value)
                        elif isinstance(block, TextBlock) and block.text.strip():
                            _append_agent_live_event(
                                prepared,
                                {
                                    "event": "assistant_text",
                                    "role": role,
                                    "backend": backend.name,
                                    "text": block.text[:2000],
                                },
                            )
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            _append_agent_live_event(
                                prepared,
                                {
                                    "event": "tool_result",
                                    "role": role,
                                    "backend": backend.name,
                                    "is_error": bool(block.is_error),
                                    "content": _agent_result_summary(block.content),
                                },
                            )
                if isinstance(message, ResultMessage):
                    result = message
                    _append_agent_live_event(
                        prepared,
                        {
                            "event": "session_result",
                            "role": role,
                            "backend": backend.name,
                            "is_error": result.is_error,
                            "subtype": result.subtype,
                            "terminal_reason": result.terminal_reason,
                            "num_turns": result.num_turns,
                        },
                    )
    metrics.add_result(result)
    return result


def _validated_session_output(
    result: ResultMessage | None,
    *,
    backend: AgentBackend,
    role: str,
) -> JsonObject:
    if result is None:
        raise ToolFailure(
            status="error",
            origin="agent",
            code=f"template_{role}_result_missing",
            message=f"The {backend.name} {role} session returned no SDK result.",
            retryable=True,
        )
    terminal_reason = result.terminal_reason or "unknown"
    if result.is_error:
        status = result.api_error_status
        raise ToolFailure(
            status="error",
            origin="agent",
            code=f"template_{role}_session_failed",
            message=(
                f"The {backend.name} {role} session failed "
                f"(terminal_reason={terminal_reason}, turns={result.num_turns}"
                f"{f', http={status}' if status is not None else ''})."
            ),
            retryable=status not in {400, 401, 402, 403},
        )
    if not isinstance(result.structured_output, dict):
        raise ToolFailure(
            status="error",
            origin="agent",
            code=f"template_{role}_structured_output_missing",
            message=f"The {backend.name} {role} session returned no structured output.",
            retryable=True,
        )
    return result.structured_output


async def _run_semantic_work_item(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    metrics: _ExecutionMetrics,
    service: TemplateWorkspaceService,
    *,
    work_item: JsonObject,
    images: list[Path],
    internal_region_ref: str | None,
    allow_preserve: bool,
) -> None:
    last_failure: ToolFailure | None = None
    last_ambiguity: JsonObject | None = None
    for _attempt in range(PREPARE_TEMPLATE_MAX_SEMANTIC_ATTEMPTS):
        state = SemanticWorkItemState(
            service=service,
            work_item=work_item,
            images=images,
            internal_region_ref=internal_region_ref,
            allow_preserve=allow_preserve,
            start_progress=service.workflow_progress_snapshot(),
        )
        try:
            result = await _run_sdk_session(
                prepared,
                backend,
                config_directory,
                role="semantic",
                mcp_server=build_template_semantic_tool_server(state),
                metrics=metrics,
            )
            output = _validated_session_output(
                result,
                backend=backend,
                role="semantic",
            )
        except (TimeoutError, ToolFailure) as error:
            state.rollback()
            last_failure = (
                error
                if isinstance(error, ToolFailure)
                else ToolFailure(
                    status="error",
                    origin="agent",
                    code="template_semantic_session_timeout",
                    message="A bounded semantic work-item session timed out.",
                    retryable=True,
                )
            )
            continue
        status = output.get("status")
        if status == "accepted" and state.submission is not None:
            outcome = state.submission.get("outcome")
            if outcome == "handled" and not state.mutated:
                state.rollback()
                last_failure = ToolFailure(
                    status="error",
                    origin="application",
                    code="semantic_decision_not_committed",
                    message="The accepted semantic edit did not create a verified checkpoint.",
                    retryable=True,
                )
                continue
            if state.navigation_done:
                return
            if internal_region_ref is not None or state.post_region_ref is not None:
                region_ref = state.post_region_ref or internal_region_ref
                assert region_ref is not None
                service.view(
                    {
                        "action": "next",
                        "region_ref": region_ref,
                        "region_outcome": outcome,
                        "reason": state.submission.get("reason"),
                    }
                )
            return
        state.rollback()
        if status == "needs_input" and state.ambiguity is not None:
            last_ambiguity = state.ambiguity
            continue
        last_failure = ToolFailure(
            status="error",
            origin="agent",
            code="semantic_work_item_not_accepted",
            message=(
                "The semantic Agent did not submit and accept one valid decision for the "
                "current bounded work item."
            ),
            retryable=True,
        )
    if last_ambiguity is not None:
        raise ToolFailure(
            status="needs_input",
            origin="agent",
            code="semantic_ambiguity_unresolved",
            message=str(last_ambiguity.get("reason", "Semantic evidence is insufficient.")),
            suggested_actions=tuple(
                str(item) for item in last_ambiguity.get("missing_evidence", [])
            ),
        )
    raise ToolFailure(
        status="error",
        origin="agent",
        code="semantic_work_item_attempts_exhausted",
        message=(
            last_failure.message
            if last_failure is not None
            else "The bounded semantic work item made no accepted progress."
        ),
        retryable=True,
    )


def _work_item_from_opened(
    opened: JsonObject,
) -> tuple[JsonObject | None, list[Path], str | None, bool]:
    current = opened.get("current_region")
    if isinstance(current, dict):
        return (
            {
                "kind": "local_region",
                "region": current,
                "checkpoint_summary": opened.get("checkpoint_summary", {}),
            },
            [],
            current.get("region_ref") if isinstance(current.get("region_ref"), str) else None,
            True,
        )
    pending = opened.get("pending_edit_intents")
    if isinstance(pending, list) and pending:
        return (
            {
                "kind": "semantic_recovery",
                "pending_intents": pending,
                "checkpoint_summary": opened.get("checkpoint_summary", {}),
            },
            [],
            None,
            False,
        )
    generated = opened.get("pending_generated_content")
    if isinstance(generated, dict):
        return (
            {
                "kind": "generated_content",
                **generated,
                "checkpoint_summary": opened.get("checkpoint_summary", {}),
            },
            [],
            None,
            False,
        )
    return None, [], None, False


async def _complete_semantic_work(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    metrics: _ExecutionMetrics,
    service: TemplateWorkspaceService,
) -> None:
    opened, opened_images = service.view({"action": "open"})
    current = opened.get("current_region")
    region_count = int(current.get("count", 0)) if isinstance(current, dict) else 0
    budget = region_count + PREPARE_TEMPLATE_MAX_FINALIZATION_ITEMS
    for _item_index in range(budget):
        work_item, _, internal_region_ref, allow_preserve = _work_item_from_opened(opened)
        if work_item is None:
            return
        await _run_semantic_work_item(
            prepared,
            backend,
            config_directory,
            metrics,
            service,
            work_item=work_item,
            images=opened_images,
            internal_region_ref=internal_region_ref,
            allow_preserve=allow_preserve,
        )
        opened, opened_images = service.view({"action": "open"})
    raise ToolFailure(
        status="error",
        origin="application",
        code="semantic_work_item_budget_exhausted",
        message="Template semantic work exceeded its deterministic work-item budget.",
        retryable=False,
    )


def _validated_visual_pages(output: JsonObject, expected_pages: set[int]) -> list[JsonObject]:
    raw = output.get("pages")
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ToolFailure(
            status="error",
            origin="agent",
            code="visual_page_verdicts_invalid",
            message="The visual reviewer did not return typed per-page verdicts.",
            retryable=True,
        )
    verdicts = [dict(item) for item in raw]
    returned_pages = {
        int(item["page"]) for item in verdicts if isinstance(item.get("page"), int)
    }
    if returned_pages != expected_pages or len(verdicts) != len(expected_pages):
        raise ToolFailure(
            status="error",
            origin="agent",
            code="visual_page_coverage_mismatch",
            message="The visual reviewer must return exactly one verdict for every bound page.",
            retryable=True,
        )
    for item in verdicts:
        verdict = item.get("verdict")
        defects = item.get("defects")
        if (
            verdict not in {"clean", "defect"}
            or not isinstance(defects, list)
            or (verdict == "clean" and defects)
            or (verdict == "defect" and not defects)
        ):
            raise ToolFailure(
                status="error",
                origin="agent",
                code="visual_page_verdicts_invalid",
                message="Clean pages cannot contain defects and defective pages need details.",
                retryable=True,
            )
    return verdicts


async def _review_final_document(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    metrics: _ExecutionMetrics,
    service: TemplateWorkspaceService,
) -> list[JsonObject]:
    document_ref = service.current_document_ref()
    defects: list[JsonObject] = []
    batch, images = service.final_review({"document_ref": document_ref})
    page_count = batch.get("page_count")
    if not isinstance(page_count, int) or page_count < 1:
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="final_visual_batch_invalid",
            message="The renderer returned an invalid final-page count.",
        )
    for _batch_index in range(page_count):
        current_page_count = batch.get("page_count")
        batch_pages = {
            int(page) for page in batch.get("batch_pages", []) if isinstance(page, int)
        }
        if current_page_count != page_count or not batch_pages:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="final_visual_batch_invalid",
                message="The renderer returned an invalid final-page batch.",
            )
        last_failure: ToolFailure | None = None
        verdicts: list[JsonObject] | None = None
        for _attempt in range(PREPARE_TEMPLATE_MAX_VISUAL_ATTEMPTS):
            try:
                result = await _run_sdk_session(
                    prepared,
                    backend,
                    config_directory,
                    role="visual",
                    mcp_server=build_template_review_tool_server(
                        ReviewBatchState(payload=batch, images=images)
                    ),
                    metrics=metrics,
                )
                output = _validated_session_output(
                    result,
                    backend=backend,
                    role="visual",
                )
                verdicts = _validated_visual_pages(output, batch_pages)
                break
            except (TimeoutError, ToolFailure) as error:
                last_failure = (
                    error
                    if isinstance(error, ToolFailure)
                    else ToolFailure(
                        status="error",
                        origin="agent",
                        code="template_visual_session_timeout",
                        message="A bounded visual-review session timed out.",
                        retryable=True,
                    )
                )
        if verdicts is None:
            raise ToolFailure(
                status="error",
                origin="agent",
                code="visual_review_attempts_exhausted",
                message=(
                    last_failure.message
                    if last_failure is not None
                    else "The visual reviewer returned no usable page verdicts."
                ),
                retryable=True,
            )
        service.record_final_review_verdict(
            document_ref=document_ref,
            render_ref=str(batch["render_ref"]),
            page_count=page_count,
            verdicts=verdicts,
        )
        defects.extend(
            {"page": item["page"], **defect}
            for item in verdicts
            for defect in item["defects"]
            if isinstance(defect, dict)
        )
        next_cursor = batch.get("next_cursor")
        if next_cursor is None:
            return defects
        if not isinstance(next_cursor, str):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="final_visual_cursor_invalid",
                message="The renderer returned an invalid internal page-batch cursor.",
            )
        if _batch_index + 1 >= page_count:
            break
        batch, images = service.final_review(
            {"document_ref": document_ref, "cursor": next_cursor}
        )
    raise ToolFailure(
        status="error",
        origin="application",
        code="final_visual_batch_budget_exhausted",
        message="Final visual review exceeded the rendered page-count bound.",
    )


async def _repair_visual_defects(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    metrics: _ExecutionMetrics,
    service: TemplateWorkspaceService,
    defects: list[JsonObject],
) -> None:
    grouped: dict[int, list[JsonObject]] = {}
    for defect in defects:
        page = defect.get("page")
        if isinstance(page, int):
            grouped.setdefault(page, []).append(
                {key: value for key, value in defect.items() if key != "page"}
            )
    starting_ref = service.current_document_ref()
    for page, page_defects in sorted(grouped.items()):
        work_item, images = service.visual_repair_work_item(
            page=page,
            defects=page_defects,
        )
        await _run_semantic_work_item(
            prepared,
            backend,
            config_directory,
            metrics,
            service,
            work_item=work_item,
            images=images,
            internal_region_ref=None,
            allow_preserve=False,
        )
    if service.current_document_ref() == starting_ref:
        raise ToolFailure(
            status="error",
            origin="application",
            code="visual_repair_no_progress",
            message="Confirmed visual defects produced no new verified Word version.",
        )


async def _run_backend(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
) -> TemplateAgentExecution:
    service = TemplateWorkspaceService(
        task_root=prepared.task_root,
        field_registry=prepared.registry_source,
    )
    metrics = _ExecutionMetrics()
    with tempfile.TemporaryDirectory(prefix="docfit-template-sdk-") as config_name:
        config_directory = Path(config_name)
        await _complete_semantic_work(
            prepared,
            backend,
            config_directory,
            metrics,
            service,
        )
        for repair_cycle in range(PREPARE_TEMPLATE_MAX_VISUAL_REPAIR_CYCLES + 1):
            defects = await _review_final_document(
                prepared,
                backend,
                config_directory,
                metrics,
                service,
            )
            if not defects:
                publication = service.publish(
                    {"document_ref": service.current_document_ref()}
                )
                return TemplateAgentExecution(
                    structured_output=publication,
                    tool_uses=tuple(metrics.tool_uses),
                    skills_loaded=tuple(dict.fromkeys(metrics.skills)),
                    session_id=metrics.session_id,
                    backend=backend.name,
                    num_turns=metrics.num_turns,
                    duration_ms=metrics.duration_ms,
                    duration_api_ms=metrics.duration_api_ms,
                )
            if repair_cycle >= PREPARE_TEMPLATE_MAX_VISUAL_REPAIR_CYCLES:
                break
            await _repair_visual_defects(
                prepared,
                backend,
                config_directory,
                metrics,
                service,
                defects,
            )
    raise ToolFailure(
        status="error",
        origin="application",
        code="visual_repair_cycles_exhausted",
        message="Final visual defects remain after the bounded repair cycles.",
    )


async def run_template_agent(prepared: PreparedTemplateTask) -> TemplateAgentExecution:
    backends = tuple(iter_agent_backends())
    if not backends:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="agent_backend_not_configured",
            message="No configured Agent backend is available for template preparation.",
        )
    failures: list[str] = []
    needs_input: ToolFailure | None = None
    for backend in backends:
        try:
            return await _run_backend(prepared, backend)
        except TimeoutError:
            failures.append(
                f"{backend.name}: exceeded the "
                f"{PREPARE_TEMPLATE_SEGMENT_TIMEOUT_SECONDS}s SDK session timeout"
            )
        except ToolFailure as error:
            if error.origin not in {"agent", "application"}:
                raise
            failures.append(f"{backend.name}: {error.message}")
            if error.status == "needs_input":
                needs_input = error
    if needs_input is not None:
        raise needs_input
    raise ToolFailure(
        status="error",
        origin="agent",
        code="template_agent_backends_failed",
        message="All configured Agent backend candidates failed: " + "; ".join(failures),
        retryable=True,
    )


def _validated_report(
    prepared: PreparedTemplateTask,
    execution: TemplateAgentExecution,
) -> PrepareTemplateReport:
    if sha256_file(prepared.template_path) != prepared.template_sha256:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="prepare_input_changed",
            message="The read-only school template changed during preparation.",
        )
    if (
        prepared.requirements_path is not None
        and sha256_file(prepared.requirements_path) != prepared.requirements_sha256
    ) or sha256_file(prepared.registry_source) != prepared.registry_sha256:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="prepare_input_changed",
            message="A task requirement or Registry source changed during preparation.",
        )
    publication = execution.structured_output
    counts = publication.get("counts")
    if (
        publication.get("status") != "ok"
        or publication.get("published") is not True
        or publication.get("artifact_path") != "output/final-template.docx"
        or not isinstance(counts, dict)
    ):
        raise ToolFailure(
            status="error",
            origin="application",
            code="template_publication_result_invalid",
            message="The application did not produce a valid publication result.",
        )
    if (
        "docfit-school-extract" not in execution.skills_loaded
        or not _REQUIRED_BUILT_TOOL_EVIDENCE.issubset(execution.tool_uses)
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_evidence_incomplete",
            message="The built result lacks required semantic and visual Agent evidence.",
        )
    output = prepared.task_root / "output/final-template.docx"
    output_files = list((prepared.task_root / "output").iterdir())
    if output_files != [output] or not output.is_file():
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="built_result_artifact_mismatch",
            message="The output directory must contain exactly one final Word.",
        )
    template_hash = sha256_file(output)
    if publication.get("template_sha256") != template_hash:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="built_result_artifact_mismatch",
            message="The publication receipt disagrees with the final Word hash.",
        )
    return PrepareTemplateReport(
        status="built",
        task_root=str(prepared.task_root),
        artifact_path=str(output),
        template_sha256=template_hash,
        counts=counts,
        backend=execution.backend,
        session_id=execution.session_id,
        tool_uses=execution.tool_uses,
        skills_loaded=execution.skills_loaded,
        num_turns=execution.num_turns,
        duration_ms=execution.duration_ms,
        duration_api_ms=execution.duration_api_ms,
    )


def _write_execution_trace(
    prepared: PreparedTemplateTask,
    execution: TemplateAgentExecution,
) -> None:
    atomic_write_json(
        prepared.task_root / "work/.docfit/template-agent-execution.json",
        {
            "schema_version": 2,
            "orchestrator": "application_owned",
            "backend": execution.backend,
            "session_id": execution.session_id,
            "num_turns": execution.num_turns,
            "duration_ms": execution.duration_ms,
            "duration_api_ms": execution.duration_api_ms,
            "tool_uses": list(execution.tool_uses),
            "skills_loaded": list(execution.skills_loaded),
            "publication": execution.structured_output,
        },
    )


async def run_prepare_template(
    request: PrepareTemplateRequest,
    *,
    agent_runner: AgentRunner = run_template_agent,
) -> PrepareTemplateReport:
    prepared = prepare_template_task(request)
    execution = await agent_runner(prepared)
    _write_execution_trace(prepared, execution)
    return _validated_report(prepared, execution)

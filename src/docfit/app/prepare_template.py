"""Application shell for one object-driven template preparation Agent session."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
from docfit.tools.runtime import JsonObject, ToolFailure, atomic_write_json, sha256_file
from docfit.tools.template_tools import (
    TEMPLATE_FULL_TOOL_NAMES,
    build_template_tool_server,
)

PREPARE_TEMPLATE_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["built", "blocked"]},
        "artifact_path": {
            "type": ["string", "null"],
            "enum": ["output/final-template.docx", None],
        },
        "template_sha256": {"type": ["string", "null"]},
        "counts": {
            "type": "object",
            "properties": {
                name: {"type": "integer", "minimum": 0}
                for name in ("slot", "remove", "manual", "gap", "unresolved")
            },
            "required": ["slot", "remove", "manual", "gap", "unresolved"],
            "additionalProperties": False,
        },
    },
    "required": ["status", "artifact_path", "template_sha256", "counts"],
    "additionalProperties": False,
    "oneOf": [
        {
            "properties": {
                "status": {"const": "built"},
                "artifact_path": {"const": "output/final-template.docx"},
                "template_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            }
        },
        {
            "properties": {
                "status": {"const": "blocked"},
                "artifact_path": {"type": "null"},
                "template_sha256": {"type": "null"},
            }
        },
    ],
}

PREPARE_TEMPLATE_SEGMENT_TIMEOUT_SECONDS = 1800
# Claude Agent SDK sessions retain prior Tool images. Keep each native session
# deliberately short, then continue from DocFit's application checkpoint in a
# fresh session instead of resuming the transcript.
PREPARE_TEMPLATE_CONTEXT_TURN_LIMIT = 12
PREPARE_TEMPLATE_FINALIZATION_TURN_LIMIT = 24
_REQUIRED_BUILT_TOOL_EVIDENCE = {
    "Skill",
    "mcp__docfit__template_open",
    "mcp__docfit__template_publish",
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
    status: Literal["built", "blocked"]
    task_root: str
    artifact_path: str | None
    template_sha256: str | None
    counts: JsonObject
    backend: str
    session_id: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    num_turns: int
    duration_ms: int
    duration_api_ms: int


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
            requirements_sha256=(sha256_file(requirements_target) if requirements_target else None),
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
    output_files = [item for item in output_directory.iterdir()]
    if output_files:
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


def build_prepare_template_prompt(prepared: PreparedTemplateTask) -> str:
    requirements = (
        f" Optional school requirements: "
        f"{prepared.requirements_path.relative_to(prepared.task_root)} "
        f"(sha256 {prepared.requirements_sha256})."
        if prepared.requirements_path is not None
        else " No separate school-requirements file was supplied; use the template itself."
    )
    pending_edit_intents = _has_pending_edit_intents(prepared)
    finalization_guidance = ""
    if pending_edit_intents:
        finalization_guidance = (
            " Visual-region navigation may already be complete, but an Agent-requested semantic "
            "edit did not commit. Call template_open and resolve every returned "
            "pending_edit_intent before generated-content work. Use template_search or "
            "template_focus only to re-locate the current objects needed for that intent. "
            "Never publish while one remains."
        )
    elif _visual_navigation_complete(prepared):
        finalization_guidance = (
            " Visual-region navigation is already complete. Call template_open and treat "
            "checkpoint_summary, materialized_members, style_signatures, and structural_risks as "
            "facts rather than a semantic completion verdict. Decide whether this school's "
            "surviving objects demonstrate every required fill interface; use bounded "
            "template_search/template_focus only for a concrete missing capability. Resolve "
            "pending_generated_content from its supplied target and candidates, inspect the "
            "changed-region feedback, and publish."
        )
    return (
        "Load the docfit-school-extract Skill and turn the supplied school Word into one clean, "
        "fillable final Word. Start with template_open; it resumes the latest application "
        "checkpoint without loading a prior Agent transcript. Work from the current bounded "
        "region and batch up to thirty-two decisions into one template_edit operations array. "
        "Every array item is a direct action object; never use an item wrapper or put operation "
        "fields at template_edit's top level. A minimal shape is "
        '{"operations":[{"action":"materialize_slot",'
        '"object_ref":{"object_id":"obj-..."},"field_id":"abstract.zh"}]}. Resolve the '
        "current region before exploring another landmark: after open, the "
        "next semantic action must be template_edit or template_next(preserve), except for one "
        "bounded focus, search, or Registry lookup needed to decide that same region. Never "
        "inventory the "
        "document with repeated template_search calls. For a blank or ambiguous run, use its "
        "parent_context label rather than positional "
        "guessing. The Agent decides which visible objects are fixed school content, instructions, "
        "examples, generated content, optional sections, fill slots, or representative body "
        "members. The Tool verifies execution and reports facts; it does not require a global "
        "H1/H2/H3 grammar or infer semantic completeness from Word style names. "
        "When Tool feedback returns knowledge_signals, Read only the matching relative reference "
        "linked by the Skill before deciding that batch; reading an un-signaled card or preloading "
        "multiple cards is a workflow error. On a fresh task, verify every field_id's first use "
        "through one batched template_registry lookup/search for the current objects; never invent "
        "a field_id from a naming convention. Reuse an exact field_id only after the Registry or "
        "checkpoint has established it. "
        "Treat visible color and underline as evidence. If the intended outcome is formal black "
        "without underline, request effective_format={color:black, underline:none}; success means "
        "the effective value is re-read after inheritance, not merely that direct XML disappeared. "
        "Use ensure_page_starts only after deciding that an object must begin a logical new page; "
        "the Tool makes that request idempotent. Refresh a live TOC as one compound object with "
        "representative 1-3 entries; never clear cache rows individually. "
        "Judge the changed-region image and objective receipts returned by template_edit, then "
        "advance with template_next using outcome=handled. If the region is genuinely fixed and "
        "needs no edit, use outcome=preserve plus a short reason. Never preserve writing "
        "instructions, sample/student content, or a student-authored region that still lacks its "
        "fill interface. On every fresh open, resolve pending_edit_intents first; they are prior "
        "Agent-authored semantic operations that never committed, not Tool-generated semantic "
        "guesses. Use their target, member_field_ids, and last_failure as compact recovery "
        "context, re-locate only the necessary current objects, and submit an improved decision. "
        f"Task root: {prepared.task_root}. School template: "
        f"{prepared.template_path.relative_to(prepared.task_root)} "
        f"(sha256 {prepared.template_sha256}).{requirements} "
        "The Registry is Tool-private and lazily searchable; it is not a task list. Do not try to "
        "enumerate or reproduce every Registry field. Remove template instructions, examples, "
        "sample thesis content, and other content that should not survive in a reusable template; "
        "preserve school-mandated fixed text and layout. The absence of existing content controls "
        "is normal. Agent-visible object refs are short object IDs bound by the Tool to the latest "
        "application checkpoint; after an edit, continue only from fresh refs returned by the Tool "
        "and never copy or invent document hashes or fingerprints. template_next only navigates "
        "to an unprocessed physical visual region; you remain responsible for every semantic "
        "decision. Focus or search only when the current crop needs more context; do not review "
        "every page or request full pages for coverage, and do not repeat visual feedback already "
        "returned by template_edit. Publish the exact final document_ref once with "
        "template_publish. Only output/final-template.docx is user-visible. Return blocked only "
        "for a genuinely material semantic ambiguity that cannot be resolved from the current "
        "object, template, optional requirements, Tool feedback, or Skill knowledge."
        f"{finalization_guidance}"
    )


def build_prepare_template_options(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
) -> ClaudeAgentOptions:
    policy = build_read_path_policy(project=prepared.task_root, cwd=prepared.task_root)
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)
    builtin_tools = ("Skill", "Read", "AskUserQuestion")
    permission_callback = make_permission_callback(
        terminal_ask_user,
        read_path_policy=policy,
        registered_tool_names=TEMPLATE_FULL_TOOL_NAMES,
    )
    return ClaudeAgentOptions(
        tools=list(builtin_tools),
        allowed_tools=[],
        disallowed_tools=[
            *FORBIDDEN_TOOLS,
            "Bash",
            "Write",
            "Agent",
            "Glob",
            "Grep",
        ],
        mcp_servers={
            "docfit": build_template_tool_server(
                prepared.task_root,
                prepared.registry_source,
            )
        },
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
        max_turns=_prepare_template_turn_limit(prepared),
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={"type": "json_schema", "schema": PREPARE_TEMPLATE_OUTPUT_SCHEMA},
        system_prompt=(
            "You are the single DocFit template-preparation Agent. Trust your semantic and visual "
            "judgment. The SDK-native Agent loop and seven focused template Tools are the entire "
            "workflow: view one target-object region, batch the decisions visible there, inspect "
            "the changed-region feedback, and publish one Word without an all-page coverage gate. "
            "Inputs are read-only. "
            "There are no plan files, compilers, attempt paths, semantic checker, or compatibility "
            "protocol. Tool checks are mechanical feedback, not a substitute for your judgment."
        ),
    )


def _prepare_template_turn_limit(prepared: PreparedTemplateTask) -> int:
    """Allow one longer, single-image session only for final generated content."""

    return (
        PREPARE_TEMPLATE_FINALIZATION_TURN_LIMIT
        if _visual_navigation_complete(prepared)
        else PREPARE_TEMPLATE_CONTEXT_TURN_LIMIT
    )


def _visual_navigation_complete(prepared: PreparedTemplateTask) -> bool:
    """Read only the durable cursor needed to choose the bounded Agent phase."""

    workspace = prepared.task_root / "work/.docfit/template-workspace-v1"
    try:
        progress: object = json.loads(
            (workspace / "task-progress.json").read_text(encoding="utf-8")
        )
        blueprint: object = json.loads(
            (workspace / "visual-regions.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    region_index = progress.get("region_index") if isinstance(progress, dict) else None
    regions = blueprint.get("regions") if isinstance(blueprint, dict) else None
    return (
        isinstance(region_index, int) and isinstance(regions, list) and region_index >= len(regions)
    )


def _has_pending_edit_intents(prepared: PreparedTemplateTask) -> bool:
    progress_path = prepared.task_root / "work/.docfit/template-workspace-v1/task-progress.json"
    try:
        progress: object = json.loads(progress_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(progress, dict)
        and isinstance(progress.get("pending_edit_intents"), list)
        and progress["pending_edit_intents"]
    )


def _validated_sdk_output(
    result: ResultMessage | None,
    *,
    backend: AgentBackend,
) -> JsonObject:
    if result is None:
        raise ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_result_missing",
            message=f"The {backend.name} Agent backend returned no SDK result.",
            retryable=True,
        )
    terminal_reason = result.terminal_reason or "unknown"
    if result.is_error:
        if result.api_error_status is not None:
            status = result.api_error_status
            raise ToolFailure(
                status="error",
                origin="agent",
                code="template_agent_backend_api_error",
                message=(
                    f"The {backend.name} Agent backend returned HTTP {status} "
                    f"(terminal_reason={terminal_reason}, turns={result.num_turns})."
                ),
                retryable=status not in {400, 401, 402, 403},
            )
        raise ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_backend_error",
            message=(
                f"The {backend.name} Agent backend ended with an SDK error "
                f"(terminal_reason={terminal_reason}, turns={result.num_turns})."
            ),
            retryable=True,
        )
    if not isinstance(result.structured_output, dict):
        raise ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_structured_output_missing",
            message=(
                f"The {backend.name} Agent backend returned no structured output "
                f"(terminal_reason={terminal_reason}, turns={result.num_turns})."
            ),
            retryable=True,
        )
    return result.structured_output


async def _run_backend_segment(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    tool_uses: list[str],
    skills: list[str],
) -> ResultMessage | None:
    """Run one bounded SDK transcript while progress remains application-owned."""

    options = build_prepare_template_options(prepared, backend, config_directory)
    result: ResultMessage | None = None
    async with asyncio.timeout(PREPARE_TEMPLATE_SEGMENT_TIMEOUT_SECONDS):
        async with ClaudeSDKClient(options=options) as client:
            await client.query(build_prepare_template_prompt(prepared))
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_uses.append(block.name)
                            _append_agent_live_event(
                                prepared,
                                {
                                    "event": "tool_use",
                                    "backend": backend.name,
                                    "tool": block.name,
                                    "input": block.input,
                                },
                            )
                            if block.name == "Skill":
                                value = block.input.get("skill") or block.input.get("name")
                                if isinstance(value, str):
                                    skills.append(value)
                        elif isinstance(block, TextBlock) and block.text.strip():
                            _append_agent_live_event(
                                prepared,
                                {
                                    "event": "assistant_text",
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
                            "backend": backend.name,
                            "is_error": result.is_error,
                            "subtype": result.subtype,
                            "terminal_reason": result.terminal_reason,
                            "num_turns": result.num_turns,
                        },
                    )
    return result


async def _run_backend(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
) -> TemplateAgentExecution:
    with tempfile.TemporaryDirectory(prefix="docfit-template-sdk-") as config_name:
        tool_uses: list[str] = []
        skills: list[str] = []
        total_turns = 0
        total_duration_ms = 0
        total_duration_api_ms = 0
        while True:
            result = await _run_backend_segment(
                prepared,
                backend,
                Path(config_name),
                tool_uses,
                skills,
            )
            if result is not None:
                total_turns += result.num_turns
                total_duration_ms += result.duration_ms
                total_duration_api_ms += result.duration_api_ms
            if _context_segment_exhausted(result):
                continue
            structured_output = _validated_sdk_output(result, backend=backend)
            assert result is not None
            return TemplateAgentExecution(
                structured_output=structured_output,
                tool_uses=tuple(tool_uses),
                skills_loaded=tuple(dict.fromkeys(skills)),
                session_id=result.session_id,
                backend=backend.name,
                num_turns=total_turns,
                duration_ms=total_duration_ms,
                duration_api_ms=total_duration_api_ms,
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


def _append_agent_live_event(
    prepared: PreparedTemplateTask,
    event: JsonObject,
) -> None:
    path = prepared.task_root / "work/.docfit/template-agent-live.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp_unix": time.time(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _context_segment_exhausted(result: ResultMessage | None) -> bool:
    if result is None or not result.is_error:
        return False
    reason = (result.terminal_reason or "").casefold()
    subtype = result.subtype.casefold()
    return "max_turn" in reason or "max_turn" in subtype


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
    for backend in backends:
        try:
            return await _run_backend(prepared, backend)
        except TimeoutError:
            failures.append(
                f"{backend.name}: exceeded the "
                f"{PREPARE_TEMPLATE_SEGMENT_TIMEOUT_SECONDS}s SDK segment timeout"
            )
        except ToolFailure as error:
            failures.append(f"{backend.name}: {error.message}")
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
    structured = execution.structured_output
    status = structured.get("status")
    counts = structured.get("counts")
    if status not in {"built", "blocked"} or not isinstance(counts, dict):
        raise ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_result_invalid",
            message="The template Agent result does not match the output contract.",
        )
    if status == "blocked":
        if (
            structured.get("artifact_path") is not None
            or structured.get("template_sha256") is not None
        ):
            raise ToolFailure(
                status="error",
                origin="agent",
                code="blocked_result_fabricated_artifact",
                message="A blocked Agent result included fabricated delivery fields.",
            )
        return PrepareTemplateReport(
            status="blocked",
            task_root=str(prepared.task_root),
            artifact_path=None,
            template_sha256=None,
            counts=counts,
            backend=execution.backend,
            session_id=execution.session_id,
            tool_uses=execution.tool_uses,
            skills_loaded=execution.skills_loaded,
            num_turns=execution.num_turns,
            duration_ms=execution.duration_ms,
            duration_api_ms=execution.duration_api_ms,
        )
    if structured.get("artifact_path") != "output/final-template.docx":
        raise ToolFailure(
            status="error",
            origin="agent",
            code="built_result_artifact_mismatch",
            message="The built result does not identify the one canonical final Word.",
        )
    if (
        "docfit-school-extract" not in execution.skills_loaded
        or not _REQUIRED_BUILT_TOOL_EVIDENCE.issubset(execution.tool_uses)
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_evidence_incomplete",
            message="The built result lacks required Skill/view/publication evidence.",
        )
    output = prepared.task_root / "output" / "final-template.docx"
    output_files = [item for item in (prepared.task_root / "output").iterdir()]
    if output_files != [output] or not output.is_file():
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="built_result_artifact_mismatch",
            message="The output directory must contain exactly one final Word.",
        )
    template_hash = sha256_file(output)
    if structured.get("template_sha256") != template_hash:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="built_result_artifact_mismatch",
            message="The Agent result disagrees with the final Word hash.",
        )
    if template_hash != prepared.template_sha256 and "mcp__docfit__template_edit" not in (
        execution.tool_uses
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_evidence_incomplete",
            message="The changed final Word lacks direct edit Tool evidence.",
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
    """Persist metadata-only evidence even when final result validation fails."""

    atomic_write_json(
        prepared.task_root / "work/.docfit/template-agent-execution.json",
        {
            "schema_version": 1,
            "backend": execution.backend,
            "session_id": execution.session_id,
            "num_turns": execution.num_turns,
            "duration_ms": execution.duration_ms,
            "duration_api_ms": execution.duration_api_ms,
            "tool_uses": list(execution.tool_uses),
            "skills_loaded": list(execution.skills_loaded),
            "structured_output": execution.structured_output,
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

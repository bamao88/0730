"""Application shell for one object-driven template preparation Agent session."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.agent import (
    AGENT_SDK_MAX_BUFFER_BYTES,
    FORBIDDEN_TOOLS,
    READ_ONLY_BUILTIN_TOOLS,
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

PREPARE_TEMPLATE_BACKEND_TIMEOUT_SECONDS = 1800
_REQUIRED_BUILT_TOOL_EVIDENCE = {
    "Skill",
    "mcp__docfit__template_view",
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
    if task_root.exists() or task_root.parent.is_symlink() or not task_root.parent.is_dir():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="output_exists" if task_root.exists() else "invalid_prepare_output",
            message="prepare-template requires a new output task directory.",
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


def build_prepare_template_prompt(prepared: PreparedTemplateTask) -> str:
    requirements = (
        f" Optional school requirements: "
        f"{prepared.requirements_path.relative_to(prepared.task_root)} "
        f"(sha256 {prepared.requirements_sha256})."
        if prepared.requirements_path is not None
        else " No separate school-requirements file was supplied; use the template itself."
    )
    return (
        "Load the docfit-school-extract Skill and turn the supplied school Word into one clean, "
        "fillable final Word. Work from the current page/object context. Start with template_view "
        "action=open; batch up to thirty-two clear decisions visible on the same page into one "
        "template_edit. Use a known field_id directly; when several meanings are uncertain, "
        "query them together in one template_registry call. Judge the changed-page image returned "
        "by template_edit before continuing. Every student-authored content region must retain a "
        "fillable slot after its examples are removed; a structural heading by itself is not a "
        "fillable region. When the current page/object matches one of the Skill's "
        "knowledge-routing signals, Read only that referenced topic before deciding the batch; "
        "never preload all references. "
        f"Task root: {prepared.task_root}. School template: "
        f"{prepared.template_path.relative_to(prepared.task_root)} "
        f"(sha256 {prepared.template_sha256}).{requirements} "
        "The Registry is Tool-private and lazily searchable; it is not a task list. Do not try to "
        "enumerate or reproduce every Registry field. Remove template instructions, examples, "
        "sample thesis content, and other content that should not survive in a reusable template; "
        "preserve school-mandated fixed text and layout. The absence of existing content controls "
        "is normal. Prior object refs still identify their immutable prior version but do not "
        "address the new version, so normally continue from the fresh refs returned by the Tool. "
        "Request another page or object only when the task needs it; do not review every page for "
        "coverage and do not repeat review for a page already returned by template_edit. Publish "
        "the exact final document_ref once with template_publish. Only "
        "output/final-template.docx is user-visible. Return blocked only for a genuinely material "
        "semantic ambiguity that cannot be resolved from the current object, template, optional "
        "requirements, Tool feedback, or Skill knowledge."
    )


def build_prepare_template_options(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
) -> ClaudeAgentOptions:
    policy = build_read_path_policy(
        project=prepared.task_root,
        cwd=prepared.task_root,
        task_root=prepared.task_root,
    )
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)
    builtin_tools = ("Skill", *READ_ONLY_BUILTIN_TOOLS, "AskUserQuestion")
    permission_callback = make_permission_callback(
        terminal_ask_user,
        read_path_policy=policy,
        registered_tool_names=TEMPLATE_FULL_TOOL_NAMES,
    )
    return ClaudeAgentOptions(
        tools=list(builtin_tools),
        allowed_tools=[],
        disallowed_tools=[*FORBIDDEN_TOOLS, "Bash", "Write", "Agent"],
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
                HookMatcher(
                    matcher="Read|Glob|Grep",
                    hooks=[make_read_path_gate_hook(policy)],
                ),
            ]
        },
        setting_sources=["project"],
        skills=["docfit-school-extract"],
        cwd=prepared.task_root,
        env=environment,
        model=backend.model,
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={"type": "json_schema", "schema": PREPARE_TEMPLATE_OUTPUT_SCHEMA},
        system_prompt=(
            "You are the single DocFit template-preparation Agent. Trust your semantic and visual "
            "judgment. The SDK-native Agent loop and four focused template Tools are the entire "
            "workflow: view one needed page/object, batch the decisions visible there, inspect "
            "the changed-page feedback, and publish one Word without an all-page coverage gate. "
            "Inputs are read-only. "
            "There are no plan files, compilers, attempt paths, semantic checker, or compatibility "
            "protocol. Tool checks are mechanical feedback, not a substitute for your judgment."
        ),
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


async def _run_backend(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
) -> TemplateAgentExecution:
    with tempfile.TemporaryDirectory(prefix="docfit-template-sdk-") as config_name:
        options = build_prepare_template_options(prepared, backend, Path(config_name))
        result: ResultMessage | None = None
        tool_uses: list[str] = []
        skills: list[str] = []
        async with ClaudeSDKClient(options=options) as client:
            await client.query(build_prepare_template_prompt(prepared))
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_uses.append(block.name)
                            if block.name == "Skill":
                                value = block.input.get("skill") or block.input.get("name")
                                if isinstance(value, str):
                                    skills.append(value)
                if isinstance(message, ResultMessage):
                    result = message
        structured_output = _validated_sdk_output(result, backend=backend)
        assert result is not None
        return TemplateAgentExecution(
            structured_output=structured_output,
            tool_uses=tuple(tool_uses),
            skills_loaded=tuple(dict.fromkeys(skills)),
            session_id=result.session_id,
            backend=backend.name,
            num_turns=result.num_turns,
            duration_ms=result.duration_ms,
            duration_api_ms=result.duration_api_ms,
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
    for backend in backends:
        try:
            async with asyncio.timeout(PREPARE_TEMPLATE_BACKEND_TIMEOUT_SECONDS):
                return await _run_backend(prepared, backend)
        except TimeoutError:
            failures.append(
                f"{backend.name}: exceeded the "
                f"{PREPARE_TEMPLATE_BACKEND_TIMEOUT_SECONDS}s backend timeout"
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

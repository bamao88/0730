"""Agent-first school-template preparation.

The application creates an immutable task boundary, starts one native Claude
Agent SDK loop with the complete task context, and checks objective terminal
postconditions. It does not select work items, crop semantic context, advance a
region cursor, or decide document meaning.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.agent import (
    AGENT_SDK_MAX_BUFFER_BYTES,
    FORBIDDEN_TOOLS,
    build_read_path_policy,
    build_unit_analyst_definition,
    make_agent_gate_hook,
    make_docfit_schema_version_hook,
    make_permission_callback,
    make_read_path_gate_hook,
    project_root,
    terminal_ask_user,
)
from docfit.app.sdk_execution import SDKResultMetrics
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.observability.transcript import isolated_sdk_environment
from docfit.template.artifact import publish_template_artifact
from docfit.tools import FULL_TOOL_NAMES, MCP_SERVER_NAME, build_docfit_server
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    authorized_path,
    sha256_file,
)
from docfit.tools.service import DocFitToolService

PREPARE_TEMPLATE_TIMEOUT_SECONDS = 1800
PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS = 240
PREPARE_TEMPLATE_MAX_TURNS = 80

_DEFAULT_REGISTRY = (
    project_root() / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
)
_MANIFEST = "work/.docfit/prepare-template-task.json"
_TRACE = "work/.docfit/template-agent-execution.json"
_PUBLICATION = "work/.docfit/template-publication/fill-contract.json"
_REQUIRED_AGENT_EVIDENCE = {
    "Skill",
    "mcp__docfit__docx_inspect",
    "mcp__docfit__docx_edit",
    "mcp__docfit__docx_render",
    "mcp__docfit__docx_visual_review",
    "mcp__docfit__docx_validate",
}

PREPARE_TEMPLATE_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["complete", "needs_input"]},
        "final_docx": {"type": "string", "minLength": 1},
        "candidate_render_ref": {
            "type": "string",
            "pattern": "^render:v2:[0-9a-f]{64}$",
        },
        "reviewed_pages": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "uniqueItems": True,
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "minimum": 1},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "warning", "blocking"],
                    },
                    "blocking": {"type": "boolean"},
                    "category": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                },
                "required": ["page", "severity", "blocking", "category", "description"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string", "minLength": 1},
        "missing_evidence": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": ["status", "summary"],
    "additionalProperties": False,
}


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
    session_count: int = 1
    client_count: int = 1
    wall_duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class PrepareTemplateReport:
    status: Literal["built"]
    task_root: str
    artifact_path: str
    fill_contract_path: str
    template_sha256: str
    counts: JsonObject
    backend: str
    session_id: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    num_turns: int
    duration_ms: int
    duration_api_ms: int
    session_count: int = 1
    client_count: int = 1
    wall_duration_ms: int = 0


AgentRunner = Callable[[PreparedTemplateTask], Awaitable[TemplateAgentExecution]]


def _failure(code: str, message: str, *, origin: str = "request") -> ToolFailure:
    return ToolFailure(status="needs_input", origin=origin, code=code, message=message)


def _regular_input(path: Path, *, field: str, suffixes: tuple[str, ...]) -> Path:
    try:
        value = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise _failure("invalid_prepare_input", f"{field} is unavailable.") from error
    if value.is_symlink() or not value.is_file() or value.suffix.casefold() not in suffixes:
        raise _failure(
            "invalid_prepare_input",
            f"{field} must be a regular supported input file.",
        )
    return value


def _input_manifest(prepared: PreparedTemplateTask) -> JsonObject:
    return {
        "schema_version": 1,
        "architecture": "main_agent_full_context/v1",
        "template": {
            "path": "input/school-template.docx",
            "sha256": prepared.template_sha256,
            "role": "school_template",
        },
        "requirements": (
            {
                "path": str(prepared.requirements_path.relative_to(prepared.task_root)),
                "sha256": prepared.requirements_sha256,
                "role": "school_requirements",
            }
            if prepared.requirements_path is not None
            else None
        ),
        "field_registry": {
            "path": str(prepared.registry_source.relative_to(prepared.task_root)),
            "sha256": prepared.registry_sha256,
            "role": "field_registry",
        },
        "output_boundary": "output/final-template.docx",
    }


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
        return _resume_task(task_root, template, requirements, registry)
    if task_root.parent.is_symlink() or not task_root.parent.is_dir():
        raise _failure(
            "invalid_prepare_output",
            "prepare-template requires a writable task-directory parent.",
        )
    task_root.mkdir(mode=0o700)
    try:
        (task_root / "input").mkdir()
        (task_root / "work/.docfit").mkdir(parents=True)
        (task_root / "output").mkdir()
        template_target = task_root / "input/school-template.docx"
        shutil.copyfile(template, template_target)
        template_target.chmod(0o444)
        requirements_target = None
        if requirements is not None:
            requirements_target = task_root / (
                f"input/school-requirements{requirements.suffix.lower()}"
            )
            shutil.copyfile(requirements, requirements_target)
            requirements_target.chmod(0o444)
        registry_target = task_root / f"input/field-registry{registry.suffix.lower()}"
        shutil.copyfile(registry, registry_target)
        registry_target.chmod(0o444)
        prepared = PreparedTemplateTask(
            task_root=task_root,
            template_path=template_target,
            requirements_path=requirements_target,
            registry_source=registry_target,
            template_sha256=sha256_file(template_target),
            requirements_sha256=(
                sha256_file(requirements_target) if requirements_target is not None else None
            ),
            registry_sha256=sha256_file(registry_target),
        )
        atomic_write_json(task_root / _MANIFEST, _input_manifest(prepared))
        return prepared
    except BaseException:
        shutil.rmtree(task_root, ignore_errors=True)
        raise


def _resume_task(
    task_root: Path,
    template: Path,
    requirements: Path | None,
    registry: Path,
) -> PreparedTemplateTask:
    if task_root.is_symlink() or not task_root.is_dir():
        raise _failure("invalid_prepare_output", "The task root must be a regular directory.")
    manifest_path = task_root / _MANIFEST
    try:
        manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _failure(
            "prepare_checkpoint_invalid",
            "The existing directory is not an Agent-first prepare-template task.",
        ) from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("architecture") != "main_agent_full_context/v1"
    ):
        raise _failure(
            "prepare_checkpoint_invalid",
            "Legacy work-item checkpoints are intentionally not resumed by this architecture.",
        )
    template_target = task_root / "input/school-template.docx"
    requirements_entries = sorted((task_root / "input").glob("school-requirements.*"))
    registry_entries = sorted((task_root / "input").glob("field-registry.*"))
    if (
        not template_target.is_file()
        or template_target.is_symlink()
        or sha256_file(template_target) != sha256_file(template)
        or len(registry_entries) != 1
        or registry_entries[0].is_symlink()
        or sha256_file(registry_entries[0]) != sha256_file(registry)
    ):
        raise _failure("prepare_source_mismatch", "The task belongs to different inputs.")
    requirements_target = requirements_entries[0] if requirements_entries else None
    if (requirements is None) != (requirements_target is None) or (
        requirements is not None
        and requirements_target is not None
        and sha256_file(requirements_target) != sha256_file(requirements)
    ):
        raise _failure(
            "prepare_requirements_mismatch",
            "Resume with the same school-requirements input.",
        )
    output = task_root / "output/final-template.docx"
    output_entries = list((task_root / "output").iterdir())
    if output_entries and (
        output_entries != [output] or output.is_symlink() or not output.is_file()
    ):
        raise _failure(
            "prepare_checkpoint_invalid",
            "The output directory may contain only final-template.docx.",
        )
    return PreparedTemplateTask(
        task_root=task_root,
        template_path=template_target,
        requirements_path=requirements_target,
        registry_source=registry_entries[0],
        template_sha256=sha256_file(template_target),
        requirements_sha256=(
            sha256_file(requirements_target) if requirements_target is not None else None
        ),
        registry_sha256=sha256_file(registry_entries[0]),
    )


def build_prepare_template_prompt(prepared: PreparedTemplateTask) -> str:
    requirements = (
        str(prepared.requirements_path)
        if prepared.requirements_path is not None
        else "none supplied"
    )
    return (
        "Prepare one clean, reusable, fillable school thesis template and own the result "
        "end to end. Load the docfit-school-extract Skill before analysis. You have the complete "
        "task access boundary; decide your own inspection order, visual checks, batching, "
        "retries, and optional read-only delegation. Inputs: school template "
        f"{prepared.template_path}; school requirements: {requirements}; field Registry "
        f"{prepared.registry_source}. The immutable source hash is {prepared.template_sha256}. "
        "Use docx_inspect for the whole-document inventory, Read only for supplied textual "
        "requirements/Registry and Skill references, and only docx_edit for DOCX changes. "
        "Write intermediate DOCX versions under work/ with new names; never modify input/ and "
        "never write output/. Determine school-specific semantics yourself from the supplied "
        "materials; Tool feedback is mechanical evidence, not semantic authority. Before "
        "completion, render the exact final candidate, visually review every final page, repair "
        "blocking defects, and call docx_validate with structured review evidence bound to that "
        "render and DOCX. Return complete only with final_docx, candidate_render_ref, exact "
        "reviewed_pages, findings, and summary. If essential evidence truly cannot be obtained, "
        "return needs_input and name only the missing evidence that changes the result."
    )


def build_prepare_template_options(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
) -> ClaudeAgentOptions:
    root = project_root()
    policy = build_read_path_policy(project=root, cwd=root, task_root=prepared.task_root)
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)
    return ClaudeAgentOptions(
        tools=["Skill", "Read", "Glob", "Grep", "AskUserQuestion", "Agent"],
        allowed_tools=list(FULL_TOOL_NAMES),
        disallowed_tools=[*FORBIDDEN_TOOLS, "Bash", "Write"],
        mcp_servers={MCP_SERVER_NAME: build_docfit_server(prepared.task_root)},
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=make_permission_callback(
            terminal_ask_user,
            read_path_policy=policy,
            registered_tool_names=FULL_TOOL_NAMES,
        ),
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
                HookMatcher(matcher="Agent", hooks=[make_agent_gate_hook()]),
            ]
        },
        agents={"docfit-unit-analyst": build_unit_analyst_definition()},
        setting_sources=["project"],
        skills=["docfit-school-extract"],
        cwd=root,
        env=environment,
        model=backend.model,
        max_turns=PREPARE_TEMPLATE_MAX_TURNS,
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={"type": "json_schema", "schema": PREPARE_TEMPLATE_OUTPUT_SCHEMA},
        system_prompt=(
            "You are DocFit's main template-preparation Agent. You receive one complete task "
            "and own planning, context selection, optional decomposition, Tool choice, retry, "
            "semantic synthesis, visual repair, and completion judgment. The application does "
            "not provide work items or semantic gates. The five DocFit Tools are stateless "
            "domain capabilities; object refs are snapshot-bound and every edit creates a new "
            "snapshot. Follow the canonical docfit-school-extract Skill. Preserve objective "
            "safety invariants and do not claim completion before independent validation and "
            "full-page review of the exact final candidate."
        ),
    )


async def _run_backend(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
) -> TemplateAgentExecution:
    options = build_prepare_template_options(prepared, backend, config_directory)
    tool_uses: list[str] = []
    skills_loaded: list[str] = []
    result: ResultMessage | None = None
    started = time.perf_counter()
    async with ClaudeSDKClient(options=options) as client:
        async with asyncio.timeout(PREPARE_TEMPLATE_TIMEOUT_SECONDS):
            await client.query(build_prepare_template_prompt(prepared))
            responses = client.receive_response().__aiter__()
            while True:
                try:
                    message = await asyncio.wait_for(
                        anext(responses), timeout=PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS
                    )
                except StopAsyncIteration:
                    break
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if not isinstance(block, ToolUseBlock):
                            continue
                        tool_uses.append(block.name)
                        if block.name == "Skill":
                            skill = block.input.get("skill") or block.input.get("name")
                            if isinstance(skill, str):
                                skills_loaded.append(skill)
                if isinstance(message, ResultMessage):
                    result = message
    if result is None:
        raise ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_result_missing",
            message="The main Agent loop ended without a ResultMessage.",
            retryable=True,
        )
    if result.is_error or not isinstance(result.structured_output, dict):
        raise ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_result_invalid",
            message="The main Agent did not return a valid structured completion result.",
            retryable=True,
        )
    metrics = SDKResultMetrics.from_result(result)
    return TemplateAgentExecution(
        structured_output=result.structured_output,
        tool_uses=tuple(tool_uses),
        skills_loaded=tuple(dict.fromkeys(skills_loaded)),
        session_id=result.session_id,
        backend=backend.name,
        num_turns=metrics.num_turns,
        duration_ms=metrics.duration_ms,
        duration_api_ms=metrics.duration_api_ms,
        wall_duration_ms=round((time.perf_counter() - started) * 1000),
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
            with tempfile.TemporaryDirectory(prefix="docfit-template-sdk-") as config_name:
                return await _run_backend(prepared, backend, Path(config_name))
        except (TimeoutError, ToolFailure) as error:
            failures.append(
                error.code if isinstance(error, ToolFailure) else "template_agent_timeout"
            )
    raise ToolFailure(
        status="error",
        origin="agent",
        code="template_agent_backends_exhausted",
        message="No configured backend completed the main template Agent loop: "
        + ", ".join(failures),
        retryable=True,
    )


def _validate_agent_completion(
    prepared: PreparedTemplateTask,
    execution: TemplateAgentExecution,
) -> tuple[Path, JsonObject, JsonObject]:
    output = execution.structured_output
    if output.get("status") != "complete":
        missing = output.get("missing_evidence", [])
        raise _failure(
            "template_agent_needs_input",
            f"The main Agent needs additional evidence: {missing}",
            origin="agent",
        )
    if (
        "docfit-school-extract" not in execution.skills_loaded
        or not _REQUIRED_AGENT_EVIDENCE.issubset(execution.tool_uses)
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_evidence_incomplete",
            message="Completion lacks the canonical Skill or one of the five stable Tools.",
        )
    candidate = authorized_path(
        output.get("final_docx"),
        task_root=prepared.task_root,
        field="final_docx",
    )
    if (
        candidate.suffix.casefold() != ".docx"
        or prepared.task_root / "work" not in candidate.parents
    ):
        raise _failure(
            "template_candidate_path_invalid",
            "The Agent's final candidate must be a DOCX under task work/.",
            origin="postcondition",
        )
    render_ref = output.get("candidate_render_ref")
    reviewed_pages = output.get("reviewed_pages")
    findings = output.get("findings")
    if (
        not isinstance(render_ref, str)
        or not isinstance(reviewed_pages, list)
        or not reviewed_pages
        or any(not isinstance(page, int) or isinstance(page, bool) for page in reviewed_pages)
        or not isinstance(findings, list)
        or any(not isinstance(item, dict) for item in findings)
    ):
        raise _failure(
            "template_visual_evidence_invalid",
            "Completion requires a bound render, reviewed pages, and typed findings.",
            origin="postcondition",
        )
    candidate_hash = sha256_file(candidate)
    visual_review: JsonObject = {
        "document_sha256": candidate_hash,
        "render_ref": render_ref,
        "reviewed_pages": reviewed_pages,
        "findings": findings,
    }
    service = DocFitToolService(task_root=prepared.task_root)
    validation = service.validate(
        {
            "source_docx": str(prepared.template_path),
            "source_sha256": prepared.template_sha256,
            "final_docx": str(candidate),
            "candidate_render_ref": render_ref,
            "visual_review": visual_review,
            "required_visual_coverage": "all_final_pages",
        }
    )
    blocking = [
        item
        for item in validation.get("checks", [])
        if isinstance(item, dict) and item.get("blocking") is True
    ]
    if blocking:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_validation_blocked",
            message="The Agent-selected final Word failed objective validation.",
        )
    return candidate, visual_review, validation


def _inputs_unchanged(prepared: PreparedTemplateTask) -> None:
    if (
        sha256_file(prepared.template_path) != prepared.template_sha256
        or sha256_file(prepared.registry_source) != prepared.registry_sha256
        or (
            prepared.requirements_path is not None
            and sha256_file(prepared.requirements_path) != prepared.requirements_sha256
        )
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="prepare_input_changed",
            message="An immutable task input changed during template preparation.",
        )


def _report(
    prepared: PreparedTemplateTask,
    execution: TemplateAgentExecution,
    publication: JsonObject,
) -> PrepareTemplateReport:
    artifact = prepared.task_root / "output/final-template.docx"
    contract = prepared.task_root / _PUBLICATION
    if (
        publication.get("status") != "ok"
        or publication.get("published") is not True
        or not artifact.is_file()
        or artifact.is_symlink()
        or not contract.is_file()
        or contract.is_symlink()
        or publication.get("template_sha256") != sha256_file(artifact)
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_publication_result_invalid",
            message="Published Word, Fill Contract, and receipt are not hash-consistent.",
        )
    counts = publication.get("counts")
    if not isinstance(counts, dict):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_publication_result_invalid",
            message="The publication receipt has no objective counts.",
        )
    return PrepareTemplateReport(
        status="built",
        task_root=str(prepared.task_root),
        artifact_path=str(artifact),
        fill_contract_path=str(contract),
        template_sha256=sha256_file(artifact),
        counts=counts,
        backend=execution.backend,
        session_id=execution.session_id,
        tool_uses=execution.tool_uses,
        skills_loaded=execution.skills_loaded,
        num_turns=execution.num_turns,
        duration_ms=execution.duration_ms,
        duration_api_ms=execution.duration_api_ms,
        session_count=execution.session_count,
        client_count=execution.client_count,
        wall_duration_ms=execution.wall_duration_ms,
    )


def _load_completed(
    prepared: PreparedTemplateTask,
) -> tuple[TemplateAgentExecution, JsonObject] | None:
    artifact = prepared.task_root / "output/final-template.docx"
    if not artifact.exists():
        return None
    trace_path = prepared.task_root / _TRACE
    try:
        trace: Any = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _failure(
            "completed_prepare_trace_invalid",
            "The final Word exists without a valid Agent-first execution trace.",
            origin="postcondition",
        ) from error
    if not isinstance(trace, dict) or trace.get("architecture") != "main_agent_full_context/v1":
        raise _failure(
            "completed_prepare_trace_invalid",
            "The final Word is not bound to the current Agent-first architecture.",
            origin="postcondition",
        )
    publication = trace.get("publication")
    completion = trace.get("agent_completion")
    if not isinstance(publication, dict) or not isinstance(completion, dict):
        raise _failure(
            "completed_prepare_trace_invalid",
            "The completed trace lacks Agent completion or publication evidence.",
            origin="postcondition",
        )
    execution = TemplateAgentExecution(
        structured_output=completion,
        tool_uses=tuple(str(item) for item in trace.get("tool_uses", [])),
        skills_loaded=tuple(str(item) for item in trace.get("skills_loaded", [])),
        session_id=str(trace.get("session_id", "")),
        backend=str(trace.get("backend", "")),
        num_turns=int(trace.get("num_turns", 0)),
        duration_ms=int(trace.get("duration_ms", 0)),
        duration_api_ms=int(trace.get("duration_api_ms", 0)),
        session_count=1,
        client_count=1,
        wall_duration_ms=int(trace.get("wall_duration_ms", 0)),
    )
    return execution, publication


async def run_prepare_template(
    request: PrepareTemplateRequest,
    *,
    agent_runner: AgentRunner = run_template_agent,
) -> PrepareTemplateReport:
    prepared = prepare_template_task(request)
    completed = _load_completed(prepared)
    if completed is not None:
        execution, publication = completed
        _inputs_unchanged(prepared)
        return _report(prepared, execution, publication)

    execution = await agent_runner(prepared)
    _inputs_unchanged(prepared)
    candidate, visual_review, validation = _validate_agent_completion(prepared, execution)
    publication = publish_template_artifact(
        task_root=prepared.task_root,
        source_docx=prepared.template_path,
        candidate_docx=candidate,
        field_registry=prepared.registry_source,
        validation=validation,
        visual_review=visual_review,
    )
    atomic_write_json(
        prepared.task_root / _TRACE,
        {
            "schema_version": 1,
            "architecture": "main_agent_full_context/v1",
            "sdk_query_count": 1,
            "application_semantic_work_items": 0,
            "backend": execution.backend,
            "session_id": execution.session_id,
            "num_turns": execution.num_turns,
            "duration_ms": execution.duration_ms,
            "duration_api_ms": execution.duration_api_ms,
            "wall_duration_ms": execution.wall_duration_ms,
            "tool_uses": list(execution.tool_uses),
            "skills_loaded": list(execution.skills_loaded),
            "agent_completion": execution.structured_output,
            "publication": publication,
        },
    )
    return _report(prepared, execution, publication)

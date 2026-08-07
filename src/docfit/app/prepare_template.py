"""Development-stage application shell for one template preparation Agent session."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.agent import (
    AGENT_SDK_MAX_BUFFER_BYTES,
    FORBIDDEN_TOOLS,
    READ_ONLY_BUILTIN_TOOLS,
    TRUSTED_BASIC_TOOLS,
    build_read_path_policy,
    make_permission_callback,
    make_read_path_gate_hook,
    project_root,
    terminal_ask_user,
)
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.observability.transcript import isolated_sdk_environment
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
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
            "enum": ["output/template-artifact", None],
        },
        "template_sha256": {"type": ["string", "null"]},
        "fill_contract_sha256": {"type": ["string", "null"]},
        "counts": {
            "type": "object",
            "properties": {
                name: {"type": "integer", "minimum": 0}
                for name in ("slot", "protected", "remove", "manual", "gap", "unresolved")
            },
            "required": ["slot", "protected", "remove", "manual", "gap", "unresolved"],
            "additionalProperties": False,
        },
    },
    "required": [
        "status",
        "artifact_path",
        "template_sha256",
        "fill_contract_sha256",
        "counts",
    ],
    "additionalProperties": False,
}

PREPARE_TEMPLATE_BACKEND_TIMEOUT_SECONDS = 1800
_REQUIRED_BUILT_TOOL_EVIDENCE = {
    "Skill",
    "mcp__docfit__template_observe",
    "mcp__docfit__template_compare",
    "mcp__docfit__template_build",
}


@dataclass(frozen=True, slots=True)
class PrepareTemplateRequest:
    school_template: Path
    school_requirements: Path
    field_registry: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class PreparedTemplateTask:
    task_root: Path
    template_path: Path
    requirements_path: Path
    registry_path: Path
    template_sha256: str
    requirements_sha256: str
    registry_sha256: str


@dataclass(frozen=True, slots=True)
class TemplateAgentExecution:
    structured_output: JsonObject
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    session_id: str
    backend: str


@dataclass(frozen=True, slots=True)
class PrepareTemplateReport:
    status: Literal["built", "blocked"]
    task_root: str
    artifact_path: str | None
    template_sha256: str | None
    fill_contract_sha256: str | None
    counts: JsonObject
    backend: str
    session_id: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]


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
    requirements = _regular_input(
        request.school_requirements,
        field="school_requirements",
        suffixes=(".txt", ".md", ".yaml", ".yml", ".json", ".pdf", ".docx"),
    )
    registry = _regular_input(
        request.field_registry,
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
        (task_root / "work/decisions").mkdir(parents=True)
        (task_root / "work/compiled").mkdir()
        (task_root / "work/attempts").mkdir()
        (task_root / "output").mkdir()
        template_target = input_directory / "school-template.docx"
        requirements_target = input_directory / f"school-requirements{requirements.suffix.lower()}"
        registry_target = input_directory / f"content-fields{registry.suffix.lower()}"
        for source, target in (
            (template, template_target),
            (requirements, requirements_target),
            (registry, registry_target),
        ):
            shutil.copyfile(source, target)
            target.chmod(0o444)
        skill_source = (
            project_root() / "docs/plans/docfit-school-extract-v2-candidate-skill"
        )
        skill_target = task_root / ".claude/skills/docfit-school-extract"
        skill_target.parent.mkdir(parents=True)
        shutil.copytree(skill_source, skill_target)
        return PreparedTemplateTask(
            task_root=task_root,
            template_path=template_target,
            requirements_path=requirements_target,
            registry_path=registry_target,
            template_sha256=sha256_file(template_target),
            requirements_sha256=sha256_file(requirements_target),
            registry_sha256=sha256_file(registry_target),
        )
    except BaseException:
        shutil.rmtree(task_root, ignore_errors=True)
        raise


def build_prepare_template_prompt(prepared: PreparedTemplateTask) -> str:
    return (
        "Load the docfit-school-extract Skill and prepare one development-stage template artifact. "
        f"Task root: {prepared.task_root}. "
        f"School template: {prepared.template_path.relative_to(prepared.task_root)} "
        f"(sha256 {prepared.template_sha256}). "
        f"School requirements: {prepared.requirements_path.relative_to(prepared.task_root)} "
        f"(sha256 {prepared.requirements_sha256}). "
        f"Field Registry: {prepared.registry_path.relative_to(prepared.task_root)} "
        f"(sha256 {prepared.registry_sha256}). "
        "The development-stage working copy is intentionally mutable. You are authorized to "
        "materialize content controls for required registered slots and to remove examples, "
        "placeholders, or instructions when the supplied requirements and observed structure "
        "establish their role and every surviving responsibility is migrated. The absence of "
        "pre-existing content controls is not a blocker. Do not ask for authorization merely "
        "because a required slot or content control does not yet exist. Ask only when the "
        "available task evidence leaves a material field mapping, deletion boundary, source "
        "priority, or visual decision genuinely unresolved. "
        "Use the four DocFit template Tools for all DOCX evidence and mutations. Write decisions "
        "only below work/decisions and compiled files only below work/compiled. Invoke the Skill "
        f"compiler scripts with the exact Python interpreter {sys.executable!s}. Inspect every "
        "required final image before accepting it. Publish only through template_build to "
        "output/template-artifact. Return blocked rather than guessing any material semantic, "
        "deletion, source-priority, or visual decision. Do not claim Human acceptance, a fixed "
        "template, a quality score, or M3 completion."
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
    environment["DOCFIT_PYTHON"] = sys.executable
    builtin_tools = (
        "Skill",
        *READ_ONLY_BUILTIN_TOOLS,
        *TRUSTED_BASIC_TOOLS,
        "AskUserQuestion",
    )
    return ClaudeAgentOptions(
        tools=list(builtin_tools),
        allowed_tools=[],
        disallowed_tools=[*FORBIDDEN_TOOLS, "Agent"],
        mcp_servers={"docfit": build_template_tool_server()},
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=make_permission_callback(
            terminal_ask_user,
            read_path_policy=policy,
            registered_tool_names=TEMPLATE_FULL_TOOL_NAMES,
        ),
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher="Read|Glob|Grep",
                    hooks=[make_read_path_gate_hook(policy)],
                )
            ]
        },
        setting_sources=["project"],
        skills=["docfit-school-extract"],
        cwd=prepared.task_root,
        env=environment,
        model=backend.model,
        max_turns=160,
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={"type": "json_schema", "schema": PREPARE_TEMPLATE_OUTPUT_SCHEMA},
        system_prompt=(
            "You are the single DocFit template-preparation Agent. The filesystem Skill is your "
            "workflow contract; the four MCP Tools are the only trusted DOCX evidence, mutation, "
            "comparison, and publication boundaries. Inputs are read-only. Use SDK-native Tool "
            "calls, permissions, AskUserQuestion, and structured output. Bash and Write are "
            "available only for decision files and the two compiler scripts; never edit a DOCX "
            "with them. A built artifact remains pending the user's Word content review."
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
                f"{backend.name}: The template Agent exceeded the "
                f"{PREPARE_TEMPLATE_BACKEND_TIMEOUT_SECONDS}s backend timeout."
            )
        except ToolFailure as error:
            failures.append(f"{backend.name}: {error.message}")
    raise ToolFailure(
        status="error",
        origin="agent",
        code="template_agent_backends_failed",
        message="All configured Agent backend candidates failed: " + "; ".join(failures),
        retryable=True,
        suggested_actions=(
            "Restore at least one backend credential or quota, then rerun with a "
            "new output directory.",
        ),
    )


def _validated_report(
    prepared: PreparedTemplateTask,
    execution: TemplateAgentExecution,
) -> PrepareTemplateReport:
    if (
        sha256_file(prepared.template_path) != prepared.template_sha256
        or sha256_file(prepared.requirements_path) != prepared.requirements_sha256
        or sha256_file(prepared.registry_path) != prepared.registry_sha256
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="prepare_input_changed",
            message="A read-only task input changed during template preparation.",
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
        if any(
            structured.get(name) is not None
            for name in ("artifact_path", "template_sha256", "fill_contract_sha256")
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
            fill_contract_sha256=None,
            counts=counts,
            backend=execution.backend,
            session_id=execution.session_id,
            tool_uses=execution.tool_uses,
            skills_loaded=execution.skills_loaded,
        )
    if structured.get("artifact_path") != "output/template-artifact":
        raise ToolFailure(
            status="error",
            origin="agent",
            code="built_result_artifact_mismatch",
            message="The Agent built result does not identify the canonical artifact path.",
        )
    if (
        "docfit-school-extract" not in execution.skills_loaded
        or not _REQUIRED_BUILT_TOOL_EVIDENCE.issubset(execution.tool_uses)
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_evidence_incomplete",
            message="The built result lacks required Skill/Tool evidence.",
        )
    artifact = prepared.task_root / "output/template-artifact"
    expected_files = {
        "clean-template.docx",
        "fill-contract.json",
        "visual-review.json",
        "build-report.json",
    }
    if not artifact.is_dir() or {item.name for item in artifact.iterdir()} != expected_files:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="built_result_artifact_mismatch",
            message="The Agent built result does not match a complete four-file artifact.",
        )
    template_hash = sha256_file(artifact / "clean-template.docx")
    contract_hash = sha256_file(artifact / "fill-contract.json")
    try:
        report: Any = json.loads((artifact / "build-report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="built_result_artifact_mismatch",
            message="The build report cannot be revalidated.",
        ) from error
    if (
        structured.get("template_sha256") != template_hash
        or structured.get("fill_contract_sha256") != contract_hash
        or not isinstance(report, dict)
        or report.get("artifact_status") != "built"
        or report.get("counts") != counts
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="built_result_artifact_mismatch",
            message="The Agent structured result disagrees with disk artifact hashes or counts.",
        )
    if (
        template_hash != prepared.template_sha256
        and "mcp__docfit__template_mutate" not in execution.tool_uses
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_evidence_incomplete",
            message="The changed built template lacks mutation Tool evidence.",
        )
    return PrepareTemplateReport(
        status="built",
        task_root=str(prepared.task_root),
        artifact_path=str(artifact),
        template_sha256=template_hash,
        fill_contract_sha256=contract_hash,
        counts=counts,
        backend=execution.backend,
        session_id=execution.session_id,
        tool_uses=execution.tool_uses,
        skills_loaded=execution.skills_loaded,
    )


async def run_prepare_template(
    request: PrepareTemplateRequest,
    *,
    agent_runner: AgentRunner = run_template_agent,
) -> PrepareTemplateReport:
    prepared = prepare_template_task(request)
    execution = await agent_runner(prepared)
    return _validated_report(prepared, execution)

"""Thin M2 application shell around the single Claude Agent SDK runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from functools import partial
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    HookContext,
    HookInput,
    HookJSONOutput,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
)

from docfit.app.agent import (
    SKILL_NAMES,
    PermissionAuditEvent,
    build_agent_options,
    project_root,
    terminal_ask_user,
)
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.knowledge.loader import load_knowledge, select_knowledge_modules
from docfit.observability.models import (
    ObservationCoverageSummary,
    ObservationRecorder,
    SDKTranscriptSummary,
)
from docfit.observability.privacy import (
    project_app_event,
    project_assistant_message,
    project_permission_decision,
    project_report_event,
    project_result_message,
    project_subagent_hook,
    project_tool_hook,
    project_tool_result_block,
    project_tool_use_block,
)
from docfit.observability.runtime import (
    NullObservationRecorder,
    ObservationRun,
    close_observation_safely,
    observation_summary_safely,
)
from docfit.observability.transcript import (
    SDKTranscriptManager,
    isolated_sdk_environment,
    transcript_summary_safely,
)
from docfit.tools.images import pdf_page_count
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    sha256_file,
)
from docfit.tools.service import DocFitToolService
from docfit.visual.evidence import EvidenceStore as VisualEvidenceStore

ConversionStatus = Literal["COMPLETED", "NEEDS_INPUT", "ERROR"]
CONVERSION_BACKEND_TIMEOUT_SECONDS = 900

REQUIRED_CONVERSION_TOOLS = frozenset(
    {
        "Skill",
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
        "mcp__docfit__docx_validate",
    }
)


def _installed_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _observation_runtime_identity() -> dict[str, str]:
    """Return non-secret runtime conditions required for honest run comparison."""

    app_version = _installed_version("docfit-agent")
    sdk_version = _installed_version("claude-agent-sdk")
    values = {
        "app_version": app_version,
        "sdk_version": sdk_version,
        "tool_version": app_version,
        "routing_policy": "configured_backend_fallback_v1",
        "task_authorization": "task_root_capability_v1",
        "validation_requirement": "m2_delivery_gate_v1",
    }
    return {key: value for key, value in values.items() if value is not None}

CONVERSION_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "schema_version": {"const": 1},
        "status": {"type": "string", "enum": ["completed", "needs_input", "error"]},
        "candidate_backbone": {
            "type": ["string", "null"],
            "enum": ["school_template_work_copy", None],
        },
        "final_docx": {"type": ["string", "null"]},
        "candidate_render_ref": {"type": ["string", "null"]},
        "visual_review": {
            "type": ["object", "null"],
            "properties": {
                "schema_version": {"const": 2},
                "document_sha256": {"type": "string"},
                "render_ref": {
                    "type": "string",
                    "pattern": "^render:v2:[0-9a-f]{64}$",
                },
                "renderer": {"type": "object"},
                "reviewed_pages": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "uniqueItems": True,
                },
                "evidence_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "evidence_ref": {"type": "string"},
                            "page": {"type": "integer", "minimum": 1},
                            "kind": {"type": "string"},
                            "severity": {
                                "type": "string",
                                "enum": ["info", "warning", "blocking"],
                            },
                            "blocking": {"type": "boolean"},
                            "observation": {"type": "string"},
                            "suggested_action": {"type": ["string", "null"]},
                        },
                        "required": [
                            "evidence_ref",
                            "page",
                            "kind",
                            "severity",
                            "blocking",
                            "observation",
                            "suggested_action",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "schema_version",
                "document_sha256",
                "render_ref",
                "renderer",
                "reviewed_pages",
                "evidence_refs",
                "findings",
            ],
            "additionalProperties": False,
        },
        "task_rule_evidence": {"type": "array", "items": {"type": "object"}},
        "summary": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "needs_input": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "schema_version",
        "status",
        "candidate_backbone",
        "final_docx",
        "candidate_render_ref",
        "visual_review",
        "task_rule_evidence",
        "summary",
        "warnings",
        "needs_input",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class ConversionRequest:
    input_docx: Path
    school_template: Path
    school_requirements: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class PreparedConversion:
    task_root: Path
    source_docx: Path
    template_docx: Path
    requirements_file: Path
    work_directory: Path
    final_docx: Path
    source_sha256: str
    template_sha256: str
    requirements_sha256: str
    requirements_text: str
    knowledge_version: str
    knowledge_digest: str
    knowledge_modules: tuple[JsonObject, ...]


@dataclass(frozen=True, slots=True)
class AgentExecution:
    structured_output: JsonObject
    final_text: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    session_id: str
    backend: str


class BackendAttemptFailure(RuntimeError):
    """Privacy-safe SDK attempt failure with an explicit route retry decision."""

    def __init__(self, code: str, *, retry_same_route: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retry_same_route = retry_same_route


@dataclass(frozen=True, slots=True)
class ConversionReport:
    schema_version: int
    status: ConversionStatus
    output_directory: str
    final_docx: str | None
    candidate_render_ref: str | None
    candidate_pdf: str | None
    visual_review: str | None
    validation: str | None
    source_sha256: str
    template_sha256: str
    requirements_sha256: str
    knowledge_version: str
    knowledge_digest: str
    backend: str | None
    session_id: str | None
    tool_uses: tuple[str, ...]
    warnings: tuple[str, ...]
    detail: str
    run_id: str | None = None
    task_ref: str | None = None
    final_sha256: str | None = None
    observation_coverage: ObservationCoverageSummary | None = None
    sdk_transcript: SDKTranscriptSummary | None = None


ConversionRunner = Callable[
    [str, PreparedConversion, SDKTranscriptManager, ObservationRun],
    Awaitable[AgentExecution],
]


def _extract_requirements(path: Path, *, character_limit: int = 80000) -> str:
    if path.suffix.casefold() in {".txt", ".md"}:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="requirements_text_unreadable",
                message="The school requirements text cannot be read as UTF-8.",
            ) from error
    elif path.suffix.casefold() == ".pdf":
        executable = shutil.which("pdftotext")
        if executable is None:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="pdftotext_not_found",
                message="pdftotext is required to mount PDF school requirements.",
            )
        try:
            completed = subprocess.run(
                [executable, "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="requirements_pdf_extract_failed",
                message="The school requirements PDF could not be extracted.",
            ) from error
        if completed.returncode != 0:
            raise ToolFailure(
                status="error",
                origin="document",
                code="requirements_pdf_unreadable",
                message="The school requirements PDF has no readable text layer.",
            )
        text = completed.stdout
    else:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_requirements_type",
            message="School requirements must be a PDF, UTF-8 text file, or Markdown file.",
        )
    if not text.strip():
        raise ToolFailure(
            status="needs_input",
            origin="document",
            code="requirements_empty",
            message="The school requirements contain no readable text evidence.",
        )
    return text[:character_limit]


def _require_input_file(path: Path, *, suffixes: set[str], label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except FileNotFoundError as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="conversion_input_missing",
            message=f"{label} does not exist.",
        ) from error
    if not resolved.is_file() or resolved.suffix.casefold() not in suffixes:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="conversion_input_type",
            message=f"{label} has an unsupported file type.",
        )
    return resolved


def prepare_conversion(request: ConversionRequest) -> PreparedConversion:
    source = _require_input_file(request.input_docx, suffixes={".docx"}, label="input_docx")
    template = _require_input_file(
        request.school_template,
        suffixes={".docx"},
        label="school_template",
    )
    requirements = _require_input_file(
        request.school_requirements,
        suffixes={".pdf", ".txt", ".md"},
        label="school_requirements",
    )
    output = request.output_directory.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="conversion_output_not_empty",
            message="The conversion output directory must be absent or empty.",
        )
    source_hash = sha256_file(source)
    template_hash = sha256_file(template)
    requirements_hash = sha256_file(requirements)
    requirements_text = _extract_requirements(requirements)
    knowledge = load_knowledge()
    modules = select_knowledge_modules(
        [document.spec.id for document in knowledge.documents],
        package=knowledge,
    )
    module_payload = tuple(
        {
            "id": module.id,
            "kind": module.kind,
            "description": module.description,
            "version": module.version,
            "content_digest": module.content_digest,
            "content": module.content,
            "package_id": module.package_id,
        }
        for module in modules
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-prepare-", dir=output.parent)
    )
    try:
        temporary_input = temporary / "input"
        temporary_work = temporary / "work"
        temporary_input.mkdir()
        temporary_work.mkdir()
        temporary_source = temporary_input / "student.docx"
        temporary_template = temporary_input / "school-template.docx"
        temporary_requirements = (
            temporary_input / f"school-requirements{requirements.suffix.casefold()}"
        )
        shutil.copy2(source, temporary_source)
        shutil.copy2(template, temporary_template)
        shutil.copy2(requirements, temporary_requirements)
        snapshots = (
            (source, temporary_source, source_hash),
            (template, temporary_template, template_hash),
            (requirements, temporary_requirements, requirements_hash),
        )
        if any(
            sha256_file(original) != expected or sha256_file(copied) != expected
            for original, copied, expected in snapshots
        ):
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="conversion_input_changed",
                message="A conversion input changed while its read-only snapshot was prepared.",
            )
        for copied in (temporary_source, temporary_template, temporary_requirements):
            copied.chmod(0o444)
        temporary_input.chmod(0o555)
        if output.exists():
            if not output.is_dir() or any(output.iterdir()):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="conversion_output_not_empty",
                    message="The conversion output directory changed during preparation.",
                )
            output.rmdir()
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    input_directory = output / "input"
    work_directory = output / "work"
    source_copy = input_directory / "student.docx"
    template_copy = input_directory / "school-template.docx"
    requirements_copy = input_directory / f"school-requirements{requirements.suffix.casefold()}"
    return PreparedConversion(
        task_root=output,
        source_docx=source_copy,
        template_docx=template_copy,
        requirements_file=requirements_copy,
        work_directory=work_directory,
        final_docx=output / "final.docx",
        source_sha256=source_hash,
        template_sha256=template_hash,
        requirements_sha256=requirements_hash,
        requirements_text=requirements_text,
        knowledge_version=knowledge.manifest.version,
        knowledge_digest=knowledge.manifest.content_digest,
        knowledge_modules=module_payload,
    )


def build_conversion_prompt(prepared: PreparedConversion) -> str:
    task = {
        "schema_version": 1,
        "scope": "current_task_only",
        "authorized_task_root": str(prepared.task_root),
        "student_docx": {
            "path": str(prepared.source_docx),
            "sha256": prepared.source_sha256,
            "read_only": True,
        },
        "school_template": {
            "path": str(prepared.template_docx),
            "sha256": prepared.template_sha256,
            "read_only": True,
        },
        "conversion_direction": {
            "candidate_backbone": "school_template_work_copy",
            "content_source": "student_docx_read_only",
            "placement": "student_content_to_template_slots_or_regions",
            "student_copy_as_candidate": "forbidden",
        },
        "school_requirements": {
            "path": str(prepared.requirements_file),
            "sha256": prepared.requirements_sha256,
            "text": prepared.requirements_text,
        },
        "work_directory": str(prepared.work_directory),
        "required_final_docx": str(prepared.final_docx),
        "universal_knowledge": {
            "version": prepared.knowledge_version,
            "package_digest": prepared.knowledge_digest,
            "modules": list(prepared.knowledge_modules),
        },
    }
    return (
        "Complete this one DocFit thesis conversion using the current-task evidence below. "
        "Load both project Skills with Skill and let them guide your semantic decisions. "
        "Use path-bounded Read, Glob, and Grep when a Skill directs you to an explicit "
        "reference, when you need a product Knowledge document, or when you need to search "
        "the authorized current-task input/work/output evidence. "
        "Bash and Write are trusted, auto-approved main-Agent capabilities without a DocFit "
        "path gate. Use them deliberately for supporting work, never expose credentials or "
        "document bodies in logs, and prefer the five DocFit Tools for evidence-bound document "
        "operations. "
        "Use only the five DocFit Tools for document operations. Inspect the student and "
        "template; establish a LibreOffice visual snapshot before layout-sensitive "
        "edits. The school template work copy is the only candidate backbone: begin editing "
        "with the template as docx_edit input_docx, place student content into its confirmed "
        "slots or regions, and use import_content_objects for cross-document objects. Never "
        "start the candidate from a student-document copy or import template sections into "
        "one. Apply supported school rules on the template-backed work copy; use OfficeCLI "
        "feedback when useful; "
        "produce the exact required final.docx; generate a LibreOffice render bound to "
        "it; observe "
        "every final page through docx_visual_review in bounded batches; and call docx_validate. "
        "Use current object_refs after every document hash change. Do not select a backend, use "
        "page numbers as edit identities, consume committed=false, or claim completion with a "
        "verification gap/blocking finding. Delegation to docfit-unit-analyst is optional and "
        "must stay read-only. Return only the requested structured output. Every visual finding "
        "must cite an evidence_ref returned by visual-review. School facts remain current-task "
        "evidence and must not be written to Knowledge.\n\nCURRENT_TASK_JSON:\n"
        + json.dumps(task, ensure_ascii=False, sort_keys=True)
    )


def _conversion_system_prompt() -> str:
    return (
        "You are the single DocFit main Agent running inside Claude Agent SDK. The application "
        "shell only mounts inputs, universal Knowledge, Skills, Tools, permissions, and output "
        "schema; all thesis semantics, Knowledge selection, optional delegation, edits, render "
        "choices, visual judgment, and recovery decisions are yours. Use convert-thesis and "
        "docfit-school-extract as adaptive guidance, not a fixed workflow. The input directory "
        "is read-only. Read, Glob, and Grep are limited to canonical project Skill references, "
        "product Knowledge, and this task's input/work/output roots. Bash and Write are trusted, "
        "auto-approved capabilities without a DocFit path gate and can access any resource "
        "available to this process. Use them deliberately and never expose credentials or "
        "document bodies in logs. The five DocFit Tools remain the authoritative route for "
        "document mutations and document evidence. A clean school-template work copy is the "
        "candidate backbone; the student DOCX is only the read-only content source. "
        "LibreOffice is the only visual renderer and OfficeCLI is only structural. Complete "
        "only with current approximate LibreOffice evidence, full final-page observation, "
        "independent "
        "validation, and zero "
        "blocking findings."
    )


async def _run_backend(
    prompt: str,
    prepared: PreparedConversion,
    backend: AgentBackend,
    config_directory: Path,
    observation_run: ObservationRun,
) -> AgentExecution:
    environment = isolated_sdk_environment(
        backend.sdk_environment(),
        config_directory,
    )
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)

    async def observe_hook(
        hook_input: HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> HookJSONOutput:
        with suppress(Exception):
            phase = hook_input.get("hook_event_name")
            observation_run.project(
                lambda context: (
                    project_subagent_hook(hook_input, context)
                    if phase in {"SubagentStart", "SubagentStop"}
                    else project_tool_hook(hook_input, context)
                )
            )
        return {}

    def observe_permission(event: PermissionAuditEvent) -> None:
        with suppress(Exception):
            observation_run.project(
                lambda context: project_permission_decision(
                    context,
                    tool_name=event.tool_name,
                    decision=("allow" if event.decision == "allow" else "deny"),
                    tool_use_id=event.tool_use_id,
                    agent_id=event.agent_id,
                    subagent_type=event.subagent_type,
                    reason_code=event.reason_code,
                    question_count=event.question_count,
                    option_count=event.option_count,
                    answered=event.answered,
                    duration_ms=event.duration_ms,
                ),
            )

    options = build_agent_options(
        terminal_ask_user,
        cwd=project_root(),
        task_root=prepared.task_root,
        agent_env=environment,
        model=backend.model,
        permission_audit=observe_permission if observation_run.enabled else None,
        observation_hook=observe_hook if observation_run.enabled else None,
        system_prompt=_conversion_system_prompt(),
        output_format={"type": "json_schema", "schema": CONVERSION_OUTPUT_SCHEMA},
        max_turns=40,
    )
    result: ResultMessage | None = None
    tool_uses: list[str] = []
    skills_loaded: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                observation_run.project(
                    partial(project_assistant_message, message)
                )
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        observation_run.project(
                            partial(
                                project_tool_use_block,
                                block,
                                session_id=message.session_id,
                                parent_tool_use_id=message.parent_tool_use_id,
                            )
                        )
                        tool_uses.append(block.name)
                        if block.name == "Skill":
                            skill_name = block.input.get("skill") or block.input.get("name")
                            if isinstance(skill_name, str):
                                skills_loaded.append(skill_name)
                    elif isinstance(block, ToolResultBlock):
                        observation_run.project(
                            partial(
                                project_tool_result_block,
                                block,
                                session_id=message.session_id,
                                parent_tool_use_id=message.parent_tool_use_id,
                            )
                        )
            if isinstance(message, ResultMessage):
                observation_run.project(
                    partial(project_result_message, message)
                )
                result = message
    if result is None:
        raise BackendAttemptFailure("agent_result_missing", retry_same_route=True)
    if result.is_error:
        if result.api_error_status == 400:
            raise BackendAttemptFailure(
                "backend_request_rejected",
                retry_same_route=False,
            )
        raise BackendAttemptFailure("backend_result_error", retry_same_route=True)
    if not isinstance(result.structured_output, dict):
        raise BackendAttemptFailure(
            "agent_structured_output_missing",
            retry_same_route=True,
        )
    return AgentExecution(
        structured_output=result.structured_output,
        final_text=result.result or "",
        tool_uses=tuple(tool_uses),
        skills_loaded=tuple(dict.fromkeys(skills_loaded)),
        session_id=result.session_id,
        backend=backend.name,
    )


async def run_conversion_agent(
    prompt: str,
    prepared: PreparedConversion,
    transcripts: SDKTranscriptManager | None = None,
    observation_run: ObservationRun | None = None,
) -> AgentExecution:
    transcript_manager = transcripts or SDKTranscriptManager()
    run_observation = observation_run or ObservationRun(
        f"run_{secrets.token_hex(16)}",
        NullObservationRecorder(),
    )
    backends = tuple(iter_agent_backends())
    if not backends:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="agent_backend_not_configured",
            message="No configured Agent backend is available for conversion.",
        )
    failures: list[str] = []
    timed_out_routes: set[tuple[str, str, str]] = set()
    rejected_routes: set[tuple[str, str, str]] = set()
    for attempt_number, backend in enumerate(backends, start=1):
        route = (backend.name, backend.base_url, backend.model)
        route_fingerprint = hashlib.sha256("\x00".join(route).encode()).hexdigest()
        if route in timed_out_routes or route in rejected_routes:
            continue
        attempt_started = time.monotonic()
        run_observation.project(
            partial(
                project_app_event,
                source_event_id=f"backend-{attempt_number}-start",
                kind="backend_started",
                status="started",
                backend=backend.name,
                model=backend.model,
                attempt=attempt_number,
                runtime_identity={"route_fingerprint": route_fingerprint},
            )
        )
        try:
            with transcript_manager.attempt() as config_directory:
                async with asyncio.timeout(CONVERSION_BACKEND_TIMEOUT_SECONDS):
                    execution = await _run_backend(
                        prompt,
                        prepared,
                        backend,
                        config_directory,
                        run_observation,
                    )
            run_observation.project(
                partial(
                    project_app_event,
                    source_event_id=f"backend-{attempt_number}-finish",
                    kind="backend_finished",
                    status="ok",
                    backend=backend.name,
                    model=backend.model,
                    attempt=attempt_number,
                    runtime_identity={"route_fingerprint": route_fingerprint},
                    duration_ms=(time.monotonic() - attempt_started) * 1000,
                )
            )
            return execution
        except TimeoutError:
            timed_out_routes.add(route)
            failures.append(
                f"{backend.name}:timeout-{CONVERSION_BACKEND_TIMEOUT_SECONDS}s"
            )
            failure_code = "backend_timeout"
        except BackendAttemptFailure as error:
            failures.append(f"{backend.name}:{error.code}")
            failure_code = error.code
            if not error.retry_same_route:
                rejected_routes.add(route)
        except Exception as error:
            failures.append(f"{backend.name}:{type(error).__name__}")
            failure_code = "backend_attempt_failed"
        run_observation.project(
            partial(
                project_app_event,
                source_event_id=f"backend-{attempt_number}-finish",
                kind="backend_finished",
                status="error",
                backend=backend.name,
                model=backend.model,
                attempt=attempt_number,
                runtime_identity={"route_fingerprint": route_fingerprint},
                failure_code=failure_code,
                duration_ms=(time.monotonic() - attempt_started) * 1000,
            )
        )
    raise ToolFailure(
        status="error",
        origin="engine",
        code="agent_conversion_failed",
        message="All configured Agent backend candidates failed: " + ", ".join(failures),
    )


def _resolve_render_reference(
    value: Any,
    prepared: PreparedConversion,
) -> tuple[str, Path, JsonObject]:
    if not isinstance(value, str) or not value:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="candidate_render_ref_missing",
            message="The Agent returned no candidate render ref.",
        )
    path, manifest = VisualEvidenceStore(prepared.task_root).resolve_render(value)
    return value, path, manifest


def _validated_report_warnings(
    candidate: JsonObject,
    validation: JsonObject,
) -> tuple[str, ...]:
    """Return privacy-safe warning identities from final verified evidence only."""
    labels: list[str] = []
    for source, raw_items in (
        ("candidate", candidate.get("warnings", [])),
        ("validation", validation.get("warnings", [])),
    ):
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            code = item.get("code") if isinstance(item, dict) else None
            if isinstance(code, str) and code:
                labels.append(f"{source}:{code}")
            elif item:
                labels.append(f"{source}:unspecified_warning")
    checks = validation.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict) or check.get("result") == "ok":
                continue
            name = check.get("name")
            result = check.get("result")
            if isinstance(name, str) and isinstance(result, str):
                labels.append(f"validation_check:{name}:{result}")
    return tuple(dict.fromkeys(labels))


def _finalize_conversion(
    prepared: PreparedConversion,
    execution: AgentExecution,
) -> ConversionReport:
    output = execution.structured_output
    if output.get("status") != "completed":
        status: ConversionStatus = (
            "NEEDS_INPUT" if output.get("status") == "needs_input" else "ERROR"
        )
        return ConversionReport(
            1,
            status,
            str(prepared.task_root),
            None,
            None,
            None,
            None,
            None,
            prepared.source_sha256,
            prepared.template_sha256,
            prepared.requirements_sha256,
            prepared.knowledge_version,
            prepared.knowledge_digest,
            execution.backend,
            execution.session_id,
            execution.tool_uses,
            tuple(str(item) for item in output.get("warnings", [])),
            str(output.get("summary", "Agent did not complete conversion.")),
        )
    if output.get("candidate_backbone") != "school_template_work_copy":
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="candidate_backbone_invalid",
            message=(
                "The Agent did not declare the school-template work copy as candidate "
                "backbone."
            ),
        )
    missing_tools = REQUIRED_CONVERSION_TOOLS - set(execution.tool_uses)
    if missing_tools:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="conversion_tool_evidence_incomplete",
            message="The Agent completion lacks one or more required Skill/Tool calls.",
        )
    missing_skills = set(SKILL_NAMES) - set(execution.skills_loaded)
    if missing_skills:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="conversion_skill_evidence_incomplete",
            message="The Agent completion did not load both required DocFit domain Skills.",
        )
    final_value = output.get("final_docx")
    if not isinstance(final_value, str) or Path(final_value).resolve() != prepared.final_docx:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="final_docx_path_mismatch",
            message="The Agent did not publish the exact required final.docx.",
        )
    if not prepared.final_docx.is_file():
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="final_docx_missing",
            message="The Agent claimed completion but final.docx is absent.",
        )
    if sha256_file(prepared.source_docx) != prepared.source_sha256:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="conversion_source_changed",
            message="The read-only source snapshot changed during conversion.",
        )
    candidate_ref, candidate_path, candidate = _resolve_render_reference(
        output.get("candidate_render_ref"), prepared
    )
    final_hash = sha256_file(prepared.final_docx)
    if not (
        candidate.get("document_sha256") == final_hash
        and candidate.get("fidelity") == "approximate"
        and isinstance(candidate.get("renderer"), dict)
        and candidate["renderer"].get("name") == "libreoffice"
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="candidate_evidence_invalid",
            message="The final candidate is not current LibreOffice visual evidence.",
        )
    visual = output.get("visual_review")
    if not isinstance(visual, dict):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="visual_review_missing",
            message="The Agent returned no structured final-page visual review.",
        )
    if not (
        visual.get("document_sha256") == final_hash
        and visual.get("render_ref") == candidate_ref
        and visual.get("renderer") == candidate.get("renderer")
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="visual_review_binding_mismatch",
            message="The visual review is not bound to the current candidate evidence.",
        )
    page_count = candidate.get("page_count")
    reviewed_pages = visual.get("reviewed_pages")
    if not isinstance(page_count, int) or reviewed_pages != list(range(1, page_count + 1)):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="visual_review_incomplete",
            message="The Agent did not review every final candidate page in order.",
        )
    evidence_refs = visual.get("evidence_refs")
    findings = visual.get("findings")
    if not isinstance(evidence_refs, list) or not isinstance(findings, list):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="visual_review_shape_invalid",
            message="The final visual review has an invalid evidence shape.",
        )
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("evidence_ref") not in evidence_refs:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="visual_finding_evidence_missing",
                message="A visual finding does not cite valid observed evidence.",
            )
        if finding.get("blocking") is True or finding.get("severity") == "blocking":
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="blocking_visual_finding",
                message="The Agent claimed completion with a blocking visual finding.",
            )
    visual_path = prepared.task_root / "visual-review.json"
    atomic_write_json(visual_path, visual)
    validation = DocFitToolService(task_root=prepared.task_root).validate(
        {
            "task_root": str(prepared.task_root),
            "source_docx": str(prepared.source_docx),
            "source_sha256": prepared.source_sha256,
            "final_docx": str(prepared.final_docx),
            "knowledge_version": prepared.knowledge_version,
            "task_rule_evidence": output.get("task_rule_evidence", []),
            "visual_review": str(visual_path),
            "candidate_render_ref": candidate_ref,
            "required_visual_coverage": "all_final_pages",
        }
    )
    if validation["summary"]["errors"] or any(
        warning.get("code") == "verification_gap" for warning in validation["warnings"]
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="final_validation_failed",
            message="Independent final validation did not pass the M2 delivery gate.",
        )
    validation_path = prepared.task_root / "validation.json"
    atomic_write_json(validation_path, validation)
    candidate_pdf_path = (candidate_path / "document.pdf").resolve()
    if (
        not candidate_pdf_path.is_file()
        or prepared.task_root not in candidate_pdf_path.parents
        or pdf_page_count(candidate_pdf_path) != page_count
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="candidate_pdf_invalid",
            message="The LibreOffice candidate PDF is missing, outside the task, or incomplete.",
        )
    # A model may retain warnings from intermediate Tool calls after the final
    # evidence has changed.  Successful reports are authoritative summaries of
    # the current candidate and the independent validation rerun, not a replay
    # of stale Agent narration.
    warnings = _validated_report_warnings(candidate, validation)
    validation_summary = validation.get("summary", {})
    issue_count = (
        validation_summary.get("issues", 0)
        if isinstance(validation_summary, dict)
        else 0
    )
    return ConversionReport(
        1,
        "COMPLETED",
        str(prepared.task_root),
        str(prepared.final_docx),
        candidate_ref,
        str(candidate_pdf_path),
        str(visual_path),
        str(validation_path),
        prepared.source_sha256,
        prepared.template_sha256,
        prepared.requirements_sha256,
        prepared.knowledge_version,
        prepared.knowledge_digest,
        execution.backend,
        execution.session_id,
        execution.tool_uses,
        warnings,
        (
            "Conversion completed with current LibreOffice visual evidence, complete "
            "Agent visual coverage, and independent validation; "
            f"pages={page_count}, validation_issues={issue_count}, "
            f"evidence_warnings={len(warnings)}."
        ),
    )


async def run_conversion(
    request: ConversionRequest,
    *,
    runner: ConversionRunner = run_conversion_agent,
    observation: ObservationRecorder | None = None,
    transcripts: SDKTranscriptManager | None = None,
) -> ConversionReport:
    run_id = f"run_{secrets.token_hex(16)}"
    task_ref = f"task_{secrets.token_hex(16)}"
    recorder = observation or NullObservationRecorder()
    transcript_manager = transcripts
    observation_run: ObservationRun | None = None
    try:
        prepared = prepare_conversion(request)
        observation_run = ObservationRun(run_id, recorder)
        observation_run.project(
            lambda context: project_app_event(
                context,
                source_event_id="run-start",
                kind="run_started",
                status="started",
                task_ref=task_ref,
                hashes={
                    "source_sha256": prepared.source_sha256,
                    "template_sha256": prepared.template_sha256,
                    "requirements_sha256": prepared.requirements_sha256,
                },
                runtime_identity=_observation_runtime_identity(),
            ),
        )
        transcript_manager = transcript_manager or SDKTranscriptManager(
            forbidden_roots=(prepared.task_root, project_root())
        )
        prompt = build_conversion_prompt(prepared)
        try:
            execution = await runner(
                prompt,
                prepared,
                transcript_manager,
                observation_run,
            )
            report = _finalize_conversion(prepared, execution)
        except ToolFailure as error:
            report = ConversionReport(
                1,
                "NEEDS_INPUT" if error.status == "needs_input" else "ERROR",
                str(prepared.task_root),
                None,
                None,
                None,
                None,
                None,
                prepared.source_sha256,
                prepared.template_sha256,
                prepared.requirements_sha256,
                prepared.knowledge_version,
                prepared.knowledge_digest,
                None,
                None,
                (),
                (error.code,),
                error.message,
            )
        final_sha256: str | None = None
        if report.final_docx is not None:
            try:
                final_sha256 = sha256_file(Path(report.final_docx))
            except OSError:
                final_sha256 = None
        report = replace(
            report,
            schema_version=2,
            run_id=run_id,
            task_ref=task_ref,
            final_sha256=final_sha256,
            observation_coverage=observation_summary_safely(recorder),
            sdk_transcript=transcript_summary_safely(transcript_manager),
        )
        observation_run.project(
            lambda context: project_report_event(asdict(report), context)
        )
        observation_run.project(
            lambda context: project_app_event(
                context,
                source_event_id="run-finish",
                kind="run_finished",
                status=report.status.casefold(),
                duration_ms=context.monotonic_offset_ms,
                hashes={"final_sha256": report.final_sha256 or ""},
                failure_code=(
                    report.warnings[0]
                    if report.status != "COMPLETED" and report.warnings
                    else None
                ),
            ),
        )
        try:
            atomic_write_json(prepared.task_root / "conversion-report.json", asdict(report))
        except OSError as error:
            raise ToolFailure(
                status="error",
                origin="app",
                code="conversion_report_write_failed",
                message="The conversion report could not be written to task storage.",
            ) from error
        return report
    finally:
        close_observation_safely(recorder)

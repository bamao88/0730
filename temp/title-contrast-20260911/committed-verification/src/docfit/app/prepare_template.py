"""Agent-first school-template preparation.

The application creates an immutable task boundary, starts one native Claude
Agent SDK loop with the complete task context, and checks objective terminal
postconditions. It does not select work items, crop semantic context, advance a
region cursor, or decide document meaning.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NoReturn

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import AssistantMessage, ResultMessage, StreamEvent, ToolUseBlock

from docfit.app.agent import (
    AGENT_SDK_MAX_BUFFER_BYTES,
    FORBIDDEN_TOOLS,
    UNTRUSTED_SOURCE_DATA_LABEL,
    PermissionAuditEvent,
    build_read_path_policy,
    make_docfit_schema_version_hook,
    make_permission_callback,
    make_read_path_gate_hook,
    project_root,
    terminal_ask_user,
)
from docfit.app.sdk_execution import SDKResultMetrics
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.fields import FieldRegistrySnapshot
from docfit.observability.transcript import isolated_sdk_environment
from docfit.template.artifact import (
    publication_slot_protocol_status,
    publish_template_artifact,
)
from docfit.template.harness import TemplateHarnessService
from docfit.template.judgment_shape import (
    ORDERED_SEMANTIC_PART_ROLES,
    mechanical_feedback,
)
from docfit.template.materialization import (
    MaterializationIntentType,
    compile_materialization_intents,
    materialization_readiness_feedback,
    materialize_template_from_semantics,
)
from docfit.template.reading_packet import (
    build_unit_reading_packet,
    object_id_for_item,
    objects_for_locator_span,
)
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_entries import (
    OBJECT_ID_BACKEND_ALIAS_ROLE,
    CanonicalSourceInventory,
    build_canonical_source_inventory,
    project_source_entries_onto_objects,
    select_source_entries_for_objects,
    source_entry_by_object_id,
    source_entry_ref_for_entry,
)
from docfit.tools import (
    MCP_SERVER_NAME,
    build_docfit_server,
)
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    sha256_file,
    sha256_json,
)
from docfit.tools.service import DocFitToolService
from docfit.tools.surface import (
    DOCFIT_EVIDENCE_TOOL,
)


def _positive_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


PREPARE_TEMPLATE_TIMEOUT_SECONDS = _positive_int_env(
    "DOCFIT_PREPARE_TEMPLATE_TIMEOUT_SECONDS",
    3600,
)
PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS = _positive_int_env(
    "DOCFIT_PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS",
    600,
)
PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS = _positive_int_env(
    "DOCFIT_PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS",
    180,
)
PREPARE_TEMPLATE_MAX_TURNS = _positive_int_env("DOCFIT_PREPARE_TEMPLATE_MAX_TURNS", 120)
POST_UNIT_MAX_TURNS = min(PREPARE_TEMPLATE_MAX_TURNS, 20)

_DEFAULT_REGISTRY = (
    project_root() / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
)
_MANIFEST = "work/.docfit/prepare-template-task.json"
_TRACE = "work/.docfit/template-agent-execution.json"
_UNIT_BOUNDARY_CHECKPOINT = "work/.docfit/unit-boundary-checkpoint.json"
_POST_UNIT_CHECKPOINT = "work/.docfit/post-unit-checkpoint.json"
_HARNESS_OBJECT_INVENTORY = "work/.docfit/harness/object-inventory.json"
_HARNESS_SEMANTIC_JUDGMENTS = "work/.docfit/harness/semantic-judgments.json"
_POST_UNIT_MATERIALIZATION_RECEIPT = "work/.docfit/post-unit-materialization/materialization.json"
_UNIT_BOUNDARY_STAGE = "unit-boundary"
_POST_UNIT_STAGE = "post-unit"
_PUBLICATION = "output/fill-contract.yaml"
_SEMANTIC_FEEDBACK_ATTEMPTS = 7
_UNIT_BOUNDARY_FEEDBACK_ATTEMPTS = 3
_MATERIALIZATION_READINESS_NEXT_STEP = (
    "Return to the Agent with this materialization readiness feedback. "
    "The Agent must revise semantic_judgments for the listed source_entry_id "
    "with ordered parts, or return needs_input if the "
    "required school semantic evidence is unavailable. Each part text must "
    "come from the scoped source entry text. If a blocker is open_questions, "
    "keep only questions that would change the school semantic judgment; "
    "remove implementation, Registry maintenance, Word carrier, or Host "
    "materialization concerns from complete semantic_judgments."
)
_AGENT_AUTHORED_STYLE_CONTRACT_KEYS = frozenset(
    {
        "fill_contract",
        "style_contract",
        "style_contracts",
        "style_contract_set",
        "style_contract_set_digest",
    }
)

_ORDERED_SEMANTIC_JUDGMENT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "source_entry_id": {"type": "string", "minLength": 1},
        "scope": {
            "type": "object",
            "properties": {
                "reading_block_id": {"type": "string", "minLength": 1},
                "reading_range_id": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "parts": {
            "type": "array",
            "description": (
                "Partition the supplied visible text in reading order. Each part labels "
                "one consecutive substring; together they account for the original text "
                "once, without overlap or reordering. Semantic boundaries may fall inside "
                "unbroken text. This is source annotation, not before/after edits."
            ),
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Exact consecutive text copied from the supplied entry or "
                            "range, preserving punctuation and internal whitespace. "
                            "Include text to be cleaned as its own part; do not rewrite "
                            "the source or add a new placeholder."
                        ),
                    },
                    "role": {
                        "type": "string",
                        "enum": list(ORDERED_SEMANTIC_PART_ROLES),
                        "description": (
                            "Responsibility of this exact text. A fill_slot is the text "
                            "to replace with a field value, including a prompt or example "
                            "occupying that value's position. style_only describes a "
                            "formatting requirement, not an example field value."
                        ),
                    },
                    "field_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Field from the supplied vocabulary whose meaning and "
                            "allowed role match the responsibility this part carries "
                            "in context. A fill_slot binds the value replacing this "
                            "exact part. "
                            "Only for fill_slot, body_structure or generated_content."
                        ),
                    },
                },
                "required": ["text", "role"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string"},
        "open_questions": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": ["parts"],
    "oneOf": [
        {"required": ["source_entry_id"]},
        {"required": ["scope"]},
    ],
    "additionalProperties": False,
}

_ORDERED_SEMANTIC_JUDGMENTS_SCHEMA: JsonObject = {
    "type": "array",
    "items": _ORDERED_SEMANTIC_JUDGMENT_SCHEMA,
}

PREPARE_TEMPLATE_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["complete", "needs_input"]},
        "summary": {"type": "string", "minLength": 1},
        "needs_input": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "semantic_judgments": _ORDERED_SEMANTIC_JUDGMENTS_SCHEMA,
    },
    "required": ["status", "summary", "semantic_judgments"],
    "additionalProperties": False,
}

POST_UNIT_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        key: PREPARE_TEMPLATE_OUTPUT_SCHEMA["properties"][key]
        for key in ("status", "summary", "needs_input", "semantic_judgments")
    },
    "required": ["status", "summary", "semantic_judgments"],
    "additionalProperties": False,
}

UNIT_BOUNDARY_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["complete", "needs_input"]},
        "summary": {"type": "string", "minLength": 1},
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "string", "minLength": 1},
                    "unit_name": {"type": "string", "minLength": 1},
                    "start_boundary": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer", "minimum": 1},
                            "region": {"type": "string"},
                            "seen_text": {"type": "string", "minLength": 1},
                        },
                        "required": ["seen_text"],
                        "additionalProperties": False,
                    },
                    "end_boundary": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer", "minimum": 1},
                            "region": {"type": "string"},
                            "seen_text": {"type": "string", "minLength": 1},
                        },
                        "required": ["seen_text"],
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "unit_id",
                    "unit_name",
                    "start_boundary",
                    "end_boundary",
                ],
                "additionalProperties": False,
            },
        },
        "needs_input": {
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
    until_stage: Literal["unit-boundary", "post-unit"] | None = None
    from_stage: Literal["unit-boundary"] | None = None
    resume_proof: Path | None = None
    force_rebuild_checkpoint: Literal["unit-boundary"] | None = None


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
    sdk_query_count: int = 1
    harness_feedback_attempts: int = 0
    semantic_feedback_attempts: int = 0
    permission_events: tuple[JsonObject, ...] = ()
    unit_boundary_checkpoint: JsonObject | None = None
    sdk_events: tuple[JsonObject, ...] = ()
    timing_events: tuple[JsonObject, ...] = ()


@dataclass(frozen=True, slots=True)
class PrepareTemplateReport:
    status: Literal["built", "checkpointed"]
    task_root: str
    artifact_path: str | None
    fill_contract_path: str | None
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


def _failure_evidence(error: BaseException) -> JsonObject:
    if isinstance(error, ToolFailure):
        return {
            "status": error.status,
            "origin": error.origin,
            "code": error.code,
            "retryable": error.retryable,
            "message": error.message,
            "suggested_actions": list(error.suggested_actions),
        }
    if isinstance(error, TimeoutError):
        return {
            "status": "error",
            "origin": "agent",
            "code": "template_agent_timeout",
            "retryable": True,
            "message": "The main Agent loop exceeded the configured template timeout.",
            "suggested_actions": ["resume_or_rerun_with_existing_task_root"],
        }
    return {
        "status": "error",
        "origin": "application",
        "code": error.__class__.__name__,
        "retryable": False,
        "message": str(error),
        "suggested_actions": [],
    }


def _agent_no_progress_timeout_failure(*, seconds: float) -> ToolFailure:
    timeout = max(0, round(seconds, 3))
    return ToolFailure(
        status="error",
        origin="agent",
        code="template_agent_no_progress_timeout",
        message=(
            "The Agent stream did not produce a tool call or structured result "
            f"within {timeout:g} seconds."
        ),
        retryable=True,
        suggested_actions=(
            "inspect_template_agent_execution_trace",
            "resume_or_rerun_with_existing_task_root",
        ),
    )


def _permission_event_payload(event: PermissionAuditEvent) -> JsonObject:
    payload: JsonObject = {
        "tool_name": event.tool_name,
        "decision": event.decision,
        "reason_code": event.reason_code,
    }
    optional: tuple[tuple[str, object | None], ...] = (
        ("subagent_type", event.subagent_type),
        ("tool_use_id", event.tool_use_id),
        ("agent_id", event.agent_id),
        ("question_count", event.question_count),
        ("option_count", event.option_count),
        ("answered", event.answered),
        ("duration_ms", event.duration_ms),
        ("input_summary", event.input_summary),
    )
    for key, value in optional:
        if value is not None:
            payload[key] = value
    return payload


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _start_timing_event(
    timing_events: list[JsonObject],
    *,
    started: float,
    stage: str,
    operation: str,
    **metadata: object,
) -> JsonObject:
    event: JsonObject = {
        "schema_version": "docfit-timing-event/v1",
        "stage": stage,
        "operation": operation,
        "started_elapsed_ms": _elapsed_ms(started),
        "started_unix_ms": time.time_ns() // 1_000_000,
    }
    for key, value in metadata.items():
        if value is not None:
            event[key] = value
    timing_events.append(event)
    return event


def _finish_timing_event(
    event: JsonObject,
    *,
    started: float,
    status: str,
    **metadata: object,
) -> None:
    ended_elapsed_ms = _elapsed_ms(started)
    event["ended_elapsed_ms"] = ended_elapsed_ms
    event["ended_unix_ms"] = time.time_ns() // 1_000_000
    event["duration_ms"] = max(
        0,
        ended_elapsed_ms - int(event.get("started_elapsed_ms", ended_elapsed_ms)),
    )
    event["status"] = status
    for key, value in metadata.items():
        if value is not None:
            event[key] = value


def _timing_summary(timing_events: tuple[JsonObject, ...] | list[JsonObject]) -> JsonObject:
    summary: JsonObject = {
        "schema_version": "docfit-timing-summary/v1",
        "event_count": 0,
        "by_operation": {},
        "by_stage": {},
    }
    by_operation: dict[str, JsonObject] = {}
    by_stage: dict[str, JsonObject] = {}
    for event in timing_events:
        if not isinstance(event, dict):
            continue
        duration = event.get("duration_ms")
        if not isinstance(duration, int):
            continue
        summary["event_count"] = int(summary["event_count"]) + 1
        operation = str(event.get("operation", "unknown"))
        stage = str(event.get("stage", "unknown"))
        operation_bucket = by_operation.setdefault(
            operation,
            {"count": 0, "duration_ms": 0},
        )
        operation_bucket["count"] = int(operation_bucket["count"]) + 1
        operation_bucket["duration_ms"] = int(operation_bucket["duration_ms"]) + duration
        stage_bucket = by_stage.setdefault(stage, {"count": 0, "duration_ms": 0})
        stage_bucket["count"] = int(stage_bucket["count"]) + 1
        stage_bucket["duration_ms"] = int(stage_bucket["duration_ms"]) + duration
    summary["by_operation"] = by_operation
    summary["by_stage"] = by_stage
    return summary


def _sdk_has_generation_progress(message: object) -> bool:
    """Count generated content as activity without retaining its contents."""
    if not isinstance(message, StreamEvent):
        return False
    if message.event.get("type") != "content_block_delta":
        return False
    delta = message.event.get("delta")
    if not isinstance(delta, dict):
        return False
    delta_type = delta.get("type")
    if not isinstance(delta_type, str):
        return False
    payload_key = {
        "thinking_delta": "thinking",
        "text_delta": "text",
        "input_json_delta": "partial_json",
    }.get(delta_type)
    payload = delta.get(payload_key) if payload_key is not None else None
    return isinstance(payload, str) and bool(payload)


def _sdk_receive_event(
    message: object,
    *,
    elapsed_ms: int,
    stage: str | None = None,
    query_index: int | None = None,
    stage_query_index: int | None = None,
) -> JsonObject:
    event: JsonObject = {
        "message_type": message.__class__.__name__,
        "elapsed_ms": elapsed_ms,
    }
    if stage is not None:
        event["stage"] = stage
    if query_index is not None:
        event["query_index"] = query_index
    if stage_query_index is not None:
        event["stage_query_index"] = stage_query_index
    subtype = getattr(message, "subtype", None)
    if isinstance(subtype, str) and subtype:
        event["subtype"] = subtype
    data = getattr(message, "data", None)
    if isinstance(data, dict):
        event["data_keys"] = sorted(str(key) for key in data)
        for key in ("status", "task_type", "last_tool_name", "terminal_reason"):
            value = data.get(key)
            if isinstance(value, str) and value:
                event[key] = value
    if isinstance(message, AssistantMessage):
        content = list(message.content)
        event["content_block_types"] = [block.__class__.__name__ for block in content]
        tool_uses = [block.name for block in content if isinstance(block, ToolUseBlock)]
        if tool_uses:
            event["tool_uses"] = tool_uses
    if isinstance(message, StreamEvent):
        event["stream_event_type"] = message.event.get("type")
        delta = message.event.get("delta")
        if isinstance(delta, dict):
            event["delta_type"] = delta.get("type")
    if isinstance(message, ResultMessage):
        event["is_error"] = message.is_error
        event["has_structured_output"] = isinstance(message.structured_output, dict)
        if isinstance(message.structured_output, dict):
            status = message.structured_output.get("status")
            if isinstance(status, str):
                event["structured_status"] = status
    return event


def _write_agent_trace(
    prepared: PreparedTemplateTask,
    *,
    execution: TemplateAgentExecution | None = None,
    backend: str | None = None,
    session_id: str = "",
    tool_uses: tuple[str, ...] = (),
    skills_loaded: tuple[str, ...] = (),
    structured_output: JsonObject | None = None,
    wall_duration_ms: int = 0,
    publication: JsonObject | None = None,
    failure: JsonObject | None = None,
    sdk_query_count: int = 1,
    harness_feedback_attempts: int = 0,
    semantic_feedback_attempts: int = 0,
    permission_events: tuple[JsonObject, ...] = (),
    unit_boundary_checkpoint: JsonObject | None = None,
    sdk_events: tuple[JsonObject, ...] = (),
    timing_events: tuple[JsonObject, ...] = (),
) -> None:
    effective_timing_events = (
        timing_events
        if timing_events
        else execution.timing_events
        if execution is not None
        else ()
    )
    trace: JsonObject = {
        "schema_version": 1,
        "architecture": "main_agent_full_context/v1",
        "sdk_query_count": (
            execution.sdk_query_count if execution is not None else sdk_query_count
        ),
        "harness_feedback_attempts": (
            execution.harness_feedback_attempts
            if execution is not None
            else harness_feedback_attempts
        ),
        "semantic_feedback_attempts": (
            execution.semantic_feedback_attempts
            if execution is not None
            else semantic_feedback_attempts
        ),
        "application_semantic_work_items": 0,
        "status": "failed" if failure is not None else "complete",
        "backend": backend or (execution.backend if execution is not None else ""),
        "session_id": session_id or (execution.session_id if execution is not None else ""),
        "num_turns": execution.num_turns if execution is not None else 0,
        "duration_ms": execution.duration_ms if execution is not None else 0,
        "duration_api_ms": execution.duration_api_ms if execution is not None else 0,
        "wall_duration_ms": (
            execution.wall_duration_ms if execution is not None else wall_duration_ms
        ),
        "tool_uses": list(execution.tool_uses if execution is not None else tool_uses),
        "skills_loaded": list(execution.skills_loaded if execution is not None else skills_loaded),
        "permission_events": list(
            execution.permission_events if execution is not None else permission_events
        ),
        "sdk_events": list(execution.sdk_events if execution is not None else sdk_events),
        "timing_events": list(effective_timing_events),
        "timing_summary": _timing_summary(effective_timing_events),
        "agent_completion": (
            execution.structured_output
            if execution is not None
            else structured_output
            if structured_output is not None
            else {}
        ),
    }
    checkpoint = (
        execution.unit_boundary_checkpoint if execution is not None else unit_boundary_checkpoint
    )
    if checkpoint is not None:
        trace["unit_boundary_checkpoint"] = checkpoint
    if publication is not None:
        trace["publication"] = publication
    if failure is not None:
        trace["failure"] = failure
    atomic_write_json(prepared.task_root / _TRACE, trace)


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
        "output_boundary": [
            "output/final-template.docx",
            "output/fill-contract.yaml",
        ],
        "harness": {
            "agent_visible_tool": False,
            "object_inventory": "work/.docfit/harness/object-inventory.json",
            "semantic_judgments": "work/.docfit/harness/semantic-judgments.json",
        },
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
    output_contract = task_root / "output/fill-contract.yaml"
    output_directory = task_root / "output"
    if output_directory.exists():
        if output_directory.is_symlink() or not output_directory.is_dir():
            raise _failure(
                "prepare_checkpoint_invalid",
                "The output boundary must be a regular directory.",
            )
        output_entries = sorted(output_directory.iterdir())
    else:
        output_directory.mkdir()
        output_entries = []
    expected_outputs = sorted((output, output_contract))
    if output_entries and (
        output_entries != expected_outputs
        or output.is_symlink()
        or not output.is_file()
        or output_contract.is_symlink()
        or not output_contract.is_file()
    ):
        raise _failure(
            "prepare_checkpoint_invalid",
            "The output directory may contain only the published Word/Fill Contract pair.",
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


def _validate_stage_request(request: PrepareTemplateRequest) -> None:
    if request.until_stage not in (None, _UNIT_BOUNDARY_STAGE, _POST_UNIT_STAGE):
        raise _failure(
            "prepare_stage_invalid",
            f"until_stage supports only {_UNIT_BOUNDARY_STAGE} or {_POST_UNIT_STAGE}.",
        )
    if request.from_stage not in (None, _UNIT_BOUNDARY_STAGE):
        raise _failure(
            "prepare_stage_invalid",
            f"from_stage supports only {_UNIT_BOUNDARY_STAGE}.",
        )
    if request.force_rebuild_checkpoint not in (None, _UNIT_BOUNDARY_STAGE):
        raise _failure(
            "prepare_stage_invalid",
            f"force_rebuild_checkpoint supports only {_UNIT_BOUNDARY_STAGE}.",
        )
    if request.until_stage == _UNIT_BOUNDARY_STAGE and (
        request.from_stage is not None or request.resume_proof is not None
    ):
        raise _failure(
            "prepare_stage_invalid",
            "--until unit-boundary cannot be combined with --from or --resume-proof.",
        )
    if request.force_rebuild_checkpoint is not None and (
        request.from_stage is not None or request.resume_proof is not None
    ):
        raise _failure(
            "prepare_stage_invalid",
            "--force-rebuild-checkpoint cannot be combined with stage resume.",
        )


def _checkpoint_file(prepared: PreparedTemplateTask, proof: Path | None = None) -> Path:
    if proof is None:
        return prepared.task_root / _UNIT_BOUNDARY_CHECKPOINT
    expanded = proof.expanduser()
    return expanded if expanded.is_absolute() else prepared.task_root / expanded


def _load_unit_boundary_checkpoint(
    prepared: PreparedTemplateTask,
    proof: Path | None = None,
) -> JsonObject:
    path = _checkpoint_file(prepared, proof)
    if path.is_symlink() or not path.is_file():
        raise _failure(
            "unit_boundary_proof_missing",
            "Unit-boundary resume proof is missing or not a regular file.",
        )
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _failure(
            "unit_boundary_proof_invalid",
            "Unit-boundary resume proof is not readable JSON.",
        ) from error
    if not isinstance(payload, dict):
        raise _failure(
            "unit_boundary_proof_invalid",
            "Unit-boundary resume proof must be one JSON object.",
        )
    return _validate_unit_boundary_checkpoint(prepared, payload)


def _validate_unit_boundary_checkpoint(
    prepared: PreparedTemplateTask,
    checkpoint: JsonObject,
) -> JsonObject:
    schema_version = checkpoint.get("schema_version")
    if schema_version not in (1, "docfit-unit-boundary-proof/v1"):
        raise _failure(
            "unit_boundary_proof_invalid",
            "Unit-boundary proof schema_version is unsupported.",
        )
    if checkpoint.get("status") != "ok":
        raise _failure(
            "unit_boundary_proof_invalid",
            "Unit-boundary proof status must be ok before resume.",
        )
    if checkpoint.get("source_hash") != prepared.template_sha256:
        raise _failure(
            "unit_boundary_proof_source_mismatch",
            "Unit-boundary proof source_hash does not match the prepared source.",
        )
    units_value = checkpoint.get("resolved_units")
    if not isinstance(units_value, list) or not units_value:
        raise _failure(
            "unit_boundary_proof_invalid",
            "Unit-boundary proof must include non-empty Host-resolved resolved_units.",
        )
    unit_ids = [
        str(item.get("unit_id"))
        for item in units_value
        if isinstance(item, dict) and isinstance(item.get("unit_id"), str)
    ]
    if len(unit_ids) != len(units_value) or len(set(unit_ids)) != len(unit_ids):
        raise _failure(
            "unit_boundary_proof_invalid",
            "Unit-boundary proof units must have unique unit_id values.",
        )
    try:
        result = DocFitToolService(task_root=prepared.task_root).check(
            {
                "schema_version": "docfit_check_input_v1",
                "check": "unit_coverage",
                "payload": {"units": units_value},
            }
        )
    except ToolFailure as error:
        result = error.result()
    if result.get("status") != "ok":
        failure = result.get("failure", {})
        suggested_actions = (
            failure.get("suggested_actions", []) if isinstance(failure, dict) else []
        )
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unit_boundary_proof_invalid",
            message="Unit-boundary proof no longer passes Harness unit coverage.",
            suggested_actions=tuple(str(item) for item in suggested_actions),
        )
    normalized = dict(checkpoint)
    normalized["schema_version"] = checkpoint.get("schema_version")
    normalized["status"] = "ok"
    normalized["source_hash"] = prepared.template_sha256
    normalized["checkpoint"] = _UNIT_BOUNDARY_STAGE
    normalized["unit_count"] = int(result.get("unit_count", len(units_value)))
    resolved_units = result.get("resolved_units")
    if not isinstance(resolved_units, list) or not resolved_units:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unit_boundary_proof_invalid",
            message=(
                "Unit-boundary proof validation must return non-empty Host-resolved "
                "resolved_units."
            ),
            suggested_actions=(
                "Re-run unit-boundary validation with the current Harness contract.",
            ),
        )
    normalized["resolved_units"] = resolved_units
    return normalized


def _unit_boundary_checkpoint_report(
    prepared: PreparedTemplateTask,
    checkpoint: JsonObject,
) -> PrepareTemplateReport:
    return PrepareTemplateReport(
        status="checkpointed",
        task_root=str(prepared.task_root),
        artifact_path=None,
        fill_contract_path=None,
        template_sha256=prepared.template_sha256,
        counts={
            "checkpoint": _UNIT_BOUNDARY_STAGE,
            "unit_count": int(checkpoint.get("unit_count", 0)),
        },
        backend=str(checkpoint.get("backend", "checkpoint")),
        session_id=str(checkpoint.get("session_id", "")),
        tool_uses=tuple(
            str(item) for item in checkpoint.get("tool_uses", []) if isinstance(item, str)
        ),
        skills_loaded=tuple(
            str(item) for item in checkpoint.get("skills_loaded", []) if isinstance(item, str)
        ),
        num_turns=0,
        duration_ms=0,
        duration_api_ms=0,
        session_count=1,
        client_count=1,
        wall_duration_ms=int(checkpoint.get("wall_duration_ms", 0)),
    )


def _post_unit_checkpoint_report(
    prepared: PreparedTemplateTask,
    execution: TemplateAgentExecution,
) -> PrepareTemplateReport:
    output = execution.structured_output
    if output.get("status") != "complete":
        needs = output.get("needs_input", [])
        raise _failure(
            "post_unit_agent_needs_input",
            f"The post-unit Agent needs additional semantic input: {needs}",
            origin="agent",
        )
    semantic_feedback = _semantic_coverage_feedback(prepared, output)
    if semantic_feedback is not None:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_semantic_coverage_incomplete",
            message="Post-unit semantic judgments did not pass Harness phase review.",
            suggested_actions=_semantic_feedback_failure_actions(semantic_feedback),
        )
    readiness_feedback = _materialization_readiness_feedback_for_complete_output(prepared)
    if readiness_feedback is not None:
        _raise_materialization_readiness_feedback(prepared, readiness_feedback)
    try:
        inventory = json.loads(
            (prepared.task_root / "work/.docfit/harness/object-inventory.json").read_text(
                encoding="utf-8"
            )
        )
        judgments = json.loads(
            (prepared.task_root / "work/.docfit/harness/semantic-judgments.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="post_unit_checkpoint_missing",
            message="Harness accepted post-unit semantics but did not persist checkpoint evidence.",
        ) from error
    if not isinstance(inventory, dict) or not isinstance(judgments, dict):
        _raise_accepted_harness_semantics_invalid()
    if not _accepted_harness_semantics_current(
        prepared=prepared,
        inventory=inventory,
        review=judgments,
    ):
        _raise_accepted_harness_semantics_invalid()
    counts: JsonObject = {
        "checkpoint": _POST_UNIT_STAGE,
        "object_count": int(inventory.get("object_count", 0)) if isinstance(inventory, dict) else 0,
        "reading_block_count": int(inventory.get("reading_block_count", 0))
        if isinstance(inventory, dict)
        else 0,
        "judgment_count": int(judgments.get("judgment_count", 0))
        if isinstance(judgments, dict)
        else 0,
        "covered_object_count": int(judgments.get("covered_object_count", 0))
        if isinstance(judgments, dict)
        else 0,
    }
    field_vocabulary_digest = None
    if isinstance(judgments, dict) and isinstance(judgments.get("field_vocabulary_digest"), str):
        field_vocabulary_digest = judgments["field_vocabulary_digest"]
    elif isinstance(inventory, dict) and isinstance(inventory.get("field_vocabulary_digest"), str):
        field_vocabulary_digest = inventory["field_vocabulary_digest"]
    checkpoint: JsonObject = {
        "schema_version": "docfit-post-unit-proof/v1",
        "checkpoint": _POST_UNIT_STAGE,
        "status": "ok",
        "source_hash": prepared.template_sha256,
        "unit_boundary_checkpoint": _UNIT_BOUNDARY_CHECKPOINT,
        "object_inventory": "work/.docfit/harness/object-inventory.json",
        "semantic_judgments": "work/.docfit/harness/semantic-judgments.json",
        "semantic_judgments_sha256": judgments.get("semantic_judgments_sha256")
        if isinstance(judgments, dict)
        else None,
        "summary": str(output.get("summary", "")),
        **counts,
        "backend": execution.backend,
        "session_id": execution.session_id,
        "tool_uses": list(execution.tool_uses),
        "skills_loaded": list(execution.skills_loaded),
        "sdk_query_count": execution.sdk_query_count,
        "harness_feedback_attempts": execution.harness_feedback_attempts,
        "semantic_feedback_attempts": execution.semantic_feedback_attempts,
        "wall_duration_ms": execution.wall_duration_ms,
        "timing_events": list(execution.timing_events),
        "timing_summary": _timing_summary(execution.timing_events),
    }
    if field_vocabulary_digest is not None:
        checkpoint["field_vocabulary_digest"] = field_vocabulary_digest
    atomic_write_json(prepared.task_root / _POST_UNIT_CHECKPOINT, checkpoint)
    return PrepareTemplateReport(
        status="checkpointed",
        task_root=str(prepared.task_root),
        artifact_path=None,
        fill_contract_path=None,
        template_sha256=prepared.template_sha256,
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


_UNIT_CONTEXT_KEYS = (
    "unit_id",
    "unit_name",
    "boundary_kind",
    "responsibility",
    "style_anchor",
    "notes",
)

_SPECIAL_UNIT_REFERENCE_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "generated-content-and-toc.md",
        (
            "目录",
            "toc",
            "contents",
            "图目录",
            "表目录",
            "清单",
            "题注",
            "caption",
            "编号",
            "交叉引用",
            "字段缓存",
        ),
    ),
    (
        "body-structure.md",
        (
            "正文",
            "body",
            "章节",
            "chapter",
            "paper body",
            "论文正文",
            "正文样本",
            "正文结构",
            "图表公式列表",
            "outline",
        ),
    ),
    (
        "collections-and-optional-sections.md",
        (
            "任务书",
            "开题",
            "评阅",
            "答辩",
            "成绩",
            "审批",
            "proposal",
            "review",
            "approval",
            "form",
        ),
    ),
)


def _unit_boundary_prompt_context(unit_boundary_checkpoint: JsonObject) -> list[JsonObject]:
    raw_units = unit_boundary_checkpoint.get("resolved_units")
    if not isinstance(raw_units, list):
        return []
    context: list[JsonObject] = []
    for raw_unit in raw_units:
        if not isinstance(raw_unit, dict):
            continue
        compact = {
            key: raw_unit[key]
            for key in _UNIT_CONTEXT_KEYS
            if isinstance(raw_unit.get(key), str) and str(raw_unit[key]).strip()
        }
        if compact:
            context.append(compact)
    return context


def _markdown_subsection(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    lines: list[str] = []
    for line in text[start:].splitlines():
        if lines and (line.startswith("## ") or line.startswith("### ")):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _special_unit_reference_context(unit_boundary_checkpoint: JsonObject) -> str:
    units = _unit_boundary_prompt_context(unit_boundary_checkpoint)
    if not units:
        return ""
    searchable_unit_text = " ".join(
        str(value)
        for unit in units
        for value in unit.values()
        if isinstance(value, str)
    ).casefold()
    reference_names: list[str] = []
    for reference_name, keywords in _SPECIAL_UNIT_REFERENCE_ROUTES:
        if any(keyword.casefold() in searchable_unit_text for keyword in keywords):
            reference_names.append(reference_name)
    if not reference_names:
        return ""
    reference_root = (
        project_root() / ".claude/skills/docfit-school-extract/references"
    )
    excerpts: list[str] = []
    for reference_name in dict.fromkeys(reference_names):
        reference_path = reference_root / reference_name
        if not reference_path.is_file():
            continue
        reference_text = reference_path.read_text(encoding="utf-8")
        headings = ["### 快速路由摘要"]
        if reference_name == "generated-content-and-toc.md":
            headings.append("### 目录输出结构")
        sections = [
            section
            for heading in headings
            if (section := _markdown_subsection(reference_text, heading))
        ]
        if sections:
            excerpts.append(f"references/{reference_name}\n" + "\n\n".join(sections))
    if not excerpts:
        return ""
    return (
        "Special unit Reference context selected from resolved_units. These notes are "
        "Agent-facing school-semantic knowledge, not mechanical authority. Use them "
        "before local reading_block/range_id judgments; generic text classification is "
        "only an initial semantic aid and cannot replace the selected Reference or "
        "field_id_vocabulary.\n"
        + "\n\n".join(excerpts)
        + "\n"
    )


def build_prepare_template_prompt(
    prepared: PreparedTemplateTask,
    unit_boundary_checkpoint: JsonObject | None = None,
    *,
    stop_after_post_unit: bool = False,
) -> str:
    requirements = (
        str(prepared.requirements_path)
        if prepared.requirements_path is not None
        else "none supplied"
    )
    checkpoint_note = ""
    if unit_boundary_checkpoint is not None:
        checkpoint_summary = {
            "checkpoint_ref": _UNIT_BOUNDARY_CHECKPOINT,
            "status": unit_boundary_checkpoint.get("status"),
            "summary": unit_boundary_checkpoint.get("summary"),
            "unit_count": unit_boundary_checkpoint.get("unit_count"),
            "resolved_units": _unit_boundary_prompt_context(unit_boundary_checkpoint),
        }
        checkpoint_note = (
            "Runtime unit-boundary checkpoint already passed before this main flow. "
            "Harness, not the Agent, accepted mechanical boundary closure. "
            f"Checkpoint: {json.dumps(checkpoint_summary, ensure_ascii=False, sort_keys=True)} "
            "Use it as accepted boundary context; do not re-litigate unit boundaries unless "
            "Harness invalidates the checkpoint. "
            f"{_special_unit_reference_context(unit_boundary_checkpoint)}"
            "Begin post-unit semantic judgment; do not start from final artifact or delivery "
            "review. Do not call boundary-closure checks or split units again while "
            "the runtime keeps the checkpoint valid. For each accepted unit, first decide "
            "whether a whole-unit semantic_judgment can close that school function area. "
            "Terminal examples include fixed declarations, manual signature/date pages, "
            "task/proposal forms, and school review or approval forms. Directory/list "
            "units are generated "
            "areas rather than unit-layer terminal keeps; judge their TOC/list mechanism, "
            "source title families, and inclusion depth as generated reading_block/range_id "
            "semantics, not by decomposing old cache rows as content. Generated content "
            "and body structure fields must be chosen from the pre-input "
            "field_id_vocabulary in the unit packet and must match each field's "
            "usage_affordance.allowed_part_roles; if the required field is absent, "
            "return needs_input instead of querying or inventing a field. When a whole-unit "
            "judgment is terminal, do not decompose the unit just to bind fields or inspect "
            "styles. For task/proposal terminal forms, keep form notes, usage notes, "
            "blank fill areas, signature/date areas, and label cells inside the same "
            "terminal keep judgment; do not split form notes into template-note deletion "
            "only to satisfy block ownership. If the unit is not terminal, call "
            "docfit_evidence with "
            "focus=unit_evidence_packet and unit_id; this returns an Agent-readable unit "
            "source entry packet with field_id_vocabulary, source_entries[].source_entry_id, "
            "source_entries[].text, reading_blocks as view context, block-local range_id, "
            "summary.reading_ranges[].range_id for whole-unit ranges, and visible text, "
            "not a bottom-layer object dump. For each local source entry, block, or listed "
            "range, output source_entry_id plus ordered parts. Use the whole-unit range "
            "when one semantic judgment must cover multiple reading blocks in document "
            "order. Fill-slot, "
            "body-structure, and generated-content "
            "parts carry field_id only when the value was present in "
            "field_id_vocabulary.allowed_field_ids and that field's "
            "usage_affordance.allowed_part_roles includes the chosen part role; other "
            "parts carry no field_id. Style "
            "context is needed only when slot/style inheritance is unclear. Terminal "
            "whole-unit keeps, generated TOC/list judgments, fixed keeps, "
            "template-note deletions, and no-op "
            "layout do not need field IDs or style context. Build one semantic_judgments "
            "set whose entries each use source_entry_id and ordered parts, with legacy "
            "scope only for compatibility view ranges, plus reason or blocking open "
            "questions when needed. "
            "Do not build per-object mechanical gate payloads or manually check each "
            "judgment before stage submission; Harness reviews the completed judgment set "
            "at the phase boundary and returns affected scopes if revision is needed. "
            "Do not call write, render, visual review, or delivery tools; submit only the "
            "semantic_judgments set for host review. "
        )
    completion_note = (
        "This run stops at the post-unit checkpoint. This is a single post-unit "
        "semantic judgment transaction: use the accepted unit context, read "
        "unit_evidence_packet for non-terminal units, choose field IDs only from "
        "the packet's field_id_vocabulary, then return status=complete with "
        "semantic_judgments or status=needs_input; do not delegate, ask the user, "
        "glob, grep, or keep exploring after the unit evidence is sufficient. "
        "Return complete once semantic_judgments are ready for Harness phase review "
        "or have been accepted; "
        "do not produce final output paths, review handles, page-review lists, "
        "or validation findings in this run. The runtime will materialize and visually "
        "validate the clean template in a later stage."
        if stop_after_post_unit
        else (
            "Return complete once semantic_judgments are ready for Harness phase review or "
            "have been accepted. Do not produce final output paths, candidate paths, render "
            "handles, page-review lists, validation findings, acceptance artifacts, or delivery "
            "decisions. After Harness accepts the semantic set, App/Harness code owns "
            "deterministic materialization, validation, artifact delivery, and any related "
            "blocking errors. If the current semantic decision lacks necessary readable "
            "school context, return needs_input with needs_input[] naming only the missing "
            "input that would change the semantic result."
        )
    )
    return (
        "DocFit template extraction startup brief v1. Load the docfit-school-extract Skill. "
        "System goal: prepare one clean, reusable, fillable school thesis template. "
        "Agent responsibility: return only school-template semantic judgments; host "
        "runtime owns final Word and Fill Contract materialization. "
        "Runtime-bound source identities are tracked by Harness/session, not by Agent Tool "
        "parameters. "
        f"school_template={prepared.template_path} role=school_template "
        f"trust={UNTRUSTED_SOURCE_DATA_LABEL}; "
        f"school_requirements={requirements} role=school_requirements "
        f"trust={UNTRUSTED_SOURCE_DATA_LABEL if prepared.requirements_path else 'not_supplied'}; "
        f"field_registry={prepared.registry_source} role=field_registry. "
        "Use role/path/context handles for reasoning; do not copy, compare, or choose "
        "between low-level asset identities. "
        "This brief contains handles only, not raw OOXML or a full inventory dump. "
        "Use docfit_evidence only for bounded readable context; do not use per-object "
        "mechanical checks as a workflow. Read only supplied textual requirements, "
        "Registry, and Skill references; never Read/Grep Word packages directly. "
        "Return semantic_judgments in the structured output. Each new judgment names "
        "source_entry_id from source_entries and an ordered parts array over that entry's "
        "visible text. Legacy scope reading_block_id or reading_range_id is accepted only "
        "as a compatibility view token when a single source entry cannot express the "
        "range. Use only reading_range_id tokens listed in the unit evidence packet, "
        "including summary.reading_ranges[].range_id for whole-unit scope. Do not invent "
        "source entry IDs, low-level document positions, spans, slots, or snapshot "
        "identities. The host runtime maps source-entry semantic spans to document "
        "objects and may feed back missing, overlapping, malformed, or stale source "
        "entries or spans in the same SDK session. "
        + "Never modify input/, never write output/, and do not select or name final candidate "
        "documents. Tool feedback is mechanical repair context, not semantic authority. "
        f"{checkpoint_note}"
        f"{completion_note}"
    )


def build_prepare_template_options(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    permission_audit: Callable[[PermissionAuditEvent], None] | None = None,
    *,
    stop_after_post_unit: bool = False,
) -> ClaudeAgentOptions:
    root = project_root()
    policy = build_read_path_policy(project=root, cwd=root, task_root=prepared.task_root)
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)
    transaction_scope = "checkpoint" if stop_after_post_unit else "stage"
    return ClaudeAgentOptions(
        tools=["Skill", "Read"],
        allowed_tools=[],
        disallowed_tools=[
            *FORBIDDEN_TOOLS,
            "Bash",
            "Write",
            "Agent",
            "AskUserQuestion",
            "Glob",
            "Grep",
        ],
        mcp_servers={
            MCP_SERVER_NAME: build_docfit_server(
                prepared.task_root,
                include_docx_tools=False,
                template_semantic_only=True,
            )
        },
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=make_permission_callback(
            terminal_ask_user,
            read_path_policy=policy,
            registered_tool_names=(f"mcp__{MCP_SERVER_NAME}__{DOCFIT_EVIDENCE_TOOL}",),
            trusted_basic_tools=(),
            audit=permission_audit,
        ),
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher="mcp__docfit__.*",
                    hooks=[make_docfit_schema_version_hook()],
                ),
                HookMatcher(
                    matcher="Read",
                    hooks=[make_read_path_gate_hook(policy, permission_audit)],
                ),
            ]
        },
        setting_sources=["project"],
        skills=["docfit-school-extract"],
        cwd=root,
        env=environment,
        model=backend.model,
        max_turns=POST_UNIT_MAX_TURNS,
        thinking={"type": "adaptive"},
        include_partial_messages=True,
        effort="low",
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={"type": "json_schema", "schema": POST_UNIT_OUTPUT_SCHEMA},
        system_prompt=(
            "You are DocFit's post-unit school-template semantic judgment Agent. "
            f"This run is a bounded semantic-output {transaction_scope} over accepted units. "
            "Use unit_evidence_packet source_entries for bounded source text and choose "
            "field IDs only from its field_id_vocabulary, then return semantic_judgments. Runtime "
            "Harness checks completeness, vocabulary provenance, field existence, "
            "and mechanical closure at the phase boundary. Do not delegate, ask the "
            "user, perform DOCX materialization, render, visually review, or deliver "
            "artifacts in this run."
        ),
    )


def build_unit_boundary_checkpoint_options(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    permission_audit: Callable[[PermissionAuditEvent], None] | None = None,
) -> ClaudeAgentOptions:
    root = project_root()
    policy = build_read_path_policy(project=root, cwd=root, task_root=prepared.task_root)
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)
    return ClaudeAgentOptions(
        tools=["Skill", "Read"],
        allowed_tools=[],
        disallowed_tools=[*FORBIDDEN_TOOLS, "Bash", "Write", "Agent", "AskUserQuestion"],
        mcp_servers={
            MCP_SERVER_NAME: build_docfit_server(
                prepared.task_root,
                include_docx_tools=False,
                template_semantic_only=True,
            )
        },
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=make_permission_callback(
            terminal_ask_user,
            read_path_policy=policy,
            registered_tool_names=(f"mcp__{MCP_SERVER_NAME}__{DOCFIT_EVIDENCE_TOOL}",),
            trusted_basic_tools=(),
            audit=permission_audit,
        ),
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher="mcp__docfit__.*",
                    hooks=[make_docfit_schema_version_hook()],
                ),
                HookMatcher(
                    matcher="Read",
                    hooks=[make_read_path_gate_hook(policy, permission_audit)],
                ),
            ]
        },
        setting_sources=["project"],
        skills=["docfit-school-extract"],
        cwd=root,
        env=environment,
        model=backend.model,
        max_turns=min(PREPARE_TEMPLATE_MAX_TURNS, 20),
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={"type": "json_schema", "schema": UNIT_BOUNDARY_OUTPUT_SCHEMA},
        system_prompt=(
            "You are DocFit's runtime unit-boundary checkpoint Agent. Your only job is to "
            "propose structural school-template units from readable source context. The "
            "host Harness mechanically validates boundary closure before the main "
            "preparation flow. "
            "Do not provide low-level runtime identifiers, write outputs, or final "
            "template completion."
        ),
    )


def _source_noop_publishability(prepared: PreparedTemplateTask) -> JsonObject:
    return publication_slot_protocol_status(
        candidate_docx=prepared.template_path,
        registry=FieldRegistrySnapshot.load(prepared.registry_source),
    )


def _read_json_object(path: Path, *, code: str, message: str) -> JsonObject:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code=code,
            message=message,
            retryable=True,
        ) from error
    if not isinstance(payload, dict):
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code=code,
            message=message,
            retryable=True,
        )
    return payload


def _accepted_harness_semantics_current(
    *,
    prepared: PreparedTemplateTask,
    inventory: JsonObject,
    review: JsonObject,
) -> bool:
    expected_vocabulary = FieldRegistrySnapshot.load(
        prepared.registry_source
    ).pre_input_vocabulary()
    return review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=expected_vocabulary,
        expected_document_sha256=prepared.template_sha256,
    )


def _raise_accepted_harness_semantics_invalid() -> NoReturn:
    raise ToolFailure(
        status="needs_input",
        origin="harness",
        code="template_materialization_semantics_invalid",
        message=(
            "Accepted Harness semantics must use current scope, ordered parts, "
            "input field vocabulary, and resolved span provenance."
        ),
        retryable=True,
        suggested_actions=(
            "Rebuild the Harness phase review from current semantic_judgments.",
            "Do not reuse old semantic judgment shapes or hand-written coverage.",
        ),
    )


def _accepted_harness_semantics(prepared: PreparedTemplateTask) -> tuple[JsonObject, JsonObject]:
    inventory = _read_json_object(
        prepared.task_root / _HARNESS_OBJECT_INVENTORY,
        code="template_materialization_inventory_missing",
        message=(
            "Harness accepted post-unit semantics but did not persist the object inventory "
            "needed for deterministic materialization."
        ),
    )
    judgments = _read_json_object(
        prepared.task_root / _HARNESS_SEMANTIC_JUDGMENTS,
        code="template_materialization_semantics_missing",
        message=(
            "Harness accepted post-unit semantics but did not persist semantic judgments "
            "needed for deterministic materialization."
        ),
    )
    if not _accepted_harness_semantics_current(
        prepared=prepared,
        inventory=inventory,
        review=judgments,
    ):
        _raise_accepted_harness_semantics_invalid()
    return inventory, judgments


_CANDIDATE_MATERIALIZATION_EFFECT_INTENT_TYPES = {
    MaterializationIntentType.DELETE_BLOCK,
    MaterializationIntentType.MATERIALIZE_SLOT,
    MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE,
    MaterializationIntentType.KEEP_MANUAL_TABLE_CELL,
    MaterializationIntentType.TRANSFER_STYLE_ONLY,
    MaterializationIntentType.REFRESH_GENERATED_CONTENT,
}
_CANDIDATE_MATERIALIZATION_EFFECT_PART_ROLES = {
    "fill_slot",
    "body_structure",
    "generated_content",
    "cleanup",
}
_PUBLISHED_SLOT_REQUIRED_PART_ROLES = {
    "fill_slot",
    "body_structure",
}


def _terminal_source_noop_judgment(judgment: JsonObject) -> bool:
    parts = judgment.get("parts")
    if not isinstance(parts, list) or not parts:
        return False
    for part in parts:
        if not isinstance(part, dict):
            continue
        role = part.get("role")
        if isinstance(role, str) and role.strip().casefold() == "manual_region":
            return True
    return False


def _judgment_has_candidate_materialization_effect(judgment: JsonObject) -> bool:
    parts = judgment.get("parts")
    if not isinstance(parts, list):
        return False
    for part in parts:
        if not isinstance(part, dict):
            continue
        role = part.get("role")
        if (
            isinstance(role, str)
            and role.strip().casefold() in _CANDIDATE_MATERIALIZATION_EFFECT_PART_ROLES
        ):
            return True
    return False


def _judgment_requires_published_slot(judgment: JsonObject) -> bool:
    parts = judgment.get("parts")
    if not isinstance(parts, list):
        return False
    for part in parts:
        if not isinstance(part, dict):
            continue
        role = part.get("role")
        if (
            isinstance(role, str)
            and role.strip().casefold() in _PUBLISHED_SLOT_REQUIRED_PART_ROLES
        ):
            return True
    return False


def _accepted_review_allows_no_published_slots(review: JsonObject) -> bool:
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list) or not raw_judgments:
        return False
    judgments = [item for item in raw_judgments if isinstance(item, dict)]
    if len(judgments) != len(raw_judgments):
        return False
    if any(not isinstance(judgment.get("parts"), list) for judgment in judgments):
        return False
    return not any(_judgment_requires_published_slot(judgment) for judgment in judgments)


def _accepted_semantics_allow_source_noop(prepared: PreparedTemplateTask) -> bool:
    try:
        _, review = _accepted_harness_semantics(prepared)
    except ToolFailure:
        return False
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list) or not raw_judgments:
        return False
    judgments = [item for item in raw_judgments if isinstance(item, dict)]
    if len(judgments) != len(raw_judgments):
        return False
    if any(not isinstance(judgment.get("parts"), list) for judgment in judgments):
        return False
    if any(_judgment_has_candidate_materialization_effect(judgment) for judgment in judgments):
        return False
    return any(_terminal_source_noop_judgment(judgment) for judgment in judgments)


def _accepted_semantics_allow_no_slots(prepared: PreparedTemplateTask) -> bool:
    try:
        _, review = _accepted_harness_semantics(prepared)
    except ToolFailure:
        return False
    return _accepted_review_allows_no_published_slots(review)


def _accepted_semantics_have_materialization_effect(
    *,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> bool:
    raw_judgments = review.get("semantic_judgments")
    judgments = (
        [item for item in raw_judgments if isinstance(item, dict)]
        if isinstance(raw_judgments, list)
        else []
    )
    if any(_judgment_has_candidate_materialization_effect(judgment) for judgment in judgments):
        return True
    compiled = compile_materialization_intents(review=review, registry=registry)
    return any(
        intent.intent_type in _CANDIDATE_MATERIALIZATION_EFFECT_INTENT_TYPES
        for intent in compiled.intents
    )


def _next_materialization_candidate_path(prepared: PreparedTemplateTask) -> Path:
    directory = prepared.task_root / "work/.docfit/post-unit-materialization"
    directory.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        candidate = directory / f"candidate-{index:04d}.docx"
        if not candidate.exists():
            return candidate
        index += 1


def _raise_materialization_readiness_feedback(
    prepared: PreparedTemplateTask,
    readiness_feedback: JsonObject,
) -> NoReturn:
    revision_packet = _agent_visible_feedback_packet(
        readiness_feedback,
        next_step=_MATERIALIZATION_READINESS_NEXT_STEP,
    )
    directory = prepared.task_root / "work/.docfit/post-unit-materialization"
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        prepared.task_root / _POST_UNIT_MATERIALIZATION_RECEIPT,
        {
            "schema_version": 1,
            "status": "needs_input",
            "checks": [{"name": "materialization_readiness", "result": "needs_input"}],
            "agent_revision_packet": revision_packet,
            "failure": readiness_feedback["failure"],
        },
    )
    failure = readiness_feedback.get("failure", {})
    failure_message = (
        failure.get("message")
        if isinstance(failure, dict) and isinstance(failure.get("message"), str)
        else None
    )
    materialization_message = (
        failure_message
        or "Accepted semantic_judgments are not ready for deterministic materialization."
    )
    raise ToolFailure(
        status="needs_input",
        origin="harness",
        code="template_materialization_readiness_incomplete",
        message=materialization_message,
        retryable=True,
        suggested_actions=(
            "Return the agent_revision_packet to the Agent.",
            (
                "Revise semantic_judgments with source_entry_id, ordered parts, and "
                "input vocabulary field_id values."
            ),
            "Do not run materialization handlers until the readiness gate passes.",
        ),
    )


def _materialize_candidate_from_accepted_semantics(
    prepared: PreparedTemplateTask,
) -> Path | None:
    inventory, review = _accepted_harness_semantics(prepared)
    raw_objects = inventory.get("objects")
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_objects, list) or not isinstance(raw_judgments, list):
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="template_materialization_review_invalid",
            message="Accepted Harness review lacks materializable objects or judgments.",
            retryable=True,
        )

    registry = FieldRegistrySnapshot.load(prepared.registry_source)
    readiness_feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )
    if readiness_feedback is not None:
        _raise_materialization_readiness_feedback(prepared, readiness_feedback)
    if not _accepted_semantics_have_materialization_effect(review=review, registry=registry):
        return None
    current_candidate = _next_materialization_candidate_path(prepared)
    result = materialize_template_from_semantics(
        source_docx=prepared.template_path,
        output_docx=current_candidate,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    materialized = result.get("operations", [])
    cleanup = result.get("cleanup", [])
    policy_receipts = result.get("policy_receipts", [])
    mutation_receipts = result.get("mutation_receipts", [])
    has_materialization_effect = any(
        isinstance(items, list) and items
        for items in (materialized, cleanup, policy_receipts, mutation_receipts)
    )
    if not isinstance(materialized, list) or not has_materialization_effect:
        return None
    current_hash = sha256_file(current_candidate)
    allow_no_slots = _accepted_review_allows_no_published_slots(review)
    if allow_no_slots:
        publishability = publication_slot_protocol_status(
            candidate_docx=current_candidate,
            registry=registry,
            allow_no_slots=True,
        )
    else:
        publishability = publication_slot_protocol_status(
            candidate_docx=current_candidate,
            registry=registry,
        )
    receipt: JsonObject = {
        "schema_version": 1,
        "status": "ok" if publishability.get("status") == "ok" else "needs_input",
        "candidate_docx": str(current_candidate.relative_to(prepared.task_root)),
        "candidate_sha256": current_hash,
        "document_sha256": review.get("document_sha256"),
        "semantic_judgments_sha256": review.get("semantic_judgments_sha256"),
        "field_vocabulary_digest": review.get("field_vocabulary_digest"),
        "field_registry_ref": registry.identity(),
        "operation_count": len(materialized),
        "cleanup_count": result.get("cleanup_count", 0),
        "operations": materialized,
        "cleanup": cleanup if isinstance(cleanup, list) else [],
        "publishability": publishability,
    }
    if isinstance(mutation_receipts, list) and mutation_receipts:
        receipt["mutation_receipts"] = mutation_receipts
        receipt["receipt_count"] = result.get("receipt_count", len(mutation_receipts))
    write_result = result.get("write")
    if isinstance(write_result, dict):
        receipt["write"] = write_result
    shadow_intent_plan = result.get("shadow_intent_plan")
    if isinstance(shadow_intent_plan, dict):
        receipt["shadow_intent_plan"] = shadow_intent_plan
    if isinstance(policy_receipts, list) and policy_receipts:
        receipt["policy_receipts"] = policy_receipts
    atomic_write_json(prepared.task_root / _POST_UNIT_MATERIALIZATION_RECEIPT, receipt)
    if publishability.get("status") != "ok":
        failure = publishability.get("failure")
        failure_message = (
            failure.get("message")
            if isinstance(failure, dict) and isinstance(failure.get("message"), str)
            else None
        )
        detail = failure_message or "The materialized candidate is not publication-compatible."
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="template_materialization_candidate_not_publishable",
            message=detail,
            retryable=True,
        )
    return current_candidate


def _materialization_readiness_feedback_if_available(
    prepared: PreparedTemplateTask,
) -> JsonObject | None:
    try:
        return _materialization_readiness_feedback_for_complete_output(prepared)
    except ToolFailure as error:
        if error.code in {
            "template_materialization_inventory_missing",
            "template_materialization_semantics_missing",
        }:
            return None
        raise


def _select_host_candidate_for_accepted_semantics(prepared: PreparedTemplateTask) -> Path:
    readiness_feedback = _materialization_readiness_feedback_if_available(prepared)
    if readiness_feedback is not None:
        _raise_materialization_readiness_feedback(prepared, readiness_feedback)

    if _accepted_semantics_allow_source_noop(prepared):
        return prepared.template_path
    candidate = _materialize_candidate_from_accepted_semantics(prepared)
    if candidate is not None:
        return candidate

    publishability = _source_noop_publishability(prepared)
    failure = publishability.get("failure", {})
    detail = (
        str(failure.get("message"))
        if isinstance(failure, dict) and failure.get("message")
        else "The source is not directly publication-compatible."
    )
    raise ToolFailure(
        status="needs_input",
        origin="harness",
        code="template_materialization_required",
        message=(
            "Harness accepted the semantic_judgments set, but deterministic post-unit "
            f"materialization is required before final artifacts can be built. {detail}"
        ),
        retryable=True,
        suggested_actions=(
            (
                "Implement or run Harness-owned post-unit materialization from the "
                "accepted semantic judgments."
            ),
            (
                "Do not ask the Agent to provide candidate paths, render handles, or "
                "delivery materials."
            ),
        ),
    )


def _materialization_readiness_feedback_for_complete_output(
    prepared: PreparedTemplateTask,
) -> JsonObject | None:
    inventory, review = _accepted_harness_semantics(prepared)
    return materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=FieldRegistrySnapshot.load(prepared.registry_source),
    )


def _validate_host_candidate(
    prepared: PreparedTemplateTask,
    candidate: Path,
) -> tuple[JsonObject, JsonObject]:
    candidate_hash = sha256_file(candidate)
    service = DocFitToolService(task_root=prepared.task_root)
    validation = service.validate(
        {
            "source_docx": str(prepared.template_path),
            "source_sha256": prepared.template_sha256,
            "final_docx": str(candidate),
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
            message="The Harness-selected final Word failed objective validation.",
        )
    visual_review: JsonObject = {
        "schema_version": 1,
        "status": "host_review_not_requested",
        "origin": "harness",
        "document_sha256": candidate_hash,
        "reviewed_pages": [],
        "findings": [],
    }
    return visual_review, validation


def _semantic_coverage_feedback(
    prepared: PreparedTemplateTask,
    structured_output: JsonObject,
) -> JsonObject | None:
    semantic_judgments = structured_output.get("semantic_judgments")
    if not isinstance(semantic_judgments, list):
        return {
            "status": "needs_input",
            "feedback": {
                "type": "semantic_completeness",
                "mechanical": True,
                "semantic_authority": False,
                "agent_action": (
                    "Return semantic_judgments with source_entry_id and ordered parts; "
                    "choose field IDs only from "
                    "field_id_vocabulary."
                ),
            },
            "blockers": [
                {
                    "code": "semantic_judgments_missing",
                    "message": (
                        "The structured output must include semantic_judgments so the "
                        "runtime can map semantic decisions to accepted source spans."
                    ),
                }
            ],
            "failure": {
                "suggested_actions": [
                    (
                        "return semantic_judgments with source_entry_id and ordered parts from "
                        "the current unit_evidence_packet"
                    )
                ]
            },
        }
    service = TemplateHarnessService(task_root=prepared.task_root)
    checkpoint = _current_unit_boundary_checkpoint(prepared)
    if checkpoint is None:
        service.handle(
            {
                "action": "inspect_objects",
                "input_docx": str(prepared.template_path),
            }
        )
    else:
        _ensure_post_unit_inventory(prepared, checkpoint)
    result = service.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": prepared.template_sha256,
            "semantic_judgments": semantic_judgments,
        }
    )
    if result.get("status") == "ok":
        return None
    return result


_AGENT_VISIBLE_FEEDBACK_SCOPE_KEYS = (
    "code",
    "unit_id",
    "unit_ids",
    "source_entry_id",
    "source_entry_ids",
    "reading_block_id",
    "reading_block_ids",
    "range_id",
    "range_ids",
    "reading_range_id",
    "reading_range_ids",
    "responsibility",
    "evidence_focus",
    "missing_requirement",
    "why_it_blocks_execution",
    "field_id",
    "submitted_text",
    "scoped_text",
    "source_text_after_search_start",
    "uncovered_text",
    "search_start_offset",
)
_RETIRED_AGENT_VISIBLE_EVIDENCE_FOCUS = frozenset({"unit_slice", "registry_field"})


def _agent_visible_feedback_type(feedback: JsonObject) -> str:
    raw_feedback = feedback.get("feedback")
    raw_type = raw_feedback.get("type") if isinstance(raw_feedback, dict) else None
    if raw_type in {"unit_coverage", "boundary_coverage"}:
        return "unit_boundary_review"
    if raw_type in {"coverage", "semantic_coverage", "semantic_completeness"}:
        return "semantic_source_entry_review"
    if raw_type == "materialization_readiness":
        return "materialization_readiness_review"
    return "mechanical_review"


_LEGACY_AGENT_FEEDBACK_TOKENS = (
    "toc_contract",
    "generated_field_id",
    "registry_binding",
    "registry_field",
    "semantic_field",
    "source_content_id",
    "source_content_ids",
    "parent_content_id",
    "target_content_id",
    "source_object_id",
    "source_object_ids",
    "source_object_ref",
    "source_object_refs",
    "source_entry_ref",
    "source_entry_refs",
    "span_ref",
    "span_refs",
    "slot_ref",
    "slot_refs",
    "covered_reading_block_ids",
    "covered_reading_range_ids",
    "covered_reading_spans",
    "semantic_parts",
    "bound_field_id",
    "bound_field_ids",
    "required_field",
    "required_field_ids",
    "structure_ref",
    "members",
    "clean_template_treatment",
    "semantic_role",
    "judgment_id",
    "interface_ref",
    "output_effect",
    "style_obligation",
    "style_role",
    "cleanup_reason",
    "replacement_or_carrier",
    "variant_id",
    "variant_role",
    "variant_condition",
    "selection_condition",
    "object_text_spans",
)


def _agent_visible_blocker_code(code: object) -> object:
    if not isinstance(code, str):
        return code
    if code == "materialization_legacy_shape_unsupported":
        return "ordered_parts_incomplete"
    if code == "unknown_judgment_objects":
        return "semantic_judgment_scope_unknown"
    if code == "semantic_judgments_without_coverage":
        return "semantic_judgment_scope_uncovered"
    if code == "missing_source_entry_semantic_judgments":
        return "semantic_judgment_source_entry_missing"
    if code == "unknown_source_entry_semantic_judgments":
        return "semantic_judgment_source_entry_unknown"
    if code == "overlapping_source_entry_semantic_judgments":
        return "semantic_judgment_source_entry_overlap"
    if code == "semantic_spans_without_source_entry_coverage":
        return "semantic_judgment_source_entry_unresolved"
    if "semantic_parts" in code or "semantic_part" in code:
        return "ordered_parts_incomplete"
    if "structure_ref" in code or "body_structure_member" in code:
        return "body_structure_parts_incomplete"
    if "body_structure_range" in code or "body_structure_candidate" in code:
        return "body_structure_parts_incomplete"
    if "body_structure_member" in code:
        return "body_structure_parts_incomplete"
    if "body_structure_parent" in code:
        return "body_structure_field_group_incomplete"
    if any(token in code for token in _LEGACY_AGENT_FEEDBACK_TOKENS):
        return "semantic_judgment_incomplete"
    return code


def _agent_visible_missing_requirement(requirement: object) -> object:
    if not isinstance(requirement, str):
        return requirement
    if "semantic_parts" in requirement or "semantic_part" in requirement:
        return "ordered_parts"
    if "structure_ref" in requirement or "members" in requirement:
        return "body_structure_parts"
    if "body_structure_range" in requirement or "body_structure_candidate" in requirement:
        return "body_structure_parts"
    if "body_structure_member" in requirement:
        return "body_structure_parts"
    if "parent_field_id" in requirement:
        return "body_structure_field_group"
    if any(token in requirement for token in _LEGACY_AGENT_FEEDBACK_TOKENS):
        return "semantic_judgment"
    return requirement


def _agent_visible_why_it_blocks(value: object) -> object:
    if not isinstance(value, str):
        return value
    if "parent_field_id" in value or any(
        token in value for token in _LEGACY_AGENT_FEEDBACK_TOKENS
    ):
        return (
            "This scope is not executable until its ordered parts and field_id choices "
            "match the current semantic judgment contract."
        )
    return value


def _agent_visible_blocker_message(blocker: JsonObject) -> str:
    code = blocker.get("code")
    raw = blocker.get("message")
    if code in {"missing_semantic_judgments", "semantic_judgments_missing"}:
        if not _agent_visible_reading_blocks(blocker):
            return (
                "Some accepted source entries still need a semantic_judgment with "
                "source_entry_id and ordered parts."
            )
        return (
            "The listed reading_blocks are inside the current accepted unit packet and "
            "must be covered by semantic_judgments with source_entry_id and ordered "
            "parts. If a block is only an instruction, layout carrier, or non-content "
            "note, still classify it with cleanup, style_only, fixed_label, or "
            "manual_region as appropriate."
        )
    if code == "overlapping_semantic_judgments":
        return (
            "More than one semantic_judgment points at the same accepted source range. "
            "Each listed reading block or range needs one ordered owner judgment, with "
            "mixed responsibilities split into parts inside that same judgment."
        )
    if code == "missing_source_entry_semantic_judgments":
        return (
            "The listed source entries must be covered by semantic_judgments with "
            "source_entry_id and ordered parts."
        )
    if code == "unknown_source_entry_semantic_judgments":
        return (
            "A semantic_judgment source_entry_id is not in the current unit packet. "
            "Revise it to one of the listed source entries."
        )
    if code == "overlapping_source_entry_semantic_judgments":
        return (
            "More than one semantic_judgment covers the same source entry text. Merge "
            "or split the listed source-entry judgments so each text span has one owner."
        )
    if code == "semantic_spans_without_source_entry_coverage":
        return (
            "A resolved semantic span did not map back to a current source entry. "
            "Revise the judgment to source_entry_id and ordered parts from the current "
            "unit packet."
        )
    if code == "empty_semantic_judgments":
        return "A semantic_judgment is present but does not explain the source range."
    if code in {"unknown_judgment_objects", "semantic_judgments_without_coverage"}:
        return (
            "A semantic_judgment range does not match a current source_entry_id or "
            "compatibility reading view token. Revise it to the current unit packet."
        )
    if code in {
        "materialization_structure_ref_unknown",
        "materialization_structure_contract_unsupported",
    }:
        return (
            "This range is not executable as body structure. If it is a plain slot, fixed "
            "section, format note, references section, acknowledgment, appendix, or "
            "style-only range, revise the ordered parts to the matching role. Only real "
            "body representative text should use body_structure parts."
        )
    if code == "materialization_body_structure_member_unknown":
        return (
            "Body structure parts must use field_id values from the pre-input "
            "field_id_vocabulary. Keep reading_block ids only in scope or reading block "
            "feedback; do not put reading_block ids in field_id."
        )
    if code == "materialization_slot_field_incompatible":
        return (
            "This fill_slot part references a field_id that cannot be used as a plain "
            "fillable slot. Choose a fillable field from field_id_vocabulary, revise the "
            "part role if this range is generated content or a non-text section, or "
            "return needs_input if no safe field exists."
        )
    if code == "materialization_slot_field_missing":
        return (
            "This fill slot is missing a Registry field. Revise the ordered fill_slot "
            "part to use a field_id from the pre-input field_id_vocabulary. If no safe "
            "field exists in that vocabulary, return needs_input or revise this range as "
            "non-executable."
        )
    if code == "materialization_body_structure_semantics_missing":
        return (
            "If this is the actual body representative, revise the scoped judgment to "
            "use ordered body_structure parts with one input-vocabulary field_id per "
            "member in document order. If it is references, acknowledgment, appendix, "
            "abstract, or a style-only/non-body section, use fill_slot, fixed_label, "
            "cleanup, style_only, or manual_region parts as appropriate."
        )
    if code == "materialization_body_structure_member_block_ambiguous":
        return (
            "Each body reading_block can become only one body_structure member slot. "
            "Revise the judgment so the block has a single body_structure part for the "
            "body member field, and classify numbering, separators, style notes, or fixed "
            "template text as non-body parts."
        )
    if code == "materialization_body_structure_parent_missing":
        return (
            "Body_structure parts must choose field_id values that belong to one "
            "body-structure group in the pre-input field_id_vocabulary. If this range "
            "is title, references, acknowledgment, appendix, abstract, or a non-body "
            "section, revise the ordered parts to the matching role instead of using "
            "body_structure."
        )
    if code == "materialization_legacy_shape_unsupported":
        return (
            "Accepted semantic judgments must be rewritten as source_entry_id plus "
            "ordered parts. Each executable fill_slot, body_structure, or "
            "generated_content part must choose field_id from the pre-input "
            "field_id_vocabulary, and Harness must resolve the selected ordered part "
            "to a source-entry span before materialization."
        )
    if code == "materialization_body_structure_member_scope_mismatch":
        return (
            "The body_structure parts are not a category summary. Use one ordered part "
            "for every body representative text segment in document order, with each "
            "field_id chosen from the pre-input field_id_vocabulary. If a covered block "
            "is only a track label, format note, example prose, or blank carrier, split "
            "it out as fixed_label, cleanup, style_only, or manual_region."
        )
    if code in {
        "materialization_body_structure_range_group_missing",
        "materialization_body_structure_candidate_ambiguous",
    }:
        return (
            "The body representative structure must describe one executable contiguous "
            "body track in document order. Keep representative body text as "
            "body_structure parts with field_id values from field_id_vocabulary, and "
            "classify alternate tracks, references, acknowledgment, appendix, notes, "
            "or style-only ranges into their own non-body roles."
        )
    if blocker.get("missing_requirement") == "open_questions":
        return (
            "A complete semantic_judgment cannot keep open_questions. If the question "
            "would change the school semantic decision, return needs_input for that "
            "missing school evidence; if it is about implementation, Registry maintenance, "
            "Word carrier details, or Host materialization, remove it from the judgment."
        )
    if isinstance(raw, str) and raw.strip():
        for internal in (
            "object_ref",
            "object_id",
            "object_ids",
            "covered_object_ids",
            "target_ref",
            "locator",
            "source_entry_ref",
            "span_ref",
            "slot_ref",
            "candidate_hash",
            "render_ref",
            "coverage",
            "publish",
            "stale_ref",
            "fingerprint",
            *_LEGACY_AGENT_FEEDBACK_TOKENS,
        ):
            if internal in raw:
                return "This range needs a revised semantic_judgment in Agent terms."
        return raw.strip()
    return "This range needs a revised semantic_judgment in Agent terms."


def _agent_visible_reading_blocks(blocker: JsonObject) -> list[JsonObject]:
    raw = blocker.get("reading_blocks")
    if not isinstance(raw, list):
        return []
    visible: list[JsonObject] = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        summary: JsonObject = {}
        for key in ("block_id", "range_id", "unit_range_id", "unit_id", "text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                summary[key] = value.strip()[:500] if key == "text" else value.strip()
        if summary:
            visible.append(summary)
    return visible


def _agent_visible_blocker(blocker: Any) -> JsonObject:
    if not isinstance(blocker, dict):
        return {"message": "A semantic range needs revision."}
    visible: JsonObject = {}
    for key in _AGENT_VISIBLE_FEEDBACK_SCOPE_KEYS:
        value = blocker.get(key)
        if value is not None:
            if key == "code":
                visible[key] = _agent_visible_blocker_code(value)
            elif key == "evidence_focus" and value in _RETIRED_AGENT_VISIBLE_EVIDENCE_FOCUS:
                continue
            elif key == "missing_requirement":
                visible[key] = _agent_visible_missing_requirement(value)
            elif key == "why_it_blocks_execution":
                visible[key] = _agent_visible_why_it_blocks(value)
            elif key in {
                "submitted_text",
                "scoped_text",
                "source_text_after_search_start",
                "uncovered_text",
            } and isinstance(value, str):
                visible[key] = value[:500]
            else:
                visible[key] = value
    field = blocker.get("field")
    if (
        isinstance(field, str)
        and field.startswith("semantic_judgments")
        and not any(token in field for token in _LEGACY_AGENT_FEEDBACK_TOKENS)
    ):
        visible["field"] = field
    reading_blocks = _agent_visible_reading_blocks(blocker)
    if reading_blocks:
        visible["reading_blocks"] = reading_blocks
        visible["reading_block_ids"] = [
            item["block_id"] for item in reading_blocks if isinstance(item.get("block_id"), str)
        ]
    source_entries = _agent_visible_source_entries(blocker)
    if source_entries:
        visible["source_entries"] = source_entries
    visible["message"] = _agent_visible_blocker_message(blocker)
    return visible


def _agent_visible_source_entries(blocker: JsonObject) -> list[JsonObject]:
    raw = blocker.get("source_entries")
    if not isinstance(raw, list):
        return []
    visible: list[JsonObject] = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        summary: JsonObject = {}
        for key in ("source_entry_id", "entry_type", "text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                summary[key] = value.strip()[:500] if key == "text" else value.strip()
        source_order = item.get("source_order")
        if isinstance(source_order, dict):
            summary["source_order"] = {
                str(key): value
                for key, value in source_order.items()
                if isinstance(key, str) and isinstance(value, int)
            }
        if summary:
            visible.append(summary)
    return visible


def _semantic_feedback_failure_actions(feedback: JsonObject) -> tuple[str, ...]:
    packet = _agent_visible_feedback_packet(
        feedback,
        next_step=(
            "Revise semantic_judgments for the listed unit, reading block, or range ids."
        ),
    )
    affected = packet.get("affected", [])
    reading_block_ids: list[str] = []
    reading_range_ids: list[str] = []
    source_entry_ids: list[str] = []
    if isinstance(affected, list):
        for item in affected:
            if not isinstance(item, dict):
                continue
            raw_source_entry_ids = item.get("source_entry_ids")
            if isinstance(raw_source_entry_ids, list):
                source_entry_ids.extend(
                    value.strip()
                    for value in raw_source_entry_ids
                    if isinstance(value, str) and value.strip()
                )
            source_entry_id = item.get("source_entry_id")
            if isinstance(source_entry_id, str) and source_entry_id.strip():
                source_entry_ids.append(source_entry_id.strip())
            raw_source_entries = item.get("source_entries")
            if isinstance(raw_source_entries, list):
                for entry in raw_source_entries:
                    if not isinstance(entry, dict):
                        continue
                    entry_id = entry.get("source_entry_id")
                    if isinstance(entry_id, str) and entry_id.strip():
                        source_entry_ids.append(entry_id.strip())
            raw_block_ids = item.get("reading_block_ids")
            if isinstance(raw_block_ids, list):
                reading_block_ids.extend(
                    value.strip()
                    for value in raw_block_ids
                    if isinstance(value, str) and value.strip()
                )
            raw_range_ids = item.get("reading_range_ids")
            if isinstance(raw_range_ids, list):
                reading_range_ids.extend(
                    value.strip()
                    for value in raw_range_ids
                    if isinstance(value, str) and value.strip()
                )
            for key in ("reading_block_id", "range_id", "reading_range_id"):
                value = item.get(key)
                if not isinstance(value, str) or not value.strip():
                    continue
                if key == "reading_block_id":
                    reading_block_ids.append(value.strip())
                else:
                    reading_range_ids.append(value.strip())
            raw_blocks = item.get("reading_blocks")
            if isinstance(raw_blocks, list):
                for block in raw_blocks:
                    if not isinstance(block, dict):
                        continue
                    block_id = block.get("block_id")
                    if isinstance(block_id, str) and block_id.strip():
                        reading_block_ids.append(block_id.strip())
                    for key in ("range_id", "unit_range_id"):
                        range_id = block.get(key)
                        if isinstance(range_id, str) and range_id.strip():
                            reading_range_ids.append(range_id.strip())

    actions: list[str] = []
    unique_source_entry_ids = list(dict.fromkeys(source_entry_ids))[:20]
    unique_block_ids = list(dict.fromkeys(reading_block_ids))[:20]
    unique_range_ids = list(dict.fromkeys(reading_range_ids))[:20]
    if unique_source_entry_ids:
        actions.append(
            f"revise_semantic_judgments_for_source_entries={unique_source_entry_ids}"
        )
    if unique_block_ids:
        actions.append(f"revise_semantic_judgments_for_reading_blocks={unique_block_ids}")
    if unique_range_ids:
        actions.append(f"revise_semantic_judgments_for_reading_ranges={unique_range_ids}")
    actions.extend(
        (
            "return_source_entry_id_and_ordered_parts_from_current_unit_packet",
            "choose_field_ids_only_from_field_id_vocabulary",
        )
    )
    return tuple(dict.fromkeys(actions))


def _agent_visible_feedback_packet(
    feedback: JsonObject,
    *,
    next_step: str,
) -> JsonObject:
    raw_feedback = feedback.get("feedback")
    semantic_authority = (
        raw_feedback.get("semantic_authority") if isinstance(raw_feedback, dict) else False
    )
    blockers = feedback.get("blockers", [])
    return {
        "status": feedback.get("status", "needs_input"),
        "review": {
            "type": _agent_visible_feedback_type(feedback),
            "mechanical": True,
            "semantic_authority": bool(semantic_authority),
        },
        "affected": [
            _agent_visible_blocker(blocker) for blocker in blockers if isinstance(blocker, dict)
        ],
        "next_step": next_step,
    }


def _semantic_feedback_prompt(feedback: JsonObject) -> str:
    raw_feedback = feedback.get("feedback")
    feedback_type = raw_feedback.get("type") if isinstance(raw_feedback, dict) else None
    next_step = (
        _MATERIALIZATION_READINESS_NEXT_STEP
        if feedback_type == "materialization_readiness"
        else (
            "Revise semantic_judgments for the listed unit, reading block, or range ids. "
            "Keep school semantics unchanged unless the affected range changes the "
            "meaning; return needs_input if the readable context is insufficient."
        )
    )
    compact_feedback = _agent_visible_feedback_packet(
        feedback,
        next_step=next_step,
    )
    return (
        "Runtime Harness feedback:\n"
        f"{json.dumps(compact_feedback, ensure_ascii=False, sort_keys=True)}\n"
        "Revise only the blocked structured output fields unless the feedback exposes a real "
        "school-semantic conflict. Do not treat this feedback as a semantic grade. Return "
        "a full structured result again."
    )


def _runtime_feedback_for_complete_output(
    prepared: PreparedTemplateTask,
    structured_output: JsonObject,
    *,
    unit_boundary_checkpoint: JsonObject | None,
    stop_after_post_unit: bool = False,
) -> tuple[JsonObject | None, bool]:
    if unit_boundary_checkpoint is not None:
        semantic_feedback = _semantic_coverage_feedback(prepared, structured_output)
        if semantic_feedback is not None:
            return semantic_feedback, True
        readiness_feedback = _materialization_readiness_feedback_for_complete_output(prepared)
        if readiness_feedback is not None:
            return readiness_feedback, True
        return None, True
    if unit_boundary_checkpoint is None:
        semantic_feedback = _semantic_coverage_feedback(prepared, structured_output)
        if semantic_feedback is not None:
            return semantic_feedback, True
        readiness_feedback = _materialization_readiness_feedback_for_complete_output(prepared)
        if readiness_feedback is not None:
            return readiness_feedback, True
    return None, True


def _current_unit_boundary_checkpoint(prepared: PreparedTemplateTask) -> JsonObject | None:
    path = prepared.task_root / _UNIT_BOUNDARY_CHECKPOINT
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "ok" or payload.get("source_hash") != prepared.template_sha256:
        return None
    return payload


def _checkpoint_units(checkpoint: JsonObject) -> list[JsonObject]:
    raw_units = checkpoint.get("resolved_units")
    if not isinstance(raw_units, list) or not raw_units:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="post_unit_inventory_units_missing",
            message=(
                "Unit-boundary checkpoint must include Host-resolved resolved_units "
                "before post-unit semantic extraction."
            ),
            retryable=True,
            suggested_actions=(
                "Rebuild the unit-boundary checkpoint for the current source.",
            ),
        )
    units: list[JsonObject] = []
    for index, raw_unit in enumerate(raw_units):
        if not isinstance(raw_unit, dict):
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="post_unit_inventory_unit_invalid",
                message="Unit-boundary checkpoint resolved_units must contain unit objects.",
                retryable=True,
                suggested_actions=(
                    "Rebuild the unit-boundary checkpoint for the current source.",
                ),
            )
        unit = dict(raw_unit)
        raw_unit_id = unit.get("unit_id")
        if not isinstance(raw_unit_id, str) or not raw_unit_id.strip():
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="post_unit_inventory_unit_invalid",
                message=(
                    "Unit-boundary checkpoint resolved_units must keep the accepted unit_id "
                    f"for item {index + 1}."
                ),
                retryable=True,
                suggested_actions=(
                    "Rebuild the unit-boundary checkpoint for the current source.",
                ),
            )
        unit["unit_id"] = raw_unit_id.strip()
        units.append(unit)
    return units


def _post_unit_inventory_from_checkpoint(
    prepared: PreparedTemplateTask,
    checkpoint: JsonObject,
) -> JsonObject:
    inspection = DocFitToolService(task_root=prepared.task_root).inspect(
        {
            "input_docx": str(prepared.template_path),
            "focus": ["structure", "styles", "visible_objects"],
            "include_objects": True,
        }
    )
    raw_objects = inspection.get("objects", [])
    objects = raw_objects if isinstance(raw_objects, list) else []
    document = inspection.get("document")
    inspected_sha256 = document.get("sha256") if isinstance(document, dict) else None
    document_sha256 = (
        inspected_sha256 if isinstance(inspected_sha256, str) else prepared.template_sha256
    )
    objects_by_id = {
        object_id: item for item in objects if (object_id := object_id_for_item(item)) is not None
    }
    inventory_objects: list[JsonObject] = []
    reading_blocks: list[JsonObject] = []
    source_entries: list[JsonObject] = []
    unit_reading_packets: dict[str, JsonObject] = {}
    seen_object_ids: set[str] = set()
    seen_source_entry_ids: set[str] = set()
    field_id_vocabulary = FieldRegistrySnapshot.load(
        prepared.registry_source
    ).pre_input_vocabulary()
    try:
        canonical_inventory = build_canonical_source_inventory(
            source_snapshot_sha256=document_sha256,
            inspected_objects=objects,
        )
    except ValueError as error:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="canonical_source_inventory_unsupported",
            message=str(error),
            retryable=False,
        ) from error

    checkpoint_units = _checkpoint_units(checkpoint)
    for unit in checkpoint_units:
        start_locator = unit.get("start_locator")
        end_locator = unit.get("end_locator") or start_locator
        if not isinstance(start_locator, str) or not start_locator.strip():
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="post_unit_inventory_range_missing",
                message="An accepted unit is missing a resolved readable range.",
                retryable=True,
                suggested_actions=("Restart unit-boundary discovery for the current template.",),
            )
        if not isinstance(end_locator, str) or not end_locator.strip():
            end_locator = start_locator
        scoped_objects = objects_for_locator_span(
            objects,
            start_locator=start_locator,
            end_locator=end_locator,
        )
        raw_covered = unit.get("covered_object_ids", [])
        unit_coverage_ids = (
            [str(item) for item in raw_covered if isinstance(item, str)]
            if isinstance(raw_covered, list)
            else []
        )
        unit_source_entries = select_source_entries_for_objects(
            canonical_inventory,
            [
                object_id
                for item in scoped_objects
                if (object_id := object_id_for_item(item)) is not None
            ],
        )
        for source_entry in unit_source_entries:
            if source_entry.source_entry_id in seen_source_entry_ids:
                continue
            source_entries.append(source_entry.to_json())
            seen_source_entry_ids.add(source_entry.source_entry_id)
        entry_by_object_id = source_entry_by_object_id(unit_source_entries)
        projected_scoped_objects = project_source_entries_onto_objects(
            scoped_objects,
            unit_source_entries,
            source_sha256=document_sha256,
        )
        packet = build_unit_reading_packet(
            unit=unit,
            scoped_objects=projected_scoped_objects,
            coverage_object_ids=unit_coverage_ids or None,
            source_entries=unit_source_entries,
            field_id_vocabulary=field_id_vocabulary,
        )
        unit_reading_packets[unit["unit_id"]] = packet
        for mapping in packet.get("reading_block_mappings", []):
            if isinstance(mapping, dict):
                global_mapping = dict(mapping)
                global_mapping["order"] = len(reading_blocks) + 1
                reading_blocks.append(global_mapping)
        coverage_ids_for_inventory = [
            provenance.object_id
            for source_entry in unit_source_entries
            for provenance in source_entry.provenance
        ]
        for object_id in coverage_ids_for_inventory:
            if object_id in seen_object_ids:
                continue
            source_object = objects_by_id.get(object_id)
            if not isinstance(source_object, dict):
                raise ToolFailure(
                    status="needs_input",
                    origin="harness",
                    code="post_unit_inventory_object_missing",
                    message=(
                        "Unit-boundary checkpoint references an object that is no "
                        "longer present in the prepared source inspection."
                    ),
                    retryable=True,
                    suggested_actions=(
                        "Rebuild the unit-boundary checkpoint for the current source.",
                    ),
                )
            mapped_entry = entry_by_object_id.get(object_id)
            if mapped_entry is None:
                raise ToolFailure(
                    status="needs_input",
                    origin="harness",
                    code="post_unit_inventory_source_entry_missing",
                    message=(
                        "Unit reading packet coverage references an object that was not "
                        "included in a canonical source entry."
                    ),
                    retryable=True,
                    suggested_actions=(
                        "Rebuild post-unit source entry normalization for the current source.",
                    ),
                )
            source_entry_ref = source_entry_ref_for_entry(
                mapped_entry,
                source_sha256=document_sha256,
            )
            object_ref = source_object.get("object_ref")
            inventory_object: JsonObject = {
                "source_entry_id": mapped_entry.source_entry_id,
                "source_entry_ref": source_entry_ref,
                "object_id": object_id,
                "object_id_role": OBJECT_ID_BACKEND_ALIAS_ROLE,
                "object_id_alias_for": mapped_entry.source_entry_id,
                "object_ref": object_ref
                if isinstance(object_ref, dict)
                else {"object_id": object_id},
            }
            object_type = source_object.get("type")
            if isinstance(object_type, str):
                inventory_object["type"] = object_type
            locator = source_object.get("locator")
            if isinstance(locator, str):
                inventory_object["locator"] = locator
            inventory_objects.append(inventory_object)
            seen_object_ids.add(object_id)

    inventory: JsonObject = {
        "document_sha256": document_sha256,
        "canonical_source_inventory": canonical_inventory.to_json(),
        "source_entries": source_entries,
        "objects": inventory_objects,
        "reading_blocks": reading_blocks,
        "unit_reading_packets": unit_reading_packets,
        "unit_projection_digest": sha256_json(checkpoint_units),
        "field_id_vocabulary": field_id_vocabulary,
    }
    digest = field_id_vocabulary.get("digest")
    if isinstance(digest, str) and digest.strip():
        inventory["field_vocabulary_digest"] = digest.strip()
    return inventory


def _ensure_post_unit_inventory(
    prepared: PreparedTemplateTask,
    checkpoint: JsonObject,
) -> JsonObject:
    inventory_path = prepared.task_root / _HARNESS_OBJECT_INVENTORY
    if inventory_path.is_file():
        try:
            persisted = json.loads(inventory_path.read_text(encoding="utf-8"))
            if not isinstance(persisted, dict):
                raise ValueError("persisted object inventory must be an object")
            canonical = CanonicalSourceInventory.from_json(
                persisted.get("canonical_source_inventory")
            )
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="canonical_source_inventory_stale",
                message="The persisted canonical source inventory is invalid.",
                retryable=True,
                suggested_actions=("Restart post-unit preparation from the current source.",),
            ) from error
        if canonical.source_snapshot_sha256 != prepared.template_sha256:
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="canonical_source_inventory_stale",
                message="The persisted canonical source inventory is bound to another source.",
                retryable=True,
                suggested_actions=("Restart post-unit preparation from the current source.",),
            )
        if persisted.get("unit_projection_digest") != sha256_json(
            _checkpoint_units(checkpoint)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="canonical_source_inventory_projection_stale",
                message="The persisted unit projections do not match the accepted units.",
                retryable=True,
                suggested_actions=("Restart post-unit preparation from the current source.",),
            )
        return persisted

    inventory = _post_unit_inventory_from_checkpoint(prepared, checkpoint)
    TemplateHarnessService(task_root=prepared.task_root).handle(
        {
            "action": "submit_object_inventory",
            "document_sha256": inventory["document_sha256"],
            "objects": inventory["objects"],
            "reading_blocks": inventory["reading_blocks"],
            "source_entries": inventory["source_entries"],
            "canonical_source_inventory": inventory["canonical_source_inventory"],
            "unit_reading_packets": inventory["unit_reading_packets"],
            "unit_projection_digest": inventory["unit_projection_digest"],
        }
    )
    return inventory


def build_unit_boundary_checkpoint_prompt(
    prepared: PreparedTemplateTask,
    feedback: JsonObject | None = None,
) -> str:
    requirements = (
        str(prepared.requirements_path)
        if prepared.requirements_path is not None
        else "none supplied"
    )
    feedback_note = ""
    if feedback is not None:
        compact = _agent_visible_feedback_packet(
            feedback,
            next_step=(
                "Revise only top-level unit names and start/end boundary text. Keep "
                "later slot, Registry, style, and cleanup questions as open questions."
            ),
        )
        feedback_note = (
            "Runtime Harness feedback from the previous unit proposal:\n"
            f"{json.dumps(compact, ensure_ascii=False, sort_keys=True)}\n"
            "Revise only unit boundaries. The feedback is mechanical boundary feedback, "
            "not a semantic role judgment.\n"
        )
    return (
        "DocFit unit-boundary checkpoint v1. Load the docfit-school-extract Skill. "
        "Goal: return school function unit candidates for the source template only. "
        "The host runtime will run Harness boundary closure before any main preparation flow. "
        "Do not call write tools, do not perform final delivery, and do not decide final "
        "template quality. "
        "Use docfit_evidence with focus=document_map to read the template's visible text "
        "outline. Identify cover, declarations, TOC, body starts, references, appendix, "
        "achievements, acknowledgements, and similar top-level units from source order and "
        "visible boundary text, not from renderer state or a flat object index. Return "
        "semantic boundary descriptions only: start_boundary/end_boundary with page when "
        "known, region when useful, and seen_text. Do not output low-level document identity, "
        "renderer bookkeeping, boundary-closure payloads, or acceptance artifacts; Tool/Harness "
        "code maps your boundary descriptions to Word spans and then checks mechanical "
        "closure. Do not page through object windows just to prove closure; the host Harness "
        "checks closure after you return units. "
        "For unit splitting, document_map.summary.text_outline is the primary boundary index. "
        "If text_outline_window.has_more=true, continue document_map with "
        "offset=text_outline_window.next_offset until you can see the final top-level school "
        "unit or have enough boundary context to return needs_input. "
        "Do not repeat the same focus/offset window. "
        "If school requirements are supplied, Read them before naming units. "
        "A unit-split output contains only top-level school logical units with unit_name, "
        "start boundary, and end boundary. Do not output slots, deletion reminders, Registry "
        "fields, style obligations, cleanup tasks, or internal responsibilities as units. "
        "Runtime-bound source: "
        f"school_template={prepared.template_path} "
        f"trust={UNTRUSTED_SOURCE_DATA_LABEL}. "
        f"school_requirements={requirements} "
        f"trust={UNTRUSTED_SOURCE_DATA_LABEL if prepared.requirements_path else 'not_supplied'}. "
        f"{feedback_note}"
        "Return status=complete with summary and units[]. Each unit "
        "must include unit_id, unit_name, start_boundary, and end_boundary. If the readable "
        "source context or required school material is insufficient to make the semantic "
        "boundary judgment, return status=needs_input with needs_input[]."
    )


def _unit_boundary_feedback(
    prepared: PreparedTemplateTask,
    structured_output: JsonObject,
) -> JsonObject | None:
    if structured_output.get("status") != "complete":
        return mechanical_feedback(
            feedback_type="unit_coverage",
            code="unit_checkpoint_incomplete",
            message="Unit boundary checkpoint must return complete before main flow.",
            source_hash=prepared.template_sha256,
            blockers=[
                {
                    "code": "unit_checkpoint_incomplete",
                    "message": "Return complete with units[] or explain blocking input.",
                }
            ],
            suggested_actions=("return units[] with semantic start/end boundary text",),
        )
    units = structured_output.get("units")
    if not isinstance(units, list) or not units:
        return mechanical_feedback(
            feedback_type="unit_coverage",
            code="unit_boundaries_missing",
            message="Unit boundary checkpoint must include non-empty units[].",
            source_hash=prepared.template_sha256,
            blockers=[
                {
                    "code": "unit_boundaries_missing",
                    "field": "units",
                    "message": (
                        "Return unit candidates with start_boundary and end_boundary seen_text."
                    ),
                }
            ],
            suggested_actions=("return units[] with semantic start/end boundary text",),
        )
    try:
        result = DocFitToolService(task_root=prepared.task_root).check(
            {
                "schema_version": "docfit_check_input_v1",
                "check": "unit_coverage",
                "payload": {"units": units},
            }
        )
    except ToolFailure as error:
        result = error.result()
    if result.get("status") == "ok":
        if isinstance(result.get("resolved_units"), list):
            structured_output["resolved_units"] = result["resolved_units"]
        return None
    return result


def _unit_boundary_checkpoint_payload(
    *,
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    structured_output: JsonObject,
    tool_uses: tuple[str, ...],
    skills_loaded: tuple[str, ...],
    permission_events: tuple[JsonObject, ...],
    session_id: str,
    sdk_query_count: int,
    harness_feedback_attempts: int,
    wall_duration_ms: int,
    timing_events: tuple[JsonObject, ...] = (),
) -> JsonObject:
    units = structured_output.get("units")
    unit_count = len(units) if isinstance(units, list) else 0
    return {
        "schema_version": 1,
        "status": "ok",
        "checkpoint": _UNIT_BOUNDARY_STAGE,
        "source_hash": prepared.template_sha256,
        "summary": structured_output.get("summary", ""),
        "unit_count": unit_count,
        "units": units if isinstance(units, list) else [],
        "resolved_units": (
            structured_output["resolved_units"]
            if isinstance(structured_output.get("resolved_units"), list)
            else []
        ),
        "backend": backend.name,
        "session_id": session_id,
        "tool_uses": list(tool_uses),
        "skills_loaded": list(skills_loaded),
        "permission_events": list(permission_events),
        "sdk_query_count": sdk_query_count,
        "harness_feedback_attempts": harness_feedback_attempts,
        "wall_duration_ms": wall_duration_ms,
        "timing_events": list(timing_events),
        "timing_summary": _timing_summary(timing_events),
    }


async def _run_unit_boundary_checkpoint(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
) -> JsonObject:
    tool_uses: list[str] = []
    skills_loaded: list[str] = []
    permission_events: list[JsonObject] = []
    options = build_unit_boundary_checkpoint_options(
        prepared,
        backend,
        config_directory,
        permission_audit=lambda event: permission_events.append(_permission_event_payload(event)),
    )
    started = time.perf_counter()
    sdk_query_count = 0
    feedback_attempts = 0
    feedback: JsonObject | None = None
    result: ResultMessage | None = None
    timing_events: list[JsonObject] = []
    async with ClaudeSDKClient(options=options) as client:
        async with asyncio.timeout(PREPARE_TEMPLATE_TIMEOUT_SECONDS):
            while True:
                stage_query_index = sdk_query_count + 1
                query_event = _start_timing_event(
                    timing_events,
                    started=started,
                    stage=_UNIT_BOUNDARY_STAGE,
                    operation="sdk_query",
                    query_index=sdk_query_count + 1,
                    stage_query_index=stage_query_index,
                    prompt_kind="initial" if feedback is None else "harness_feedback",
                )
                query_finished = False
                try:
                    await client.query(build_unit_boundary_checkpoint_prompt(prepared, feedback))
                    sdk_query_count += 1
                    query_event["query_sent_elapsed_ms"] = _elapsed_ms(started)
                    result = None
                    responses = client.receive_response().__aiter__()
                    last_progress = time.perf_counter()
                    message_count = 0
                    tool_use_count = 0
                    while True:
                        no_progress_remaining = PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS - (
                            time.perf_counter() - last_progress
                        )
                        if no_progress_remaining <= 0:
                            raise _agent_no_progress_timeout_failure(
                                seconds=PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS
                            )
                        try:
                            message = await asyncio.wait_for(
                                anext(responses),
                                timeout=min(
                                    PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS,
                                    no_progress_remaining,
                                ),
                            )
                        except TimeoutError as error:
                            if (
                                time.perf_counter() - last_progress
                                >= PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS
                            ):
                                raise _agent_no_progress_timeout_failure(
                                    seconds=PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS
                                ) from error
                            raise
                        except StopAsyncIteration:
                            break
                        message_count += 1
                        made_progress = False
                        if isinstance(message, AssistantMessage):
                            for block in message.content:
                                if not isinstance(block, ToolUseBlock):
                                    continue
                                made_progress = True
                                tool_use_count += 1
                                tool_uses.append(block.name)
                                if block.name == "Skill":
                                    skill = block.input.get("skill") or block.input.get("name")
                                    if isinstance(skill, str):
                                        skills_loaded.append(skill)
                        if isinstance(message, ResultMessage):
                            made_progress = True
                            result = message
                        if made_progress:
                            last_progress = time.perf_counter()
                    structured_status = (
                        result.structured_output.get("status")
                        if result is not None and isinstance(result.structured_output, dict)
                        else None
                    )
                    result_valid = (
                        result is not None
                        and not result.is_error
                        and isinstance(result.structured_output, dict)
                    )
                    _finish_timing_event(
                        query_event,
                        started=started,
                        status="response_complete" if result_valid else "response_invalid",
                        message_count=message_count,
                        tool_use_count=tool_use_count,
                        result_is_error=result.is_error if result is not None else None,
                        result_duration_ms=(
                            result.duration_ms if result is not None else None
                        ),
                        result_api_duration_ms=(
                            result.duration_api_ms if result is not None else None
                        ),
                        result_num_turns=result.num_turns if result is not None else None,
                        structured_status=structured_status,
                    )
                    query_finished = True
                except BaseException as error:
                    if not query_finished:
                        _finish_timing_event(
                            query_event,
                            started=started,
                            status="interrupted",
                            error_type=error.__class__.__name__,
                        )
                    raise
                if (
                    result is None
                    or result.is_error
                    or not isinstance(result.structured_output, dict)
                ):
                    raise ToolFailure(
                        status="error",
                        origin="agent",
                        code="unit_checkpoint_result_invalid",
                        message="Unit boundary checkpoint did not return structured units.",
                            retryable=True,
                        )
                feedback_event = _start_timing_event(
                    timing_events,
                    started=started,
                    stage=_UNIT_BOUNDARY_STAGE,
                    operation="harness_feedback_check",
                    query_index=sdk_query_count,
                    stage_query_index=stage_query_index,
                    check_name="unit_boundary_closure",
                )
                feedback = _unit_boundary_feedback(prepared, result.structured_output)
                raw_feedback = feedback.get("feedback") if isinstance(feedback, dict) else None
                feedback_type = (
                    raw_feedback.get("type") if isinstance(raw_feedback, dict) else None
                )
                _finish_timing_event(
                    feedback_event,
                    started=started,
                    status="accepted" if feedback is None else "needs_feedback",
                    feedback_type=feedback_type,
                )
                if feedback is None:
                    checkpoint = _unit_boundary_checkpoint_payload(
                        prepared=prepared,
                        backend=backend,
                        structured_output=result.structured_output,
                        tool_uses=tuple(tool_uses),
                        skills_loaded=tuple(dict.fromkeys(skills_loaded)),
                        permission_events=tuple(permission_events),
                        session_id=result.session_id,
                        sdk_query_count=sdk_query_count,
                        harness_feedback_attempts=feedback_attempts,
                        wall_duration_ms=_elapsed_ms(started),
                        timing_events=tuple(timing_events),
                    )
                    atomic_write_json(prepared.task_root / _UNIT_BOUNDARY_CHECKPOINT, checkpoint)
                    return checkpoint
                feedback_attempts += 1
                if feedback_attempts >= _UNIT_BOUNDARY_FEEDBACK_ATTEMPTS:
                    atomic_write_json(
                        prepared.task_root / _UNIT_BOUNDARY_CHECKPOINT,
                        {
                            "schema_version": 1,
                            "status": "needs_input",
                            "source_hash": prepared.template_sha256,
                            "feedback": feedback,
                            "last_structured_output": (
                                result.structured_output
                                if result is not None and isinstance(result.structured_output, dict)
                                else {}
                            ),
                            "tool_uses": tool_uses,
                            "skills_loaded": list(dict.fromkeys(skills_loaded)),
                            "permission_events": permission_events,
                            "sdk_query_count": sdk_query_count,
                            "harness_feedback_attempts": feedback_attempts,
                            "wall_duration_ms": _elapsed_ms(started),
                            "timing_events": timing_events,
                            "timing_summary": _timing_summary(timing_events),
                        },
                    )
                    raise ToolFailure(
                        status="needs_input",
                        origin="harness",
                        code="unit_boundary_checkpoint_failed",
                        message="Harness rejected unit boundary candidates before main flow.",
                        retryable=True,
                        suggested_actions=("revise units[] against Harness feedback",),
                    )
    raise ToolFailure(
        status="error",
        origin="agent",
        code="unit_checkpoint_result_missing",
        message="Unit boundary checkpoint ended without a structured result.",
        retryable=True,
    )


async def _run_backend(
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    *,
    existing_unit_boundary_checkpoint: JsonObject | None = None,
    stop_after_post_unit: bool = False,
) -> TemplateAgentExecution:
    tool_uses: list[str] = []
    skills_loaded: list[str] = []
    permission_events: list[JsonObject] = []
    started = time.perf_counter()
    unit_boundary_checkpoint: JsonObject | None = existing_unit_boundary_checkpoint
    sdk_query_count = 0
    harness_feedback_attempts = 0
    semantic_feedback_attempts = 0
    sdk_events: list[JsonObject] = []
    timing_events: list[JsonObject] = []
    active_timing_event: JsonObject | None = None
    try:
        if unit_boundary_checkpoint is None:
            unit_boundary_checkpoint = await _run_unit_boundary_checkpoint(
                prepared,
                backend,
                config_directory,
            )
        else:
            atomic_write_json(
                prepared.task_root / _UNIT_BOUNDARY_CHECKPOINT,
                unit_boundary_checkpoint,
            )
        tool_uses.extend(
            str(item)
            for item in unit_boundary_checkpoint.get("tool_uses", [])
            if isinstance(item, str)
        )
        skills_loaded.extend(
            str(item)
            for item in unit_boundary_checkpoint.get("skills_loaded", [])
            if isinstance(item, str)
        )
        permission_events.extend(
            item
            for item in unit_boundary_checkpoint.get("permission_events", [])
            if isinstance(item, dict)
        )
        sdk_query_count += int(unit_boundary_checkpoint.get("sdk_query_count", 0))
        harness_feedback_attempts += int(
            unit_boundary_checkpoint.get("harness_feedback_attempts", 0)
        )
        timing_events.extend(
            item
            for item in unit_boundary_checkpoint.get("timing_events", [])
            if isinstance(item, dict)
        )
    except (TimeoutError, ToolFailure) as caught:
        _write_agent_trace(
            prepared,
            backend=backend.name,
            tool_uses=tuple(tool_uses),
            skills_loaded=tuple(dict.fromkeys(skills_loaded)),
            wall_duration_ms=round((time.perf_counter() - started) * 1000),
            failure=_failure_evidence(caught),
            sdk_query_count=sdk_query_count,
            harness_feedback_attempts=harness_feedback_attempts,
            semantic_feedback_attempts=semantic_feedback_attempts,
            permission_events=tuple(permission_events),
            unit_boundary_checkpoint=unit_boundary_checkpoint,
            sdk_events=tuple(sdk_events),
            timing_events=tuple(timing_events),
        )
        raise
    _ensure_post_unit_inventory(prepared, unit_boundary_checkpoint)
    options = build_prepare_template_options(
        prepared,
        backend,
        config_directory,
        permission_audit=lambda event: permission_events.append(_permission_event_payload(event)),
        stop_after_post_unit=stop_after_post_unit,
    )
    result: ResultMessage | None = None
    try:
        async with ClaudeSDKClient(options=options) as client:
            async with asyncio.timeout(PREPARE_TEMPLATE_TIMEOUT_SECONDS):
                stage_query_index = 1
                query_event = _start_timing_event(
                    timing_events,
                    started=started,
                    stage=_POST_UNIT_STAGE if stop_after_post_unit else "template-agent",
                    operation="sdk_query",
                    query_index=sdk_query_count + 1,
                    stage_query_index=stage_query_index,
                    prompt_kind="initial",
                )
                active_timing_event = query_event
                await client.query(
                    build_prepare_template_prompt(
                        prepared,
                        unit_boundary_checkpoint,
                        stop_after_post_unit=stop_after_post_unit,
                    )
                )
                sdk_query_count += 1
                query_event["query_sent_elapsed_ms"] = _elapsed_ms(started)
                feedback_attempt = 0
                while True:
                    result = None
                    responses = client.receive_response().__aiter__()
                    last_progress = time.perf_counter()
                    message_count = 0
                    tool_use_count = 0
                    query_finished = False
                    while True:
                        no_progress_remaining = PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS - (
                            time.perf_counter() - last_progress
                        )
                        if no_progress_remaining <= 0:
                            failure = _agent_no_progress_timeout_failure(
                                seconds=PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS,
                            )
                            _finish_timing_event(
                                query_event,
                                started=started,
                                status="no_progress_timeout",
                                message_count=message_count,
                                tool_use_count=tool_use_count,
                                error_code=failure.code,
                            )
                            active_timing_event = None
                            query_finished = True
                            raise failure
                        try:
                            message = await asyncio.wait_for(
                                anext(responses),
                                timeout=min(
                                    PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS,
                                    no_progress_remaining,
                                ),
                            )
                        except TimeoutError as error:
                            if (
                                time.perf_counter() - last_progress
                                >= PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS
                            ):
                                failure = _agent_no_progress_timeout_failure(
                                    seconds=PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS,
                                )
                                _finish_timing_event(
                                    query_event,
                                    started=started,
                                    status="no_progress_timeout",
                                    message_count=message_count,
                                    tool_use_count=tool_use_count,
                                    error_code=failure.code,
                                )
                                active_timing_event = None
                                query_finished = True
                                raise failure from error
                            _finish_timing_event(
                                query_event,
                                started=started,
                                status="idle_timeout",
                                message_count=message_count,
                                tool_use_count=tool_use_count,
                                error_type=error.__class__.__name__,
                            )
                            active_timing_event = None
                            query_finished = True
                            raise
                        except StopAsyncIteration:
                            break
                        message_count += 1
                        sdk_events.append(
                            _sdk_receive_event(
                                message,
                                elapsed_ms=_elapsed_ms(started),
                                stage=(
                                    _POST_UNIT_STAGE
                                    if stop_after_post_unit
                                    else "template-agent"
                                ),
                                query_index=int(query_event["query_index"]),
                                stage_query_index=stage_query_index,
                            )
                        )
                        del sdk_events[:-200]
                        made_progress = _sdk_has_generation_progress(message)
                        if isinstance(message, AssistantMessage):
                            for block in message.content:
                                if not isinstance(block, ToolUseBlock):
                                    continue
                                made_progress = True
                                tool_use_count += 1
                                tool_uses.append(block.name)
                                if block.name == "Skill":
                                    skill = block.input.get("skill") or block.input.get("name")
                                    if isinstance(skill, str):
                                        skills_loaded.append(skill)
                        if isinstance(message, ResultMessage):
                            made_progress = True
                            result = message
                        if made_progress:
                            last_progress = time.perf_counter()
                    structured_status = (
                        result.structured_output.get("status")
                        if result is not None and isinstance(result.structured_output, dict)
                        else None
                    )
                    result_valid = (
                        result is not None
                        and not result.is_error
                        and isinstance(result.structured_output, dict)
                    )
                    if not query_finished:
                        _finish_timing_event(
                            query_event,
                            started=started,
                            status="response_complete" if result_valid else "response_invalid",
                            message_count=message_count,
                            tool_use_count=tool_use_count,
                            result_is_error=result.is_error if result is not None else None,
                            result_duration_ms=(
                                result.duration_ms if result is not None else None
                            ),
                            result_api_duration_ms=(
                                result.duration_api_ms if result is not None else None
                            ),
                            result_num_turns=result.num_turns if result is not None else None,
                            structured_status=structured_status,
                        )
                        active_timing_event = None
                    if (
                        result is None
                        or result.is_error
                        or not isinstance(result.structured_output, dict)
                    ):
                        break
                    status = result.structured_output.get("status")
                    is_semantic_feedback = False
                    if status == "complete":
                        feedback_event = _start_timing_event(
                            timing_events,
                            started=started,
                            stage=(
                                _POST_UNIT_STAGE
                                if stop_after_post_unit
                                else "template-agent"
                            ),
                            operation="harness_feedback_check",
                            query_index=int(query_event["query_index"]),
                            stage_query_index=stage_query_index,
                            check_name="runtime_feedback_for_complete_output",
                        )
                        active_timing_event = feedback_event
                        feedback, is_semantic_feedback = _runtime_feedback_for_complete_output(
                            prepared,
                            result.structured_output,
                            unit_boundary_checkpoint=unit_boundary_checkpoint,
                            stop_after_post_unit=stop_after_post_unit,
                        )
                        raw_feedback = (
                            feedback.get("feedback") if isinstance(feedback, dict) else None
                        )
                        feedback_type = (
                            raw_feedback.get("type") if isinstance(raw_feedback, dict) else None
                        )
                        _finish_timing_event(
                            feedback_event,
                            started=started,
                            status="accepted" if feedback is None else "needs_feedback",
                            feedback_type=feedback_type,
                            semantic_feedback=is_semantic_feedback,
                        )
                        active_timing_event = None
                    else:
                        break
                    if feedback is None:
                        break
                    harness_feedback_attempts += 1
                    if is_semantic_feedback:
                        semantic_feedback_attempts += 1
                    feedback_attempt += 1
                    if feedback_attempt >= _SEMANTIC_FEEDBACK_ATTEMPTS:
                        break
                    stage_query_index += 1
                    query_event = _start_timing_event(
                        timing_events,
                        started=started,
                        stage=_POST_UNIT_STAGE if stop_after_post_unit else "template-agent",
                        operation="sdk_query",
                        query_index=sdk_query_count + 1,
                        stage_query_index=stage_query_index,
                        prompt_kind="harness_feedback",
                    )
                    active_timing_event = query_event
                    await client.query(_semantic_feedback_prompt(feedback))
                    sdk_query_count += 1
                    query_event["query_sent_elapsed_ms"] = _elapsed_ms(started)
    except (TimeoutError, ToolFailure) as caught:
        if active_timing_event is not None and "duration_ms" not in active_timing_event:
            _finish_timing_event(
                active_timing_event,
                started=started,
                status="interrupted",
                error_type=caught.__class__.__name__,
            )
        _write_agent_trace(
            prepared,
            backend=backend.name,
            tool_uses=tuple(tool_uses),
            skills_loaded=tuple(dict.fromkeys(skills_loaded)),
            wall_duration_ms=round((time.perf_counter() - started) * 1000),
            failure=_failure_evidence(caught),
            sdk_query_count=sdk_query_count,
            harness_feedback_attempts=harness_feedback_attempts,
            semantic_feedback_attempts=semantic_feedback_attempts,
            permission_events=tuple(permission_events),
            unit_boundary_checkpoint=unit_boundary_checkpoint,
            sdk_events=tuple(sdk_events),
            timing_events=tuple(timing_events),
        )
        raise
    except (KeyboardInterrupt, asyncio.CancelledError) as caught:
        if active_timing_event is not None and "duration_ms" not in active_timing_event:
            _finish_timing_event(
                active_timing_event,
                started=started,
                status="interrupted",
                error_type=caught.__class__.__name__,
            )
        _write_agent_trace(
            prepared,
            backend=backend.name,
            tool_uses=tuple(tool_uses),
            skills_loaded=tuple(dict.fromkeys(skills_loaded)),
            wall_duration_ms=round((time.perf_counter() - started) * 1000),
            failure=_failure_evidence(caught),
            sdk_query_count=sdk_query_count,
            harness_feedback_attempts=harness_feedback_attempts,
            semantic_feedback_attempts=semantic_feedback_attempts,
            permission_events=tuple(permission_events),
            unit_boundary_checkpoint=unit_boundary_checkpoint,
            sdk_events=tuple(sdk_events),
            timing_events=tuple(timing_events),
        )
        raise
    if result is None:
        failure = ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_result_missing",
            message="The main Agent loop ended without a ResultMessage.",
            retryable=True,
        )
        _write_agent_trace(
            prepared,
            backend=backend.name,
            tool_uses=tuple(tool_uses),
            skills_loaded=tuple(dict.fromkeys(skills_loaded)),
            wall_duration_ms=round((time.perf_counter() - started) * 1000),
            failure=_failure_evidence(failure),
            sdk_query_count=sdk_query_count,
            harness_feedback_attempts=harness_feedback_attempts,
            semantic_feedback_attempts=semantic_feedback_attempts,
            permission_events=tuple(permission_events),
            unit_boundary_checkpoint=unit_boundary_checkpoint,
            sdk_events=tuple(sdk_events),
            timing_events=tuple(timing_events),
        )
        raise failure
    if result.is_error or not isinstance(result.structured_output, dict):
        failure = ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_result_invalid",
            message="The main Agent did not return a valid structured completion result.",
            retryable=True,
        )
        _write_agent_trace(
            prepared,
            backend=backend.name,
            session_id=result.session_id,
            tool_uses=tuple(tool_uses),
            skills_loaded=tuple(dict.fromkeys(skills_loaded)),
            structured_output=(
                result.structured_output if isinstance(result.structured_output, dict) else {}
            ),
            wall_duration_ms=round((time.perf_counter() - started) * 1000),
            failure=_failure_evidence(failure),
            sdk_query_count=sdk_query_count,
            harness_feedback_attempts=harness_feedback_attempts,
            semantic_feedback_attempts=semantic_feedback_attempts,
            permission_events=tuple(permission_events),
            unit_boundary_checkpoint=unit_boundary_checkpoint,
            sdk_events=tuple(sdk_events),
            timing_events=tuple(timing_events),
        )
        raise failure
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
        sdk_query_count=sdk_query_count,
        harness_feedback_attempts=harness_feedback_attempts,
        semantic_feedback_attempts=semantic_feedback_attempts,
        permission_events=tuple(permission_events),
        unit_boundary_checkpoint=unit_boundary_checkpoint,
        sdk_events=tuple(sdk_events),
        timing_events=tuple(timing_events),
    )


async def run_unit_boundary_checkpoint(prepared: PreparedTemplateTask) -> JsonObject:
    backends = tuple(iter_agent_backends())
    if not backends:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="agent_backend_not_configured",
            message="No configured Agent backend is available for template preparation.",
        )
    failures: list[str] = []
    last_tool_failure: ToolFailure | None = None
    for backend in backends:
        try:
            with tempfile.TemporaryDirectory(prefix="docfit-template-sdk-") as config_name:
                return await _run_unit_boundary_checkpoint(prepared, backend, Path(config_name))
        except (TimeoutError, ToolFailure) as error:
            if isinstance(error, ToolFailure):
                last_tool_failure = error
            failures.append(
                error.code if isinstance(error, ToolFailure) else "unit_checkpoint_timeout"
            )
    if len(backends) == 1 and last_tool_failure is not None:
        raise last_tool_failure
    raise ToolFailure(
        status="error",
        origin="agent",
        code="unit_checkpoint_backends_exhausted",
        message="No configured backend completed the unit-boundary checkpoint: "
        + ", ".join(failures),
        retryable=True,
    )


async def run_template_agent(
    prepared: PreparedTemplateTask,
    *,
    unit_boundary_checkpoint: JsonObject | None = None,
    stop_after_post_unit: bool = False,
) -> TemplateAgentExecution:
    backends = tuple(iter_agent_backends())
    if not backends:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="agent_backend_not_configured",
            message="No configured Agent backend is available for template preparation.",
        )
    failures: list[str] = []
    last_tool_failure: ToolFailure | None = None
    for backend in backends:
        try:
            with tempfile.TemporaryDirectory(prefix="docfit-template-sdk-") as config_name:
                return await _run_backend(
                    prepared,
                    backend,
                    Path(config_name),
                    existing_unit_boundary_checkpoint=unit_boundary_checkpoint,
                    stop_after_post_unit=stop_after_post_unit,
                )
        except (TimeoutError, ToolFailure) as error:
            if isinstance(error, ToolFailure):
                last_tool_failure = error
            failures.append(
                error.code if isinstance(error, ToolFailure) else "template_agent_timeout"
            )
    if len(backends) == 1 and last_tool_failure is not None:
        raise last_tool_failure
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
    *,
    semantic_coverage_already_accepted: bool = False,
) -> tuple[Path, JsonObject, JsonObject]:
    output = execution.structured_output
    if output.get("status") != "complete":
        needs = output.get("needs_input", [])
        raise _failure(
            "template_agent_needs_input",
            f"The main Agent needs additional semantic input: {needs}",
            origin="agent",
        )
    agent_style_keys = sorted(set(output) & _AGENT_AUTHORED_STYLE_CONTRACT_KEYS)
    if agent_style_keys:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_style_contract_denied",
            message=(
                "Style Contract data is captured by O1 from the final Word; "
                f"Agent-authored fields are not accepted: {', '.join(agent_style_keys)}."
            ),
        )
    if "docfit-school-extract" not in execution.skills_loaded:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_agent_skill_missing",
            message="Completion lacks the canonical docfit-school-extract Skill.",
        )
    if not semantic_coverage_already_accepted:
        semantic_feedback = _semantic_coverage_feedback(prepared, output)
        if semantic_feedback is not None:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="template_semantic_completeness_incomplete",
                message="Completion requires Harness acceptance of the semantic_judgments set.",
                suggested_actions=_semantic_feedback_failure_actions(semantic_feedback),
            )
    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    visual_review, validation = _validate_host_candidate(prepared, candidate)
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
        sdk_query_count=int(trace.get("sdk_query_count", 1)),
        harness_feedback_attempts=int(trace.get("harness_feedback_attempts", 0)),
        semantic_feedback_attempts=int(trace.get("semantic_feedback_attempts", 0)),
        permission_events=tuple(
            item for item in trace.get("permission_events", []) if isinstance(item, dict)
        ),
        sdk_events=tuple(item for item in trace.get("sdk_events", []) if isinstance(item, dict)),
        timing_events=tuple(
            item for item in trace.get("timing_events", []) if isinstance(item, dict)
        ),
    )
    return execution, publication


def _load_post_unit_checkpoint_execution(
    prepared: PreparedTemplateTask,
) -> TemplateAgentExecution | None:
    checkpoint_path = prepared.task_root / _POST_UNIT_CHECKPOINT
    if not checkpoint_path.exists():
        return None
    try:
        checkpoint: Any = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _failure(
            "post_unit_checkpoint_invalid",
            "The post-unit checkpoint is not readable JSON.",
            origin="postcondition",
        ) from error
    if (
        not isinstance(checkpoint, dict)
        or checkpoint.get("checkpoint") != _POST_UNIT_STAGE
        or checkpoint.get("status") != "ok"
        or checkpoint.get("source_hash") != prepared.template_sha256
    ):
        raise _failure(
            "post_unit_checkpoint_invalid",
            "The post-unit checkpoint is not bound to the current prepared source.",
            origin="postcondition",
        )
    _inventory, review = _accepted_harness_semantics(prepared)
    semantic_judgments = review.get("semantic_judgments")
    if not isinstance(semantic_judgments, list):
        raise _failure(
            "post_unit_checkpoint_invalid",
            "The post-unit checkpoint lacks persisted semantic judgments.",
            origin="postcondition",
        )
    return TemplateAgentExecution(
        structured_output={
            "status": "complete",
            "summary": str(checkpoint.get("summary", "")),
            "semantic_judgments": semantic_judgments,
        },
        tool_uses=tuple(
            str(item) for item in checkpoint.get("tool_uses", []) if isinstance(item, str)
        ),
        skills_loaded=tuple(
            str(item) for item in checkpoint.get("skills_loaded", []) if isinstance(item, str)
        ),
        session_id=str(checkpoint.get("session_id", "")),
        backend=str(checkpoint.get("backend", "checkpoint")),
        num_turns=0,
        duration_ms=0,
        duration_api_ms=0,
        session_count=1,
        client_count=1,
        wall_duration_ms=int(checkpoint.get("wall_duration_ms", 0)),
        sdk_query_count=int(checkpoint.get("sdk_query_count", 0)),
        harness_feedback_attempts=int(checkpoint.get("harness_feedback_attempts", 0)),
        semantic_feedback_attempts=int(checkpoint.get("semantic_feedback_attempts", 0)),
        unit_boundary_checkpoint=_current_unit_boundary_checkpoint(prepared),
        timing_events=tuple(
            item for item in checkpoint.get("timing_events", []) if isinstance(item, dict)
        ),
    )


async def _checkpoint_for_request(
    prepared: PreparedTemplateTask,
    request: PrepareTemplateRequest,
) -> JsonObject:
    checkpoint_path = prepared.task_root / _UNIT_BOUNDARY_CHECKPOINT
    if request.force_rebuild_checkpoint != _UNIT_BOUNDARY_STAGE and checkpoint_path.exists():
        return _load_unit_boundary_checkpoint(prepared)
    checkpoint = await run_unit_boundary_checkpoint(prepared)
    return _validate_unit_boundary_checkpoint(prepared, checkpoint)


async def run_prepare_template(
    request: PrepareTemplateRequest,
    *,
    agent_runner: AgentRunner = run_template_agent,
) -> PrepareTemplateReport:
    _validate_stage_request(request)
    prepared = prepare_template_task(request)
    if request.until_stage == _UNIT_BOUNDARY_STAGE:
        checkpoint = await _checkpoint_for_request(prepared, request)
        _write_agent_trace(
            prepared,
            backend=str(checkpoint.get("backend", "checkpoint")),
            session_id=str(checkpoint.get("session_id", "")),
            tool_uses=tuple(
                str(item) for item in checkpoint.get("tool_uses", []) if isinstance(item, str)
            ),
            skills_loaded=tuple(
                str(item) for item in checkpoint.get("skills_loaded", []) if isinstance(item, str)
            ),
            structured_output={
                "status": "checkpointed",
                "checkpoint": _UNIT_BOUNDARY_STAGE,
                "summary": checkpoint.get("summary", ""),
                "unit_count": checkpoint.get("unit_count", 0),
            },
            wall_duration_ms=int(checkpoint.get("wall_duration_ms", 0)),
            sdk_query_count=int(checkpoint.get("sdk_query_count", 0)),
            harness_feedback_attempts=int(checkpoint.get("harness_feedback_attempts", 0)),
            permission_events=tuple(
                item for item in checkpoint.get("permission_events", []) if isinstance(item, dict)
            ),
            unit_boundary_checkpoint=checkpoint,
            timing_events=tuple(
                item for item in checkpoint.get("timing_events", []) if isinstance(item, dict)
            ),
        )
        return _unit_boundary_checkpoint_report(prepared, checkpoint)
    completed = _load_completed(prepared)
    if completed is not None:
        execution, publication = completed
        _inputs_unchanged(prepared)
        return _report(prepared, execution, publication)

    unit_boundary_checkpoint: JsonObject | None = None
    checkpoint_execution = (
        _load_post_unit_checkpoint_execution(prepared) if request.until_stage is None else None
    )
    reusing_post_unit_checkpoint = checkpoint_execution is not None
    if checkpoint_execution is not None:
        execution = checkpoint_execution
    elif request.resume_proof is not None or request.from_stage == _UNIT_BOUNDARY_STAGE:
        unit_boundary_checkpoint = _load_unit_boundary_checkpoint(
            prepared,
            request.resume_proof,
        )
        atomic_write_json(prepared.task_root / _UNIT_BOUNDARY_CHECKPOINT, unit_boundary_checkpoint)
    else:
        checkpoint_execution = None
    if checkpoint_execution is None:
        if agent_runner is run_template_agent:
            execution = await run_template_agent(
                prepared,
                unit_boundary_checkpoint=unit_boundary_checkpoint,
                stop_after_post_unit=request.until_stage == _POST_UNIT_STAGE,
            )
        else:
            execution = await agent_runner(prepared)
    host_started = time.perf_counter()
    timing_events = list(execution.timing_events)
    input_event: JsonObject | None = None
    checkpoint_event: JsonObject | None = None
    candidate_event: JsonObject | None = None
    publication_event: JsonObject | None = None
    try:
        input_event = _start_timing_event(
            timing_events,
            started=host_started,
            stage="host-post-agent",
            operation="input_integrity_check",
        )
        _inputs_unchanged(prepared)
        _finish_timing_event(input_event, started=host_started, status="ok")
        input_event = None
        if request.until_stage == _POST_UNIT_STAGE:
            checkpoint_event = _start_timing_event(
                timing_events,
                started=host_started,
                stage=_POST_UNIT_STAGE,
                operation="post_unit_checkpoint_report",
            )
            report = _post_unit_checkpoint_report(prepared, execution)
            _finish_timing_event(checkpoint_event, started=host_started, status="ok")
            checkpoint_event = None
            _write_agent_trace(
                prepared,
                execution=execution,
                timing_events=tuple(timing_events),
            )
            return report
        candidate_event = _start_timing_event(
            timing_events,
            started=host_started,
            stage="host-post-agent",
            operation="host_candidate_selection",
            semantic_coverage_already_accepted=reusing_post_unit_checkpoint,
        )
        candidate, visual_review, validation = _validate_agent_completion(
            prepared,
            execution,
            semantic_coverage_already_accepted=reusing_post_unit_checkpoint,
        )
        _finish_timing_event(
            candidate_event,
            started=host_started,
            status="ok",
            candidate=str(candidate.relative_to(prepared.task_root))
            if candidate.is_relative_to(prepared.task_root)
            else str(candidate),
        )
        candidate_event = None
        publication_event = _start_timing_event(
            timing_events,
            started=host_started,
            stage="host-post-agent",
            operation="publish_template_artifact",
        )
        publication = publish_template_artifact(
            task_root=prepared.task_root,
            source_docx=prepared.template_path,
            candidate_docx=candidate,
            field_registry=prepared.registry_source,
            validation=validation,
            visual_review=visual_review,
            allow_no_slots=_accepted_semantics_allow_no_slots(prepared),
        )
        _finish_timing_event(
            publication_event,
            started=host_started,
            status=str(publication.get("status", "unknown")),
        )
        publication_event = None
    except ToolFailure as error:
        if input_event is not None and "duration_ms" not in input_event:
            _finish_timing_event(
                input_event,
                started=host_started,
                status="error",
                error_code=error.code,
            )
        if checkpoint_event is not None and "duration_ms" not in checkpoint_event:
            _finish_timing_event(
                checkpoint_event,
                started=host_started,
                status="error",
                error_code=error.code,
            )
        if candidate_event is not None and "duration_ms" not in candidate_event:
            _finish_timing_event(
                candidate_event,
                started=host_started,
                status="error",
                error_code=error.code,
            )
        if publication_event is not None and "duration_ms" not in publication_event:
            _finish_timing_event(
                publication_event,
                started=host_started,
                status="error",
                error_code=error.code,
            )
        _write_agent_trace(
            prepared,
            execution=execution,
            failure=_failure_evidence(error),
            timing_events=tuple(timing_events),
        )
        raise
    _write_agent_trace(
        prepared,
        execution=execution,
        publication=publication,
        timing_events=tuple(timing_events),
    )
    return _report(prepared, execution, publication)

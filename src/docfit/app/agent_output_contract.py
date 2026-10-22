"""Run and validate the post-unit Agent output contract without later stages."""

from __future__ import annotations

import asyncio
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.prepare_template import (
    PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS,
    PREPARE_TEMPLATE_TIMEOUT_SECONDS,
    PreparedTemplateTask,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _load_unit_boundary_checkpoint,
    _post_unit_inventory_from_checkpoint,
    _run_unit_boundary_checkpoint,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
)
from docfit.app.sdk_execution import SDKResultMetrics
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.template.judgment_shape import mechanical_feedback, validate_ordered_semantic_parts
from docfit.tools.runtime import JsonObject, ToolFailure, atomic_write_json
from docfit.tools.surface import DOCFIT_EVIDENCE_TOOL

AGENT_OUTPUT_STAGE = "agent-output"
AGENT_OUTPUT_CONTRACT_SCHEMA_VERSION = "docfit-agent-output-contract/v1"
AGENT_OUTPUT_PROOF = "work/.docfit/agent-output-contract.json"
AGENT_OUTPUT_RAW_OUTPUT = "work/.docfit/agent-output.json"
_UNIT_EVIDENCE_FOCUS = "unit_evidence_packet"


@dataclass(frozen=True, slots=True)
class AgentOutputContractRequest:
    school_template: Path
    output_directory: Path
    school_requirements: Path | None = None
    field_registry: Path | None = None
    resume_proof: Path | None = None


@dataclass(frozen=True, slots=True)
class AgentOutputContractReport:
    status: Literal["checkpointed"]
    task_root: str
    proof_path: str
    raw_output_path: str
    template_sha256: str
    counts: JsonObject
    backend: str
    session_id: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    num_turns: int
    duration_ms: int
    duration_api_ms: int
    wall_duration_ms: int


def _json_safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    return str(value)


def _tool_request(name: str, tool_input: Any) -> JsonObject:
    safe_input = _json_safe(tool_input)
    return {
        "name": name,
        "input": safe_input if isinstance(safe_input, dict) else {},
    }


def _used_unit_evidence_packet(tool_requests: Sequence[JsonObject]) -> bool:
    expected_names = {DOCFIT_EVIDENCE_TOOL, f"mcp__docfit__{DOCFIT_EVIDENCE_TOOL}"}
    for request in tool_requests:
        name = request.get("name")
        tool_input = request.get("input")
        if name not in expected_names or not isinstance(tool_input, dict):
            continue
        if tool_input.get("focus") == _UNIT_EVIDENCE_FOCUS:
            return True
    return False


def _feedback(
    *,
    code: str,
    message: str,
    field: str,
    suggested_actions: Sequence[str],
) -> JsonObject:
    return mechanical_feedback(
        feedback_type="agent_output_contract",
        code=code,
        message=message,
        origin="postcondition",
        blockers=[
            {
                "code": code,
                "field": field,
                "message": message,
            }
        ],
        suggested_actions=suggested_actions,
        agent_action=(
            "Read the current unit_evidence_packet and return semantic_judgments with "
            "source_entry_id plus ordered parts. Select field_id values only from that "
            "packet's field_id_vocabulary."
        ),
    )


def _allowed_field_ids(inventory: JsonObject) -> tuple[str, ...]:
    vocabulary = inventory.get("field_id_vocabulary")
    if not isinstance(vocabulary, dict):
        return ()
    raw_ids = vocabulary.get("allowed_field_ids")
    if not isinstance(raw_ids, list):
        return ()
    return tuple(item.strip() for item in raw_ids if isinstance(item, str) and item.strip())


def _reading_block_ids(inventory: JsonObject) -> tuple[str, ...]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return ()
    return tuple(
        item["block_id"].strip()
        for item in raw_blocks
        if isinstance(item, dict)
        and isinstance(item.get("block_id"), str)
        and item["block_id"].strip()
    )


def _reading_range_ids(inventory: JsonObject) -> tuple[str, ...]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return ()
    range_ids: list[str] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        for key in ("range_id", "unit_range_id"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                range_ids.append(value.strip())
    return tuple(dict.fromkeys(range_ids))


def _source_entry_ids(inventory: JsonObject) -> tuple[str, ...]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return ()
    return tuple(
        item["source_entry_id"].strip()
        for item in raw_entries
        if isinstance(item, dict)
        and isinstance(item.get("source_entry_id"), str)
        and item["source_entry_id"].strip()
    )


def _semantic_judgments(output: JsonObject) -> list[Any]:
    judgments = output.get("semantic_judgments")
    return judgments if isinstance(judgments, list) else []


def _semantic_part_count(judgments: Sequence[Any]) -> int:
    count = 0
    for judgment in judgments:
        if not isinstance(judgment, dict):
            continue
        parts = judgment.get("parts")
        if isinstance(parts, list):
            count += len(parts)
    return count


def _field_reference_count(judgments: Sequence[Any]) -> int:
    count = 0
    for judgment in judgments:
        if not isinstance(judgment, dict):
            continue
        parts = judgment.get("parts")
        if not isinstance(parts, list):
            continue
        count += sum(
            1
            for part in parts
            if isinstance(part, dict)
            and isinstance(part.get("field_id"), str)
            and part["field_id"].strip()
        )
    return count


def agent_output_contract_feedback(
    *,
    structured_output: JsonObject,
    inventory: JsonObject,
    tool_requests: Sequence[JsonObject],
) -> JsonObject | None:
    """Return contract feedback for raw Agent output, without Harness mapping."""

    if structured_output.get("status") != "complete":
        return _feedback(
            code="agent_output_not_complete",
            field="status",
            message="Agent output must be complete before its semantic_judgments can be checked.",
            suggested_actions=(
                "Return status=complete with semantic_judgments, or keep this run blocked.",
            ),
        )
    if not _used_unit_evidence_packet(tool_requests):
        return _feedback(
            code="agent_output_unit_packet_not_observed",
            field="tool_requests",
            message=(
                "Agent-output proof requires a real docfit_evidence "
                "focus=unit_evidence_packet tool request in this SDK run."
            ),
            suggested_actions=(
                "Run the post-unit Agent against unit_evidence_packet before validating output.",
            ),
        )
    vocabulary = inventory.get("field_id_vocabulary")
    if not isinstance(vocabulary, dict):
        return _feedback(
            code="agent_output_field_vocabulary_missing",
            field="field_id_vocabulary",
            message="Agent-output proof requires the pre-input field_id_vocabulary.",
            suggested_actions=("Prepare the task with an input field Registry.",),
        )
    source_entry_ids = _source_entry_ids(inventory)
    if not source_entry_ids:
        return _feedback(
            code="agent_output_source_entries_missing",
            field="source_entries",
            message=(
                "Agent-output proof requires canonical source entries from the current "
                "unit reading packet."
            ),
            suggested_actions=("Rebuild the unit_evidence_packet for the accepted unit.",),
        )

    result = validate_ordered_semantic_parts(
        structured_output.get("semantic_judgments"),
        allowed_field_ids=_allowed_field_ids(inventory),
        source_entry_ids=source_entry_ids,
        field_vocabulary=vocabulary,
    )
    if result.get("status") != "ok":
        return result
    return None


def _agent_output_contract_proof(
    *,
    prepared: PreparedTemplateTask,
    execution: TemplateAgentExecution,
    inventory: JsonObject,
    tool_requests: Sequence[JsonObject],
) -> JsonObject:
    feedback = agent_output_contract_feedback(
        structured_output=execution.structured_output,
        inventory=inventory,
        tool_requests=tool_requests,
    )
    if feedback is not None:
        raise ToolFailure(
            status="needs_input",
            origin="postcondition",
            code="agent_output_contract_invalid",
            message="Raw Agent output did not pass the Agent I/O contract.",
            retryable=True,
            suggested_actions=tuple(
                str(item)
                for item in (
                    feedback.get("failure", {}).get("suggested_actions", [])
                    if isinstance(feedback.get("failure"), dict)
                    else []
                )
            ),
        )

    judgments = _semantic_judgments(execution.structured_output)
    vocabulary = inventory.get("field_id_vocabulary")
    field_vocabulary_digest = (
        vocabulary.get("digest") if isinstance(vocabulary, dict) else None
    )
    if not isinstance(field_vocabulary_digest, str):
        field_vocabulary_digest = inventory.get("field_vocabulary_digest")
    return {
        "schema_version": AGENT_OUTPUT_CONTRACT_SCHEMA_VERSION,
        "checkpoint": AGENT_OUTPUT_STAGE,
        "status": "ok",
        "source_hash": prepared.template_sha256,
        "agent_output": AGENT_OUTPUT_RAW_OUTPUT,
        "unit_boundary_checkpoint": "work/.docfit/unit-boundary-checkpoint.json",
        "field_vocabulary_digest": field_vocabulary_digest,
        "checks": [
            {"name": "unit_evidence_packet_tool_use", "result": "ok"},
            {"name": "field_id_vocabulary_present", "result": "ok"},
            {"name": "ordered_semantic_parts", "result": "ok"},
            {"name": "harness_mapping_not_run", "result": "not_run"},
            {"name": "word_materialization_not_run", "result": "not_run"},
            {"name": "publication_not_run", "result": "not_run"},
        ],
        "counts": {
            "judgment_count": len(judgments),
            "part_count": _semantic_part_count(judgments),
            "field_reference_count": _field_reference_count(judgments),
            "reading_block_count": len(_reading_block_ids(inventory)),
            "reading_range_count": len(_reading_range_ids(inventory)),
        },
        "not_proven": [
            "harness_semantic_mapping",
            "word_materialization",
            "publication",
            "product_acceptance",
        ],
        "backend": execution.backend,
        "session_id": execution.session_id,
        "tool_uses": list(execution.tool_uses),
        "skills_loaded": list(execution.skills_loaded),
        "tool_requests": list(tool_requests),
        "sdk_query_count": execution.sdk_query_count,
        "wall_duration_ms": execution.wall_duration_ms,
    }


async def _run_agent_output_only(
    *,
    prepared: PreparedTemplateTask,
    backend: AgentBackend,
    config_directory: Path,
    unit_boundary_checkpoint: JsonObject,
) -> tuple[TemplateAgentExecution, tuple[JsonObject, ...]]:
    tool_uses: list[str] = []
    tool_requests: list[JsonObject] = []
    skills_loaded: list[str] = []
    started = time.perf_counter()
    options = build_prepare_template_options(
        prepared,
        backend,
        config_directory,
        stop_after_post_unit=True,
    )
    result: ResultMessage | None = None
    async with ClaudeSDKClient(options=options) as client:
        async with asyncio.timeout(PREPARE_TEMPLATE_TIMEOUT_SECONDS):
            await client.query(
                build_prepare_template_prompt(
                    prepared,
                    unit_boundary_checkpoint,
                    stop_after_post_unit=True,
                )
            )
            responses = client.receive_response().__aiter__()
            while True:
                try:
                    message = await asyncio.wait_for(
                        anext(responses),
                        timeout=PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS,
                    )
                except StopAsyncIteration:
                    break
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if not isinstance(block, ToolUseBlock):
                            continue
                        tool_uses.append(block.name)
                        tool_requests.append(_tool_request(block.name, block.input))
                        if block.name == "Skill":
                            skill = block.input.get("skill") or block.input.get("name")
                            if isinstance(skill, str):
                                skills_loaded.append(skill)
                if isinstance(message, ResultMessage):
                    result = message

    if result is None or result.is_error or not isinstance(result.structured_output, dict):
        raise ToolFailure(
            status="error",
            origin="agent",
            code="agent_output_result_invalid",
            message="The Agent-output contract run did not return structured output.",
            retryable=True,
        )
    metrics = SDKResultMetrics.from_result(result)
    return (
        TemplateAgentExecution(
            structured_output=result.structured_output,
            tool_uses=tuple(tool_uses),
            skills_loaded=tuple(dict.fromkeys(skills_loaded)),
            session_id=result.session_id,
            backend=backend.name,
            num_turns=metrics.num_turns,
            duration_ms=metrics.duration_ms,
            duration_api_ms=metrics.duration_api_ms,
            wall_duration_ms=round((time.perf_counter() - started) * 1000),
            sdk_query_count=1,
            unit_boundary_checkpoint=unit_boundary_checkpoint,
        ),
        tuple(tool_requests),
    )


async def _unit_boundary_checkpoint_for_request(
    *,
    prepared: PreparedTemplateTask,
    request: AgentOutputContractRequest,
) -> JsonObject:
    if request.resume_proof is not None:
        checkpoint = _load_unit_boundary_checkpoint(prepared, request.resume_proof)
        atomic_write_json(
            prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json",
            checkpoint,
        )
        return checkpoint
    backends = tuple(iter_agent_backends())
    if not backends:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="agent_backend_not_configured",
            message="No configured Agent backend is available for unit-boundary discovery.",
        )
    for backend in backends:
        with tempfile.TemporaryDirectory(prefix="docfit-agent-output-unit-") as config_name:
            return await _run_unit_boundary_checkpoint(prepared, backend, Path(config_name))
    raise AssertionError("iter_agent_backends returned a non-empty tuple")


async def run_agent_output_contract(
    request: AgentOutputContractRequest,
) -> AgentOutputContractReport:
    prepared = prepare_template_task(
        PrepareTemplateRequest(
            school_template=request.school_template,
            output_directory=request.output_directory,
            school_requirements=request.school_requirements,
            field_registry=request.field_registry,
        )
    )
    unit_boundary_checkpoint = await _unit_boundary_checkpoint_for_request(
        prepared=prepared,
        request=request,
    )
    inventory = _post_unit_inventory_from_checkpoint(prepared, unit_boundary_checkpoint)
    backends = tuple(iter_agent_backends())
    if not backends:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="agent_backend_not_configured",
            message="No configured Agent backend is available for template preparation.",
        )

    failures: list[str] = []
    last_failure: ToolFailure | None = None
    for backend in backends:
        try:
            with tempfile.TemporaryDirectory(prefix="docfit-agent-output-sdk-") as config_name:
                execution, tool_requests = await _run_agent_output_only(
                    prepared=prepared,
                    backend=backend,
                    config_directory=Path(config_name),
                    unit_boundary_checkpoint=unit_boundary_checkpoint,
                )
            proof = _agent_output_contract_proof(
                prepared=prepared,
                execution=execution,
                inventory=inventory,
                tool_requests=tool_requests,
            )
            atomic_write_json(
                prepared.task_root / AGENT_OUTPUT_RAW_OUTPUT,
                execution.structured_output,
            )
            atomic_write_json(prepared.task_root / AGENT_OUTPUT_PROOF, proof)
            return AgentOutputContractReport(
                status="checkpointed",
                task_root=str(prepared.task_root),
                proof_path=str(prepared.task_root / AGENT_OUTPUT_PROOF),
                raw_output_path=str(prepared.task_root / AGENT_OUTPUT_RAW_OUTPUT),
                template_sha256=prepared.template_sha256,
                counts=dict(proof["counts"]) if isinstance(proof.get("counts"), dict) else {},
                backend=execution.backend,
                session_id=execution.session_id,
                tool_uses=execution.tool_uses,
                skills_loaded=execution.skills_loaded,
                num_turns=execution.num_turns,
                duration_ms=execution.duration_ms,
                duration_api_ms=execution.duration_api_ms,
                wall_duration_ms=execution.wall_duration_ms,
            )
        except (TimeoutError, ToolFailure) as error:
            if isinstance(error, ToolFailure):
                last_failure = error
                failures.append(error.code)
            else:
                failures.append("agent_output_timeout")

    if len(backends) == 1 and last_failure is not None:
        raise last_failure
    raise ToolFailure(
        status="error",
        origin="agent",
        code="agent_output_backends_exhausted",
        message="No configured backend completed the Agent-output contract run: "
        + ", ".join(failures),
        retryable=True,
    )

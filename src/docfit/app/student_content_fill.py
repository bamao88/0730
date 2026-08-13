"""Independent Student Content -> Placement -> template-fill debug slice."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import tempfile
import time
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree import ElementTree as ET

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    ToolUseBlock,
)

from docfit.app.agent import AGENT_SDK_MAX_BUFFER_BYTES, project_root
from docfit.app.sdk_execution import SDKResultMetrics
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.content.extraction import (
    extraction_output_schema,
    registry_semantic_lexicon,
    validate_extraction,
)
from docfit.content.fill import fill_template
from docfit.content.placement import build_placement, load_fill_contract
from docfit.content.projection import project_student_content, resolve_template_style_map
from docfit.content.quality_patches import load_quality_patches
from docfit.content.student import build_student_inventory
from docfit.content.style_application import apply_and_validate_candidate_styles
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.observability.transcript import SDKTranscriptManager, isolated_sdk_environment
from docfit.styles import StyleContractSet
from docfit.tools.inspection import inspect_document
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    read_json,
    sha256_file,
    sha256_json,
)
from docfit.tools.service import DocFitToolService
from docfit.visual.evidence import EvidenceStore

STUDENT_EXTRACTION_TIMEOUT_SECONDS = 600
STUDENT_EXTRACTION_BATCH_SIZE = 32
STUDENT_EXTRACTION_BATCH_TEXT_BYTES = 24_000
STUDENT_EXTRACTION_CONCURRENCY = 3
STUDENT_EXTRACTION_CONTEXT_ITEMS = 3
STUDENT_EXTRACTION_MAX_ATTEMPTS_PER_BACKEND = 2
STUDENT_EXTRACTION_CHECKPOINT_VERSION = 1
_ALLOWED_EXTRACTION_TOOLS = frozenset({"StructuredOutput"})


@dataclass(frozen=True, slots=True)
class StudentContentExtractionRequest:
    source_docx: Path
    field_registry: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class PreparedStudentContentExtraction:
    task_root: Path
    source_docx: Path
    field_registry: Path
    inventory_path: Path
    source_sha256: str
    registry_sha256: str
    inventory: JsonObject
    batch: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class StudentContentFillRequest:
    source_docx: Path
    template_docx: Path
    fill_contract: Path
    field_registry: Path
    output_directory: Path
    quality_patches: Path | None = None


@dataclass(frozen=True, slots=True)
class PreparedStudentContentFill:
    task_root: Path
    extraction: PreparedStudentContentExtraction
    source_docx: Path
    template_docx: Path
    fill_contract: Path
    field_registry: Path
    quality_patches: Path | None
    inventory_path: Path
    candidate_docx: Path
    source_sha256: str
    template_sha256: str
    contract_sha256: str
    registry_sha256: str
    quality_patches_sha256: str | None
    inventory: JsonObject


@dataclass(frozen=True, slots=True)
class StudentExtractionExecution:
    structured_output: JsonObject
    backend: str
    session_id: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]
    num_turns: int = 0
    duration_ms: int = 0
    duration_api_ms: int = 0
    total_cost_usd: float | None = None
    usage: JsonObject | None = None
    attempt_evidence: tuple[JsonObject, ...] = ()
    batch_evidence: tuple[JsonObject, ...] = ()


StudentExtractionRunner = Callable[
    [str, PreparedStudentContentExtraction, JsonObject, SDKTranscriptManager],
    Awaitable[StudentExtractionExecution],
]


def prepare_student_content_extraction(
    request: StudentContentExtractionRequest,
    *,
    office: OfficeCliAdapter | None = None,
) -> PreparedStudentContentExtraction:
    """Create an extraction-only snapshot with no template or Fill Contract access."""

    source = _input_file(request.source_docx, ".docx", "source_docx")
    registry_path = _input_file(request.field_registry, ".yaml", "field_registry")
    source_hash = sha256_file(source)
    registry_hash = sha256_file(registry_path)
    FieldRegistrySnapshot.load(registry_path)
    output = request.output_directory.expanduser().resolve()
    if output.exists():
        if not output.is_dir() or output.is_symlink():
            raise _failure(
                "student_extraction_output_not_directory",
                "The extraction output path must be a regular directory.",
            )
        if any(output.iterdir()):
            return _resume_student_content_extraction(
                output,
                source_sha256=source_hash,
                registry_sha256=registry_hash,
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-prepare-", dir=output.parent))
    try:
        input_directory = temporary / "input"
        work_directory = temporary / "work"
        input_directory.mkdir()
        work_directory.mkdir()
        source_copy = input_directory / "student.docx"
        registry_copy = input_directory / "content-fields.yaml"
        shutil.copy2(source, source_copy)
        shutil.copy2(registry_path, registry_copy)
        if (
            sha256_file(source) != source_hash
            or sha256_file(registry_path) != registry_hash
            or sha256_file(source_copy) != source_hash
            or sha256_file(registry_copy) != registry_hash
        ):
            raise _failure(
                "student_extraction_input_changed",
                "An extraction input changed while its private snapshot was prepared.",
            )
        inspection = inspect_document(source_copy, office or OfficeCliAdapter())
        inventory = build_student_inventory(inspection, source_docx=source_copy)
        atomic_write_json(work_directory / "student-inventory.json", inventory)
        source_copy.chmod(0o444)
        registry_copy.chmod(0o444)
        input_directory.chmod(0o555)
        if output.exists():
            output.rmdir()
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return PreparedStudentContentExtraction(
        task_root=output,
        source_docx=output / "input" / "student.docx",
        field_registry=output / "input" / "content-fields.yaml",
        inventory_path=output / "work" / "student-inventory.json",
        source_sha256=source_hash,
        registry_sha256=registry_hash,
        inventory=inventory,
    )


def _resume_student_content_extraction(
    task_root: Path,
    *,
    source_sha256: str,
    registry_sha256: str,
) -> PreparedStudentContentExtraction:
    """Resume only an identity-bound extraction task created by this module."""

    source = task_root / "input" / "student.docx"
    registry = task_root / "input" / "content-fields.yaml"
    inventory_path = task_root / "work" / "student-inventory.json"
    required = (source, registry, inventory_path)
    if any(path.is_symlink() or not path.is_file() for path in required):
        raise _failure(
            "student_extraction_output_not_resumable",
            "The non-empty extraction directory is not a complete DocFit extraction task.",
        )
    if sha256_file(source) != source_sha256 or sha256_file(registry) != registry_sha256:
        raise _failure(
            "student_extraction_resume_input_mismatch",
            "The existing extraction task is bound to different source inputs.",
        )
    FieldRegistrySnapshot.load(registry)
    inventory = read_json(inventory_path)
    if (
        inventory.get("schema_version") != "docfit-student-source-inventory/v2"
        or inventory.get("source_sha256") != source_sha256
        or not isinstance(inventory.get("content_items"), list)
    ):
        raise _failure(
            "student_extraction_resume_inventory_invalid",
            "The existing extraction task has a stale or invalid Source Inventory.",
        )
    return PreparedStudentContentExtraction(
        task_root=task_root,
        source_docx=source,
        field_registry=registry,
        inventory_path=inventory_path,
        source_sha256=source_sha256,
        registry_sha256=registry_sha256,
        inventory=inventory,
    )


def prepare_student_content_fill(
    request: StudentContentFillRequest,
    *,
    office: OfficeCliAdapter | None = None,
) -> PreparedStudentContentFill:
    """Create a private task snapshot and a complete local source-object inventory."""

    source = _input_file(request.source_docx, ".docx", "source_docx")
    template = _input_file(request.template_docx, ".docx", "template_docx")
    contract_path = _input_file(request.fill_contract, ".yaml", "fill_contract")
    registry_path = _input_file(request.field_registry, ".yaml", "field_registry")
    quality_patches_path = (
        _input_file(request.quality_patches, ".yaml", "quality_patches")
        if request.quality_patches is not None
        else None
    )
    source_hash = sha256_file(source)
    template_hash = sha256_file(template)
    contract_hash = sha256_file(contract_path)
    registry_hash = sha256_file(registry_path)
    quality_patches_hash = (
        sha256_file(quality_patches_path) if quality_patches_path is not None else None
    )
    contract = load_fill_contract(contract_path)
    StyleContractSet.from_fill_contract(contract)
    registry = FieldRegistrySnapshot.load(registry_path)
    if contract.get("template_sha256") != template_hash:
        raise _failure("prepare_template_stale", "The fill contract does not bind this template.")
    registry_ref = contract.get("field_registry_ref")
    if not isinstance(registry_ref, dict) or any(
        registry_ref.get(key) != registry.identity()[key]
        for key in ("registry_id", "registry_version", "sha256")
    ):
        raise _failure(
            "prepare_registry_stale",
            "The fill contract does not bind this Registry snapshot.",
        )
    output = request.output_directory.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise _failure(
            "student_fill_output_not_empty",
            "The student-fill output directory must be absent or empty.",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-prepare-", dir=output.parent))
    try:
        input_directory = temporary / "input"
        work_directory = temporary / "work"
        extraction_input_directory = temporary / "extraction" / "input"
        input_directory.mkdir()
        work_directory.mkdir()
        extraction_input_directory.mkdir(parents=True)
        copies = {
            source: input_directory / "student.docx",
            template: input_directory / "template.docx",
            contract_path: input_directory / "fill-contract.yaml",
            registry_path: input_directory / "content-fields.yaml",
        }
        if quality_patches_path is not None:
            copies[quality_patches_path] = input_directory / "quality-patches.yaml"
        for original, copied in copies.items():
            shutil.copy2(original, copied)
        extraction_source = extraction_input_directory / "student.docx"
        extraction_registry = extraction_input_directory / "content-fields.yaml"
        shutil.copy2(source, extraction_source)
        shutil.copy2(registry_path, extraction_registry)
        expected_hashes = {
            source: source_hash,
            template: template_hash,
            contract_path: contract_hash,
            registry_path: registry_hash,
        }
        if quality_patches_path is not None and quality_patches_hash is not None:
            expected_hashes[quality_patches_path] = quality_patches_hash
        if any(
            sha256_file(original) != expected_hash or sha256_file(copies[original]) != expected_hash
            for original, expected_hash in expected_hashes.items()
        ):
            raise _failure(
                "student_fill_input_changed",
                "An input changed while the private task snapshot was prepared.",
            )
        if (
            sha256_file(extraction_source) != source_hash
            or sha256_file(extraction_registry) != registry_hash
        ):
            raise _failure(
                "student_fill_input_changed",
                "The extraction-only input snapshot does not match the bound inputs.",
            )
        source_copy = copies[source]
        inspection = inspect_document(source_copy, office or OfficeCliAdapter())
        inventory = build_student_inventory(inspection, source_docx=source_copy)
        inventory_path = work_directory / "student-inventory.json"
        atomic_write_json(inventory_path, inventory)
        if quality_patches_path is not None:
            load_quality_patches(
                copies[quality_patches_path],
                source_sha256=source_hash,
                inventory=inventory,
            )
        for copied in copies.values():
            copied.chmod(0o444)
        extraction_source.chmod(0o444)
        extraction_registry.chmod(0o444)
        input_directory.chmod(0o555)
        extraction_input_directory.chmod(0o555)
        if output.exists():
            output.rmdir()
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return PreparedStudentContentFill(
        task_root=output,
        extraction=PreparedStudentContentExtraction(
            task_root=output / "extraction",
            source_docx=output / "extraction" / "input" / "student.docx",
            field_registry=(
                output / "extraction" / "input" / "content-fields.yaml"
            ),
            inventory_path=output / "work" / "student-inventory.json",
            source_sha256=source_hash,
            registry_sha256=registry_hash,
            inventory=inventory,
        ),
        source_docx=output / "input" / "student.docx",
        template_docx=output / "input" / "template.docx",
        fill_contract=output / "input" / "fill-contract.yaml",
        field_registry=output / "input" / "content-fields.yaml",
        quality_patches=(
            output / "input" / "quality-patches.yaml"
            if quality_patches_path is not None
            else None
        ),
        inventory_path=output / "work" / "student-inventory.json",
        candidate_docx=output / "candidate.docx",
        source_sha256=source_hash,
        template_sha256=template_hash,
        contract_sha256=contract_hash,
        registry_sha256=registry_hash,
        quality_patches_sha256=quality_patches_hash,
        inventory=inventory,
    )


def build_student_extraction_prompt(prepared: PreparedStudentContentExtraction) -> str:
    registry = FieldRegistrySnapshot.load(prepared.field_registry)
    all_content_items = prepared.inventory.get("content_items")
    if not isinstance(all_content_items, list):
        raise _failure(
            "student_extraction_inventory_invalid",
            "The extraction inventory has no ordered content items.",
        )
    batch = prepared.batch or {}
    primary_ids = batch.get("primary_content_ids")
    context_ids = batch.get("context_content_ids")
    if primary_ids is None:
        primary_ids = [item.get("source_content_id") for item in all_content_items]
    if context_ids is None:
        context_ids = primary_ids
    if not isinstance(primary_ids, list) or not isinstance(context_ids, list):
        raise _failure(
            "student_extraction_batch_invalid",
            "The extraction batch scope is invalid.",
        )
    by_id = {
        str(item.get("source_content_id")): item
        for item in all_content_items
        if isinstance(item, dict) and isinstance(item.get("source_content_id"), str)
    }
    primary_id_set = {str(value) for value in primary_ids}
    primary_items = [by_id[str(value)] for value in primary_ids if str(value) in by_id]
    context_items = [
        by_id[str(value)]
        for value in context_ids
        if str(value) in by_id and str(value) not in primary_id_set
    ]
    if len(primary_items) != len(primary_ids):
        raise _failure(
            "student_extraction_batch_invalid",
            "The extraction batch cites a stale source content item.",
        )
    task = {
        "schema_version": 3,
        "student_docx": {
            "sha256": prepared.source_sha256,
            "read_only": True,
        },
        "inventory_facts": {
            "object_count": prepared.inventory.get("object_count"),
            "content_item_count": prepared.inventory.get("content_item_count"),
            "transferable_object_count": prepared.inventory.get("transferable_object_count"),
            "semantic_neutral_profile": prepared.inventory.get(
                "semantic_neutral_profile"
            ),
        },
        "batch": {
            "index": batch.get("index", 1),
            "count": batch.get("count", 1),
            "primary_content_ids": primary_ids,
        },
        "ordered_source_content_items_to_annotate": [
            _student_annotation_view(item) for item in primary_items
        ],
        "adjacent_context_items_do_not_annotate": [
            _student_annotation_view(item) for item in context_items
        ],
        "registry_semantic_lexicon": registry_semantic_lexicon(registry),
    }
    return (
        "Semantically annotate every ordered source content item in the bound read-only "
        "student thesis DOCX. The deterministic Source Inventory is the complete authoritative "
        "Word fact layer for this task; do not inspect or read the DOCX again. "
        "This is extraction only: do not edit, render, validate, write files, use Bash, ask "
        "the user, or delegate. The ordered_source_content_items array is immutable source "
        "evidence: do not add, omit, merge, split, or reorder its keys. Annotate only "
        "ordered_source_content_items_to_annotate and return exactly one "
        "annotation under each existing source_content_id. The Registry is a read-only semantic "
        "dictionary: use only field_id, label, meaning, and content_type; it does not define "
        "presence, requiredness, placement, or order. Bind a field_id only when the content item "
        "is that semantic kind. Treat source_facts and semantic_neutral_profile as neutral Word "
        "evidence, not as semantic decisions. Infer one consistent numbering hierarchy across "
        "the document: chapter markers, decimal component depth, and parenthesized list markers "
        "must not be flattened into adjacent heading levels. When the document profile contains "
        "chinese_chapter markers, normally map chinese_chapter to body.heading.level1, "
        "decimal_1_component to body.heading.level2, decimal_2_component to "
        "body.heading.level3, and parenthesized_integer to body.numbered_list_item unless the "
        "surrounding source facts provide contrary evidence. A standalone region label such as "
        "an abstract or references label is layout_only when the Registry defines its contents "
        "but no corresponding label/title field; do not bind it to the nearest content field. "
        "Use unregistered, unresolved, unsupported, conflict, or "
        "layout_only instead of guessing. Values must be exact visible substrings; never "
        "translate, complete, normalize, or infer student facts. Describe explicit relations "
        "such as caption_of without changing order. Relations may cite adjacent context items, "
        "but at least one endpoint must be a primary item. Do not return any source_order, "
        "range, or body sequence field. Keep note absent unless it records a concrete ambiguity "
        "or non-classified decision. Do not produce a batch summary. Return only the requested "
        "structured output.\n\n"
        "CURRENT_TASK_JSON:\n"
        + json.dumps(task, ensure_ascii=False, sort_keys=True)
    )


def _student_annotation_view(item: JsonObject) -> JsonObject:
    """Project neutral Word facts into the minimum semantic-annotation input."""

    return {
        key: item[key]
        for key in (
            "source_content_id",
            "physical_type",
            "observed_text",
            "source_order",
            "source_facts",
        )
        if key in item
    }


def _plan_student_extraction_batches(
    content_items: list[JsonObject],
) -> list[list[JsonObject]]:
    """Keep source order while enforcing both item-count and prompt-payload budgets."""

    batches: list[list[JsonObject]] = []
    current: list[JsonObject] = []
    current_bytes = 0
    for item in content_items:
        item_bytes = len(
            json.dumps(
                _student_annotation_view(item),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        exceeds_count = len(current) >= STUDENT_EXTRACTION_BATCH_SIZE
        exceeds_bytes = bool(current) and (
            current_bytes + item_bytes > STUDENT_EXTRACTION_BATCH_TEXT_BYTES
        )
        if exceeds_count or exceeds_bytes:
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(item)
        current_bytes += item_bytes
    if current:
        batches.append(current)
    return batches


def _student_extraction_system_prompt() -> str:
    return (
        "You are the DocFit main Agent performing a read-only student-content extraction. "
        "Claude Agent SDK owns the single Agent session. The application owns inventory, "
        "schema validation, placement, and all writes after you return. Treat "
        "CURRENT_TASK_JSON Source Content Items as the complete "
        "hash-bound Word fact layer. Do not inspect, read, or mutate documents, and do not infer "
        "missing values. Object IDs, not page numbers, are evidence identities."
    )


def _build_student_extraction_options(
    *,
    task_root: Path,
    environment: dict[str, str],
    model: str,
    schema: JsonObject,
) -> ClaudeAgentOptions:
    """Build the extraction-only SDK runtime without template or editing capabilities."""

    agent_environment = dict(environment)
    agent_environment["DOCFIT_TASK_ROOT"] = str(task_root)
    # The application already owns explicit route attempts and a visible timeout. Avoid a
    # second, hidden retry multiplier inside each isolated CLI process.
    agent_environment["CLAUDE_CODE_MAX_RETRIES"] = "0"
    return ClaudeAgentOptions(
        tools=[],
        allowed_tools=[],
        disallowed_tools=[
            "Bash",
            "Write",
            "Edit",
            "Agent",
            "AskUserQuestion",
            "Web",
            "WebSearch",
            "WebFetch",
            "Read",
            "Glob",
            "Grep",
            "Skill",
        ],
        mcp_servers={},
        strict_mcp_config=True,
        permission_mode="default",
        agents={},
        setting_sources=[],
        skills=[],
        cwd=task_root,
        env=agent_environment,
        model=model,
        max_turns=2,
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format={"type": "json_schema", "schema": schema},
        system_prompt=_student_extraction_system_prompt(),
    )


async def _run_extraction_backend(
    prompt: str,
    prepared: PreparedStudentContentExtraction,
    schema: JsonObject,
    backend: AgentBackend,
    config_directory: Path,
) -> StudentExtractionExecution:
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    options = _build_student_extraction_options(
        task_root=prepared.task_root,
        environment=environment,
        model=backend.model,
        schema=schema,
    )
    result: ResultMessage | None = None
    tool_uses: list[str] = []
    skills_loaded: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tool_uses.append(block.name)
                        if block.name == "Skill":
                            skill = block.input.get("skill") or block.input.get("name")
                            if isinstance(skill, str):
                                skills_loaded.append(skill)
            elif isinstance(message, ResultMessage):
                result = message
    if result is None:
        raise _failure(
            "student_extraction_agent_result_missing",
            f"The {backend.name} Agent backend returned no terminal ResultMessage.",
            origin="engine",
            retryable=True,
        )
    terminal_reason = result.terminal_reason or "unknown"
    if result.is_error:
        status = result.api_error_status
        status_detail = f", http_status={status}" if status is not None else ""
        raise _failure(
            "student_extraction_agent_backend_error",
            (
                f"The {backend.name} Agent backend ended with an SDK error "
                f"(terminal_reason={terminal_reason}, turns={result.num_turns}"
                f"{status_detail})."
            ),
            origin="engine",
            retryable=status not in {400, 401, 402, 403},
        )
    if not isinstance(result.structured_output, dict):
        raise _failure(
            "student_extraction_agent_structured_output_missing",
            (
                f"The {backend.name} Agent backend returned no structured output "
                f"(terminal_reason={terminal_reason}, turns={result.num_turns}, "
                f"result_text_present={bool(result.result)})."
            ),
            origin="engine",
            retryable=True,
        )
    metrics = SDKResultMetrics.from_result(result)
    return StudentExtractionExecution(
        structured_output=result.structured_output,
        backend=backend.name,
        session_id=result.session_id,
        tool_uses=tuple(tool_uses),
        skills_loaded=tuple(dict.fromkeys(skills_loaded)),
        num_turns=metrics.num_turns,
        duration_ms=metrics.duration_ms,
        duration_api_ms=metrics.duration_api_ms,
        total_cost_usd=metrics.total_cost_usd,
        usage=metrics.usage,
    )


async def run_student_extraction_agent(
    prompt: str,
    prepared: PreparedStudentContentExtraction,
    schema: JsonObject,
    transcripts: SDKTranscriptManager,
) -> StudentExtractionExecution:
    backends = tuple(iter_agent_backends())
    if not backends:
        raise _failure(
            "agent_backend_not_configured",
            "No configured Agent backend is available for student extraction.",
            origin="environment",
        )
    failures: list[str] = []
    attempt_evidence: list[JsonObject] = []
    for backend in backends:
        route = hashlib.sha256(
            (
                f"{backend.name}\0{backend.base_url}\0{backend.model}\0"
                f"{backend.credential_variable}"
            ).encode()
        ).hexdigest()
        route_label = f"{backend.name}:{route[:10]}"
        for attempt in range(1, STUDENT_EXTRACTION_MAX_ATTEMPTS_PER_BACKEND + 1):
            attempt_started = time.perf_counter()
            try:
                with transcripts.attempt() as config_directory:
                    async with asyncio.timeout(STUDENT_EXTRACTION_TIMEOUT_SECONDS):
                        execution = await _run_extraction_backend(
                            prompt,
                            prepared,
                            schema,
                            backend,
                            config_directory,
                        )
                attempt_evidence.append(
                    {
                        "route": route_label,
                        "attempt": attempt,
                        "outcome": "success",
                        "wall_duration_ms": round(
                            (time.perf_counter() - attempt_started) * 1000
                        ),
                    }
                )
                return replace(
                    execution,
                    attempt_evidence=tuple(attempt_evidence),
                )
            except TimeoutError:
                failures.append(f"{route_label}:attempt-{attempt}:timeout")
                attempt_evidence.append(
                    {
                        "route": route_label,
                        "attempt": attempt,
                        "outcome": "timeout",
                        "wall_duration_ms": round(
                            (time.perf_counter() - attempt_started) * 1000
                        ),
                    }
                )
                break
            except ToolFailure as error:
                failures.append(
                    f"{route_label}:attempt-{attempt}:{error.code}"
                )
                attempt_evidence.append(
                    {
                        "route": route_label,
                        "attempt": attempt,
                        "outcome": "failure",
                        "failure_code": error.code,
                        "retryable": error.retryable,
                        "wall_duration_ms": round(
                            (time.perf_counter() - attempt_started) * 1000
                        ),
                    }
                )
                if not error.retryable:
                    break
            except Exception as error:
                failures.append(
                    f"{route_label}:attempt-{attempt}:{type(error).__name__}"
                )
                attempt_evidence.append(
                    {
                        "route": route_label,
                        "attempt": attempt,
                        "outcome": "exception",
                        "exception_type": type(error).__name__,
                        "wall_duration_ms": round(
                            (time.perf_counter() - attempt_started) * 1000
                        ),
                    }
                )
                break
    raise _failure(
        "student_extraction_backends_failed",
        "All configured Agent routes failed: " + ", ".join(failures),
        origin="engine",
    )


async def _run_batched_student_extraction(
    *,
    prepared: PreparedStudentContentExtraction,
    runner: StudentExtractionRunner,
    transcripts: SDKTranscriptManager,
) -> StudentExtractionExecution:
    content_items = prepared.inventory.get("content_items")
    if not isinstance(content_items, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("source_content_id"), str)
        for item in content_items
    ):
        raise _failure(
            "student_extraction_inventory_invalid",
            "The extraction inventory has no valid ordered content items.",
        )
    registry = FieldRegistrySnapshot.load(prepared.field_registry)
    batches = _plan_student_extraction_batches(content_items)
    if not batches:
        raise _failure(
            "student_extraction_inventory_empty",
            "The student document contains no semantic content items.",
        )
    all_ids = [str(item["source_content_id"]) for item in content_items]
    positions = {source_id: index for index, source_id in enumerate(all_ids)}
    semaphore = asyncio.Semaphore(STUDENT_EXTRACTION_CONCURRENCY)

    async def run_batch(
        batch_index: int,
        primary_items: list[JsonObject],
    ) -> tuple[StudentExtractionExecution, str, int, int]:
        primary_ids = tuple(str(item["source_content_id"]) for item in primary_items)
        start = positions[primary_ids[0]]
        end = positions[primary_ids[-1]] + 1
        context_start = max(0, start - STUDENT_EXTRACTION_CONTEXT_ITEMS)
        context_end = min(len(all_ids), end + STUDENT_EXTRACTION_CONTEXT_ITEMS)
        context_ids = tuple(all_ids[context_start:context_end])
        batch_scope: JsonObject = {
            "index": batch_index,
            "count": len(batches),
            "primary_content_ids": list(primary_ids),
            "context_content_ids": list(context_ids),
        }
        batch_prepared = replace(prepared, batch=batch_scope)
        schema = extraction_output_schema(
            prepared.inventory,
            registry,
            annotation_content_ids=primary_ids,
            relation_content_ids=context_ids,
        )
        prompt = build_student_extraction_prompt(batch_prepared)
        identity = _student_extraction_checkpoint_identity(
            prepared=batch_prepared,
            prompt=prompt,
            schema=schema,
        )
        checkpoint = _load_student_extraction_checkpoint(
            prepared.task_root,
            batch_index=batch_index,
            identity=identity,
        )
        if checkpoint is not None:
            return checkpoint, "reused", 0, 0
        queued_at = time.perf_counter()
        await semaphore.acquire()
        queue_wait_duration_ms = round((time.perf_counter() - queued_at) * 1000)
        execution_started = time.perf_counter()
        try:
            execution = await runner(
                prompt,
                batch_prepared,
                schema,
                transcripts,
            )
        finally:
            semaphore.release()
        execution_wall_duration_ms = round(
            (time.perf_counter() - execution_started) * 1000
        )
        _save_student_extraction_checkpoint(
            prepared.task_root,
            batch_index=batch_index,
            identity=identity,
            execution=execution,
        )
        return (
            execution,
            "created",
            queue_wait_duration_ms,
            execution_wall_duration_ms,
        )

    gathered = await asyncio.gather(
        *(
            run_batch(batch_index, primary_items)
            for batch_index, primary_items in enumerate(batches, start=1)
        ),
        return_exceptions=True,
    )
    failures = [result for result in gathered if isinstance(result, BaseException)]
    if failures:
        first = failures[0]
        if isinstance(first, ToolFailure):
            raise first
        raise _failure(
            "student_extraction_batch_execution_failed",
            f"An extraction batch failed with {type(first).__name__}.",
            origin="engine",
        ) from first

    annotations: JsonObject = {}
    relations: list[JsonObject] = []
    relation_keys: set[tuple[str, str, str]] = set()
    summaries: list[str] = []
    uncertainties: list[str] = []
    batch_evidence: list[JsonObject] = []
    all_tool_uses: list[str] = []
    all_skills: list[str] = []
    backends: list[str] = []
    sessions: list[str] = []
    total_num_turns = 0
    total_duration_ms = 0
    total_duration_api_ms = 0
    total_cost_usd: float | None = None
    combined_usage: JsonObject = {}
    all_attempt_evidence: list[JsonObject] = []
    for batch_index, (primary_items, batch_result) in enumerate(
        zip(batches, gathered, strict=True),
        start=1,
    ):
        if not isinstance(batch_result, tuple):
            raise AssertionError("Batch failures must be handled before merge.")
        (
            execution,
            checkpoint_status,
            queue_wait_duration_ms,
            execution_wall_duration_ms,
        ) = batch_result
        primary_ids = tuple(str(item["source_content_id"]) for item in primary_items)
        start = positions[primary_ids[0]]
        end = positions[primary_ids[-1]] + 1
        context_start = max(0, start - STUDENT_EXTRACTION_CONTEXT_ITEMS)
        context_end = min(len(all_ids), end + STUDENT_EXTRACTION_CONTEXT_ITEMS)
        context_ids = tuple(all_ids[context_start:context_end])
        raw = execution.structured_output
        raw_annotations = raw.get("annotations")
        annotation_map = {
            str(item.get("source_content_id")): item
            for item in raw_annotations
            if isinstance(item, dict) and isinstance(item.get("source_content_id"), str)
        } if isinstance(raw_annotations, list) else {}
        if (
            raw.get("schema_version") != 3
            or not isinstance(raw_annotations, list)
            or len(annotation_map) != len(raw_annotations)
            or set(annotation_map) != set(primary_ids)
        ):
            raise _failure(
                "student_extraction_batch_annotations_invalid",
                "An extraction batch did not annotate each primary item exactly once.",
            )
        annotations.update(annotation_map)
        raw_relations = raw.get("relations")
        if not isinstance(raw_relations, list):
            raise _failure(
                "student_extraction_batch_relations_invalid",
                "An extraction batch returned invalid semantic relations.",
            )
        ignored_out_of_scope_relation_count = 0
        for relation in raw_relations:
            if not isinstance(relation, dict):
                raise _failure(
                    "student_extraction_batch_relation_invalid",
                    "An extraction batch returned an invalid semantic relation.",
                )
            source = relation.get("source_content_id")
            target = relation.get("target_content_id")
            if source not in primary_ids and target not in primary_ids:
                ignored_out_of_scope_relation_count += 1
                continue
            key = (
                str(relation.get("relation_type")),
                str(source),
                str(target),
            )
            if key not in relation_keys:
                relation_keys.add(key)
                relations.append(dict(relation))
        summary = raw.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(f"Batch {batch_index}/{len(batches)}: {summary}")
        raw_uncertainties = raw.get("uncertainties")
        if isinstance(raw_uncertainties, list):
            uncertainties.extend(str(value) for value in raw_uncertainties)
        if ignored_out_of_scope_relation_count:
            uncertainties.append(
                f"Batch {batch_index}/{len(batches)} ignored "
                f"{ignored_out_of_scope_relation_count} relation(s) without a primary endpoint."
            )
        batch_evidence.append(
            {
                "batch_index": batch_index,
                "batch_count": len(batches),
                "primary_content_item_count": len(primary_ids),
                "context_content_item_count": len(context_ids) - len(primary_ids),
                "ignored_out_of_scope_relation_count": (
                    ignored_out_of_scope_relation_count
                ),
                "backend": execution.backend,
                "session_id": execution.session_id,
                "tool_uses": list(execution.tool_uses),
                "skills_loaded": list(execution.skills_loaded),
                "checkpoint_status": checkpoint_status,
                "queue_wait_duration_ms": queue_wait_duration_ms,
                "execution_wall_duration_ms": execution_wall_duration_ms,
                "batch_wall_duration_ms": (
                    queue_wait_duration_ms + execution_wall_duration_ms
                ),
                "sdk_num_turns": execution.num_turns,
                "sdk_duration_ms": execution.duration_ms,
                "sdk_duration_api_ms": execution.duration_api_ms,
                "sdk_total_cost_usd": execution.total_cost_usd,
                "sdk_usage": dict(execution.usage) if execution.usage else None,
                "attempts": [dict(value) for value in execution.attempt_evidence],
            }
        )
        backends.append(execution.backend)
        sessions.append(execution.session_id)
        all_tool_uses.extend(execution.tool_uses)
        all_skills.extend(execution.skills_loaded)
        total_num_turns += execution.num_turns
        total_duration_ms += execution.duration_ms
        total_duration_api_ms += execution.duration_api_ms
        if execution.total_cost_usd is not None:
            total_cost_usd = (total_cost_usd or 0.0) + execution.total_cost_usd
        _merge_sdk_usage(combined_usage, execution.usage)
        all_attempt_evidence.extend(execution.attempt_evidence)
    return StudentExtractionExecution(
        structured_output={
            "schema_version": 3,
            "annotations": [annotations[source_id] for source_id in all_ids],
            "relations": relations,
            "summary": "\n".join(summaries),
            "uncertainties": list(dict.fromkeys(uncertainties)),
        },
        backend=",".join(dict.fromkeys(backends)),
        session_id=",".join(sessions),
        tool_uses=tuple(all_tool_uses),
        skills_loaded=tuple(all_skills),
        num_turns=total_num_turns,
        duration_ms=total_duration_ms,
        duration_api_ms=total_duration_api_ms,
        total_cost_usd=total_cost_usd,
        usage=combined_usage or None,
        attempt_evidence=tuple(all_attempt_evidence),
        batch_evidence=tuple(batch_evidence),
    )


def _student_extraction_checkpoint_identity(
    *,
    prepared: PreparedStudentContentExtraction,
    prompt: str,
    schema: JsonObject,
) -> JsonObject:
    return {
        "checkpoint_version": STUDENT_EXTRACTION_CHECKPOINT_VERSION,
        "source_sha256": prepared.source_sha256,
        "registry_sha256": prepared.registry_sha256,
        "inventory_sha256": sha256_json(prepared.inventory),
        "batch": dict(prepared.batch or {}),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "schema_sha256": sha256_json(schema),
        "system_prompt_sha256": hashlib.sha256(
            _student_extraction_system_prompt().encode("utf-8")
        ).hexdigest(),
    }


def _student_extraction_checkpoint_path(task_root: Path, batch_index: int) -> Path:
    return task_root / "work" / "extraction-batches" / f"batch-{batch_index:03d}.json"


def _load_student_extraction_checkpoint(
    task_root: Path,
    *,
    batch_index: int,
    identity: JsonObject,
) -> StudentExtractionExecution | None:
    path = _student_extraction_checkpoint_path(task_root, batch_index)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise _failure(
            "student_extraction_checkpoint_unsafe",
            "An extraction checkpoint is not a regular task-local file.",
        )
    try:
        payload = read_json(path)
    except (OSError, ValueError, TypeError, ToolFailure):
        return None
    if any(payload.get(key) != value for key, value in identity.items()):
        return None
    execution = payload.get("execution")
    if not isinstance(execution, dict) or not isinstance(
        execution.get("structured_output"), dict
    ):
        return None
    usage = execution.get("usage")
    attempt_evidence = execution.get("attempt_evidence")
    return StudentExtractionExecution(
        structured_output=dict(execution["structured_output"]),
        backend=str(execution.get("backend", "checkpoint")),
        session_id=str(execution.get("session_id", "checkpoint")),
        tool_uses=tuple(str(value) for value in execution.get("tool_uses", [])),
        skills_loaded=tuple(str(value) for value in execution.get("skills_loaded", [])),
        num_turns=int(execution.get("num_turns", 0)),
        duration_ms=int(execution.get("duration_ms", 0)),
        duration_api_ms=int(execution.get("duration_api_ms", 0)),
        total_cost_usd=(
            float(execution["total_cost_usd"])
            if isinstance(execution.get("total_cost_usd"), (int, float))
            else None
        ),
        usage=dict(usage) if isinstance(usage, dict) else None,
        attempt_evidence=tuple(
            dict(value)
            for value in attempt_evidence
            if isinstance(value, dict)
        )
        if isinstance(attempt_evidence, list)
        else (),
    )


def _save_student_extraction_checkpoint(
    task_root: Path,
    *,
    batch_index: int,
    identity: JsonObject,
    execution: StudentExtractionExecution,
) -> None:
    path = _student_extraction_checkpoint_path(task_root, batch_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        path,
        {
            "schema_version": "docfit-student-extraction-batch-checkpoint/v1",
            **identity,
            "execution": {
                "structured_output": execution.structured_output,
                "backend": execution.backend,
                "session_id": execution.session_id,
                "tool_uses": list(execution.tool_uses),
                "skills_loaded": list(execution.skills_loaded),
                "num_turns": execution.num_turns,
                "duration_ms": execution.duration_ms,
                "duration_api_ms": execution.duration_api_ms,
                "total_cost_usd": execution.total_cost_usd,
                "usage": dict(execution.usage) if execution.usage else None,
                "attempt_evidence": [
                    dict(value) for value in execution.attempt_evidence
                ],
            },
        },
    )


def _merge_sdk_usage(target: JsonObject, usage: JsonObject | None) -> None:
    if usage is None:
        return
    for key, value in usage.items():
        if isinstance(value, bool):
            target.setdefault(key, value)
        elif isinstance(value, (int, float)):
            current = target.get(key, 0)
            target[key] = current + value if isinstance(current, (int, float)) else value
        else:
            target.setdefault(key, value)


async def run_student_content_extraction(
    request: StudentContentExtractionRequest,
    *,
    runner: StudentExtractionRunner = run_student_extraction_agent,
    office: OfficeCliAdapter | None = None,
    transcripts: SDKTranscriptManager | None = None,
) -> JsonObject:
    """Run the extraction module without a template, Fill Contract, or placement step."""

    prepared: PreparedStudentContentExtraction | None = None
    run_started = time.perf_counter()
    preparation_duration_ms = 0
    agent_wall_duration_ms = 0
    finalization_duration_ms = 0
    agent_phase_started: float | None = None
    try:
        phase_started = time.perf_counter()
        prepared = prepare_student_content_extraction(request, office=office)
        preparation_duration_ms = round((time.perf_counter() - phase_started) * 1000)
        manager = transcripts or SDKTranscriptManager(
            forbidden_roots=(prepared.task_root, project_root())
        )
        phase_started = time.perf_counter()
        agent_phase_started = phase_started
        execution = await _run_batched_student_extraction(
            prepared=prepared,
            runner=runner,
            transcripts=manager,
        )
        agent_wall_duration_ms = round((time.perf_counter() - phase_started) * 1000)
        atomic_write_json(
            prepared.task_root / "work" / "raw-agent-extraction.json",
            execution.structured_output,
        )
        atomic_write_json(
            prepared.task_root / "work" / "agent-evidence.json",
            {
                "backend": execution.backend,
                "session_id": execution.session_id,
                "tool_uses": list(execution.tool_uses),
                "skills_loaded": list(execution.skills_loaded),
                "sdk_execution": {
                    "num_turns": execution.num_turns,
                    "duration_ms": execution.duration_ms,
                    "duration_api_ms": execution.duration_api_ms,
                    "total_cost_usd": execution.total_cost_usd,
                    "usage": dict(execution.usage) if execution.usage else None,
                },
                "batches": [dict(value) for value in execution.batch_evidence],
                "privacy": "metadata_only_no_document_content",
            },
        )
        phase_started = time.perf_counter()
        model = finalize_saved_student_content_extraction(prepared.task_root)
        finalization_duration_ms = round((time.perf_counter() - phase_started) * 1000)
        report: JsonObject = {
            "schema_version": "docfit-student-content-extraction-report/v1",
            "status": model["status"],
            "source_sha256": prepared.source_sha256,
            "registry_sha256": prepared.registry_sha256,
            "student_content": str(prepared.task_root / "student-content.json"),
            "content_item_count": len(model["items"]),
            "field_result_count": len(model["field_results"]),
            "source_coverage": dict(model["source_coverage"]),
            "backend": execution.backend,
            "session_id": execution.session_id,
            "timing": {
                "preparation_duration_ms": preparation_duration_ms,
                "agent_wall_duration_ms": agent_wall_duration_ms,
                "agent_sdk_duration_ms_sum": execution.duration_ms,
                "agent_sdk_api_duration_ms_sum": execution.duration_api_ms,
                "finalization_duration_ms": finalization_duration_ms,
                "total_wall_duration_ms": round(
                    (time.perf_counter() - run_started) * 1000
                ),
            },
            "privacy": "report_contains_metadata_and_paths_only",
        }
    except ToolFailure as error:
        if agent_phase_started is not None and agent_wall_duration_ms == 0:
            agent_wall_duration_ms = round(
                (time.perf_counter() - agent_phase_started) * 1000
            )
        report = {
            "schema_version": "docfit-student-content-extraction-report/v1",
            "status": "NEEDS_INPUT" if error.status == "needs_input" else "ERROR",
            "failure": {
                "origin": error.origin,
                "code": error.code,
                "message": error.message,
            },
            "source_sha256": prepared.source_sha256 if prepared else None,
            "registry_sha256": prepared.registry_sha256 if prepared else None,
            "timing": {
                "preparation_duration_ms": preparation_duration_ms,
                "agent_wall_duration_ms": agent_wall_duration_ms,
                "finalization_duration_ms": finalization_duration_ms,
                "total_wall_duration_ms": round(
                    (time.perf_counter() - run_started) * 1000
                ),
            },
            "privacy": "report_contains_metadata_and_paths_only",
        }
    report_root = prepared.task_root if prepared is not None else request.output_directory
    if report_root.is_dir():
        atomic_write_json(report_root / "run-report.json", report)
    return report


def finalize_saved_student_content_extraction(task_root: Path) -> JsonObject:
    """Deterministically assemble a saved annotation into Student Content Model v2."""

    root = task_root.expanduser().resolve(strict=True)
    registry = FieldRegistrySnapshot.load(root / "input" / "content-fields.yaml")
    inventory = read_json(root / "work" / "student-inventory.json")
    raw_extraction = read_json(root / "work" / "raw-agent-extraction.json")
    evidence = read_json(root / "work" / "agent-evidence.json")
    _validate_agent_evidence(evidence)
    model = validate_extraction(
        raw_extraction,
        inventory=inventory,
        registry=registry,
    )
    atomic_write_json(root / "student-content.json", model)
    return model


async def run_student_content_fill(
    request: StudentContentFillRequest,
    *,
    runner: StudentExtractionRunner = run_student_extraction_agent,
    office: OfficeCliAdapter | None = None,
    transcripts: SDKTranscriptManager | None = None,
) -> JsonObject:
    """Run the independent debug slice and persist a privacy-safe summary report."""

    prepared: PreparedStudentContentFill | None = None
    try:
        office_adapter = office or OfficeCliAdapter()
        prepared = prepare_student_content_fill(request, office=office_adapter)
        manager = transcripts or SDKTranscriptManager(
            forbidden_roots=(prepared.task_root, project_root())
        )
        execution = await _run_batched_student_extraction(
            prepared=prepared.extraction,
            runner=runner,
            transcripts=manager,
        )
        atomic_write_json(
            prepared.task_root / "work" / "raw-agent-extraction.json",
            execution.structured_output,
        )
        atomic_write_json(
            prepared.task_root / "work" / "agent-evidence.json",
            {
                "backend": execution.backend,
                "session_id": execution.session_id,
                "tool_uses": list(execution.tool_uses),
                "skills_loaded": list(execution.skills_loaded),
                "batches": [dict(value) for value in execution.batch_evidence],
                "privacy": "metadata_only_no_document_content",
            },
        )
        report = finalize_saved_student_content_fill(
            prepared.task_root,
            office=office_adapter,
        )
    except ToolFailure as error:
        report = {
            "schema_version": "docfit-student-content-fill-report/v1",
            "status": "NEEDS_INPUT" if error.status == "needs_input" else "ERROR",
            "failure": {
                "origin": error.origin,
                "code": error.code,
                "message": error.message,
            },
            "source_sha256": prepared.source_sha256 if prepared else None,
            "template_sha256": prepared.template_sha256 if prepared else None,
            "privacy": "report_contains_metadata_and_paths_only",
        }
    report_root = prepared.task_root if prepared is not None else request.output_directory
    if report_root.is_dir():
        atomic_write_json(report_root / "run-report.json", report)
    return report


def finalize_saved_student_content_fill(
    task_root: Path,
    *,
    office: OfficeCliAdapter | None = None,
) -> JsonObject:
    """Resume deterministic work from a saved, evidence-checked Agent extraction."""

    root = task_root.expanduser().resolve(strict=True)
    source = root / "input" / "student.docx"
    template = root / "input" / "template.docx"
    contract_path = root / "input" / "fill-contract.yaml"
    registry_path = root / "input" / "content-fields.yaml"
    inventory_path = root / "work" / "student-inventory.json"
    raw_extraction_path = root / "work" / "raw-agent-extraction.json"
    evidence_path = root / "work" / "agent-evidence.json"
    inventory = read_json(inventory_path)
    raw_extraction = read_json(raw_extraction_path)
    evidence = read_json(evidence_path)
    contract = load_fill_contract(contract_path)
    style_contracts = StyleContractSet.from_fill_contract(contract)
    registry = FieldRegistrySnapshot.load(registry_path)
    quality_patches_path = root / "input" / "quality-patches.yaml"
    quality_patches = (
        load_quality_patches(
            quality_patches_path,
            source_sha256=sha256_file(source),
            inventory=inventory,
        )
        if quality_patches_path.is_file()
        else ()
    )
    _validate_agent_evidence(evidence)
    student_content = validate_extraction(
        raw_extraction,
        inventory=inventory,
        registry=registry,
    )
    student_content_path = root / "student-content.json"
    atomic_write_json(student_content_path, student_content)
    placement = build_placement(
        student_content=student_content,
        contract=contract,
        registry=registry,
        template_docx=template,
    )
    placement_path = root / "placement.json"
    atomic_write_json(placement_path, placement)
    filled_candidate = root / "work" / "filled-candidate.docx"
    fill_result = fill_template(
        source_docx=source,
        template_docx=template,
        placement=placement,
        style_contracts=style_contracts,
        output_docx=filled_candidate,
    )
    fill_result_path = root / "fill-result.json"
    atomic_write_json(fill_result_path, fill_result)
    candidate = root / "candidate.docx"
    projection = project_student_content(
        input_docx=filled_candidate,
        template_docx=template,
        fill_result=fill_result,
        output_docx=candidate,
        styles=resolve_template_style_map(contract=contract, template_docx=template),
        text_replacements=quality_patches,
    )
    style_audit = apply_and_validate_candidate_styles(
        candidate_docx=candidate,
        contract=contract,
        fill_result=fill_result,
        projection=projection,
    )
    style_audit_path = root / "style-audit.json"
    atomic_write_json(style_audit_path, style_audit)
    projection["style_contract_set_digest"] = style_contracts.digest
    projection["post_style_output_sha256"] = style_audit["output_sha256"]
    projection_path = root / "quality-projection.json"
    atomic_write_json(projection_path, projection)
    office_adapter = office or OfficeCliAdapter()
    content_audit = _audit_candidate(
        candidate=candidate,
        source=source,
        placement=placement,
        inventory=inventory,
        student_content=student_content,
        office=office_adapter,
        approved_text_replacements=tuple(
            (replacement.old, replacement.new) for replacement in quality_patches
        ),
    )
    content_audit_path = root / "content-audit.json"
    atomic_write_json(content_audit_path, content_audit)
    if (
        content_audit["missing_text_object_count"]
        or content_audit["missing_selected_complex_object_count"]
    ):
        raise _failure(
            "student_fill_content_missing",
            "The candidate is missing one or more selected source text objects.",
            origin="postcondition",
        )
    service = DocFitToolService(task_root=root, office=office_adapter)
    render, _ = service.render({"input_docx": str(candidate), "overview": False})
    render_path, _ = EvidenceStore(root).resolve_render(render["render_ref"])
    validation = _validate_partial_candidate(
        source=source,
        template=template,
        candidate=candidate,
        render_ref=str(render["render_ref"]),
        service=service,
        office=office_adapter,
    )
    validation_path = root / "validation.json"
    atomic_write_json(validation_path, validation)
    partial_reasons = list(placement["partial_reasons"])
    source_coverage = student_content["source_coverage"]
    if source_coverage["unsupported_source_object_ids"]:
        partial_reasons.append("source_objects_unsupported")
    source_complex = content_audit["source_complex_objects"]
    selected_complex = content_audit["selected_source_complex_objects"]
    if any(
        int(source_complex.get(kind, 0)) > int(selected_complex.get(kind, 0))
        for kind in ("drawings", "equations", "tables")
    ):
        partial_reasons.append("source_complex_objects_unmapped")
    if validation.get("new_officecli_regression") == "UNKNOWN":
        partial_reasons.append("officecli_validation_unknown_from_invalid_template_baseline")
    report: JsonObject = {
        "schema_version": "docfit-student-content-fill-report/v1",
        "status": placement["status"],
        "run_id": f"student-fill-{secrets.token_hex(8)}",
        "source_sha256": sha256_file(source),
        "template_sha256": sha256_file(template),
        "contract_sha256": sha256_file(contract_path),
        "registry_sha256": registry.sha256,
        "quality_patches_sha256": (
            sha256_file(quality_patches_path) if quality_patches_path.is_file() else None
        ),
        "quality_patch_count": len(quality_patches),
        "backend": evidence.get("backend"),
        "session_id": evidence.get("session_id"),
        "tool_uses": list(evidence.get("tool_uses", [])),
        "skills_loaded": list(evidence.get("skills_loaded", [])),
        "candidate_docx": str(candidate),
        "candidate_sha256": sha256_file(candidate),
        "candidate_pdf": str(render_path / "document.pdf"),
        "render_ref": render["render_ref"],
        "page_count": render["page_count"],
        "student_content": str(student_content_path),
        "placement": str(placement_path),
        "fill_result": str(fill_result_path),
        "quality_projection": str(projection_path),
        "style_audit": str(style_audit_path),
        "style_contract_set_digest": style_contracts.digest,
        "style_occurrence_counts": dict(style_audit["validation"]["counts"]),
        "content_audit": str(content_audit_path),
        "validation": str(validation_path),
        "missing_required_count": len(placement["missing_required"]),
        "unsupported_source_object_count": len(
            source_coverage["unsupported_source_object_ids"]
        ),
        "partial_reasons": list(dict.fromkeys(partial_reasons)),
        "privacy": "report_contains_metadata_and_paths_only",
    }
    atomic_write_json(root / "run-report.json", report)
    return report


def _validate_agent_evidence(evidence: JsonObject) -> None:
    tool_uses = {str(value) for value in evidence.get("tool_uses", [])}
    forbidden_tools = tool_uses - _ALLOWED_EXTRACTION_TOOLS
    if forbidden_tools:
        raise _failure(
            "student_extraction_forbidden_tool_used",
            "The extraction Agent used a forbidden tool: " + ", ".join(sorted(forbidden_tools)),
            origin="postcondition",
        )
    batches = evidence.get("batches")
    if batches is not None:
        if not isinstance(batches, list) or not batches:
            raise _failure(
                "student_extraction_batch_evidence_invalid",
                "The extraction Agent batch evidence is invalid.",
                origin="postcondition",
            )
        for batch in batches:
            if not isinstance(batch, dict):
                raise _failure(
                    "student_extraction_batch_evidence_invalid",
                    "An extraction Agent batch has invalid evidence.",
                    origin="postcondition",
                )
            batch_tools = {str(value) for value in batch.get("tool_uses", [])}
            if batch_tools - _ALLOWED_EXTRACTION_TOOLS:
                raise _failure(
                    "student_extraction_batch_forbidden_tool_used",
                    "An extraction batch used a forbidden tool.",
                    origin="postcondition",
                )


def _audit_candidate(
    *,
    candidate: Path,
    source: Path,
    placement: JsonObject,
    inventory: JsonObject,
    student_content: JsonObject,
    office: OfficeCliAdapter,
    approved_text_replacements: tuple[tuple[str, str], ...] = (),
) -> JsonObject:
    final_inspection = inspect_document(candidate, office)
    final_text = _normalize_text(_document_visible_text(candidate))
    by_id = {
        item["source_object_ref"]["object_id"]: item
        for item in inventory.get("objects", [])
        if isinstance(item, dict) and isinstance(item.get("source_object_ref"), dict)
    }
    selected_block_ids = {
        str(object_id)
        for operation in placement.get("operations", [])
        if isinstance(operation, dict)
        and operation.get("action") == "replace_block_content_control"
        for object_id in operation.get("source_object_ids", [])
    }
    missing_block_ids = [
        object_id
        for object_id in sorted(selected_block_ids)
        if (
            text := _apply_approved_text_replacements(
                str(by_id.get(object_id, {}).get("text", "")),
                approved_text_replacements,
            )
        ).strip()
        and _normalize_text(text) not in final_text
    ]
    missing_scalar_content_ids = [
        str(item.get("content_id"))
        for item in student_content.get("items", [])
        if isinstance(item, dict)
        and item.get("classification_status") == "classified"
        and str(item.get("transport_source_object_id")) not in selected_block_ids
        and isinstance(item.get("value"), str)
        and str(item["value"]).strip()
        and _normalize_text(str(item["value"])) not in final_text
    ]
    selected_pictures = sum(
        item.get("physical_type") == "image"
        and item.get("classification_status") == "classified"
        for item in student_content.get("items", [])
        if isinstance(item, dict)
    )
    selected_complex = _selected_ooxml_counts(source, placement)
    candidate_images = int(final_inspection.summary.get("images", 0))
    candidate_equations = int(final_inspection.summary.get("equations", 0))
    candidate_tables = int(final_inspection.summary.get("tables", 0))
    missing_complex = (
        max(0, selected_complex["drawings"] - candidate_images)
        + max(0, selected_complex["equations"] - candidate_equations)
        + max(0, selected_complex["tables"] - candidate_tables)
    )
    return {
        "schema_version": "docfit-student-content-audit/v1",
        "candidate_sha256": final_inspection.document_sha256,
        "selected_block_text_object_count": sum(
            bool(str(by_id.get(object_id, {}).get("text", "")).strip())
            for object_id in selected_block_ids
        ),
        "missing_text_object_count": len(missing_block_ids)
        + len(missing_scalar_content_ids),
        "missing_block_text_object_ids": missing_block_ids,
        "missing_scalar_content_ids": missing_scalar_content_ids,
        "selected_dependency_picture_count": selected_pictures,
        "selected_source_complex_objects": selected_complex,
        "source_complex_objects": {
            "drawings": inventory.get("package_summary", {}).get("drawings"),
            "equations": inventory.get("package_summary", {}).get("equations"),
            "tables": inventory.get("package_summary", {}).get("tables"),
        },
        "missing_selected_complex_object_count": missing_complex,
        "candidate_image_count": candidate_images,
        "candidate_equation_count": candidate_equations,
        "candidate_table_count": candidate_tables,
        "package_summary": dict(final_inspection.summary),
    }


def _selected_ooxml_counts(source: Path, placement: JsonObject) -> dict[str, int]:
    word_namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    math_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    locators = {
        str(locator)
        for operation in placement.get("operations", [])
        if isinstance(operation, dict)
        for locator in operation.get("source_locators", [])
    }
    with zipfile.ZipFile(source) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    body = document.find(f"{{{word_namespace}}}body")
    if body is None:
        raise _failure(
            "student_source_body_missing",
            "The source body cannot be audited.",
            origin="postcondition",
        )
    selected: list[ET.Element] = []
    table_index = 0
    for child in body:
        locator: str | None = None
        if child.tag == f"{{{word_namespace}}}p":
            para_id = next(
                (value for key, value in child.attrib.items() if key.endswith("}paraId")),
                None,
            )
            if para_id:
                locator = f"/body/p[@paraId={para_id}]"
        elif child.tag == f"{{{word_namespace}}}tbl":
            table_index += 1
            locator = f"/body/tbl[{table_index}]"
        if locator in locators:
            selected.append(child)
    return {
        "top_level_objects": len(selected),
        "tables": sum(child.tag == f"{{{word_namespace}}}tbl" for child in selected),
        "drawings": sum(
            len(child.findall(f".//{{{word_namespace}}}drawing")) for child in selected
        ),
        "equations": sum(len(child.findall(f".//{{{math_namespace}}}oMath")) for child in selected),
    }


def _validate_partial_candidate(
    *,
    source: Path,
    template: Path,
    candidate: Path,
    render_ref: str,
    service: DocFitToolService,
    office: OfficeCliAdapter,
) -> JsonObject:
    candidate_package_warnings = validate_docx_package(candidate)
    template_package_warnings = validate_docx_package(template)

    def office_status(document: Path) -> tuple[bool, str]:
        try:
            office.validate(document)
        except ToolFailure as error:
            return False, error.code
        return True, "officecli_openxml_passed"

    template_passed, template_code = office_status(template)
    candidate_passed, candidate_code = office_status(candidate)
    if template_passed and not candidate_passed:
        raise _failure(
            "student_fill_officecli_regression",
            "The candidate fails OfficeCLI although the bound template passes.",
            origin="postcondition",
        )
    if candidate_passed:
        return service.validate(
            {
                "source_docx": str(source),
                "source_sha256": sha256_file(source),
                "final_docx": str(candidate),
                "candidate_render_ref": render_ref,
                "task_rule_evidence": [],
            }
        )
    return {
        "schema_version": "docfit-student-content-partial-validation/v1",
        "status": "PARTIAL",
        "candidate_sha256": sha256_file(candidate),
        "template_sha256": sha256_file(template),
        "candidate_package_warnings": candidate_package_warnings,
        "template_package_warnings": template_package_warnings,
        "candidate_officecli": {"passed": candidate_passed, "code": candidate_code},
        "template_officecli": {"passed": template_passed, "code": template_code},
        "new_officecli_regression": "UNKNOWN",
        "explanation": (
            "Both the candidate and its bound candidate template are rejected by the fixed "
            "OfficeCLI validator without diagnostic details; LibreOffice render evidence is "
            "current, but this is not a green structural validation result."
        ),
    }


def _input_file(path: Path, suffix: str, label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except FileNotFoundError as error:
        raise _failure("student_fill_input_missing", f"{label} does not exist.") from error
    if not resolved.is_file() or resolved.suffix.casefold() != suffix:
        raise _failure("student_fill_input_type", f"{label} has an unsupported file type.")
    return resolved


def _normalize_text(value: str) -> str:
    return "".join(value.split()).casefold()


def _document_visible_text(document: Path) -> str:
    word_namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    math_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    text_tags = {f"{{{word_namespace}}}t", f"{{{math_namespace}}}t"}
    return "\n".join(node.text or "" for node in root.iter() if node.tag in text_tags)


def _apply_approved_text_replacements(value: str, replacements: tuple[tuple[str, str], ...]) -> str:
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def _failure(
    code: str,
    message: str,
    *,
    origin: str = "request",
    retryable: bool = False,
) -> ToolFailure:
    return ToolFailure(
        status="error" if origin in {"engine", "environment", "postcondition"} else "needs_input",
        origin=origin,
        code=code,
        message=message,
        retryable=retryable,
    )

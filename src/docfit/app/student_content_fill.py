"""Independent Student Content -> Placement -> template-fill debug slice."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import tempfile
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree import ElementTree as ET

from claude_agent_sdk import ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import (
    AssistantMessage,
    HookContext,
    HookInput,
    HookJSONOutput,
    PreToolUseHookSpecificOutput,
    ResultMessage,
    ToolUseBlock,
)

from docfit.app.agent import build_agent_options, project_root, terminal_ask_user
from docfit.app.settings import AgentBackend, iter_agent_backends
from docfit.content.extraction import (
    SEGMENT_FIELD_IDS,
    extraction_output_schema,
    validate_extraction,
)
from docfit.content.fill import fill_template
from docfit.content.placement import build_placement, load_fill_contract
from docfit.content.student import build_student_inventory
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.observability.transcript import SDKTranscriptManager, isolated_sdk_environment
from docfit.tools.inspection import inspect_document
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    read_json,
    sha256_file,
)
from docfit.tools.service import DocFitToolService
from docfit.visual.evidence import EvidenceStore

STUDENT_EXTRACTION_TIMEOUT_SECONDS = 600
_REQUIRED_AGENT_TOOLS = frozenset({"Skill", "mcp__docfit__docx_inspect"})
_ALLOWED_EXTRACTION_TOOLS = frozenset(
    {
        "Skill",
        "Read",
        "Glob",
        "Grep",
        "StructuredOutput",
        "mcp__docfit__docx_inspect",
    }
)


@dataclass(frozen=True, slots=True)
class StudentContentFillRequest:
    source_docx: Path
    template_docx: Path
    fill_contract: Path
    field_registry: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class PreparedStudentContentFill:
    task_root: Path
    source_docx: Path
    template_docx: Path
    fill_contract: Path
    field_registry: Path
    inventory_path: Path
    candidate_docx: Path
    source_sha256: str
    template_sha256: str
    contract_sha256: str
    registry_sha256: str
    expected_field_ids: tuple[str, ...]
    inventory: JsonObject


@dataclass(frozen=True, slots=True)
class StudentExtractionExecution:
    structured_output: JsonObject
    backend: str
    session_id: str
    tool_uses: tuple[str, ...]
    skills_loaded: tuple[str, ...]


StudentExtractionRunner = Callable[
    [str, PreparedStudentContentFill, JsonObject, SDKTranscriptManager],
    Awaitable[StudentExtractionExecution],
]


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
    source_hash = sha256_file(source)
    template_hash = sha256_file(template)
    contract_hash = sha256_file(contract_path)
    registry_hash = sha256_file(registry_path)
    contract = load_fill_contract(contract_path)
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
    expected_field_ids = _expected_field_ids(contract, registry)
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
        input_directory.mkdir()
        work_directory.mkdir()
        copies = {
            source: input_directory / "student.docx",
            template: input_directory / "template.docx",
            contract_path: input_directory / "fill-contract.yaml",
            registry_path: input_directory / "content-fields.yaml",
        }
        for original, copied in copies.items():
            shutil.copy2(original, copied)
        expected_hashes = {
            source: source_hash,
            template: template_hash,
            contract_path: contract_hash,
            registry_path: registry_hash,
        }
        if any(
            sha256_file(original) != expected_hash or sha256_file(copies[original]) != expected_hash
            for original, expected_hash in expected_hashes.items()
        ):
            raise _failure(
                "student_fill_input_changed",
                "An input changed while the private task snapshot was prepared.",
            )
        source_copy = copies[source]
        inspection = inspect_document(source_copy, office or OfficeCliAdapter())
        inventory = build_student_inventory(inspection, source_docx=source_copy)
        inventory_path = work_directory / "student-inventory.json"
        atomic_write_json(inventory_path, inventory)
        for copied in copies.values():
            copied.chmod(0o444)
        input_directory.chmod(0o555)
        if output.exists():
            output.rmdir()
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return PreparedStudentContentFill(
        task_root=output,
        source_docx=output / "input" / "student.docx",
        template_docx=output / "input" / "template.docx",
        fill_contract=output / "input" / "fill-contract.yaml",
        field_registry=output / "input" / "content-fields.yaml",
        inventory_path=output / "work" / "student-inventory.json",
        candidate_docx=output / "candidate.docx",
        source_sha256=source_hash,
        template_sha256=template_hash,
        contract_sha256=contract_hash,
        registry_sha256=registry_hash,
        expected_field_ids=expected_field_ids,
        inventory=inventory,
    )


def build_student_extraction_prompt(prepared: PreparedStudentContentFill) -> str:
    registry = FieldRegistrySnapshot.load(prepared.field_registry)
    field_catalog = [registry.lookup(field_id) for field_id in prepared.expected_field_ids]
    segment_catalog = [registry.lookup(field_id) for field_id in sorted(SEGMENT_FIELD_IDS)]
    task = {
        "schema_version": 1,
        "authorized_task_root": str(prepared.task_root),
        "student_docx": {
            "path": str(prepared.source_docx),
            "sha256": prepared.source_sha256,
            "read_only": True,
        },
        "inventory_facts": {
            "object_count": prepared.inventory.get("object_count"),
            "transferable_object_count": prepared.inventory.get("transferable_object_count"),
            "package_summary": prepared.inventory.get("package_summary"),
        },
        "scalar_fields": field_catalog,
        "continuous_segments": segment_catalog,
    }
    return (
        "Extract student thesis content from the bound read-only DOCX. Load the "
        "convert-thesis Skill, then call docx_inspect exactly for the student snapshot. "
        "This is extraction only: do not edit, render, validate, write files, use Bash, ask "
        "the user, or delegate. Return exact visible source values; never translate, infer, "
        "complete, normalize, or guess absent personal/academic facts. An extracted scalar "
        "must cite every source object needed to find its exact value. Mark absent values "
        "missing and ambiguous contradictory values conflict. For body.chapters, return the "
        "continuous top-level paragraph/table range after front matter through the conclusion, "
        "excluding references, acknowledgements, and appendices. For references.entries, "
        "acknowledgement.body, and appendix.body, select content only and exclude a standalone "
        "section heading when the heading itself is not content. Range endpoints must be "
        "transferable top-level paragraph/table object IDs from docx_inspect. Put any source "
        "object not intentionally covered by a scalar or segment into unmapped_object_ids; the "
        "application will independently close the coverage accounting. Return only the "
        "requested structured output.\n\nCURRENT_TASK_JSON:\n"
        + json.dumps(task, ensure_ascii=False, sort_keys=True)
    )


def _student_extraction_system_prompt() -> str:
    return (
        "You are the DocFit main Agent performing a read-only student-content extraction. "
        "Claude Agent SDK owns the single Agent session. The application owns inventory, "
        "schema validation, placement, and all writes after you return. Use convert-thesis "
        "for domain guidance and docx_inspect for evidence. Do not mutate documents or infer "
        "missing values. Object IDs, not page numbers or visible text, are evidence identities."
    )


async def _force_inline_inspection(
    hook_input: HookInput,
    _tool_use_id: str | None,
    _context: HookContext,
) -> HookJSONOutput:
    """Prevent the read-only inspection Tool from persisting its optional JSON output."""

    if (
        hook_input["hook_event_name"] != "PreToolUse"
        or hook_input["tool_name"] != "mcp__docfit__docx_inspect"
    ):
        return {}
    updated_input = dict(hook_input["tool_input"])
    updated_input.pop("output", None)
    output: PreToolUseHookSpecificOutput = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": (
            "Student extraction is read-only; inspection evidence must remain inline."
        ),
        "updatedInput": updated_input,
    }
    return {"hookSpecificOutput": output}


async def _run_extraction_backend(
    prompt: str,
    prepared: PreparedStudentContentFill,
    schema: JsonObject,
    backend: AgentBackend,
    config_directory: Path,
) -> StudentExtractionExecution:
    environment = isolated_sdk_environment(backend.sdk_environment(), config_directory)
    environment["DOCFIT_TASK_ROOT"] = str(prepared.task_root)
    options = build_agent_options(
        terminal_ask_user,
        cwd=project_root(),
        task_root=prepared.task_root,
        agent_env=environment,
        model=backend.model,
        system_prompt=_student_extraction_system_prompt(),
        output_format={"type": "json_schema", "schema": schema},
        max_turns=10,
    )
    options = replace(
        options,
        tools=["Skill", "Read", "Glob", "Grep"],
        allowed_tools=["mcp__docfit__docx_inspect"],
        disallowed_tools=[
            "Bash",
            "Write",
            "Edit",
            "Agent",
            "AskUserQuestion",
            "Web",
            "WebSearch",
            "WebFetch",
            "mcp__docfit__docx_edit",
            "mcp__docfit__docx_render",
            "mcp__docfit__docx_visual_review",
            "mcp__docfit__docx_validate",
        ],
        agents={},
        skills=["convert-thesis"],
    )
    hooks = dict(options.hooks or {})
    hooks.setdefault("PreToolUse", []).insert(
        0,
        HookMatcher(
            matcher="mcp__docfit__docx_inspect",
            hooks=[_force_inline_inspection],
        ),
    )
    options = replace(options, hooks=hooks)
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
    if result is None or result.is_error or not isinstance(result.structured_output, dict):
        raise _failure(
            "student_extraction_agent_failed",
            "The Agent returned no usable structured student-content result.",
            origin="engine",
        )
    return StudentExtractionExecution(
        structured_output=result.structured_output,
        backend=backend.name,
        session_id=result.session_id,
        tool_uses=tuple(tool_uses),
        skills_loaded=tuple(dict.fromkeys(skills_loaded)),
    )


async def run_student_extraction_agent(
    prompt: str,
    prepared: PreparedStudentContentFill,
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
    attempted_routes: set[str] = set()
    for backend in backends:
        route = hashlib.sha256(
            f"{backend.name}\0{backend.base_url}\0{backend.model}".encode()
        ).hexdigest()
        if route in attempted_routes:
            continue
        attempted_routes.add(route)
        try:
            with transcripts.attempt() as config_directory:
                async with asyncio.timeout(STUDENT_EXTRACTION_TIMEOUT_SECONDS):
                    return await _run_extraction_backend(
                        prompt,
                        prepared,
                        schema,
                        backend,
                        config_directory,
                    )
        except TimeoutError:
            failures.append(f"{backend.name}:timeout")
        except ToolFailure as error:
            failures.append(f"{backend.name}:{error.code}")
        except Exception as error:
            failures.append(f"{backend.name}:{type(error).__name__}")
    raise _failure(
        "student_extraction_backends_failed",
        "All configured Agent routes failed: " + ", ".join(failures),
        origin="engine",
    )


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
        schema = extraction_output_schema(prepared.expected_field_ids)
        manager = transcripts or SDKTranscriptManager(
            forbidden_roots=(prepared.task_root, project_root())
        )
        execution = await runner(
            build_student_extraction_prompt(prepared),
            prepared,
            schema,
            manager,
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
    registry = FieldRegistrySnapshot.load(registry_path)
    expected_field_ids = _expected_field_ids(contract, registry)
    _validate_agent_evidence(evidence)
    student_content = validate_extraction(
        raw_extraction,
        inventory=inventory,
        registry=registry,
        expected_field_ids=expected_field_ids,
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
    candidate = root / "candidate.docx"
    fill_result = fill_template(
        source_docx=source,
        template_docx=template,
        placement=placement,
        output_docx=candidate,
    )
    fill_result_path = root / "fill-result.json"
    atomic_write_json(fill_result_path, fill_result)
    office_adapter = office or OfficeCliAdapter()
    content_audit = _audit_candidate(
        candidate=candidate,
        source=source,
        placement=placement,
        inventory=inventory,
        student_content=student_content,
        office=office_adapter,
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
    if student_content["coverage"]["unmapped_object_count"]:
        partial_reasons.append("source_objects_unmapped")
    source_complex = content_audit["source_complex_objects"]
    selected_complex = content_audit["selected_source_complex_objects"]
    if any(
        int(source_complex.get(kind, 0)) > int(selected_complex.get(kind, 0))
        for kind in ("drawings", "equations", "tables")
    ):
        partial_reasons.append("source_complex_objects_unmapped")
    if validation.get("new_officecli_regression") == "UNKNOWN":
        partial_reasons.append(
            "officecli_validation_unknown_from_invalid_template_baseline"
        )
    report: JsonObject = {
        "schema_version": "docfit-student-content-fill-report/v1",
        "status": placement["status"],
        "run_id": f"student-fill-{secrets.token_hex(8)}",
        "source_sha256": sha256_file(source),
        "template_sha256": sha256_file(template),
        "contract_sha256": sha256_file(contract_path),
        "registry_sha256": registry.sha256,
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
        "content_audit": str(content_audit_path),
        "validation": str(validation_path),
        "missing_required_count": len(placement["missing_required"]),
        "unmapped_object_count": student_content["coverage"]["unmapped_object_count"],
        "partial_reasons": list(dict.fromkeys(partial_reasons)),
        "privacy": "report_contains_metadata_and_paths_only",
    }
    atomic_write_json(root / "run-report.json", report)
    return report


def _validate_agent_evidence(evidence: JsonObject) -> None:
    tool_uses = {str(value) for value in evidence.get("tool_uses", [])}
    skills_loaded = {str(value) for value in evidence.get("skills_loaded", [])}
    missing_tools = _REQUIRED_AGENT_TOOLS - tool_uses
    forbidden_tools = tool_uses - _ALLOWED_EXTRACTION_TOOLS
    if missing_tools:
        raise _failure(
            "student_extraction_tool_evidence_incomplete",
            "The Agent result lacks required inspection Tool evidence: "
            + ", ".join(sorted(missing_tools)),
            origin="postcondition",
        )
    if forbidden_tools:
        raise _failure(
            "student_extraction_forbidden_tool_used",
            "The extraction Agent used a forbidden tool: " + ", ".join(sorted(forbidden_tools)),
            origin="postcondition",
        )
    if "convert-thesis" not in skills_loaded:
        raise _failure(
            "student_extraction_skill_evidence_incomplete",
            "The Agent result lacks convert-thesis Skill evidence.",
            origin="postcondition",
        )


def _expected_field_ids(
    contract: JsonObject,
    registry: FieldRegistrySnapshot,
) -> tuple[str, ...]:
    values: list[str] = []
    for slot in contract.get("slots", []):
        if not isinstance(slot, dict):
            continue
        field_id = slot.get("field_id")
        if (
            isinstance(field_id, str)
            and field_id not in SEGMENT_FIELD_IDS
            and not field_id.startswith("body.")
            and field_id not in values
        ):
            registry.lookup(field_id)
            values.append(field_id)
    return tuple(values)


def _audit_candidate(
    *,
    candidate: Path,
    source: Path,
    placement: JsonObject,
    inventory: JsonObject,
    student_content: JsonObject,
    office: OfficeCliAdapter,
) -> JsonObject:
    final_inspection = inspect_document(candidate, office)
    final_text = _normalize_text(_document_visible_text(candidate))
    by_id = {
        item["source_object_ref"]["object_id"]: item
        for item in inventory.get("objects", [])
        if isinstance(item, dict) and isinstance(item.get("source_object_ref"), dict)
    }
    selected_segment_ids = {
        object_id
        for item in student_content.get("segments", [])
        if isinstance(item, dict) and item.get("status") == "extracted"
        for object_id in item.get("source_object_ids", [])
    }
    missing_segment_ids = [
        object_id
        for object_id in sorted(selected_segment_ids)
        if (text := str(by_id.get(object_id, {}).get("text", ""))).strip()
        and _normalize_text(text) not in final_text
    ]
    missing_scalar_field_ids = [
        str(item.get("field_id"))
        for item in student_content.get("fields", [])
        if isinstance(item, dict)
        and item.get("status") == "extracted"
        and isinstance(item.get("value"), str)
        and _normalize_text(str(item["value"])) not in final_text
    ]
    dependency_ids = set(student_content.get("covered_dependency_object_ids", []))
    selected_pictures = sum(
        item.get("kind") == "picture"
        and item.get("source_object_ref", {}).get("object_id") in dependency_ids
        for item in inventory.get("objects", [])
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
        "selected_segment_text_object_count": sum(
            bool(str(by_id.get(object_id, {}).get("text", "")).strip())
            for object_id in selected_segment_ids
        ),
        "missing_text_object_count": len(missing_segment_ids) + len(missing_scalar_field_ids),
        "missing_segment_text_object_ids": missing_segment_ids,
        "missing_scalar_field_ids": missing_scalar_field_ids,
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
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "\n".join(node.text or "" for node in root.iter(f"{{{word_namespace}}}t"))


def _failure(code: str, message: str, *, origin: str = "request") -> ToolFailure:
    return ToolFailure(
        status="error" if origin in {"engine", "environment", "postcondition"} else "needs_input",
        origin=origin,
        code=code,
        message=message,
    )

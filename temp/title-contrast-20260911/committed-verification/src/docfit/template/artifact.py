"""Stateless publication of one Agent-completed school template.

This module owns objective artifact invariants only. It does not decide what
school text means, which representative body block is correct, or whether a
section belongs in the TOC; those decisions are already embodied in the final
DOCX selected by the main Agent.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from docfit.fields import FieldRegistrySnapshot
from docfit.styles.capture import (
    capture_template_style_contracts,
    capture_template_style_observations,
    slot_style_contract_id,
)
from docfit.styles.profiles import DEFAULT_STYLE_PROPERTY_PROFILES
from docfit.tools.inspection import inspect_document_snapshot
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

_PUBLICATION_OUTPUTS = {"final-template.docx", "fill-contract.yaml"}
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_W_NS}}}"
_SLOT_REF_FIELD_SEPARATOR = ";field_id="


def _style_metadata(*, field_id: str, slot_ref: str, content_type: str) -> JsonObject:
    if content_type not in {"text", "rich_text"}:
        return {"handling": "non_style"}
    style_role_id = slot_style_contract_id(slot_ref)
    style_role_type = "paragraph"
    profile = DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type(style_role_type)
    return {
        "handling": "styled",
        "style_role_id": style_role_id,
        "style_role_type": style_role_type,
        "property_profile_ref": profile.ref().as_dict(),
    }


def _publication_failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="postcondition",
        code=code,
        message=message,
    )


def _office_validation_status(document: Path, adapter: OfficeCliAdapter) -> JsonObject:
    try:
        validation = adapter.validate_snapshot(document)
    except ToolFailure as error:
        return {
            "passed": False,
            "code": error.code,
            "origin": error.origin,
            "detail": error.message,
        }
    return {
        "passed": True,
        "code": None,
        "origin": None,
        "detail": validation.get("detail", "OfficeCLI OpenXML validation passed."),
    }


def _content_control_value(control: ET.Element, name: str) -> str | None:
    element = control.find(f"{_W}sdtPr/{_W}{name}")
    return element.get(f"{_W}val") if element is not None else None


def _parse_slot_ref(value: str) -> JsonObject | None:
    if _SLOT_REF_FIELD_SEPARATOR not in value:
        return None
    span_ref, field_id = value.rsplit(_SLOT_REF_FIELD_SEPARATOR, 1)
    if not span_ref or not field_id.strip():
        return None
    segments = span_ref.split(";")
    parsed: dict[str, str] = {}
    for segment in segments:
        if "=" not in segment:
            return None
        key, raw = segment.split("=", 1)
        if not key or not raw:
            return None
        parsed[key] = raw
    part_index = parsed.get("part_index")
    if part_index is None or not part_index.isdigit():
        return None
    scope_keys = [
        key for key in ("source_entry_id", "reading_block_id", "reading_range_id") if key in parsed
    ]
    if len(scope_keys) != 1:
        return None
    scope_key = scope_keys[0]
    return {
        "slot_ref": value,
        "span_ref": span_ref,
        "field_id": field_id.strip(),
        "part_index": int(part_index),
        "scope": {scope_key: parsed[scope_key]},
    }


def _is_legacy_docfit_slot_tag(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith("slot.")


def _is_harness_slot_ref_marker(value: str | None) -> bool:
    return isinstance(value, str) and (
        value.startswith(("source_entry_id=", "reading_block_id=", "reading_range_id="))
        or _SLOT_REF_FIELD_SEPARATOR in value
    )


def _registry_has_field(registry: FieldRegistrySnapshot, field_id: str | None) -> bool:
    if not isinstance(field_id, str) or not field_id.strip():
        return False
    try:
        registry.lookup(field_id.strip())
    except ToolFailure:
        return False
    return True


def _slot_protocol_entry(
    *,
    field_id: str,
    slot_ref: str,
) -> JsonObject | None:
    parsed = _parse_slot_ref(slot_ref)
    if parsed is None or parsed.get("field_id") != field_id:
        return None
    return parsed


def publication_slot_protocol_status(
    *,
    candidate_docx: Path,
    registry: FieldRegistrySnapshot,
    allow_no_slots: bool = False,
) -> JsonObject:
    """Check only the DocFit-owned slot marker protocol needed for publication."""

    try:
        with zipfile.ZipFile(candidate_docx) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as error:
        return {
            "status": "needs_input",
            "failure": {
                "code": "source_candidate_not_publishable",
                "message": "The source candidate cannot be inspected for DocFit slots.",
                "retryable": False,
                "suggested_actions": [
                    "Use a valid DOCX candidate returned by docfit_apply.",
                ],
            },
            "error": str(error),
        }

    controls = list(document.iter(f"{_W}sdt"))
    slots: list[JsonObject] = []
    invalid: list[JsonObject] = []
    seen_tags: set[str] = set()
    for control in controls:
        field_id = _content_control_value(control, "alias")
        slot_ref = _content_control_value(control, "tag")
        if _is_legacy_docfit_slot_tag(slot_ref):
            invalid.append({"code": "legacy_slot_ref_marker", "slot_ref": slot_ref})
            continue
        registered_alias = _registry_has_field(registry, field_id)
        harness_marker = _is_harness_slot_ref_marker(slot_ref)
        if not registered_alias and not harness_marker:
            continue
        if registered_alias and not isinstance(slot_ref, str):
            invalid.append(
                {
                    "code": "content_control_slot_ref_missing",
                    "field_id": field_id,
                    "message": (
                        "A Registry-bound content control is missing its Harness slot_ref tag."
                    ),
                }
            )
            continue
        if harness_marker and not isinstance(field_id, str):
            invalid.append(
                {
                    "code": "content_control_identity_missing",
                    "slot_ref": slot_ref,
                    "message": (
                        "A Harness slot_ref content control is missing its Registry alias."
                    ),
                }
            )
            continue
        if not isinstance(slot_ref, str) or not isinstance(field_id, str):
            continue
        protocol = _slot_protocol_entry(field_id=field_id, slot_ref=slot_ref)
        if protocol is None:
            invalid.append(
                {
                    "code": "content_control_identity_missing",
                    "slot_ref": slot_ref,
                    "field_id": field_id,
                    "message": (
                        "Every DocFit slot control must expose a Registry alias and "
                        "matching Harness slot_ref tag."
                    ),
                }
            )
            continue
        if slot_ref in seen_tags:
            invalid.append({"code": "content_control_tag_duplicate", "slot_ref": slot_ref})
            continue
        seen_tags.add(slot_ref)
        try:
            registry.lookup(field_id)
        except ToolFailure as error:
            invalid.append(
                {
                    "code": "content_control_field_invalid",
                    "slot_ref": slot_ref,
                    "field_id": field_id,
                    "message": error.message,
                }
            )
            continue
        slots.append(
            {
                "slot_ref": slot_ref,
                "span_ref": protocol["span_ref"],
                "field_id": field_id,
            }
        )
    if invalid:
        return {
            "status": "needs_input",
            "slot_count": len(slots),
            "school_content_control_count": len(controls) - len(slots),
            "invalid_slots": invalid,
            "failure": {
                "code": "source_candidate_slot_protocol_invalid",
                "message": "One or more DocFit slot controls are not publication-compatible.",
                "retryable": False,
                "suggested_actions": [
                    "Repair the selected slot identity with docfit_apply(bind_field).",
                ],
            },
        }
    if not slots and allow_no_slots:
        return {
            "status": "ok",
            "slot_count": 0,
            "school_content_control_count": len(controls),
            "slots": [],
            "failure": None,
        }
    if not slots:
        return {
            "status": "needs_input",
            "slot_count": 0,
            "school_content_control_count": len(controls),
            "failure": {
                "code": "source_candidate_not_publishable",
                "message": (
                    "The source may contain school fill controls, but it has no DocFit-owned "
                    "Harness slot_ref content-control markers."
                ),
                "retryable": False,
                "suggested_actions": [
                    "Materialize accepted Harness resolved_spans before publication.",
                    "Return needs_input if the current write backend cannot create a DocFit slot.",
                ],
            },
        }
    return {
        "status": "ok",
        "slot_count": len(slots),
        "school_content_control_count": len(controls) - len(slots),
        "slots": slots,
        "failure": None,
    }


def _atomic_write_yaml(path: Path, value: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _assert_output_directory_ready(output: Path, output_contract: Path) -> None:
    output_dir = output.parent
    if not output_dir.exists():
        return
    entries = sorted(path.name for path in output_dir.iterdir())
    if not entries:
        return
    if output.name in entries or output_contract.name in entries:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_publication_exists",
            message="Publication never overwrites an existing Word/Fill Contract pair.",
        )
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="template_output_directory_not_clean",
        message="The template output directory must be empty before publication.",
    )


def _published_slots(
    *,
    candidate_docx: Path,
    registry: FieldRegistrySnapshot,
    office: OfficeCliAdapter,
) -> tuple[list[JsonObject], int]:
    inspection = inspect_document_snapshot(
        candidate_docx,
        office,
        selector="paragraph, table, picture, run, sdt, shape",
    )
    controls = [item for item in inspection.objects if item.kind == "sdt"]
    slots: list[JsonObject] = []
    structure_count = 0
    seen_tags: set[str] = set()
    for control in controls:
        field_id = control.format.get("alias")
        slot_ref = control.format.get("tag")
        # School-authored controls are legitimate source content.  DocFit owns
        # only controls carrying a Harness slot_ref marker; applying Registry
        # rules to every pre-existing SDT would silently redefine school
        # semantics at publication time.  Once a control uses a Registry alias,
        # it is no longer safe to treat it as school-authored: publication must
        # prove it came from accepted Harness spans.
        if _is_legacy_docfit_slot_tag(slot_ref):
            raise _publication_failure(
                "legacy_slot_ref_marker",
                "Publication rejects legacy slot.* content-control tags.",
            )
        registered_alias = _registry_has_field(registry, field_id)
        harness_marker = _is_harness_slot_ref_marker(slot_ref)
        if not registered_alias and not harness_marker:
            continue
        if registered_alias and not isinstance(slot_ref, str):
            raise _publication_failure(
                "content_control_slot_ref_missing",
                "A Registry-bound content control is missing its Harness slot_ref tag.",
            )
        if harness_marker and not isinstance(field_id, str):
            raise _publication_failure(
                "content_control_identity_missing",
                "A Harness slot_ref content control is missing its Registry alias.",
            )
        if not isinstance(slot_ref, str) or not isinstance(field_id, str):
            continue
        protocol = _slot_protocol_entry(field_id=field_id, slot_ref=slot_ref)
        if protocol is None:
            raise _publication_failure(
                "content_control_identity_missing",
                "Every DocFit slot control must expose a Registry alias and Harness slot_ref tag.",
            )
        try:
            field = registry.lookup(field_id)
        except ToolFailure as error:
            raise _publication_failure(
                "content_control_field_invalid",
                "A DocFit slot control references a field outside the Registry snapshot.",
            ) from error
        if slot_ref in seen_tags:
            raise _publication_failure(
                "content_control_tag_duplicate",
                "Final content-control tags must be unique within the Word document.",
            )
        seen_tags.add(slot_ref)
        content_type = str(field.get("content_type", "text"))
        if content_type == "section":
            structure_count += 1
            continue
        slot: JsonObject = {
            "slot_ref": slot_ref,
            "span_ref": protocol["span_ref"],
            "field_id": field_id,
            "content_type": content_type,
            "required": True,
            "locator": {
                "type": "content_control_tag",
                "value": slot_ref,
                "story": "document",
                "part": "word/document.xml",
                "expected_match_count": 1,
            },
        }
        slot.update(
            _style_metadata(
                field_id=field_id,
                slot_ref=slot_ref,
                content_type=content_type,
            )
        )
        label = field.get("label")
        if isinstance(label, str) and label:
            slot["label"] = label
        slots.append(slot)
    if structure_count > 1:
        raise _publication_failure(
            "body_structure_duplicate",
            "The final template may contain at most one reusable body structure.",
        )
    return slots, structure_count


def _accepted_slot_provenance(root: Path, registry: FieldRegistrySnapshot) -> dict[str, JsonObject]:
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    if not review_path.is_file() or not materialization_path.is_file():
        raise _publication_failure(
            "template_slot_provenance_missing",
            (
                "Publication requires accepted semantic judgments and materialization "
                "receipt evidence."
            ),
        )
    review = read_json(review_path)
    materialization = read_json(materialization_path)
    vocabulary = review.get("field_id_vocabulary")
    if not isinstance(vocabulary, dict):
        raise _publication_failure(
            "field_vocabulary_provenance_missing",
            "Accepted semantic judgments must include the pre-input field vocabulary.",
        )
    raw_allowed = vocabulary.get("allowed_field_ids")
    if not isinstance(raw_allowed, list):
        raise _publication_failure(
            "field_vocabulary_provenance_missing",
            "Accepted semantic judgments must include allowed_field_ids.",
        )
    allowed_field_ids = {item for item in raw_allowed if isinstance(item, str)}
    materialized_slot_refs = _materialized_slot_refs(materialization)
    result: dict[str, JsonObject] = {}
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list):
        return result
    for judgment_index, judgment in enumerate(raw_judgments):
        if not isinstance(judgment, dict):
            continue
        parts = judgment.get("parts")
        spans = judgment.get("resolved_spans")
        if not isinstance(parts, list) or not isinstance(spans, list):
            continue
        for span in spans:
            if not isinstance(span, dict):
                continue
            slot_ref = span.get("slot_ref")
            field_id = span.get("field_id")
            span_ref = span.get("span_ref")
            part_index = span.get("part_index")
            if (
                not isinstance(slot_ref, str)
                or not isinstance(field_id, str)
                or not isinstance(span_ref, str)
                or not isinstance(part_index, int)
                or isinstance(part_index, bool)
            ):
                continue
            if field_id not in allowed_field_ids:
                raise _publication_failure(
                    "published_slot_field_not_in_vocabulary",
                    "A published slot field_id is not in the accepted input vocabulary.",
                )
            if field_id != registry.lookup(field_id).get("field_id"):
                raise _publication_failure(
                    "published_slot_field_invalid",
                    "A published slot field_id is not present in the Registry snapshot.",
                )
            if slot_ref not in materialized_slot_refs:
                raise _publication_failure(
                    "published_slot_receipt_missing",
                    "A published slot_ref is missing from the materialization receipt.",
                )
            part = parts[part_index] if 0 <= part_index < len(parts) else None
            if not isinstance(part, dict) or part.get("field_id") != field_id:
                raise _publication_failure(
                    "published_slot_part_mismatch",
                    "A published slot_ref does not match its accepted ordered part.",
                )
            parsed = _parse_slot_ref(slot_ref)
            if (
                parsed is None
                or parsed.get("span_ref") != span_ref
                or parsed.get("field_id") != field_id
            ):
                raise _publication_failure(
                    "published_slot_ref_invalid",
                    "A published slot_ref does not match its Harness span_ref and field_id.",
                )
            provenance: JsonObject = {
                "source": "harness_resolved_span",
                "source_judgment_ref": f"semantic_judgments[{judgment_index}]",
                "part_index": part_index,
                "span_ref": span_ref,
                "slot_ref": slot_ref,
                "field_vocabulary_digest": vocabulary.get("digest"),
            }
            reading_block_id = span.get("reading_block_id")
            if isinstance(reading_block_id, str) and reading_block_id.strip():
                provenance["reading_block_id"] = reading_block_id.strip()
            result[slot_ref] = provenance
    return result


def _materialized_slot_refs(materialization: JsonObject) -> set[str]:
    refs: set[str] = set()
    operations = materialization.get("operations")
    if isinstance(operations, list):
        for operation in operations:
            refs.update(_slot_refs_from_mapping(operation))
    receipts = materialization.get("mutation_receipts")
    if isinstance(receipts, list):
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            slot_refs = receipt.get("slot_refs")
            if isinstance(slot_refs, list):
                refs.update(item for item in slot_refs if isinstance(item, str) and item)
            refs.update(_slot_refs_from_mapping(receipt.get("operation")))
    return refs


def _slot_refs_from_mapping(value: object) -> set[str]:
    if not isinstance(value, dict):
        return set()
    refs: set[str] = set()
    slot_ref = value.get("slot_ref")
    if isinstance(slot_ref, str) and slot_ref.strip():
        refs.add(slot_ref.strip())
    members = value.get("members")
    if isinstance(members, list):
        for member in members:
            if not isinstance(member, dict):
                continue
            member_slot_ref = member.get("slot_ref")
            if isinstance(member_slot_ref, str) and member_slot_ref.strip():
                refs.add(member_slot_ref.strip())
    return refs


def _attach_slot_provenance(
    *,
    slots: list[JsonObject],
    provenance_by_slot_ref: dict[str, JsonObject],
) -> None:
    for slot in slots:
        slot_ref = slot.get("slot_ref")
        if not isinstance(slot_ref, str):
            raise _publication_failure(
                "published_slot_ref_missing",
                "Every fill-contract slot must carry its Harness slot_ref.",
            )
        provenance = provenance_by_slot_ref.get(slot_ref)
        if provenance is None:
            raise _publication_failure(
                "published_slot_provenance_missing",
                "A fill-contract slot is not backed by an accepted ordered part.",
            )
        slot["provenance"] = provenance


def publish_template_artifact(
    *,
    task_root: Path,
    source_docx: Path,
    candidate_docx: Path,
    field_registry: Path,
    validation: JsonObject,
    visual_review: JsonObject,
    allow_no_slots: bool = False,
    office: OfficeCliAdapter | None = None,
) -> JsonObject:
    """Bind final Word, Fill Contract, style evidence, and review to one hash."""

    adapter = office or OfficeCliAdapter()
    root = task_root.expanduser().resolve(strict=True)
    source = source_docx.expanduser().resolve(strict=True)
    candidate = candidate_docx.expanduser().resolve(strict=True)
    registry = FieldRegistrySnapshot.load(field_registry)
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    output = root / "output/final-template.docx"
    output_contract = root / "output/fill-contract.yaml"
    _assert_output_directory_ready(output, output_contract)
    if validation.get("final_sha256") != candidate_hash:
        raise _publication_failure(
            "validation_snapshot_mismatch",
            "Independent validation is not bound to the Agent-selected final Word.",
        )
    if visual_review.get("document_sha256") != candidate_hash:
        raise _publication_failure(
            "visual_review_snapshot_mismatch",
            "Final visual-review evidence is not bound to the Agent-selected Word.",
        )
    validate_docx_package(candidate)
    source_office_validation = _office_validation_status(source, adapter)
    candidate_office_validation = _office_validation_status(candidate, adapter)
    if (
        source_office_validation["passed"] is True
        and candidate_office_validation["passed"] is not True
    ):
        raise _publication_failure(
            "template_publication_officecli_regression",
            "The final template introduced an OfficeCLI OpenXML regression.",
        )
    office_validation = (
        candidate_office_validation
        if candidate_office_validation["passed"] is True
        else {
            "passed": False,
            "source": source_office_validation,
            "final": candidate_office_validation,
            "new_officecli_regression": "UNKNOWN",
        }
    )
    slots, structure_count = _published_slots(
        candidate_docx=candidate,
        registry=registry,
        office=adapter,
    )
    if slots:
        _attach_slot_provenance(
            slots=slots,
            provenance_by_slot_ref=_accepted_slot_provenance(root, registry),
        )
    if not slots and not allow_no_slots:
        raise _publication_failure(
            "fillable_slots_missing",
            "A clean school template must expose at least one Registry-bound fill interface.",
        )

    if slots:
        style_contracts, style_capture = capture_template_style_contracts(candidate, slots)
        school_capture = capture_template_style_observations(candidate, slots)
        if school_capture.failed_observations:
            raise _publication_failure(
                "school_style_observation_failed",
                "One or more final fill interfaces have no evaluable school style evidence.",
            )
        refs = {
            style.style_contract_id: {
                "style_contract_id": style.style_contract_id,
                "contract_digest": style.contract_digest,
            }
            for style in style_contracts.styles
        }
        for slot in slots:
            slot["style_contract_ref"] = refs[
                slot_style_contract_id(str(slot["slot_ref"]))
            ]
        style_payload = [style.as_dict() for style in style_contracts.styles]
        style_contract_set_digest = style_contracts.digest
        profile_registry_digest = school_capture.observation_set.profile_registry_digest
        school_observation_set_digest = school_capture.school_observation_set_digest
        school_candidates = list(school_capture.school_candidates)
        known_gaps = list(school_capture.known_gaps)
        school_capture_status = school_capture.status
        school_capture_payload = school_capture.as_dict()
    else:
        style_capture = {
            "status": "skipped",
            "reason": "accepted_terminal_source_noop_without_registry_slots",
        }
        style_payload = []
        style_contract_set_digest = sha256_json(
            {"schema_version": "docfit-template-style-contract-set/v1", "styles": []}
        )
        profile_registry_digest = DEFAULT_STYLE_PROPERTY_PROFILES.registry_digest
        school_observation_set_digest = sha256_json(
            {
                "schema_version": "docfit-school-style-observations/v1",
                "school_candidates": [],
                "known_gaps": [],
            }
        )
        school_candidates = []
        known_gaps = []
        school_capture_status = "skipped_no_registry_slots"
        school_capture_payload = {
            "status": school_capture_status,
            "profile_registry_digest": profile_registry_digest,
            "school_observation_set_digest": school_observation_set_digest,
            "school_candidates": [],
            "known_gaps": [],
            "failed_observations": [],
        }

    publication_dir = root / "work/.docfit/template-publication"
    publication_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(publication_dir / "school-style-observations.json", school_capture_payload)
    fill_contract: JsonObject = {
        "schema_version": "docfit-template-fill-contract/v2",
        "contract_id": f"docfit.template.{candidate_hash[:16]}",
        "artifact_role": "template_fill_contract",
        "status": "candidate_pending_human_acceptance",
        "revision": "1",
        "template_sha256": candidate_hash,
        "field_registry_ref": registry.identity(),
        "marker_protocol": "docfit-content-control-marker/v1",
        "profile_registry_digest": profile_registry_digest,
        "school_observation_set_digest": school_observation_set_digest,
        "school_style_candidates": school_candidates,
        "known_school_style_gaps": known_gaps,
        "regions": [],
        "slots": slots,
        "styles": style_payload,
        "style_contract_set_digest": style_contract_set_digest,
        "provenance": {
            "source_sha256": source_hash,
            "body_structure_count": structure_count,
            "agent_owned_semantics": True,
        },
        "review": {
            "status": "machine_checked_pending_human_signoff",
            "reviewer": None,
            "reviewed_at": None,
            "conclusion": "pending",
            "blockers": [],
            "prepared_by": "docfit-main-agent",
        },
        "validation": {
            "docx_validate": validation,
            "final_visual_review": visual_review,
            "style_capture": style_capture,
            "school_style_observation": {
                "status": school_capture_status,
                "artifact_path": "school-style-observations.json",
            },
            "officecli_validation": office_validation,
        },
    }
    contract_path = publication_dir / "fill-contract.yaml"
    _atomic_write_yaml(contract_path, fill_contract)

    if output.exists() or output_contract.exists():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_publication_exists",
            message="Publication never overwrites an existing Word/Fill Contract pair.",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    word_descriptor, word_temporary_name = tempfile.mkstemp(
        prefix=".final-template-", suffix=".docx", dir=output.parent
    )
    os.close(word_descriptor)
    contract_descriptor, contract_temporary_name = tempfile.mkstemp(
        prefix=".fill-contract-", suffix=".yaml", dir=output.parent
    )
    os.close(contract_descriptor)
    word_temporary = Path(word_temporary_name)
    contract_temporary = Path(contract_temporary_name)
    try:
        shutil.copyfile(candidate, word_temporary)
        shutil.copyfile(contract_path, contract_temporary)
        word_temporary.chmod(0o600)
        contract_temporary.chmod(0o600)
        os.link(word_temporary, output)
        try:
            os.link(contract_temporary, output_contract)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    except FileExistsError as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_publication_exists",
            message="Publication never overwrites an existing Word/Fill Contract pair.",
        ) from error
    finally:
        word_temporary.unlink(missing_ok=True)
        contract_temporary.unlink(missing_ok=True)
    published_entries = sorted(path.name for path in output.parent.iterdir())
    if set(published_entries) != _PUBLICATION_OUTPUTS:
        output.unlink(missing_ok=True)
        output_contract.unlink(missing_ok=True)
        raise _publication_failure(
            "template_output_directory_not_clean",
            "Publication must leave exactly final-template.docx and fill-contract.yaml.",
        )
    if (
        sha256_file(output) != candidate_hash
        or sha256_file(output_contract) != sha256_file(contract_path)
    ):
        output.unlink(missing_ok=True)
        output_contract.unlink(missing_ok=True)
        raise _publication_failure(
            "published_artifact_hash_mismatch",
            "The published Word/Fill Contract pair differs from the validated artifacts.",
        )

    counts: JsonObject = {
        "slot": len(slots),
        "remove": 0,
        "manual": 1 if allow_no_slots and not slots else 0,
        "gap": len(known_gaps),
        "unresolved": sum(
            len(item.get("unresolved_properties", []))
            for item in known_gaps
            if isinstance(item, dict)
        ),
    }
    receipt: JsonObject = {
        "schema_version": 1,
        "status": "ok",
        "published": True,
        "artifact_path": "output/final-template.docx",
        "fill_contract_path": "output/fill-contract.yaml",
        "template_sha256": candidate_hash,
        "counts": counts,
        "checks": [
            {"name": "source_unchanged", "result": "ok", "sha256": source_hash},
            {"name": "registry_bound", "result": "ok", **registry.identity()},
            {"name": "validation_bound", "result": "ok"},
            {"name": "visual_review_bound", "result": "ok"},
            {"name": "package_reopens", "result": "ok"},
            {"name": "fill_contract_hash_matches_word", "result": "ok"},
        ],
    }
    atomic_write_json(publication_dir / "build-report.json", receipt)
    return receipt

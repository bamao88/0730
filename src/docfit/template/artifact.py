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
from docfit.template.final_visual_review import validate_final_visual_review
from docfit.template.materialization.body_interfaces import body_interfaces, validate_coalescence
from docfit.template.materialization.models import AcceptedResolvedSpan
from docfit.template.materialization.vocabulary import (
    inventory_review_vocabulary_provenance_errors,
)
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_spans import (
    TextSourceExtent,
    parse_source_span_ref,
    resolve_source_span,
)
from docfit.template.unit_source import (
    require_initial_binding,
    source_unit_cut_points,
    validate_inventory_partition,
)
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
from docfit.tools.word_parts import read_word_stories
from docfit.visual.evidence import EvidenceStore

_PUBLICATION_OUTPUTS = {"final-template.docx", "fill-contract.yaml"}
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_W_NS}}}"
_SLOT_REF_FIELD_SEPARATOR = ";field_id="
_PUBLISHED_SLOT_REQUIRED_PART_ROLES = frozenset({"fill_slot", "body_structure"})
_NO_SLOT_MATERIALIZATION_EFFECT_PART_ROLES = frozenset({"cleanup", "generated_content"})
_PHASE6_PROVENANCE_SCHEMA = "docfit-template-materialization-provenance/v1"
_COALESCED_PROVENANCE_SCHEMA = "docfit-template-materialization-provenance/v2"


def validate_published_template_artifact(
    *,
    template_docx: Path,
    fill_contract: JsonObject,
    publication_receipt: JsonObject | None = None,
) -> JsonObject:
    """Validate the persisted Phase-6 package contract used by every consumer."""

    template = template_docx.expanduser().resolve(strict=True)
    template_hash = sha256_file(template)
    if (
        fill_contract.get("schema_version") != "docfit-template-fill-contract/v2"
        or fill_contract.get("template_sha256") != template_hash
    ):
        raise _artifact_contract_failure("The Fill Contract is not bound to this Word file.")
    provenance = fill_contract.get("provenance")
    phase6 = provenance.get("materialization") if isinstance(provenance, dict) else None
    digest = provenance.get("materialization_digest") if isinstance(provenance, dict) else None
    if (
        not isinstance(phase6, dict)
        or phase6.get("schema_version") not in {
            _PHASE6_PROVENANCE_SCHEMA, _COALESCED_PROVENANCE_SCHEMA,
        }
        or not isinstance(digest, str)
        or sha256_json(phase6) != digest
        or phase6.get("template_sha256") != template_hash
    ):
        raise _artifact_contract_failure(
            "Fill Contract v2 requires current, digest-bound materialization provenance."
        )
    required_hashes = (
        "source_sha256",
        "source_inventory_digest",
        "semantic_judgments_sha256",
        "field_vocabulary_digest",
    )
    if any(not _is_sha256(phase6.get(key)) for key in required_hashes):
        raise _artifact_contract_failure("Materialization provenance hashes are incomplete.")
    if phase6.get("field_registry_ref") != fill_contract.get("field_registry_ref") or (
        phase6.get("template_sha256") != phase6.get("source_sha256")
        and not _is_sha256(phase6.get("materialization_receipt_sha256"))
    ):
        raise _artifact_contract_failure(
            "Materialization provenance is not bound to the package Registry and receipt."
        )
    partition = phase6.get("source_partition")
    try:
        if not isinstance(partition, dict):
            raise ValueError("Artifact lacks its initial source partition.")
        partition_units = validate_inventory_partition(partition)
        if (
            partition["canonical_source_inventory"]["inventory_digest"]
            != phase6["source_inventory_digest"]
            or partition["unit_projection_digest"] != phase6.get("unit_projection_digest")
            or partition["document_sha256"] != phase6["source_sha256"]
        ):
            raise ValueError("Artifact source partition binding differs.")
    except ValueError as error:
        raise _artifact_contract_failure(str(error)) from error
    cut_points = source_unit_cut_points(partition_units)
    raw_slots = fill_contract.get("slots")
    provenance_slots = phase6.get("slots")
    if not isinstance(raw_slots, list) or not isinstance(provenance_slots, list):
        raise _artifact_contract_failure("Materialization slot provenance is missing.")
    by_slot_ref: dict[str, JsonObject] = {}
    for item in provenance_slots:
        if not isinstance(item, dict):
            raise _artifact_contract_failure("Materialization slot provenance is malformed.")
        slot_ref = item.get("slot_ref")
        if not isinstance(slot_ref, str) or slot_ref in by_slot_ref:
            raise _artifact_contract_failure("Materialization slot references must be unique.")
        by_slot_ref[slot_ref] = item
    coalesced_refs = {
        ref for ref, item in by_slot_ref.items() if "coalescence" in item
    }
    declared_refs = phase6.get("coalesced_body_slot_refs")
    if phase6["schema_version"] == _COALESCED_PROVENANCE_SCHEMA:
        if (
            not isinstance(declared_refs, list) or not declared_refs
            or any(not isinstance(ref, str) for ref in declared_refs)
            or len(declared_refs) != len(set(declared_refs))
            or set(declared_refs) != coalesced_refs
        ):
            raise _artifact_contract_failure("Coalesced body interface provenance is incomplete.")
    elif coalesced_refs or declared_refs is not None:
        raise _artifact_contract_failure("Coalesced body interfaces require provenance schema v2.")
    controls = _persisted_slot_controls(template)
    expected_controls: dict[str, str] = {}
    for raw_slot in raw_slots:
        if not isinstance(raw_slot, dict):
            raise _artifact_contract_failure("A Fill Contract slot is malformed.")
        slot_ref = raw_slot.get("slot_ref")
        field_id = raw_slot.get("field_id")
        span_ref = raw_slot.get("span_ref")
        slot_provenance = raw_slot.get("provenance")
        canonical = by_slot_ref.get(slot_ref) if isinstance(slot_ref, str) else None
        if (
            not isinstance(field_id, str)
            or not isinstance(span_ref, str)
            or not isinstance(slot_provenance, dict)
            or canonical != slot_provenance
            or canonical is None
            or canonical.get("field_id") != field_id
            or canonical.get("span_ref") != span_ref
            or canonical.get("source_snapshot_sha256") != phase6.get("source_sha256")
            or canonical.get("source_inventory_digest") != phase6.get("source_inventory_digest")
        ):
            raise _artifact_contract_failure(
                "A Fill Contract slot does not match its accepted span provenance."
            )
        source_entry_id = canonical.get("source_entry_id")
        word_fragments = canonical.get("word_fragments")
        accepted_span = canonical.get("accepted_span")
        actual_result = canonical.get("actual_result")
        accepted_result = canonical.get("accepted_result")
        try:
            typed_span = (
                AcceptedResolvedSpan.from_json(accepted_span)
                if isinstance(accepted_span, dict)
                else None
            )
        except ValueError as error:
            raise _artifact_contract_failure(
                "A Fill Contract slot has malformed accepted span provenance."
            ) from error
        parsed_span = parse_source_span_ref(span_ref)
        if typed_span is None or parsed_span is None:
            raise _artifact_contract_failure(
                "A Fill Contract slot has malformed SourceSpan provenance."
            )
        try:
            source_span = parsed_span[1]
            extent = source_span.extent
            if isinstance(extent, TextSourceExtent) and any(
                extent.start < cut < extent.end
                for cut in cut_points.get(source_span.source_entry_id, set())
            ):
                raise ValueError("Published span crosses an accepted unit cut.")
            exact = resolve_source_span(inventory=partition, source_span=source_span)
            if not typed_span.matches(exact):
                raise ValueError("Published span differs from the initial source partition.")
        except ValueError as error:
            raise _artifact_contract_failure(str(error)) from error
        if (
            typed_span is None
            or typed_span.span_ref != span_ref
            or typed_span.slot_ref != slot_ref
            or typed_span.field_id != field_id
            or typed_span.source_entry_id != source_entry_id
            or typed_span.source_snapshot_sha256 != phase6.get("source_sha256")
            or typed_span.source_inventory_digest != phase6.get("source_inventory_digest")
            or list(typed_span.word_fragments) != word_fragments
            or not isinstance(source_entry_id, str)
            or not source_entry_id
            or not isinstance(canonical.get("expected_source_content"), str)
            or not isinstance(word_fragments, list)
            or not word_fragments
            or any(not isinstance(fragment, dict) for fragment in word_fragments)
            or not isinstance(accepted_result, dict)
            or accepted_result.get("semantic_judgments_sha256")
            != phase6.get("semantic_judgments_sha256")
            or accepted_result.get("field_vocabulary_digest")
            != phase6.get("field_vocabulary_digest")
            or not isinstance(actual_result, dict)
            or actual_result.get("outcome") != "applied"
            or actual_result.get("candidate_before_sha256") != phase6.get("source_sha256")
            or actual_result.get("candidate_after_sha256") != template_hash
            or not _is_sha256(actual_result.get("operation_sha256"))
            or not _is_sha256(actual_result.get("mutation_receipt_sha256"))
        ):
            raise _artifact_contract_failure(
                "A Fill Contract slot lacks exact fragments or an actual mutation result."
            )
        if "coalescence" in canonical:
            try:
                record = canonical["coalescence"]
                if not isinstance(record, dict):
                    raise ValueError("Coalesced body interface provenance is malformed.")
                validate_coalescence(
                    record, anchor=typed_span, partition=partition, cut_points=cut_points,
                )
            except (ValueError, TypeError, AttributeError) as error:
                raise _artifact_contract_failure(str(error)) from error
        if not isinstance(slot_ref, str):
            raise _artifact_contract_failure("A Fill Contract slot_ref is malformed.")
        expected_controls[slot_ref] = field_id
    if set(by_slot_ref) != set(expected_controls) or controls != expected_controls:
        raise _artifact_contract_failure(
            "The Word controls, Fill Contract slots, and provenance ledger do not match."
        )
    if publication_receipt is not None and (
        publication_receipt.get("schema_version") != 2
        or publication_receipt.get("template_sha256") != template_hash
        or publication_receipt.get("materialization_digest") != digest
        or publication_receipt.get("fill_contract_sha256") != fill_contract.get("contract_sha256")
    ):
        raise _artifact_contract_failure(
            "The publication receipt does not match the persisted template package."
        )
    return phase6


def _artifact_contract_failure(message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="postcondition",
        code="template_artifact_provenance_invalid",
        message=message,
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _persisted_slot_controls(document: Path) -> dict[str, str]:
    try:
        with zipfile.ZipFile(document) as archive:
            roots = {story.part_name: story.root for story in read_word_stories(archive).values()}
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as error:
        raise _artifact_contract_failure(
            "The published Word package cannot be reopened."
        ) from error
    controls: dict[str, str] = {}
    for control in (control for root in roots.values() for control in root.iter(f"{_W}sdt")):
        tag = _content_control_value(control, "tag")
        alias = _content_control_value(control, "alias")
        if tag is None or alias is None or _parse_slot_ref(tag) is None:
            continue
        if tag in controls:
            raise _artifact_contract_failure("The published Word contains duplicate slot tags.")
        controls[tag] = alias
    return controls


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
    parsed_source_span = parse_source_span_ref(span_ref)
    if parsed_source_span is None:
        return None
    source_snapshot_sha256, source_span = parsed_source_span
    result: JsonObject = {
        "slot_ref": value,
        "span_ref": span_ref,
        "field_id": field_id.strip(),
        "scope": {"source_entry_id": source_span.source_entry_id},
    }
    extent = source_span.extent
    if isinstance(extent, TextSourceExtent):
        result["extent"] = {
            "kind": "text",
            "start": extent.start,
            "end": extent.end,
        }
    else:
        result["extent"] = {"kind": "whole_entry"}
    result["source_snapshot_sha256"] = source_snapshot_sha256
    return result


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
            roots = {story.part_name: story.root for story in read_word_stories(archive).values()}
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

    controls = [control for root in roots.values() for control in root.iter(f"{_W}sdt")]
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
            field = registry.lookup(field_id)
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
        if str(field.get("content_type", "")).casefold() == "section" and registry.has_children(
            field_id
        ):
            invalid.append(
                {
                    "code": "body_structure_container_field_published",
                    "slot_ref": slot_ref,
                    "field_id": field_id,
                    "message": ("Body-structure container fields are not published slot controls."),
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
                    (
                        "Repair the selected slot identity with a reviewed "
                        "materialize_slot action package."
                    ),
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
        if str(field.get("content_type", "")).casefold() == "section" and registry.has_children(
            field_id
        ):
            raise _publication_failure(
                "body_structure_container_field_published",
                (
                    "Body-structure container fields are internal structure refs, not "
                    "published slot controls."
                ),
            )
        if slot_ref in seen_tags:
            raise _publication_failure(
                "content_control_tag_duplicate",
                "Final content-control tags must be unique within the Word document.",
            )
        seen_tags.add(slot_ref)
        content_type = str(field.get("content_type", "text"))
        slot: JsonObject = {
            "slot_ref": slot_ref,
            "span_ref": protocol["span_ref"],
            "field_id": field_id,
            "content_type": content_type,
            "required": True,
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
    if slots:
        with zipfile.ZipFile(candidate_docx) as archive:
            stories = read_word_stories(archive)
        parts = {story.part_name: story.root for story in stories.values()}
        for slot in slots:
            matches = [
                part
                for part, root in parts.items()
                for control in root.iter(f"{_W}sdt")
                if _content_control_value(control, "tag") == slot["slot_ref"]
            ]
            if len(matches) != 1:
                raise _publication_failure(
                    "content_control_target_invalid",
                    "Each published slot must identify exactly one persisted Word control.",
                )
            part = matches[0]
            story_name = next(name for name, story in stories.items() if story.part_name == part)
            slot["locator"] = {
                "type": "content_control_tag",
                "value": slot["slot_ref"],
                "story": "document" if story_name == "body" else story_name.split("[")[0],
                "part": part,
                "expected_match_count": 1,
            }
    return slots, structure_count


def _accepted_slot_provenance(
    root: Path,
    registry: FieldRegistrySnapshot,
    *,
    source_hash: str,
    inventory: JsonObject | None,
    review: JsonObject | None,
    materialization: JsonObject | None,
) -> dict[str, JsonObject]:
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    if (
        not inventory_path.is_file()
        or not review_path.is_file()
        or not materialization_path.is_file()
    ):
        raise _publication_failure(
            "template_slot_provenance_missing",
            (
                "Publication requires accepted inventory, semantic judgments, and "
                "materialization receipt evidence."
            ),
        )
    if inventory is None or review is None or materialization is None:
        raise _publication_failure(
            "template_slot_provenance_missing",
            (
                "Publication requires accepted inventory, semantic judgments, and "
                "materialization receipt evidence."
            ),
        )
    try:
        require_initial_binding(root, inventory)
    except (ValueError, ToolFailure) as error:
        raise _publication_failure("template_initial_inventory_invalid", str(error)) from error
    if not _review_document_hash_matches(review, inventory, source_hash):
        raise _publication_failure(
            "template_slot_source_mismatch",
            "Slot publication semantic provenance is not bound to the source template.",
        )
    if not _review_semantic_digest_matches(review):
        raise _publication_failure(
            "template_slot_semantic_digest_mismatch",
            "Slot publication requires a current semantic_judgments digest.",
        )
    vocabulary_errors = inventory_review_vocabulary_provenance_errors(
        inventory=inventory,
        review=review,
        registry=registry,
    )
    if vocabulary_errors:
        _raise_publication_vocabulary_failure(vocabulary_errors[0])
    if not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=registry.pre_input_vocabulary(),
    ):
        raise _publication_failure(
            "template_slot_semantics_invalid",
            (
                "Slot publication requires current scope, ordered parts, and complete "
                "Harness resolved span coverage."
            ),
        )
    _assert_materialization_bound_to_review(
        materialization=materialization,
        review=review,
        registry=registry,
    )
    vocabulary = review.get("field_id_vocabulary")
    if not isinstance(vocabulary, dict):
        raise _publication_failure(
            "field_vocabulary_provenance_missing",
            "Accepted semantic judgments must include the pre-input field vocabulary.",
        )
    raw_allowed = vocabulary["allowed_field_ids"]
    if not isinstance(raw_allowed, list):
        raise _publication_failure(
            "field_vocabulary_provenance_missing",
            "Accepted semantic judgments must include allowed_field_ids.",
        )
    allowed_field_ids = {item for item in raw_allowed if isinstance(item, str)}
    materialized_operations = _materialized_slot_operations(materialization)
    result: dict[str, JsonObject] = {}
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list):
        return result
    cut_points = source_unit_cut_points(validate_inventory_partition(inventory))
    for judgment_index, judgment in enumerate(raw_judgments):
        if not isinstance(judgment, dict):
            continue
        parts = judgment.get("parts")
        spans = judgment.get("resolved_spans")
        if not isinstance(parts, list) or not isinstance(spans, list):
            continue
        groups = body_interfaces(
            [AcceptedResolvedSpan.from_json(span) for span in spans], cut_points=cut_points,
        )
        coalescences = {
            group.anchor.span_ref: group.coalescence() for group in groups
            if len(group.source_spans) > 1
        }
        secondary_refs = {
            span.span_ref for group in groups for span in group.source_spans[1:]
        }
        for span in spans:
            if not isinstance(span, dict):
                continue
            if span.get("span_ref") in secondary_refs:
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
            materialized_operation = _matching_materialized_operation(
                materialized_operations,
                slot_ref=slot_ref,
                span_ref=span_ref,
                field_id=field_id,
            )
            if materialized_operation is None:
                raise _publication_failure(
                    "published_slot_operation_mismatch",
                    (
                        "A published slot_ref is missing a matching materialization "
                        "operation for the accepted field_id and span_ref."
                    ),
                )
            coalescence = coalescences.get(span_ref)
            if materialized_operation.get("coalescence") != coalescence:
                raise _publication_failure(
                    "published_body_interface_mismatch",
                    "The physical body interface differs from its accepted source ranges.",
                )
            if materialized_operation.get("word_fragments") != span.get("word_fragments"):
                raise _publication_failure(
                    "published_slot_fragment_mismatch",
                    "A materialized slot does not preserve its accepted Word fragments.",
                )
            materialized_receipt = _matching_materialized_receipt(
                materialization,
                slot_ref=slot_ref,
                span_ref=span_ref,
                field_id=field_id,
            )
            if materialized_receipt is None:
                raise _publication_failure(
                    "published_slot_receipt_missing",
                    (
                        "A published slot_ref is missing matching field_id/span_ref "
                        "evidence in the materialization receipt."
                    ),
                )
            receipt_slots = _slot_infos_from_mapping(materialized_receipt.get("operation"))
            if not any(
                item.get("slot_ref") == slot_ref and item.get("coalescence") == coalescence
                for item in receipt_slots
            ):
                raise _publication_failure(
                    "published_body_interface_receipt_mismatch",
                    "The body interface receipt lost or changed its contributing source ranges.",
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
                "field_id": field_id,
                "span_ref": span_ref,
                "slot_ref": slot_ref,
                "source_entry_id": span.get("source_entry_id"),
                "source_snapshot_sha256": span.get("source_snapshot_sha256"),
                "source_inventory_digest": span.get("source_inventory_digest"),
                "expected_source_content": span.get("expected_source_content"),
                "word_fragments": span.get("word_fragments"),
                "accepted_span": dict(span),
                "accepted_result": {
                    "source_judgment_ref": f"semantic_judgments[{judgment_index}]",
                    "part_index": part_index,
                    "semantic_judgments_sha256": review.get("semantic_judgments_sha256"),
                    "field_vocabulary_digest": vocabulary.get("digest"),
                },
                "actual_result": {
                    "outcome": "applied",
                    "candidate_before_sha256": materialization.get("document_sha256"),
                    "candidate_after_sha256": materialization.get("write", {}).get("output_sha256")
                    if isinstance(materialization.get("write"), dict)
                    else None,
                    "operation_sha256": sha256_json(materialized_operation),
                    "mutation_receipt_sha256": sha256_json(materialized_receipt),
                },
            }
            if coalescence is not None:
                provenance["coalescence"] = coalescence
            result[slot_ref] = provenance
    return result


def _review_document_hash_matches(
    review: JsonObject,
    inventory: JsonObject,
    source_hash: str,
) -> bool:
    return (
        review.get("document_sha256") == source_hash
        and inventory.get("document_sha256") == source_hash
    )


def _review_semantic_digest_matches(review: JsonObject) -> bool:
    raw_judgments = review.get("semantic_judgments")
    digest = review.get("semantic_judgments_sha256")
    return (
        isinstance(raw_judgments, list)
        and isinstance(digest, str)
        and sha256_json(raw_judgments) == digest
    )


def _review_part_roles(review: JsonObject) -> tuple[str, ...] | None:
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list) or not raw_judgments:
        return None
    roles: list[str] = []
    for judgment in raw_judgments:
        if not isinstance(judgment, dict):
            return None
        parts = judgment.get("parts")
        if not isinstance(parts, list) or not parts:
            return None
        for part in parts:
            if not isinstance(part, dict):
                return None
            role = part.get("role")
            if not isinstance(role, str) or not role.strip():
                return None
            roles.append(role.strip().casefold())
    return tuple(roles)


def _review_field_ids(review: JsonObject) -> tuple[str, ...]:
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list):
        return ()
    field_ids: list[str] = []
    for judgment in raw_judgments:
        if not isinstance(judgment, dict):
            continue
        for key in ("parts", "resolved_spans"):
            values = judgment.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                field_id = item.get("field_id")
                if isinstance(field_id, str) and field_id.strip():
                    field_ids.append(field_id.strip())
    return tuple(dict.fromkeys(field_ids))


def _accepted_no_slot_publication_provenance(
    *,
    root: Path,
    registry: FieldRegistrySnapshot,
    source_hash: str,
    candidate_is_source: bool,
    inventory: JsonObject | None,
    review: JsonObject | None,
    materialization: JsonObject | None,
) -> JsonObject:
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    if not inventory_path.is_file() or not review_path.is_file():
        raise _publication_failure(
            "template_no_slot_provenance_missing",
            "No-slot publication requires accepted Harness semantic provenance.",
        )
    if inventory is None or review is None:
        raise _publication_failure(
            "template_no_slot_provenance_missing",
            "No-slot publication requires accepted Harness semantic provenance.",
        )
    try:
        require_initial_binding(root, inventory)
    except (ValueError, ToolFailure) as error:
        raise _publication_failure("template_initial_inventory_invalid", str(error)) from error
    if not _review_document_hash_matches(review, inventory, source_hash):
        raise _publication_failure(
            "template_no_slot_source_mismatch",
            "No-slot publication semantic provenance is not bound to the source template.",
        )
    if not _review_semantic_digest_matches(review):
        raise _publication_failure(
            "template_no_slot_semantic_digest_mismatch",
            "No-slot publication requires a current semantic_judgments digest.",
        )
    vocabulary_errors = inventory_review_vocabulary_provenance_errors(
        inventory=inventory,
        review=review,
        registry=registry,
    )
    if vocabulary_errors:
        _raise_publication_vocabulary_failure(vocabulary_errors[0])
    if not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=registry.pre_input_vocabulary(),
    ):
        raise _publication_failure(
            "template_no_slot_semantics_invalid",
            (
                "No-slot publication requires current scope, ordered parts, and "
                "complete Harness resolved span coverage."
            ),
        )
    vocabulary = review.get("field_id_vocabulary")
    raw_allowed = vocabulary.get("allowed_field_ids") if isinstance(vocabulary, dict) else None
    allowed_field_ids = {item for item in raw_allowed or [] if isinstance(item, str)}
    for field_id in _review_field_ids(review):
        if field_id not in allowed_field_ids:
            raise _publication_failure(
                "template_no_slot_field_not_in_vocabulary",
                "No-slot semantic field_id values must come from the accepted vocabulary.",
            )
        try:
            registry.lookup(field_id)
        except ToolFailure as error:
            raise _publication_failure(
                "template_no_slot_field_invalid",
                "No-slot semantic field_id values must exist in the Registry snapshot.",
            ) from error
    roles = _review_part_roles(review)
    if roles is None:
        raise _publication_failure(
            "template_no_slot_semantics_invalid",
            "No-slot publication requires current scope plus ordered parts semantics.",
        )
    if any(role in _PUBLISHED_SLOT_REQUIRED_PART_ROLES for role in roles):
        raise _publication_failure(
            "published_slots_missing_for_executable_semantics",
            "Accepted fill_slot or body_structure semantics require published slots.",
        )
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    if not candidate_is_source:
        if not materialization_path.is_file():
            raise _publication_failure(
                "template_no_slot_materialization_missing",
                "No-slot materialized candidates require materialization receipt evidence.",
            )
        if materialization is None:
            raise _publication_failure(
                "template_no_slot_materialization_missing",
                "No-slot materialized candidates require materialization receipt evidence.",
            )
        _assert_materialization_bound_to_review(
            materialization=materialization,
            review=review,
            registry=registry,
        )
    elif any(role in _NO_SLOT_MATERIALIZATION_EFFECT_PART_ROLES for role in roles):
        raise _publication_failure(
            "template_no_slot_materialization_missing",
            "Cleanup or generated-content no-slot semantics require a materialized candidate.",
        )
    provenance: JsonObject = {
        "source": "accepted_no_slot_semantic_review",
        "semantic_judgments_sha256": review.get("semantic_judgments_sha256"),
        "field_vocabulary_digest": review.get("field_vocabulary_digest"),
        "judgment_count": len(review["semantic_judgments"]),
        "roles": list(dict.fromkeys(roles)),
    }
    if not candidate_is_source:
        provenance["materialization_receipt"] = str(materialization_path.relative_to(root))
    return provenance


def _raise_publication_vocabulary_failure(error: JsonObject) -> None:
    code = error.get("code")
    message = error.get("message")
    raise _publication_failure(
        str(code) if isinstance(code, str) and code.strip() else "field_vocabulary_invalid",
        str(message)
        if isinstance(message, str) and message.strip()
        else "Publication requires accepted pre-input field vocabulary provenance.",
    )


def _assert_materialization_bound_to_review(
    *,
    materialization: JsonObject,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> None:
    if materialization.get("status") != "ok":
        raise _publication_failure(
            "published_slot_materialization_not_ok",
            "Publication requires an ok materialization receipt.",
        )
    review_digest = review.get("semantic_judgments_sha256")
    if (
        not isinstance(review_digest, str)
        or materialization.get("semantic_judgments_sha256") != review_digest
    ):
        raise _publication_failure(
            "published_slot_materialization_review_mismatch",
            "Materialization receipt is not bound to the accepted semantic judgments.",
        )
    for key in ("source_inventory_digest", "unit_projection_digest"):
        if materialization.get(key) != review.get(key):
            raise _publication_failure(
                "published_slot_materialization_source_mismatch",
                "Materialization receipt differs from its accepted source partition.",
            )
    vocabulary_digest = review.get("field_vocabulary_digest")
    if (
        not isinstance(vocabulary_digest, str)
        or materialization.get("field_vocabulary_digest") != vocabulary_digest
    ):
        raise _publication_failure(
            "published_slot_materialization_vocabulary_mismatch",
            "Materialization receipt is not bound to the accepted field vocabulary.",
        )
    if materialization.get("field_registry_ref") != registry.identity():
        raise _publication_failure(
            "published_slot_materialization_registry_mismatch",
            "Materialization receipt is not bound to the current Registry snapshot.",
        )
    from docfit.template.materialization.effect_verification import has_verified_effects

    if not has_verified_effects(materialization):
        raise _publication_failure(
            "materialization_effect_verification_missing",
            "Publication requires source-bound effects verified against the reopened candidate.",
        )


def _materialized_slot_operations(materialization: JsonObject) -> dict[str, list[JsonObject]]:
    slots: dict[str, list[JsonObject]] = {}
    operations = materialization.get("operations")
    if isinstance(operations, list):
        for operation in operations:
            for item in _slot_infos_from_mapping(operation):
                slot_ref = item.get("slot_ref")
                if isinstance(slot_ref, str) and slot_ref.strip():
                    slots.setdefault(slot_ref.strip(), []).append(item)
    return slots


def _matching_materialized_operation(
    materialized_operations: dict[str, list[JsonObject]],
    *,
    slot_ref: str,
    span_ref: str,
    field_id: str,
) -> JsonObject | None:
    matches = [
        item
        for item in materialized_operations.get(slot_ref, [])
        if item.get("span_ref") == span_ref and item.get("field_id") == field_id
    ]
    return matches[0] if len(matches) == 1 else None


def _matching_materialized_receipt(
    materialization: JsonObject,
    *,
    slot_ref: str,
    span_ref: str,
    field_id: str,
) -> JsonObject | None:
    matches: list[JsonObject] = []
    receipts = materialization.get("mutation_receipts")
    if isinstance(receipts, list):
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            slot_refs = _strings(receipt.get("slot_refs"))
            field_ids = _strings(receipt.get("field_ids"))
            span_refs = _strings(receipt.get("span_refs"))
            if slot_ref not in slot_refs or field_id not in field_ids or span_ref not in span_refs:
                continue
            if any(
                item.get("slot_ref") == slot_ref
                and item.get("field_id") == field_id
                and item.get("span_ref") == span_ref
                for item in _slot_infos_from_mapping(receipt.get("operation"))
            ):
                matches.append(receipt)
    return matches[0] if len(matches) == 1 else None


def _slot_infos_from_mapping(value: object) -> list[JsonObject]:
    if not isinstance(value, dict):
        return []
    result: list[JsonObject] = []
    info = _slot_info_from_mapping(value)
    if info is not None:
        result.append(info)
    members = value.get("members")
    if isinstance(members, list):
        for member in members:
            member_info = _slot_info_from_mapping(member)
            if member_info is not None:
                result.append(member_info)
    return result


def _slot_info_from_mapping(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    slot_ref = value.get("slot_ref")
    if not isinstance(slot_ref, str) or not slot_ref.strip():
        return None
    parsed = _parse_slot_ref(slot_ref.strip())
    if parsed is None:
        return None
    field_id = value.get("field_id")
    field_id = field_id.strip() if isinstance(field_id, str) and field_id.strip() else None
    span_ref = value.get("span_ref")
    span_ref = span_ref.strip() if isinstance(span_ref, str) and span_ref.strip() else None
    if field_id is None or span_ref is None:
        return None
    result = dict(value)
    result.update(
        {
            "slot_ref": slot_ref.strip(),
            "span_ref": span_ref,
            "field_id": field_id,
        }
    )
    return result


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip())
    )


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


def _phase6_contract_provenance(
    *,
    root: Path,
    source_hash: str,
    candidate_hash: str,
    registry: FieldRegistrySnapshot,
    slots: list[JsonObject],
    inventory: JsonObject | None,
    review: JsonObject | None,
    materialization: JsonObject | None,
) -> JsonObject:
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    if not review_path.is_file() or not inventory_path.is_file():
        raise _publication_failure(
            "template_artifact_provenance_missing",
            "Publication requires the persisted accepted review and source inventory.",
        )
    if review is None or inventory is None:
        raise _publication_failure(
            "template_artifact_provenance_missing",
            "Publication requires the persisted accepted review and source inventory.",
        )
    raw_spans = review.get("resolved_spans")
    inventory_digests = {
        str(span["source_inventory_digest"])
        for span in raw_spans or []
        if isinstance(span, dict) and _is_sha256(span.get("source_inventory_digest"))
    }
    if (
        not isinstance(raw_spans, list)
        or not raw_spans
        or len(inventory_digests) != 1
        or not _review_document_hash_matches(review, inventory, source_hash)
        or not _review_semantic_digest_matches(review)
    ):
        raise _publication_failure(
            "template_artifact_provenance_invalid",
            "Publication provenance is not bound to one accepted source inventory.",
        )
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    receipt_sha256: str | None = None
    materialization_required = candidate_hash != source_hash or bool(slots)
    if materialization_required and materialization_path.is_file():
        if materialization is None:
            raise _publication_failure(
                "template_artifact_materialization_missing",
                "A changed Word candidate requires a persisted materialization receipt.",
            )
        if (
            materialization.get("schema_version") != 2
            or materialization.get("document_sha256") != source_hash
            or not isinstance(materialization.get("write"), dict)
            or materialization["write"].get("output_sha256") != candidate_hash
        ):
            raise _publication_failure(
                "template_artifact_materialization_mismatch",
                "The materialization receipt does not describe the published Word result.",
            )
        receipt_sha256 = sha256_file(materialization_path)
    elif materialization_required:
        raise _publication_failure(
            "template_artifact_materialization_missing",
            "A changed Word candidate requires a persisted materialization receipt.",
        )
    phase6: JsonObject = {
        "schema_version": _PHASE6_PROVENANCE_SCHEMA,
        "source_sha256": source_hash,
        "template_sha256": candidate_hash,
        "source_inventory_digest": next(iter(inventory_digests)),
        "unit_projection_digest": inventory.get("unit_projection_digest"),
        "source_partition": {
            "document_sha256": inventory["document_sha256"],
            "canonical_source_inventory": inventory["canonical_source_inventory"],
            "source_entries": inventory["source_entries"],
            "unit_boundary_proof": inventory["unit_boundary_proof"],
            "unit_projection_digest": inventory["unit_projection_digest"],
        },
        "semantic_judgments_sha256": review.get("semantic_judgments_sha256"),
        "field_vocabulary_digest": review.get("field_vocabulary_digest"),
        "field_registry_ref": registry.identity(),
        "materialization_receipt_sha256": receipt_sha256,
        "slots": [dict(slot["provenance"]) for slot in slots],
    }
    coalesced_refs = [
        slot["slot_ref"] for slot in slots if "coalescence" in slot["provenance"]
    ]
    if coalesced_refs:
        phase6["schema_version"] = _COALESCED_PROVENANCE_SCHEMA
        phase6["coalesced_body_slot_refs"] = coalesced_refs
    return phase6


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
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    publication_inventory = read_json(inventory_path) if inventory_path.is_file() else None
    publication_review = read_json(review_path) if review_path.is_file() else None
    publication_materialization = (
        read_json(materialization_path) if materialization_path.is_file() else None
    )
    _assert_output_directory_ready(output, output_contract)
    if validation.get("final_sha256") != candidate_hash:
        raise _publication_failure(
            "validation_snapshot_mismatch",
            "Independent validation is not bound to the Harness-selected final Word.",
        )
    if visual_review.get("document_sha256") != candidate_hash:
        raise _publication_failure(
            "visual_review_snapshot_mismatch",
            "Final visual-review evidence is not bound to the Harness-selected Word.",
        )
    validate_final_visual_review(
        visual_review,
        candidate_hash=candidate_hash,
        source_hash=source_hash,
        store=EvidenceStore(root),
    )
    validation_checks = validation.get("checks", [])
    if (
        validation.get("status") != "ok"
        or validation.get("failure")
        or not isinstance(validation_checks, list)
        or any(
            not isinstance(check, dict) or check.get("blocking") is True
            for check in validation_checks
        )
    ):
        raise _publication_failure(
            "template_validation_blocked",
            "Independent final Word validation has not passed.",
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
    no_slot_provenance: JsonObject | None = None
    if slots:
        _attach_slot_provenance(
            slots=slots,
            provenance_by_slot_ref=_accepted_slot_provenance(
                root,
                registry,
                source_hash=source_hash,
                inventory=publication_inventory,
                review=publication_review,
                materialization=publication_materialization,
            ),
        )
    elif allow_no_slots:
        no_slot_provenance = _accepted_no_slot_publication_provenance(
            root=root,
            registry=registry,
            source_hash=source_hash,
            candidate_is_source=candidate == source,
            inventory=publication_inventory,
            review=publication_review,
            materialization=publication_materialization,
        )
    else:
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
            if slot.get("handling") == "styled":
                slot["style_contract_ref"] = refs[slot_style_contract_id(str(slot["slot_ref"]))]
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
    contract_provenance: JsonObject = {
        "source_sha256": source_hash,
        "body_structure_count": structure_count,
        "agent_owned_semantics": True,
    }
    if no_slot_provenance is not None:
        contract_provenance["no_slot_semantic_provenance"] = no_slot_provenance
    phase6_provenance = _phase6_contract_provenance(
        root=root,
        source_hash=source_hash,
        candidate_hash=candidate_hash,
        registry=registry,
        slots=slots,
        inventory=publication_inventory,
        review=publication_review,
        materialization=publication_materialization,
    )
    contract_provenance["materialization"] = phase6_provenance
    contract_provenance["materialization_digest"] = sha256_json(phase6_provenance)

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
        "provenance": contract_provenance,
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
    validate_published_template_artifact(
        template_docx=candidate,
        fill_contract=fill_contract,
    )
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
    if sha256_file(output) != candidate_hash or sha256_file(output_contract) != sha256_file(
        contract_path
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
        "schema_version": 2,
        "status": "ok",
        "published": True,
        "artifact_path": "output/final-template.docx",
        "fill_contract_path": "output/fill-contract.yaml",
        "template_sha256": candidate_hash,
        "fill_contract_sha256": sha256_file(output_contract),
        "materialization_digest": contract_provenance["materialization_digest"],
        "materialization_receipt_sha256": phase6_provenance.get("materialization_receipt_sha256"),
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
    persisted_contract = dict(fill_contract)
    persisted_contract["contract_sha256"] = sha256_file(output_contract)
    try:
        validate_published_template_artifact(
            template_docx=output,
            fill_contract=persisted_contract,
            publication_receipt=receipt,
        )
    except BaseException:
        output.unlink(missing_ok=True)
        output_contract.unlink(missing_ok=True)
        raise
    try:
        atomic_write_json(publication_dir / "build-report.json", receipt)
    except BaseException:
        output.unlink(missing_ok=True)
        output_contract.unlink(missing_ok=True)
        raise
    return receipt

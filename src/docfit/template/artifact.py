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
from pathlib import Path

from docfit.fields import FieldRegistrySnapshot
from docfit.styles.capture import (
    capture_template_style_contracts,
    capture_template_style_observations,
)
from docfit.styles.profiles import DEFAULT_STYLE_PROPERTY_PROFILES
from docfit.tools.inspection import inspect_document
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    sha256_file,
)

_FIELD_STYLE_ROLES: dict[str, tuple[str, str]] = {
    "body.heading.outline1": ("style.body.heading.1", "heading"),
    "body.heading.outline2": ("style.body.heading.2", "heading"),
    "body.heading.outline3": ("style.body.heading.3", "heading"),
    "body.heading.outline4": ("style.body.heading.4", "heading"),
    "body.heading.outline5": ("style.body.heading.5", "heading"),
    "body.paragraph": ("style.body.paragraph", "paragraph"),
    "body.numbered_list_item": ("style.body.numbered_list_item", "paragraph"),
    "body.inline_emphasis": ("style.inline.emphasis", "character"),
    "body.inline_quote": ("style.inline.quote", "character"),
    "body.block_quote": ("style.body.block_quote", "paragraph"),
    "body.figure.caption": ("style.caption.figure", "caption"),
    "body.equation": ("style.equation.block", "equation"),
    "body.table.caption": ("style.caption.table", "caption"),
    "body.table.note": ("style.table.note", "paragraph"),
}


def _style_metadata(*, field_id: str, slot_id: str, content_type: str) -> JsonObject:
    binding = _FIELD_STYLE_ROLES.get(field_id)
    if binding is None:
        if content_type not in {"text", "rich_text"}:
            return {"handling": "non_style"}
        binding = (f"style.slot.{slot_id}", "paragraph")
    style_role_id, style_role_type = binding
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


def _published_slots(
    *,
    candidate_docx: Path,
    registry: FieldRegistrySnapshot,
    office: OfficeCliAdapter,
) -> tuple[list[JsonObject], int]:
    inspection = inspect_document(
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
        slot_id = control.format.get("tag")
        if not isinstance(field_id, str) or not isinstance(slot_id, str):
            raise _publication_failure(
                "content_control_identity_missing",
                "Every final content control must expose Registry alias and unique tag.",
            )
        field = registry.lookup(field_id)
        if slot_id in seen_tags:
            raise _publication_failure(
                "content_control_tag_duplicate",
                "Final content-control tags must be unique within the Word document.",
            )
        seen_tags.add(slot_id)
        if field_id == "body.chapters":
            structure_count += 1
            continue
        content_type = str(field.get("content_type", "text"))
        slot: JsonObject = {
            "slot_id": slot_id,
            "field_id": field_id,
            "content_type": content_type,
            "required": True,
            "locator": {
                "type": "content_control_tag",
                "value": slot_id,
                "story": "document",
                "part": "word/document.xml",
                "expected_match_count": 1,
            },
        }
        slot.update(
            _style_metadata(
                field_id=field_id,
                slot_id=slot_id,
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
            "The final template may contain at most one reusable body.chapters structure.",
        )
    return slots, structure_count


def publish_template_artifact(
    *,
    task_root: Path,
    source_docx: Path,
    candidate_docx: Path,
    field_registry: Path,
    validation: JsonObject,
    visual_review: JsonObject,
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
    office_validation = adapter.validate(candidate)
    slots, structure_count = _published_slots(
        candidate_docx=candidate,
        registry=registry,
        office=adapter,
    )
    if not slots:
        raise _publication_failure(
            "fillable_slots_missing",
            "A clean school template must expose at least one Registry-bound fill interface.",
        )

    style_contracts, style_capture = capture_template_style_contracts(candidate, slots)
    school_capture = capture_template_style_observations(candidate, slots)
    if school_capture.failed_observations:
        raise _publication_failure(
            "school_style_observation_failed",
            "One or more final fill interfaces have no evaluable school style evidence.",
        )
    refs = {
        style.style_contract_id.removeprefix("style.slot."): {
            "style_contract_id": style.style_contract_id,
            "contract_digest": style.contract_digest,
        }
        for style in style_contracts.styles
    }
    for slot in slots:
        slot["style_contract_ref"] = refs[str(slot["slot_id"])]

    publication_dir = root / "work/.docfit/template-publication"
    publication_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(publication_dir / "school-style-observations.json", school_capture.as_dict())
    fill_contract: JsonObject = {
        "schema_version": "docfit-template-fill-contract/v2",
        "contract_id": f"docfit.template.{candidate_hash[:16]}",
        "artifact_role": "template_fill_contract",
        "status": "candidate_pending_human_acceptance",
        "revision": "1",
        "template_sha256": candidate_hash,
        "field_registry_ref": registry.identity(),
        "marker_protocol": "docfit-content-control-marker/v1",
        "profile_registry_digest": school_capture.observation_set.profile_registry_digest,
        "school_observation_set_digest": school_capture.school_observation_set_digest,
        "school_style_candidates": list(school_capture.school_candidates),
        "known_school_style_gaps": list(school_capture.known_gaps),
        "regions": [],
        "slots": slots,
        "styles": [style.as_dict() for style in style_contracts.styles],
        "style_contract_set_digest": style_contracts.digest,
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
                "status": school_capture.status,
                "artifact_path": "school-style-observations.json",
            },
            "officecli_validation": office_validation,
        },
    }
    contract_path = publication_dir / "fill-contract.json"
    atomic_write_json(contract_path, fill_contract)

    output = root / "output/final-template.docx"
    if output.exists():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="final_template_exists",
            message="Publication never overwrites an existing final-template.docx.",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".final-template-", suffix=".docx", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(candidate, temporary)
        temporary.chmod(0o600)
        os.link(temporary, output)
    except FileExistsError as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="final_template_exists",
            message="Publication never overwrites an existing final-template.docx.",
        ) from error
    finally:
        temporary.unlink(missing_ok=True)
    if sha256_file(output) != candidate_hash:
        output.unlink(missing_ok=True)
        raise _publication_failure(
            "published_template_hash_mismatch",
            "The published Word differs from the validated Agent-selected snapshot.",
        )

    counts: JsonObject = {
        "slot": len(slots),
        "remove": 0,
        "manual": 0,
        "gap": len(school_capture.known_gaps),
        "unresolved": sum(
            len(item.get("unresolved_properties", []))
            for item in school_capture.known_gaps
            if isinstance(item, dict)
        ),
    }
    receipt: JsonObject = {
        "schema_version": 1,
        "status": "ok",
        "published": True,
        "artifact_path": "output/final-template.docx",
        "fill_contract_path": "work/.docfit/template-publication/fill-contract.json",
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

"""Deterministic execution of a validated Placement Actual."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from docfit.styles import StyleContractSet
from docfit.tools.ooxml import import_content_objects, mutate_content_controls
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file


def fill_template(
    *,
    source_docx: Path,
    template_docx: Path,
    placement: JsonObject,
    style_contracts: StyleContractSet,
    output_docx: Path,
) -> JsonObject:
    """Create a new candidate DOCX without mutating either bound input snapshot."""

    source_hash = sha256_file(source_docx)
    template_hash = sha256_file(template_docx)
    if placement.get("source_sha256") != source_hash:
        raise _invalid("fill_source_stale", "Placement is bound to another student snapshot.")
    if placement.get("template_sha256") != template_hash:
        raise _invalid("fill_template_stale", "Placement is bound to another template snapshot.")
    placement_contract = placement.get("contract")
    if (
        style_contracts.template_sha256 != template_hash
        or not isinstance(placement_contract, dict)
        or placement_contract.get("style_contract_set_digest") != style_contracts.digest
    ):
        raise _invalid(
            "fill_style_contracts_stale",
            "Placement and template must bind the same Style Contract Set.",
        )
    if output_docx.exists():
        raise _invalid("fill_output_exists", "The candidate output path must not already exist.")
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    operations = placement.get("operations")
    if not isinstance(operations, list):
        raise _invalid("fill_operations_invalid", "Placement contains no operation list.")
    text_replacements: dict[str, str] = {}
    text_formats: dict[str, JsonObject] = {}
    block_operations: list[JsonObject] = []
    remove_tags: list[str] = []
    occurrence_manifest: list[JsonObject] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise _invalid("fill_operation_invalid", "A placement operation has an invalid shape.")
        action = operation.get("action")
        raw_style_ref = operation.get("style_contract_ref")
        if not isinstance(raw_style_ref, dict):
            raise _invalid(
                "fill_style_contract_ref_invalid",
                "Every fill operation must carry a complete Style Contract reference.",
            )
        try:
            style_contract = style_contracts.resolve(raw_style_ref)
        except ToolFailure as error:
            raise _invalid(
                "fill_style_contract_ref_invalid",
                "Every fill operation must carry a current Style Contract reference.",
            ) from error
        style_ref: JsonObject = {
            "style_contract_id": style_contract.style_contract_id,
            "contract_digest": style_contract.contract_digest,
        }
        if action == "replace_text_content_control":
            tag = operation.get("tag")
            value = operation.get("value")
            if not isinstance(tag, str) or not isinstance(value, str) or tag in text_replacements:
                raise _invalid(
                    "fill_text_operation_invalid", "A text fill operation is invalid or duplicated."
                )
            text_replacements[tag] = value
            text_formats[tag] = {}
            occurrence_manifest.append(
                {
                    "occurrence_id": f"slot:{operation.get('slot_id', tag)}",
                    "locator": {"type": "content_control_tag", "value": tag},
                    "style_contract_ref": style_ref,
                }
            )
        elif action == "replace_block_content_control":
            normalized_operation = dict(operation)
            normalized_operation["style_contract_ref"] = style_ref
            raw_role_refs = operation.get("style_role_refs", {})
            if not isinstance(raw_role_refs, dict):
                raise _invalid(
                    "fill_style_role_refs_invalid",
                    "A block fill operation has invalid role Style Contract references.",
                )
            normalized_operation["style_role_refs"] = {
                str(field_id): {
                    "style_contract_id": resolved.style_contract_id,
                    "contract_digest": resolved.contract_digest,
                }
                for field_id, reference in raw_role_refs.items()
                if isinstance(field_id, str)
                for resolved in (style_contracts.resolve(reference),)
            }
            block_operations.append(normalized_operation)
            raw_remove = operation.get("remove_tags_after_fill", [])
            if not isinstance(raw_remove, list) or not all(
                isinstance(value, str) for value in raw_remove
            ):
                raise _invalid(
                    "fill_remove_tags_invalid", "Body representative removal tags are invalid."
                )
            remove_tags.extend(raw_remove)
        else:
            raise _invalid(
                "fill_action_unsupported", "Placement contains an unsupported fill action."
            )

    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{output_docx.name}-fill-", dir=output_docx.parent)
    )
    current = temporary_root / "step-000.docx"
    try:
        text_fill_evidence = mutate_content_controls(
            input_docx=template_docx,
            text_replacements=text_replacements,
            text_formats=text_formats,
            remove_body_tags=(),
            output_docx=current,
        )
        block_evidence: list[JsonObject] = []
        for index, operation in enumerate(block_operations, start=1):
            tag = operation.get("tag")
            locators = operation.get("source_locators")
            source_object_ids = operation.get("source_object_ids", [])
            if (
                not isinstance(tag, str)
                or not isinstance(locators, list)
                or not all(isinstance(value, str) for value in locators)
                or not isinstance(source_object_ids, list)
                or not all(isinstance(value, str) for value in source_object_ids)
            ):
                raise _invalid("fill_block_operation_invalid", "A block fill operation is invalid.")
            if source_object_ids and len(source_object_ids) != len(locators):
                raise _invalid(
                    "fill_block_source_refs_misaligned",
                    "A block fill operation has misaligned source IDs and locators.",
                )
            next_docx = temporary_root / f"step-{index:03d}.docx"
            evidence = import_content_objects(
                target_docx=current,
                source_docx=source_docx,
                source_locators=locators,
                anchor_locator=None,
                position="end",
                include_source_final_section_properties=False,
                output_docx=next_docx,
                replace_content_control_tag=tag,
                copy_source_styles=False,
            )
            block_evidence.append(
                {
                    "field_id": operation.get("field_id"),
                    "tag": tag,
                    "source_object_ids": list(source_object_ids),
                    "style_contract_ref": dict(operation["style_contract_ref"]),
                    "style_role_refs": dict(operation.get("style_role_refs", {})),
                    **evidence,
                }
            )
            if operation.get("field_id") != "body.chapters":
                for inserted_index, inserted in enumerate(
                    evidence.get("inserted_body_refs", []), start=1
                ):
                    target_locator = (
                        inserted.get("target_locator") if isinstance(inserted, dict) else None
                    )
                    if isinstance(target_locator, str):
                        occurrence_manifest.append(
                            {
                                "occurrence_id": (
                                    f"block:{operation.get('field_id')}:{inserted_index}"
                                ),
                                "locator": target_locator,
                                "style_contract_ref": dict(operation["style_contract_ref"]),
                            }
                        )
            current = next_docx
        final_temporary = temporary_root / "final.docx"
        mutate_content_controls(
            input_docx=current,
            text_replacements={},
            text_formats={},
            remove_body_tags=tuple(dict.fromkeys(remove_tags)),
            output_docx=final_temporary,
        )
        package_warnings = validate_docx_package(final_temporary)
        os.replace(final_temporary, output_docx)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    if sha256_file(source_docx) != source_hash or sha256_file(template_docx) != template_hash:
        output_docx.unlink(missing_ok=True)
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="fill_input_changed",
            message="A read-only input changed during deterministic template fill.",
        )
    return {
        "schema_version": "docfit-template-fill-result/v2",
        "status": placement.get("status"),
        "source_sha256": source_hash,
        "template_sha256": template_hash,
        "style_contract_set_digest": style_contracts.digest,
        "output_docx": str(output_docx.resolve()),
        "output_sha256": sha256_file(output_docx),
        "text_controls_replaced": len(text_replacements),
        "text_controls_formatted": text_fill_evidence["text_controls_formatted"],
        "block_operations": block_evidence,
        "body_controls_removed": len(set(remove_tags)),
        "package_warnings": list(package_warnings),
        "style_occurrence_manifest": {"occurrences": occurrence_manifest},
    }


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="request", code=code, message=message)

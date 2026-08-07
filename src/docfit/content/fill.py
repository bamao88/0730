"""Deterministic execution of a validated Placement Actual."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from docfit.tools.ooxml import import_content_objects, mutate_content_controls
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file


def fill_template(
    *,
    source_docx: Path,
    template_docx: Path,
    placement: JsonObject,
    output_docx: Path,
) -> JsonObject:
    """Create a new candidate DOCX without mutating either bound input snapshot."""

    source_hash = sha256_file(source_docx)
    template_hash = sha256_file(template_docx)
    if placement.get("source_sha256") != source_hash:
        raise _invalid("fill_source_stale", "Placement is bound to another student snapshot.")
    if placement.get("template_sha256") != template_hash:
        raise _invalid("fill_template_stale", "Placement is bound to another template snapshot.")
    if output_docx.exists():
        raise _invalid("fill_output_exists", "The candidate output path must not already exist.")
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    operations = placement.get("operations")
    if not isinstance(operations, list):
        raise _invalid("fill_operations_invalid", "Placement contains no operation list.")
    text_replacements: dict[str, str] = {}
    block_operations: list[JsonObject] = []
    remove_tags: list[str] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise _invalid("fill_operation_invalid", "A placement operation has an invalid shape.")
        action = operation.get("action")
        if action == "replace_text_content_control":
            tag = operation.get("tag")
            value = operation.get("value")
            if not isinstance(tag, str) or not isinstance(value, str) or tag in text_replacements:
                raise _invalid(
                    "fill_text_operation_invalid", "A text fill operation is invalid or duplicated."
                )
            text_replacements[tag] = value
        elif action == "replace_block_content_control":
            block_operations.append(operation)
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
        mutate_content_controls(
            input_docx=template_docx,
            text_replacements=text_replacements,
            remove_body_tags=(),
            output_docx=current,
        )
        block_evidence: list[JsonObject] = []
        for index, operation in enumerate(block_operations, start=1):
            tag = operation.get("tag")
            locators = operation.get("source_locators")
            if (
                not isinstance(tag, str)
                or not isinstance(locators, list)
                or not all(isinstance(value, str) for value in locators)
            ):
                raise _invalid("fill_block_operation_invalid", "A block fill operation is invalid.")
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
                    **evidence,
                }
            )
            current = next_docx
        final_temporary = temporary_root / "final.docx"
        mutate_content_controls(
            input_docx=current,
            text_replacements={},
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
        "schema_version": "docfit-template-fill-result/v1",
        "status": placement.get("status"),
        "source_sha256": source_hash,
        "template_sha256": template_hash,
        "output_docx": str(output_docx.resolve()),
        "output_sha256": sha256_file(output_docx),
        "text_controls_replaced": len(text_replacements),
        "block_operations": block_evidence,
        "body_controls_removed": len(set(remove_tags)),
        "package_warnings": list(package_warnings),
    }


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="request", code=code, message=message)

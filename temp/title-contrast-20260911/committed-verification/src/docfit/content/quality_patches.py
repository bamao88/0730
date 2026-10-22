"""Load task-bound, evidence-checked student text quality patches."""

from __future__ import annotations

from pathlib import Path

import yaml

from docfit.content.projection import TextReplacement
from docfit.tools.runtime import JsonObject, ToolFailure

QUALITY_PATCH_SCHEMA_VERSION = "docfit-student-quality-patches/v1"


def load_quality_patches(
    path: Path,
    *,
    source_sha256: str,
    inventory: JsonObject,
) -> tuple[TextReplacement, ...]:
    """Return exact patches bound to one source snapshot and one source object each."""

    try:
        source = path.expanduser().resolve(strict=True)
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, yaml.YAMLError) as error:
        raise _invalid(
            "quality_patches_unreadable",
            "The task-bound quality patch file cannot be read.",
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != QUALITY_PATCH_SCHEMA_VERSION
    ):
        raise _invalid(
            "quality_patches_invalid",
            "The task-bound quality patch file has an unsupported shape.",
        )
    if payload.get("source_sha256") != source_sha256:
        raise _invalid(
            "quality_patches_source_stale",
            "The task-bound quality patches belong to another student snapshot.",
        )
    inventory_source = inventory.get("source_sha256")
    if inventory_source != source_sha256:
        raise _invalid(
            "quality_patches_inventory_stale",
            "The student inventory belongs to another source snapshot.",
        )
    by_object_id = {
        str(reference["object_id"]): item
        for item in inventory.get("objects", [])
        if isinstance(item, dict)
        and isinstance((reference := item.get("source_object_ref")), dict)
        and isinstance(reference.get("object_id"), str)
    }
    raw_patches = payload.get("patches")
    if not isinstance(raw_patches, list):
        raise _invalid(
            "quality_patches_list_invalid",
            "The task-bound quality patch collection must be a list.",
        )

    seen_patch_ids: set[str] = set()
    replacements: list[TextReplacement] = []
    for raw in raw_patches:
        if not isinstance(raw, dict):
            raise _invalid(
                "quality_patch_invalid",
                "A task-bound quality patch has an invalid shape.",
            )
        patch_id = raw.get("patch_id")
        source_object_id = raw.get("source_object_id")
        before = raw.get("before")
        after = raw.get("after")
        reason = raw.get("reason")
        expected_count = raw.get("expected_count", 1)
        if (
            not isinstance(patch_id, str)
            or not patch_id
            or patch_id in seen_patch_ids
            or not isinstance(source_object_id, str)
            or source_object_id not in by_object_id
            or not isinstance(before, str)
            or not before
            or not isinstance(after, str)
            or before == after
            or not isinstance(reason, str)
            or not reason
            or not isinstance(expected_count, int)
            or isinstance(expected_count, bool)
            or expected_count <= 0
        ):
            raise _invalid(
                "quality_patch_invalid",
                "A task-bound quality patch is incomplete, duplicated, or untraceable.",
            )
        source_text = by_object_id[source_object_id].get("text")
        if not isinstance(source_text, str) or source_text.count(before) != expected_count:
            raise _invalid(
                "quality_patch_evidence_mismatch",
                "A task-bound quality patch does not match its exact source object evidence.",
            )
        seen_patch_ids.add(patch_id)
        replacements.append(
            TextReplacement(
                old=before,
                new=after,
                expected_count=expected_count,
                source_object_id=source_object_id,
                patch_id=patch_id,
                reason=reason,
            )
        )
    return tuple(replacements)


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="request", code=code, message=message)

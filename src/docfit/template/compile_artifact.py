"""Compile human/Agent artifact decisions into a canonical, verified spec."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from docfit.template.runtime.atomic import write_json_file
from docfit.template.runtime.paths import task_file
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

MARKER_PROTOCOL = "docfit-content-control-marker/v1"
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_TOP_LEVEL_KEYS = {
    "schema_version",
    "final_snapshot_ref",
    "template_sha256",
    "field_registry_ref",
    "marker_protocol",
    "sources",
    "protected_regions",
    "slots",
    "remove_regions",
    "manual",
    "gaps",
    "unresolved",
    "style_claims",
    "mutation_evidence_chain",
    "final_review",
}


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _StrictLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_decisions",
                message="Decision object keys must be strings.",
            )
        if key in result:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="duplicate_decision_key",
                message="The decisions file contains a duplicate object key.",
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _load_object(path: Path) -> JsonObject:
    try:
        raw = path.read_bytes()
        if len(raw) > 2 * 1024 * 1024 or raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("size or BOM")
        text = raw.decode("utf-8")
        value: Any = (
            json.loads(text)
            if path.suffix.casefold() == ".json"
            else yaml.load(text, Loader=_StrictLoader)
        )
    except ToolFailure:
        raise
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_decisions",
            message="The artifact decisions file cannot be parsed safely.",
        ) from error
    if not isinstance(value, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_decisions",
            message="Artifact decisions must contain one object.",
        )
    return value


def _objects(value: Any, field: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_decisions",
            message=f"{field} must be an array of objects.",
        )
    return value


def _registry(
    decisions: JsonObject,
    *,
    task_root: Path,
) -> tuple[JsonObject, set[str]]:
    reference = decisions.get("field_registry_ref")
    if not isinstance(reference, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="A field Registry reference is required.",
        )
    path = task_file(
        reference.get("path"),
        task_root=task_root,
        field="field_registry_ref.path",
        allowed_roots=("input",),
    )
    registry = _load_object(path)
    if (
        reference.get("registry_id") != registry.get("registry_id")
        or reference.get("registry_version") != registry.get("registry_version")
        or reference.get("sha256") != sha256_file(path)
        or registry.get("registry_id") != "docfit.thesis.content_fields"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry binding does not match the referenced file.",
        )
    fields = registry.get("fields")
    if not isinstance(fields, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry has no valid field inventory.",
        )
    field_ids = {
        item["field_id"]
        for item in fields
        if isinstance(item, dict) and isinstance(item.get("field_id"), str)
    }
    return reference, field_ids


def _validate_locator(locator: Any) -> JsonObject:
    if not isinstance(locator, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="artifact_locator_invalid",
            message="Every artifact locator must be an object.",
        )
    forbidden = {"snapshot_ref", "object_id", "expected_fingerprint"}.intersection(locator)
    if forbidden or locator.get("expected_match_count") != 1:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="artifact_locator_not_persistent",
            message="Artifact locators cannot contain task-local evidence identities.",
        )
    if locator.get("story") not in {
        "document",
        "header",
        "footer",
        "footnote",
        "endnote",
        "textbox",
    } or not isinstance(locator.get("part"), str):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="artifact_locator_invalid",
            message="An artifact locator lacks a valid story or OOXML part.",
        )
    return locator


def _validate_review(
    decisions: JsonObject,
    *,
    snapshot: JsonObject,
    store: EvidenceStore,
) -> JsonObject:
    review = decisions.get("final_review")
    if not isinstance(review, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="review_page_missing",
            message="A final candidate review is required.",
        )
    comparison = store.resolve(review.get("comparison_ref"), expected_kind="comparison")
    if (
        review.get("final_snapshot_ref") != decisions.get("final_snapshot_ref")
        or comparison.get("final_snapshot_ref") != decisions.get("final_snapshot_ref")
        or comparison.get("document_sha256") != snapshot.get("document_sha256")
        or comparison.get("visual_level") != "candidate_verification"
        or review.get("visual_level") != "candidate_verification"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="final_comparison_not_candidate_verification",
            message="The final comparison does not bind the exact candidate snapshot.",
        )
    required = _objects(comparison.get("required_images"), "required_images")
    dispositions = _objects(review.get("image_dispositions"), "image_dispositions")
    by_id = {item.get("required_image_id"): item for item in dispositions}
    missing = [
        item.get("required_image_id")
        for item in required
        if item.get("required_image_id") not in by_id
    ]
    if missing or review.get("page_count") != len(required):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="required_image_without_disposition",
            message="Every final page requires an explicit Agent disposition.",
        )
    if any(
        by_id[item.get("required_image_id")].get("disposition") != "accepted"
        for item in required
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="blocking_finding_present",
            message="A required image was rejected by the final review.",
        )
    blockers = comparison.get("machine_blockers")
    if not isinstance(blockers, list) or blockers:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="blocking_finding_present",
            message="The final comparison contains an unresolved machine blocker.",
        )
    record: JsonObject = {
        "schema_version": 1,
        "final_snapshot_ref": decisions.get("final_snapshot_ref"),
        "comparison_ref": review.get("comparison_ref"),
        "render_ref": comparison.get("render_ref"),
        "document_sha256": snapshot.get("document_sha256"),
        "visual_level": "candidate_verification",
        "page_count": len(required),
        "required_images": [
            {key: value for key, value in item.items() if key != "render_page_path"}
            for item in required
        ],
        "image_dispositions": dispositions,
        "finding_dispositions": review.get("finding_dispositions", []),
        "machine_blockers": [],
    }
    record["review_digest"] = sha256_json(record)
    return record


def _validate_mutation_lineage(
    decisions: JsonObject,
    *,
    store: EvidenceStore,
) -> list[JsonObject]:
    chain = _objects(decisions.get("mutation_evidence_chain"), "mutation_evidence_chain")
    if not chain:
        return []
    previous_after: str | None = None
    normalized: list[JsonObject] = []
    for index, item in enumerate(chain, start=1):
        if item.get("sequence") != index:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="mutation_lineage_gap",
                message="Mutation lineage sequence numbers must be contiguous.",
            )
        mutation = store.resolve(item.get("mutation_ref"), expected_kind="mutation")
        comparison = store.resolve(item.get("comparison_ref"), expected_kind="comparison")
        before_ref = item.get("before_snapshot_ref")
        after_ref = item.get("after_snapshot_ref")
        if (
            mutation.get("before_snapshot_ref") != before_ref
            or mutation.get("after_snapshot_ref") != after_ref
            or comparison.get("review_mode") != "mutation_review"
            or comparison.get("mutation_ref") != item.get("mutation_ref")
            or comparison.get("before_snapshot_ref") != before_ref
            or comparison.get("after_snapshot_ref") != after_ref
            or comparison.get("machine_blockers") != []
            or comparison.get("unexpected_changes") != []
            or (previous_after is not None and previous_after != before_ref)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="mutation_lineage_gap",
                message="Mutation lineage evidence is discontinuous or contains blockers.",
            )
        previous_after = after_ref if isinstance(after_ref, str) else None
        normalized.append(item)
    if previous_after != decisions.get("final_snapshot_ref"):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="mutation_lineage_gap",
            message="Mutation lineage does not reach the final snapshot.",
        )
    return normalized


def compile_artifact_decisions(
    *,
    task_root: Path,
    input_path: Path,
    output_path: Path,
) -> JsonObject:
    root = task_root.resolve(strict=True)
    decisions_path = task_file(
        str(input_path),
        task_root=root,
        field="input",
        allowed_roots=("work",),
    )
    if decisions_path.parent.name != "decisions" or decisions_path.suffix.casefold() not in {
        ".yaml",
        ".yml",
        ".json",
    }:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="source_path_outside_task_root",
            message="Artifact decisions must be read from work/decisions.",
        )
    output = output_path if output_path.is_absolute() else root / output_path
    output = output.resolve(strict=False)
    if (
        output.exists()
        or root not in output.parents
        or output.parent.name != "compiled"
        or output.suffix.casefold() != ".json"
        or output.parent.is_symlink()
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="output_exists" if output.exists() else "invalid_compiler_output",
            message="Compiler output must be a new JSON file in work/compiled.",
        )
    decisions = _load_object(decisions_path)
    if decisions.get("schema_version") != 1 or set(decisions) != _TOP_LEVEL_KEYS:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_decisions",
            message="Artifact decisions do not match the v1 top-level contract.",
        )
    if decisions.get("marker_protocol") != MARKER_PROTOCOL:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="marker_protocol_mismatch",
            message="The marker protocol is not the approved v1 contract.",
        )
    store = EvidenceStore(root)
    snapshot = store.resolve(decisions.get("final_snapshot_ref"), expected_kind="snapshot")
    if decisions.get("template_sha256") != snapshot.get("document_sha256"):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="final_document_hash_mismatch",
            message="The template hash does not match the final snapshot.",
        )
    registry_ref, field_ids = _registry(decisions, task_root=root)
    sources = _objects(decisions.get("sources"), "sources")
    source_ids: set[str] = set()
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not _ID_PATTERN.fullmatch(source_id):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_path_outside_task_root",
                message="A source ID is invalid.",
            )
        source_path = task_file(
            source.get("path"),
            task_root=root,
            field=f"sources.{source_id}.path",
        )
        if source.get("sha256") != sha256_file(source_path):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_hash_declaration_mismatch",
                message="A declared source hash no longer matches its file.",
            )
        source_ids.add(source_id)
    protected = _objects(decisions.get("protected_regions"), "protected_regions")
    slots = _objects(decisions.get("slots"), "slots")
    remove = _objects(decisions.get("remove_regions"), "remove_regions")
    for name in ("manual", "gaps", "unresolved"):
        items = _objects(decisions.get(name), name)
        if any(item.get("blocking") is True for item in items):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="blocking_unresolved",
                message="A blocking manual, gap, or unresolved item prevents publication.",
            )
    slot_ids: set[str] = set()
    controls = snapshot.get("content_controls")
    if not isinstance(controls, list):
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="evidence_invalid",
            message="The final snapshot has no valid content-control inventory.",
        )
    for slot in slots:
        slot_id = slot.get("slot_id")
        field_id = slot.get("field_id")
        marker = slot.get("marker")
        if not isinstance(slot_id, str) or slot_id in slot_ids:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="duplicate_slot_id",
                message="Slot IDs must be unique.",
            )
        if (
            not isinstance(field_id, str)
            or not _FIELD_PATTERN.fullmatch(field_id)
            or field_id not in field_ids
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="field_not_registered",
                message="An automatic slot does not bind a registered field.",
            )
        if not isinstance(marker, dict) or marker != {"alias": field_id, "tag": slot_id}:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="marker_protocol_mismatch",
                message="A slot marker does not bind alias=field_id and tag=slot_id.",
            )
        _validate_locator(slot.get("artifact_locator"))
        matched = [
            item
            for item in controls
            if isinstance(item, dict)
            and item.get("alias") == field_id
            and item.get("tag") == slot_id
        ]
        if len(matched) != 1:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="slot_locator_not_unique",
                message="A slot marker does not resolve exactly once in the final document.",
            )
        slot_ids.add(slot_id)
    for region in (*protected, *remove):
        _validate_locator(region.get("artifact_locator"))
    mutation_lineage = _validate_mutation_lineage(decisions, store=store)
    review_record = _validate_review(decisions, snapshot=snapshot, store=store)
    contract_id = (
        f"{sources[0]['source_id']}.fill-contract"
        if sources
        else "template.fill-contract"
    )
    fill_contract: JsonObject = {
        "schema_version": "docfit-template-fill-contract/v1",
        "contract_id": contract_id,
        "artifact_role": "template_fill_contract",
        "status": "candidate_pending_human_acceptance",
        "contract_version": "1",
        "template_sha256": decisions["template_sha256"],
        "field_registry_ref": registry_ref,
        "marker_protocol": MARKER_PROTOCOL,
        "provenance": {"source_ids": sorted(source_ids)},
        "regions": [
            {
                "region_id": item["region_id"],
                "owner": item["owner"],
                "required": item["required"],
                "locator": item["artifact_locator"],
                **(
                    {"expected_style": item["expected_style"]}
                    if "expected_style" in item
                    else {}
                ),
                **(
                    {"forbidden_text": item["forbidden_text"]}
                    if "forbidden_text" in item
                    else {}
                ),
            }
            for item in (*protected, *remove)
        ],
        "slots": [
            {
                "slot_id": item["slot_id"],
                "owner": "slot",
                "field_id": item["field_id"],
                "content_type": item["content_type"],
                "required": item["required"],
                "cardinality": item["cardinality"],
                "locator": item["artifact_locator"],
                "fill_mode": "replace_content_control_content",
                "expected_value_style": item["expected_value_style"],
            }
            for item in slots
        ],
        "review": {
            "status": "machine_checked_pending_human_signoff",
            "reviewer": None,
            "reviewed_at": None,
            "conclusion": "pending",
            "blockers": [],
            "prepared_by": "docfit-school-extract-v2",
        },
    }
    compiled: JsonObject = {
        "schema_version": 1,
        "compiler": {
            "name": "compile_artifact_spec",
            "contract_version": 1,
            "implementation_version": "0.1.0",
        },
        "input_sha256": sha256_file(decisions_path),
        "task_binding": {
            "task_store_version": 1,
            "snapshot_ref": decisions["final_snapshot_ref"],
            "document_sha256": decisions["template_sha256"],
        },
        "field_registry_ref": registry_ref,
        "marker_protocol": MARKER_PROTOCOL,
        "sources": sources,
        "protected_regions": protected,
        "slots": slots,
        "remove_regions": remove,
        "manual": decisions["manual"],
        "gaps": decisions["gaps"],
        "unresolved": decisions["unresolved"],
        "style_claims": decisions["style_claims"],
        "mutation_lineage": mutation_lineage,
        "review_record": review_record,
        "fill_contract": fill_contract,
    }
    compiled["spec_digest"] = sha256_json(compiled)
    write_json_file(output, compiled)
    return compiled


def compiler_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compile_artifact_spec.py")
    parser.add_argument("--version", action="version", version="compile_artifact_spec 0.1.0")
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--input", required=True, dest="input_path")
    parser.add_argument("--output", required=True, dest="output_path")
    args = parser.parse_args(argv)
    task_root = Path(args.task_root).expanduser().resolve(strict=True)
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)
    try:
        compiled = compile_artifact_decisions(
            task_root=task_root,
            input_path=input_path,
            output_path=output_path,
        )
    except ToolFailure as error:
        print(
            json.dumps(
                {
                    "code": error.code,
                    "field": None,
                    "message": error.message,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2 if error.origin in {"request", "document", "evidence"} else 3
    resolved_output = output_path if output_path.is_absolute() else task_root / output_path
    print(
        json.dumps(
            {
                "script": "compile_artifact_spec",
                "contract_version": 1,
                "output": resolved_output.resolve().relative_to(task_root).as_posix(),
                "output_sha256": sha256_file(resolved_output),
                "input_sha256": compiled["input_sha256"],
                "document_sha256": compiled["task_binding"]["document_sha256"],
                "registry_sha256": compiled["field_registry_ref"]["sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0

"""Compile mutation decisions into the only executable mutation plan."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from docfit.template.decision_contracts import (
    decision_objects,
    load_decision_object,
    resolve_registry,
)
from docfit.template.runtime.atomic import write_json_file
from docfit.template.runtime.paths import task_file
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

_TOP_LEVEL_KEYS = {
    "schema_version",
    "snapshot_ref",
    "document_sha256",
    "field_registry_ref",
    "sources",
    "decisions",
    "operations",
}
_DECISION_KEYS = {
    "decision_id",
    "subject",
    "responsibility",
    "source_refs",
    "evidence_refs",
    "rationale",
}


def _compiler_paths(
    task_root: Path,
    input_path: Path,
    output_path: Path,
) -> tuple[Path, Path]:
    source = task_file(
        str(input_path),
        task_root=task_root,
        field="input",
        allowed_roots=("work",),
    )
    output = output_path if output_path.is_absolute() else task_root / output_path
    output = output.resolve(strict=False)
    if (
        source.parent.name != "decisions"
        or source.suffix.casefold() not in {".yaml", ".yml", ".json"}
        or output.parent.name != "compiled"
        or output.suffix.casefold() != ".json"
        or task_root not in output.parents
        or output.exists()
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="output_exists" if output.exists() else "invalid_compiler_path",
            message="Mutation compiler paths must use new work/decisions and work/compiled files.",
        )
    return source, output


def _validate_execution_locator(
    locator: Any,
    *,
    snapshot_ref: str,
    objects: dict[str, JsonObject],
) -> None:
    if not isinstance(locator, dict) or locator.get("snapshot_ref") != snapshot_ref:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="cross_snapshot_ref",
            message="An operation target does not belong to the bound snapshot.",
        )
    object_id = locator.get("object_id")
    target = objects.get(object_id) if isinstance(object_id, str) else None
    if (
        target is None
        or target.get("expected_fingerprint") != locator.get("expected_fingerprint")
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_fingerprint_mismatch",
            message="An operation target does not match the bound snapshot object.",
        )


def compile_mutation_decisions(
    *,
    task_root: Path,
    input_path: Path,
    output_path: Path,
) -> JsonObject:
    root = task_root.resolve(strict=True)
    source_path, output = _compiler_paths(root, input_path, output_path)
    decisions_file = load_decision_object(source_path)
    if decisions_file.get("schema_version") != 1 or set(decisions_file) != _TOP_LEVEL_KEYS:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_schema_version",
            message="Mutation decisions do not match the v1 top-level contract.",
        )
    store = EvidenceStore(root)
    snapshot_ref = decisions_file.get("snapshot_ref")
    if not isinstance(snapshot_ref, str):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="snapshot_ref_not_found",
            message="A mutation snapshot reference is required.",
        )
    snapshot = store.resolve(snapshot_ref, expected_kind="snapshot")
    if decisions_file.get("document_sha256") != snapshot.get("document_sha256"):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="document_hash_mismatch",
            message="The mutation document hash does not match its snapshot.",
        )
    registry_ref, field_ids = resolve_registry(decisions_file, task_root=root)
    sources = decision_objects(decisions_file.get("sources"), "sources")
    source_ids: set[str] = set()
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or source_id in source_ids:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_ref_not_found",
                message="Mutation source IDs must be unique strings.",
            )
        path = task_file(source.get("path"), task_root=root, field="source.path")
        if source.get("sha256") != sha256_file(path):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="document_hash_mismatch",
                message="A mutation source hash does not match its file.",
            )
        source_ids.add(source_id)
    raw_objects = snapshot.get("objects")
    if not isinstance(raw_objects, list):
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="evidence_invalid",
            message="The snapshot object inventory is invalid.",
        )
    objects: dict[str, JsonObject] = {}
    for item in raw_objects:
        if isinstance(item, dict) and isinstance(item.get("object_id"), str):
            objects[item["object_id"]] = item
    decisions = decision_objects(decisions_file.get("decisions"), "decisions")
    decision_by_id: dict[str, JsonObject] = {}
    for decision in decisions:
        decision_id = decision.get("decision_id")
        responsibility = decision.get("responsibility")
        if (
            set(decision) != _DECISION_KEYS
            or not isinstance(decision_id, str)
            or decision_id in decision_by_id
            or not isinstance(responsibility, dict)
            or not isinstance(decision.get("source_refs"), list)
            or any(item not in source_ids for item in decision["source_refs"])
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unknown_decision_ref",
                message="A mutation decision is incomplete or references an unknown source.",
            )
        decision_by_id[decision_id] = decision
    operations = decision_objects(decisions_file.get("operations"), "operations")
    operation_ids: set[str] = set()
    materialized_slots: set[str] = set()
    for operation in operations:
        operation_id = operation.get("operation_id")
        decision_ref = operation.get("decision_ref")
        action = operation.get("operation")
        if (
            not isinstance(operation_id, str)
            or operation_id in operation_ids
            or decision_ref not in decision_by_id
            or action not in {"materialize_slot", "remove_content"}
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unknown_decision_ref",
                message="A mutation operation ID, action, or decision reference is invalid.",
            )
        _validate_execution_locator(
            operation.get("execution_locator"),
            snapshot_ref=snapshot_ref,
            objects=objects,
        )
        responsibility = decision_by_id[decision_ref]["responsibility"]
        assert isinstance(responsibility, dict)
        if action == "materialize_slot":
            slot_id = operation.get("slot_id")
            field_id = operation.get("field_id")
            marker = operation.get("marker")
            if (
                responsibility.get("kind") != "fill"
                or responsibility.get("handling") != "automatic"
                or not isinstance(slot_id, str)
                or slot_id in materialized_slots
                or field_id not in field_ids
                or marker
                != {
                    "protocol": "docfit-content-control-marker/v1",
                    "alias": field_id,
                    "tag": slot_id,
                }
                or operation.get("preserve_container") is not True
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code=(
                        "field_not_registered"
                        if field_id not in field_ids
                        else "marker_identity_mismatch"
                    ),
                    message="A materialize_slot operation violates field or marker invariants.",
                )
            materialized_slots.add(slot_id)
        else:
            if operation.get("mode") != "clear_text_preserve_container":
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="unsupported_operation",
                    message="Only clear_text_preserve_container is open in this mutation slice.",
                )
            targets = operation.get("migration_targets")
            authority = operation.get("deletion_authority")
            migrated = (
                isinstance(targets, list)
                and bool(targets)
                and all(
                    isinstance(item, dict)
                    and item.get("target_kind") == "materialized_slot"
                    and item.get("slot_id") in materialized_slots
                    for item in targets
                )
            )
            authorized = (
                isinstance(authority, dict)
                and isinstance(authority.get("authority_sha256"), str)
                and isinstance(authority.get("source_ref"), str)
            )
            if not migrated and not authorized:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code=(
                        "migration_target_not_materialized"
                        if isinstance(targets, list) and targets
                        else "deletion_authority_missing"
                    ),
                    message="Removal requires earlier responsibility migration or exact authority.",
                )
        operation_ids.add(operation_id)
    compiled: JsonObject = {
        "schema_version": 1,
        "compiler": {
            "name": "compile_mutation_plan",
            "contract_version": 1,
            "implementation_version": "0.1.0",
        },
        "input_sha256": sha256_file(source_path),
        "task_binding": {
            "task_store_version": 1,
            "snapshot_ref": snapshot_ref,
            "document_sha256": decisions_file["document_sha256"],
        },
        "field_registry_ref": registry_ref,
        "sources": sources,
        "decisions": decisions,
        "operations": operations,
    }
    compiled["plan_digest"] = sha256_json(compiled)
    write_json_file(output, compiled)
    return compiled


def compiler_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compile_mutation_plan.py")
    parser.add_argument("--version", action="version", version="compile_mutation_plan 0.1.0")
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--input", required=True, dest="input_path")
    parser.add_argument("--output", required=True, dest="output_path")
    args = parser.parse_args(argv)
    task_root = Path(args.task_root).expanduser().resolve(strict=True)
    try:
        compiled = compile_mutation_decisions(
            task_root=task_root,
            input_path=Path(args.input_path),
            output_path=Path(args.output_path),
        )
    except ToolFailure as error:
        print(
            json.dumps({"code": error.code, "field": None, "message": error.message}),
            file=sys.stderr,
        )
        return 2 if error.origin in {"request", "document", "evidence"} else 3
    resolved_output = Path(args.output_path)
    resolved_output = (
        resolved_output if resolved_output.is_absolute() else task_root / resolved_output
    )
    print(
        json.dumps(
            {
                "script": "compile_mutation_plan",
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

"""Transactional execution of compiled template mutation plans."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from docfit.template.decision_contracts import resolve_registry
from docfit.template.mutation_package import _write_mutated_package
from docfit.template.observation import snapshot_document
from docfit.template.runtime.paths import task_file
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json


def _load_plan(path: Path) -> JsonObject:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_mutation_plan",
            message="The compiled mutation plan cannot be read.",
        ) from error
    if not isinstance(value, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_mutation_plan",
            message="The compiled mutation plan must be one object.",
        )
    digest = value.pop("plan_digest", None)
    actual = sha256_json(value)
    value["plan_digest"] = digest
    if digest != actual:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="plan_digest_mismatch",
            message="The mutation plan digest does not match its payload.",
        )
    return value

class TemplateMutationService:
    def mutate(self, args: dict[str, Any], *, task_root: Path) -> JsonObject:
        plan_path = task_file(
            args.get("mutation_plan_path"),
            task_root=task_root,
            field="mutation_plan_path",
            allowed_roots=("work",),
            suffix=".json",
        )
        plan = _load_plan(plan_path)
        binding = plan.get("task_binding")
        if not isinstance(binding, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_mutation_plan",
                message="The mutation plan has no valid task binding.",
            )
        store = EvidenceStore(task_root)
        snapshot_ref = binding.get("snapshot_ref")
        snapshot = store.resolve(snapshot_ref, expected_kind="snapshot")
        source_path = snapshot.get("source_path")
        if not isinstance(source_path, str):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="The mutation snapshot has no source path.",
            )
        source = task_file(
            source_path,
            task_root=task_root,
            field="mutation_source",
            suffix=".docx",
        )
        source_hash = sha256_file(source)
        if source_hash != binding.get("document_sha256"):
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="snapshot_hash_mismatch",
                message="The mutation source no longer matches its snapshot.",
            )
        _, registered_fields = resolve_registry(plan, task_root=task_root)
        operations = plan.get("operations")
        if not isinstance(operations, list) or not all(
            isinstance(item, dict) for item in operations
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_mutation_plan",
                message="The mutation plan operation inventory is invalid.",
            )
        for operation in operations:
            if operation.get("operation") == "materialize_slot":
                field_id = operation.get("field_id")
                marker = operation.get("marker")
                if (
                    field_id not in registered_fields
                    or not isinstance(marker, dict)
                    or marker.get("alias") != field_id
                    or marker.get("tag") != operation.get("slot_id")
                ):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="marker_identity_mismatch",
                        message="A compiled slot marker failed independent revalidation.",
                    )
        output_value = args.get("output_docx")
        if not isinstance(output_value, str):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_output_path",
                message="A mutation output DOCX path is required.",
            )
        output = (task_root / output_value).resolve(strict=False)
        attempts = (task_root / "work/attempts").resolve(strict=True)
        if (
            output.parent != attempts
            or output.suffix.casefold() != ".docx"
            or output.exists()
            or output.parent.is_symlink()
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="output_exists" if output.exists() else "invalid_output_path",
                message="Mutation output must be a new DOCX in work/attempts.",
            )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".template-mutation.", suffix=".docx", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        output_committed = False
        after_snapshot_ref: str | None = None
        try:
            operation_results = _write_mutated_package(
                source,
                temporary,
                snapshot=snapshot,
                operations=operations,
            )
            validate_docx_package(temporary)
            output_hash = sha256_file(temporary)
            after_payload = snapshot_document(
                temporary,
                output_hash,
                output.relative_to(task_root).as_posix(),
            )
            if sha256_file(source) != source_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="document",
                    code="source_changed",
                    message="The mutation source changed before commit.",
                )
            os.rename(temporary, output)
            output_committed = True
            after_snapshot_ref = store.publish("snapshot", after_payload)
            mutation_payload: JsonObject = {
                "schema_version": 1,
                "kind": "mutation",
                "implementation_version": "0.1.0",
                "plan_digest": plan.get("plan_digest"),
                "before_snapshot_ref": snapshot_ref,
                "before_document_sha256": source_hash,
                "after_snapshot_ref": after_snapshot_ref,
                "after_document_sha256": output_hash,
                "output_path": output.relative_to(task_root).as_posix(),
                "operation_results": operation_results,
                "operations": operations,
            }
            mutation_ref = store.publish("mutation", mutation_payload)
            return {
                "schema_version": 1,
                "call_status": "ok",
                "result_state": "mutated",
                "committed": True,
                "output_docx": output.relative_to(task_root).as_posix(),
                "output_sha256": output_hash,
                "after_snapshot_ref": after_snapshot_ref,
                "mutation_ref": mutation_ref,
                "operation_results": operation_results,
                "checks": [
                    {"name": "source_unchanged", "result": "ok"},
                    {"name": "compiled_plan_executed", "result": "ok"},
                    {"name": "docx_package_valid", "result": "ok"},
                    {"name": "output_published_atomically", "result": "ok"},
                ],
                "warnings": [
                    {
                        "code": "agent_semantic_review_required",
                        "message": (
                            "The tool does not judge semantic correctness. Review the "
                            "mutation diff and rendered pages before building the artifact."
                        ),
                    }
                ],
                "failure": None,
            }
        except BaseException:
            if after_snapshot_ref is not None:
                store.discard(after_snapshot_ref, expected_kind="snapshot")
            if output_committed:
                output.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)

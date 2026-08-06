"""Independent validation and atomic publication of a template artifact."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from docfit.template.runtime.atomic import write_json_file
from docfit.template.runtime.paths import task_file
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json


def _load_spec(path: Path) -> JsonObject:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The artifact spec cannot be read.",
        ) from error
    if not isinstance(value, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The artifact spec must be one object.",
        )
    digest = value.pop("spec_digest", None)
    actual = sha256_json(value)
    value["spec_digest"] = digest
    if digest != actual:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The artifact spec digest does not match its payload.",
        )
    return value


def _copy_file(source: Path, destination: Path) -> None:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        with source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output)
        output.flush()
        os.fsync(output.fileno())


def _verify_review_digest(review: JsonObject) -> None:
    digest = review.get("review_digest")
    body = {key: value for key, value in review.items() if key != "review_digest"}
    if digest != sha256_json(body):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The embedded review digest is invalid.",
        )


def _verify_registry_and_markers(
    spec: JsonObject,
    snapshot: JsonObject,
    *,
    task_root: Path,
) -> None:
    reference = spec.get("field_registry_ref")
    if not isinstance(reference, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The artifact spec has no valid Registry binding.",
        )
    registry_path = task_file(
        reference.get("path"),
        task_root=task_root,
        field="field_registry_ref.path",
        allowed_roots=("input",),
    )
    try:
        registry: Any = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry cannot be revalidated.",
        ) from error
    if (
        not isinstance(registry, dict)
        or reference.get("sha256") != sha256_file(registry_path)
        or reference.get("registry_id") != registry.get("registry_id")
        or reference.get("registry_version") != registry.get("registry_version")
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry changed after artifact compilation.",
        )
    raw_fields = registry.get("fields")
    if not isinstance(raw_fields, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry inventory is invalid.",
        )
    field_ids = {
        item.get("field_id")
        for item in raw_fields
        if isinstance(item, dict) and isinstance(item.get("field_id"), str)
    }
    controls = snapshot.get("content_controls")
    slots = spec.get("slots")
    fill_contract = spec.get("fill_contract")
    if (
        spec.get("marker_protocol") != "docfit-content-control-marker/v1"
        or not isinstance(controls, list)
        or not isinstance(slots, list)
        or not isinstance(fill_contract, dict)
        or not isinstance(fill_contract.get("slots"), list)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="marker_protocol_mismatch",
            message="The artifact spec marker contract is invalid.",
        )
    contract_slots = {
        item.get("slot_id"): item
        for item in fill_contract["slots"]
        if isinstance(item, dict)
    }
    seen: set[str] = set()
    for raw_slot in slots:
        if not isinstance(raw_slot, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="marker_protocol_mismatch",
                message="A slot record is invalid.",
            )
        slot_id = raw_slot.get("slot_id")
        field_id = raw_slot.get("field_id")
        marker = raw_slot.get("marker")
        locator = raw_slot.get("artifact_locator")
        contract_slot = contract_slots.get(slot_id)
        if (
            not isinstance(slot_id, str)
            or slot_id in seen
            or field_id not in field_ids
            or marker != {"alias": field_id, "tag": slot_id}
            or not isinstance(locator, dict)
            or locator.get("type") != "content_control_tag"
            or locator.get("value") != slot_id
            or not isinstance(contract_slot, dict)
            or contract_slot.get("field_id") != field_id
            or contract_slot.get("locator") != locator
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="marker_protocol_mismatch",
                message="A slot marker or fill-contract mapping is inconsistent.",
            )
        matches = [
            item
            for item in controls
            if isinstance(item, dict)
            and item.get("alias") == field_id
            and item.get("tag") == slot_id
        ]
        if len(matches) != 1:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="slot_locator_not_unique",
                message="A content-control marker does not resolve exactly once.",
            )
        seen.add(slot_id)


def _verify_regions(spec: JsonObject, snapshot: JsonObject) -> None:
    objects = snapshot.get("objects")
    if not isinstance(objects, list):
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="evidence_invalid",
            message="The final snapshot has no object inventory.",
        )
    by_id = {
        item.get("object_id"): item
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }
    protected = spec.get("protected_regions")
    remove = spec.get("remove_regions")
    if not isinstance(protected, list) or not isinstance(remove, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The region inventory is invalid.",
        )
    for item in protected:
        if not isinstance(item, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="protected_fingerprint_mismatch",
                message="A protected region is invalid.",
            )
        execution = item.get("execution_locator")
        locator = item.get("artifact_locator")
        if not isinstance(execution, dict) or not isinstance(locator, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="protected_fingerprint_mismatch",
                message="A protected region lacks valid locators.",
            )
        object_id = execution.get("object_id")
        target = by_id.get(object_id) if isinstance(object_id, str) else None
        anchor = locator.get("left_anchor")
        occurrences = sum(
            1
            for candidate in objects
            if isinstance(candidate, dict)
            and isinstance(candidate.get("text"), str)
            and isinstance(anchor, str)
            and anchor in candidate["text"]
        )
        if (
            not isinstance(target, dict)
            or target.get("expected_fingerprint") != execution.get("expected_fingerprint")
            or item.get("expected_fingerprint") != execution.get("expected_fingerprint")
            or occurrences != locator.get("expected_match_count")
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="protected_fingerprint_mismatch",
                message="A protected region no longer resolves to its expected fingerprint.",
            )
    all_text = "\n".join(
        item.get("text", "") for item in objects if isinstance(item, dict)
    )
    for item in remove:
        if (
            isinstance(item, dict)
            and isinstance(item.get("forbidden_text"), str)
            and item["forbidden_text"] in all_text
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="remove_residue_present",
                message="A forbidden remove-region residue remains in the final template.",
            )


def _verify_mutation_lineage(
    spec: JsonObject,
    *,
    store: EvidenceStore,
    final_snapshot_ref: str,
) -> None:
    lineage = spec.get("mutation_lineage")
    if not isinstance(lineage, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The mutation lineage has an invalid shape.",
        )
    previous_after: str | None = None
    for index, item in enumerate(lineage, start=1):
        if not isinstance(item, dict) or item.get("sequence") != index:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="mutation_lineage_gap",
                message="Mutation lineage sequence numbers are invalid.",
            )
        mutation = store.resolve(item.get("mutation_ref"), expected_kind="mutation")
        comparison = store.resolve(item.get("comparison_ref"), expected_kind="comparison")
        before_ref = item.get("before_snapshot_ref")
        after_ref = item.get("after_snapshot_ref")
        if (
            mutation.get("before_snapshot_ref") != before_ref
            or mutation.get("after_snapshot_ref") != after_ref
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
                message="Mutation lineage failed independent evidence validation.",
            )
        previous_after = after_ref if isinstance(after_ref, str) else None
    if lineage and previous_after != final_snapshot_ref:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="mutation_lineage_gap",
            message="Mutation lineage does not reach the final snapshot.",
        )


class TemplateArtifactBuilder:
    def build(self, args: dict[str, Any], *, task_root: Path) -> JsonObject:
        spec_path = task_file(
            args.get("artifact_spec_path"),
            task_root=task_root,
            field="artifact_spec_path",
            allowed_roots=("work",),
            suffix=".json",
        )
        spec = _load_spec(spec_path)
        binding = spec.get("task_binding")
        if not isinstance(binding, dict) or args.get("final_snapshot_ref") != binding.get(
            "snapshot_ref"
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_snapshot_mismatch",
                message="The requested final snapshot does not match the artifact spec.",
            )
        store = EvidenceStore(task_root)
        final_snapshot_ref = args.get("final_snapshot_ref")
        snapshot = store.resolve(final_snapshot_ref, expected_kind="snapshot")
        if snapshot.get("document_sha256") != binding.get("document_sha256"):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_snapshot_mismatch",
                message="The final snapshot hash does not match the artifact spec.",
            )
        source_path = snapshot.get("source_path")
        if not isinstance(source_path, str):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="The final snapshot has no source path.",
            )
        source = task_file(
            source_path,
            task_root=task_root,
            field="final_document",
            suffix=".docx",
        )
        template_hash = sha256_file(source)
        if template_hash != binding.get("document_sha256"):
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="final_snapshot_mismatch",
                message="The final DOCX changed after artifact compilation.",
            )
        sources = spec.get("sources")
        if not isinstance(sources, list):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_artifact_spec",
                message="The artifact source inventory is invalid.",
            )
        for item in sources:
            if not isinstance(item, dict):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_artifact_spec",
                    message="An artifact source record is invalid.",
                )
            source_file = task_file(
                item.get("path"),
                task_root=task_root,
                field="source.path",
            )
            if sha256_file(source_file) != item.get("sha256"):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="source_hash_mismatch",
                    message="An artifact source changed after compilation.",
                )
        review = spec.get("review_record")
        if not isinstance(review, dict) or review.get("document_sha256") != template_hash:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="incomplete_review_coverage",
                message="The final visual review does not bind this template.",
            )
        _verify_review_digest(review)
        _verify_registry_and_markers(spec, snapshot, task_root=task_root)
        _verify_regions(spec, snapshot)
        if not isinstance(final_snapshot_ref, str):
            raise AssertionError("the evidence store validated the final snapshot ref")
        _verify_mutation_lineage(
            spec,
            store=store,
            final_snapshot_ref=final_snapshot_ref,
        )
        comparison = store.resolve(review.get("comparison_ref"), expected_kind="comparison")
        if (
            comparison.get("document_sha256") != template_hash
            or comparison.get("page_count") != review.get("page_count")
            or comparison.get("machine_blockers") != []
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="incomplete_review_coverage",
                message="The final visual review coverage is incomplete.",
            )
        dispositions = review.get("image_dispositions")
        if not isinstance(dispositions, list) or len(dispositions) != review.get("page_count"):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="incomplete_review_coverage",
                message="Every final page must have a review disposition.",
            )
        fill_contract = spec.get("fill_contract")
        if (
            not isinstance(fill_contract, dict)
            or fill_contract.get("template_sha256") != template_hash
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_artifact_spec",
                message="The fill contract does not bind the final template.",
            )
        output_value = args.get("output_dir")
        if output_value != "output/template-artifact":
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_output_directory",
                message="Template artifacts publish only to output/template-artifact.",
            )
        output = task_root / "output/template-artifact"
        if output.exists():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="output_exists",
                message="The template artifact output already exists and is never overwritten.",
            )
        temporary = Path(tempfile.mkdtemp(prefix=".template-artifact.", dir=output.parent))
        try:
            clean_template = temporary / "clean-template.docx"
            _copy_file(source, clean_template)
            with zipfile.ZipFile(clean_template) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="artifact_incomplete",
                        message="The copied template is not a readable DOCX package.",
                    )
            write_json_file(temporary / "fill-contract.json", fill_contract)
            visual_review: JsonObject = {
                "schema_version": "docfit-template-visual-review/v1",
                "template_sha256": template_hash,
                "comparison_ref": review.get("comparison_ref"),
                "render_ref": review.get("render_ref"),
                "visual_level": review.get("visual_level"),
                "page_count": review.get("page_count"),
                "required_images": review.get("required_images"),
                "image_dispositions": dispositions,
                "finding_dispositions": review.get("finding_dispositions", []),
                "machine_blockers": [],
                "review_digest": review.get("review_digest"),
            }
            write_json_file(temporary / "visual-review.json", visual_review)
            file_hashes = {
                "clean-template.docx": sha256_file(clean_template),
                "fill-contract.json": sha256_file(temporary / "fill-contract.json"),
                "visual-review.json": sha256_file(temporary / "visual-review.json"),
            }
            report: JsonObject = {
                "schema_version": "docfit-template-build-report/v1",
                "artifact_status": "built",
                "template_sha256": template_hash,
                "spec_digest": spec.get("spec_digest"),
                "review_digest": review.get("review_digest"),
                "source_hashes": {item["source_id"]: item["sha256"] for item in sources},
                "file_hashes": file_hashes,
                "checks": [
                    {"name": "source_hashes", "result": "ok"},
                    {"name": "registry_and_markers", "result": "ok"},
                    {"name": "artifact_locators", "result": "ok"},
                    {"name": "final_review_coverage", "result": "ok"},
                    {"name": "four_file_publication", "result": "ok"},
                ],
                "warnings": [],
                "manual": spec.get("manual", []),
                "gaps": spec.get("gaps", []),
                "unresolved": spec.get("unresolved", []),
                "unregistered_fields": [],
                "counts": {
                    "slot": len(spec.get("slots", [])),
                    "protected": len(spec.get("protected_regions", [])),
                    "remove": len(spec.get("remove_regions", [])),
                    "manual": len(spec.get("manual", [])),
                    "gap": len(spec.get("gaps", [])),
                    "unresolved": len(spec.get("unresolved", [])),
                },
            }
            write_json_file(temporary / "build-report.json", report)
            if sha256_file(source) != template_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="document",
                    code="source_hash_mismatch",
                    message="The final template changed before publication.",
                )
            os.rename(temporary, output)
            return {
                "schema_version": 1,
                "call_status": "ok",
                "result_state": "built",
                "artifact_status": "built",
                "published": True,
                "output_path": "output/template-artifact",
                "template_sha256": template_hash,
                "fill_contract_sha256": file_hashes["fill-contract.json"],
                "counts": report["counts"],
                "checks": report["checks"],
                "warnings": [],
                "failure": None,
            }
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

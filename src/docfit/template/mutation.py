"""Transactional execution of compiled template mutation plans."""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

from docfit.template.compile_artifact import _registry
from docfit.template.observation import snapshot_document
from docfit.template.runtime.paths import task_file
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_W = f"{{{W_NS}}}"
_KNOWN_NAMESPACES = {
    "w": W_NS,
    "mc": MC_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
}
for _prefix, _uri in _KNOWN_NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)


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


def _serialize(root: ET.Element) -> bytes:
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ignorable = root.get(f"{{{MC_NS}}}Ignorable", "").split()
    missing = [
        (prefix, _KNOWN_NAMESPACES[prefix])
        for prefix in ignorable
        if prefix in _KNOWN_NAMESPACES and f"xmlns:{prefix}=".encode() not in payload
    ]
    if missing:
        declaration_end = payload.find(b"?>")
        root_start = payload.find(b"<", declaration_end + 2)
        root_end = payload.find(b">", root_start)
        declarations = b"".join(
            f' xmlns:{prefix}="{uri}"'.encode() for prefix, uri in missing
        )
        payload = payload[:root_end] + declarations + payload[root_end:]
    return cast(bytes, payload)


def _target(
    roots: dict[str, ET.Element],
    objects: dict[str, JsonObject],
    locator: Any,
) -> tuple[ET.Element, JsonObject]:
    if not isinstance(locator, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target locator is invalid.",
        )
    object_id = locator.get("object_id")
    item = objects.get(object_id) if isinstance(object_id, str) else None
    if item is None or item.get("expected_fingerprint") != locator.get(
        "expected_fingerprint"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_fingerprint_mismatch",
            message="A mutation target no longer matches its snapshot fingerprint.",
        )
    part = item.get("part")
    paragraph_index = item.get("paragraph_index")
    root = roots.get(part) if isinstance(part, str) else None
    if root is None or not isinstance(paragraph_index, int):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target cannot be located in the DOCX package.",
        )
    paragraphs = list(root.iter(f"{_W}p"))
    if not 0 <= paragraph_index < len(paragraphs):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target paragraph no longer exists.",
        )
    return paragraphs[paragraph_index], item


def _materialize(paragraph: ET.Element, operation: JsonObject) -> None:
    if paragraph.find(f".//{_W}sdt") is not None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="slot_id_not_unique",
            message="The materialize target already contains a content control.",
        )
    slot_id = operation["slot_id"]
    field_id = operation["field_id"]
    sdt = ET.Element(f"{_W}sdt")
    properties = ET.SubElement(sdt, f"{_W}sdtPr")
    ET.SubElement(properties, f"{_W}alias", {f"{_W}val": field_id})
    ET.SubElement(properties, f"{_W}tag", {f"{_W}val": slot_id})
    internal_id = int(sha256_json({"slot_id": slot_id})[:7], 16)
    ET.SubElement(properties, f"{_W}id", {f"{_W}val": str(internal_id)})
    ET.SubElement(properties, f"{_W}text")
    content = ET.SubElement(sdt, f"{_W}sdtContent")
    for child in list(paragraph):
        if child.tag == f"{_W}pPr":
            continue
        paragraph.remove(child)
        content.append(child)
    paragraph.append(sdt)


def _remove_content(paragraph: ET.Element, operation: JsonObject) -> None:
    targets = operation.get("migration_targets")
    slot_id = None
    if isinstance(targets, list) and targets and isinstance(targets[0], dict):
        slot_id = targets[0].get("slot_id")
    candidates: list[ET.Element] = []
    for control in paragraph.iter(f"{_W}sdt"):
        tag = control.find(f"{_W}sdtPr/{_W}tag")
        if slot_id is None or (tag is not None and tag.get(f"{_W}val") == slot_id):
            candidates.append(control)
    if len(candidates) > 1:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_ambiguous",
            message="The remove target resolves to multiple content controls.",
        )
    target = candidates[0] if candidates else paragraph
    text_nodes = list(target.iter(f"{_W}t"))
    if not text_nodes:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="The remove target contains no visible text.",
        )
    for text in text_nodes:
        text.text = None


def _write_mutated_package(
    source: Path,
    temporary: Path,
    *,
    snapshot: JsonObject,
    operations: list[JsonObject],
) -> list[JsonObject]:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    object_list = snapshot.get("objects")
    if not isinstance(object_list, list):
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="evidence_invalid",
            message="The mutation snapshot has no valid object inventory.",
        )
    objects: dict[str, JsonObject] = {}
    for item in object_list:
        if isinstance(item, dict) and isinstance(item.get("object_id"), str):
            objects[item["object_id"]] = item
    needed_parts: set[str] = set()
    for operation in operations:
        locator = operation.get("execution_locator")
        object_id = locator.get("object_id") if isinstance(locator, dict) else None
        item = objects.get(object_id) if isinstance(object_id, str) else None
        part = item.get("part") if isinstance(item, dict) else None
        if isinstance(part, str):
            needed_parts.add(part)
    try:
        roots: dict[str, ET.Element] = {
            part: ET.fromstring(parts[part]) for part in needed_parts
        }
    except (KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="document",
            code="target_not_found",
            message="A mutation target OOXML part cannot be parsed.",
        ) from error
    results: list[JsonObject] = []
    for index, operation in enumerate(operations):
        paragraph, _ = _target(roots, objects, operation.get("execution_locator"))
        action = operation.get("operation")
        if action == "materialize_slot":
            _materialize(paragraph, operation)
        elif action == "remove_content":
            _remove_content(paragraph, operation)
        else:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unsupported_operation",
                message="The mutation plan contains an unsupported operation.",
            )
        results.append(
            {
                "index": index,
                "operation_id": operation.get("operation_id"),
                "operation": action,
                "result": "applied",
            }
        )
    for part, root in roots.items():
        parts[part] = _serialize(root)
    with zipfile.ZipFile(temporary, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    return results


def _verify_after(
    before: JsonObject,
    after: JsonObject,
    operations: list[JsonObject],
) -> None:
    controls = after.get("content_controls")
    if not isinstance(controls, list):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="post_check_failed",
            message="The mutated template has no valid content-control inventory.",
        )
    target_ids = {
        operation.get("execution_locator", {}).get("object_id") for operation in operations
    }
    before_objects = before.get("objects")
    after_objects = after.get("objects")
    if not isinstance(before_objects, list) or not isinstance(after_objects, list):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="post_check_failed",
            message="The mutation object inventory cannot be revalidated.",
        )
    after_by_position = {
        (item.get("part"), item.get("paragraph_index")): item
        for item in after_objects
        if isinstance(item, dict)
    }
    for item in before_objects:
        if not isinstance(item, dict) or item.get("object_id") in target_ids:
            continue
        current = after_by_position.get((item.get("part"), item.get("paragraph_index")))
        if not isinstance(current, dict) or current.get("text") != item.get("text"):
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="protected_content_changed",
                message="A non-target paragraph changed during mutation.",
            )
    for operation in operations:
        if operation.get("operation") == "materialize_slot":
            matched = [
                item
                for item in controls
                if isinstance(item, dict)
                and item.get("alias") == operation.get("field_id")
                and item.get("tag") == operation.get("slot_id")
            ]
            if len(matched) != 1:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="post_check_failed",
                    message="A materialized slot failed its marker postcondition.",
                )
        if operation.get("operation") == "remove_content":
            expected = operation.get("expected_after")
            forbidden = (
                expected.get("forbidden_text_absent")
                if isinstance(expected, dict)
                else None
            )
            all_text = "\n".join(
                item.get("text", "") for item in after_objects if isinstance(item, dict)
            )
            if isinstance(forbidden, str) and forbidden in all_text:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="post_check_failed",
                    message="Removed content remains visible after mutation.",
                )
    if before.get("styles") != after.get("styles") or before.get("sections") != after.get(
        "sections"
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="protected_content_changed",
            message="Styles or sections changed outside the mutation plan.",
        )


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
        _, registered_fields = _registry(plan, task_root=task_root)
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
            _verify_after(snapshot, after_payload, operations)
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
                    {"name": "planned_operations_only", "result": "ok"},
                    {"name": "protected_content_preserved", "result": "ok"},
                    {"name": "marker_postconditions", "result": "ok"},
                ],
                "warnings": [],
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

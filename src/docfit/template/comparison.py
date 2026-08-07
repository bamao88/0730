"""Deterministic structural comparison and required visual evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docfit.template.runtime.store import EvidenceStore
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json
from docfit.visual.evidence import EvidenceStore as VisualEvidenceStore


class TemplateComparisonService:
    def review(self, args: dict[str, Any], *, task_root: Path) -> JsonObject:
        if args.get("review_mode") == "mutation_review":
            return self.mutation_review(args, task_root=task_root)
        return self.final_review(args, task_root=task_root)

    def mutation_review(self, args: dict[str, Any], *, task_root: Path) -> JsonObject:
        store = EvidenceStore(task_root)
        before_ref = args.get("before_snapshot_ref")
        after_ref = args.get("after_snapshot_ref")
        mutation_ref = args.get("mutation_ref")
        before = store.resolve(before_ref, expected_kind="snapshot")
        after = store.resolve(after_ref, expected_kind="snapshot")
        mutation = store.resolve(mutation_ref, expected_kind="mutation")
        if (
            mutation.get("before_snapshot_ref") != before_ref
            or mutation.get("after_snapshot_ref") != after_ref
            or mutation.get("before_document_sha256") != before.get("document_sha256")
            or mutation.get("after_document_sha256") != after.get("document_sha256")
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="mutation_lineage_mismatch",
                message="Mutation evidence does not connect the requested snapshots.",
            )
        before_objects = before.get("objects")
        after_objects = after.get("objects")
        operations = mutation.get("operations")
        if (
            not isinstance(before_objects, list)
            or not isinstance(after_objects, list)
            or not isinstance(operations, list)
        ):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="Mutation comparison evidence is incomplete.",
            )
        before_by_id = {
            item.get("object_id"): item
            for item in before_objects
            if isinstance(item, dict)
        }
        target_positions = {
            (item.get("part"), item.get("paragraph_index"))
            for operation in operations
            if isinstance(operation, dict)
            for locator in [operation.get("execution_locator")]
            if isinstance(locator, dict)
            for item in [before_by_id.get(locator.get("object_id"))]
            if isinstance(item, dict)
        }
        before_by_position = {
            (item.get("part"), item.get("paragraph_index")): item
            for item in before_objects
            if isinstance(item, dict) and item.get("kind") == "paragraph"
        }
        after_by_position = {
            (item.get("part"), item.get("paragraph_index")): item
            for item in after_objects
            if isinstance(item, dict) and item.get("kind") == "paragraph"
        }
        expected_changes: list[JsonObject] = []
        unexpected_changes: list[JsonObject] = []
        for position in sorted(
            set(before_by_position) | set(after_by_position),
            key=lambda item: (str(item[0]), int(item[1] or 0)),
        ):
            previous = before_by_position.get(position)
            current = after_by_position.get(position)
            if previous == current:
                continue
            change = {
                "kind": "target_text_changed" if position in target_positions else "object_changed",
                "part": position[0],
                "paragraph_index": position[1],
                "before_text_sha256": (
                    sha256_json(previous.get("text")) if isinstance(previous, dict) else None
                ),
                "after_text_sha256": (
                    sha256_json(current.get("text")) if isinstance(current, dict) else None
                ),
            }
            (expected_changes if position in target_positions else unexpected_changes).append(
                change
            )
        before_controls = {
            (item.get("alias"), item.get("tag"))
            for item in before.get("content_controls", [])
            if isinstance(item, dict)
        }
        after_controls = {
            (item.get("alias"), item.get("tag"))
            for item in after.get("content_controls", [])
            if isinstance(item, dict)
        }
        expected_markers = {
            (operation.get("field_id"), operation.get("slot_id"))
            for operation in operations
            if isinstance(operation, dict) and operation.get("operation") == "materialize_slot"
        }
        for marker in sorted(after_controls - before_controls, key=lambda item: str(item)):
            change = {"kind": "content_control_added", "alias": marker[0], "tag": marker[1]}
            (expected_changes if marker in expected_markers else unexpected_changes).append(change)
        for marker in sorted(before_controls - after_controls, key=lambda item: str(item)):
            unexpected_changes.append(
                {"kind": "content_control_removed", "alias": marker[0], "tag": marker[1]}
            )
        if before.get("styles") != after.get("styles"):
            unexpected_changes.append({"kind": "styles_changed"})
        if before.get("sections") != after.get("sections"):
            unexpected_changes.append({"kind": "sections_changed"})
        blockers = [
            {"code": "unexpected_mutation_change", "change": item}
            for item in unexpected_changes
        ]
        payload: JsonObject = {
            "schema_version": 1,
            "kind": "comparison",
            "implementation_version": "0.1.0",
            "review_mode": "mutation_review",
            "before_snapshot_ref": before_ref,
            "after_snapshot_ref": after_ref,
            "mutation_ref": mutation_ref,
            "document_sha256": after.get("document_sha256"),
            "expected_changes": expected_changes,
            "unexpected_changes": unexpected_changes,
            "required_images": [],
            "machine_blockers": blockers,
        }
        comparison_ref = store.publish("comparison", payload)
        return {
            "schema_version": 1,
            "call_status": "ok",
            "result_state": "compared",
            "comparison_ref": comparison_ref,
            "expected_changes": expected_changes,
            "unexpected_changes": unexpected_changes,
            "required_images": [],
            "machine_blockers": blockers,
            "next_cursor": None,
            "checks": [
                {"name": "mutation_lineage", "result": "ok"},
                {
                    "name": "unexpected_change_scan",
                    "result": "ok" if not unexpected_changes else "blocked",
                },
            ],
            "warnings": [],
            "failure": None,
        }

    def final_review(self, args: dict[str, Any], *, task_root: Path) -> JsonObject:
        if args.get("review_mode") != "final_review":
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unsupported_review_mode",
                message="review_mode must be mutation_review or final_review.",
            )
        snapshot_ref = args.get("final_snapshot_ref")
        if not isinstance(snapshot_ref, str):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="snapshot_ref_not_found",
                message="final_snapshot_ref is required.",
            )
        store = EvidenceStore(task_root)
        snapshot = store.resolve(snapshot_ref, expected_kind="snapshot")
        visual_store = VisualEvidenceStore(task_root)
        render_ref = args.get("render_ref")
        _, render = visual_store.resolve_render(render_ref)
        if render.get("document_sha256") != snapshot.get("document_sha256"):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_render_snapshot_mismatch",
                message="The LibreOffice render does not bind the final template snapshot.",
            )
        page_count = render.get("page_count")
        reviewed_pages = args.get("reviewed_pages")
        evidence_refs = args.get("evidence_refs")
        if (
            not isinstance(page_count, int)
            or reviewed_pages != list(range(1, page_count + 1))
            or not isinstance(evidence_refs, list)
            or not all(isinstance(item, str) for item in evidence_refs)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="incomplete_review_coverage",
                message="Final review must cite full-page evidence for every rendered page.",
            )
        by_page: dict[int, JsonObject] = {}
        for evidence_ref in evidence_refs:
            view = visual_store.resolve_view(evidence_ref)
            identity = view.metadata.get("identity")
            page = view.metadata.get("page")
            if (
                view.metadata.get("render_ref") != render_ref
                or not isinstance(identity, dict)
                or identity.get("view") != "page"
                or not isinstance(page, int)
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_final_page_evidence",
                    message="Final review evidence must be full pages from the final render.",
                )
            by_page[page] = {
                "required_image_id": f"image-final-page-{page:04d}",
                "kind": "final_full_page",
                "pages": [page],
                "evidence_ref": evidence_ref,
                "image_sha256": view.metadata.get("image_sha256"),
            }
        if sorted(by_page) != reviewed_pages:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="incomplete_review_coverage",
                message="Every final page requires one current full-page evidence reference.",
            )
        findings = args.get("findings", [])
        if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_visual_findings",
                message="findings must be an array of visual finding objects.",
            )
        blockers = [
            item
            for item in findings
            if item.get("blocking") is True or item.get("severity") == "blocking"
        ]
        required_images = [by_page[page] for page in reviewed_pages]
        payload: JsonObject = {
            "schema_version": 2,
            "kind": "comparison",
            "implementation_version": "0.2.0",
            "review_mode": "final_review",
            "final_snapshot_ref": snapshot_ref,
            "document_sha256": snapshot.get("document_sha256"),
            "render_ref": render_ref,
            "fidelity": render.get("fidelity"),
            "renderer": render.get("renderer"),
            "page_count": page_count,
            "expected_changes": [],
            "unexpected_changes": [],
            "required_images": required_images,
            "findings": findings,
            "machine_blockers": blockers,
        }
        comparison_ref = store.publish("comparison", payload)
        return {
            "schema_version": 2,
            "call_status": "ok",
            "result_state": "compared",
            "comparison_ref": comparison_ref,
            "document_sha256": snapshot.get("document_sha256"),
            "render_ref": render_ref,
            "fidelity": render.get("fidelity"),
            "renderer": render.get("renderer"),
            "expected_changes": [],
            "unexpected_changes": [],
            "required_images": required_images,
            "machine_blockers": blockers,
            "next_cursor": None,
            "checks": [
                {"name": "final_snapshot_integrity", "result": "ok"},
                {"name": "libreoffice_render_binding", "result": "ok"},
                {
                    "name": "all_final_pages_reviewed",
                    "result": "ok" if not blockers else "blocked",
                },
            ],
            "warnings": [],
            "failure": None,
        }

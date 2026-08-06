"""Deterministic structural comparison and required visual evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docfit.template.ports import TemplateRenderer
from docfit.template.rendering import TemplateRenderService
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json


class TemplateComparisonService:
    def __init__(self, renderer: TemplateRenderer | None = None) -> None:
        self.rendering = TemplateRenderService(renderer)

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
                message="This implementation slice currently supports final_review.",
            )
        if args.get("visual_level") != "candidate_verification":
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="candidate_verification_unavailable",
                message="Final review requires candidate_verification visual evidence.",
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
        render_result = self.rendering.create(
            task_root=task_root,
            snapshot_ref=snapshot_ref,
            visual_level="candidate_verification",
        )
        render_ref = render_result["render_ref"]
        if not isinstance(render_ref, str):
            raise AssertionError("render service returned an invalid reference")
        render = store.resolve(render_ref, expected_kind="render")
        pages = render.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="candidate_verification_unavailable",
                message="Final candidate page evidence is incomplete.",
            )
        required_images: list[JsonObject] = []
        for item in pages:
            if not isinstance(item, dict) or not isinstance(item.get("page"), int):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="candidate_verification_unavailable",
                    message="Final candidate page evidence is invalid.",
                )
            page = item["page"]
            required_images.append(
                {
                    "required_image_id": f"image-final-page-{page:04d}",
                    "kind": "final_full_page",
                    "pages": [page],
                    "image_sha256": item.get("sha256"),
                    "render_page_path": item.get("path"),
                }
            )
        payload: JsonObject = {
            "schema_version": 1,
            "kind": "comparison",
            "implementation_version": "0.1.0",
            "review_mode": "final_review",
            "final_snapshot_ref": snapshot_ref,
            "document_sha256": snapshot.get("document_sha256"),
            "visual_level": "candidate_verification",
            "render_ref": render_ref,
            "page_count": len(required_images),
            "expected_changes": [],
            "unexpected_changes": [],
            "required_images": required_images,
            "machine_blockers": [],
        }
        comparison_ref = store.publish("comparison", payload)
        return {
            "schema_version": 1,
            "call_status": "ok",
            "result_state": "compared",
            "comparison_ref": comparison_ref,
            "document_sha256": snapshot.get("document_sha256"),
            "render_ref": render_ref,
            "expected_changes": [],
            "unexpected_changes": [],
            "required_images": [
                {key: value for key, value in item.items() if key != "render_page_path"}
                for item in required_images
            ],
            "machine_blockers": [],
            "next_cursor": None,
            "checks": [
                {"name": "final_snapshot_integrity", "result": "ok"},
                {"name": "all_final_pages_required", "result": "ok"},
            ],
            "warnings": [],
            "failure": None,
        }

    def images(
        self,
        args: dict[str, Any],
        *,
        task_root: Path,
    ) -> tuple[JsonObject, list[Path]]:
        store = EvidenceStore(task_root)
        comparison_ref = args.get("comparison_ref")
        comparison = store.resolve(comparison_ref, expected_kind="comparison")
        requested = args.get("required_image_ids")
        max_images = args.get("max_images", 4)
        if (
            not isinstance(requested, list)
            or not requested
            or not all(isinstance(item, str) for item in requested)
            or not isinstance(max_images, int)
            or not 1 <= max_images <= 4
            or len(requested) > max_images
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="image_budget_exceeded",
                message="Required comparison images exceed the per-call budget.",
            )
        required = comparison.get("required_images")
        render_ref = comparison.get("render_ref")
        if not isinstance(required, list) or not isinstance(render_ref, str):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="The comparison image inventory is invalid.",
            )
        by_id = {
            item.get("required_image_id"): item
            for item in required
            if isinstance(item, dict) and isinstance(item.get("required_image_id"), str)
        }
        if any(image_id not in by_id for image_id in requested):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="requested_image_not_required",
                message="A requested image is not required by this comparison.",
            )
        render_bundle = store.bundle_path(render_ref, expected_kind="render")
        selected: list[JsonObject] = []
        paths: list[Path] = []
        for image_id in requested:
            item = by_id[image_id]
            path_value = item.get("render_page_path")
            if not isinstance(path_value, str):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="evidence_invalid",
                    message="A required image path is invalid.",
                )
            path = (render_bundle / path_value).resolve(strict=True)
            if render_bundle not in path.parents or sha256_file(path) != item.get("image_sha256"):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="evidence_hash_mismatch",
                    message="A required image failed its integrity check.",
                )
            selected.append(
                {key: value for key, value in item.items() if key != "render_page_path"}
            )
            paths.append(path)
        return (
            {
                "schema_version": 1,
                "call_status": "ok",
                "result_state": "compared",
                "comparison_ref": comparison_ref,
                "images": selected,
                "next_cursor": None,
                "checks": [{"name": "required_images_verified", "result": "ok"}],
                "warnings": [],
                "failure": None,
            },
            paths,
        )

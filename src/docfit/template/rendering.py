"""Hash-bound rendering and image retrieval for template evidence."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from docfit.template.ports import DefaultTemplateRenderer, TemplateRenderer
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.images import image_metadata, verify_png
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json


def _cursor(reference: str, index: int) -> str:
    digest = sha256_json({"render_ref": reference, "index": index})[:16]
    return f"image-cursor:v1:{digest}:{index}"


def _cursor_index(value: Any, reference: str) -> int:
    if value is None:
        return 0
    if not isinstance(value, str):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_image_cursor",
            message="The image cursor is invalid for this render.",
        )
    parts = value.split(":")
    if (
        len(parts) != 4
        or not parts[3].isdigit()
        or parts[:3]
        != [
            "image-cursor",
            "v1",
            sha256_json({"render_ref": reference, "index": int(parts[3])})[:16],
        ]
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_image_cursor",
            message="The image cursor is invalid for this render.",
        )
    return int(parts[3])


class TemplateRenderService:
    def __init__(self, renderer: TemplateRenderer | None = None) -> None:
        self.renderer = renderer or DefaultTemplateRenderer()

    def create(
        self,
        *,
        task_root: Path,
        snapshot_ref: str,
        visual_level: str,
    ) -> JsonObject:
        store = EvidenceStore(task_root)
        snapshot = store.resolve(snapshot_ref, expected_kind="snapshot")
        source_path = snapshot.get("source_path")
        document_hash = snapshot.get("document_sha256")
        if not isinstance(source_path, str) or not isinstance(document_hash, str):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="The snapshot lacks a valid document binding.",
            )
        document = (task_root / source_path).resolve(strict=True)
        if task_root not in document.parents or sha256_file(document) != document_hash:
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="snapshot_hash_mismatch",
                message="The snapshot no longer matches its source document.",
            )
        store.root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".render.", dir=store.root))
        try:
            rendered = self.renderer.render(
                document,
                visual_level=visual_level,
                output=temporary,
            )
            if not rendered.pages:
                raise ToolFailure(
                    status="error",
                    origin="renderer",
                    code="candidate_verification_unavailable",
                    message="The renderer returned no complete page evidence.",
                )
            page_records: list[JsonObject] = []
            files: dict[str, Path] = {}
            for number, page in enumerate(rendered.pages, start=1):
                verify_png(page)
                relative = f"pages/page-{number:04d}.png"
                metadata = image_metadata(page)
                page_records.append(
                    {
                        "page": number,
                        "path": relative,
                        "sha256": metadata["sha256"],
                        "width": metadata["width"],
                        "height": metadata["height"],
                        "mime_type": "image/png",
                    }
                )
                files[relative] = page
            if rendered.pdf is not None:
                files["document.pdf"] = rendered.pdf
            if sha256_file(document) != document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="document",
                    code="source_changed",
                    message="The source changed while visual evidence was being created.",
                )
            payload: JsonObject = {
                "schema_version": 1,
                "kind": "render",
                "implementation_version": "0.1.0",
                "snapshot_ref": snapshot_ref,
                "document_sha256": document_hash,
                "visual_level": visual_level,
                "page_count": len(page_records),
                "pages": page_records,
                "provider": rendered.provider,
            }
            render_ref = store.publish_bundle("render", payload, files)
            return {
                "render_ref": render_ref,
                "page_count": len(page_records),
                "provider": rendered.provider,
            }
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def images(
        self,
        args: dict[str, Any],
        *,
        task_root: Path,
    ) -> tuple[JsonObject, list[Path]]:
        store = EvidenceStore(task_root)
        render_ref = args.get("render_ref")
        render = store.resolve(render_ref, expected_kind="render")
        if not isinstance(render_ref, str):
            raise AssertionError("render ref was validated by the evidence store")
        pages = render.get("pages")
        if not isinstance(pages, list):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="The render page inventory is invalid.",
            )
        requested = args.get("pages")
        cursor_value = args.get("cursor")
        if requested is not None and cursor_value is not None:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_image_cursor",
                message="pages and cursor are mutually exclusive.",
            )
        max_images = args.get("max_images", 4)
        if not isinstance(max_images, int) or not 1 <= max_images <= 4:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="image_budget_exceeded",
                message="At most four render images may be returned per call.",
            )
        if requested is not None:
            if (
                not isinstance(requested, list)
                or not requested
                or len(requested) > max_images
                or any(not isinstance(value, int) for value in requested)
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="image_budget_exceeded",
                    message="The requested page set is invalid or exceeds the image budget.",
                )
            indices = [value - 1 for value in requested]
            next_cursor = None
        else:
            start = _cursor_index(cursor_value, render_ref)
            indices = list(range(start, min(start + max_images, len(pages))))
            next_cursor = (
                _cursor(render_ref, indices[-1] + 1)
                if indices and indices[-1] + 1 < len(pages)
                else None
            )
        if any(index < 0 or index >= len(pages) for index in indices):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="image_page_out_of_range",
                message="A requested page is outside this render.",
            )
        bundle = store.bundle_path(render_ref, expected_kind="render")
        selected: list[JsonObject] = []
        paths: list[Path] = []
        for index in indices:
            item = pages[index]
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="evidence_invalid",
                    message="A render page record is invalid.",
                )
            path = (bundle / item["path"]).resolve(strict=True)
            if bundle not in path.parents or sha256_file(path) != item.get("sha256"):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="evidence_hash_mismatch",
                    message="A render image failed its integrity check.",
                )
            selected.append(item)
            paths.append(path)
        return (
            {
                "schema_version": 1,
                "call_status": "ok",
                "result_state": "observed",
                "render_ref": render_ref,
                "document_sha256": render.get("document_sha256"),
                "images": selected,
                "next_cursor": next_cursor,
                "checks": [{"name": "render_integrity", "result": "ok"}],
                "warnings": [],
                "failure": None,
            },
            paths,
        )

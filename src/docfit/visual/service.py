"""LibreOffice render and on-demand visual review orchestration."""

from __future__ import annotations

import json
import math
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from docfit.tools.inspection import inspect_document
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    authorized_path,
    require_docx,
    sha256_file,
    sha256_json,
)
from docfit.visual.evidence import EvidenceStore, StoredView, render_reference
from docfit.visual.locator import build_anchor_index, locate_object, locate_text, normalize_text
from docfit.visual.pdf import PdfBackend
from docfit.visual.renderer import LibreOfficeRenderer
from docfit.visual.views import comparison, contact_sheet

_QUALITY_DPI = {"thumbnail": 72, "review": 144, "detail": 220}
_MODES = {"contact_sheet", "pages", "regions", "compare"}
_MAX_RETURNED_IMAGES = 4
_CONTACT_PAGE_LIMIT = 12


class VisualEvidenceService:
    """One render path, one evidence store, and no provider routing."""

    def __init__(
        self,
        task_root: Path,
        *,
        renderer: LibreOfficeRenderer | None = None,
        pdf: PdfBackend | None = None,
        office: OfficeCliAdapter | None = None,
    ) -> None:
        self.task_root = task_root.resolve(strict=True)
        self.store = EvidenceStore(self.task_root)
        self.renderer = renderer or LibreOfficeRenderer()
        self.pdf = pdf or PdfBackend()
        self._office = office

    @property
    def office(self) -> OfficeCliAdapter:
        if self._office is None:
            self._office = OfficeCliAdapter()
        return self._office

    def render(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        self._reject_args(args, {"input_docx", "overview"}, operation="docx_render")
        document = authorized_path(
            args.get("input_docx"), task_root=self.task_root, field="input_docx"
        )
        require_docx(document, field="input_docx")
        overview = args.get("overview", True)
        if not isinstance(overview, bool):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_overview",
                message="overview must be true or false.",
            )
        document_hash = sha256_file(document)
        renderer = self.renderer.environment()
        identity: JsonObject = {
            "document_sha256": document_hash,
            "renderer": {
                "name": renderer.name,
                "version": renderer.version,
                "container_image_digest": renderer.container_image_digest,
                "font_environment_digest": renderer.font_environment_digest,
                "locale": renderer.locale,
                "pdf_export_options": renderer.pdf_export_options,
            },
        }
        reference = render_reference(identity)
        cache_hit = True
        try:
            _, manifest = self.store.resolve_render(reference)
        except ToolFailure as error:
            if error.code != "render_ref_not_found":
                raise
            cache_hit = False
            manifest = self._create_render(
                document=document,
                document_hash=document_hash,
                identity=identity,
                reference=reference,
                renderer=renderer.public(),
            )
        result: JsonObject = {
            "schema_version": 2,
            "status": "ok",
            "checks": [
                {"name": "libreoffice_pdf", "result": "ok"},
                {"name": "render_integrity", "result": "ok"},
            ],
            "warnings": [
                {
                    "code": "approximate_render",
                    "kind": "fidelity",
                    "message": "LibreOffice visual evidence is approximate, not Word pixel parity.",
                }
            ],
            "failure": None,
            "cache_hit": cache_hit,
            "render_ref": reference,
            "document_sha256": document_hash,
            "page_count": manifest["page_count"],
            "fidelity": "approximate",
            "renderer": manifest["renderer"],
            "overview": None,
        }
        images: list[Path] = []
        if overview:
            review, images = self.review(
                {"render_ref": reference, "mode": "contact_sheet", "quality": "thumbnail"}
            )
            evidence = review["evidence"][0]
            covered_pages = evidence["pages"]
            result["overview"] = {
                "evidence_ref": evidence["evidence_ref"],
                "covered_pages": covered_pages,
                "has_more": int(manifest["page_count"]) > len(covered_pages),
            }
        return result, images

    def review(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        allowed = {
            "render_ref",
            "mode",
            "quality",
            "pages",
            "regions",
            "compare_render_ref",
            "cursor",
        }
        self._reject_args(args, allowed, operation="docx_visual_review")
        reference = args.get("render_ref")
        render_path, manifest = self.store.resolve_render(reference)
        assert isinstance(reference, str)
        mode = args.get("mode")
        if mode not in _MODES:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_visual_mode",
                message="mode must be contact_sheet, pages, regions, or compare.",
            )
        quality = args.get("quality", "review")
        if quality not in _QUALITY_DPI:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_visual_quality",
                message="quality must be thumbnail, review, or detail.",
            )
        index = self._read_index(render_path / "indexes" / "pdf-text.json")
        pdf = render_path / "document.pdf"
        warnings: list[JsonObject] = []
        next_cursor: str | None = None
        if mode == "contact_sheet":
            evidence, images, next_cursor = self._contact_sheet(
                args, reference, manifest, pdf, index
            )
        elif mode == "pages":
            evidence, images, next_cursor = self._pages(
                args, reference, manifest, pdf, index, str(quality)
            )
        elif mode == "regions":
            evidence, images, next_cursor, warnings = self._regions(
                args, reference, manifest, render_path, pdf, index, str(quality)
            )
        else:
            evidence, images, next_cursor = self._compare(
                args, reference, manifest, pdf, index, str(quality)
            )
        return (
            {
                "schema_version": 2,
                "status": "ok",
                "checks": [{"name": "evidence_integrity", "result": "ok"}],
                "warnings": warnings,
                "failure": None,
                "render_ref": reference,
                "document_sha256": manifest["document_sha256"],
                "fidelity": "approximate",
                "renderer": manifest["renderer"],
                "mode": mode,
                "quality": quality,
                "evidence": evidence,
                "next_cursor": next_cursor,
            },
            images,
        )

    def _create_render(
        self,
        *,
        document: Path,
        document_hash: str,
        identity: JsonObject,
        reference: str,
        renderer: JsonObject,
    ) -> JsonObject:
        temporary = self.store.temporary_render(reference)
        try:
            pdf = temporary / "document.pdf"
            self.renderer.render(document, pdf)
            index = self.pdf.build_text_index(pdf)
            page_count = index.get("page_count")
            if not isinstance(page_count, int) or page_count < 1:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="render_page_count_invalid",
                    message="LibreOffice produced no readable PDF pages.",
                )
            inspection = inspect_document(document, self.office)
            anchors = build_anchor_index(inspection)
            indexes = temporary / "indexes"
            indexes.mkdir()
            atomic_write_json(indexes / "pdf-text.json", index)
            atomic_write_json(
                indexes / "page-metadata.json",
                {
                    "schema_version": 2,
                    "page_count": page_count,
                    "pages": [
                        {
                            "page": page["page"],
                            "width_pt": page["width_pt"],
                            "height_pt": page["height_pt"],
                        }
                        for page in index["pages"]
                    ],
                },
            )
            atomic_write_json(indexes / "semantic-anchors.json", anchors)
            if sha256_file(document) != document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="document",
                    code="source_changed",
                    message="The DOCX changed while LibreOffice evidence was being created.",
                )
            files = [
                pdf,
                indexes / "pdf-text.json",
                indexes / "page-metadata.json",
                indexes / "semantic-anchors.json",
            ]
            manifest: JsonObject = {
                "schema_version": 2,
                "render_ref": reference,
                "render_identity": identity,
                "document_sha256": document_hash,
                "page_count": page_count,
                "fidelity": "approximate",
                "renderer": renderer,
                "files": self.store.file_inventory(temporary, files),
            }
            atomic_write_json(temporary / "manifest.json", manifest)
            self.store.publish_render(temporary, reference)
            return manifest
        finally:
            self.store.discard_temporary(temporary)

    def _contact_sheet(
        self,
        args: JsonObject,
        reference: str,
        manifest: JsonObject,
        pdf: Path,
        index: JsonObject,
    ) -> tuple[list[JsonObject], list[Path], str | None]:
        page_count = int(manifest["page_count"])
        requested, next_cursor = self._page_batch(
            args,
            page_count,
            reference=reference,
            mode="contact_sheet",
            limit=_CONTACT_PAGE_LIMIT,
        )
        thumbnails = [
            self._page_view(reference, pdf, index, page, "thumbnail")
            for page in requested
        ]
        identity: JsonObject = {
            "render_ref": reference,
            "view": "contact_sheet",
            "pages": requested,
            "dpi": _QUALITY_DPI["thumbnail"],
        }
        stored = self.store.get_or_create_view(
            render_ref=reference,
            identity=identity,
            stem=f"contact-{requested[0]:04d}-{requested[-1]:04d}",
            build=lambda output: contact_sheet(
                [(page, view.path) for page, view in zip(requested, thumbnails, strict=True)],
                output,
            ),
        )
        return [self._public_view(stored)], [stored.path], next_cursor

    def _pages(
        self,
        args: JsonObject,
        reference: str,
        manifest: JsonObject,
        pdf: Path,
        index: JsonObject,
        quality: str,
    ) -> tuple[list[JsonObject], list[Path], str | None]:
        requested, next_cursor = self._page_batch(
            args,
            int(manifest["page_count"]),
            reference=reference,
            mode="pages",
            limit=_MAX_RETURNED_IMAGES,
        )
        stored = [self._page_view(reference, pdf, index, page, quality) for page in requested]
        return (
            [self._public_view(item) for item in stored],
            [item.path for item in stored],
            next_cursor,
        )

    def _regions(
        self,
        args: JsonObject,
        reference: str,
        manifest: JsonObject,
        render_path: Path,
        pdf: Path,
        index: JsonObject,
        quality: str,
    ) -> tuple[list[JsonObject], list[Path], str | None, list[JsonObject]]:
        regions = args.get("regions")
        if not isinstance(regions, list) or not regions or not all(
            isinstance(item, dict) for item in regions
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_regions",
                message="regions mode requires a non-empty regions array.",
            )
        start, next_cursor = self._cursor_batch(
            args.get("cursor"),
            reference=reference,
            mode="regions",
            values=regions,
            limit=_MAX_RETURNED_IMAGES,
        )
        selected = regions[start : start + _MAX_RETURNED_IMAGES]
        anchors = self._read_index(render_path / "indexes" / "semantic-anchors.json")
        evidence: list[JsonObject] = []
        images: list[Path] = []
        warnings: list[JsonObject] = []
        for region in selected:
            located = self._locate_region(region, reference, index, anchors)
            if located.get("mapping_quality") == "mapping_unavailable":
                candidate_pages = located.get("candidate_pages", [])
                warnings.append(
                    {
                        "code": "mapping_unavailable",
                        "kind": "semantic_location",
                        "candidate_pages": candidate_pages,
                        "message": (
                            "The selector could not be mapped uniquely; no precise crop "
                            "was generated."
                        ),
                    }
                )
                for page in candidate_pages[:_MAX_RETURNED_IMAGES - len(images)]:
                    view = self._page_view(reference, pdf, index, int(page), "review")
                    public = self._public_view(view)
                    public["mapping_quality"] = "mapping_unavailable"
                    evidence.append(public)
                    images.append(view.path)
                continue
            page = int(located["page"])
            bbox = [float(value) for value in located["bbox_pdf"]]
            page_record = self._page_record(index, page)
            padding = region.get("padding", 16)
            if not isinstance(padding, int) or not 0 <= padding <= 256:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_region_padding",
                    message="Region padding must be an integer from 0 through 256.",
                )
            dpi = _QUALITY_DPI[quality]
            pad_pt = padding * 72 / dpi
            expanded = [
                max(0.0, bbox[0] - pad_pt),
                max(0.0, bbox[1] - pad_pt),
                min(float(page_record["width_pt"]), bbox[2] + pad_pt),
                min(float(page_record["height_pt"]), bbox[3] + pad_pt),
            ]
            identity = {
                "render_ref": reference,
                "view": "region",
                "selector": region,
                "page": page,
                "bbox_pdf": expanded,
                "dpi": dpi,
            }

            def build_region(
                output: Path,
                selected_page: int = page,
                selected_box: list[float] = expanded,
                selected_dpi: int = dpi,
            ) -> JsonObject:
                return self.pdf.rasterize_region(
                    pdf,
                    selected_page,
                    selected_box,
                    selected_dpi,
                    output,
                )

            stored = self.store.get_or_create_view(
                render_ref=reference,
                identity=identity,
                stem="region",
                build=build_region,
            )
            public = self._public_view(stored)
            public["mapping_quality"] = located.get("mapping_quality")
            public["mapping_basis"] = located.get("mapping_basis", [])
            evidence.append(public)
            images.append(stored.path)
        return evidence, images, next_cursor, warnings

    def _compare(
        self,
        args: JsonObject,
        reference: str,
        manifest: JsonObject,
        pdf: Path,
        index: JsonObject,
        quality: str,
    ) -> tuple[list[JsonObject], list[Path], str | None]:
        other_ref = args.get("compare_render_ref")
        other_path, other_manifest = self.store.resolve_render(other_ref)
        assert isinstance(other_ref, str)
        first_renderer = manifest.get("renderer")
        second_renderer = other_manifest.get("renderer")
        comparable = (
            isinstance(first_renderer, dict)
            and isinstance(second_renderer, dict)
            and all(
                first_renderer.get(field) == second_renderer.get(field)
                for field in (
                    "name",
                    "version",
                    "container_image_digest",
                    "font_environment_digest",
                    "locale",
                    "pdf_export_options",
                )
            )
        )
        if not comparable:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="incomparable_render_environment",
                message=(
                    "Compare requires the same LibreOffice image, fonts, locale, and PDF "
                    "export options."
                ),
            )
        requested, next_cursor = self._page_batch(
            args,
            int(manifest["page_count"]),
            reference=reference,
            mode=f"compare:{other_ref}",
            limit=_MAX_RETURNED_IMAGES,
        )
        other_index = self._read_index(other_path / "indexes" / "pdf-text.json")
        other_pdf = other_path / "document.pdf"
        dpi = _QUALITY_DPI[quality]
        evidence: list[JsonObject] = []
        images: list[Path] = []
        for page in requested:
            aligned_page, score = self._aligned_page(index, page, other_index)
            current = self._page_view(reference, pdf, index, page, quality)
            baseline = self._page_view(other_ref, other_pdf, other_index, aligned_page, quality)
            identity = {
                "render_ref": reference,
                "compare_render_ref": other_ref,
                "view": "compare",
                "page": page,
                "compare_page": aligned_page,
                "alignment": "text_anchor",
                "alignment_score": score,
                "dpi": dpi,
            }

            def build_comparison(
                output: Path,
                first: Path = baseline.path,
                second: Path = current.path,
            ) -> JsonObject:
                return comparison(first, second, output)

            stored = self.store.get_or_create_view(
                render_ref=reference,
                identity=identity,
                stem="compare",
                build=build_comparison,
            )
            public = self._public_view(stored)
            public["compare_render_ref"] = other_ref
            public["compare_page"] = aligned_page
            public["alignment"] = "text_anchor"
            public["alignment_score"] = score
            evidence.append(public)
            images.append(stored.path)
        return evidence, images, next_cursor

    def _page_view(
        self,
        reference: str,
        pdf: Path,
        index: JsonObject,
        page: int,
        quality: str,
    ) -> StoredView:
        page_record = self._page_record(index, page)
        dpi = _QUALITY_DPI[quality]
        identity: JsonObject = {
            "render_ref": reference,
            "view": "page",
            "page": page,
            "dpi": dpi,
        }
        return self.store.get_or_create_view(
            render_ref=reference,
            identity=identity,
            stem=f"page-{page:04d}-{quality}",
            build=lambda output: {
                **self.pdf.rasterize_page(pdf, page, dpi, output),
                "bbox_pdf": [
                    0.0,
                    0.0,
                    float(page_record["width_pt"]),
                    float(page_record["height_pt"]),
                ],
            },
        )

    def _locate_region(
        self,
        region: JsonObject,
        render_ref: str,
        index: JsonObject,
        anchors: JsonObject,
    ) -> JsonObject:
        selector = region.get("selector")
        allowed = {
            "object_ref": {"selector", "object_ref", "padding"},
            "text": {"selector", "text", "occurrence", "padding"},
            "image_bbox": {"selector", "evidence_ref", "bbox_px", "padding"},
        }
        if selector not in allowed or set(region) - allowed[str(selector)]:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_region_selector",
                message=(
                    "A region selector must be object_ref, text, or image_bbox with only "
                    "its supported fields."
                ),
            )
        if selector == "object_ref":
            return locate_object(index, anchors, region.get("object_ref"))
        if selector == "text":
            occurrence = region.get("occurrence")
            if occurrence is not None and not isinstance(occurrence, int):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_text_occurrence",
                    message="occurrence must be a positive integer.",
                )
            text = region.get("text")
            if not isinstance(text, str):
                text = ""
            return locate_text(index, text, occurrence=occurrence)
        stored = self.store.resolve_view(region.get("evidence_ref"))
        metadata = stored.metadata
        if metadata.get("render_ref") != render_ref or not isinstance(metadata.get("page"), int):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="image_bbox_source_invalid",
                message="image_bbox requires a single-page evidence_ref from the same render.",
            )
        bbox_px = region.get("bbox_px")
        pixel_size = metadata.get("pixel_size")
        source_bbox = metadata.get("bbox_pdf")
        if (
            not isinstance(bbox_px, list)
            or len(bbox_px) != 4
            or not all(isinstance(value, int) for value in bbox_px)
            or not isinstance(pixel_size, list)
            or len(pixel_size) != 2
            or not isinstance(source_bbox, list)
            or len(source_bbox) != 4
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_image_bbox",
                message="image_bbox requires four valid pixel coordinates bound to page evidence.",
            )
        width, height = (int(pixel_size[0]), int(pixel_size[1]))
        left, top, right, bottom = bbox_px
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="image_bbox_out_of_bounds",
                message="bbox_px lies outside the referenced image.",
            )
        x_scale = (float(source_bbox[2]) - float(source_bbox[0])) / width
        y_scale = (float(source_bbox[3]) - float(source_bbox[1])) / height
        return {
            "page": metadata["page"],
            "bbox_pdf": [
                float(source_bbox[0]) + left * x_scale,
                float(source_bbox[1]) + top * y_scale,
                float(source_bbox[0]) + right * x_scale,
                float(source_bbox[1]) + bottom * y_scale,
            ],
            "mapping_quality": "image_coordinates",
            "mapping_basis": [stored.reference],
        }

    @staticmethod
    def _public_view(stored: StoredView) -> JsonObject:
        hidden = {"identity", "schema_version", "image_sha256", "render_ref"}
        return {
            "evidence_ref": stored.reference,
            "image_sha256": stored.metadata["image_sha256"],
            **{key: value for key, value in stored.metadata.items() if key not in hidden},
        }

    @staticmethod
    def _read_index(path: Path) -> JsonObject:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="render_index_invalid",
                message="The render index cannot be read.",
            ) from error
        if not isinstance(value, dict) or value.get("schema_version") != 2:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="render_index_invalid",
                message="The render index has an unsupported shape.",
            )
        return value

    @staticmethod
    def _page_record(index: JsonObject, page: int) -> JsonObject:
        pages = index.get("pages")
        if not isinstance(pages, list) or not 1 <= page <= len(pages):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="visual_page_out_of_range",
                message="A requested page is outside this render.",
            )
        value = pages[page - 1]
        if not isinstance(value, dict):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="render_index_invalid",
                message="The render page index is invalid.",
            )
        return value

    def _page_batch(
        self,
        args: JsonObject,
        page_count: int,
        *,
        reference: str,
        mode: str,
        limit: int,
    ) -> tuple[list[int], str | None]:
        requested = args.get("pages")
        if requested is not None:
            if (
                not isinstance(requested, list)
                or not requested
                or not all(isinstance(item, int) for item in requested)
                or len(requested) != len(set(requested))
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_visual_pages",
                    message="pages must be a non-empty unique integer array.",
                )
            values = requested
        else:
            values = list(range(1, page_count + 1))
        if any(page < 1 or page > page_count for page in values):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="visual_page_out_of_range",
                message="A requested page is outside this render.",
            )
        start, next_cursor = self._cursor_batch(
            args.get("cursor"),
            reference=reference,
            mode=mode,
            values=values,
            limit=limit,
        )
        return values[start : start + limit], next_cursor

    @staticmethod
    def _cursor_batch(
        cursor: Any,
        *,
        reference: str,
        mode: str,
        values: list[Any],
        limit: int,
    ) -> tuple[int, str | None]:
        fingerprint = sha256_json({"render_ref": reference, "mode": mode, "values": values})[:16]
        start = 0
        if cursor is not None:
            if not isinstance(cursor, str):
                VisualEvidenceService._invalid_cursor()
            parts = cursor.split(":")
            if (
                len(parts) != 4
                or parts[:3] != ["visual-cursor", "v2", fingerprint]
                or not parts[3].isdigit()
            ):
                VisualEvidenceService._invalid_cursor()
            start = int(parts[3])
        if start < 0 or start >= len(values):
            VisualEvidenceService._invalid_cursor()
        end = min(start + limit, len(values))
        next_cursor = (
            f"visual-cursor:v2:{fingerprint}:{end}" if end < len(values) else None
        )
        return start, next_cursor

    @staticmethod
    def _invalid_cursor() -> None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_visual_cursor",
            message="The visual evidence cursor is invalid for this request.",
        )

    @staticmethod
    def _aligned_page(
        current_index: JsonObject,
        current_page: int,
        other_index: JsonObject,
    ) -> tuple[int, float]:
        current = VisualEvidenceService._page_record(current_index, current_page)
        current_text = normalize_text(str(current.get("text", "")))
        pages = other_index.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="compare_alignment_unavailable",
                message="The comparison render has no pages to align.",
            )
        if not current_text and current_page <= len(pages):
            return current_page, 1.0
        scored = [
            (
                SequenceMatcher(
                    None,
                    current_text,
                    normalize_text(str(page.get("text", ""))) if isinstance(page, dict) else "",
                ).ratio(),
                number,
            )
            for number, page in enumerate(pages, start=1)
        ]
        scored.sort(reverse=True)
        best_score, best_page = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if best_score < 0.2 or math.isclose(best_score, runner_up, abs_tol=0.02):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="compare_alignment_unavailable",
                message="The two renders cannot be uniquely aligned by PDF text anchors.",
            )
        return best_page, round(best_score, 4)

    @staticmethod
    def _reject_args(args: JsonObject, allowed: set[str], *, operation: str) -> None:
        unsupported = sorted(set(args) - allowed)
        if unsupported:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unsupported_visual_argument",
                message=f"{operation} does not accept: {', '.join(unsupported)}.",
            )

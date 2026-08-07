"""Object-driven template preparation without Agent-authored plans.

Every document version is immutable and addressed by its SHA-256.  The Agent
works on one opaque OfficeCLI object reference at a time; direct edits create a
new version and deliberately stale every reference from the prior version.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from docfit.fields import FieldRegistrySnapshot
from docfit.template.object_mutation import ObjectMutation, mutate_objects
from docfit.tools.inspection import (
    InspectedObject,
    Inspection,
    inspect_document,
    resolve_object_ref,
)
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    sha256_file,
)
from docfit.visual.service import VisualEvidenceService

_DOCUMENT_REF = re.compile(r"^document:v1:([0-9a-f]{64})$")
_TEMPLATE_SELECTOR = "paragraph, table, picture, run, sdt, shape"
_EDITABLE_KINDS = {"paragraph", "run", "table", "picture", "sdt", "shape"}
_MAX_SEARCH_RESULTS = 5
_MAX_PAGE_OBJECTS = 192
_MAX_BATCH_OPERATIONS = 32


def _normalize(value: str) -> str:
    return "".join(value.split()).casefold()


def _document_ref(document_hash: str) -> str:
    return f"document:v1:{document_hash}"


def _parent_paragraph_locator(locator: str) -> str | None:
    match = re.match(r"^(.*?/p(?:\[@paraId=[^]]+]|\[\d+]))(?:/.*)?$", locator)
    return match.group(1) if match else None


def _brief_text(value: Any, *, limit: int = 120) -> str:
    text = value if isinstance(value, str) else ""
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _placeholder_text(field: JsonObject) -> str:
    label = str(field.get("label", field["field_id"]))
    return f"【{label}】"


class TemplateWorkspaceService:
    """Thin domain service over shared OfficeCLI and visual evidence."""

    def __init__(
        self,
        *,
        task_root: Path,
        field_registry: Path,
        office: OfficeCliAdapter | None = None,
        visual: VisualEvidenceService | None = None,
    ) -> None:
        self.task_root = task_root.expanduser().resolve(strict=True)
        self.source = (self.task_root / "input" / "school-template.docx").resolve(strict=True)
        self.registry = FieldRegistrySnapshot.load(field_registry)
        self.office = office or OfficeCliAdapter()
        self._visual = visual

    @property
    def root(self) -> Path:
        return self.task_root / "work" / ".docfit" / "template-workspace-v1"

    @property
    def versions(self) -> Path:
        return self.root / "versions"

    @property
    def receipts(self) -> Path:
        return self.root / "receipts"

    @property
    def reviews(self) -> Path:
        return self.root / "reviews"

    @property
    def visual(self) -> VisualEvidenceService:
        if self._visual is None:
            self._visual = VisualEvidenceService(
                self.task_root,
                office=self.office,
                semantic_selector=_TEMPLATE_SELECTOR,
            )
        return self._visual

    def _inspection(self, document: Path) -> Inspection:
        return inspect_document(document, self.office, selector=_TEMPLATE_SELECTOR)

    def _register_source(self) -> tuple[str, Path]:
        source_hash = sha256_file(self.source)
        self.versions.mkdir(parents=True, exist_ok=True)
        target = self.versions / f"{source_hash}.docx"
        if not target.exists():
            temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            shutil.copyfile(self.source, temporary)
            temporary.chmod(0o600)
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
            finally:
                temporary.unlink(missing_ok=True)
        if sha256_file(target) != source_hash:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="document_version_hash_mismatch",
                message="An internal template version failed its integrity check.",
            )
        return _document_ref(source_hash), target

    def _resolve_document(self, reference: Any) -> tuple[str, Path]:
        if not isinstance(reference, str):
            raise _document_ref_error()
        match = _DOCUMENT_REF.fullmatch(reference)
        if match is None:
            raise _document_ref_error()
        document_hash = match.group(1)
        path = self.versions / f"{document_hash}.docx"
        if not path.is_file() or path.is_symlink() or sha256_file(path) != document_hash:
            raise _document_ref_error()
        return document_hash, path

    def _resolve_object(self, reference: Any) -> tuple[Path, Inspection, InspectedObject]:
        if not isinstance(reference, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_object_ref",
                message="An object_ref from template_view is required.",
            )
        document_hash = reference.get("document_sha256")
        _, document = self._resolve_document(
            _document_ref(document_hash) if isinstance(document_hash, str) else None
        )
        inspection = self._inspection(document)
        return document, inspection, resolve_object_ref(reference, inspection)

    def _local_context(
        self,
        inspection: Inspection,
        selected: InspectedObject,
    ) -> JsonObject:
        paragraph_locator = (
            selected.locator
            if selected.kind == "paragraph"
            else _parent_paragraph_locator(selected.locator)
        )
        paragraphs = [item for item in inspection.objects if item.kind == "paragraph"]
        parent = next(
            (item for item in paragraphs if item.locator == paragraph_locator),
            None,
        )
        siblings: list[JsonObject] = []
        if parent is not None:
            index = paragraphs.index(parent)
            for relative in (index - 1, index + 1):
                if 0 <= relative < len(paragraphs):
                    siblings.append(paragraphs[relative].public())
        children = [
            item.public()
            for item in inspection.objects
            if paragraph_locator is not None
            and item.locator.startswith(f"{paragraph_locator}/")
            and item.kind in {"run", "sdt"}
        ][:12]
        return {
            "current_object": selected.public(),
            "parent_paragraph": parent.public() if parent and parent is not selected else None,
            "adjacent_paragraphs": siblings,
            "child_objects": children,
            "context_truncated": len(children) == 12,
        }

    def _page_view(
        self,
        document_hash: str,
        document: Path,
        inspection: Inspection,
        page: int,
    ) -> tuple[JsonObject, list[Path]]:
        render, _ = self.visual.render({"input_docx": str(document), "overview": False})
        page_count = int(render["page_count"])
        if not 1 <= page <= page_count:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="page_out_of_range",
                message="The requested page does not exist in this Word version.",
            )
        review, images = self.visual.review(
            {
                "render_ref": render["render_ref"],
                "mode": "pages",
                "quality": "review",
                "pages": [page],
            }
        )
        self._record_review(
            document_hash,
            render_ref=str(render["render_ref"]),
            page_count=page_count,
            pages={page},
        )
        objects, truncated = self.visual.objects_on_page(
            str(render["render_ref"]),
            inspection,
            page,
            limit=_MAX_PAGE_OBJECTS,
        )
        return (
            {
                "page": page,
                "page_count": page_count,
                "objects": objects,
                "objects_truncated": truncated,
                "evidence": review.get("evidence", []),
            },
            images,
        )

    def view(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        action = args.get("action")
        if action == "open":
            reference, document = self._register_source()
            inspection = self._inspection(document)
            current_page, images = self._page_view(
                inspection.document_sha256,
                document,
                inspection,
                1,
            )
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": reference,
                    "document": {
                        "sha256": inspection.document_sha256,
                        "paragraphs": inspection.summary.get("paragraphs", 0),
                        "tables": inspection.summary.get("tables", 0),
                        "sections": inspection.summary.get("sections", 0),
                        "page_count": current_page["page_count"],
                    },
                    "registry": self.registry.identity(),
                    "current_page": current_page,
                    "visual": {"scope": "current_page"},
                    "guidance": (
                        "Judge only this current page/object context. Batch clear decisions "
                        "that are all visible here; search or request another page only when "
                        "the task actually needs it."
                    ),
                },
                images,
            )

        if action == "page":
            document_hash, document = self._resolve_document(args.get("document_ref"))
            page = args.get("page")
            if not isinstance(page, int):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="page_missing",
                    message="Viewing a page requires one page number.",
                )
            inspection = self._inspection(document)
            current_page, images = self._page_view(
                document_hash,
                document,
                inspection,
                page,
            )
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": _document_ref(document_hash),
                    "current_page": current_page,
                    "guidance": "Act only on objects you can identify in this page context.",
                },
                images,
            )

        if action == "focus":
            _, inspection, selected = self._resolve_object(args.get("object_ref"))
            reviewed, images = self._review(
                {
                    "document_ref": _document_ref(inspection.document_sha256),
                    "mode": "object",
                    "object_ref": selected.object_ref,
                    "quality": args.get("quality", "review"),
                    "padding": args.get("padding", 32),
                }
            )
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": _document_ref(inspection.document_sha256),
                    "local_context": self._local_context(inspection, selected),
                    "visual_review": reviewed["visual_review"],
                },
                images,
            )

        if action == "search":
            _, document = self._resolve_document(args.get("document_ref"))
            query = args.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="object_query_empty",
                    message="Object search requires non-empty text from the current task.",
                )
            inspection = self._inspection(document)
            normalized = _normalize(query)
            matches = [item for item in inspection.objects if normalized in _normalize(item.text)]
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": _document_ref(inspection.document_sha256),
                    "query": query,
                    "matches": [item.public() for item in matches[:_MAX_SEARCH_RESULTS]],
                    "match_count": len(matches),
                    "truncated": len(matches) > _MAX_SEARCH_RESULTS,
                    "guidance": (
                        "Focus one candidate before editing; refine the query when candidates "
                        "are ambiguous."
                    ),
                },
                [],
            )

        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_view_action_invalid",
            message="template_view action must be open, page, search, or focus.",
        )

    def registry_query(self, args: dict[str, Any]) -> JsonObject:
        raw_queries = args.get("queries")
        if (
            not isinstance(raw_queries, list)
            or not 1 <= len(raw_queries) <= 16
            or not all(isinstance(item, dict) for item in raw_queries)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="registry_queries_invalid",
                message="Provide one through sixteen object-specific Registry queries.",
            )
        document_hash: str | None = None
        results: list[JsonObject] = []
        for raw in raw_queries:
            _, inspection, selected = self._resolve_object(raw.get("object_ref"))
            if document_hash is None:
                document_hash = inspection.document_sha256
            elif inspection.document_sha256 != document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="batch_document_mismatch",
                    message="Every Registry query in a batch must use refs from one Word version.",
                )
            query = raw.get("query")
            field_id = raw.get("field_id")
            if isinstance(field_id, str) and field_id:
                matches = [self.registry.lookup(field_id)]
                operation = "lookup"
            elif isinstance(query, str) and query.strip():
                matches = list(self.registry.search(query, limit=_MAX_SEARCH_RESULTS))
                operation = "search"
            else:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="registry_query_missing",
                    message="Each item needs one exact field_id or object-specific search query.",
                )
            results.append(
                {
                    "current_object": {
                        "object_ref": selected.object_ref,
                        "type": selected.kind,
                        "text": selected.text,
                    },
                    "operation": operation,
                    "matches": matches,
                    "truncated": len(matches) == _MAX_SEARCH_RESULTS,
                }
            )
        assert document_hash is not None
        return {
            "schema_version": 1,
            "status": "ok",
            "document_ref": _document_ref(document_hash),
            "results": results,
            "registry": self.registry.identity(),
        }

    def edit(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        raw_operations = args.get("operations")
        review_page = args.get("review_page")
        if (
            not isinstance(raw_operations, list)
            or not 1 <= len(raw_operations) <= _MAX_BATCH_OPERATIONS
            or not all(isinstance(item, dict) for item in raw_operations)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_edit_operations_invalid",
                message="template_edit requires one through thirty-two object operations.",
            )
        if not isinstance(review_page, int) or review_page < 1:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="review_page_missing",
                message="A page-sized edit batch must identify the page to return after editing.",
            )

        document: Path | None = None
        before: Inspection | None = None
        existing_tags: set[str] = set()
        prepared: list[JsonObject] = []
        mutations: list[ObjectMutation] = []
        for raw in raw_operations:
            action = raw.get("action")
            if action not in {"materialize_slot", "clear_content", "remove_object"}:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_edit_action_invalid",
                    message=(
                        "Each operation must materialize_slot, clear_content, or remove_object."
                    ),
                )
            candidate_document, candidate_before, selected = self._resolve_object(
                raw.get("object_ref")
            )
            if before is None:
                document = candidate_document
                before = candidate_before
                existing_tags = {
                    str(item.format["tag"])
                    for item in before.objects
                    if item.kind == "sdt" and item.format.get("tag")
                }
            elif candidate_before.document_sha256 != before.document_sha256:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="batch_document_mismatch",
                    message="Every operation in a batch must use refs from one Word version.",
                )
            if selected.kind not in _EDITABLE_KINDS:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="object_kind_not_editable",
                    message="A selected object kind is not editable by template_edit.",
                )
            field: JsonObject | None = None
            slot_id: str | None = None
            placeholder: str | None = None
            if action == "materialize_slot":
                raw_field_id = raw.get("field_id")
                if not isinstance(raw_field_id, str):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="field_id_missing",
                        message="materialize_slot requires one Registry field_id.",
                    )
                field = self.registry.lookup(raw_field_id)
                ordinal = 1
                while f"{raw_field_id}.{ordinal}" in existing_tags:
                    ordinal += 1
                slot_id = f"{raw_field_id}.{ordinal}"
                existing_tags.add(slot_id)
                placeholder = _placeholder_text(field)
            prepared.append(
                {
                    "action": action,
                    "target": selected.public(),
                    "target_locator": selected.locator,
                    "field": field,
                    "slot_id": slot_id,
                    "placeholder": placeholder,
                }
            )
            mutations.append(
                ObjectMutation(
                    selected=selected,
                    action=str(action),
                    field_id=str(field["field_id"]) if field else None,
                    slot_id=slot_id,
                    content_type=(
                        str(field.get("content_type", "text")) if field else "text"
                    ),
                    placeholder_text=placeholder,
                )
            )

        assert document is not None and before is not None
        source_hash = before.document_sha256
        self.versions.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".template-edit-", suffix=".docx", dir=self.versions
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            mutate_objects(document, temporary, mutations=mutations)
            validate_docx_package(temporary)
            office_validation = self.office.validate(temporary)
            output_hash = sha256_file(temporary)
            if output_hash == source_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="edit_had_no_effect",
                    message="The selected edit did not change the Word document.",
                )
            if sha256_file(document) != source_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="source_document_changed",
                    message="The immutable input version changed during editing.",
                )
            output = self.versions / f"{output_hash}.docx"
            if output.exists():
                if sha256_file(output) != output_hash:
                    raise ToolFailure(
                        status="error",
                        origin="evidence",
                        code="document_version_hash_mismatch",
                        message="An internal template version failed its integrity check.",
                    )
            else:
                os.link(temporary, output)
            after = self._inspection(output)
            self._verify_edit_effects(before, after, prepared)
            receipt: JsonObject = {
                "schema_version": 1,
                "input_sha256": source_hash,
                "output_sha256": output_hash,
                "operations": prepared,
                "officecli_validation": office_validation,
            }
            self.receipts.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.receipts / f"{output_hash}.json", receipt)
            current_page, images = self._page_view(
                output_hash,
                output,
                after,
                review_page,
            )
            materialized_count = sum(
                item["action"] == "materialize_slot" for item in prepared
            )
            removed_count = len(prepared) - materialized_count
            guidance = (
                "Judge the returned changed page now. If it is correct, continue from "
                "its fresh object refs without a separate review call."
            )
            if removed_count >= 5 and materialized_count == 0:
                guidance = (
                    f"This batch removed or cleared {removed_count} objects and created no "
                    "fillable slot. Judge the returned page before continuing. If these were "
                    "student-authored examples, do not accept a blank content page: branch "
                    "from previous_document_ref and reissue the batch with one representative "
                    "object materialized as its fill interface."
                )
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "committed": True,
                    "previous_document_ref": _document_ref(source_hash),
                    "document_ref": _document_ref(output_hash),
                    "document_sha256": output_hash,
                    "prior_refs_do_not_address_new_version": True,
                    "applied": [
                        {
                            "action": item["action"],
                            "type": item["target"].get("type"),
                            "text": _brief_text(item["target"].get("text")),
                            **(
                                {"field_id": item["field"]["field_id"]}
                                if item["field"] is not None
                                else {}
                            ),
                            **(
                                {"slot_id": item["slot_id"]}
                                if item["slot_id"] is not None
                                else {}
                            ),
                        }
                        for item in prepared
                    ],
                    "slots": [
                        {
                            "slot_id": item["slot_id"],
                            "field_id": item["field"]["field_id"],
                            "placeholder": item["placeholder"],
                        }
                        for item in prepared
                        if item["field"] is not None
                    ],
                    "reviewed_page": review_page,
                    "current_page": current_page,
                    "checks": [
                        {"name": "source_unchanged", "result": "ok"},
                        {"name": "package_reopens", "result": "ok"},
                        {"name": "officecli_validate", "result": "ok"},
                        {"name": "all_requested_effects_re_read", "result": "ok"},
                        {"name": "non_target_text_preserved", "result": "ok"},
                        {"name": "changed_page_returned", "result": "ok"},
                    ],
                    "guidance": guidance,
                },
                images,
            )
        finally:
            temporary.unlink(missing_ok=True)

    def _verify_edit_effects(
        self,
        before: Inspection,
        after: Inspection,
        operations: list[JsonObject],
    ) -> None:
        selected = [item["target"] for item in operations]

        def in_target_closure(item: InspectedObject) -> bool:
            for operation, target in zip(operations, selected, strict=True):
                locator = operation.get("target_locator")
                kind = target.get("type")
                if not isinstance(locator, str):
                    continue
                paragraph_locator = _parent_paragraph_locator(locator)
                if item.locator == locator:
                    return True
                if kind in {"paragraph", "table", "sdt", "shape"} and item.locator.startswith(
                    f"{locator}/"
                ):
                    return True
                if kind != "paragraph" and paragraph_locator == item.locator:
                    return True
            return False

        protected = Counter(
            item.text for item in before.objects if item.text and not in_target_closure(item)
        )
        resulting = Counter(item.text for item in after.objects if item.text)
        lost = protected - resulting
        if lost:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="non_target_content_changed",
                message="Text outside the selected object changed during the edit.",
            )
        removed_by_kind = Counter(
            item["target"].get("type")
            for item in operations
            if item.get("action") == "remove_object"
        )
        for kind, count in removed_by_kind.items():
            kind_before = sum(1 for item in before.objects if item.kind == kind)
            kind_after = sum(1 for item in after.objects if item.kind == kind)
            if kind_after > kind_before - count:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="object_not_removed",
                    message="At least one selected object is still present after batch removal.",
                )
        before_text = Counter(item.text for item in before.objects if item.text)
        after_text = Counter(item.text for item in after.objects if item.text)
        for operation in operations:
            action = operation.get("action")
            field = operation.get("field")
            slot_id = operation.get("slot_id")
            target = operation["target"]
            if action == "materialize_slot":
                assert isinstance(field, dict)
                matches = [
                    item
                    for item in after.objects
                    if item.kind == "sdt"
                    and item.format.get("tag") == slot_id
                    and item.format.get("alias") == field.get("field_id")
                ]
                if len(matches) != 1:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="content_control_not_materialized",
                        message="A requested content control is not uniquely present after edit.",
                    )
            elif action == "clear_content":
                text = target.get("text")
                if isinstance(text, str) and text and after_text[text] >= before_text[text]:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="content_not_cleared",
                        message="At least one selected object's content was not cleared.",
                    )

    def _review(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        document_hash, document = self._resolve_document(args.get("document_ref"))
        mode = args.get("mode", "pages")
        render, _ = self.visual.render({"input_docx": str(document), "overview": False})
        visual_args: JsonObject = {
            "render_ref": render["render_ref"],
            "quality": args.get("quality", "review"),
        }
        if mode == "pages":
            visual_args["mode"] = "pages"
            if "pages" in args:
                visual_args["pages"] = args["pages"]
        elif mode == "object":
            object_ref = args.get("object_ref")
            document_ref_hash = (
                object_ref.get("document_sha256") if isinstance(object_ref, dict) else None
            )
            if document_ref_hash != document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="stale_object_ref",
                    message="The review object_ref does not belong to this document version.",
                )
            visual_args.update(
                {
                    "mode": "regions",
                    "regions": [
                        {
                            "selector": "object_ref",
                            "object_ref": object_ref,
                            "padding": args.get("padding", 32),
                        }
                    ],
                }
            )
        else:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_review_mode_invalid",
                message="Review mode must be pages or object.",
            )
        review, images = self.visual.review(visual_args)
        pages: set[int] = set()
        for evidence in review.get("evidence", []):
            pages.update(self._evidence_pages(evidence))
        self._record_review(
            document_hash,
            render_ref=str(render["render_ref"]),
            page_count=int(render["page_count"]),
            pages=pages,
        )
        return (
            {
                "schema_version": 1,
                "status": "ok",
                "document_ref": _document_ref(document_hash),
                "document_sha256": document_hash,
                "page_count": render["page_count"],
                "mode": mode,
                "visual_review": review,
                "next_cursor": review.get("next_cursor"),
            },
            images,
        )

    @staticmethod
    def _evidence_pages(value: Any) -> set[int]:
        if not isinstance(value, dict):
            return set()
        raw_pages = value.get("covered_pages", value.get("pages"))
        if isinstance(raw_pages, list):
            return {page for page in raw_pages if isinstance(page, int)}
        page = value.get("page")
        return {page} if isinstance(page, int) else set()

    def _record_review(
        self,
        document_hash: str,
        *,
        render_ref: str,
        page_count: int,
        pages: set[int],
    ) -> None:
        self.reviews.mkdir(parents=True, exist_ok=True)
        path = self.reviews / f"{document_hash}.json"
        existing: JsonObject = {}
        if path.exists():
            try:
                value: Any = json.loads(path.read_text(encoding="utf-8"))
                existing = value if isinstance(value, dict) else {}
            except (OSError, json.JSONDecodeError):
                existing = {}
        accumulated = {page for page in existing.get("reviewed_pages", []) if isinstance(page, int)}
        accumulated.update(pages)
        atomic_write_json(
            path,
            {
                "schema_version": 1,
                "document_sha256": document_hash,
                "render_ref": render_ref,
                "page_count": page_count,
                "reviewed_pages": sorted(accumulated),
            },
        )

    def publish(self, args: dict[str, Any]) -> JsonObject:
        document_hash, document = self._resolve_document(args.get("document_ref"))
        if sha256_file(self.registry.path) != self.registry.sha256:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="field_registry_changed",
                message="The field Registry changed during template preparation.",
            )
        source_hash = sha256_file(self.source)
        registered_source = self.versions / f"{source_hash}.docx"
        if not registered_source.exists() or sha256_file(registered_source) != source_hash:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="source_document_changed",
                message="The source template changed during preparation.",
            )
        validate_docx_package(document)
        office_validation = self.office.validate(document)
        review = self._read_review(document_hash)
        reviewed_pages = {page for page in review["reviewed_pages"] if isinstance(page, int)}
        if not reviewed_pages:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_visual_review_missing",
                message="Review the changed local region of the current Word before publishing.",
                suggested_actions=("review_the_changed_region",),
            )
        lineage = self._lineage(document_hash, source_hash)
        operations = [
            operation
            for receipt in lineage
            for operation in receipt.get("operations", [])
            if isinstance(operation, dict)
        ]
        slots = [item for item in operations if item.get("action") == "materialize_slot"]
        removes = [
            item
            for item in operations
            if item.get("action") in {"remove_object", "clear_content"}
        ]
        inspection = self._inspection(document)
        controls = [item for item in inspection.objects if item.kind == "sdt"]
        fill_contract: JsonObject = {
            "schema_version": 1,
            "template_sha256": document_hash,
            "registry": self.registry.identity(),
            "slots": [
                {
                    "slot_id": item.get("slot_id"),
                    "field": item.get("field"),
                    "object_ref": next(
                        (
                            control.object_ref
                            for control in controls
                            if control.format.get("tag") == item.get("slot_id")
                        ),
                        None,
                    ),
                }
                for item in slots
            ],
        }
        if any(item.get("object_ref") is None for item in fill_contract["slots"]):
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="created_slot_missing",
                message="A content control created during this task is absent from the final Word.",
            )
        audit_dir = self.root / "publication"
        audit_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(audit_dir / "fill-contract.json", fill_contract)
        counts: JsonObject = {
            "slot": len(slots),
            "remove": len(removes),
            "manual": 0,
            "gap": 0,
            "unresolved": 0,
        }
        atomic_write_json(
            audit_dir / "build-report.json",
            {
                "schema_version": 1,
                "status": "built",
                "source_sha256": source_hash,
                "template_sha256": document_hash,
                "counts": counts,
                "review": review,
                "officecli_validation": office_validation,
            },
        )
        output = self.task_root / "output" / "final-template.docx"
        if output.exists():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_template_exists",
                message="The final Word already exists; publication never overwrites it.",
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".final-template-", suffix=".docx", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(document, temporary)
            temporary.chmod(0o600)
            os.link(temporary, output)
        except FileExistsError as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_template_exists",
                message="The final Word already exists; publication never overwrites it.",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)
        if sha256_file(output) != document_hash:
            output.unlink(missing_ok=True)
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="published_template_hash_mismatch",
                message="The published Word does not match the validated document version.",
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "published": True,
            "artifact_path": "output/final-template.docx",
            "template_sha256": document_hash,
            "counts": counts,
            "checks": [
                {"name": "source_unchanged", "result": "ok"},
                {"name": "registry_unchanged", "result": "ok"},
                {"name": "package_reopens", "result": "ok"},
                {"name": "officecli_validate", "result": "ok"},
                {"name": "current_version_local_feedback_returned", "result": "ok"},
                {"name": "single_word_published", "result": "ok"},
            ],
        }

    def _read_review(self, document_hash: str) -> JsonObject:
        path = self.reviews / f"{document_hash}.json"
        try:
            value: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_visual_review_missing",
                message="Review the changed local region of the current Word before publishing.",
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("document_sha256") != document_hash
            or not isinstance(value.get("page_count"), int)
            or not isinstance(value.get("reviewed_pages"), list)
        ):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="final_visual_review_invalid",
                message="The final visual review receipt is invalid.",
            )
        return value

    def _lineage(self, document_hash: str, source_hash: str) -> list[JsonObject]:
        current = document_hash
        reverse: list[JsonObject] = []
        visited: set[str] = set()
        while current != source_hash:
            if current in visited:
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_cycle",
                    message="The internal template edit lineage contains a cycle.",
                )
            visited.add(current)
            path = self.receipts / f"{current}.json"
            try:
                value: Any = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_missing",
                    message="The current document is not connected to the source template.",
                ) from error
            if not isinstance(value, dict) or value.get("output_sha256") != current:
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_invalid",
                    message="An internal edit receipt is invalid.",
                )
            reverse.append(value)
            parent = value.get("input_sha256")
            if not isinstance(parent, str):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_invalid",
                    message="An internal edit receipt has no valid parent version.",
                )
            current = parent
        return list(reversed(reverse))


def _document_ref_error() -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code="document_ref_not_found",
        message="The document_ref is invalid or unavailable in this template task.",
        suggested_actions=("open_the_template_or_use_the_latest_edit_result",),
    )

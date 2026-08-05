"""Concrete implementation of the five stable DocFit Tool contracts."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from docfit.tools.adobe import (
    ADOBE_CONVERSION_PROFILE,
    ADOBE_FIDELITY,
    ADOBE_REVISION_DISPLAY,
    AdobePdfServicesAdapter,
)
from docfit.tools.images import (
    compare_pages,
    create_contact_sheet,
    crop_page,
    ensure_review_budget,
    font_environment_fingerprint,
    image_metadata,
    pdf_to_png_pages,
    verify_png,
)
from docfit.tools.inspection import (
    Inspection,
    html_path_for_locator,
    inspect_document,
    resolve_object_ref,
)
from docfit.tools.layout import measure_html_layout
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.ooxml import import_content_objects
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    authorized_path,
    read_json,
    require_docx,
    sha256_file,
    sha256_json,
    task_root_from_args,
)

RENDER_INTENTS = ("baseline", "edit_feedback", "candidate_verification")
VISUAL_MODES = ("pages", "crops", "contact_sheet", "compare")
MAX_RENDER_PAGES = 500

_SET_PROPERTY_ALLOWLIST = {
    "alignment",
    "bold",
    "color",
    "font",
    "font.ascii",
    "font.eastAsia",
    "font.hAnsi",
    "italic",
    "keepTogether",
    "keepWithNext",
    "lineSpacing",
    "pageBreakBefore",
    "size",
    "spaceAfter",
    "spaceBefore",
    "widowControl",
}


def _normalized_property_value(key: str, value: Any) -> str:
    normalized = str(value).strip().casefold()
    if key == "color":
        return normalized.removeprefix("#")
    if key == "lineSpacing":
        return normalized.removesuffix("x")
    return normalized


def _property_applied(item: Any, key: str, expected: str) -> bool:
    candidate_keys = [key, f"effective.{key}"]
    if key == "font":
        candidate_keys.extend(
            (
                "font.latin",
                "font.ea",
                "effective.font.ascii",
                "effective.font.eastAsia",
                "effective.font.hAnsi",
            )
        )
    elif key == "font.ascii":
        candidate_keys.extend(("font.latin", "effective.font.ascii"))
    elif key == "font.eastAsia":
        candidate_keys.extend(("font.ea", "effective.font.eastAsia"))
    elif key == "font.hAnsi":
        candidate_keys.extend(("font.latin", "effective.font.hAnsi"))
    return any(
        candidate in item.format
        and _normalized_property_value(key, item.format[candidate])
        == _normalized_property_value(key, expected)
        for candidate in candidate_keys
    )


def _output_directory(value: Any, *, task_root: Path, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="missing_output_directory",
            message=f"{field} must be a non-empty path string.",
        )
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else task_root / raw
    if candidate.exists():
        return authorized_path(
            str(candidate),
            task_root=task_root,
            field=field,
            expect_directory=True,
        )
    return authorized_path(
        str(candidate),
        task_root=task_root,
        field=field,
        must_exist=False,
    )


def _document_path(args: dict[str, Any], field: str, root: Path) -> Path:
    path = authorized_path(args.get(field), task_root=root, field=field)
    require_docx(path, field=field)
    return path


def _public_inspection(inspection: Inspection) -> JsonObject:
    return {
        "schema_version": 1,
        "status": "ok",
        "checks": [
            {"name": "docx_package", "result": "ok"},
            {"name": "officecli_parse", "result": "ok"},
        ],
        "warnings": list(inspection.warnings),
        "failure": None,
        "document": {
            "sha256": inspection.document_sha256,
            **inspection.summary,
        },
        "objects": [item.public() for item in inspection.objects],
        "risks": list(inspection.risks),
        "provider": inspection.provider,
    }


def _require_operations(value: Any) -> list[JsonObject]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, dict) for item in value)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_operations",
            message="docx_edit requires a non-empty array of operation objects.",
        )
    return value


def _scalar_properties(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_edit_properties",
            message="set_properties requires a non-empty properties object.",
        )
    unsupported = sorted(set(value) - _SET_PROPERTY_ALLOWLIST)
    if unsupported:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_edit_property",
            message="One or more requested formatting properties are not in the M1 allowlist.",
        )
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, (str, int, float, bool)):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_edit_property_value",
                message="Formatting property values must be scalar.",
            )
        result[key] = str(item).lower() if isinstance(item, bool) else str(item)
    return result


def _render_ref_path(value: Any, *, task_root: Path, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="missing_render_ref_path",
            message=f"{field} must identify render evidence.",
        )
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else task_root / raw
    path = authorized_path(
        str(candidate),
        task_root=task_root,
        field=field,
        expect_directory=candidate.is_dir(),
    )
    if path.is_dir():
        path = path / "render-ref.json"
    if path.name != "render-ref.json" or not path.is_file():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_render_ref_path",
            message=f"{field} must identify a render-ref.json file or its containing directory.",
        )
    return path


def _load_render_ref(value: Any, *, task_root: Path, field: str) -> tuple[Path, JsonObject]:
    path = _render_ref_path(value, task_root=task_root, field=field)
    reference = read_json(path)
    required = {
        "schema_version",
        "document_sha256",
        "render_sha256",
        "render_intent",
        "fidelity",
        "provider",
        "font_environment",
        "page_count",
        "dpi",
        "artifacts",
    }
    if reference.get("schema_version") != 1 or not required.issubset(reference):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_render_ref",
            message="The referenced render evidence has an invalid or unsupported schema.",
        )
    artifacts = reference.get("artifacts")
    pages = artifacts.get("pages") if isinstance(artifacts, dict) else None
    if not isinstance(pages, list) or len(pages) != reference.get("page_count"):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="incomplete_render_ref",
            message="The render ref does not enumerate every page artifact.",
        )
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("path"), str):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_render_page",
                message="A render page entry is invalid.",
            )
        page_path = authorized_path(
            page["path"],
            task_root=task_root,
            field="render_page",
        )
        if page.get("sha256") != sha256_file(page_path):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="stale_render_ref",
                message="A page image no longer matches its render ref.",
            )
    document_path = reference.get("document_path")
    if isinstance(document_path, str):
        current = authorized_path(
            document_path,
            task_root=task_root,
            field="render_document",
        )
        if sha256_file(current) != reference.get("document_sha256"):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="render_document_changed",
                message="The render ref belongs to an older document snapshot.",
            )
    return path, reference


def _page_paths(reference: JsonObject, *, task_root: Path) -> list[Path]:
    artifacts = reference["artifacts"]
    assert isinstance(artifacts, dict)
    values = artifacts["pages"]
    assert isinstance(values, list)
    return [
        authorized_path(value["path"], task_root=task_root, field="render_page")
        for value in values
        if isinstance(value, dict)
    ]


class DocFitToolService:
    """One concrete service; it owns no Agent loop or workflow state."""

    def __init__(
        self,
        *,
        office: OfficeCliAdapter | None = None,
        adobe: AdobePdfServicesAdapter | None = None,
    ) -> None:
        self._office = office
        self._adobe = adobe

    @property
    def office(self) -> OfficeCliAdapter:
        if self._office is None:
            self._office = OfficeCliAdapter()
        return self._office

    @property
    def adobe(self) -> AdobePdfServicesAdapter:
        if self._adobe is None:
            self._adobe = AdobePdfServicesAdapter()
        return self._adobe

    def inspect(self, args: dict[str, Any]) -> JsonObject:
        root = task_root_from_args(args)
        document = _document_path(args, "input_docx", root)
        inspection = inspect_document(document, self.office)
        result = _public_inspection(inspection)
        focus = args.get("focus", [])
        if focus and (
            not isinstance(focus, list) or not all(isinstance(item, str) for item in focus)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_inspect_focus",
                message="focus must be an array of inspection focus strings.",
            )
        result["focus"] = focus
        output_value = args.get("output")
        if output_value is not None:
            output = authorized_path(
                output_value,
                task_root=root,
                field="output",
                must_exist=False,
            )
            atomic_write_json(output, result)
            result["analysis_path"] = str(output)
        return result

    def edit(self, args: dict[str, Any]) -> JsonObject:
        root = task_root_from_args(args)
        input_docx = _document_path(args, "input_docx", root)
        output_docx = authorized_path(
            args.get("output_docx"),
            task_root=root,
            field="output_docx",
            must_exist=False,
        )
        require_docx(output_docx, field="output_docx")
        if input_docx == output_docx:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_overwrite_denied",
                message="docx_edit never writes over its input document.",
            )
        overwrite = args.get("overwrite", False)
        if not isinstance(overwrite, bool):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_overwrite_flag",
                message="overwrite must be a boolean.",
            )
        if output_docx.exists() and not overwrite:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="output_exists",
                message=(
                    "output_docx already exists; set overwrite only when replacement is intended."
                ),
            )
        operations = _require_operations(args.get("operations"))
        source_hash = sha256_file(input_docx)
        inspection = inspect_document(input_docx, self.office)
        office_commands: list[JsonObject] = []
        import_plans: list[dict[str, Any]] = []
        effect_expectations: list[dict[str, Any]] = []
        changed_locators: set[str] = set()

        for operation in operations:
            action = operation.get("action")
            if action in {"replace_text", "apply_style", "set_properties"}:
                target = resolve_object_ref(operation.get("target_ref"), inspection)
                changed_locators.add(target.locator)
                if action == "replace_text":
                    expected = operation.get("expected_text")
                    replacement = operation.get("replacement")
                    if (
                        not isinstance(expected, str)
                        or not expected
                        or not isinstance(replacement, str)
                    ):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="invalid_text_replacement",
                            message=(
                                "replace_text requires non-empty expected_text and string "
                                "replacement."
                            ),
                        )
                    if expected not in target.text:
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="expected_text_mismatch",
                            message="expected_text is absent from the referenced object.",
                        )
                    properties = {"find": expected, "replace": replacement}
                    effect_expectations.append(
                        {
                            "action": action,
                            "locator": target.locator,
                            "replacement": replacement,
                        }
                    )
                elif action == "apply_style":
                    style = operation.get("style")
                    if not isinstance(style, str) or not style:
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="invalid_style",
                            message="apply_style requires a non-empty style name.",
                        )
                    properties = {"style": style}
                    effect_expectations.append(
                        {"action": action, "locator": target.locator, "style": style}
                    )
                else:
                    properties = _scalar_properties(operation.get("properties"))
                    effect_expectations.append(
                        {"action": action, "locator": target.locator, "properties": properties}
                    )
                office_commands.append(
                    {"command": "set", "path": target.locator, "props": properties}
                )
                continue
            if action not in {"import_content_objects", "import_template_sections"}:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="unsupported_edit_action",
                    message="An edit operation uses an unsupported M1 action.",
                )
            legacy_template_import = action == "import_template_sections"
            document_field = "template_docx" if legacy_template_import else "source_docx"
            hash_field = "template_sha256" if legacy_template_import else "source_sha256"
            source_docx = _document_path(operation, document_field, root)
            if source_docx == input_docx:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="cross_document_source_required",
                    message=(
                        "Cross-document content import requires distinct source and target "
                        "documents."
                    ),
                )
            imported_source_hash = sha256_file(source_docx)
            if operation.get(hash_field) != imported_source_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code=(
                        "template_hash_mismatch"
                        if legacy_template_import
                        else "content_source_hash_mismatch"
                    ),
                    message=f"The source snapshot hash does not match {hash_field}.",
                    suggested_actions=("inspect_source_again",),
                )
            source_inspection = inspect_document(source_docx, self.office)
            source_refs = operation.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_content_source_refs",
                    message="source_refs must be a non-empty array of source object refs.",
                )
            source_objects = [
                resolve_object_ref(reference, source_inspection) for reference in source_refs
            ]
            position = operation.get("position", "end")
            anchor_ref = operation.get(
                "insert_anchor_ref" if legacy_template_import else "target_anchor_ref"
            )
            anchor = resolve_object_ref(anchor_ref, inspection) if anchor_ref is not None else None
            include_section = operation.get(
                (
                    "include_final_section_properties"
                    if legacy_template_import
                    else "include_source_final_section_properties"
                ),
                False,
            )
            if not isinstance(position, str) or not isinstance(include_section, bool):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_content_import_options",
                    message="Content import position or section option is invalid.",
                )
            import_plans.append(
                {
                    "action": action,
                    "source_docx": source_docx,
                    "source_sha256": imported_source_hash,
                    "source_locators": [item.locator for item in source_objects],
                    "source_texts": [item.text for item in source_objects if item.text],
                    "anchor_locator": anchor.locator if anchor else None,
                    "position": position,
                    "include_source_final_section_properties": include_section,
                }
            )

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".docfit-edit-",
            suffix=".docx",
            dir=output_docx.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        import_evidence: list[JsonObject] = []
        try:
            shutil.copyfile(input_docx, temporary)
            temporary.chmod(0o600)
            if office_commands:
                self.office.batch(temporary, office_commands)
            for index, plan in enumerate(import_plans):
                imported = temporary.with_name(f"{temporary.stem}-import-{index}.docx")
                evidence = import_content_objects(
                    target_docx=temporary,
                    source_docx=plan["source_docx"],
                    source_locators=plan["source_locators"],
                    anchor_locator=plan["anchor_locator"],
                    position=plan["position"],
                    include_source_final_section_properties=plan[
                        "include_source_final_section_properties"
                    ],
                    output_docx=imported,
                )
                os.replace(imported, temporary)
                import_evidence.append(
                    {
                        **evidence,
                        "action": plan["action"],
                        "source_sha256": plan["source_sha256"],
                        "target_sha256_before": source_hash,
                    }
                )
            validate_docx_package(temporary)
            office_validation = self.office.validate(temporary)
            after = inspect_document(temporary, self.office)
            after_by_locator = {item.locator: item for item in after.objects}
            for expectation in effect_expectations:
                actual = after_by_locator.get(expectation["locator"])
                if actual is None:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="edited_object_missing",
                        message="An edited object disappeared during the postcondition check.",
                    )
                if (
                    expectation["action"] == "replace_text"
                    and expectation["replacement"] not in actual.text
                ):
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="replacement_not_applied",
                        message="OfficeCLI reported success but the replacement is absent.",
                    )
                if expectation["action"] == "apply_style" and actual.style != expectation["style"]:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="style_not_applied",
                        message="OfficeCLI reported success but the requested style is absent.",
                    )
                if expectation["action"] == "set_properties":
                    unapplied = [
                        key
                        for key, expected in expectation["properties"].items()
                        if not _property_applied(actual, key, expected)
                    ]
                    if unapplied:
                        raise ToolFailure(
                            status="error",
                            origin="postcondition",
                            code="properties_not_applied",
                            message=(
                                "OfficeCLI reported success but one or more requested "
                                "properties are absent."
                            ),
                        )
            protected_text = Counter(
                item.text
                for item in inspection.objects
                if item.text and item.locator not in changed_locators
            )
            resulting_text = Counter(item.text for item in after.objects if item.text)
            lost = protected_text - resulting_text
            if lost:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="non_target_content_changed",
                    message="A non-target text object was lost during editing.",
                )
            imported_text = Counter(
                text for plan in import_plans for text in plan["source_texts"]
            )
            missing_imported = imported_text - resulting_text
            if missing_imported:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="imported_content_missing",
                    message="One or more selected source text objects are absent after import.",
                )
            if sha256_file(input_docx) != source_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="source_document_changed",
                    message="The source document changed during editing; output was not published.",
                )
            if any(
                sha256_file(plan["source_docx"]) != plan["source_sha256"]
                for plan in import_plans
            ):
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="import_source_document_changed",
                    message=(
                        "A content source document changed during editing; output was not "
                        "published."
                    ),
                )
            output_hash = sha256_file(temporary)
            os.replace(temporary, output_docx)
            return {
                "schema_version": 1,
                "status": "ok",
                "committed": True,
                "checks": [
                    {"name": "request_preconditions", "result": "ok"},
                    {"name": "source_unchanged", "result": "ok", "sha256": source_hash},
                    {"name": "package_reopens", "result": "ok"},
                    {"name": "officecli_validate", "result": "ok", **office_validation},
                    {"name": "effects_re_read", "result": "ok"},
                    {"name": "non_target_text_preserved", "result": "ok"},
                ],
                "warnings": [],
                "failure": None,
                "input_sha256": source_hash,
                "output_sha256": output_hash,
                "output_docx": str(output_docx),
                "operations": [
                    {"index": index, "action": operation.get("action"), "result": "applied"}
                    for index, operation in enumerate(operations)
                ],
                "content_imports": import_evidence,
                "template_imports": [
                    item
                    for item in import_evidence
                    if item.get("action") == "import_template_sections"
                ],
                "provider": self.office.evidence(),
            }
        finally:
            temporary.unlink(missing_ok=True)
            for leftover in output_docx.parent.glob(f"{temporary.stem}-import-*.docx"):
                leftover.unlink(missing_ok=True)

    def render(self, args: dict[str, Any]) -> JsonObject:
        root = task_root_from_args(args)
        input_docx = _document_path(args, "input_docx", root)
        intent = args.get("render_intent")
        if intent not in RENDER_INTENTS:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_render_intent",
                message="render_intent must be baseline, edit_feedback, or candidate_verification.",
            )
        forbidden = {"provider", "backend", "engine"}.intersection(args)
        if forbidden:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="backend_selection_denied",
                message="The public render contract does not accept a backend selector.",
            )
        output = _output_directory(args.get("output_dir"), task_root=root, field="output_dir")
        document_hash = sha256_file(input_docx)
        focus_value = args.get("focus_object_refs", [])
        if not isinstance(focus_value, list):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_focus_object_refs",
                message="focus_object_refs must be an array of current object refs.",
            )
        focused_objects: list[tuple[Any, str | None]] = []
        if focus_value:
            current_inspection = inspect_document(input_docx, self.office)
            focused_objects = [
                (
                    item,
                    html_path_for_locator(input_docx, item.locator),
                )
                for item in (
                    resolve_object_ref(reference, current_inspection) for reference in focus_value
                )
            ]
        parent_reference: JsonObject | None = None
        parent_identity: JsonObject | None = None
        baseline_value = args.get("baseline_render_ref")
        if baseline_value is not None:
            parent_path, parent_reference = _load_render_ref(
                baseline_value,
                task_root=root,
                field="baseline_render_ref",
            )
            parent_identity = {
                "render_sha256": parent_reference["render_sha256"],
                "document_sha256": parent_reference["document_sha256"],
                "ref_path": str(parent_path),
            }
        if intent == "candidate_verification" and parent_reference is None:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="candidate_baseline_required",
                message="candidate_verification requires a valid baseline_render_ref.",
            )
        if intent == "edit_feedback":
            provider = self.office.evidence()
            fidelity = "approximate"
            conversion_profile = "officecli_html_screenshot"
            revision_display = "not_applicable"
            font_environment = font_environment_fingerprint()
            target_application: str | None = None
            target_application_version: str | None = None
        else:
            provider = self.adobe.evidence()
            fidelity = ADOBE_FIDELITY
            conversion_profile = ADOBE_CONVERSION_PROFILE
            revision_display = ADOBE_REVISION_DISPLAY
            font_environment = self.adobe.font_environment()
            target_application = None
            target_application_version = None
        cache_key = sha256_json(
            {
                "document_sha256": document_hash,
                "render_intent": intent,
                "provider": provider,
                "font_environment": font_environment,
                "conversion_profile": conversion_profile,
                "revision_display": revision_display,
                "parent_render_sha256": (
                    parent_reference.get("render_sha256") if parent_reference else None
                ),
                "dpi": 144,
            }
        )
        existing_ref = output / "render-ref.json"
        if output.is_dir() and existing_ref.is_file():
            existing = read_json(existing_ref)
            if existing.get("cache_key") == cache_key:
                _, verified = _load_render_ref(
                    str(existing_ref), task_root=root, field="output_render_ref"
                )
                return {
                    "schema_version": 1,
                    "status": "ok",
                    "checks": [{"name": "render_cache", "result": "ok"}],
                    "warnings": list(verified.get("warnings", [])),
                    "failure": None,
                    "cache_hit": True,
                    "render_ref": verified,
                    "render_ref_path": str(existing_ref),
                    "artifacts": verified["artifacts"],
                }
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="render_output_conflict",
                message="output_dir contains different render evidence; choose a new directory.",
            )
        if output.exists():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="render_output_not_empty",
                message="output_dir already exists without a reusable render ref.",
            )

        temporary = Path(tempfile.mkdtemp(prefix=".docfit-render-", dir=output.parent))
        try:
            pages_directory = temporary / "pages"
            pages_directory.mkdir()
            warnings: list[JsonObject] = []
            pdf_final: Path | None = None
            if intent == "edit_feedback":
                html = temporary / "document.html"
                self.office.html(input_docx, html)
                html_text = html.read_text(encoding="utf-8", errors="replace")
                page_count = len(re.findall(r"\bdata-page(?:=|\b)", html_text)) or 1
                if page_count > MAX_RENDER_PAGES:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="render_page_limit_exceeded",
                        message="The approximate render exceeds the configured page limit.",
                    )
                pages = []
                for page_number in range(1, page_count + 1):
                    page = pages_directory / f"page-{page_number:04d}.png"
                    self.office.screenshot(input_docx, page=page_number, output=page)
                    pages.append(page)
                warnings.append(
                    {
                        "code": "approximate_render",
                        "kind": "fidelity",
                        "message": (
                            "OfficeCLI HTML screenshots are iteration feedback, not delivery "
                            "conversion evidence."
                        ),
                    }
                )
            else:
                pdf = temporary / "document.pdf"
                self.adobe.export_pdf(input_docx, pdf)
                pages = pdf_to_png_pages(pdf, pages_directory, dpi=144)
                pdf_final = output / "document.pdf"
                warnings.append(
                    {
                        "code": "service_managed_render_environment",
                        "kind": "fidelity",
                        "message": (
                            "Adobe PDF Services completed the official conversion, but its "
                            "font inventory and substitution details are not exposed."
                        ),
                    }
                )
            if sha256_file(input_docx) != document_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="source_document_changed",
                    message="The source document changed during rendering; evidence was discarded.",
                )
            page_entries: list[JsonObject] = []
            for page_number, page in enumerate(pages, start=1):
                metadata = image_metadata(page)
                metadata["page"] = page_number
                metadata["path"] = str(output / "pages" / page.name)
                page_entries.append(metadata)
            contact = temporary / "contact-sheet.png"
            contact_metadata = create_contact_sheet(pages, contact)
            contact_metadata["path"] = str(output / contact.name)
            layout_map: JsonObject = {
                "schema_version": 1,
                "pages": [
                    {
                        "page": entry["page"],
                        "coordinate_space": {
                            "unit": "px",
                            "origin": "top_left",
                            "width": entry["width"],
                            "height": entry["height"],
                            "dpi": 144,
                        },
                        "elements": [],
                    }
                    for entry in page_entries
                ],
                "mapping_quality": "unavailable",
            }
            mapped_count = 0
            if intent == "edit_feedback" and focused_objects:
                measured = {str(item["path"]): item for item in measure_html_layout(html)}
                layout_pages = layout_map["pages"]
                assert isinstance(layout_pages, list)
                for focused, html_path in focused_objects:
                    measurement = measured.get(html_path or "")
                    if measurement is None:
                        continue
                    measured_page = measurement.get("page")
                    if not isinstance(measured_page, int) or not 1 <= measured_page <= len(
                        layout_pages
                    ):
                        continue
                    page_record = layout_pages[measured_page - 1]
                    assert isinstance(page_record, dict)
                    page_elements = page_record["elements"]
                    assert isinstance(page_elements, list)
                    page_elements.append(
                        {
                            "object_ref": focused.object_ref,
                            "type": focused.kind,
                            "bbox": measurement["bbox"],
                            "mapping_quality": "approximate",
                            "source": "officecli_html_dom",
                        }
                    )
                    mapped_count += 1
                if mapped_count:
                    layout_map["mapping_quality"] = "approximate"
            if intent == "edit_feedback" and mapped_count < len(focused_objects):
                warnings.append(
                    {
                        "code": "layout_mapping_unavailable",
                        "kind": "capability",
                        "message": (
                            "OfficeCLI supplied page pixels but one or more requested object "
                            "bbox mappings were unavailable."
                        ),
                    }
                )
            if intent != "edit_feedback" and focused_objects:
                warnings.append(
                    {
                        "code": "layout_mapping_unavailable",
                        "kind": "capability",
                        "message": (
                            "The Adobe PDF Services route does not expose reliable object bbox "
                            "mapping; use text anchors or current object refs."
                        ),
                    }
                )
            layout_path = temporary / "layout-map.json"
            artifacts: JsonObject = {
                "pdf": str(pdf_final) if pdf_final else None,
                "pages": page_entries,
                "pages_directory": str(output / "pages"),
                "contact_sheet": contact_metadata,
                "layout_map": str(output / "layout-map.json"),
            }
            render_basis = {
                "document_sha256": document_hash,
                "render_intent": intent,
                "fidelity": fidelity,
                "target_application": target_application,
                "target_application_version": target_application_version,
                "provider": provider,
                "font_environment": font_environment,
                "conversion_profile": conversion_profile,
                "revision_display": revision_display,
                "parent_render_ref": parent_identity,
                "page_count": len(page_entries),
                "dpi": 144,
                "page_hashes": [entry["sha256"] for entry in page_entries],
            }
            render_sha256 = sha256_json(render_basis)
            layout_map["render_sha256"] = render_sha256
            atomic_write_json(layout_path, layout_map)
            reference: JsonObject = {
                "schema_version": 1,
                "document_path": str(input_docx),
                "document_sha256": document_hash,
                "render_sha256": render_sha256,
                "render_intent": intent,
                "fidelity": fidelity,
                "target_application": target_application,
                "target_application_version": target_application_version,
                "provider": provider,
                "font_environment": font_environment,
                "font_substitutions": font_environment["substitutions"],
                "conversion_profile": conversion_profile,
                "revision_display": revision_display,
                "parent_render_ref": parent_identity,
                "page_count": len(page_entries),
                "dpi": 144,
                "cache_key": cache_key,
                "artifacts": artifacts,
                "warnings": warnings,
            }
            atomic_write_json(temporary / "render-ref.json", reference)
            os.replace(temporary, output)
            return {
                "schema_version": 1,
                "status": "ok",
                "checks": [
                    {"name": "source_unchanged", "result": "ok"},
                    {"name": "all_pages_present", "result": "ok"},
                    {"name": "render_evidence_bound", "result": "ok"},
                ],
                "warnings": warnings,
                "failure": None,
                "cache_hit": False,
                "render_ref": reference,
                "render_ref_path": str(output / "render-ref.json"),
                "artifacts": artifacts,
            }
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def visual_review(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        root = task_root_from_args(args)
        _, reference = _load_render_ref(args.get("render_ref"), task_root=root, field="render_ref")
        mode = args.get("mode", "pages")
        if mode not in VISUAL_MODES:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_visual_mode",
                message="Visual review mode must be pages, crops, contact_sheet, or compare.",
            )
        page_paths = _page_paths(reference, task_root=root)
        images: list[Path] = []
        evidence: list[JsonObject] = []
        if mode == "contact_sheet":
            artifacts = reference["artifacts"]
            assert isinstance(artifacts, dict)
            contact = artifacts.get("contact_sheet")
            contact_path_value = contact.get("path") if isinstance(contact, dict) else None
            contact_path = authorized_path(
                contact_path_value,
                task_root=root,
                field="contact_sheet",
            )
            images.append(contact_path)
            evidence.append(
                {
                    "evidence_ref": f"visual-{sha256_file(contact_path)[:24]}",
                    "view": "contact_sheet",
                    "image_sha256": sha256_file(contact_path),
                    "pages": list(range(1, len(page_paths) + 1)),
                    "candidate_object_refs": [],
                }
            )
        elif mode == "pages":
            requested = args.get("pages")
            if (
                not isinstance(requested, list)
                or not requested
                or not all(isinstance(value, int) for value in requested)
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_review_pages",
                    message="pages mode requires a non-empty array of page numbers.",
                )
            for page_number in requested:
                if not 1 <= page_number <= len(page_paths):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="review_page_out_of_range",
                        message="A requested page is outside the render ref.",
                    )
                page = page_paths[page_number - 1]
                images.append(page)
                evidence_identity = {
                    "render": reference["render_sha256"],
                    "page": page_number,
                }
                evidence.append(
                    {
                        "evidence_ref": f"visual-{sha256_json(evidence_identity)[:24]}",
                        "page": page_number,
                        "view": "full_page",
                        "image_sha256": sha256_file(page),
                        "candidate_object_refs": [],
                    }
                )
        elif mode == "crops":
            crops = args.get("crops")
            if (
                not isinstance(crops, list)
                or not crops
                or not all(isinstance(item, dict) for item in crops)
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_review_crops",
                    message="crops mode requires crop objects with page and bbox.",
                )
            derived = (
                Path(
                    _render_ref_path(args["render_ref"], task_root=root, field="render_ref")
                ).parent
                / "visual-evidence"
            )
            derived.mkdir(exist_ok=True)
            for crop in crops:
                page_number = crop.get("page")
                bbox = crop.get("bbox")
                if not isinstance(page_number, int) or not 1 <= page_number <= len(page_paths):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="crop_page_out_of_range",
                        message="A crop page is outside the render ref.",
                    )
                if not isinstance(bbox, list):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="invalid_crop_bbox",
                        message="Each crop requires a bbox array.",
                    )
                identity = sha256_json(
                    {"render": reference["render_sha256"], "page": page_number, "bbox": bbox}
                )
                output = derived / f"crop-{identity[:24]}.png"
                metadata = crop_page(page_paths[page_number - 1], bbox, output)
                images.append(output)
                evidence.append(
                    {
                        "evidence_ref": f"visual-{identity[:24]}",
                        "page": page_number,
                        "view": "crop",
                        "bbox": bbox,
                        "image_sha256": metadata["sha256"],
                        "candidate_object_refs": [],
                    }
                )
        else:
            _, baseline = _load_render_ref(
                args.get("baseline_render_ref"),
                task_root=root,
                field="baseline_render_ref",
            )
            comparable_fields = ("dpi", "fidelity", "render_intent", "font_environment")
            provider_fields = ("name", "version")
            providers_match = all(
                isinstance(reference.get("provider"), dict)
                and isinstance(baseline.get("provider"), dict)
                and reference["provider"].get(field) == baseline["provider"].get(field)
                for field in provider_fields
            )
            if not providers_match or any(
                reference.get(field) != baseline.get(field) for field in comparable_fields
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="incomparable_render_refs",
                    message=(
                        "Compare requires the same provider, version, font environment, "
                        "intent, fidelity, and DPI."
                    ),
                )
            requested = args.get("pages")
            if (
                not isinstance(requested, list)
                or not requested
                or not all(isinstance(value, int) for value in requested)
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_compare_pages",
                    message="compare mode requires a non-empty pages array.",
                )
            baseline_pages = _page_paths(baseline, task_root=root)
            derived = (
                _render_ref_path(args["render_ref"], task_root=root, field="render_ref").parent
                / "visual-evidence"
            )
            derived.mkdir(exist_ok=True)
            for page_number in requested:
                if not 1 <= page_number <= min(len(page_paths), len(baseline_pages)):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="compare_page_out_of_range",
                        message="A compare page is absent from one render ref.",
                    )
                identity = sha256_json(
                    {
                        "baseline": baseline["render_sha256"],
                        "current": reference["render_sha256"],
                        "page": page_number,
                    }
                )
                output = derived / f"compare-{identity[:24]}.png"
                metadata = compare_pages(
                    baseline_pages[page_number - 1],
                    page_paths[page_number - 1],
                    output,
                )
                images.append(output)
                evidence.append(
                    {
                        "evidence_ref": f"visual-{identity[:24]}",
                        "page": page_number,
                        "view": metadata["view"],
                        "image_sha256": metadata["sha256"],
                        "baseline_render_sha256": baseline["render_sha256"],
                        "baseline_image_sha256": sha256_file(baseline_pages[page_number - 1]),
                        "candidate_object_refs": [],
                    }
                )
        ensure_review_budget(images)
        return (
            {
                "schema_version": 1,
                "status": "ok",
                "checks": [{"name": "existing_render_only", "result": "ok"}],
                "warnings": [],
                "failure": None,
                "document_sha256": reference["document_sha256"],
                "render_sha256": reference["render_sha256"],
                "render_intent": reference["render_intent"],
                "fidelity": reference["fidelity"],
                "provider": reference["provider"],
                "font_environment": reference["font_environment"],
                "mode": mode,
                "evidence": evidence,
            },
            images,
        )

    def validate(self, args: dict[str, Any]) -> JsonObject:
        root = task_root_from_args(args)
        source = _document_path(args, "source_docx", root)
        final = _document_path(args, "final_docx", root)
        source_hash = sha256_file(source)
        final_hash = sha256_file(final)
        expected_source = args.get("source_sha256")
        if expected_source is not None and expected_source != source_hash:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_hash_mismatch",
                message="The source document no longer matches source_sha256.",
            )
        validate_docx_package(final)
        office_validation = self.office.validate(final)
        source_inspection = inspect_document(source, self.office)
        final_inspection = inspect_document(final, self.office)
        checks: list[JsonObject] = [
            {
                "name": "docx_opens",
                "result": "ok",
                "severity": "info",
                "blocking": False,
                "evidence": "Independent ZIP/XML reopen passed.",
                "suggested_action": None,
            },
            {
                "name": "officecli_openxml",
                "result": "ok",
                "severity": "info",
                "blocking": False,
                "evidence": office_validation["detail"],
                "suggested_action": None,
            },
            {
                "name": "source_unchanged",
                "result": "ok",
                "severity": "info",
                "blocking": False,
                "evidence": {"source_sha256": source_hash},
                "suggested_action": None,
            },
        ]
        source_text = [item.text for item in source_inspection.objects if item.text]
        final_text = [item.text for item in final_inspection.objects if item.text]
        missing_text = Counter(source_text) - Counter(final_text)
        if missing_text:
            checks.append(
                {
                    "name": "content_preservation",
                    "result": "issue",
                    "severity": "warning",
                    "blocking": False,
                    "evidence": {"missing_object_count": sum(missing_text.values())},
                    "suggested_action": "Review intended replacements against source content.",
                }
            )
        else:
            checks.append(
                {
                    "name": "content_preservation",
                    "result": "ok",
                    "severity": "info",
                    "blocking": False,
                    "evidence": {"source_text_objects_preserved": len(source_text)},
                    "suggested_action": None,
                }
            )
        placeholders = ("在此填写", "TODO", "{{", "XXXXX")
        placeholder_count = sum(
            text.count(marker) for text in final_text for marker in placeholders
        )
        checks.append(
            {
                "name": "placeholder_scan",
                "result": "issue" if placeholder_count else "ok",
                "severity": "error" if placeholder_count else "info",
                "blocking": bool(placeholder_count),
                "evidence": {"placeholder_occurrences": placeholder_count},
                "suggested_action": (
                    "Replace or explicitly waive every remaining placeholder."
                    if placeholder_count
                    else None
                ),
            }
        )
        warnings: list[JsonObject] = []
        visual_value = args.get("visual_review")
        candidate_value = args.get("candidate_render_ref")
        reviewed_pages: set[int] = set()
        blocking_findings = 0
        if visual_value is not None:
            visual_path = authorized_path(
                visual_value,
                task_root=root,
                field="visual_review",
            )
            visual = read_json(visual_path)
            if visual.get("document_sha256") != final_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="visual_review_document_mismatch",
                    message="visual_review is not bound to the final document snapshot.",
                )
            raw_pages = visual.get("reviewed_pages", [])
            if isinstance(raw_pages, list):
                reviewed_pages = {item for item in raw_pages if isinstance(item, int)}
            findings = visual.get("findings", [])
            if isinstance(findings, list):
                blocking_findings = sum(
                    1
                    for finding in findings
                    if isinstance(finding, dict)
                    and (finding.get("blocking") is True or finding.get("severity") == "blocking")
                )
        candidate: JsonObject | None = None
        if candidate_value is not None:
            _, candidate = _load_render_ref(
                candidate_value,
                task_root=root,
                field="candidate_render_ref",
            )
            if candidate.get("document_sha256") != final_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="candidate_document_mismatch",
                    message="candidate_render_ref is not bound to the final document snapshot.",
                )
        all_pages_covered = candidate is not None and reviewed_pages == set(
            range(1, int(candidate["page_count"]) + 1)
        )
        delivery_candidate = (
            candidate is not None
            and candidate.get("render_intent") == "candidate_verification"
            and candidate.get("fidelity") == ADOBE_FIDELITY
            and isinstance(candidate.get("provider"), dict)
            and candidate["provider"].get("name") == "adobe_pdf_services"
        )
        visual_ok = delivery_candidate and all_pages_covered and blocking_findings == 0
        checks.append(
            {
                "name": "visual_review_coverage",
                "result": "ok" if visual_ok else "warning",
                "severity": "warning" if not visual_ok else "info",
                "blocking": False,
                "evidence": {
                    "delivery_candidate": delivery_candidate,
                    "all_final_pages_reviewed": all_pages_covered,
                    "blocking_findings": blocking_findings,
                },
                "suggested_action": (
                    None
                    if visual_ok
                    else (
                        "Generate current Adobe delivery candidate evidence and review every "
                        "final page."
                    )
                ),
            }
        )
        if not visual_ok:
            warnings.append(
                {
                    "code": "verification_gap",
                    "kind": "visual_review",
                    "message": (
                        "Current Adobe delivery candidate evidence and complete Agent page "
                        "coverage are absent or incomplete."
                    ),
                }
            )
        issue_count = sum(check["result"] == "issue" for check in checks)
        warning_count = sum(check["result"] == "warning" for check in checks) + len(warnings)
        error_count = sum(check.get("blocking") is True for check in checks)
        return {
            "schema_version": 1,
            "status": "ok",
            "checks": checks,
            "warnings": warnings,
            "failure": None,
            "source_sha256": source_hash,
            "final_sha256": final_hash,
            "knowledge_version": args.get("knowledge_version"),
            "task_rule_evidence": args.get("task_rule_evidence", []),
            "summary": {
                "errors": error_count,
                "issues": issue_count,
                "warnings": warning_count,
            },
            "provider": self.office.evidence(),
        }


def image_content_blocks(paths: list[Path]) -> list[JsonObject]:
    blocks: list[JsonObject] = []
    for path in paths:
        verify_png(path)
        blocks.append(
            {
                "type": "image",
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                "mimeType": "image/png",
            }
        )
    return blocks


def tool_result(structured: JsonObject, *, image_paths: list[Path] | None = None) -> JsonObject:
    status = structured.get("status")
    content: list[JsonObject] = [
        {
            "type": "text",
            # claude-agent-sdk 0.2.128's in-process MCP bridge currently omits
            # structuredContent when it builds CallToolResult. Mirror the same
            # payload as compact text so the Agent can actually consume refs,
            # artifacts, and validation evidence without gaining file-read access.
            "text": json.dumps(
                structured,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
    ]
    if image_paths:
        content.extend(image_content_blocks(image_paths))
    result: JsonObject = {"content": content, "structuredContent": structured}
    if status == "error":
        result["is_error"] = True
    return result


def failure_result(error: ToolFailure, *, committed: bool | None = None) -> JsonObject:
    return tool_result(error.result(committed=committed))


def unexpected_failure_result(*, committed: bool | None = None) -> JsonObject:
    failure = ToolFailure(
        status="error",
        origin="adapter",
        code="unexpected_adapter_error",
        message=(
            "DocFit encountered an unexpected adapter error; no unverified output was published."
        ),
    )
    return failure_result(failure, committed=committed)

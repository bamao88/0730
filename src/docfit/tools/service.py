"""Concrete implementation of the five stable DocFit Tool contracts."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from docfit.fields import FieldRegistrySnapshot
from docfit.template.object_mutation import (
    ObjectMutation,
    StructureMember,
    TocEntry,
    mutate_objects,
)
from docfit.template.semantic_types import (
    require_body_member_type,
    require_body_structure_type,
    semantic_object_type,
)
from docfit.tools.images import verify_png
from docfit.tools.inspection import (
    Inspection,
    inspect_document,
    resolve_object_ref,
)
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
    task_root_from_args,
)
from docfit.visual.service import VisualEvidenceService

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

_DOMAIN_EDIT_ACTIONS = frozenset(
    {
        "clear_content",
        "remove_object",
        "materialize_slot",
        "materialize_structure",
        "normalize_effective_format",
        "refresh_toc",
        "ensure_page_start",
    }
)
_MAX_DOMAIN_EDIT_OPERATIONS = 32


def _required_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="domain_edit_argument_invalid",
            message=f"{field} must be a non-empty string.",
        )
    return value


def _effective_format(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or set(value) - {"color", "underline"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="effective_format_invalid",
            message="effective_format supports only color=black and underline=none.",
        )
    if value.get("color", "black") != "black" or value.get("underline", "none") != "none":
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="effective_format_invalid",
            message="effective_format supports only color=black and underline=none.",
        )
    return tuple(
        (key, str(value[key])) for key in ("color", "underline") if key in value
    )


def _slot_id(field_id: str, object_id: str, supplied: Any) -> str:
    if supplied is not None:
        return _required_string(supplied, field="slot_id")
    return f"slot.{field_id}.{object_id.removeprefix('obj-')[:10]}"


def _placeholder(field: JsonObject, supplied: Any) -> str:
    if supplied is not None:
        return _required_string(supplied, field="placeholder_text")
    return f"【{field.get('label', field['field_id'])}】"


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


def _locator_related(first: str, second: str) -> bool:
    return first == second or first.startswith(f"{second}/") or second.startswith(f"{first}/")


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


class DocFitToolService:
    """One concrete service; it owns no Agent loop or workflow state."""

    def __init__(
        self,
        *,
        task_root: Path | None = None,
        office: OfficeCliAdapter | None = None,
        visual: VisualEvidenceService | None = None,
    ) -> None:
        self._task_root = (
            task_root.expanduser().resolve(strict=True) if task_root is not None else None
        )
        self._office = office
        self._visual = visual

    def _session_root(self, args: dict[str, Any]) -> Path:
        if self._task_root is None:
            return task_root_from_args(args)
        requested = args.get("task_root")
        if requested is not None:
            candidate = task_root_from_args({"task_root": requested})
            if candidate != self._task_root:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="task_root_mismatch",
                    message="task_root does not match the root bound to this application session.",
                )
        return self._task_root

    @property
    def office(self) -> OfficeCliAdapter:
        if self._office is None:
            self._office = OfficeCliAdapter()
        return self._office

    def visual(self) -> VisualEvidenceService:
        if self._visual is None:
            root = self._task_root or task_root_from_args({})
            self._visual = VisualEvidenceService(root, office=self._office)
        return self._visual

    def inspect(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
        document = _document_path(args, "input_docx", root)
        # The stable inspection surface is the complete queryable inventory.
        # The Agent may progressively focus its own attention; the application
        # does not choose a semantic crop on its behalf.
        inspection = inspect_document(
            document,
            self.office,
            selector="paragraph, table, picture, run, sdt, shape",
        )
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

    def _domain_mutations(
        self,
        *,
        args: dict[str, Any],
        root: Path,
        inspection: Inspection,
        operations: list[JsonObject],
    ) -> tuple[list[ObjectMutation], list[JsonObject]]:
        if len(operations) > _MAX_DOMAIN_EDIT_OPERATIONS:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="too_many_domain_edit_operations",
                message="One atomic docx_edit batch supports at most 32 domain operations.",
            )
        registry: FieldRegistrySnapshot | None = None
        if any(
            item.get("action") in {"materialize_slot", "materialize_structure"}
            for item in operations
        ):
            registry_path = authorized_path(
                args.get("field_registry"),
                task_root=root,
                field="field_registry",
            )
            registry = FieldRegistrySnapshot.load(registry_path)

        mutations: list[ObjectMutation] = []
        public_operations: list[JsonObject] = []
        for operation in operations:
            action = str(operation.get("action"))
            selected = resolve_object_ref(operation.get("target_ref"), inspection)
            field: JsonObject | None = None
            field_id: str | None = None
            slot_id: str | None = None
            placeholder_text: str | None = None
            members: list[StructureMember] = []
            public_members: list[JsonObject] = []
            replaced_structure = None
            toc_entries: list[TocEntry] = []
            public_entries: list[JsonObject] = []
            effective_format = _effective_format(operation.get("effective_format"))

            if action == "materialize_slot":
                assert registry is not None
                field_id = _required_string(operation.get("field_id"), field="field_id")
                semantic = semantic_object_type(field_id)
                if semantic is not None:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="structured_field_requires_structure",
                        message=(
                            "Body semantic fields are members of a reusable structure; use "
                            "materialize_structure with Agent-selected representatives."
                        ),
                    )
                field = registry.lookup(field_id)
                slot_id = _slot_id(
                    field_id,
                    str(selected.object_ref["object_id"]),
                    operation.get("slot_id"),
                )
                placeholder_text = _placeholder(field, operation.get("placeholder_text"))
            elif action == "materialize_structure":
                assert registry is not None
                field_id = _required_string(
                    operation.get("field_id", "body.chapters"), field="field_id"
                )
                require_body_structure_type(field_id)
                field = registry.lookup(field_id)
                slot_id = _slot_id(
                    field_id,
                    str(selected.object_ref["object_id"]),
                    operation.get("slot_id"),
                )
                raw_members = operation.get("members")
                if not isinstance(raw_members, list) or not raw_members:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="body_structure_members_invalid",
                        message="materialize_structure requires Agent-selected ordered members.",
                    )
                for raw_member in raw_members:
                    if not isinstance(raw_member, dict):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="body_structure_members_invalid",
                            message="Every structure member must be an object.",
                        )
                    member_selected = resolve_object_ref(
                        raw_member.get("target_ref"), inspection
                    )
                    member_field_id = _required_string(
                        raw_member.get("field_id"), field="members[].field_id"
                    )
                    require_body_member_type(member_field_id, member_selected.kind)
                    member_field = registry.lookup(member_field_id)
                    member_slot_id = _slot_id(
                        member_field_id,
                        str(member_selected.object_ref["object_id"]),
                        raw_member.get("slot_id"),
                    )
                    member_placeholder = _placeholder(
                        member_field, raw_member.get("placeholder_text")
                    )
                    members.append(
                        StructureMember(
                            selected=member_selected,
                            field_id=member_field_id,
                            slot_id=member_slot_id,
                            content_type=str(member_field.get("content_type", "text")),
                            placeholder_text=member_placeholder,
                            effective_format=_effective_format(
                                raw_member.get("effective_format")
                            ),
                        )
                    )
                    public_members.append(
                        {
                            "field_id": member_field_id,
                            "slot_id": member_slot_id,
                            "target_ref": member_selected.object_ref,
                        }
                    )
                raw_replaced = operation.get("replaced_structure_ref")
                if raw_replaced is not None:
                    replaced_structure = resolve_object_ref(raw_replaced, inspection)
            elif action == "refresh_toc":
                raw_entries = operation.get("toc_entries")
                if not isinstance(raw_entries, list) or not raw_entries:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="toc_entries_invalid",
                        message="refresh_toc requires Agent-selected source titles and levels.",
                    )
                for raw_entry in raw_entries:
                    if not isinstance(raw_entry, dict):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="toc_entries_invalid",
                            message="Every TOC entry must be an object.",
                        )
                    entry_selected = resolve_object_ref(
                        raw_entry.get("target_ref"), inspection
                    )
                    level = raw_entry.get("level")
                    if (
                        not isinstance(level, int)
                        or isinstance(level, bool)
                        or level not in {1, 2, 3}
                    ):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="toc_entry_level_invalid",
                            message="Each TOC source title needs level 1, 2, or 3.",
                        )
                    toc_entries.append(TocEntry(entry_selected, level))
                    public_entries.append(
                        {"target_ref": entry_selected.object_ref, "level": level}
                    )
            elif action == "ensure_page_start" and operation.get("mode") != "new_page":
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="page_start_mode_invalid",
                    message="ensure_page_start requires mode=new_page.",
                )

            mutation = ObjectMutation(
                selected=selected,
                action=action,
                field_id=field_id,
                slot_id=slot_id,
                content_type=str(field.get("content_type", "text")) if field else "text",
                placeholder_text=placeholder_text,
                effective_format=effective_format,
                structure_members=tuple(members),
                replaced_structure=replaced_structure,
                toc_entries=tuple(toc_entries),
            )
            mutations.append(mutation)
            public_operations.append(
                {
                    "action": action,
                    "target_ref": selected.object_ref,
                    **({"field_id": field_id} if field_id else {}),
                    **({"slot_id": slot_id} if slot_id else {}),
                    **({"members": public_members} if public_members else {}),
                    **({"toc_entries": public_entries} if public_entries else {}),
                }
            )
        return mutations, public_operations

    def _edit_domain(
        self,
        *,
        args: dict[str, Any],
        root: Path,
        input_docx: Path,
        output_docx: Path,
        inspection: Inspection,
        operations: list[JsonObject],
    ) -> JsonObject:
        mutations, public_operations = self._domain_mutations(
            args=args,
            root=root,
            inspection=inspection,
            operations=operations,
        )
        source_hash = inspection.document_sha256
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".docfit-domain-edit-",
            suffix=".docx",
            dir=output_docx.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            effects = mutate_objects(input_docx, temporary, mutations=mutations)
            validate_docx_package(temporary)
            office_validation = self.office.validate(temporary)
            after = inspect_document(
                temporary,
                self.office,
                selector="paragraph, table, picture, run, sdt, shape",
            )
            if sha256_file(input_docx) != source_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="source_document_changed",
                    message="The immutable input changed; the edit was not published.",
                )
            output_hash = after.document_sha256
            os.replace(temporary, output_docx)
            return {
                "schema_version": 1,
                "status": "ok",
                "committed": True,
                "checks": [
                    {"name": "object_refs_bound", "result": "ok"},
                    {"name": "source_unchanged", "result": "ok", "sha256": source_hash},
                    {"name": "package_reopens", "result": "ok"},
                    {"name": "officecli_validate", "result": "ok", **office_validation},
                    {"name": "effects_re_read", "result": "ok"},
                ],
                "warnings": [],
                "failure": None,
                "input_sha256": source_hash,
                "output_sha256": output_hash,
                "output_docx": str(output_docx),
                "operations": [
                    {"index": index, **operation, "result": "applied"}
                    for index, operation in enumerate(public_operations)
                ],
                "effects": effects,
                "provider": self.office.evidence(),
            }
        finally:
            temporary.unlink(missing_ok=True)

    def edit(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
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
        inspection = inspect_document(
            input_docx,
            self.office,
            selector="paragraph, table, picture, run, sdt, shape",
        )
        domain_actions = [
            str(operation.get("action")) in _DOMAIN_EDIT_ACTIONS for operation in operations
        ]
        if any(domain_actions):
            if not all(domain_actions):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="mixed_edit_families",
                    message=(
                        "Keep direct template mutations and OfficeCLI/import edits in separate "
                        "atomic docx_edit calls so every snapshot has unambiguous refs."
                    ),
                )
            return self._edit_domain(
                args=args,
                root=root,
                input_docx=input_docx,
                output_docx=output_docx,
                inspection=inspection,
                operations=operations,
            )
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
            source_inspection = inspect_document(
                source_docx,
                self.office,
                selector="paragraph, table, picture, run, sdt, shape",
            )
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
            after = inspect_document(
                temporary,
                self.office,
                selector="paragraph, table, picture, run, sdt, shape",
            )
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
                if item.text
                and not any(
                    _locator_related(item.locator, changed) for changed in changed_locators
                )
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

    def render(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        return self.visual().render(args)

    def visual_review(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        return self.visual().review(args)

    def validate(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
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
            if isinstance(visual_value, str):
                visual_path = authorized_path(
                    visual_value,
                    task_root=root,
                    field="visual_review",
                )
                visual = read_json(visual_path)
            elif isinstance(visual_value, dict):
                visual = dict(visual_value)
            else:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="visual_review_invalid",
                    message="visual_review must be a task-local JSON path or an evidence object.",
                )
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
            _, candidate = self.visual().store.resolve_render(candidate_value)
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
        current_visual_snapshot = (
            candidate is not None
            and candidate.get("fidelity") == "approximate"
            and isinstance(candidate.get("renderer"), dict)
            and candidate["renderer"].get("name") == "libreoffice"
        )
        visual_ok = current_visual_snapshot and all_pages_covered and blocking_findings == 0
        visual_required = args.get("required_visual_coverage") == "all_final_pages"
        checks.append(
            {
                "name": "visual_review_coverage",
                "result": "ok" if visual_ok else ("issue" if visual_required else "warning"),
                "severity": (
                    "error"
                    if visual_required and not visual_ok
                    else "warning"
                    if not visual_ok
                    else "info"
                ),
                "blocking": visual_required and not visual_ok,
                "evidence": {
                    "current_visual_snapshot": current_visual_snapshot,
                    "all_final_pages_reviewed": all_pages_covered,
                    "blocking_findings": blocking_findings,
                },
                "suggested_action": (
                    None
                    if visual_ok
                    else "Render the current final DOCX and review every final page."
                ),
            }
        )
        if not visual_ok:
            warnings.append(
                {
                    "code": "verification_gap",
                    "kind": "visual_review",
                    "message": (
                        "Current LibreOffice render evidence and complete Agent page coverage "
                        "are absent or incomplete."
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

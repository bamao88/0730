from __future__ import annotations

from pathlib import Path
from typing import Any

from docfit.tools import (
    DOCFIT_GENERAL_FULL_TOOL_NAMES,
    DOCFIT_GENERAL_READ_ONLY_FULL_TOOL_NAMES,
    DOCFIT_GENERAL_READ_ONLY_TOOL_NAMES,
    DOCFIT_GENERAL_SUBAGENT_FULL_TOOL_NAMES,
    DOCFIT_GENERAL_SUBAGENT_TOOL_NAMES,
    DOCFIT_GENERAL_TOOL_NAMES,
    DOCFIT_GENERAL_WRITE_FULL_TOOL_NAMES,
    DOCFIT_GENERAL_WRITE_TOOL_NAMES,
    DOCFIT_TOOL_SURFACE,
    DOCX_TOOL_ADAPTERS,
    TEMPLATE_RUNTIME_AGENT_TOOL_NAMES,
    TEMPLATE_RUNTIME_FULL_AGENT_TOOL_NAMES,
    TOOL_FAILURE_CODES,
    TOOL_SURFACE_VERSION,
    _audit_input,
    build_docfit_tools,
)
from docfit.tools.runtime import ToolFailure
from docfit.tools.service import DocFitToolService
from docfit.tools.surface import (
    CHECK_KINDS,
    DOCFIT_APPLY_INPUT_V1,
    DOCFIT_APPLY_SCHEMA,
    DOCFIT_APPLY_TOOL,
    DOCFIT_CHECK_INPUT_V1,
    DOCFIT_CHECK_SCHEMA,
    DOCFIT_CHECK_TOOL,
    DOCFIT_EVIDENCE_INPUT_V1,
    DOCFIT_EVIDENCE_SCHEMA,
    DOCFIT_EVIDENCE_TOOL,
    DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA,
    EVIDENCE_FOCUS,
    SUBAGENT_CHECK_KINDS,
    TEMPLATE_SEMANTIC_EVIDENCE_FOCUS,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_COMPOSITION_KEYWORDS = {"oneOf", "anyOf", "allOf"}


def _nested_values(value: object) -> list[object]:
    if isinstance(value, dict):
        return [value, *(child for item in value.values() for child in _nested_values(item))]
    if isinstance(value, list):
        return [child for item in value for child in _nested_values(item)]
    return []


def _assert_flat_versioned_schema(
    schema: dict[str, Any],
    *,
    schema_version: str,
    discriminator: str,
) -> None:
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"] == {"const": schema_version}
    assert "schema_version" in schema["required"]
    assert discriminator in schema["required"]
    assert all(
        not _COMPOSITION_KEYWORDS.intersection(item)
        for item in _nested_values(schema)
        if isinstance(item, dict)
    )
    for name, property_schema in schema["properties"].items():
        if name in {"reviewed_pages", "payload"}:
            continue
        assert property_schema.get("type") != "object"


def test_p2_freezes_general_docfit_tool_facade_and_template_runtime_profile() -> None:
    assert TOOL_SURFACE_VERSION == "docfit-tool-surface/v1"
    assert DOCFIT_GENERAL_TOOL_NAMES == (
        DOCFIT_EVIDENCE_TOOL,
        DOCFIT_CHECK_TOOL,
        DOCFIT_APPLY_TOOL,
    )
    assert DOCFIT_GENERAL_FULL_TOOL_NAMES == (
        "mcp__docfit__docfit_evidence",
        "mcp__docfit__docfit_check",
        "mcp__docfit__docfit_apply",
    )
    assert TEMPLATE_RUNTIME_AGENT_TOOL_NAMES == (DOCFIT_EVIDENCE_TOOL,)
    assert TEMPLATE_RUNTIME_FULL_AGENT_TOOL_NAMES == ("mcp__docfit__docfit_evidence",)
    assert tuple(entry["name"] for entry in DOCFIT_TOOL_SURFACE) == DOCFIT_GENERAL_TOOL_NAMES
    assert all(not name.startswith("docx_") for name in DOCFIT_GENERAL_TOOL_NAMES)
    assert DOCX_TOOL_ADAPTERS == {
        DOCFIT_EVIDENCE_TOOL: ("docx_inspect", "docx_render", "docx_visual_review"),
        DOCFIT_CHECK_TOOL: ("docx_validate",),
        DOCFIT_APPLY_TOOL: ("docx_edit",),
    }


def test_p2_schema_envelopes_are_versioned_flat_and_provider_free() -> None:
    _assert_flat_versioned_schema(
        DOCFIT_EVIDENCE_SCHEMA,
        schema_version=DOCFIT_EVIDENCE_INPUT_V1,
        discriminator="focus",
    )
    _assert_flat_versioned_schema(
        DOCFIT_CHECK_SCHEMA,
        schema_version=DOCFIT_CHECK_INPUT_V1,
        discriminator="check",
    )
    _assert_flat_versioned_schema(
        DOCFIT_APPLY_SCHEMA,
        schema_version=DOCFIT_APPLY_INPUT_V1,
        discriminator="batch_ref",
    )
    assert DOCFIT_EVIDENCE_SCHEMA["properties"]["focus"]["enum"] == list(EVIDENCE_FOCUS)
    assert "unit_slice" not in EVIDENCE_FOCUS
    assert "semantic_field" not in DOCFIT_EVIDENCE_SCHEMA["properties"]
    assert "query" not in DOCFIT_EVIDENCE_SCHEMA["properties"]
    assert "scope_ref" not in DOCFIT_EVIDENCE_SCHEMA["properties"]
    assert DOCFIT_EVIDENCE_SCHEMA["properties"]["offset"] == {
        "type": "integer",
        "minimum": 0,
        "description": (
            "Object-window offset for paginated document_map evidence; "
            "use summary.object_window.next_offset from the previous evidence card."
        ),
    }
    assert DOCFIT_CHECK_SCHEMA["properties"]["check"]["enum"] == list(CHECK_KINDS)
    assert DOCFIT_CHECK_SCHEMA["properties"]["payload"]["type"] == "object"
    assert "do not pass a top-level array" in str(
        DOCFIT_CHECK_SCHEMA["properties"]["payload"]["description"]
    )
    assert "registry_binding" not in DOCFIT_CHECK_SCHEMA["properties"]["check"]["enum"]
    assert "field_id" not in DOCFIT_CHECK_SCHEMA["properties"]
    assert "scope_ref" not in DOCFIT_CHECK_SCHEMA["properties"]
    assert "action_plan" not in DOCFIT_CHECK_SCHEMA["properties"]["check"]["enum"]
    assert "judgment_shape" not in DOCFIT_CHECK_SCHEMA["properties"]["check"]["enum"]
    assert "coverage_closure" not in DOCFIT_CHECK_SCHEMA["properties"]["check"]["enum"]
    assert "closure_aggregation" not in DOCFIT_CHECK_SCHEMA["properties"]["check"]["enum"]
    assert "action_plan" not in str(DOCFIT_CHECK_SCHEMA["properties"]["payload"])
    assert "action_requirement" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "slot_id" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "field_id" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "slot_ref" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "replacement_text" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "style_contract_ref" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "evidence_ref" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "target_ref" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "target_ref" not in DOCFIT_APPLY_SCHEMA["required"]
    assert "operation" not in DOCFIT_APPLY_SCHEMA["properties"]
    assert "operation" not in DOCFIT_APPLY_SCHEMA["required"]
    assert "batch_ref" in DOCFIT_APPLY_SCHEMA["properties"]
    assert "batch_ref" in DOCFIT_APPLY_SCHEMA["required"]
    for retired_operation in (
        "bind_field",
        "replace_instruction",
        "remove_sample",
        "refresh_generated",
        "preserve_layout",
        "apply_style_fact",
    ):
        assert retired_operation not in str(DOCFIT_APPLY_SCHEMA)
    for schema in (DOCFIT_EVIDENCE_SCHEMA, DOCFIT_CHECK_SCHEMA, DOCFIT_APPLY_SCHEMA):
        assert "source_hash" not in schema["properties"]
        assert "source_hash" not in schema["required"]

    surface_source = (_PROJECT_ROOT / "src/docfit/tools/surface.py").read_text(
        encoding="utf-8"
    )
    assert all(
        token not in surface_source
        for token in (
            "docfit.tools.service",
            "docfit.tools.officecli",
            "docfit.tools.inspection",
            "docfit.tools.edit_actions",
            "LibreOffice",
            "OfficeCLI",
        )
    )


def test_template_semantic_tool_profile_exposes_only_readable_context(
    tmp_path: Path,
) -> None:
    tools = build_docfit_tools(
        tmp_path,
        include_docx_tools=False,
        template_semantic_only=True,
    )

    assert [tool.name for tool in tools] == [DOCFIT_EVIDENCE_TOOL]
    schema = tools[0].input_schema
    assert schema == DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA
    assert schema["properties"]["focus"]["enum"] == list(
        TEMPLATE_SEMANTIC_EVIDENCE_FOCUS
    )
    assert "unit_slice" not in schema["properties"]["focus"]["enum"]
    forbidden = {
        "candidate_hash",
        "object_ref",
        "target_ref",
        "render_ref",
        "evidence_ref",
        "reviewed_pages",
        "scope_ref",
        "task_root",
    }
    assert forbidden.isdisjoint(schema["properties"])


def test_template_tool_services_explicitly_reject_legacy_lookup_and_source_overrides(
    tmp_path: Path,
) -> None:
    service = DocFitToolService(task_root=tmp_path)
    cases = (
        (service.evidence, {"focus": "document_map"}),
        (service.check, {"check": "unit_coverage", "payload": {}}),
    )
    retired_fields = (
        "semantic_field",
        "query",
        "registry_field",
        "field_id",
        "target_ref",
        "locator",
        "paragraph",
        "paragraph_index",
        "scope_ref",
        "source_entry_id",
        "span_ref",
        "slot_ref",
        "reading_block_id",
        "reading_range_id",
        "range_id",
    )

    for call, base_args in cases:
        for retired_field in retired_fields:
            try:
                call({**base_args, retired_field: "legacy-value"})
            except ToolFailure as failure:
                assert failure.code == "schema_envelope_invalid"
                assert retired_field in failure.message
            else:
                raise AssertionError(f"{retired_field} was not explicitly rejected")


def test_p2_read_write_and_subagent_boundaries_are_visible() -> None:
    surface = {entry["name"]: entry for entry in DOCFIT_TOOL_SURFACE}

    assert DOCFIT_GENERAL_READ_ONLY_TOOL_NAMES == (DOCFIT_EVIDENCE_TOOL, DOCFIT_CHECK_TOOL)
    assert DOCFIT_GENERAL_WRITE_TOOL_NAMES == (DOCFIT_APPLY_TOOL,)
    assert DOCFIT_GENERAL_SUBAGENT_TOOL_NAMES == (DOCFIT_EVIDENCE_TOOL, DOCFIT_CHECK_TOOL)
    assert DOCFIT_GENERAL_READ_ONLY_FULL_TOOL_NAMES == (
        "mcp__docfit__docfit_evidence",
        "mcp__docfit__docfit_check",
    )
    assert DOCFIT_GENERAL_WRITE_FULL_TOOL_NAMES == ("mcp__docfit__docfit_apply",)
    assert DOCFIT_GENERAL_SUBAGENT_FULL_TOOL_NAMES == (
        "mcp__docfit__docfit_evidence",
        "mcp__docfit__docfit_check",
    )
    assert surface[DOCFIT_EVIDENCE_TOOL]["read_only"] is True
    assert surface[DOCFIT_CHECK_TOOL]["read_only"] is True
    assert surface[DOCFIT_APPLY_TOOL]["read_only"] is False
    assert surface[DOCFIT_APPLY_TOOL]["subagent_allowed"] is False
    assert tuple(surface[DOCFIT_CHECK_TOOL]["subagent_check_kinds"]) == SUBAGENT_CHECK_KINDS
    assert "publication_readiness" not in SUBAGENT_CHECK_KINDS


def test_p2_failure_codes_cover_front_contract_failures() -> None:
    assert {
        "stale_ref",
        "scope_violation",
        "target_ambiguity",
        "style_evidence_insufficient",
        "schema_envelope_invalid",
        "hash_binding_mismatch",
        "visual_coverage_incomplete",
        "unit_slice_runtime_removed",
        "unit_evidence_packet_unit_missing",
        "unit_evidence_packet_range_missing",
        "registry_field_runtime_removed",
        "phase_review_required",
        "write_operation_denied",
        "provider_failure",
    } == set(TOOL_FAILURE_CODES)
    for entry in DOCFIT_TOOL_SURFACE:
        assert entry["failure_codes"] == TOOL_FAILURE_CODES


def test_p2_tool_audit_records_evidence_pagination_offset() -> None:
    assert _audit_input(
        {
            "schema_version": DOCFIT_EVIDENCE_INPUT_V1,
            "focus": "document_map",
            "scope_ref": "/body/p[1]",
            "offset": 200,
            "limit": 200,
        }
    ) == {
        "schema_version": DOCFIT_EVIDENCE_INPUT_V1,
        "focus": "document_map",
        "offset": 200,
        "limit": 200,
    }


def test_p2_tool_audit_drops_removed_registry_semantic_field() -> None:
    assert _audit_input(
        {
            "schema_version": DOCFIT_EVIDENCE_INPUT_V1,
            "focus": "registry_field",
            "semantic_field": "author Chinese name",
            "field_id": "author.name.zh",
        }
    ) == {
        "schema_version": DOCFIT_EVIDENCE_INPUT_V1,
        "focus": "registry_field",
    }


def test_p2_tool_audit_does_not_recognize_legacy_judgments_alias() -> None:
    assert _audit_input(
        {
            "schema_version": DOCFIT_CHECK_INPUT_V1,
            "check": "unit_coverage",
            "payload": {"judgments": [{"judgment": "legacy"}]},
        }
    ) == {
        "schema_version": DOCFIT_CHECK_INPUT_V1,
        "check": "unit_coverage",
    }


def test_p2_tool_audit_drops_removed_direct_apply_mutation_fields() -> None:
    assert _audit_input(
        {
            "schema_version": DOCFIT_APPLY_INPUT_V1,
            "candidate_hash": "a" * 64,
            "target_ref": "object_ref:not-json",
            "batch_ref": "work/action.json",
            "replacement_text": "legacy direct mutation",
        }
    ) == {
        "schema_version": DOCFIT_APPLY_INPUT_V1,
        "candidate_hash": "a" * 64,
        "batch_ref": "work/action.json",
    }


def test_p2_tool_audit_records_non_object_payload_shape_only() -> None:
    assert _audit_input(
        {
            "schema_version": DOCFIT_CHECK_INPUT_V1,
            "candidate_hash": "a" * 64,
            "check": "unit_coverage",
            "payload": [{"semantic_judgments": []}],
        }
    ) == {
        "schema_version": DOCFIT_CHECK_INPUT_V1,
        "candidate_hash": "a" * 64,
        "check": "unit_coverage",
        "payload_kind": "list",
        "payload_item_count": 1,
    }

from __future__ import annotations

from pathlib import Path

from docfit.app.prepare_template import (
    POST_UNIT_OUTPUT_SCHEMA,
    PREPARE_TEMPLATE_OUTPUT_SCHEMA,
    PreparedTemplateTask,
    _agent_visible_feedback_packet,
    _failure_evidence,
    _semantic_coverage_feedback,
    _semantic_feedback_failure_actions,
    build_prepare_template_prompt,
    build_unit_boundary_checkpoint_prompt,
)
from docfit.tools.runtime import ToolFailure

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_AGENT_VISIBLE_TOKENS = (
    "candidate_hash",
    "render_ref",
    "source_content_id",
    "source_object_id",
    "source_object_ids",
    "source_object_ref",
    "source_entry_ref",
    "object_ref",
    "object_id",
    "object_ids",
    "covered_object_ids",
    "target_ref",
    "locator",
    "span_ref",
    "slot_ref",
    "coverage",
    "publish",
    "checkpoint_backend",
    "task_root",
    "stale_ref",
    "fingerprint",
)
_ALLOWED_SEMANTIC_JUDGMENT_FIELDS = {
    "source_entry_id",
    "parts",
    "open_questions",
    "reason",
}


def _semantic_judgment_item(schema: dict[str, object]) -> dict[str, object]:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    semantic_judgments = properties["semantic_judgments"]
    assert isinstance(semantic_judgments, dict)
    items = semantic_judgments["items"]
    assert isinstance(items, dict)
    return items


def _semantic_judgment_properties(schema: dict[str, object]) -> set[str]:
    properties = _semantic_judgment_item(schema)["properties"]
    assert isinstance(properties, dict)
    return set(properties)


def _prepared(tmp_path: Path) -> PreparedTemplateTask:
    template = tmp_path / "input/school-template.docx"
    registry = tmp_path / "input/field-registry.yaml"
    requirements = tmp_path / "input/school-requirements.pdf"
    template.parent.mkdir(parents=True)
    template.write_bytes(b"template")
    registry.write_text("fields: []\n", encoding="utf-8")
    requirements.write_bytes(b"%PDF-1.4\n")
    return PreparedTemplateTask(
        task_root=tmp_path,
        template_path=template,
        requirements_path=requirements,
        registry_source=registry,
        template_sha256="a" * 64,
        requirements_sha256="c" * 64,
        registry_sha256="b" * 64,
    )


def _checkpoint(prepared: PreparedTemplateTask) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ok",
        "checkpoint": "unit-boundary",
        "source_hash": prepared.template_sha256,
        "summary": "Accepted one unit.",
        "unit_count": 1,
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_locator": "/body/p[1]",
                "end_locator": "/body/p[2]",
                "covered_object_ids": ["r-title", "r-signature"],
            }
        ],
    }


def test_post_unit_semantic_schema_exposes_only_semantic_work_surface() -> None:
    for schema in (PREPARE_TEMPLATE_OUTPUT_SCHEMA, POST_UNIT_OUTPUT_SCHEMA):
        item = _semantic_judgment_item(schema)
        schema_properties = item["properties"]
        assert isinstance(schema_properties, dict)
        properties = set(schema_properties)

        assert item["additionalProperties"] is False
        assert properties == _ALLOWED_SEMANTIC_JUDGMENT_FIELDS
        assert not properties.intersection(_FORBIDDEN_AGENT_VISIBLE_TOKENS)
        assert set(item["required"]) == {"source_entry_id", "parts"}
        assert "oneOf" not in item
        parts = schema_properties["parts"]
        assert isinstance(parts, dict)
        part_items = parts["items"]
        assert isinstance(part_items, dict)
        part_required = part_items["required"]
        assert isinstance(part_required, list)
        assert set(part_required) == {"role"}
        part_properties = part_items["properties"]
        assert isinstance(part_properties, dict)
        assert set(part_properties) == {
            "text", "whitespace", "leading_whitespace", "trailing_whitespace",
            "whole_entry", "role", "field_id"
        }
        whitespace = part_properties["whitespace"]
        assert isinstance(whitespace, dict)
        assert whitespace["additionalProperties"] is False
        assert set(whitespace["required"]) == {"codepoint", "count"}
        whitespace_properties = whitespace["properties"]
        assert isinstance(whitespace_properties, dict)
        assert set(whitespace_properties) == {"codepoint", "count"}
        role = part_properties["role"]
        assert isinstance(role, dict)
        assert set(role["enum"]) == {
            "fixed_label",
            "fill_slot",
            "body_structure",
            "generated_content",
            "manual_region",
            "style_only",
            "cleanup",
        }


def test_boundary_prompts_do_not_name_internal_bookkeeping_terms(tmp_path: Path) -> None:
    prepared = _prepared(tmp_path)
    prompts = (
        build_unit_boundary_checkpoint_prompt(prepared),
        build_prepare_template_prompt(
            prepared,
            _checkpoint(prepared),
            stop_after_post_unit=True,
        ),
    )

    for prompt in prompts:
        for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
            assert token not in prompt


def test_semantic_schema_guidance_stays_on_the_text_annotation_surface() -> None:
    for schema in (PREPARE_TEMPLATE_OUTPUT_SCHEMA, POST_UNIT_OUTPUT_SCHEMA):
        parts = _semantic_judgment_item(schema)["properties"]["parts"]
        nodes = [parts, *parts["items"]["properties"].values()]
        for node in nodes:
            description = node.get("description")
            assert isinstance(description, str) and description.strip()
            for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
                assert token not in description


def test_template_contract_defines_runtime_agent_visible_allow_and_deny_lists() -> None:
    contract = (_PROJECT_ROOT / "docs/contracts/template-extraction.md").read_text(encoding="utf-8")

    assert "## Runtime Agent 可见合同" in contract
    for field in (
        "scope",
        "source_entry_id",
        "parts",
        "reading_block_id",
        "reading_range_id",
        "field_id_vocabulary",
        "field_id",
        "open_questions",
    ):
        assert field in contract
    allowed_block = contract.split("默认允许：", 1)[1].split("```", 2)[1]
    for field in (
        "style_evidence",
        "source_refs",
        "\nevidence\n",
        "registry_field",
        "semantic_field",
        "covered_unit_ids",
        "bound_field_ids",
    ):
        assert field not in allowed_block
    for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
        assert token in contract
    assert "toc_contract" in contract
    assert "generated_field_id" in contract
    assert "目录单元不再有独立的旧 post-unit 输出形状" in contract
    assert "进入产品 Agent 前必须被投影或改写" in contract


def test_semantic_feedback_uses_runtime_agent_work_surface(tmp_path: Path) -> None:
    feedback = _semantic_coverage_feedback(
        _prepared(tmp_path),
        {"status": "needs_input", "summary": "missing semantic judgment set"},
    )

    assert feedback is not None
    visible_text = str(feedback["feedback"]) + str(feedback["failure"])
    assert "source_entry_id" in visible_text
    assert "ordered parts" in visible_text
    assert "field_id_vocabulary" in visible_text
    for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
        assert token not in visible_text


def test_agent_visible_feedback_preserves_scoped_text_for_span_repairs() -> None:
    packet = _agent_visible_feedback_packet(
        {
            "status": "needs_input",
            "feedback": {"type": "span_resolution", "semantic_authority": False},
            "blockers": [
                {
                    "code": "ordered_part_text_not_found",
                    "field": "semantic_judgments[0].parts[1].text",
                    "scope": {"reading_block_id": "u-body:block-0001"},
                    "submitted_text": '"□" 表示占1个字宽。',
                    "scoped_text": "“□” 表示占1个字宽。",
                    "source_text_after_search_start": "“□” 表示占1个字宽。",
                    "search_start_offset": 0,
                    "message": "Copy parts[].text exactly from the scoped_text value.",
                }
            ],
            "failure": None,
        },
        next_step="Revise semantic_judgments.",
    )

    blocker = packet["affected"][0]
    assert blocker["submitted_text"] == '"□" 表示占1个字宽。'
    assert blocker["scoped_text"] == "“□” 表示占1个字宽。"
    assert blocker["source_text_after_search_start"] == "“□” 表示占1个字宽。"
    assert blocker["field"] == "semantic_judgments[0].parts[1].text"
    for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
        assert token not in str(packet)


def test_agent_visible_feedback_preserves_unit_range_scope_token() -> None:
    packet = _agent_visible_feedback_packet(
        {
            "status": "needs_input",
            "feedback": {"type": "materialization_readiness", "semantic_authority": False},
            "blockers": [
                {
                    "code": "body_structure_parts_incomplete",
                    "missing_requirement": "body_structure_parts",
                    "reading_blocks": [
                        {
                            "block_id": "u-body:block-0001",
                            "range_id": "u-body:range-0001",
                            "unit_range_id": "u-body:range-whole-unit",
                            "unit_id": "u-body",
                            "text": "第一章 绪论",
                        }
                    ],
                    "message": "Use one representative body structure range.",
                }
            ],
            "failure": None,
        },
        next_step="Revise semantic_judgments.",
    )

    block = packet["affected"][0]["reading_blocks"][0]
    assert block["unit_range_id"] == "u-body:range-whole-unit"
    for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
        assert token not in str(packet)


def test_agent_visible_feedback_rewrites_object_coverage_blockers() -> None:
    packet = _agent_visible_feedback_packet(
        {
            "status": "needs_input",
            "feedback": {"type": "coverage", "semantic_authority": False},
            "blockers": [
                {
                    "code": "semantic_judgments_without_coverage",
                    "object_ids": ["obj-hidden-from-agent"],
                    "objects": [
                        {
                            "object_id": "obj-hidden-from-agent",
                            "locator": "/body/p[1]/r[1]",
                        }
                    ],
                    "message": (
                        "These semantic judgments do not cover covered_object_ids in "
                        "the object inventory."
                    ),
                },
                {
                    "code": "unknown_judgment_objects",
                    "object_ids": ["obj-other-hidden"],
                    "message": "These semantic judgments cover objects outside the inventory.",
                },
            ],
            "failure": None,
        },
        next_step="Revise semantic_judgments.",
    )

    assert packet["affected"][0]["code"] == "semantic_judgment_scope_uncovered"
    assert packet["affected"][1]["code"] == "semantic_judgment_scope_unknown"
    assert "current source_entry_id" in packet["affected"][0]["message"]
    assert "current source_entry_id" in packet["affected"][1]["message"]
    for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
        assert token not in str(packet)
    assert "obj-hidden-from-agent" not in str(packet)
    assert "obj-other-hidden" not in str(packet)


def test_semantic_feedback_failure_actions_drop_object_protocol_terms() -> None:
    actions = _semantic_feedback_failure_actions(
        {
            "status": "needs_input",
            "feedback": {
                "type": "coverage",
                "mechanical": True,
                "semantic_authority": False,
            },
            "blockers": [
                {
                    "code": "missing_semantic_judgments",
                    "object_ids": ["obj-hidden-from-agent"],
                    "objects": [
                        {
                            "object_id": "obj-hidden-from-agent",
                            "locator": "/body/p[1]/r[1]",
                        }
                    ],
                    "reading_blocks": [
                        {
                            "block_id": "cover:block-0001",
                            "range_id": "cover:range-0001",
                            "unit_range_id": "cover:range-whole-unit",
                            "covered_object_ids": ["obj-hidden-from-agent"],
                            "text": "附件1 封面基本格式",
                        }
                    ],
                    "message": "These inventory objects are not covered.",
                }
            ],
            "failure": {
                "suggested_actions": [
                    "cover_missing_objects=['obj-hidden-from-agent']",
                    "remove_or_resubmit_inventory_for_unknown=['obj-other-hidden']",
                ]
            },
        }
    )

    assert "cover:block-0001" in str(actions)
    assert "cover:range-0001" in str(actions)
    assert "return_source_entry_id_and_ordered_parts_from_current_unit_packet" in actions
    assert "choose_field_ids_only_from_field_id_vocabulary" in actions
    forbidden = (
        "obj-hidden-from-agent",
        "obj-other-hidden",
        "object_id",
        "object_ids",
        "covered_object_ids",
        "locator",
        "cover_missing_objects",
        "remove_or_resubmit_inventory_for_unknown",
    )
    for token in forbidden:
        assert token not in str(actions)


def test_failure_evidence_preserves_non_agent_origin() -> None:
    failure = ToolFailure(
        status="error",
        origin="environment",
        code="visual_renderer_unavailable",
        message="Visual renderer unavailable.",
    )

    evidence = _failure_evidence(failure)

    assert evidence["origin"] == "environment"
    assert evidence["code"] == "visual_renderer_unavailable"


def test_related_revision_request_exposes_only_source_entries_and_semantic_reason() -> None:
    request = POST_UNIT_OUTPUT_SCHEMA["properties"]["revision_request"]
    assert set(request["properties"]) == {"source_entry_ids", "reason"}
    assert request["additionalProperties"] is False
    assert "expand_revision" in POST_UNIT_OUTPUT_SCHEMA["properties"]["status"]["enum"]
    assert "revision_request" not in PREPARE_TEMPLATE_OUTPUT_SCHEMA["properties"]
    for token in _FORBIDDEN_AGENT_VISIBLE_TOKENS:
        assert token not in str(request)

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk.types import ResultMessage

from docfit.app.cli import build_parser
from docfit.app.prepare_template import (
    PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS,
    PREPARE_TEMPLATE_MAX_SEMANTIC_ATTEMPTS,
    PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT,
    PREPARE_TEMPLATE_VISUAL_TURN_LIMIT,
    VISUAL_REVIEW_OUTPUT_SCHEMA,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _append_agent_live_event,
    _complete_semantic_work,
    _ExecutionMetrics,
    _load_persistent_agent_metrics,
    _persist_agent_metrics,
    _review_final_document,
    _run_sdk_session,
    _run_semantic_work_item,
    _semantic_session_key,
    _SemanticSessionCoordinator,
    _validated_visual_pages,
    _with_persistent_agent_evidence,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
    run_prepare_template,
    run_template_agent,
)
from docfit.app.settings import AgentBackend
from docfit.tools.runtime import JsonObject, ToolFailure, atomic_write_json, sha256_file
from docfit.tools.template_tools import (
    ReviewBatchState,
    SemanticWorkItemState,
    _agent_payload,
    _bounded_work_item_payload,
    _mechanical_blank_segments,
    _operation_field_assignments,
    _translate_operation,
    _translate_operations,
    _validated_decision_operations,
    _validated_work_item_operations,
    build_template_review_tool_server,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = PROJECT_ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
COUNTS = {"slot": 0, "remove": 0, "manual": 0, "gap": 0, "unresolved": 0}


def _request(tmp_path: Path) -> PrepareTemplateRequest:
    return PrepareTemplateRequest(
        school_template=TEMPLATE,
        output_directory=tmp_path / "prepared-task",
    )


def _write_fill_contract(prepared: Any, template: Path) -> Path:
    path = (
        prepared.task_root
        / "work/.docfit/template-workspace-v1/publication/fill-contract.json"
    )
    atomic_write_json(path, {"template_sha256": sha256_file(template)})
    return path


def _backend() -> AgentBackend:
    return AgentBackend(
        name="minimax",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def test_prepare_task_copies_only_inputs_skill_and_empty_output(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    assert prepared.template_path.stat().st_mode & 0o222 == 0
    assert prepared.registry_source == REGISTRY.resolve()
    assert prepared.template_sha256 == sha256_file(TEMPLATE)
    skill = prepared.task_root / ".claude/skills/docfit-school-extract"
    references = sorted(item.name for item in (skill / "references").iterdir())
    assert references == [
        "body-structure.md",
        "collection-and-optional-sections.md",
        "effective-style.md",
        "final-visual-review.md",
        "generated-content.md",
        "logical-page-starts.md",
        "object-safety.md",
    ]
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for reference in references:
        assert f"](references/{reference})" in skill_text
    assert "应用负责选择当前工作项、推进流程、限制重试" in skill_text
    assert "此时禁止主动逐页巡检" in skill_text
    assert "只有收到应用绑定的最终全页 PNG 批次时" in skill_text
    assert "cursor" not in skill_text.casefold()
    assert "document_ref" not in skill_text
    assert "template_publish" not in skill_text
    assert not any((prepared.task_root / "output").iterdir())


def test_prepare_task_resumes_matching_unpublished_checkpoint(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    progress = prepared.task_root / "work/.docfit/template-workspace-v1/task-progress.json"
    progress.parent.mkdir(parents=True)
    progress.write_text('{"region_index": 15}', encoding="utf-8")

    assert prepare_template_task(request) == prepared
    assert progress.read_text(encoding="utf-8") == '{"region_index": 15}'


def test_prepare_task_rejects_symlinked_completed_output(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    (prepared.task_root / "output/final-template.docx").symlink_to(TEMPLATE)

    with pytest.raises(ToolFailure) as caught:
        prepare_template_task(request)

    assert caught.value.code == "prepare_checkpoint_invalid"


def test_prepare_task_rejects_resume_with_different_source(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepare_template_task(request)
    different = tmp_path / "different.docx"
    different.write_bytes(TEMPLATE.read_bytes() + b"different")

    with pytest.raises(ToolFailure) as caught:
        prepare_template_task(
            PrepareTemplateRequest(
                school_template=different,
                output_directory=request.output_directory,
            )
        )

    assert caught.value.code == "prepare_source_mismatch"


@pytest.mark.parametrize(
    ("role", "turn_limit"),
    [
        ("semantic", PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT),
        ("visual", PREPARE_TEMPLATE_VISUAL_TURN_LIMIT),
    ],
)
def test_options_are_role_scoped_and_application_owned(
    tmp_path: Path,
    role: str,
    turn_limit: int,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()
    server = build_template_review_tool_server(
        ReviewBatchState(payload={"batch_pages": [1]}, images=[])
    )

    options = build_prepare_template_options(
        prepared,
        _backend(),
        config,
        role=role,  # type: ignore[arg-type]
        mcp_server=server,
    )

    assert options.max_turns == turn_limit
    assert options.tools == ["Skill", "Read"]
    assert {"AskUserQuestion", "Bash", "Write", "Agent", "Glob", "Grep"} <= set(
        options.disallowed_tools or ()
    )
    assert options.mcp_servers is not None
    assert options.output_format is not None
    output_schema = str(options.output_format)
    assert ("accepted" in output_schema) == (role == "semantic")
    assert ("defect" in output_schema) == (role == "visual")
    if role == "semantic":
        system_prompt = str(options.system_prompt)
        assert "submit register_body_member" in system_prompt
        assert "never search for a structure container" in system_prompt
        assert "never submit materialize_structure or a members array" in system_prompt
        assert "already_registered_body_roles" in system_prompt


def test_prompts_keep_semantic_and_full_page_roles_separate(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    semantic = build_prepare_template_prompt(prepared, role="semantic")
    visual = build_prepare_template_prompt(prepared, role="visual")

    assert "not only its target anchor" in semantic
    assert "batch all clear operations" in semantic
    assert "candidates are supplied for every visible top-level object" in semantic
    assert "explicit empty matches" in semantic
    assert "mechanical_blank_segments" in semantic
    assert "separate advisor-name and title blanks" in semantic
    assert "absence of a whitespace-only segment never proves" in semantic
    assert "20 年 月 日" in semantic
    assert "materialize that whole date paragraph" in semantic
    assert "verify the candidate's meaning" in semantic
    assert "returned for that exact object" in semantic
    assert "never materialize the parent paragraph" in semantic
    assert "collapse them into one interface" in semantic
    assert "must never be reused" in semantic
    assert "preceding_landmarks" in semantic
    assert "resubmitting every field responsibility" in semantic
    assert "never probe with a smaller test edit" in semantic
    assert "One content responsibility on one logical page gets exactly one interface" in semantic
    assert "materialize the actual sample object, never both" in semantic
    assert "cardinality=many describes multiple data items" in semantic
    assert "one representative collection slot per logical collection" in semantic
    assert "checkpoint references.entries>=1 or achievements.entries>=1" in semantic
    assert "never materialize another slot" in semantic
    assert "materialize exactly one appendix.title" in semantic
    assert "Never leave the appendix heading without both interfaces" in semantic
    assert "exactly one reusable body.chapters demonstration" in semantic
    assert "body.heading.outline1" in semantic
    assert "body.heading.outline2" in semantic
    assert "body.heading.outline3" in semantic
    assert "Named examples such as 文献综述 or 结论与展望" in semantic
    assert "do not get their own heading or body interfaces" in semantic
    assert "use register_body_member with one object_id and one field_id" in semantic
    assert "never search for a structure container" in semantic
    assert "never submit materialize_structure or members" in semantic
    assert "already_registered_body_roles" in semantic
    assert "carrying slot metadata is an already materialized interface" in semantic
    assert "Select entries only from title_candidates" in semantic
    assert "does not infer which fixed titles belong in the TOC" in semantic
    assert "prior locations only" in semantic
    assert "abstract page still needs its own slot" in semantic
    assert "formatting annotation is not thereby a fixed label" in semantic
    assert "do not delete a demonstrated member type" in semantic
    assert "1000-character limit" in semantic
    assert "application owns traversal" in semantic.casefold()
    assert "final review" in semantic
    assert "cursor" not in semantic.casefold()
    assert "publish" not in semantic.casefold()
    assert "every returned native full-page PNG" in visual
    assert "exactly one verdict" in visual
    assert "blank page alone is not proof" in visual
    assert "bracketed SDT labels are legitimate" in visual
    assert "do not redo template semantics" in visual.casefold()

    categories = set(
        VISUAL_REVIEW_OUTPUT_SCHEMA["properties"]["pages"]["items"]["properties"][
            "defects"
        ]["items"]["properties"]["category"]["enum"]
    )
    assert categories == {
        "clipping",
        "overlap",
        "missing_glyph",
        "table_damage",
        "spacing",
        "header_footer",
    }


def test_decision_contract_accepts_zero_operations_only_for_preserve() -> None:
    assert _validated_decision_operations("preserve", None) == []
    assert _validated_decision_operations("preserve", []) == []

    with pytest.raises(ToolFailure) as preserve_error:
        _validated_decision_operations(
            "preserve",
            [{"action": "clear_content", "object_id": "obj-" + "a" * 24}],
        )
    assert preserve_error.value.code == "preserve_operations_invalid"

    with pytest.raises(ToolFailure) as apply_error:
        _validated_decision_operations("apply", [])
    assert apply_error.value.code == "apply_operations_missing"


def test_body_heading_registration_hides_structure_protocol_from_agent() -> None:
    heading = "obj-" + "a" * 24
    with pytest.raises(ToolFailure) as caught:
        _validated_work_item_operations(
            {"kind": "local_region", "region": {"knowledge_signals": []}},
            "apply",
            [
                {
                    "action": "materialize_slot",
                    "object_id": heading,
                    "field_id": "body.heading.outline2",
                }
            ],
        )

    assert caught.value.code == "body_heading_requires_structure"
    assert caught.value.suggested_actions == ("register_body_member",)

    registration = {
        "action": "register_body_member",
        "object_id": heading,
        "field_id": "body.heading.outline2",
    }
    assert _validated_work_item_operations(
        {"kind": "local_region", "region": {"knowledge_signals": []}},
        "apply",
        [registration],
    ) == [registration]
    assert _translate_operation(registration) == {
        "action": "materialize_structure",
        "object_ref": {"object_id": heading},
        "field_id": "body.chapters",
        "members": [
            {
                "object_ref": {"object_id": heading},
                "field_id": "body.heading.outline2",
            }
        ],
    }


def test_existing_body_role_rejects_registration_without_exposing_container() -> None:
    heading = "obj-" + "a" * 24
    with pytest.raises(ToolFailure) as caught:
        _validated_work_item_operations(
            {
                "kind": "local_region",
                "region": {"knowledge_signals": ["body-structure"]},
                "checkpoint_summary": {
                    "body_structure_gate": {
                        "member_field_counts": {"body.heading.outline2": 1}
                    }
                },
            },
            "apply",
            [
                {
                    "action": "register_body_member",
                    "object_id": heading,
                    "field_id": "body.heading.outline2",
                }
            ],
        )

    assert caught.value.code == "body_member_already_registered"
    assert "structure" in caught.value.message


def test_multiple_body_role_registrations_become_one_ordered_structure_edit() -> None:
    later = "obj-" + "b" * 24
    earlier = "obj-" + "a" * 24
    translated = _translate_operations(
        [
            {
                "action": "register_body_member",
                "object_id": later,
                "field_id": "body.heading.outline2",
            },
            {"action": "remove_object", "object_id": "obj-" + "c" * 24},
            {
                "action": "register_body_member",
                "object_id": earlier,
                "field_id": "body.paragraph",
            },
        ],
        {
            "region": {
                "target": {"object_id": later, "document_order": 20},
                "adjacent_objects": [
                    {"object_id": earlier, "document_order": 10}
                ],
            }
        },
    )

    structures = [
        item for item in translated if item["action"] == "materialize_structure"
    ]
    assert len(structures) == 1
    assert structures[0]["object_ref"] == {"object_id": earlier}
    assert [
        member["field_id"] for member in structures[0]["members"]
    ] == ["body.paragraph", "body.heading.outline2"]


def test_toc_refresh_is_reserved_for_generated_content_work_item() -> None:
    entry_id = "obj-" + "b" * 24
    operation = {
        "action": "refresh_toc",
        "object_id": "obj-" + "a" * 24,
        "entries": [{"object_id": entry_id, "level": 1}],
    }

    with pytest.raises(ToolFailure) as local_error:
        _validated_work_item_operations(
            {
                "kind": "local_region",
                "region": {"knowledge_signals": ["generated-content"]},
            },
            "apply",
            [operation],
        )
    assert local_error.value.code == "local_generated_content_read_only"

    assert _validated_work_item_operations(
        {"kind": "generated_content"},
        "apply",
        [operation],
    ) == [operation]

    with pytest.raises(ToolFailure) as parameters_error:
        _validated_work_item_operations(
            {"kind": "generated_content"},
            "apply",
            [{**operation, "field_id": "generated.toc"}],
        )
    assert parameters_error.value.code == "generated_content_parameters_application_owned"

    with pytest.raises(ToolFailure) as entries_error:
        _validated_work_item_operations(
            {"kind": "generated_content"},
            "apply",
            [{**operation, "entries": []}],
        )
    assert entries_error.value.code == "generated_content_entries_missing"

    with pytest.raises(ToolFailure) as mixed_error:
        _validated_work_item_operations(
            {"kind": "generated_content"},
            "apply",
            [
                operation,
                {
                    "action": "clear_content",
                    "object_id": "obj-" + "c" * 24,
                },
            ],
        )
    assert mixed_error.value.code == "generated_content_action_invalid"


@pytest.mark.parametrize(
    "operation",
    [
        {"action": "clear_content", "object_id": "obj-" + "a" * 24},
        {"action": "remove_object", "object_id": "obj-" + "a" * 24},
        {
            "action": "normalize_effective_format",
            "object_id": "obj-" + "a" * 24,
            "effective_format": {"color": "black"},
        },
    ],
)
def test_local_generated_content_rejects_every_mutation(operation: JsonObject) -> None:
    with pytest.raises(ToolFailure) as caught:
        _validated_work_item_operations(
            {
                "kind": "local_region",
                "region": {"knowledge_signals": ["generated-content"]},
            },
            "apply",
            [operation],
        )
    assert caught.value.code == "local_generated_content_read_only"


def test_initial_registry_candidates_cover_every_visible_top_level_object() -> None:
    calls: list[str] = []

    class FakeRegistry:
        def search(self, text: str, *, limit: int) -> list[JsonObject]:
            calls.append(text)
            assert limit == 5
            return (
                [{"field_id": "submission.date"}]
                if text.startswith("20 年 月 日")
                else []
            )

    class FakeService:
        registry = FakeRegistry()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {
                    "object_id": "obj-" + "a" * 24,
                    "text": "20 年 月 日",
                },
                "adjacent_objects": [
                    {
                        "object_id": "obj-" + "b" * 24,
                        "text": "无关的相邻对象",
                    },
                    {"object_id": "obj-" + "c" * 24, "text": "   "},
                ],
            }
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )

    assert state.initial_candidates() == [
        {
            "object_id": "obj-" + "a" * 24,
            "matches": [{"field_id": "submission.date"}],
        },
        {"object_id": "obj-" + "b" * 24, "matches": []},
        {"object_id": "obj-" + "c" * 24, "matches": []},
    ]
    assert calls == ["20 年 月 日 20年月日", "无关的相邻对象 无关的相邻对象"]
    assert state.offered_field_ids == {"submission.date"}
    assert state.offered_fields_by_object == {
        "obj-" + "a" * 24: {"submission.date"}
    }


def test_application_does_not_prune_body_candidates_by_inferred_position() -> None:
    early_paragraph = "obj-" + "a" * 24
    outline3 = "obj-" + "b" * 24
    later_paragraph = "obj-" + "c" * 24

    class FakeService:
        pass

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {
                    "object_id": early_paragraph,
                    "text": "章前正文样例",
                    "document_order": 10,
                },
                "adjacent_objects": [
                    {
                        "object_id": outline3,
                        "text": "1.1 二级节标题",
                        "document_order": 20,
                    },
                    {
                        "object_id": later_paragraph,
                        "text": "节后正文样例",
                        "document_order": 30,
                    },
                ],
            },
            "checkpoint_summary": {
                "body_structure_gate": {"member_field_counts": {}}
            },
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )
    candidates = [
        {"field_id": "body.chapters"},
        {"field_id": "body.paragraph"},
    ]

    early, _ = state._filter_registered_body_candidates(
        candidates,
        object_id=early_paragraph,
    )
    later, _ = state._filter_registered_body_candidates(
        candidates,
        object_id=later_paragraph,
    )

    assert early == [{"field_id": "body.paragraph"}]
    assert later == [{"field_id": "body.paragraph"}]


def test_prefetched_registry_candidate_is_bound_to_each_object_and_descendants() -> None:
    target = "obj-" + "a" * 24
    child = "obj-" + "b" * 24
    sibling = "obj-" + "c" * 24
    unseen = "obj-" + "d" * 24

    class FakeRegistry:
        def search(self, _text: str, *, limit: int) -> list[JsonObject]:
            assert limit == 5
            return [{"field_id": "appendix.title"}]

    class FakeService:
        registry = FakeRegistry()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {"object_id": target, "text": "附录名称"},
                "adjacent_objects": [
                    {
                        "object_id": child,
                        "type": "run",
                        "parent_context": {"object_id": target},
                    },
                    {"object_id": sibling, "type": "paragraph", "text": "附录说明"},
                ],
            }
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )
    state.initial_candidates()
    state.offer_fields(
        target,
        {"appendix.title"},
        descendants=state.agent_work_item,
    )

    state.validate_field_assignments(
        [{"action": "materialize_slot", "object_id": target, "field_id": "appendix.title"}]
    )
    state.validate_field_assignments(
        [{"action": "materialize_slot", "object_id": child, "field_id": "appendix.title"}]
    )
    state.validate_field_assignments(
        [
            {
                "action": "materialize_slot",
                "object_id": sibling,
                "field_id": "appendix.title",
            }
        ]
    )
    with pytest.raises(ToolFailure) as caught:
        state.validate_field_assignments(
            [{"action": "materialize_slot", "object_id": unseen, "field_id": "appendix.title"}]
        )

    assert caught.value.code == "field_not_offered_for_object"


def test_initial_candidates_mark_existing_body_role_without_reoffering_it() -> None:
    target = "obj-" + "d" * 24

    class FakeRegistry:
        def search(self, _text: str, *, limit: int) -> list[JsonObject]:
            assert limit == 5
            return [{"field_id": "body.heading.outline3"}]

    class FakeService:
        registry = FakeRegistry()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "checkpoint_summary": {
                "body_structure_gate": {
                    "member_field_counts": {"body.heading.outline3": 1}
                }
            },
            "region": {
                "target": {"object_id": target, "text": "1.2 重复二级节标题"},
                "adjacent_objects": [],
            },
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )

    assert state.initial_candidates() == [
        {
            "object_id": target,
            "matches": [],
            "already_registered_body_roles": ["body.heading.outline3"],
            "guidance": (
                "These body roles already have their single representative. Remove this "
                "object only if it is a redundant sample; otherwise preserve it. Do not "
                "search for or edit the structure container."
            ),
        }
    ]
    assert state.offered_field_ids == set()


def test_corrected_retry_cannot_drop_declared_field_responsibilities() -> None:
    target = "obj-" + "a" * 24
    second = "obj-" + "b" * 24

    class FakeService:
        registry = object()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={"region": {"target": {"object_id": target, "text": "姓名"}}},
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )
    complete = [
        {"action": "materialize_slot", "object_id": target, "field_id": "author.name.zh"},
        {"action": "materialize_slot", "object_id": second, "field_id": "advisor.title"},
    ]
    state.validate_retry_field_contract(complete)
    state.validate_retry_field_contract(list(reversed(complete)))

    with pytest.raises(ToolFailure) as caught:
        state.validate_retry_field_contract(complete[:1])

    assert caught.value.code == "retry_dropped_declared_fields"


def test_failed_object_field_binding_does_not_poison_corrected_retry() -> None:
    target = "obj-" + "c" * 24
    sibling = "obj-" + "d" * 24

    class FakeService:
        registry = object()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {"object_id": target, "text": "姓名"},
                "adjacent_objects": [
                    {"object_id": sibling, "type": "paragraph", "text": "职称"}
                ],
            }
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )
    state.offer_fields(target, {"author.name.zh"}, descendants=state.agent_work_item)

    with pytest.raises(ToolFailure) as caught:
        state.prepare_apply_operations(
            [
                {
                    "action": "materialize_slot",
                    "object_id": sibling,
                    "field_id": "author.name.zh",
                }
            ]
        )

    assert caught.value.code == "field_not_offered_for_object"
    assert state.declared_apply_fields is None
    normalized, absorbed, prior = state.prepare_apply_operations(
        [
            {
                "action": "materialize_slot",
                "object_id": target,
                "field_id": "author.name.zh",
            }
        ]
    )
    assert normalized[0]["object_id"] == target
    assert absorbed == []
    assert prior is None


def test_structure_parent_is_not_a_separate_object_field_responsibility() -> None:
    anchor = "obj-" + "7" * 24
    heading = "obj-" + "8" * 24

    assignments = _operation_field_assignments(
        {
            "action": "materialize_structure",
            "field_id": "body.chapters",
            "object_id": anchor,
            "members": [
                {
                    "field_id": "body.heading.outline1",
                    "object_id": heading,
                }
            ],
        }
    )

    assert assignments == {(heading, "body.heading.outline1")}


def test_corrected_retry_may_split_one_field_across_sibling_runs() -> None:
    parent = "obj-" + "2" * 24
    first = "obj-" + "3" * 24
    second = "obj-" + "4" * 24

    class FakeService:
        registry = object()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {"object_id": parent, "type": "paragraph", "text": "职称"},
                "adjacent_objects": [
                    {
                        "object_id": first,
                        "type": "run",
                        "parent_context": {"object_id": parent},
                    },
                    {
                        "object_id": second,
                        "type": "run",
                        "parent_context": {"object_id": parent},
                    },
                ],
            }
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )

    state.validate_retry_field_contract(
        [{"action": "materialize_slot", "object_id": parent, "field_id": "advisor.title"}]
    )
    state.validate_retry_field_contract(
        [
            {"action": "materialize_slot", "object_id": first, "field_id": "advisor.title"},
            {"action": "materialize_slot", "object_id": second, "field_id": "advisor.title"},
        ]
    )


def test_corrected_retry_may_add_required_responsibility() -> None:
    first = "obj-" + "5" * 24
    second = "obj-" + "6" * 24

    class FakeService:
        registry = object()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={"region": {"target": {"object_id": first, "text": "正文"}}},
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )
    state.visible_object_structure[second] = (None, "paragraph")

    state.validate_retry_field_contract(
        [{"action": "materialize_slot", "object_id": first, "field_id": "body.paragraph"}]
    )
    state.validate_retry_field_contract(
        [
            {"action": "materialize_slot", "object_id": first, "field_id": "body.paragraph"},
            {
                "action": "materialize_slot",
                "object_id": second,
                "field_id": "body.heading.outline1",
            },
        ]
    )


def test_split_run_field_materializations_become_one_interface() -> None:
    parent = "obj-" + "a" * 24
    first = "obj-" + "b" * 24
    second = "obj-" + "c" * 24

    class FakeService:
        registry = object()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={"region": {"target": {"object_id": parent, "text": "附录名称"}}},
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )
    state.register_object_payload(
        {
            "local_context": {
                "target": {"object_id": parent, "type": "paragraph", "text": "附录名称"},
                "adjacent_objects": [
                    {
                        "object_id": first,
                        "type": "run",
                        "text": "附录",
                        "parent_context": {"object_id": parent},
                    },
                    {
                        "object_id": second,
                        "type": "run",
                        "text": "名称",
                        "parent_context": {"object_id": parent},
                    },
                ],
            }
        }
    )

    normalized, absorbed = state.normalize_split_run_slots(
        [
            {"action": "materialize_slot", "object_id": first, "field_id": "appendix.title"},
            {"action": "materialize_slot", "object_id": second, "field_id": "appendix.title"},
        ]
    )

    assert normalized == [
        {"action": "materialize_slot", "object_id": first, "field_id": "appendix.title"},
        {"action": "remove_object", "object_id": second},
    ]
    assert absorbed == [
        {
            "action": "materialize_slot",
            "field_id": "appendix.title",
            "object_id": second,
            "absorbed_into_object_id": first,
            "reason": "same_field_split_across_sibling_runs",
        }
    ]


def test_parent_slot_cannot_erase_unlisted_fixed_child_runs() -> None:
    parent = "obj-" + "d" * 24
    fixed = "obj-" + "e" * 24
    variable = "obj-" + "f" * 24
    annotation = "obj-" + "1" * 24

    class FakeService:
        registry = object()

    state = SemanticWorkItemState(
        service=FakeService(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {"object_id": parent, "type": "paragraph", "text": "附录名称"},
                "adjacent_objects": [
                    {
                        "object_id": fixed,
                        "type": "run",
                        "text": "附 录",
                        "parent_context": {"object_id": parent},
                    },
                    {
                        "object_id": variable,
                        "type": "run",
                        "text": "附录名称",
                        "parent_context": {"object_id": parent},
                    },
                    {
                        "object_id": annotation,
                        "type": "run",
                        "text": "（三号黑体）",
                        "parent_context": {"object_id": parent},
                    },
                ],
            }
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )

    with pytest.raises(ToolFailure) as caught:
        state.validate_parent_materialization_contract(
            [
                {"action": "remove_object", "object_id": variable},
                {"action": "remove_object", "object_id": annotation},
                {
                    "action": "materialize_slot",
                    "field_id": "appendix.title",
                    "object_id": parent,
                },
            ]
        )

    assert caught.value.code == "parent_materialization_discards_unlisted_children"


def test_agent_work_item_caps_adjacent_context_and_hides_unseen_objects() -> None:
    target_id = "obj-" + "f" * 24
    target_children = [
        {
            "object_id": f"obj-{index:024x}",
            "text": f"目标 run {index}",
            "type": "run",
            "parent_context": {"object_id": target_id},
        }
        for index in range(10)
    ]
    sibling_runs = [
        {
            "object_id": f"obj-{100 + index:024x}",
            "text": f"邻居 run {index}",
            "type": "run",
        }
        for index in range(4)
    ]
    sibling_paragraphs = [
        {
            "object_id": f"obj-{200 + index:024x}",
            "text": f"邻居段落 {index}",
            "type": "paragraph",
        }
        for index in range(14)
    ]
    adjacent = [*target_children, *sibling_runs, *sibling_paragraphs]
    internal = {
        "document_ref": "document:v1:hidden",
        "region": {
            "region_ref": "region:v1:hidden",
            "target": {"object_id": target_id, "text": "当前目标"},
            "adjacent_objects": adjacent,
        },
    }

    public = _bounded_work_item_payload(internal)

    assert "document_ref" not in public
    assert "region_ref" not in public["region"]
    assert public["region"]["adjacent_objects"] == [
        *target_children[:8],
        *sibling_paragraphs[:12],
    ]
    assert public["region"]["visible_adjacent_count"] == 20
    assert public["region"]["total_adjacent_count"] == len(adjacent)


def test_mechanical_blank_segments_keep_label_separated_values_distinct() -> None:
    parent_id = "obj-" + "f" * 24
    runs = [
        {
            "object_id": "obj-" + "1" * 24,
            "type": "run",
            "text": "指导教师:",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "2" * 24,
            "type": "run",
            "text": "                 ",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "3" * 24,
            "type": "run",
            "text": "职称",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "4" * 24,
            "type": "run",
            "text": "          ",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "5" * 24,
            "type": "run",
            "text": " ",
            "parent_context": {"object_id": parent_id},
        },
        {
            "object_id": "obj-" + "6" * 24,
            "type": "run",
            "text": "    ",
            "parent_context": {"object_id": parent_id},
        },
    ]

    assert _mechanical_blank_segments(runs) == [
        {
            "parent_object_id": parent_id,
            "object_ids": ["obj-" + "2" * 24],
            "character_count": 17,
            "before_text": "指导教师:",
            "after_text": "职称",
        },
        {
            "parent_object_id": parent_id,
            "object_ids": [
                "obj-" + "4" * 24,
                "obj-" + "5" * 24,
                "obj-" + "6" * 24,
            ],
            "character_count": 15,
            "before_text": "职称",
            "after_text": None,
        },
    ]


def test_max_turn_failure_has_a_hard_attempt_bound(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    calls = 0

    class FakeService:
        registry = object()

        def workflow_progress_snapshot(self) -> JsonObject:
            return {
                "source_sha256": "a" * 64,
                "document_sha256": "a" * 64,
                "region_index": 0,
            }

        def restore_workflow_progress(self, _snapshot: JsonObject) -> None:
            return None

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        nonlocal calls
        calls += 1
        return ResultMessage(
            subtype="error_max_turns",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=PREPARE_TEMPLATE_SEMANTIC_TURN_LIMIT,
            session_id=f"attempt-{calls}",
            terminal_reason="max_turns",
        )

    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(
            _run_semantic_work_item(
                prepared,
                _backend(),
                tmp_path,
                _ExecutionMetrics(),
                FakeService(),  # type: ignore[arg-type]
                work_item={"kind": "local_region"},
                images=[],
                internal_region_ref="internal",
                allow_preserve=True,
            )
        )

    assert caught.value.code == "semantic_work_item_attempts_exhausted"
    assert calls == PREPARE_TEMPLATE_MAX_SEMANTIC_ATTEMPTS


def test_sdk_session_times_out_when_backend_stops_emitting_events(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    exited = False

    class HangingClient:
        async def __aenter__(self) -> HangingClient:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            nonlocal exited
            exited = True

        async def query(self, _prompt: str) -> None:
            return None

        async def receive_response(self) -> Any:
            await asyncio.sleep(60)
            yield None

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_prepare_template_options",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.ClaudeSDKClient",
        lambda **_kwargs: HangingClient(),
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(TimeoutError):
        asyncio.run(
            _run_sdk_session(
                prepared,
                _backend(),
                tmp_path,
                role="semantic",
                mcp_server=object(),
                metrics=_ExecutionMetrics(),
            )
        )

    assert exited is True
    events = prepared.task_root / "work/.docfit/template-agent-live.jsonl"
    assert '"event": "session_idle_timeout"' in events.read_text(encoding="utf-8")
    assert f'"idle_timeout_seconds": {0.01}' in events.read_text(encoding="utf-8")
    assert PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS == 180


def test_application_advances_region_after_agent_accepts_one_decision(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    bound: dict[str, Any] = {}

    class FakeService:
        registry = object()

        def __init__(self) -> None:
            self.navigation: list[JsonObject] = []

        def workflow_progress_snapshot(self) -> JsonObject:
            return {
                "source_sha256": "a" * 64,
                "document_sha256": "a" * 64,
                "region_index": 0,
            }

        def restore_workflow_progress(self, _snapshot: JsonObject) -> None:
            raise AssertionError("accepted preserve must not roll back")

        def view(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
            self.navigation.append(args)
            return {"status": "ok"}, []

    service = FakeService()

    def fake_server(state: Any) -> object:
        bound["state"] = state
        return object()

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        state = bound["state"]
        state.submission = {"outcome": "preserve", "reason": "fixed school label"}
        state.post_region_ref = state.internal_region_ref
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="semantic-one",
            terminal_reason="end_turn",
            structured_output={
                "status": "accepted",
                "reason": "The fixed label remains unchanged.",
            },
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_template_semantic_tool_server",
        fake_server,
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    asyncio.run(
        _run_semantic_work_item(
            prepared,
            _backend(),
            tmp_path,
            _ExecutionMetrics(),
            service,  # type: ignore[arg-type]
            work_item={"kind": "local_region"},
            images=[],
            internal_region_ref="internal-region-ref",
            allow_preserve=True,
        )
    )

    assert service.navigation == [
        {
            "action": "next",
            "region_ref": "internal-region-ref",
            "region_outcome": "preserve",
            "reason": "fixed school label",
        }
    ]


def test_application_skips_local_generated_cache_without_agent_session(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    class FakeService:
        def __init__(self) -> None:
            self.next_calls: list[JsonObject] = []
            self.open_calls = 0

        def view(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
            if args["action"] == "next":
                self.next_calls.append(args)
                return {"status": "ok"}, []
            self.open_calls += 1
            if self.open_calls == 1:
                return (
                    {
                        "current_region": {
                            "region_ref": "internal-generated-cache",
                            "count": 1,
                            "knowledge_signals": ["generated-content"],
                        },
                        "checkpoint_summary": {},
                    },
                    [],
                )
            return {"status": "ok"}, []

    async def forbidden_agent(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("local generated cache must not start an Agent session")

    monkeypatch.setattr(
        "docfit.app.prepare_template._run_semantic_work_item",
        forbidden_agent,
    )
    service = FakeService()
    asyncio.run(
        _complete_semantic_work(
            prepared,
            _backend(),
            tmp_path,
            _ExecutionMetrics(),
            service,  # type: ignore[arg-type]
        )
    )

    assert service.next_calls == [
        {
            "action": "next",
            "region_ref": "internal-generated-cache",
            "region_outcome": "preserve",
            "reason": (
                "Application-preserved local generated-content cache; final live refresh "
                "occurs only after title sources are complete."
            ),
        }
    ]


def test_application_does_not_advance_again_when_edit_completed_navigation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    bound: dict[str, Any] = {}

    class FakeService:
        registry = object()

        def workflow_progress_snapshot(self) -> JsonObject:
            return {
                "source_sha256": "a" * 64,
                "document_sha256": "a" * 64,
                "region_index": 39,
            }

        def restore_workflow_progress(self, _snapshot: JsonObject) -> None:
            raise AssertionError("accepted final edit must not roll back")

        def view(self, _args: JsonObject) -> tuple[JsonObject, list[Path]]:
            raise AssertionError("the edit response already completed navigation")

    def fake_server(state: Any) -> object:
        bound["state"] = state
        return object()

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        state = bound["state"]
        state.submission = {
            "outcome": "handled",
            "reason": "removed final instruction shape",
        }
        state.mutated = True
        state.post_region_ref = None
        state.navigation_done = True
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="semantic-final",
            terminal_reason="end_turn",
            structured_output={
                "status": "accepted",
                "reason": "The final edit completed the semantic traversal.",
            },
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_template_semantic_tool_server",
        fake_server,
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    asyncio.run(
        _run_semantic_work_item(
            prepared,
            _backend(),
            tmp_path,
            _ExecutionMetrics(),
            FakeService(),  # type: ignore[arg-type]
            work_item={"kind": "local_region"},
            images=[],
            internal_region_ref="stale-pre-edit-region-ref",
            allow_preserve=True,
        )
    )


def test_persistent_agent_metrics_accumulate_across_process_boundaries(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    first = _ExecutionMetrics()
    first.add_client(startup_wall_duration_ms=30)
    first.add_result(
        ResultMessage(
            subtype="success",
            duration_ms=120,
            duration_api_ms=90,
            is_error=False,
            num_turns=3,
            session_id="first-session",
            terminal_reason="end_turn",
            structured_output={"status": "accepted", "reason": "first"},
        ),
        wall_duration_ms=150,
    )
    _persist_agent_metrics(prepared, first)

    resumed = _load_persistent_agent_metrics(prepared)
    resumed.add_client(startup_wall_duration_ms=30)
    resumed.add_result(
        ResultMessage(
            subtype="success",
            duration_ms=80,
            duration_api_ms=60,
            is_error=False,
            num_turns=2,
            session_id="second-session",
            terminal_reason="end_turn",
            structured_output={"status": "accepted", "reason": "second"},
        ),
        wall_duration_ms=110,
    )
    _persist_agent_metrics(prepared, resumed)

    merged = _with_persistent_agent_evidence(
        prepared,
        TemplateAgentExecution(
            structured_output={},
            tool_uses=(),
            skills_loaded=(),
            session_id="current-only",
            backend="minimax",
            num_turns=2,
            duration_ms=80,
            duration_api_ms=60,
        ),
    )

    assert merged.session_id == "second-session"
    assert merged.session_count == 2
    assert merged.client_count == 2
    assert merged.num_turns == 5
    assert merged.duration_ms == 200
    assert merged.duration_api_ms == 150
    assert merged.wall_duration_ms == 320


def test_semantic_sdk_session_is_reused_only_inside_bounded_page_group(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    clients: list[Any] = []
    prompts: list[str] = []

    class FakeClient:
        def __init__(self, *, options: Any) -> None:
            self.options = options
            self.connected = False
            self.disconnected = False
            clients.append(self)

        async def connect(self) -> None:
            self.connected = True

        async def disconnect(self) -> None:
            self.disconnected = True

    async def fake_query(
        _prepared: Any,
        _backend_value: Any,
        _client: Any,
        *,
        role: str,
        prompt: str,
        metrics: Any,
    ) -> ResultMessage:
        del metrics
        assert role == "semantic"
        prompts.append(prompt)
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id=f"session-{len(prompts)}",
            terminal_reason="end_turn",
            structured_output={"status": "accepted", "reason": "done"},
        )

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", FakeClient)
    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_query", fake_query)
    metrics = _ExecutionMetrics()
    coordinator = _SemanticSessionCoordinator(
        prepared=prepared,
        backend=_backend(),
        config_directory=tmp_path,
        metrics=metrics,
    )

    def state(page: int, suffix: str) -> SemanticWorkItemState:
        return SemanticWorkItemState(
            service=object(),  # type: ignore[arg-type]
            work_item={
                "kind": "local_region",
                "region": {
                    "target": {
                        "object_id": f"obj-{suffix * 24}",
                        "text": suffix,
                    },
                    "evidence": [{"page": page}],
                },
            },
            images=[],
            internal_region_ref="internal",
            allow_preserve=True,
            start_progress={},
        )

    first = state(1, "a")
    second = state(1, "b")
    third = state(2, "c")
    asyncio.run(coordinator.run(first, group_key=_semantic_session_key(first.work_item)))
    asyncio.run(coordinator.run(second, group_key=_semantic_session_key(second.work_item)))
    asyncio.run(coordinator.run(third, group_key=_semantic_session_key(third.work_item)))
    asyncio.run(coordinator.close())

    assert len(clients) == 2
    assert metrics.client_count == 2
    assert metrics.session_count == 0  # fake_query bypasses terminal result collection
    assert all(client.connected and client.disconnected for client in clients)
    assert "Load the docfit-school-extract Skill" in prompts[0]
    assert "previous work item is closed" in prompts[1]
    assert "Load the docfit-school-extract Skill" in prompts[2]


def test_application_owns_visual_cursor_and_agent_sees_only_bound_pages(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    bound: dict[str, Any] = {}

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[JsonObject] = []
            self.receipts: list[JsonObject] = []

        def current_document_ref(self) -> str:
            return "internal-document-ref"

        def final_review(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
            self.calls.append(args)
            page = len(self.calls)
            return (
                {
                    "document_ref": "internal-document-ref",
                    "render_ref": "internal-render-ref",
                    "page_count": 2,
                    "batch_pages": [page],
                    "next_cursor": "internal-page-two" if page == 1 else None,
                },
                [],
            )

        def record_final_review_verdict(self, **kwargs: Any) -> JsonObject:
            self.receipts.append(kwargs)
            return {"status": "clean"}

    service = FakeService()

    def fake_server(state: Any) -> object:
        bound["state"] = state
        return object()

    async def fake_session(*_args: Any, **_kwargs: Any) -> ResultMessage:
        payload = _agent_payload(bound["state"].payload)
        assert "next_cursor" not in payload
        assert "document_ref" not in payload
        page = payload["batch_pages"][0]
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id=f"visual-{page}",
            terminal_reason="end_turn",
            structured_output={
                "pages": [{"page": page, "verdict": "clean", "defects": []}],
                "summary": "No visible rendering defect.",
            },
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.build_template_review_tool_server",
        fake_server,
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_sdk_session", fake_session)

    defects = asyncio.run(
        _review_final_document(
            prepared,
            _backend(),
            tmp_path,
            _ExecutionMetrics(),
            service,  # type: ignore[arg-type]
        )
    )

    assert defects == []
    assert service.calls == [
        {"document_ref": "internal-document-ref"},
        {
            "document_ref": "internal-document-ref",
            "cursor": "internal-page-two",
        },
    ]
    assert len(service.receipts) == 2


def test_deterministic_renderer_failure_does_not_rotate_agent_backends(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backends = (_backend(), _backend())
    calls = 0

    async def fake_backend(*_args: Any, **_kwargs: Any) -> TemplateAgentExecution:
        nonlocal calls
        calls += 1
        raise ToolFailure(
            status="error",
            origin="renderer",
            code="libreoffice_conversion_failed",
            message="The fixed renderer could not convert the current Word.",
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.iter_agent_backends",
        lambda: iter(backends),
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_backend", fake_backend)

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(run_template_agent(prepared))

    assert caught.value.code == "libreoffice_conversion_failed"
    assert calls == 1


def test_visual_verdict_requires_exact_bound_pages() -> None:
    clean = {
        "pages": [
            {"page": 1, "verdict": "clean", "defects": []},
            {"page": 2, "verdict": "clean", "defects": []},
        ]
    }
    assert len(_validated_visual_pages(clean, {1, 2})) == 2

    with pytest.raises(ToolFailure) as caught:
        _validated_visual_pages(
            {"pages": [{"page": 1, "verdict": "clean", "defects": []}]},
            {1, 2},
        )

    assert caught.value.code == "visual_page_coverage_mismatch"


def test_agent_payload_hides_internal_refs_and_code_builds_them_back() -> None:
    public = _agent_payload(
        {
            "document_ref": "document:v1:hidden",
            "region_ref": "region:v1:hidden",
            "next_cursor": "hidden",
            "target": {
                "object_ref": {"object_id": "obj-0123456789abcdef01234567"},
                "text": "题目",
            },
        }
    )
    assert public == {
        "target": {
            "object_id": "obj-0123456789abcdef01234567",
            "text": "题目",
        }
    }

    translated = _translate_operation(
        {
            "action": "materialize_slot",
            "object_id": "obj-0123456789abcdef01234567",
            "field_id": "thesis.title.zh",
        }
    )
    assert translated["object_ref"] == {
        "object_id": "obj-0123456789abcdef01234567"
    }
    assert "object_id" not in translated


def test_cli_requirements_and_registry_are_optional() -> None:
    parsed = build_parser().parse_args(
        [
            "prepare-template",
            "--school-template",
            "school.docx",
            "--output",
            "task",
        ]
    )
    assert parsed.school_requirements is None
    assert parsed.field_registry is None


def test_run_prepare_template_accepts_application_publication_only(tmp_path: Path) -> None:
    async def fake_agent(prepared: Any) -> TemplateAgentExecution:
        output = prepared.task_root / "output/final-template.docx"
        shutil.copyfile(prepared.template_path, output)
        _write_fill_contract(prepared, output)
        return TemplateAgentExecution(
            structured_output={
                "status": "ok",
                "published": True,
                "artifact_path": "output/final-template.docx",
                "template_sha256": sha256_file(output),
                "counts": COUNTS,
            },
            tool_uses=(
                "Skill",
                "mcp__docfit__template_get_current_work_item",
                "mcp__docfit__template_submit_current_decision",
                "mcp__docfit__template_get_review_batch",
            ),
            skills_loaded=("docfit-school-extract",),
            session_id="session-test",
            backend="minimax",
            num_turns=4,
            duration_ms=1200,
            duration_api_ms=900,
        )

    report = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert report.status == "built"
    assert Path(report.artifact_path).name == "final-template.docx"
    assert Path(report.fill_contract_path).name == "fill-contract.json"
    assert Path(report.fill_contract_path).is_file()
    assert Path(report.fill_contract_path).is_relative_to(Path(report.task_root))
    trace = Path(report.task_root) / "work/.docfit/template-agent-execution.json"
    assert trace.is_file()
    assert '"orchestrator": "application_owned"' in trace.read_text(encoding="utf-8")


def test_completed_resume_uses_cross_process_agent_evidence_without_rerunning(
    tmp_path: Path,
) -> None:
    calls = 0

    async def first_run(prepared: Any) -> TemplateAgentExecution:
        nonlocal calls
        calls += 1
        output = prepared.task_root / "output/final-template.docx"
        shutil.copyfile(prepared.template_path, output)
        _write_fill_contract(prepared, output)
        for role, tool in (
            ("semantic", "mcp__docfit__template_get_current_work_item"),
            ("semantic", "mcp__docfit__template_submit_current_decision"),
        ):
            _append_agent_live_event(
                prepared,
                {
                    "event": "tool_use",
                    "role": role,
                    "backend": "minimax",
                    "tool": tool,
                    "input": {},
                },
            )
        return TemplateAgentExecution(
            structured_output={
                "status": "ok",
                "published": True,
                "artifact_path": "output/final-template.docx",
                "template_sha256": sha256_file(output),
                "counts": COUNTS,
            },
            tool_uses=("Skill", "mcp__docfit__template_get_review_batch"),
            skills_loaded=("docfit-school-extract",),
            session_id="visual-session",
            backend="minimax",
            num_turns=2,
            duration_ms=600,
            duration_api_ms=500,
        )

    first = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=first_run))

    async def must_not_run(_prepared: Any) -> TemplateAgentExecution:
        raise AssertionError("a completed checkpoint must not launch another Agent session")

    resumed = asyncio.run(
        run_prepare_template(_request(tmp_path), agent_runner=must_not_run)
    )

    assert calls == 1
    assert resumed.template_sha256 == first.template_sha256
    assert resumed.fill_contract_path == first.fill_contract_path
    assert set(resumed.tool_uses) >= {
        "Skill",
        "mcp__docfit__template_get_current_work_item",
        "mcp__docfit__template_submit_current_decision",
        "mcp__docfit__template_get_review_batch",
    }

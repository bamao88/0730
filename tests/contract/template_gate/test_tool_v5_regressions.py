from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from docfit.tools.runtime import ToolFailure
from docfit.tools.template_tools import SemanticWorkItemState

sys.path.insert(0, str(Path(__file__).parent))
_workspace_contract = importlib.import_module("test_workspace_contract")
_append_styled_paragraphs = _workspace_contract._append_styled_paragraphs
_finish_local_work = _workspace_contract._finish_local_work
_service = _workspace_contract._service


def test_body_members_reject_independent_slots_and_materialize_one_structure(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("普通章标题", "FF0000", "body.heading.outline1"),
        ("1 一级节标题", "0000FF", "body.heading.outline2"),
        ("1.1 二级节标题", "0000FF", "body.heading.outline3"),
        ("正文样例", "00AA00", "body.paragraph"),
    ]
    _append_styled_paragraphs(source, [(text, color) for text, color, _ in samples])
    _, document = service._register_source()
    inspection = service._inspection(document)
    paragraphs = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _, _ in samples}
    }

    with pytest.raises(ToolFailure) as independent:
        service.edit(
            {
                "operations": [
                    {
                        "action": "materialize_slot",
                        "object_ref": paragraphs[samples[0][0]].object_ref,
                        "field_id": samples[0][2],
                    }
                ]
            }
        )
    assert independent.value.code == "body_member_requires_structure"

    promoted, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": paragraphs[samples[0][0]].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": paragraphs[text].object_ref,
                            "field_id": field_id,
                        }
                        for text, _, field_id in samples
                    ],
                }
            ]
        }
    )

    assert promoted["committed"] is True
    _, promoted_path = service._resolve_document(promoted["document_ref"])
    promoted_inspection = service._inspection(promoted_path)
    aliases = [
        str(item.format.get("alias"))
        for item in promoted_inspection.objects
        if item.kind == "sdt"
    ]
    assert aliases.count("body.chapters") == 1
    for _, _, field_id in samples:
        assert aliases.count(field_id) == 1
    structure = next(
        item
        for item in promoted_inspection.objects
        if item.kind == "sdt" and item.format.get("alias") == "body.chapters"
    )
    assert structure.text == "【章标题】【一级节标题】【二级节标题】【正文段落】"


@pytest.mark.parametrize("named_heading", ["第一章 文献综述", "第X章 结论与展望"])
def test_tool_does_not_override_agent_selected_named_heading_semantics(
    tmp_path: Path,
    named_heading: str,
) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        (named_heading, "FF0000", "body.heading.outline1"),
        ("1 一级节标题", "0000FF", "body.heading.outline2"),
        ("1.1 二级节标题", "0000FF", "body.heading.outline3"),
        ("正文样例", "00AA00", "body.paragraph"),
    ]
    _append_styled_paragraphs(source, [(text, color) for text, color, _ in samples])
    _, document = service._register_source()
    inspection = service._inspection(document)
    paragraphs = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _, _ in samples}
    }

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": paragraphs[named_heading].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": paragraphs[text].object_ref,
                            "field_id": field_id,
                        }
                        for text, _, field_id in samples
                    ],
                }
            ]
        }
    )

    assert result["committed"] is True
    assert result["structures"][0]["field_id"] == "body.chapters"


def test_tool_does_not_infer_heading_level_from_visible_numbering(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("第X章 正文标题", "FF0000"),
        ("1 一级节标题", "0000FF"),
        ("正文样例", "00AA00"),
        ("另一个正文样例", "00AA00"),
        ("1.1 二级节标题", "0000FF"),
    ]
    _append_styled_paragraphs(source, samples)
    _, document = service._register_source()
    inspection = service._inspection(document)
    paragraphs = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _ in samples}
    }

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": paragraphs["第X章 正文标题"].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": paragraphs["第X章 正文标题"].object_ref,
                            "field_id": "body.heading.outline1",
                        },
                        {
                            "object_ref": paragraphs["1 一级节标题"].object_ref,
                            "field_id": "body.heading.outline2",
                        },
                        {
                            "object_ref": paragraphs["正文样例"].object_ref,
                            "field_id": "body.heading.outline3",
                        },
                        {
                            "object_ref": paragraphs["另一个正文样例"].object_ref,
                            "field_id": "body.paragraph",
                        },
                    ],
                }
            ]
        }
    )

    assert result["committed"] is True


@pytest.mark.parametrize(
    "text",
    [
        "第X章 （正文标题）",
        "1 材料与方法",
        "1.1 材料",
    ],
)
def test_registry_candidates_remain_semantic_options_not_numbering_decisions(
    tmp_path: Path,
    text: str,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(source, [(text, "0000FF")])
    _, document = service._register_source()
    inspection = service._inspection(document)
    paragraph = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == text
    )

    result = service.registry_query(
        {
            "searches": [
                {
                    "object_id": paragraph.object_ref["object_id"],
                    "query": "正文标题层级",
                }
            ]
        }
    )

    assert any(
        item["field_id"].startswith("body.heading.")
        for item in result["results"][0]["matches"]
    )


def test_unnumbered_sample_keeps_heading_roles_available_for_agent_judgment(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("第X章 正文标题", "FF0000"),
        ("1 一级节标题", "0000FF"),
        ("1.1 二级节标题", "0000FF"),
        ("×××××（小四宋体）××××××", "0000FF"),
    ]
    _append_styled_paragraphs(source, samples)
    _, document = service._register_source()
    inspection = service._inspection(document)
    paragraph = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == samples[-1][0]
    )

    result = service.registry_query(
        {
            "searches": [
                {
                    "object_id": paragraph.object_ref["object_id"],
                    "query": "chapter heading body outline title",
                }
            ]
        }
    )

    assert any(
        item["field_id"].startswith("body.heading.")
        for item in result["results"][0]["matches"]
    )


@pytest.mark.parametrize(
    "action",
    ["clear_content", "remove_object", "normalize_effective_format"],
)
def test_materialized_slot_is_read_only_to_later_semantic_edits(
    tmp_path: Path,
    action: str,
) -> None:
    del tmp_path
    object_id = "obj-" + "a" * 24
    state = SemanticWorkItemState(
        service=object(),  # type: ignore[arg-type]
        work_item={
            "region": {
                "target": {
                    "object_id": object_id,
                    "text": "【正文段落】",
                    "type": "sdt",
                    "slot": {"alias": "body.paragraph", "tag": "body.paragraph.1"},
                }
            }
        },
        images=[],
        internal_region_ref="internal",
        allow_preserve=True,
        start_progress={},
    )
    operation = {"action": action, "object_id": object_id}

    with pytest.raises(_workspace_contract.ToolFailure) as caught:
        state.validate_agent_mutation_targets([operation])

    assert caught.value.code == "materialized_slot_read_only"


def test_toc_refresh_request_does_not_target_materialized_heading_slots() -> None:
    state = SemanticWorkItemState(
        service=object(),  # type: ignore[arg-type]
        work_item={
            "field_id": "generated.toc",
            "target": {
                "object_id": "obj-" + "c" * 24,
                "text": "第X章 XXX",
                "type": "paragraph",
            },
        },
        images=[],
        internal_region_ref=None,
        allow_preserve=False,
        start_progress={},
    )

    state.validate_agent_mutation_targets(
        [
            {
                "action": "refresh_toc",
                "object_id": "obj-" + "c" * 24,
            }
        ]
    )


@pytest.mark.parametrize("cursor", ["start", "0"])
def test_final_review_accepts_conventional_first_batch_cursor(
    tmp_path: Path,
    cursor: str,
) -> None:
    service, visual, source = _service(tmp_path)
    document_ref, _ = service._register_source()
    _finish_local_work(service, source)

    reviewed, _ = service.final_review(
        {"document_ref": document_ref, "cursor": cursor}
    )

    assert reviewed["batch_pages"] == [1]
    assert visual.last_review is not None
    assert "cursor" not in visual.last_review


def test_final_review_does_not_deadlock_after_terminal_edit_without_feedback_target(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    document_ref, _ = service._register_source()
    _finish_local_work(service, source)
    progress = service._read_progress(_workspace_contract.sha256_file(source))
    progress.update(
        {
            "current_region_edited": True,
            "pending_object_ref": None,
        }
    )
    service._write_progress(progress)

    reviewed, _ = service.final_review({"document_ref": document_ref})

    assert reviewed["batch_pages"] == [1]


def test_distinct_fields_on_one_effective_target_are_not_absorbed_as_duplicates(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "run" and "请在此填写" in item.text
    )

    with pytest.raises(_workspace_contract.ToolFailure) as caught:
        service.edit(
            {
                "operations": [
                    {
                        "action": "materialize_slot",
                        "object_ref": selected.object_ref,
                        "field_id": "abstract.en",
                    },
                    {
                        "action": "materialize_slot",
                        "object_ref": selected.object_ref,
                        "field_id": "keywords.en",
                    },
                ]
            }
        )

    assert caught.value.code == "batch_operations_conflict"

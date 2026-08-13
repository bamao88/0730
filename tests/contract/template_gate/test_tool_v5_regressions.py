from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from docfit.tools.template_tools import SemanticWorkItemState

sys.path.insert(0, str(Path(__file__).parent))
_workspace_contract = importlib.import_module("test_workspace_contract")
_append_styled_paragraphs = _workspace_contract._append_styled_paragraphs
_finish_local_work = _workspace_contract._finish_local_work
_service = _workspace_contract._service


def test_independent_body_slots_are_promoted_into_one_structure(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("普通章标题", "FF0000", "body.heading.level1"),
        ("1.1 二级标题", "0000FF", "body.heading.level2"),
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

    independent, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": paragraphs[text].object_ref,
                    "field_id": field_id,
                }
                for text, _, field_id in samples
            ]
        }
    )
    _, independent_path = service._resolve_document(independent["document_ref"])
    independent_inspection = service._inspection(independent_path)
    controls = {
        str(item.format["alias"]): item
        for item in independent_inspection.objects
        if item.kind == "sdt"
        and item.format.get("alias") in {field_id for _, _, field_id in samples}
    }

    promoted, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": controls["body.heading.level1"].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": controls[field_id].object_ref,
                            "field_id": field_id,
                        }
                        for _, _, field_id in samples
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
    assert structure.text == "【一级章标题】【二级标题】【正文段落】"


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


def test_toc_can_use_materialized_heading_slots_as_read_only_sources() -> None:
    heading_id = "obj-" + "b" * 24
    state = SemanticWorkItemState(
        service=object(),  # type: ignore[arg-type]
        work_item={
            "field_id": "generated.toc",
            "title_candidates": [
                {
                    "object_id": heading_id,
                    "text": "【一级章标题】",
                    "type": "sdt",
                    "slot": {
                        "alias": "body.heading.level1",
                        "tag": "body.heading.level1.1",
                    },
                }
            ],
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
                "entries": [{"object_id": heading_id, "level": 1}],
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

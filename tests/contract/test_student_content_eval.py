from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from docfit.app.cli import build_parser, main
from docfit.evals.student_content import (
    JSON_REPORT_FILENAME,
    MARKDOWN_REPORT_FILENAME,
    compare_student_content,
)

SOURCE_SHA = "a" * 64
REGISTRY_SHA = "b" * 64


def _actual() -> dict[str, Any]:
    return {
        "schema_version": "docfit-student-content-model/v2",
        "status": "READY",
        "source_sha256": SOURCE_SHA,
        "registry": {
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.4.0",
            "sha256": REGISTRY_SHA,
        },
        "items": [
            {
                "content_id": "actual-heading",
                "source_content_id": "source-heading",
                "field_id": "body.heading.outline1",
                "classification_status": "classified",
                "value": "SENSITIVE HEADING",
                "source_order": {"block": 1, "inline": 0},
                "source_object_ids": ["obj-heading"],
                "parent_content_id": None,
            },
            {
                "content_id": "actual-body",
                "source_content_id": "source-body",
                "field_id": "body.paragraph",
                "classification_status": "classified",
                "value": "SENSITIVE BODY",
                "source_order": {"block": 2, "inline": 0},
                "source_object_ids": ["obj-body"],
                "parent_content_id": "actual-heading",
            },
        ],
        "field_results": [],
        "relations": [],
        "source_coverage": {"all_source_objects_accounted_for": True},
        "privacy": "task_local_contains_student_content",
    }


def _inventory() -> dict[str, Any]:
    return {
        "schema_version": "docfit-student-source-inventory/v2",
        "source_sha256": SOURCE_SHA,
        "object_count": 2,
        "content_item_count": 2,
        "content_items": [
            {
                "source_content_id": "source-heading",
                "source_order": {"block": 1, "inline": 0},
                "source_object_ids": ["obj-heading"],
                "source_locators": [],
            },
            {
                "source_content_id": "source-body",
                "source_order": {"block": 2, "inline": 0},
                "source_object_ids": ["obj-body"],
                "source_locators": [],
            },
        ],
        "objects": [
            {"source_object_ref": {"object_id": "obj-heading"}},
            {"source_object_ref": {"object_id": "obj-body"}},
        ],
    }


def _gold_item(
    *,
    content_id: str,
    field_id: str,
    source_id: str | None,
    order: tuple[int, int],
    value: str | None,
    parent_content_id: str | None,
) -> dict[str, Any]:
    refs = [] if source_id is None else [{"object_id": source_id}]
    occurrences = (
        []
        if source_id is None
        else [
            {
                "source_object_ref": {"object_id": source_id},
                "observed_text": value,
                "source_order": {"block": order[0], "inline": order[1]},
            }
        ]
    )
    return {
        "content_id": content_id,
        "field_id": field_id,
        "classification_status": "registered",
        "observed_value": value,
        "source_object_refs": refs,
        "source_occurrences": occurrences,
        "source_order": {"block": order[0], "inline": order[1]},
        "parent_content_id": parent_content_id,
    }


def _gold() -> dict[str, Any]:
    return {
        "schema_version": "docfit-student-content-extraction-gold/v2",
        "status": "gold",
        "gold_id": "synthetic-student.extraction",
        "gold_revision": "2026-08-12.r1",
        "student_document_sha256": SOURCE_SHA,
        "field_registry_ref": {
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.4.0",
            "sha256": REGISTRY_SHA,
        },
        "ordering_contract": {
            "version": "docfit-source-order/v1",
            "truth_source": "items",
        },
        "items": [
            _gold_item(
                content_id="gold-chapters",
                field_id="body.chapters",
                source_id=None,
                order=(0, 0),
                value=None,
                parent_content_id=None,
            ),
            _gold_item(
                content_id="gold-heading",
                field_id="body.heading.outline1",
                source_id="obj-heading",
                order=(1, 0),
                value="SENSITIVE HEADING",
                parent_content_id="gold-chapters",
            ),
            _gold_item(
                content_id="gold-body",
                field_id="body.paragraph",
                source_id="obj-body",
                order=(2, 0),
                value="SENSITIVE BODY",
                parent_content_id="gold-heading",
            ),
        ],
        "field_results": [
            {"field_id": "body.chapters", "status": "present"},
            {"field_id": "body.heading.outline1", "status": "present"},
            {"field_id": "body.paragraph", "status": "present"},
        ],
        "coverage": {
            "all_objects_accounted_for": True,
            "unresolved_count": 0,
            "objects": [
                {"object_id": "obj-heading", "status": "mapped"},
                {"object_id": "obj-body", "status": "mapped"},
            ]
        },
        "unregistered_items": [],
    }


def _evidence() -> dict[str, Any]:
    return {
        "backend": "synthetic-live-shape",
        "batches": [
            {
                "backend": "synthetic-live-shape",
                "session_id": "session-1",
                "tool_uses": ["Read"],
            }
        ],
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _saved_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    actual_directory = tmp_path / "actual"
    gold_directory = tmp_path / "gold"
    output_directory = tmp_path / "report"
    _write_json(actual_directory / "student-content.json", _actual())
    _write_json(actual_directory / "work/student-inventory.json", _inventory())
    _write_json(actual_directory / "work/agent-evidence.json", _evidence())
    _write_json(gold_directory / "student-content.gold.json", _gold())
    return actual_directory, gold_directory, output_directory


def test_exact_extraction_actual_passes_all_dimensions_without_content_leak() -> None:
    report = compare_student_content(_actual(), _inventory(), _gold(), _evidence())

    assert report["status"] == "PASS"
    assert report["blockers"] == []
    assert set(report["dimensions"].values()) == {"PASS"}
    assert report["order_comparison"]["exact_semantic_sequence_match"] is True
    assert report["hierarchy_comparison"]["implicit_structural_root_matches"] == 1
    rendered = json.dumps(report, ensure_ascii=False)
    assert "SENSITIVE HEADING" not in rendered
    assert "SENSITIVE BODY" not in rendered


def test_order_is_an_independent_failing_dimension() -> None:
    actual = deepcopy(_actual())
    inventory = deepcopy(_inventory())
    actual["items"].reverse()
    inventory["content_items"].reverse()
    for index, item in enumerate(actual["items"], start=1):
        item["source_order"] = {"block": index, "inline": 0}
    for index, item in enumerate(inventory["content_items"], start=1):
        item["source_order"] = {"block": index, "inline": 0}

    report = compare_student_content(actual, inventory, _gold(), _evidence())

    assert report["dimensions"]["content_order"] == "FAIL"
    assert "content_order_mismatch" in report["blockers"]
    assert report["order_comparison"]["first_mismatch"] == {
        "index": 0,
        "gold_binding": {
            "source_object_ids": ["obj-heading"],
            "field_id": "body.heading.outline1",
        },
        "actual_binding": {
            "source_object_ids": ["obj-body"],
            "field_id": "body.paragraph",
        },
    }


def test_multi_source_and_shared_source_semantics_can_be_compared_exactly() -> None:
    gold = _gold()
    gold["items"] = [
        _gold_item(
            content_id="gold-chapters",
            field_id="body.chapters",
            source_id=None,
            order=(0, 0),
            value=None,
            parent_content_id=None,
        ),
        {
            **_gold_item(
                content_id="gold-advisor-name",
                field_id="advisor.name.zh",
                source_id="obj-shared",
                order=(1, 0),
                value="SENSITIVE NAME",
                parent_content_id="gold-chapters",
            ),
            "source_object_refs": [
                {"object_id": "obj-shared"},
                {"object_id": "obj-repeat"},
            ],
            "source_occurrences": [
                {
                    "source_object_ref": {"object_id": "obj-shared"},
                    "observed_text": "SENSITIVE NAME",
                    "source_order": {"block": 1, "inline": 0},
                },
                {
                    "source_object_ref": {"object_id": "obj-repeat"},
                    "observed_text": "SENSITIVE LABEL NAME",
                    "source_order": {"block": 3, "inline": 0},
                },
            ],
        },
        _gold_item(
            content_id="gold-advisor-title",
            field_id="advisor.title",
            source_id="obj-shared",
            order=(1, 1),
            value="SENSITIVE TITLE",
            parent_content_id="gold-chapters",
        ),
    ]
    gold["coverage"] = {
        "all_objects_accounted_for": True,
        "unresolved_count": 0,
        "objects": [
            {"object_id": "obj-shared", "status": "mapped"},
            {"object_id": "obj-repeat", "status": "mapped"},
        ]
    }
    gold["field_results"] = [
        {"field_id": "body.chapters", "status": "present"},
        {"field_id": "advisor.name.zh", "status": "present"},
        {"field_id": "advisor.title", "status": "present"},
    ]
    actual = _actual()
    actual["items"] = [
        {
            "content_id": "actual-advisor-name",
            "source_content_id": "source-advisor-name",
            "field_id": "advisor.name.zh",
            "classification_status": "classified",
            "value": "SENSITIVE NAME",
            "source_order": {"block": 1, "inline": 0},
            "source_object_ids": ["obj-shared", "obj-repeat"],
            "parent_content_id": None,
        },
        {
            "content_id": "actual-advisor-title",
            "source_content_id": "source-advisor-title",
            "field_id": "advisor.title",
            "classification_status": "classified",
            "value": "SENSITIVE TITLE",
            "source_order": {"block": 1, "inline": 1},
            "source_object_ids": ["obj-shared"],
            "parent_content_id": None,
        },
    ]
    inventory = _inventory()
    inventory["content_items"] = [
        {
            "source_content_id": "source-advisor-name",
            "source_order": {"block": 1, "inline": 0},
            "source_object_ids": ["obj-shared", "obj-repeat"],
            "source_locators": [],
        },
        {
            "source_content_id": "source-advisor-title",
            "source_order": {"block": 1, "inline": 1},
            "source_object_ids": ["obj-shared"],
            "source_locators": [],
        },
    ]
    inventory["objects"] = [
        {"source_object_ref": {"object_id": "obj-shared"}},
        {"source_object_ref": {"object_id": "obj-repeat"}},
    ]

    report = compare_student_content(actual, inventory, gold, _evidence())

    assert report["status"] == "PASS"
    assert report["source_binding"]["actual_overlapping_source_ids"] == ["obj-shared"]
    assert report["semantic_grouping_comparison"]["exact_binding_group_count"] == 2


def test_gold_local_object_ids_align_to_runtime_inventory_locators() -> None:
    actual = _actual()
    inventory = _inventory()
    gold = _gold()
    locators = {
        "obj-heading": "/body/p[@paraId=00000001]",
        "obj-body": "/body/p[@paraId=00000002]",
    }
    for item in actual["items"]:
        item["source_locators"] = [locators[item["source_object_ids"][0]]]
    for item in inventory["content_items"]:
        item["source_locators"] = [locators[item["source_object_ids"][0]]]
    for item in inventory["objects"]:
        source_id = item["source_object_ref"]["object_id"]
        item["source_locator"] = locators[source_id]
        item["kind"] = "paragraph"
    for item in gold["items"]:
        for ref in item["source_object_refs"]:
            runtime_id = ref["object_id"]
            ref["object_id"] = f"gold-{runtime_id}"
            ref["source_locator"] = locators[runtime_id]
        for occurrence in item["source_occurrences"]:
            runtime_id = occurrence["source_object_ref"]["object_id"]
            occurrence["source_object_ref"]["object_id"] = f"gold-{runtime_id}"
            occurrence["source_object_ref"]["source_locator"] = locators[runtime_id]

    report = compare_student_content(actual, inventory, gold, _evidence())

    assert report["status"] == "PASS"
    assert report["source_alignment"]["exact_object_id_count"] == 0
    assert report["source_alignment"]["locator_crosswalk_count"] == 2
    assert report["source_alignment"]["complete"] is True


def test_cli_uses_one_actual_directory_and_publishes_both_reports(
    tmp_path: Path,
    capsys: Any,
) -> None:
    actual_directory, gold_directory, output_directory = _saved_case(tmp_path)
    args = build_parser().parse_args(
        [
            "eval-student-content",
            "--actual",
            str(actual_directory),
            "--gold",
            str(gold_directory),
            "--output",
            str(output_directory),
            "--json",
        ]
    )
    assert args.command == "eval-student-content"

    assert main(
        [
            "eval-student-content",
            "--actual",
            str(actual_directory),
            "--gold",
            str(gold_directory),
            "--output",
            str(output_directory),
            "--json",
        ]
    ) == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "PASS"
    json_report = output_directory / JSON_REPORT_FILENAME
    markdown_report = output_directory / MARKDOWN_REPORT_FILENAME
    assert json_report.is_file()
    assert markdown_report.is_file()
    assert json.loads(json_report.read_text(encoding="utf-8"))["status"] == "PASS"
    markdown = markdown_report.read_text(encoding="utf-8")
    assert "内容顺序" in markdown
    assert "SENSITIVE" not in markdown


def test_cli_fails_closed_for_a_non_gold_candidate(
    tmp_path: Path,
    capsys: Any,
) -> None:
    actual_directory, gold_directory, output_directory = _saved_case(tmp_path)
    gold = _gold()
    gold["status"] = "candidate"
    _write_json(gold_directory / "student-content.gold.json", gold)

    assert main(
        [
            "eval-student-content",
            "--actual",
            str(actual_directory),
            "--gold",
            str(gold_directory),
            "--output",
            str(output_directory),
            "--json",
        ]
    ) == 2

    failure = json.loads(capsys.readouterr().err)
    assert failure["status"] == "INPUT_ERROR"
    assert failure["failure"]["code"] == "gold_not_accepted"
    assert not output_directory.exists()

from __future__ import annotations

import json

import pytest

from docfit.template.source_entries import (
    CanonicalSourceEntry,
    CanonicalSourceInventory,
    SourceEntryProvenance,
    SourceOrder,
    build_canonical_source_inventory,
    project_source_entries_onto_objects,
    select_source_entries_for_objects,
    source_entry_id_for_entry,
    validate_canonical_source_entries,
)


def test_canonical_source_entry_allows_multiple_raw_objects_without_field_id() -> None:
    provenance = (
        SourceEntryProvenance(
            object_id="obj-label",
            locator="/body/p[1]/r[1]",
            text_span=(0, 2),
            fingerprint="a" * 64,
        ),
        SourceEntryProvenance(
            object_id="obj-value",
            locator="/body/p[1]/r[2]",
            text_span=(2, 4),
            fingerprint="b" * 64,
        ),
    )
    entry_id = source_entry_id_for_entry(
        source_sha256="c" * 64,
        text="姓名张三",
        entry_type="text",
        source_order=SourceOrder(block=1, inline=0),
        provenance=provenance,
    )

    entry = CanonicalSourceEntry(
        source_entry_id=entry_id,
        text="姓名张三",
        entry_type="text",
        source_order=SourceOrder(block=1, inline=0),
        provenance=provenance,
    )
    payload = entry.to_json()

    assert payload["source_entry_id"] == entry_id
    assert payload["text"] == "姓名张三"
    assert payload["source_order"] == {"block": 1, "inline": 0}
    assert [item["object_id"] for item in payload["provenance"]] == [
        "obj-label",
        "obj-value",
    ]
    assert "field_id" not in json.dumps(payload, ensure_ascii=False)


def test_canonical_source_entry_uses_text_as_span_boundary() -> None:
    payload = {
        "source_entry_id": "source-entry-invalid-span",
        "text": "姓名",
        "entry_type": "text",
        "source_order": {"block": 1, "inline": 0},
        "provenance": [
            {
                "object_id": "obj-too-long",
                "locator": "/body/p[1]/r[1]",
                "text_span": [0, 3],
            }
        ],
    }

    with pytest.raises(ValueError, match="inside source entry text"):
        CanonicalSourceEntry.from_json(payload)


def test_canonical_source_entry_rejects_field_binding_keys() -> None:
    payload = {
        "source_entry_id": "source-entry-has-field",
        "text": "姓名张三",
        "entry_type": "text",
        "source_order": {"block": 1, "inline": 0},
        "field_id": "author.name.zh",
        "provenance": [
            {
                "object_id": "obj-label",
                "locator": "/body/p[1]/r[1]",
                "text_span": [0, 2],
            }
        ],
    }

    with pytest.raises(ValueError, match="must not contain content field binding keys"):
        CanonicalSourceEntry.from_json(payload)


def test_canonical_source_entry_collection_rejects_duplicate_ids() -> None:
    entry = {
        "source_entry_id": "source-entry-duplicate",
        "text": "姓名",
        "entry_type": "text",
        "source_order": {"block": 1, "inline": 0},
        "provenance": [
            {
                "object_id": "obj-name",
                "locator": "/body/p[1]/r[1]",
                "text_span": [0, 2],
            }
        ],
    }
    duplicate = {
        **entry,
        "source_order": {"block": 1, "inline": 1},
    }

    with pytest.raises(ValueError, match="source_entry_id values must be unique"):
        validate_canonical_source_entries([entry, duplicate])


def test_canonical_inventory_groups_raw_objects_before_reading_packet() -> None:
    source_hash = "d" * 64
    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "姓名：张三",
            "object_ref": {
                "object_id": "obj-paragraph",
                "expected_fingerprint": "a" * 64,
            },
        },
        {
            "type": "run",
            "locator": "/body/p[1]/r[1]",
            "text": "姓名：",
            "object_ref": {
                "object_id": "obj-label",
                "expected_fingerprint": "b" * 64,
            },
        },
        {
            "type": "run",
            "locator": "/body/p[1]/r[2]",
            "text": "张三",
            "object_ref": {
                "object_id": "obj-value",
                "expected_fingerprint": "c" * 64,
            },
        },
    ]

    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=objects,
    )
    entries = canonical.source_entries

    assert len(entries) == 1
    entry = entries[0]
    assert entry.text == "姓名：张三"
    assert entry.entry_type == "text"
    assert entry.source_order == SourceOrder(block=1, inline=0)
    assert [item.object_id for item in entry.provenance] == [
        "obj-paragraph",
        "obj-label",
        "obj-value",
    ]
    assert [item.text_span for item in entry.provenance] == [
        (0, 5),
        (0, 3),
        (3, 5),
    ]
    assert "field_id" not in json.dumps(entry.to_json(), ensure_ascii=False)

    projected = project_source_entries_onto_objects(
        objects,
        entries,
        source_sha256=source_hash,
    )
    assert [item["source_entry_id"] for item in projected] == [
        entry.source_entry_id,
        entry.source_entry_id,
        entry.source_entry_id,
    ]
    assert projected[0]["source_entry_ref"]["provenance"][0]["object_id"] == (
        "obj-paragraph"
    )


def test_canonical_inventory_does_not_duplicate_ancestor_container_text() -> None:
    inventory = build_canonical_source_inventory(
        source_snapshot_sha256="d" * 64,
        inspected_objects=[
            _raw_object(
                kind="sdt",
                locator="/body/sdt[@sdtId=1001]",
                object_id="obj-toc-container",
                text="目录第一章1第二章2",
            ),
            _raw_object(
                kind="paragraph",
                locator="/body/sdt[@sdtId=1001]/p[1]",
                object_id="obj-toc-title",
                text="目录",
            ),
            _raw_object(
                kind="paragraph",
                locator="/body/sdt[@sdtId=1001]/p[2]",
                object_id="obj-toc-row-1",
                text="第一章\t1",
            ),
            _raw_object(
                kind="paragraph",
                locator="/body/sdt[@sdtId=1001]/p[3]",
                object_id="obj-toc-row-2",
                text="第二章\t2",
            ),
        ],
    )

    assert [entry.text for entry in inventory.source_entries] == [
        "",
        "目录",
        "第一章\t1",
        "第二章\t2",
    ]
    container = inventory.source_entries[0].to_json()
    assert container["entry_type"] == "sdt"
    assert container["extent"] == {"kind": "whole_entry"}
    assert container["provenance"][0]["extent"] == {"kind": "whole_entry"}


def _raw_object(
    *,
    kind: str,
    locator: str,
    object_id: str,
    text: str | None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "type": kind,
        "locator": locator,
        "object_ref": {
            "document_sha256": "e" * 64,
            "object_id": object_id,
            "expected_fingerprint": object_id.rjust(64, "0")[-64:],
        },
    }
    if text is not None:
        value["text"] = text
    return value


def test_source_entry_ids_are_stable_across_unit_windows_and_call_order() -> None:
    objects = [
        _raw_object(
            kind="paragraph",
            locator="/body/p[1]",
            object_id="obj-one",
            text="第一段",
        ),
        _raw_object(
            kind="paragraph",
            locator="/body/p[2]",
            object_id="obj-two",
            text="第二段",
        ),
        _raw_object(
            kind="paragraph",
            locator="/body/p[3]",
            object_id="obj-three",
            text="第三段",
        ),
    ]

    inventory = build_canonical_source_inventory(
        source_snapshot_sha256="e" * 64,
        inspected_objects=objects,
    )
    assert isinstance(inventory, CanonicalSourceInventory)

    second_then_first = (
        select_source_entries_for_objects(inventory, ["obj-two", "obj-three"]),
        select_source_entries_for_objects(inventory, ["obj-one", "obj-two"]),
    )
    first_then_second = (
        select_source_entries_for_objects(inventory, ["obj-one", "obj-two"]),
        select_source_entries_for_objects(inventory, ["obj-two", "obj-three"]),
    )
    retry = CanonicalSourceInventory.from_json(inventory.to_json())

    assert [entry.source_entry_id for entry in second_then_first[0]] == [
        entry.source_entry_id for entry in first_then_second[1]
    ]
    assert [entry.source_entry_id for entry in second_then_first[1]] == [
        entry.source_entry_id for entry in first_then_second[0]
    ]
    assert [entry.source_entry_id for entry in retry.source_entries] == [
        entry.source_entry_id for entry in inventory.source_entries
    ]
    assert retry.inventory_digest == inventory.inventory_digest


@pytest.mark.parametrize(
    "exact_text",
    (
        "  姓名\t张三  ",
        "第一行\n第二行\r\n第三行",
        "emoji: 👩🏽‍🎓 / family: 👨‍👩‍👧‍👦",
        "组合字符: e\u0301；预组字符: é",
        "\u00a0全角　空格\u2003",
    ),
)
def test_canonical_inventory_preserves_exact_python_code_points(exact_text: str) -> None:
    inventory = build_canonical_source_inventory(
        source_snapshot_sha256="e" * 64,
        inspected_objects=[
            _raw_object(
                kind="paragraph",
                locator="/body/p[1]",
                object_id="obj-exact",
                text=exact_text,
            )
        ],
    )

    assert inventory.source_entries[0].text == exact_text
    assert inventory.source_entries[0].provenance[0].text_span == (0, len(exact_text))
    assert inventory.to_json()["source_entries"][0]["text"] == exact_text


@pytest.mark.parametrize(
    ("kind", "text"),
    (
        ("paragraph", ""),
        ("table", ""),
        ("picture", None),
        ("shape", None),
        ("sdt", ""),
        ("fieldChar", ""),
        ("tab", ""),
        ("break", ""),
    ),
)
def test_canonical_inventory_keeps_blank_and_non_text_structural_extents(
    kind: str,
    text: str | None,
) -> None:
    inventory = build_canonical_source_inventory(
        source_snapshot_sha256="e" * 64,
        inspected_objects=[
            _raw_object(
                kind=kind,
                locator=f"/body/{kind}[1]",
                object_id=f"obj-{kind}",
                text=text,
            )
        ],
    )

    assert len(inventory.source_entries) == 1
    payload = inventory.to_json()["source_entries"][0]
    assert payload["text"] == ""
    assert payload["extent"] == {"kind": "whole_entry"}
    assert payload["provenance"][0]["extent"] == {"kind": "whole_entry"}
    assert "text_span" not in payload["provenance"][0]


def test_canonical_inventory_blocks_unsupported_structure_explicitly() -> None:
    with pytest.raises(ValueError, match="unsupported_structure.*text_box"):
        build_canonical_source_inventory(
            source_snapshot_sha256="e" * 64,
            inspected_objects=[
                _raw_object(
                    kind="text_box",
                    locator="/body/p[1]/text_box[1]",
                    object_id="obj-text-box",
                    text=None,
                )
            ],
        )


@pytest.mark.parametrize("missing_key", ["locator", "object_ref"])
def test_canonical_inventory_rejects_structure_without_provenance(
    missing_key: str,
) -> None:
    raw = _raw_object(
        kind="picture",
        locator="/body/p[1]/picture[1]",
        object_id="obj-picture",
        text=None,
    )
    raw.pop(missing_key)

    with pytest.raises(
        ValueError,
        match="canonical_source_inventory_missing_provenance",
    ):
        build_canonical_source_inventory(
            source_snapshot_sha256="e" * 64,
            inspected_objects=[raw],
        )

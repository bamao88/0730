from docfit.template.harness import _coverage_judgments_from_ordered_parts


def _inventory() -> dict[str, object]:
    return {
        "field_id_vocabulary": {"allowed_field_ids": []},
        "source_entries": [
            {
                "source_entry_id": "source-entry-title",
                "provenance": [{"object_id": "obj-title"}],
            }
        ],
        "reading_blocks": [
            {
                "block_id": "u-cover:block-0001",
                "covered_object_ids": ["obj-title"],
            }
        ],
    }


def test_coverage_projection_uses_only_canonical_source_entry_id() -> None:
    projected = _coverage_judgments_from_ordered_parts(
        _inventory(),
        [
            {
                "source_entry_id": "source-entry-title",
                "parts": [{"text": "题目", "role": "fixed_label"}],
            }
        ],
    )

    assert projected[0]["covered_object_ids"] == ["obj-title"]


def test_coverage_projection_does_not_read_retired_reading_scope() -> None:
    projected = _coverage_judgments_from_ordered_parts(
        _inventory(),
        [
            {
                "scope": {"reading_block_id": "u-cover:block-0001"},
                "parts": [{"text": "题目", "role": "fixed_label"}],
            }
        ],
    )

    assert projected[0]["covered_object_ids"] == []
    assert "scope" not in projected[0]

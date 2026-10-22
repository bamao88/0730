import pytest

from docfit.content.fill import _is_canonical_slot_ref


def test_fill_consumer_accepts_canonical_source_entry_slot_ref() -> None:
    assert _is_canonical_slot_ref(
        "source_entry_id=source-entry-title;extent=text[0:5];"
        f"source_snapshot_sha256={'a' * 64};field_id=thesis.title.zh"
    )


@pytest.mark.parametrize(
    "slot_ref",
    [
        None,
        "content-control-tag-only",
        "reading_block_id=u-cover:block-0001;part_index=0;field_id=thesis.title.zh",
        "reading_range_id=u-cover:range-0001;part_index=0;field_id=thesis.title.zh",
    ],
)
def test_fill_consumer_rejects_missing_or_retired_slot_ref(slot_ref: object) -> None:
    assert not _is_canonical_slot_ref(slot_ref)

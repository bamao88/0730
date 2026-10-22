from docfit.template.artifact import _parse_slot_ref
from docfit.template.source_spans import SourceSpan, TextSourceExtent, source_span_ref


def test_publication_accepts_only_canonical_source_entry_slot_refs() -> None:
    span_ref = source_span_ref(
        source_snapshot_sha256="a" * 64,
        source_span=SourceSpan(
            source_entry_id="source-entry-title",
            extent=TextSourceExtent(start=2, end=5),
        ),
    )

    parsed = _parse_slot_ref(f"{span_ref};field_id=thesis.title.zh")

    assert parsed is not None
    assert parsed["scope"] == {"source_entry_id": "source-entry-title"}
    assert parsed["extent"] == {"kind": "text", "start": 2, "end": 5}
    assert parsed["source_snapshot_sha256"] == "a" * 64


def test_publication_rejects_retired_reading_view_slot_refs() -> None:
    assert (
        _parse_slot_ref(
            "reading_block_id=u-all:block-0001;part_index=0;field_id=thesis.title.zh"
        )
        is None
    )
    assert (
        _parse_slot_ref(
            "reading_range_id=u-all:range-0001;part_index=0;field_id=thesis.title.zh"
        )
        is None
    )

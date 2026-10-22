import pytest

from docfit.template.source_spans import SourceSpan, TextSourceExtent, source_span_ref
from docfit.tools.runtime import ToolFailure
from docfit.tools.service import _slot_ref


def test_tool_accepts_canonical_source_entry_slot_ref() -> None:
    span_ref = source_span_ref(
        source_snapshot_sha256="a" * 64,
        source_span=SourceSpan(
            source_entry_id="source-entry-cover-title",
            extent=TextSourceExtent(start=2, end=5),
        ),
    )

    assert _slot_ref("thesis.title.zh", f"{span_ref};field_id=thesis.title.zh") == (
        f"{span_ref};field_id=thesis.title.zh"
    )


@pytest.mark.parametrize("scope_key", ["reading_block_id", "reading_range_id"])
def test_tool_rejects_retired_reading_view_slot_ref(scope_key: str) -> None:
    with pytest.raises(ToolFailure) as failure:
        _slot_ref(
            "thesis.title.zh",
            f"{scope_key}=u-cover:view-0001;part_index=0;field_id=thesis.title.zh",
        )

    assert failure.value.code == "slot_ref_invalid"

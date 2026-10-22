from __future__ import annotations

from pathlib import Path

import pytest

from docfit.tools.runtime import ToolFailure
from docfit.tools.service import DocFitToolService


@pytest.mark.parametrize(
    "legacy_field",
    (
        "semantic_field",
        "query",
        "registry_field",
        "field_id",
        "target_ref",
        "object_ref",
        "locator",
        "paragraph",
        "paragraph_index",
        "scope_ref",
        "source_entry_id",
        "span_ref",
        "slot_ref",
        "reading_block_id",
        "reading_range_id",
        "range_id",
        "operation",
        "operations",
        "edit_operation",
        "target_refs",
        "replacement_text",
        "style_contract_ref",
        "evidence_ref",
        "field_registry",
    ),
)
def test_template_apply_rejects_legacy_direct_write_inputs_before_io(
    tmp_path: Path,
    legacy_field: str,
) -> None:
    service = DocFitToolService(task_root=tmp_path)

    with pytest.raises(ToolFailure) as failure:
        service.apply(
            {
                "schema_version": "docfit_apply_input_v1",
                "candidate_hash": "a" * 64,
                "batch_ref": "work/unused-action.json",
                "output_docx": "work/unused-output.docx",
                legacy_field: "legacy-value",
            }
        )

    assert failure.value.code == "schema_envelope_invalid"
    assert legacy_field in failure.value.message
    assert failure.value.retryable is True

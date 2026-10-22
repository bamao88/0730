from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREP_PATH = PROJECT_ROOT / "prepare_v05_gold_pairs.py"


def _load_prep() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "template_eval_gold_preparation", PREP_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("gold preparation script cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "payload",
    [
        {"field_id": "body.heading.level1"},
        {"canonical_field_id": "body.heading.level2"},
        {"alias": "acknowledgement"},
        {"field_ids": ["title.zh", "body.heading.level3"]},
        {"applies_to": ["body.heading.level4"]},
    ],
)
def test_gold_preparation_rejects_retired_field_ids(payload: dict[str, Any]) -> None:
    module = _load_prep()

    with pytest.raises(ValueError, match="retired field_id"):
        module.require_current_field_values(payload)


def test_gold_preparation_preserves_current_field_ids() -> None:
    module = _load_prep()
    payload = {
        "field_id": "body.heading.outline1",
        "canonical_field_id": "acknowledgement.body",
        "field_ids": ["title.zh", "body.heading.outline2"],
        "applies_to": ["body.heading.outline3"],
    }

    assert module.require_current_field_values(payload) == payload


def test_gold_preparation_rejects_retired_fill_contract_generators(
    tmp_path: Path,
) -> None:
    module = _load_prep()

    with pytest.raises(ValueError, match="retired fill-contract/v1"):
        module.prepare_existing_v1_contract(
            tmp_path / "legacy.yaml",
            school_id="hunau-undergraduate",
            template_hash="0" * 64,
        )

    with pytest.raises(ValueError, match="retired fill-contract/v1"):
        module.prepare_pku_contract(tmp_path / "legacy.yaml", "0" * 64)


def test_gold_preparation_rejects_retired_case_kind_before_docx_transform(
    tmp_path: Path,
) -> None:
    module = _load_prep()
    output_root = tmp_path / "cases"

    with pytest.raises(ValueError, match="retired fill-contract/v1"):
        module.prepare_case(
            "retired-hunau",
            {
                "template": tmp_path / "missing-template.docx",
                "contract": tmp_path / "missing-contract.yaml",
                "kind": "existing_v1",
                "school_id": "hunau-undergraduate",
            },
            output_root,
        )

    assert not (
        output_root / "retired-hunau" / "gold" / module.GOLD_TEMPLATE_NAME
    ).exists()

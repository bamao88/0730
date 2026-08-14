from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from zipfile import ZipFile

import yaml
from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = PROJECT_ROOT / "fixtures" / "build_samples.py"
SCORING_PATH = PROJECT_ROOT / "config" / "scoring-v1.yaml"
SCHEMA_ROOT = PROJECT_ROOT / "schemas"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("template_eval_sample_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("sample builder cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build(module: ModuleType, root: Path) -> dict[str, Any]:
    result = module.build_samples(root, SCORING_PATH)
    assert isinstance(result, dict)
    return result


def test_fix_01_builds_all_manifest_samples(tmp_path: Path) -> None:
    manifest = _build(_load_builder(), tmp_path / "fixtures")

    sample_ids = [sample["sample_id"] for sample in manifest["samples"]]
    assert sample_ids == [f"S{index:02d}-{name}" for index, name in enumerate(
        [
            "minimal-pass",
            "protected-text-changed",
            "protected-style-changed",
            "slot-missing",
            "slot-extra",
            "slot-field-wrong",
            "slot-boundary-wrong",
            "ambiguous-anchor",
            "forbidden-residue",
            "protected-image-missing",
            "unsupported-object",
            "invalid-input",
            "simple-table-structure",
            "simple-formula-field-bookmark",
        ]
    )]
    assert all((tmp_path / "fixtures" / sample_id).is_dir() for sample_id in sample_ids)


def test_fix_02_repeated_builds_are_byte_deterministic(tmp_path: Path) -> None:
    module = _load_builder()
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = _build(module, first_root)
    second = _build(module, second_root)

    assert first == second
    for sample in first["samples"]:
        for filename in sample["assets"]:
            assert (first_root / sample["sample_id"] / filename).read_bytes() == (
                second_root / sample["sample_id"] / filename
            ).read_bytes()


def test_fix_03_generated_packages_and_yaml_are_parseable(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    manifest = _build(_load_builder(), root)

    for sample in manifest["samples"]:
        sample_root = root / sample["sample_id"]
        case = yaml.safe_load((sample_root / "case.yaml").read_text())
        actual_contract = yaml.safe_load((sample_root / "actual-contract.yaml").read_text())
        gold_contract = yaml.safe_load((sample_root / "gold-contract.yaml").read_text())
        assert isinstance(case, dict)
        assert isinstance(actual_contract, dict)
        assert isinstance(gold_contract, dict)
        case_schema = json.loads((SCHEMA_ROOT / "case.schema.json").read_text())
        contract_schema = json.loads((SCHEMA_ROOT / "fill-contract.schema.json").read_text())
        Draft202012Validator(case_schema).validate(case)
        Draft202012Validator(contract_schema).validate(gold_contract)
        if sample["sample_id"] != "S11-invalid-input":
            Draft202012Validator(contract_schema).validate(actual_contract)
        for docx_name in ("actual-template.docx", "gold-template.docx"):
            with ZipFile(sample_root / docx_name) as archive:
                assert archive.testzip() is None
                assert "[Content_Types].xml" in archive.namelist()
        if sample["sample_id"] != "S11-invalid-input":
            with ZipFile(sample_root / "actual-template.docx") as archive:
                assert "word/document.xml" in archive.namelist()

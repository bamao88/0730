from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MATERIALIZER_PATH = PROJECT_ROOT / "materialize_candidate_cases.py"
SOURCE_ROOT = (
    PROJECT_ROOT.parents[1]
    / "temp/manual-gold-preparation/eval-template-truth-candidates"
)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _load_materializer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "template_eval_case_materializer", MATERIALIZER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("case materializer cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_cases_01_materializes_exact_three_case_tree(tmp_path: Path) -> None:
    module = _load_materializer()
    generated = module.materialize_cases(SOURCE_ROOT, tmp_path / "cases")

    assert [path.name for path in generated] == [
        "01-hunau-undergraduate",
        "02-njau-undergraduate",
        "03-pku-graduate",
    ]
    for case_root in generated:
        assert (case_root / "case.yaml").is_file()
        assert (case_root / "gold/template.docx").is_file()
        assert (case_root / "gold/fill-contract.yaml").is_file()
        case = _yaml(case_root / "case.yaml")
        assert case["case_status"] == "candidate"
        assert case["gold_review"]["status"] == "candidate"
        assert case["expected_verdict"] == "INPUT_ERROR"
        contract = _yaml(case_root / "gold/fill-contract.yaml")
        protected = [
            region for region in contract["regions"] if region["owner"] == "protected"
        ]
        assert len(protected) == 3


def test_cases_02_all_word_aliases_equal_contract_registry_fields(tmp_path: Path) -> None:
    module = _load_materializer()
    generated = module.materialize_cases(SOURCE_ROOT, tmp_path / "cases")

    for case_root in generated:
        contract = _yaml(case_root / "gold/fill-contract.yaml")
        expected: dict[str, str] = {}
        for slot in contract["slots"]:
            expected[slot["locator"]["value"]] = slot["field_id"]
            for component in slot.get("component_locators", []):
                locator = component.get("locator", component)
                expected[locator["value"]] = slot["field_id"]
        for region in contract["regions"]:
            if region["owner"] == "slot":
                for locator_name in ("start_locator", "end_locator"):
                    locator = region[locator_name]
                    if locator["type"] == "content_control_tag":
                        expected[locator["value"]] = region["field_ids"][0]

        with ZipFile(case_root / "gold/template.docx") as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        actual: dict[str, str] = {}
        for sdt in root.iter(f"{W}sdt"):
            properties = sdt.find(f"{W}sdtPr")
            if properties is None:
                continue
            tag = properties.find(f"{W}tag")
            alias = properties.find(f"{W}alias")
            if tag is not None:
                assert alias is not None
                actual[tag.get(f"{W}val")] = alias.get(f"{W}val")
        assert actual == expected


def test_cases_03_refuses_to_overwrite_accepted_case(tmp_path: Path) -> None:
    module = _load_materializer()
    output_root = tmp_path / "cases"
    generated = module.materialize_cases(SOURCE_ROOT, output_root)
    first_case = generated[0] / "case.yaml"
    case = _yaml(first_case)
    case["gold_review"]["status"] = "accepted"
    first_case.write_text(
        yaml.safe_dump(case, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="refusing to overwrite accepted case"):
        module.materialize_cases(SOURCE_ROOT, output_root)

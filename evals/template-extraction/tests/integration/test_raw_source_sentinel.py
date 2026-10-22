from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from template_extraction_eval.contracts import (
    InputContractError,
    InputErrorCode,
    load_case,
    load_fill_contract,
)
from template_extraction_eval.sentinel import run_raw_source_sentinel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE_ROOT = REPO_ROOT / "temp/manual-gold-preparation/gold/00-inputs/schools"


@pytest.mark.parametrize(
    ("case_id", "source_name", "expected_code"),
    [
        (
            "01-hunau-undergraduate",
            "hunau-undergraduate__source-template.docx",
            InputErrorCode.CONTRACT_MISMATCH,
        ),
        (
            "02-njau-undergraduate",
            "njau-undergraduate__source-template.docx",
            InputErrorCode.SCHEMA_INVALID,
        ),
        (
            "03-pku-graduate",
            "pku-graduate__source-template.docx",
            InputErrorCode.CONTRACT_MISMATCH,
        ),
    ],
)
def test_sentinel_01_through_03_retired_school_gold_fails_closed(
    case_id: str,
    source_name: str,
    expected_code: InputErrorCode,
) -> None:
    with pytest.raises(InputContractError) as captured:
        run_raw_source_sentinel(
            PROJECT_ROOT / "cases" / case_id / "case.yaml",
            SOURCE_ROOT / source_name,
        )
    assert captured.value.code is expected_code


@pytest.mark.parametrize(
    ("case_id", "expected_code"),
    [
        ("01-hunau-undergraduate", InputErrorCode.CONTRACT_MISMATCH),
        ("02-njau-undergraduate", InputErrorCode.SCHEMA_INVALID),
        ("03-pku-graduate", InputErrorCode.CONTRACT_MISMATCH),
    ],
)
def test_sentinel_04_through_06_retired_gold_self_comparison_fails_closed(
    case_id: str,
    expected_code: InputErrorCode,
) -> None:
    case = load_case(PROJECT_ROOT / "cases" / case_id / "case.yaml")
    with pytest.raises(InputContractError) as captured:
        load_fill_contract(case.gold_contract_path)
    assert captured.value.code is expected_code


def test_hunau_13_toc_keeps_live_field_and_visible_three_level_cache() -> None:
    template = (
        PROJECT_ROOT
        / "cases/01-hunau-undergraduate/gold/final-template.gold.docx"
    )
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    with ZipFile(template) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
        styles = ElementTree.fromstring(archive.read("word/styles.xml"))

    instruction = "".join(
        node.text or "" for node in document.iter(f"{namespace}instrText")
    )
    visible_text = [
        "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        for paragraph in document.iter(f"{namespace}p")
    ]
    style_ids = {
        style.get(f"{namespace}styleId")
        for style in styles.findall(f"{namespace}style")
    }

    assert 'TOC \\o "1-3" \\h \\z \\u \\f C' in instruction
    assert "【自动目录】" not in visible_text
    assert {
        "摘要1",
        "关键词1",
        "1 章节标题1",
        "1.1 节标题1",
        "1.1.1 小节标题1",
        "5 结论1",
        "参考文献2",
        "致谢3",
        "附录4",
    }.issubset(set(visible_text))
    assert {"TOC1", "TOC2", "TOC3"}.issubset(style_ids)

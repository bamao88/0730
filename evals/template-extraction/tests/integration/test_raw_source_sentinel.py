from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from template_extraction_eval.aligned_protected import (
    evaluate_aligned_exhaustive_protected,
)
from template_extraction_eval.contracts import (
    load_case,
    load_eval_config,
    load_field_registry,
    load_fill_contract,
)
from template_extraction_eval.evaluators.slots import evaluate_slots
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import AssertionStatus
from template_extraction_eval.sentinel import run_raw_source_sentinel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE_ROOT = REPO_ROOT / "temp/manual-gold-preparation/gold/00-inputs/schools"


@pytest.mark.parametrize(
    (
        "case_id",
        "source_name",
        "slot_count",
        "gold_protected_atoms",
        "matched_paragraphs",
        "missing_paragraphs",
        "protected_failures",
        "protected_unknown",
    ),
    [
        (
            "01-hunau-undergraduate",
            "hunau-undergraduate__source-template.docx",
            31,
            1734,
            494,
            21,
            127,
            9,
        ),
        (
            "02-njau-undergraduate",
            "njau-undergraduate__source-template.docx",
            25,
            640,
            128,
            18,
            174,
            8,
        ),
        (
            "03-pku-graduate",
            "pku-graduate__source-template.docx",
            22,
            1184,
            150,
            40,
            286,
            44,
        ),
    ],
)
def test_sentinel_01_through_03_raw_source_exposes_both_view_outcomes(
    case_id: str,
    source_name: str,
    slot_count: int,
    gold_protected_atoms: int,
    matched_paragraphs: int,
    missing_paragraphs: int,
    protected_failures: int,
    protected_unknown: int,
) -> None:
    result = run_raw_source_sentinel(
        PROJECT_ROOT / "cases" / case_id / "case.yaml",
        SOURCE_ROOT / source_name,
    )
    outcome = result["result"]
    assert result["diagnostic_only"] is True
    assert outcome["verdict"] == "FAIL"
    assert outcome["score"] == outcome["protected"]["score"]
    assert outcome["analysis_coverage"] > 0.98
    assert outcome["responsibility_coverage"] == 1
    assert outcome["protected"]["scope"] == "all_clean_gold_protected_facts"
    assert outcome["protected"]["status"] == "FAIL"
    audit = outcome["protected"]["audit"]
    assert audit["responsibility_coverage"] == 1
    assert audit["expected_gold_protected_atoms"] == gold_protected_atoms
    assert audit["asserted_gold_protected_atoms"] == gold_protected_atoms
    assert audit["matched_paragraphs"] == matched_paragraphs
    assert audit["missing_gold_paragraphs"] == missing_paragraphs
    assert outcome["protected"]["counts"]["FAIL"] == protected_failures
    assert outcome["protected"]["counts"]["UNKNOWN"] == protected_unknown
    assert outcome["slot"]["status"] == "FAIL"
    assert outcome["slot"]["score"] == 0
    assert outcome["slot"]["counts"]["FAIL"] == slot_count * 4
    assert len(result["paragraph_alignment"]) >= matched_paragraphs


@pytest.mark.parametrize(
    "case_id",
    [
        "01-hunau-undergraduate",
        "02-njau-undergraduate",
        "03-pku-graduate",
    ],
)
def test_sentinel_04_through_06_real_gold_self_comparison_is_exact(
    case_id: str,
) -> None:
    case = load_case(PROJECT_ROOT / "cases" / case_id / "case.yaml")
    contract = load_fill_contract(case.gold_contract_path)
    config = load_eval_config(case.eval_config_ref.path)
    facts = analyze_docx(case.gold_template_path)

    audit = evaluate_aligned_exhaustive_protected(
        facts,
        facts,
        contract,
        contract,
        config,
    )

    assert audit.responsibility_coverage == 1
    assert len(audit.assertions) == audit.gold_inventory.protected
    assert all(item.status is AssertionStatus.PASS for item in audit.assertions)


HUNAU_BODY_TAGS = {
    "docfit.body.chapter_title",
    "docfit.body.chapter_body",
    "docfit.body.section_title",
    "docfit.body.section_body",
    "docfit.body.subsection_title",
    "docfit.body.subsection_body",
    "docfit.conclusion.title",
    "docfit.conclusion.body",
}


def _hunau_inputs():
    case = load_case(PROJECT_ROOT / "cases/01-hunau-undergraduate/case.yaml")
    contract = load_fill_contract(case.gold_contract_path)
    config = load_eval_config(case.eval_config_ref.path)
    registry = load_field_registry(case.registry_ref.path)
    facts = analyze_docx(case.gold_template_path)
    return contract, config, registry, facts


def test_hunau_07_gold_exposes_all_granular_body_markers() -> None:
    contract, _, _, facts = _hunau_inputs()
    contract_tags = {
        slot.locator.value
        for slot in contract.slots
        if slot.locator.value in HUNAU_BODY_TAGS
    }
    template_tags = {tag for tag in facts.controls_by_tag if tag in HUNAU_BODY_TAGS}

    assert contract_tags == HUNAU_BODY_TAGS
    assert template_tags == HUNAU_BODY_TAGS
    assert "docfit.body.main" not in facts.controls_by_tag


def test_hunau_08_body_marker_aliases_match_registry_fields() -> None:
    contract, _, _, facts = _hunau_inputs()
    expected_aliases = {
        slot.locator.value: slot.field_id
        for slot in contract.slots
        if slot.locator.value in HUNAU_BODY_TAGS
    }

    assert {
        tag: facts.controls_by_tag[tag].alias for tag in HUNAU_BODY_TAGS
    } == expected_aliases


def test_hunau_09_body_slots_and_corrected_margins_are_self_consistent() -> None:
    contract, config, registry, facts = _hunau_inputs()
    assertions = evaluate_slots(
        contract,
        contract,
        facts,
        facts,
        registry,
        config,
    )
    body_slot_ids = {
        slot.slot_id for slot in contract.slots if slot.locator.value in HUNAU_BODY_TAGS
    }
    body_assertions = [item for item in assertions if item.slot_id in body_slot_ids]
    document_runs = [
        run
        for paragraph in facts.paragraphs
        if paragraph.part == "word/document.xml"
        for run in paragraph.runs
    ]

    assert len(body_assertions) == len(HUNAU_BODY_TAGS) * 5
    assert all(item.status is AssertionStatus.PASS for item in body_assertions)
    assert {run.effective_style.page["margin_top_pt"] for run in document_runs} == {56.7}
    assert {run.effective_style.page["margin_bottom_pt"] for run in document_runs} == {
        56.7
    }


def test_hunau_10_all_managed_controls_are_word_placeholders() -> None:
    _, _, _, facts = _hunau_inputs()
    managed = [control for control in facts.controls if control.tag is not None]

    assert len(managed) == 31
    assert all(control.showing_placeholder for control in managed)


def test_hunau_11_all_placeholder_text_uses_final_value_color() -> None:
    _, _, _, facts = _hunau_inputs()
    managed = [control for control in facts.controls if control.tag is not None]

    assert {control.effective_style.font.get("color") for control in managed} == {
        "000000"
    }


def test_hunau_12_chinese_abstract_value_style_is_not_bold() -> None:
    contract, _, _, facts = _hunau_inputs()
    abstract_slot = next(slot for slot in contract.slots if slot.slot_id == "slot.abstract.cn")
    abstract_control = facts.controls_by_tag["docfit.abstract.cn"]
    keywords_control = facts.controls_by_tag["docfit.keywords.cn"]

    assert abstract_slot.expected_value_style.font["bold"] is False
    assert abstract_control.effective_style.font["bold"] is False
    assert keywords_control.effective_style.font["bold"] is False


def test_hunau_13_toc_keeps_live_field_and_visible_three_level_cache() -> None:
    template = PROJECT_ROOT / "cases/01-hunau-undergraduate/gold/template.docx"
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

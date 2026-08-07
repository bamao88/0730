from __future__ import annotations

from pathlib import Path

from template_extraction_eval.aligned_protected import (
    evaluate_aligned_exhaustive_protected,
)
from template_extraction_eval.models import (
    AssertionStatus,
    ContentControlFact,
    DocumentFacts,
    EffectiveStyle,
    EvalConfig,
    FillContract,
    Locator,
    ParagraphFact,
    RunFact,
    SlotContract,
)


def _style(size: float = 12) -> EffectiveStyle:
    return EffectiveStyle(
        font={"size_pt": size},
        paragraph={"alignment": "left"},
        container={},
        page={"margin_top_pt": 72, "margin_bottom_pt": 72},
    )


def _paragraph(index: int, text: str, *, style: EffectiveStyle | None = None) -> ParagraphFact:
    effective_style = style or _style()
    return ParagraphFact(
        story="document",
        part="word/document.xml",
        paragraph_index=index,
        section_index=0,
        path=f"word/document.xml:document:p[{index}]",
        text=text,
        tokens=(f"TEXT:{text}",) if text else (),
        runs=(
            RunFact(
                text=text,
                start=0,
                end=len(text),
                style_id=None,
                effective_style=effective_style,
            ),
        ),
    )


def _facts(
    paragraphs: tuple[ParagraphFact, ...],
    *,
    controls: tuple[ContentControlFact, ...] = (),
) -> DocumentFacts:
    return DocumentFacts(
        document_sha256="0" * 64,
        parts=("word/document.xml",),
        relationships=(),
        paragraphs=paragraphs,
        controls=controls,
        tables=(),
        objects=(),
        unsupported=(),
    )


def _contract(*, slots: tuple[SlotContract, ...] = ()) -> FillContract:
    return FillContract(
        schema_version="docfit-template-fill-contract/v1",
        contract_id="synthetic.aligned",
        template_sha256="0" * 64,
        registry_id="registry",
        registry_version="1",
        registry_sha256="0" * 64,
        marker_protocol="docfit-content-control-marker/v1",
        regions=(),
        slots=slots,
    )


def _config() -> EvalConfig:
    return EvalConfig(
        schema_version="docfit-template-extraction-eval-config/v1",
        config_id="synthetic",
        marker_protocol="docfit-content-control-marker/v1",
        field_identity_property="w:alias",
        slot_identity_property="w:tag",
        internal_id_property="w:id",
        tolerances={"font_size_pt": 0.01, "distance_pt": 0.05},
        normalization=(),
        scoring_path=Path(__file__),
        scoring_version="v1",
        scoring_sha256="0" * 64,
        sha256="0" * 64,
    )


def test_apr_01_exact_document_asserts_every_gold_protected_atom() -> None:
    facts = _facts((_paragraph(0, "固定标题"),))
    audit = evaluate_aligned_exhaustive_protected(
        facts,
        facts,
        _contract(),
        _contract(),
        _config(),
    )

    assert audit.responsibility_coverage == 1
    assert len(audit.assertions) == audit.gold_inventory.protected == 4
    assert {item.status for item in audit.assertions} == {AssertionStatus.PASS}


def test_apr_02_actual_leading_instruction_does_not_shift_protected_identity() -> None:
    gold = _facts((_paragraph(0, "固定标题"), _paragraph(1, "固定正文")))
    actual = _facts(
        (
            _paragraph(0, "应删除的说明"),
            _paragraph(1, "固定标题"),
            _paragraph(2, "固定正文"),
        )
    )
    audit = evaluate_aligned_exhaustive_protected(
        gold,
        actual,
        _contract(),
        _contract(),
        _config(),
    )

    aligned_indices = [
        item.actual.paragraph.paragraph_index
        for item in audit.alignments
        if item.actual
    ]
    assert aligned_indices == [1, 2]
    assert all(item.status is AssertionStatus.PASS for item in audit.assertions)


def test_apr_03_missing_gold_paragraph_fails_all_of_its_protected_facts() -> None:
    gold = _facts((_paragraph(0, "必须保留"),))
    actual = _facts(())
    audit = evaluate_aligned_exhaustive_protected(
        gold,
        actual,
        _contract(),
        _contract(),
        _config(),
    )

    failures = [item for item in audit.assertions if item.status is AssertionStatus.FAIL]
    assert len(failures) == 3
    assert {item.dimension for item in failures} == {
        "protected.content",
        "protected.structure",
        "protected.style",
    }


def test_apr_04_equal_text_with_style_change_is_reported() -> None:
    gold = _facts((_paragraph(0, "固定标题", style=_style(12)),))
    actual = _facts((_paragraph(0, "固定标题", style=_style(14)),))
    audit = evaluate_aligned_exhaustive_protected(
        gold,
        actual,
        _contract(),
        _contract(),
        _config(),
    )

    failures = [item for item in audit.assertions if item.status is AssertionStatus.FAIL]
    assert len(failures) == 1
    assert failures[0].dimension == "protected.style"


def test_apr_05_inline_slot_still_checks_the_fixed_label() -> None:
    slot_style = _style()
    locator = Locator(
        type="content_control_tag",
        story="document",
        part="word/document.xml",
        expected_match_count=1,
        value="slot.student_name",
    )
    slot = SlotContract(
        slot_id="student_name",
        field_id="student.name",
        content_type="text",
        required=True,
        locator=locator,
        expected_value_style=slot_style,
    )
    gold_paragraph = ParagraphFact(
        story="document",
        part="word/document.xml",
        paragraph_index=0,
        section_index=0,
        path="word/document.xml:document:p[0]",
        text="姓名：【姓名】",
        tokens=("TEXT:姓名：", "TEXT:【姓名】"),
        runs=(
            RunFact("姓名：", 0, 3, None, slot_style),
            RunFact("【姓名】", 3, 7, None, slot_style),
        ),
    )
    control = ContentControlFact(
        alias="student.name",
        tag="slot.student_name",
        internal_id="1",
        story="document",
        part="word/document.xml",
        paragraph_index=0,
        start=3,
        end=7,
        text="【姓名】",
        effective_style=slot_style,
    )
    audit = evaluate_aligned_exhaustive_protected(
        _facts((gold_paragraph,), controls=(control,)),
        _facts((_paragraph(0, "姓名：张三"),)),
        _contract(slots=(slot,)),
        _contract(),
        _config(),
    )

    content = next(item for item in audit.assertions if item.dimension == "protected.content")
    assert content.status is AssertionStatus.PASS
    assert content.expected == "姓名：<SLOT>"


def test_apr_06_slot_only_paragraph_is_not_counted_as_protected_content() -> None:
    slot_style = _style()
    locator = Locator(
        type="content_control_tag",
        story="document",
        part="word/document.xml",
        expected_match_count=1,
        value="slot.title",
    )
    slot = SlotContract(
        slot_id="title",
        field_id="thesis.title.cn",
        content_type="text",
        required=True,
        locator=locator,
        expected_value_style=slot_style,
    )
    paragraph = _paragraph(0, "【题目】")
    control = ContentControlFact(
        alias="thesis.title.cn",
        tag="slot.title",
        internal_id="1",
        story="document",
        part="word/document.xml",
        paragraph_index=0,
        start=0,
        end=4,
        text="【题目】",
        effective_style=slot_style,
    )
    audit = evaluate_aligned_exhaustive_protected(
        _facts((paragraph,), controls=(control,)),
        _facts((_paragraph(0, "原始题目"),)),
        _contract(slots=(slot,)),
        _contract(),
        _config(),
    )

    assert {item.dimension for item in audit.assertions} == {"protected.structure"}
    assert audit.gold_inventory.protected == 1

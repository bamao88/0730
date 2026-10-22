from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization import (
    MaterializationContextKind,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
    ScopeRef,
    apply_fixed_content_cleanup,
    explicit_materialization_field_ids,
    generated_content_policy_receipts,
    is_delete_treatment,
    is_instruction_parenthetical,
    manual_table_cell_policy_receipts,
    materialize_body_structure,
    materialize_slot_paragraph,
    normalize_square_placeholders,
    should_remove_paragraph,
    strip_instruction_parentheticals,
)
from docfit.template.materialization import (
    build_shadow_materialization_plan as _build_shadow_materialization_plan,
)
from docfit.template.materialization import (
    compile_materialization_intents as _compile_materialization_intents,
)
from docfit.tools.runtime import ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _paragraph(text: str) -> ET.Element:
    return ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>{text}</w:t></w:r></w:p>'
    )


def _text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{W}t"))


def _slot_aliases(paragraph: ET.Element) -> list[str]:
    return [
        alias.get(W + "val", "")
        for alias in paragraph.iter(W + "alias")
        if alias.get(W + "val")
    ]


def _slot_tags(paragraph: ET.Element) -> list[str]:
    return [
        tag.get(W + "val", "")
        for tag in paragraph.iter(W + "tag")
        if tag.get(W + "val")
    ]


def _slot_run_properties(paragraph: ET.Element, field_id: str) -> ET.Element:
    for control in paragraph.iter(W + "sdt"):
        alias = control.find(f"{W}sdtPr/{W}alias")
        if alias is not None and alias.get(W + "val") == field_id:
            properties = control.find(f".//{W}sdtContent/{W}r/{W}rPr")
            assert properties is not None
            return properties
    raise AssertionError(f"missing slot for {field_id}")


def _registry(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "field-registry.yaml"
    path.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
                "  - field_id: advisor.name.zh",
                "    label: 导师姓名",
                "    content_type: text",
                "  - field_id: advisor.title",
                "    label: 导师职称",
                "    content_type: text",
                "  - field_id: body.chapters",
                "    label: 正文章节集合",
                "    content_type: section",
                "  - field_id: body.heading.outline1",
                "    label: 章标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: generated.toc",
                "    label: 目录",
                "    content_type: section",
                "    value_sources:",
                "      - system_generated",
                "  - field_id: body.paragraph",
                "    label: 正文段落",
                "    content_type: rich_text",
                "    parent_field_id: body.chapters",
                "  - field_id: keywords.en",
                "    label: 英文关键词",
                "    content_type: text",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _registry_with_centered_title_layout(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "field-registry-with-layout.yaml"
    path.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
                "    materialization:",
                "      slot_layout: centered_title",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _plan(
    registry: FieldRegistrySnapshot,
    judgments: list[dict[str, object]],
):
    return compile_materialization_intents(
        review={"semantic_judgments": judgments},
        registry=registry,
    ).plan


def _with_current_vocabulary(
    registry: FieldRegistrySnapshot,
    inventory: dict[str, object],
    review: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    vocabulary = registry.pre_input_vocabulary()
    return (
        {
            **inventory,
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
        },
        {
            **review,
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
        },
    )


def compile_materialization_intents(
    *,
    review: dict[str, object],
    registry: FieldRegistrySnapshot,
):
    vocabulary = registry.pre_input_vocabulary()
    return _compile_materialization_intents(
        review={
            **review,
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
        },
        registry=registry,
    )


def build_shadow_materialization_plan(
    *,
    inventory: dict[str, object],
    review: dict[str, object],
    registry: FieldRegistrySnapshot,
):
    current_inventory, current_review = _with_current_vocabulary(
        registry,
        inventory,
        review,
    )
    return _build_shadow_materialization_plan(
        inventory=current_inventory,
        review=current_review,
        registry=registry,
    )


def _span(
    *,
    block_id: str,
    part_index: int,
    role: str,
    field_id: str | None = None,
) -> dict[str, object]:
    span_ref = f"reading_block_id={block_id};part_index={part_index}"
    span: dict[str, object] = {
        "span_ref": span_ref,
        "scope": {"reading_block_id": block_id},
        "reading_block_id": block_id,
        "part_index": part_index,
        "role": role,
        "text": "x",
    }
    if field_id is not None:
        span["field_id"] = field_id
        span["slot_ref"] = f"{span_ref};field_id={field_id}"
    return span


def _judgment(
    *,
    block_id: str,
    role: str,
    field_id: str | None = None,
) -> dict[str, object]:
    part: dict[str, object] = {"text": "x", "role": role}
    if field_id is not None:
        part["field_id"] = field_id
    return {
        "scope": {"reading_block_id": block_id},
        "parts": [part],
        "resolved_spans": [
            _span(block_id=block_id, part_index=0, role=role, field_id=field_id)
        ],
    }


def _indexed_parts(*parts: dict[str, object]) -> list[tuple[int, dict[str, object]]]:
    return list(enumerate(parts))


def test_instruction_notes_strip_format_parentheticals_without_removing_semantic_text() -> None:
    assert is_instruction_parenthetical("小三号黑体，加粗，居中") is True
    assert is_instruction_parenthetical("设计") is False
    assert strip_instruction_parentheticals("参考文献（小三号黑体，加粗，居中）") == "参考文献"
    assert strip_instruction_parentheticals("毕业论文（设计）") == "毕业论文（设计）"
    assert (
        strip_instruction_parentheticals("出版年，卷（期）：页码A-B.")
        == "出版年，卷（期）：页码A-B."
    )


def test_layout_placeholders_convert_only_fixed_heading_intercharacter_boxes() -> None:
    assert (
        normalize_square_placeholders(
            "致□□谢",
            context_kind=MaterializationContextKind.FIXED_HEADING.value,
        )
        == "致　　谢"
    )
    assert (
        normalize_square_placeholders(
            "学□□生：",
            context_kind=MaterializationContextKind.FIXED_HEADING.value,
        )
        == "学□□生："
    )
    assert (
        normalize_square_placeholders(
            "□□摘要",
            context_kind=MaterializationContextKind.PARAGRAPH_INDENT.value,
        )
        == "□□摘要"
    )


def test_fixed_content_handler_strips_visible_format_notes_and_spacing() -> None:
    paragraph = _paragraph("致□□谢  (小三号黑体，居中)")

    changed = apply_fixed_content_cleanup(
        paragraph,
        context_kind=MaterializationContextKind.FIXED_HEADING.value,
    )

    assert changed is True
    assert _text(paragraph) == "致　　谢"


def test_fixed_content_handler_ignores_non_fixed_context() -> None:
    paragraph = _paragraph("□□摘□要（小四黑体）：……")

    changed = apply_fixed_content_cleanup(
        paragraph,
        context_kind=MaterializationContextKind.SAMPLE_VALUE.value,
    )

    assert changed is False
    assert _text(paragraph) == "□□摘□要（小四黑体）：……"


def test_cleanup_handler_keeps_delete_semantics_in_cleanup_boundary() -> None:
    judgment = {"parts": [{"text": "附件1：格式说明", "role": "cleanup"}]}

    assert is_delete_treatment(judgment) is True
    assert should_remove_paragraph(judgment) is True
    assert (
        is_delete_treatment(
            {
                "clean_template_treatment": "template_note_deletion",
                "semantic_role": "template_instruction_note",
            }
        )
        is False
    )


def test_field_binding_reads_only_ordered_part_field_ids() -> None:
    judgment = {
        "parts": [
            {"text": "导师", "role": "fixed_label", "field_id": "thesis.title.zh"},
            {"text": "×××", "role": "fill_slot", "field_id": "advisor.name.zh"},
            {"text": "教授", "role": "fill_slot", "field_id": "advisor.title"},
            {"text": "old", "role": "cleanup", "field_id": "unknown.field"},
        ],
        "registry_field": {"field_id": "thesis.title.zh"},
        "judgment": "Natural language mentions thesis.title.zh but must not bind it.",
    }

    assert explicit_materialization_field_ids(judgment) == [
        "advisor.name.zh",
        "advisor.title",
    ]
    toc_judgment = {
        "parts": [
            {"text": "目 录", "role": "generated_content", "field_id": "generated.toc"}
        ]
    }
    assert explicit_materialization_field_ids(toc_judgment) == ["generated.toc"]


def test_slot_handler_materializes_title_and_composite_rows(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    title = _paragraph("毕业论文（设计）中文题目（小二黑体，加粗，居中）")
    advisor = _paragraph("指导老师及职称：×××□教授")

    title_ops = materialize_slot_paragraph(
        paragraph=title,
        block_id="cover:block-0001",
        registry=registry,
        indexed_ordered_parts=_indexed_parts(
            {
                "text": "毕业论文（设计）中文题目（小二黑体，加粗，居中）",
                "role": "fill_slot",
                "field_id": "thesis.title.zh",
            }
        ),
        resolved_spans=[
            _span(
                block_id="cover:block-0001",
                part_index=0,
                role="fill_slot",
                field_id="thesis.title.zh",
            )
        ],
    )
    advisor_ops = materialize_slot_paragraph(
        paragraph=advisor,
        block_id="cover:block-0002",
        registry=registry,
        indexed_ordered_parts=_indexed_parts(
            {"text": "指导老师及职称：", "role": "fixed_label"},
            {"text": "×××", "role": "fill_slot", "field_id": "advisor.name.zh"},
            {"text": "□", "role": "cleanup"},
            {"text": "教授", "role": "fill_slot", "field_id": "advisor.title"},
        ),
        resolved_spans=[
            _span(
                block_id="cover:block-0002",
                part_index=0,
                role="fixed_label",
            ),
            _span(
                block_id="cover:block-0002",
                part_index=1,
                role="fill_slot",
                field_id="advisor.name.zh",
            ),
            _span(
                block_id="cover:block-0002",
                part_index=2,
                role="cleanup",
            ),
            _span(
                block_id="cover:block-0002",
                part_index=3,
                role="fill_slot",
                field_id="advisor.title",
            ),
        ],
    )

    assert title_ops == [
        {
            "action": "materialize_slot",
            "field_id": "thesis.title.zh",
            "block_id": "cover:block-0001",
            "part_index": 0,
            "span_ref": "reading_block_id=cover:block-0001;part_index=0",
            "slot_ref": (
                "reading_block_id=cover:block-0001;part_index=0;"
                "field_id=thesis.title.zh"
            ),
        }
    ]
    assert advisor_ops == [
        {
            "action": "materialize_slot",
            "field_id": "advisor.name.zh",
            "block_id": "cover:block-0002",
            "part_index": 1,
            "span_ref": "reading_block_id=cover:block-0002;part_index=1",
            "slot_ref": (
                "reading_block_id=cover:block-0002;part_index=1;"
                "field_id=advisor.name.zh"
            ),
        },
        {
            "action": "materialize_slot",
            "field_id": "advisor.title",
            "block_id": "cover:block-0002",
            "part_index": 3,
            "span_ref": "reading_block_id=cover:block-0002;part_index=3",
            "slot_ref": (
                "reading_block_id=cover:block-0002;part_index=3;"
                "field_id=advisor.title"
            ),
        },
    ]
    assert _text(title) == "【中文题目】"
    assert _text(advisor) == "指导老师及职称：【填】【填】"
    assert _slot_aliases(title) == ["thesis.title.zh"]
    assert _slot_aliases(advisor) == ["advisor.name.zh", "advisor.title"]
    assert _slot_tags(title) == [
        "reading_block_id=cover:block-0001;part_index=0;field_id=thesis.title.zh"
    ]
    assert _slot_tags(advisor) == [
        "reading_block_id=cover:block-0002;part_index=1;field_id=advisor.name.zh",
        "reading_block_id=cover:block-0002;part_index=3;field_id=advisor.title",
    ]


def test_slot_handler_compacts_standalone_placeholder_when_layout_requires_it(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    paragraph = _paragraph("                                    ")

    materialize_slot_paragraph(
        paragraph=paragraph,
        block_id="cover:block-date",
        registry=registry,
        indexed_ordered_parts=_indexed_parts(
            {
                "text": "                                    ",
                "role": "fill_slot",
                "field_id": "thesis.title.zh",
            }
        ),
        resolved_spans=[
            _span(
                block_id="cover:block-date",
                part_index=0,
                role="fill_slot",
                field_id="thesis.title.zh",
            )
        ],
        compact_placeholders=True,
    )

    assert _text(paragraph) == "【填】"
    assert _slot_aliases(paragraph) == ["thesis.title.zh"]


def test_slot_handler_removes_visible_style_instruction_text(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    paragraph = _paragraph("论文题目（小二号黑体）")

    materialize_slot_paragraph(
        paragraph=paragraph,
        block_id="abstract:block-title",
        registry=registry,
        indexed_ordered_parts=_indexed_parts(
            {"text": "论文题目", "role": "fill_slot", "field_id": "thesis.title.zh"},
            {"text": "（小二号黑体）", "role": "style_only"},
        ),
        resolved_spans=[
            _span(
                block_id="abstract:block-title",
                part_index=0,
                role="fill_slot",
                field_id="thesis.title.zh",
            ),
            _span(
                block_id="abstract:block-title",
                part_index=1,
                role="style_only",
            ),
        ],
    )

    assert _text(paragraph) == "【中文题目】"
    assert "小二号黑体" not in _text(paragraph)


def test_slot_handler_uses_registry_materialization_layout_not_field_id_prefix(
    tmp_path: Path,
) -> None:
    def title_paragraph() -> ET.Element:
        return ET.fromstring(
            f'<w:p xmlns:w="{W_NS}">'
            '<w:pPr><w:ind w:firstLineChars="295" w:firstLine="829"/>'
            '<w:jc w:val="right"/></w:pPr>'
            "<w:r><w:t>中文论文题目</w:t></w:r>"
            "</w:p>"
        )

    def materialize(paragraph: ET.Element, registry: FieldRegistrySnapshot) -> None:
        materialize_slot_paragraph(
            paragraph=paragraph,
            block_id="cover:block-0001",
            registry=registry,
            indexed_ordered_parts=_indexed_parts(
                {
                    "text": "中文论文题目",
                    "role": "fill_slot",
                    "field_id": "thesis.title.zh",
                }
            ),
            resolved_spans=[
                _span(
                    block_id="cover:block-0001",
                    part_index=0,
                    role="fill_slot",
                    field_id="thesis.title.zh",
                )
            ],
        )

    plain_title = title_paragraph()
    materialize(plain_title, _registry(tmp_path))

    plain_properties = plain_title.find(W + "pPr")
    assert plain_properties is not None
    assert plain_properties.find(W + "ind") is not None
    plain_alignment = plain_properties.find(W + "jc")
    assert plain_alignment is not None
    assert plain_alignment.get(W + "val") == "right"

    centered_title = title_paragraph()
    materialize(centered_title, _registry_with_centered_title_layout(tmp_path))

    centered_properties = centered_title.find(W + "pPr")
    assert centered_properties is not None
    assert centered_properties.find(W + "ind") is None
    centered_alignment = centered_properties.find(W + "jc")
    assert centered_alignment is not None
    assert centered_alignment.get(W + "val") == "center"


def test_slot_handler_rejects_slot_ref_not_derived_from_span_ref(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    title = _paragraph("毕业论文题目")
    span = _span(
        block_id="cover:block-0001",
        part_index=0,
        role="fill_slot",
        field_id="thesis.title.zh",
    )
    span["slot_ref"] = (
        "reading_block_id=cover:block-0001;part_index=1;"
        "field_id=thesis.title.zh"
    )

    with pytest.raises(ToolFailure) as failure:
        materialize_slot_paragraph(
            paragraph=title,
            block_id="cover:block-0001",
            registry=registry,
            indexed_ordered_parts=_indexed_parts(
                {
                    "text": "毕业论文题目",
                    "role": "fill_slot",
                    "field_id": "thesis.title.zh",
                }
            ),
            resolved_spans=[span],
        )

    assert failure.value.code == "materialization_slot_ref_missing"
    assert _slot_aliases(title) == []


def test_slot_handler_uses_part_local_run_properties_for_inline_slot(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    paragraph = ET.fromstring(
        f"""<w:p xmlns:w="{W_NS}">
        <w:r>
          <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
          <w:t>KEY WORDS：</w:t>
        </w:r>
        <w:r>
          <w:rPr><w:rFonts w:ascii="宋体" w:hAnsi="宋体"/><w:sz w:val="24"/></w:rPr>
          <w:t>×××；×××</w:t>
        </w:r>
        </w:p>"""
    )

    materialize_slot_paragraph(
        paragraph=paragraph,
        block_id="abstract-en:block-0001",
        registry=registry,
        indexed_ordered_parts=_indexed_parts(
            {"text": "KEY WORDS：", "role": "fixed_label"},
            {"text": "×××；×××", "role": "fill_slot", "field_id": "keywords.en"},
        ),
        resolved_spans=[
            _span(
                block_id="abstract-en:block-0001",
                part_index=0,
                role="fixed_label",
            ),
            _span(
                block_id="abstract-en:block-0001",
                part_index=1,
                role="fill_slot",
                field_id="keywords.en",
            ),
        ],
    )

    properties = _slot_run_properties(paragraph, "keywords.en")
    fonts = properties.find(f"{W}rFonts")
    assert fonts is not None
    assert fonts.get(W + "ascii") == "宋体"
    assert fonts.get(W + "hAnsi") == "宋体"
    assert properties.find(f"{W}b") is None
    size = properties.find(f"{W}sz")
    assert size is not None
    assert size.get(W + "val") == "24"


def test_slot_handler_rejects_retired_semantic_part_index_input(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    paragraph = _paragraph("指导老师：×××")

    with pytest.raises(ToolFailure) as failure:
        materialize_slot_paragraph(
            paragraph=paragraph,
            block_id="cover:block-0001",
            registry=registry,
            indexed_ordered_parts=[
                (
                    0,
                    {
                        "text": "×××",
                        "role": "fill_slot",
                        "field_id": "advisor.name.zh",
                        "semantic_part_index": 7,
                    },
                )
            ],
            resolved_spans=[
                _span(
                    block_id="cover:block-0001",
                    part_index=7,
                    role="fill_slot",
                    field_id="advisor.name.zh",
                )
            ],
        )

    assert failure.value.code == "materialization_legacy_semantic_part_index"


def test_body_structure_handler_rejects_legacy_reading_block_member_order(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    document = ET.fromstring(
        f"""<w:document xmlns:w="{W_NS}">
          <w:body>
            <w:p><w:r><w:t>1□前言</w:t></w:r></w:p>
            <w:p><w:r><w:t>□□……</w:t></w:r></w:p>
          </w:body>
        </w:document>"""
    )
    paragraphs = list(document.iter(W + "p"))

    operations, cleanup, selected = materialize_body_structure(
        document=document,
        by_block={
            "body:block-0001": paragraphs[0],
            "body:block-0002": paragraphs[1],
        },
        registry=registry,
        inventory={
            "reading_blocks": [
                {"block_id": "body:block-0001"},
                {"block_id": "body:block-0002"},
            ]
        },
        plan=_plan(
            registry,
            [
                {
                    "scope": {"reading_block_id": "body:block-0001"},
                    "parts": [
                        {
                            "text": "1□前言",
                            "role": "body_structure",
                            "field_id": "body.heading.outline1",
                        },
                        {
                            "text": "□□……",
                            "role": "body_structure",
                            "field_id": "body.paragraph",
                        },
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="body:block-0001",
                            part_index=0,
                            role="body_structure",
                            field_id="body.heading.outline1",
                        ),
                        _span(
                            block_id="body:block-0002",
                            part_index=1,
                            role="body_structure",
                            field_id="body.paragraph",
                        ),
                    ],
                }
            ],
        ),
        removed=set(),
    )

    assert selected == set()
    assert cleanup == []
    assert operations == []
    assert _slot_aliases(document) == []


def test_body_structure_handler_rejects_member_slot_ref_not_derived_from_span_ref(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    document = ET.fromstring(
        f"""<w:document xmlns:w="{W_NS}">
          <w:body>
            <w:p><w:r><w:t>1□前言</w:t></w:r></w:p>
          </w:body>
        </w:document>"""
    )
    paragraphs = list(document.iter(W + "p"))
    span_ref = "reading_block_id=body:block-0001;part_index=0"
    plan = MaterializationPlan(
        plan_ref="materialization-plan-test",
        intents=(
            MaterializationIntent(
                intent_ref="intent-test",
                intent_type=MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE,
                source_judgment_refs=("semantic_judgments[0]",),
                scope_refs=(ScopeRef(kind="reading_block", ref_id="body:block-0001"),),
                field_ids=("body.heading.outline1",),
                payload={
                    "structure_ref": "body.chapters",
                    "members": ["body.heading.outline1"],
                    "member_bindings": [
                        {
                            "block_id": "body:block-0001",
                            "member_field_id": "body.heading.outline1",
                            "span_ref": span_ref,
                            "slot_ref": f"{span_ref};field_id=body.paragraph",
                        }
                    ],
                },
            ),
        ),
        unsupported=(),
        source_review_digest="0" * 64,
    )

    operations, cleanup, selected = materialize_body_structure(
        document=document,
        by_block={"body:block-0001": paragraphs[0]},
        registry=registry,
        inventory={"reading_blocks": [{"block_id": "body:block-0001"}]},
        plan=plan,
        removed=set(),
    )

    assert operations == []
    assert cleanup == []
    assert selected == set()
    assert _slot_aliases(document) == []


def test_body_structure_handler_rejects_contiguous_legacy_reading_block_intents(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    document = ET.fromstring(
        f"""<w:document xmlns:w="{W_NS}">
          <w:body>
            <w:p><w:r><w:t>1□前言</w:t></w:r></w:p>
            <w:p><w:r><w:t>□□……</w:t></w:r></w:p>
          </w:body>
        </w:document>"""
    )
    paragraphs = list(document.iter(W + "p"))

    operations, cleanup, selected = materialize_body_structure(
        document=document,
        by_block={
            "body:block-0001": paragraphs[0],
            "body:block-0002": paragraphs[1],
        },
        registry=registry,
        inventory={
            "reading_blocks": [
                {"block_id": "body:block-0001", "order": 1},
                {"block_id": "body:block-0002", "order": 2},
            ]
        },
        plan=build_shadow_materialization_plan(
            inventory={
                "reading_blocks": [
                    {"block_id": "body:block-0001", "order": 1},
                    {"block_id": "body:block-0002", "order": 2},
                ]
            },
            review={
                "semantic_judgments": [
                    _judgment(
                        block_id="body:block-0001",
                        role="body_structure",
                        field_id="body.heading.outline1",
                    ),
                    _judgment(
                        block_id="body:block-0002",
                        role="body_structure",
                        field_id="body.paragraph",
                    ),
                ]
            },
            registry=registry,
        ).plan,
        removed=set(),
    )

    assert selected == set()
    assert cleanup == []
    assert operations == []


def test_body_structure_handler_rejects_legacy_variant_fields_before_materialization(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    document = ET.fromstring(
        f"""<w:document xmlns:w="{W_NS}">
          <w:body>
            <w:p><w:r><w:t>一、×××</w:t></w:r></w:p>
            <w:p><w:r><w:t>1□前言</w:t></w:r></w:p>
          </w:body>
        </w:document>"""
    )
    paragraphs = list(document.iter(W + "p"))
    judgments = [
        {
            "variant_id": "track-humanities",
            "variant_role": "alternate",
            **_judgment(
                block_id="body:block-0001",
                role="body_structure",
                field_id="body.heading.outline1",
            ),
        },
    ]
    plan = _plan(registry, judgments)

    operations, cleanup, selected = materialize_body_structure(
        document=document,
        by_block={
            "body:block-0001": paragraphs[0],
            "body:block-0002": paragraphs[1],
        },
        registry=registry,
        inventory={
            "reading_blocks": [
                {"block_id": "body:block-0001"},
                {"block_id": "body:block-0002"},
            ]
        },
        plan=plan,
        removed=set(),
    )

    assert plan.unsupported[0].reason_code == "materialization_legacy_shape_unsupported"
    assert operations == []
    assert cleanup == []
    assert selected == set()


def test_body_structure_handler_does_not_guess_separated_body_candidate_groups(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    document = ET.fromstring(
        f"""<w:document xmlns:w="{W_NS}">
          <w:body>
            <w:p><w:r><w:t>1□前言</w:t></w:r></w:p>
            <w:p><w:r><w:t>以下另一类用</w:t></w:r></w:p>
            <w:p><w:r><w:t>一、×××</w:t></w:r></w:p>
          </w:body>
        </w:document>"""
    )
    paragraphs = list(document.iter(W + "p"))
    judgments = [
        _judgment(
            block_id="body:block-0001",
            role="body_structure",
            field_id="body.heading.outline1",
        ),
        _judgment(
            block_id="body:block-0003",
            role="body_structure",
            field_id="body.heading.outline1",
        ),
    ]

    operations, cleanup, selected = materialize_body_structure(
        document=document,
        by_block={
            "body:block-0001": paragraphs[0],
            "body:block-0003": paragraphs[2],
        },
        registry=registry,
        inventory={
            "reading_blocks": [
                {"block_id": "body:block-0001", "order": 1},
                {"block_id": "body:block-0002", "order": 2},
                {"block_id": "body:block-0003", "order": 3},
            ]
        },
        plan=_plan(registry, judgments),
        removed=set(),
    )

    assert operations == []
    assert cleanup == []
    assert selected == set()


def test_manual_table_and_generated_handlers_emit_policy_receipts(tmp_path: Path) -> None:
    result = build_shadow_materialization_plan(
        inventory={
            "objects": [
                {"object_id": "obj-form-table", "type": "table"},
                {"object_id": "obj-toc", "type": "paragraph"},
            ],
            "reading_blocks": [
                {
                    "block_id": "form:block-0001",
                    "unit_id": "form",
                    "text": "开题报告表",
                    "covered_object_ids": ["obj-form-table"],
                },
                {
                    "block_id": "toc:block-0001",
                    "unit_id": "toc",
                    "text": "目□□录",
                    "covered_object_ids": ["obj-toc"],
                },
            ],
        },
        review={
            "semantic_judgments": [
                _judgment(block_id="form:block-0001", role="manual_region"),
                _judgment(
                    block_id="toc:block-0001",
                    role="generated_content",
                    field_id="generated.toc",
                ),
            ]
        },
        registry=_registry(tmp_path),
    )

    manual_receipts = manual_table_cell_policy_receipts(result.plan)
    generated_receipts = generated_content_policy_receipts(result.plan)

    assert result.ready is False
    assert result.unsupported[0].reason_code == "materialization_semantic_review_not_current"
    assert manual_receipts == []
    assert generated_receipts == []

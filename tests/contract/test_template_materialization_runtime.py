from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import publication_slot_protocol_status
from docfit.template.materialization import (
    materialize_template_from_semantics as _materialize_template_from_semantics,
)
from docfit.template.materialization.runtime import _adopt_existing_sdt_slots
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from tests.support.source_identity import review_binding, source_partition

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W = f"{{{W_NS}}}"
W14 = f"{{{W14_NS}}}"


def _write_registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
                "  - field_id: thesis.title.en",
                "    label: 英文论文题目",
                "    content_type: text",
                "    materialization:",
                "      slot_layout: centered_title",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "  - field_id: author.name.en",
                "    label: 作者英文姓名",
                "    content_type: text",
                "  - field_id: author.cohort_class",
                "    label: 年级专业班级",
                "    content_type: text",
                "  - field_id: advisor.name.zh",
                "    label: 导师中文姓名",
                "    content_type: text",
                "  - field_id: advisor.name.en",
                "    label: 导师英文姓名",
                "    content_type: text",
                "  - field_id: advisor.title",
                "    label: 导师职称",
                "    content_type: text",
                "  - field_id: author.department",
                "    label: 学院",
                "    content_type: text",
                "  - field_id: author.department.en",
                "    label: 英文学院",
                "    content_type: text",
                "  - field_id: submission.date",
                "    label: 提交年月",
                "    content_type: text",
                "  - field_id: abstract.zh",
                "    label: 中文摘要",
                "    content_type: rich_text",
                "  - field_id: keywords.zh",
                "    label: 中文关键词",
                "    content_type: text",
                "  - field_id: appendix.body",
                "    label: 附录内容",
                "    content_type: section",
                "  - field_id: generated.toc",
                "    label: 目录",
                "    content_type: section",
                "    value_sources: [system_generated]",
            )
        ),
        encoding="utf-8",
    )


def _write_body_registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: body.chapters",
                "    label: 正文章节集合",
                "    content_type: section",
                "  - field_id: body.heading.outline1",
                "    label: 章标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.heading.outline2",
                "    label: 一级节标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.heading.outline3",
                "    label: 二级节标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.paragraph",
                "    label: 正文段落",
                "    content_type: rich_text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.numbered_list_item",
                "    label: 数字列表项",
                "    content_type: rich_text",
                "    parent_field_id: body.chapters",
            )
        ),
        encoding="utf-8",
    )


def _paragraph(text: str, paragraph_properties: str = "") -> str:
    return f'<w:p>{paragraph_properties}<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def _write_docx_from_paragraph_xml(path: Path, paragraph_xml: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = (
        f'<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}"><w:body>'
        + "".join(paragraph_xml)
        + "</w:body></w:document>"
    )
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    _write_docx_from_paragraph_xml(path, [_paragraph(text) for text in paragraphs])


def _read_document(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as archive:
        return ET.fromstring(archive.read("word/document.xml"))


def _visible_paragraph_text(root: ET.Element) -> list[str]:
    return [
        "".join(node.text or "" for node in paragraph.iter(W + "t"))
        for paragraph in root.iter(W + "p")
    ]


def _slot_aliases(root: ET.Element) -> list[str]:
    aliases: list[str] = []
    for control in root.iter(W + "sdt"):
        alias = control.find(f"{W}sdtPr/{W}alias")
        if alias is not None and isinstance(alias.get(f"{W}val"), str):
            aliases.append(str(alias.get(f"{W}val")))
    return aliases


def _slot_alias_para_ids(root: ET.Element) -> dict[str, str | None]:
    parent = {child: item for item in root.iter() for child in list(item)}
    result: dict[str, str | None] = {}
    for control in root.iter(W + "sdt"):
        alias = control.find(f"{W}sdtPr/{W}alias")
        if alias is None or not isinstance(alias.get(f"{W}val"), str):
            continue
        paragraph = control
        while paragraph is not None and paragraph.tag != W + "p":
            paragraph = parent.get(paragraph)
        result[str(alias.get(f"{W}val"))] = (
            str(paragraph.get(W14 + "paraId")) if paragraph is not None else None
        )
    return result


def _inventory_with_paragraph_objects(
    reading_blocks: list[dict[str, object]],
) -> dict[str, object]:
    objects: list[dict[str, object]] = []
    for paragraph_index, block in enumerate(reading_blocks, start=1):
        raw_ids = block.get("covered_object_ids")
        if not isinstance(raw_ids, list):
            continue
        for object_id in raw_ids:
            if isinstance(object_id, str) and object_id.strip():
                objects.append(
                    {
                        "object_id": object_id.strip(),
                        "type": "paragraph",
                        "locator": f"/body/p[{paragraph_index}]",
                    }
                )
    return {"objects": objects, "reading_blocks": reading_blocks}


def _span_ref(block_id: str, part_index: int) -> str:
    return f"reading_block_id={block_id};part_index={part_index}"


def _slot_ref(block_id: str, part_index: int, field_id: str) -> str:
    return f"{_span_ref(block_id, part_index)};field_id={field_id}"


def _part(role: str, text: str, *, field_id: str | None = None) -> dict[str, str]:
    part = {"role": role, "text": text}
    if field_id is not None:
        part["field_id"] = field_id
    return part


def _resolved_span(
    block_id: str,
    part_index: int,
    role: str,
    *,
    field_id: str | None = None,
    text: str = "",
) -> dict[str, object]:
    span: dict[str, object] = {
        "span_ref": _span_ref(block_id, part_index),
        "scope": {"reading_block_id": block_id},
        "reading_block_id": block_id,
        "part_index": part_index,
        "role": role,
        "text": text,
    }
    if field_id is not None:
        span["field_id"] = field_id
        span["slot_ref"] = _slot_ref(block_id, part_index, field_id)
    return span


def _source_entry_span(
    source_entry_id: str,
    part_index: int,
    role: str,
    *,
    field_id: str | None = None,
    text: str = "",
    text_start: int = 0,
    text_end: int | None = None,
    object_ids: list[str] | None = None,
) -> dict[str, object]:
    span_ref = f"source_entry_id={source_entry_id};part_index={part_index}"
    span: dict[str, object] = {
        "span_ref": span_ref,
        "scope": {"source_entry_id": source_entry_id},
        "source_entry_id": source_entry_id,
        "part_index": part_index,
        "role": role,
        "text": text,
        "text_start": text_start,
        "text_end": len(text) if text_end is None else text_end,
        "covered_object_ids": object_ids or ["obj-title"],
    }
    if field_id is not None:
        span["field_id"] = field_id
        span["slot_ref"] = f"{span_ref};field_id={field_id}"
    return span


def _source_entry_inventory(
    *,
    document_sha256: str,
    source_entry_id: str,
    text: str,
    object_id: str = "obj-title",
    locator: str = "/body/p[1]",
    fingerprint: str = "f" * 64,
) -> dict[str, object]:
    object_ref = {
        "document_sha256": document_sha256,
        "object_id": object_id,
        "expected_fingerprint": fingerprint,
    }
    return {
        "document_sha256": document_sha256,
        "objects": [
            {
                "object_id": object_id,
                "type": "paragraph",
                "locator": locator,
                "object_ref": object_ref,
                "source_entry_id": source_entry_id,
            }
        ],
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": object_id,
                        "locator": locator,
                        "text_span": [0, len(text)],
                        "object_ref": object_ref,
                        "fingerprint": fingerprint,
                    }
                ],
            }
        ],
        "reading_blocks": [],
    }


def _judgment(
    block_id: str,
    parts: list[dict[str, str]],
    *,
    resolved_spans: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "scope": {"reading_block_id": block_id},
        "parts": parts,
        "resolved_spans": (
            resolved_spans
            if resolved_spans is not None
            else [
                _resolved_span(block_id, index, part["role"], text=part.get("text", ""))
                for index, part in enumerate(parts)
            ]
        ),
    }


def _slot_judgment(block_id: str, field_id: str, text: str) -> dict[str, object]:
    return _judgment(
        block_id,
        [_part("fill_slot", text, field_id=field_id)],
        resolved_spans=[
            _resolved_span(
                block_id,
                0,
                "fill_slot",
                field_id=field_id,
                text=text,
            )
        ],
    )


def _cleanup_judgment(block_id: str, text: str) -> dict[str, object]:
    return _judgment(block_id, [_part("cleanup", text)])


def _fixed_judgment(block_id: str, text: str) -> dict[str, object]:
    return _judgment(block_id, [_part("fixed_label", text)])


def _body_structure_judgment(
    bindings: list[tuple[str, str, str]],
    *,
    range_id: str | None = None,
) -> dict[str, object]:
    parts = [
        _part("body_structure", text, field_id=field_id) for block_id, text, field_id in bindings
    ]
    judgment: dict[str, object] = {
        "scope": (
            {"reading_range_id": range_id}
            if range_id is not None
            else {"reading_block_id": bindings[0][0]}
        ),
        "parts": parts,
        "resolved_spans": [
            _resolved_span(
                block_id,
                index,
                "body_structure",
                field_id=field_id,
                text=text,
            )
            for index, (block_id, text, field_id) in enumerate(bindings)
        ],
    }
    return judgment


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


def materialize_template_from_semantics(
    *,
    source_docx: Path,
    output_docx: Path,
    registry: FieldRegistrySnapshot,
    inventory: dict[str, object],
    review: dict[str, object],
) -> dict[str, object]:
    current_inventory, current_review = _with_current_vocabulary(
        registry,
        inventory,
        review,
    )
    current_inventory, current_review = _canonicalize_materialization_fixture(
        source_docx=source_docx,
        inventory=current_inventory,
        review=current_review,
    )
    return _materialize_template_from_semantics(
        source_docx=source_docx,
        output_docx=output_docx,
        registry=registry,
        inventory=current_inventory,
        review=current_review,
    )


def _canonicalize_materialization_fixture(
    *,
    source_docx: Path,
    inventory: dict[str, object],
    review: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Project legacy test notation into the one accepted Phase-5 contract."""

    source_hash = sha256_file(source_docx)
    existing_entries = inventory.get("source_entries")
    if isinstance(existing_entries, list) and existing_entries:
        raw_judgments = review.get("semantic_judgments")
        judgments = (
            [dict(item) for item in raw_judgments if isinstance(item, dict)]
            if isinstance(raw_judgments, list)
            else []
        )
        resolved = [
            span
            for judgment in judgments
            for span in judgment.get("resolved_spans", [])
            if isinstance(span, dict)
        ]
        current_review = {
            **review,
            "document_sha256": review.get("document_sha256", source_hash),
            "semantic_judgments": judgments,
            "resolved_spans": resolved,
        }
        current_review["semantic_judgments_sha256"] = sha256_json(judgments)
        return dict(inventory), current_review
    raw_objects = inventory.get("objects")
    objects = (
        {
            item["object_id"]: dict(item)
            for item in raw_objects
            if isinstance(item, dict) and isinstance(item.get("object_id"), str)
        }
        if isinstance(raw_objects, list)
        else {}
    )
    raw_blocks = inventory.get("reading_blocks")
    blocks = (
        {
            item["block_id"]: item
            for item in raw_blocks
            if isinstance(item, dict) and isinstance(item.get("block_id"), str)
        }
        if isinstance(raw_blocks, list)
        else {}
    )
    raw_judgments = review.get("semantic_judgments")
    legacy_judgments = (
        [item for item in raw_judgments if isinstance(item, dict)]
        if isinstance(raw_judgments, list)
        else []
    )
    projected: list[dict[str, object]] = []
    source_entries: list[dict[str, object]] = []
    projected_objects: list[dict[str, object]] = []
    seen_blocks: set[str] = set()
    for legacy in legacy_judgments:
        parts = legacy.get("parts")
        if not isinstance(parts, list):
            continue
        spans = legacy.get("resolved_spans")
        raw_spans = (
            [item for item in spans if isinstance(item, dict)] if isinstance(spans, list) else []
        )
        block_ids = list(
            dict.fromkeys(
                str(item["reading_block_id"])
                for item in raw_spans
                if isinstance(item.get("reading_block_id"), str)
            )
        )
        if not block_ids:
            scope = legacy.get("scope")
            if isinstance(scope, dict) and isinstance(scope.get("reading_block_id"), str):
                block_ids = [str(scope["reading_block_id"])]
        for block_id in block_ids:
            if block_id in seen_blocks:
                continue
            selected_parts: list[dict[str, object]] = []
            if len(block_ids) == 1:
                selected_parts = [dict(part) for part in parts if isinstance(part, dict)]
            else:
                for span in raw_spans:
                    if span.get("reading_block_id") != block_id:
                        continue
                    part_index = span.get("part_index")
                    if isinstance(part_index, int) and 0 <= part_index < len(parts):
                        part = parts[part_index]
                        if isinstance(part, dict):
                            selected_parts.append(dict(part))
            if not selected_parts:
                continue
            block = blocks.get(block_id, {})
            block_text = block.get("text")
            submitted_text = "".join(str(part.get("text", "")) for part in selected_parts)
            if (
                isinstance(block_text, str)
                and block_text.startswith(submitted_text)
                and block_text != submitted_text
            ):
                selected_parts.append(
                    {"text": block_text[len(submitted_text) :], "role": "cleanup"}
                )
                submitted_text = block_text
            elif (
                isinstance(block_text, str)
                and block_text.endswith(submitted_text)
                and block_text != submitted_text
            ):
                selected_parts.insert(
                    0,
                    {
                        "text": block_text[: -len(submitted_text)],
                        "role": "fixed_label",
                    },
                )
                submitted_text = block_text
            elif isinstance(block_text, str) and submitted_text and submitted_text in block_text:
                start = block_text.index(submitted_text)
                if start:
                    selected_parts.insert(0, {"text": block_text[:start], "role": "fixed_label"})
                end = start + len(submitted_text)
                if end < len(block_text):
                    selected_parts.append({"text": block_text[end:], "role": "fixed_label"})
                submitted_text = block_text
            object_ids = block.get("covered_object_ids")
            object_id = (
                next(
                    (value for value in object_ids if isinstance(value, str) and value in objects),
                    None,
                )
                if isinstance(object_ids, list)
                else None
            )
            if object_id is None:
                continue
            obj = objects[object_id]
            locator = obj.get("locator")
            if not isinstance(locator, str):
                continue
            source_entry_id = f"source-entry-{sha256_json({'block_id': block_id})[:24]}"
            fingerprint = sha256_json({"object_id": object_id, "text": submitted_text})
            object_ref = {
                "document_sha256": source_hash,
                "object_id": object_id,
                "expected_fingerprint": fingerprint,
            }
            projected_objects.append(
                {**obj, "object_ref": object_ref, "source_entry_id": source_entry_id}
            )
            source_entries.append(
                {
                    "source_entry_id": source_entry_id,
                    "text": submitted_text,
                    "entry_type": "text",
                    "source_order": {"block": len(source_entries), "inline": 0},
                    "provenance": [
                        {
                            "object_id": object_id,
                            "locator": locator,
                            "text_span": [0, len(submitted_text)],
                            "object_ref": object_ref,
                            "fingerprint": fingerprint,
                        }
                    ],
                }
            )
            projected.append({"source_entry_id": source_entry_id, "parts": selected_parts})
            seen_blocks.add(block_id)
    current_inventory = {
        **inventory,
        "document_sha256": source_hash,
        "objects": projected_objects,
        "source_entries": source_entries,
        "reading_blocks": [],
    }
    if not source_entries:
        return inventory, review
    source_partition(current_inventory)
    resolved = resolve_semantic_judgments(
        inventory=current_inventory,
        judgments=projected,
    )
    for index, judgment in enumerate(projected):
        judgment["resolved_spans"] = [
            span for span in resolved if span.get("judgment_index") == index
        ]
    current_review = {
        **review_binding(current_inventory),
        **review,
        "document_sha256": review.get("document_sha256", source_hash),
        "semantic_judgments": projected,
        "resolved_spans": resolved,
    }
    current_review["semantic_judgments_sha256"] = sha256_json(projected)
    return current_inventory, current_review


def test_materializer_requires_accepted_field_vocabulary_before_writing(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["论文题目：×××"])
    inventory = {
        "objects": [{"object_id": "obj-title", "type": "paragraph", "locator": "/body/p[1]"}],
        "reading_blocks": [
            {
                "block_id": "u:block-0001",
                "covered_object_ids": ["obj-title"],
                "text": "论文题目：×××",
            }
        ],
    }
    review = {
        "semantic_judgments": [
            _judgment(
                "u:block-0001",
                [
                    _part("fixed_label", "论文题目："),
                    _part("fill_slot", "×××", field_id="thesis.title.zh"),
                ],
                resolved_spans=[
                    _resolved_span(
                        "u:block-0001",
                        0,
                        "fixed_label",
                        text="论文题目：",
                    ),
                    _resolved_span(
                        "u:block-0001",
                        1,
                        "fill_slot",
                        field_id="thesis.title.zh",
                        text="×××",
                    ),
                ],
            )
        ]
    }

    with pytest.raises(ToolFailure) as caught:
        _materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=FieldRegistrySnapshot.load(registry_path),
            inventory=inventory,
            review=review,
        )

    assert caught.value.code == "template_materialization_system_state_invalid"
    assert caught.value.status == "error"
    assert not caught.value.retryable
    assert "materialization_field_vocabulary_provenance_missing" in caught.value.message
    assert not output.exists()


def test_materializer_fails_closed_on_stale_accepted_word_fragment(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["论文题目：×××", "另一段"])
    inventory = {
        "objects": [
            {
                "object_id": "obj-title",
                "type": "paragraph",
                "locator": "/body/p[99]",
            }
        ],
        "reading_blocks": [
            {
                "block_id": "u:block-0001",
                "covered_object_ids": ["obj-title"],
                "text": "论文题目：×××",
            }
        ],
    }
    review = {"semantic_judgments": [_slot_judgment("u:block-0001", "thesis.title.zh", "×××")]}

    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=FieldRegistrySnapshot.load(registry_path),
            inventory=inventory,
            review=review,
        )

    assert caught.value.code == "materialization_word_fragment_stale"
    assert caught.value.origin == "harness"
    assert not output.exists()


def test_materializer_preflight_reconstructs_visible_tab_characters(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    registry = FieldRegistrySnapshot.load(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            (
                '<w:p><w:pPr><w:tabs><w:tab w:val="right" '
                'w:pos="9060"/></w:tabs></w:pPr>'
                "<w:r><w:t>题目</w:t></w:r>"
                "<w:r><w:tab/></w:r>"
                "<w:r><w:t>占位</w:t></w:r>"
                "</w:p>"
            )
        ],
    )
    source_hash = sha256_file(source)
    source_entry_id = "source-entry-tabbed-slot"
    source_text = "题目\t占位"
    inventory = _source_entry_inventory(
        document_sha256=source_hash,
        source_entry_id=source_entry_id,
        text=source_text,
    )
    vocabulary = registry.pre_input_vocabulary()
    inventory["field_id_vocabulary"] = vocabulary
    inventory["field_vocabulary_digest"] = vocabulary["digest"]
    judgment: dict[str, object] = {
        "source_entry_id": source_entry_id,
        "parts": [
            {
                "text": source_text,
                "role": "fill_slot",
                "field_id": "thesis.title.zh",
            }
        ],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=[judgment],
    )
    judgment["resolved_spans"] = resolved
    review = {
        **review_binding(inventory),
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": [judgment],
        "semantic_judgments_sha256": sha256_json([judgment]),
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )

    assert result["operation_count"] == 1
    assert output.exists()


def test_materializer_resolves_exact_fragments_inside_table_cell_paragraphs(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            (
                '<w:p w14:paraId="AAAA0001">'
                '<w:r><w:t xml:space="preserve">学  院：             </w:t></w:r>'
                "</w:p>"
            ),
            '<w:p w14:paraId="AAAA0002"><w:r><w:t>top spacer</w:t></w:r></w:p>',
            '<w:p w14:paraId="AAAA0003"><w:r><w:t>top spacer 2</w:t></w:r></w:p>',
            (
                "<w:tbl><w:tr>"
                '<w:tc><w:p w14:paraId="BBBB0001"><w:r><w:t>学生姓名</w:t></w:r></w:p></w:tc>'
                '<w:tc><w:p w14:paraId="CCCC0001"><w:r><w:t>年级专业及班级</w:t></w:r></w:p></w:tc>'
                "</w:tr></w:tbl>"
            ),
        ],
    )
    inventory = {
        "objects": [
            {
                "object_id": "obj-department",
                "type": "run",
                "locator": "/body/p[@paraId=AAAA0001]/r[1]",
            },
            {
                "object_id": "obj-name",
                "type": "run",
                "locator": "/body/tbl[1]/tr[1]/tc[1]/p[@paraId=BBBB0001]/r[1]",
            },
            {
                "object_id": "obj-cohort",
                "type": "run",
                "locator": "/body/tbl[1]/tr[1]/tc[2]/p[@paraId=CCCC0001]/r[1]",
            },
        ],
        "reading_blocks": [
            {
                "block_id": "proposal:block-0001",
                "covered_object_ids": ["obj-department"],
                "text": "学  院：             ",
            },
            {
                "block_id": "proposal:block-0002",
                "covered_object_ids": ["obj-name"],
                "text": "学生姓名",
            },
            {
                "block_id": "proposal:block-0003",
                "covered_object_ids": ["obj-cohort"],
                "text": "年级专业及班级",
            },
        ],
    }
    review = {
        "semantic_judgments": [
            _slot_judgment("proposal:block-0001", "author.department", "             "),
            _slot_judgment("proposal:block-0002", "author.name.zh", "学生姓名"),
            _slot_judgment("proposal:block-0003", "author.cohort_class", "年级专业及班级"),
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert result["operation_count"] == 3
    assert _slot_alias_para_ids(root) == {
        "author.department": "AAAA0001",
        "author.name.zh": "BBBB0001",
        "author.cohort_class": "CCCC0001",
    }


def test_cleanup_keeps_a_required_empty_paragraph_in_a_table_cell(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            (
                "<w:tbl><w:tr><w:tc>"
                '<w:p w14:paraId="BBBB0001"><w:r><w:t>删除示例值</w:t></w:r></w:p>'
                "</w:tc></w:tr></w:tbl>"
            )
        ],
    )
    inventory = {
        "objects": [
            {
                "object_id": "obj-cleanup",
                "type": "run",
                "locator": "/body/tbl[1]/tr[1]/tc[1]/p[@paraId=BBBB0001]/r[1]",
            }
        ],
        "reading_blocks": [
            {
                "block_id": "body:block-cleanup",
                "covered_object_ids": ["obj-cleanup"],
                "text": "删除示例值",
            }
        ],
    }
    review = {"semantic_judgments": [_cleanup_judgment("body:block-cleanup", "删除示例值")]}

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    cell = _read_document(output).find(f".//{W}tc")
    assert cell is not None
    assert [child.tag for child in cell][-1] == f"{W}p"
    assert result["cleanup"][0]["action"] == "remove_exact_fragments"


def test_materializer_materializes_slot_from_source_entry_span_without_reading_block(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    text = "论文题目：×××"
    source_entry_id = "source-entry-cover-title"
    _write_docx(source, [text])
    source_hash = sha256_file(source)
    inventory = _source_entry_inventory(
        document_sha256=source_hash,
        source_entry_id=source_entry_id,
        text=text,
    )
    agent_judgment = {
        "source_entry_id": source_entry_id,
        "parts": [
            _part("fixed_label", "论文题目："),
            _part("fill_slot", "×××", field_id="thesis.title.zh"),
        ],
    }
    source_partition(inventory)
    resolved_spans = resolve_semantic_judgments(
        inventory=inventory,
        judgments=[agent_judgment],
    )
    review = {
        **review_binding(inventory),
        "document_sha256": source_hash,
        "semantic_judgments": [
            {
                **agent_judgment,
                "resolved_spans": resolved_spans,
            }
        ],
    }

    registry = FieldRegistrySnapshot.load(registry_path)
    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    publication = publication_slot_protocol_status(
        candidate_docx=output,
        registry=registry,
    )

    root = _read_document(output)
    assert result["operation_count"] == 1
    assert result["operations"][0]["source_entry_id"] == source_entry_id
    assert result["operations"][0]["span_ref"] == resolved_spans[1]["span_ref"]
    assert result["operations"][0]["slot_ref"] == resolved_spans[1]["slot_ref"]
    assert _visible_paragraph_text(root) == ["论文题目：【填】"]
    assert _slot_aliases(root) == ["thesis.title.zh"]
    assert publication["status"] == "ok"
    assert publication["slots"][0]["slot_ref"] == resolved_spans[1]["slot_ref"]


def test_materializer_fails_closed_when_source_entry_document_hash_is_stale(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    source_entry_id = "source-entry-cover-title"
    _write_docx(source, ["论文题目：×××"])
    original_hash = sha256_file(source)
    inventory = _source_entry_inventory(
        document_sha256=original_hash,
        source_entry_id=source_entry_id,
        text="论文题目：×××",
    )
    agent_judgment = {
        "source_entry_id": source_entry_id,
        "parts": [
            _part("fixed_label", "论文题目："),
            _part("fill_slot", "×××", field_id="thesis.title.zh"),
        ],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=[agent_judgment],
    )
    review = {
        **review_binding(inventory),
        "document_sha256": original_hash,
        "semantic_judgments": [{**agent_judgment, "resolved_spans": resolved}],
    }
    _write_docx(source, ["论文题目：已变更"])

    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=FieldRegistrySnapshot.load(registry_path),
            inventory=inventory,
            review=review,
        )

    assert caught.value.code == "stale_ref"
    assert caught.value.origin == "request"
    assert not output.exists()


def test_materializer_applies_semantic_treatments_inside_cover_rows(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    source_paragraphs = [
        "附件1 封面基本格式：这段应删除",
        "湖 南 农 业 大 学（一号华文行楷加粗）",
        "□□□□□□学生姓名（三号黑体加粗）：×××（或×□×） （三号楷体加粗）",
        "□□□□□□指导老师及职称：×××□教授 ",
        "提交日期：20××年××月 ",
    ]
    _write_docx(source, source_paragraphs)
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": f"cover:block-{index:04d}",
                "covered_object_ids": [f"obj-{index}"],
                "text": source_paragraphs[index - 1],
            }
            for index in range(1, 6)
        ],
    )
    review = {
        "semantic_judgments": [
            _cleanup_judgment("cover:block-0001", "附件1 封面基本格式：这段应删除"),
            _judgment(
                "cover:block-0002",
                [
                    _part("fixed_label", "湖 南 农 业 大 学"),
                    _part("cleanup", "（一号华文行楷加粗）"),
                ],
            ),
            _judgment(
                "cover:block-0003",
                [
                    _part("cleanup", "□□□□□□"),
                    _part("fixed_label", "学生姓名"),
                    _part("cleanup", "（三号黑体加粗）"),
                    _part("fixed_label", "："),
                    _part("fill_slot", "×××（或×□×）", field_id="author.name.zh"),
                    _part("cleanup", " （三号楷体加粗）"),
                ],
                resolved_spans=[
                    _resolved_span("cover:block-0003", 0, "cleanup", text="□□□□□□"),
                    _resolved_span(
                        "cover:block-0003",
                        1,
                        "fixed_label",
                        text="学生姓名：",
                    ),
                    _resolved_span(
                        "cover:block-0003",
                        2,
                        "fill_slot",
                        field_id="author.name.zh",
                        text="×××（或×□×）",
                    ),
                ],
            ),
            _judgment(
                "cover:block-0004",
                [
                    _part("cleanup", "□□□□□□"),
                    _part("fixed_label", "指导老师及职称："),
                    _part("fill_slot", "×××", field_id="advisor.name.zh"),
                    _part("cleanup", "□"),
                    _part("fill_slot", "教授", field_id="advisor.title"),
                    _part("cleanup", " "),
                ],
                resolved_spans=[
                    _resolved_span("cover:block-0004", 0, "cleanup", text="□□□□□□"),
                    _resolved_span(
                        "cover:block-0004",
                        1,
                        "fixed_label",
                        text="指导老师及职称：",
                    ),
                    _resolved_span(
                        "cover:block-0004",
                        2,
                        "fill_slot",
                        field_id="advisor.name.zh",
                        text="×××",
                    ),
                    _resolved_span("cover:block-0004", 3, "fixed_label", text="　"),
                    _resolved_span(
                        "cover:block-0004",
                        4,
                        "fill_slot",
                        field_id="advisor.title",
                        text="教授",
                    ),
                ],
            ),
            _judgment(
                "cover:block-0005",
                [
                    _part("fixed_label", "提交日期："),
                    _part("fill_slot", "20××年××月", field_id="submission.date"),
                    _part("cleanup", " "),
                ],
                resolved_spans=[
                    _resolved_span(
                        "cover:block-0005",
                        0,
                        "fixed_label",
                        text="提交日期：",
                    ),
                    _resolved_span(
                        "cover:block-0005",
                        1,
                        "fill_slot",
                        field_id="submission.date",
                        text="20××年××月",
                    ),
                ],
            ),
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    text = "\n".join(_visible_paragraph_text(root))
    assert result["operation_count"] == 4
    assert result["cleanup_count"] == 5
    shadow_plan = result["shadow_intent_plan"]
    assert shadow_plan["ready"] is True
    assert [item["intent_type"] for item in shadow_plan["intents"]] == [
        "delete_block",
        "keep_fixed_content",
        "materialize_slot",
        "materialize_slot",
        "materialize_slot",
    ]
    assert shadow_plan["intents"][2]["field_ids"] == ["author.name.zh"]
    assert "附件1" not in text
    assert "一号华文行楷加粗" not in text
    assert "湖 南 农 业 大 学" in text
    assert "□□□□□□学生姓名" not in text
    assert "学生姓名：【填】" in text
    assert "×××" not in text
    assert "指导老师及职称：【填】【填】" in text
    assert "提交日期：【填】" in text
    assert _slot_aliases(root) == [
        "author.name.zh",
        "advisor.name.zh",
        "advisor.title",
        "submission.date",
    ]


def test_materializer_cleans_fixed_section_heading_format_notes(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    paragraphs = [
        "参考文献（小三号黑体，加粗，居中）",
        "致□□谢  (小三号黑体，居中)",
        "附录（一级标题小三号黑体，顶格书写）",
    ]
    _write_docx(source, paragraphs)
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": f"section:block-{index:04d}",
                "covered_object_ids": [f"obj-{index}"],
                "text": text,
            }
            for index, text in enumerate(paragraphs, start=1)
        ],
    )
    review = {
        "semantic_judgments": [
            _fixed_judgment("section:block-0001", "参考文献"),
            _fixed_judgment("section:block-0002", "致□□谢"),
            _fixed_judgment("section:block-0003", "附录"),
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert _visible_paragraph_text(root) == ["参考文献", "致□□谢", "附录"]
    assert result["cleanup_count"] == 3
    assert [item["action"] for item in result["cleanup"]] == [
        "remove_exact_fragments",
        "remove_exact_fragments",
        "remove_exact_fragments",
    ]


def test_materializer_clears_cleanup_text_without_removing_paragraph(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    title = "版权声明"
    body = "任何收存和保管本论文各种版本的单位和个人，未经本论文作者同意，不得将本论文转借他人。"
    note = "在正式提交图书馆的论文版本中，需将此页与原创性声明页替换为带有二维码的版本。"
    _write_docx(source, [title, body, note])
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "copyright:block-0001",
                "range_id": "copyright:range-whole-unit",
                "covered_object_ids": ["obj-1"],
                "text": title,
            },
            {
                "block_id": "copyright:block-0002",
                "range_id": "copyright:range-whole-unit",
                "covered_object_ids": ["obj-2"],
                "text": body,
            },
            {
                "block_id": "copyright:block-0003",
                "range_id": "copyright:range-whole-unit",
                "covered_object_ids": ["obj-3"],
                "text": note,
            },
        ],
    )
    review = {
        "semantic_judgments": [
            {
                "scope": {"reading_range_id": "copyright:range-whole-unit"},
                "parts": [
                    _part("fixed_label", title),
                    _part("fixed_label", body),
                    _part("cleanup", note),
                ],
                "resolved_spans": [
                    _resolved_span(
                        "copyright:block-0001",
                        0,
                        "fixed_label",
                        text=title,
                    ),
                    _resolved_span(
                        "copyright:block-0002",
                        1,
                        "fixed_label",
                        text=body,
                    ),
                    _resolved_span("copyright:block-0003", 2, "cleanup", text=note),
                ],
            }
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert _visible_paragraph_text(root) == [title, body, ""]
    assert result["operation_count"] == 0
    assert result["cleanup_count"] == 1
    assert result["cleanup"][0]["action"] == "remove_exact_fragments"
    accepted_cleanup_span = result["cleanup"][0]["span_refs"][0]
    assert accepted_cleanup_span.startswith("source_entry_id=source-entry-")
    cleanup_receipt = result["mutation_receipts"][0]
    assert cleanup_receipt["handler"] == "cleanup"
    assert cleanup_receipt["span_refs"] == [accepted_cleanup_span]
    source_entry_id = result["cleanup"][0]["source_entry_id"]
    assert cleanup_receipt["before_text_by_block"][source_entry_id] == note
    assert cleanup_receipt["after_text_by_block"][source_entry_id] == ""


def test_materializer_does_not_strip_non_instruction_parentheticals(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    paragraphs = [
        "毕业论文（设计）",
        "作者.题名[J].期刊名，出版年，卷（期）：页码A-B.",
        "学□□生：",
    ]
    _write_docx(source, paragraphs)
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": f"section:block-{index:04d}",
                "covered_object_ids": [f"obj-{index}"],
                "text": text,
            }
            for index, text in enumerate(paragraphs, start=1)
        ],
    )
    review = {
        "semantic_judgments": [
            _fixed_judgment(f"section:block-{index:04d}", text)
            for index in range(1, 4)
            for text in [paragraphs[index - 1]]
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert _visible_paragraph_text(root) == paragraphs
    assert result["cleanup_count"] == 0


def test_materializer_centers_short_title_slots_from_right_aligned_source(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            _paragraph(
                "TITLE OF GRADUATION PAPER（四号Times New Roman加粗，大写）",
                '<w:pPr><w:ind w:firstLineChars="295" w:firstLine="829"/>'
                '<w:jc w:val="right"/></w:pPr>',
            ),
        ],
    )
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "cover:block-0001",
                "covered_object_ids": ["obj-1"],
            }
        ],
    )
    review = {
        "semantic_judgments": [
            _judgment(
                "cover:block-0001",
                [
                    _part("fill_slot", "TITLE OF GRADUATION PAPER", field_id="thesis.title.en"),
                    _part("style_only", "（四号Times New Roman加粗，大写）"),
                ],
            )
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    paragraph = next(root.iter(W + "p"))
    properties = paragraph.find(W + "pPr")
    assert result["operation_count"] == 1
    assert _visible_paragraph_text(root) == ["【英文论文题目】"]
    assert _slot_aliases(root) == ["thesis.title.en"]
    assert properties is not None
    assert properties.find(W + "ind") is None
    alignment = properties.find(W + "jc")
    assert alignment is not None
    assert alignment.get(W + "val") == "center"


def test_materializer_preserves_title_prefix_layout_without_registry_layout_metadata(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            _paragraph(
                "中文论文题目",
                '<w:pPr><w:ind w:firstLineChars="295" w:firstLine="829"/>'
                '<w:jc w:val="right"/></w:pPr>',
            ),
        ],
    )
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "cover:block-0001",
                "covered_object_ids": ["obj-1"],
            }
        ],
    )
    review = {
        "semantic_judgments": [
            _slot_judgment(
                "cover:block-0001",
                "thesis.title.zh",
                "中文论文题目",
            )
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    paragraph = next(root.iter(W + "p"))
    properties = paragraph.find(W + "pPr")
    assert result["operation_count"] == 1
    assert _visible_paragraph_text(root) == ["【中文题目】"]
    assert _slot_aliases(root) == ["thesis.title.zh"]
    assert properties is not None
    assert properties.find(W + "ind") is not None
    alignment = properties.find(W + "jc")
    assert alignment is not None
    assert alignment.get(W + "val") == "right"


def test_materializer_uses_explicit_registry_field_ids_for_slots(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(
        source,
        [
            "□□摘□要（小四黑体）：…… （五号宋体）",
            "□□关键词：×××；×××；×××；×××",
        ],
    )
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "abstract:block-0001",
                "covered_object_ids": ["obj-1"],
                "text": "□□摘□要（小四黑体）：…… （五号宋体）",
            },
            {
                "block_id": "abstract:block-0002",
                "covered_object_ids": ["obj-2"],
                "text": "□□关键词：×××；×××；×××；×××",
            },
        ],
    )
    review = {
        "semantic_judgments": [
            _slot_judgment("abstract:block-0001", "abstract.zh", "……"),
            _slot_judgment(
                "abstract:block-0002",
                "keywords.zh",
                "×××；×××；×××；×××",
            ),
        ]
    }

    materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert _slot_aliases(root) == ["abstract.zh", "keywords.zh"]
    assert _visible_paragraph_text(root) == [
        "□□摘□要（小四黑体）：【填】 （五号宋体）",
        "□□关键词：【填】",
    ]


def test_materializer_removes_style_only_text_beside_fixed_label(tmp_path: Path) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    source_text = "ABSTRACT（三号 Times New Roman，加粗）"
    _write_docx(source, [source_text])
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "abstract:block-heading",
                "covered_object_ids": ["obj-1"],
                "text": source_text,
            }
        ],
    )
    review = {
        "semantic_judgments": [
            _judgment(
                "abstract:block-heading",
                [
                    _part("fixed_label", "ABSTRACT"),
                    _part("style_only", "（三号 Times New Roman，加粗）"),
                ],
            )
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    assert _visible_paragraph_text(_read_document(output)) == ["ABSTRACT"]
    assert result["cleanup_count"] == 1
    assert result["cleanup"][0]["span_refs"][0].startswith("source_entry_id=")
    assert result["cleanup"][0]["word_fragments"][0]["text"] == ("（三号 Times New Roman，加粗）")
    assert not result["policy_receipts"]
    assert result["mutation_receipts"][0]["handler"] == "cleanup"


@pytest.mark.parametrize("keep_fixed_prefix", [False, True])
def test_style_note_and_cleanup_mix_clears_only_accepted_text_keeps_paragraph(
    tmp_path: Path, keep_fixed_prefix: bool,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    prefix = "Retain(note)" if keep_fixed_prefix else ""
    source_text = prefix + "sample(note)sample"
    paragraph_properties = '<w:pPr><w:keepNext/><w:spacing w:after="240"/></w:pPr>'
    _write_docx_from_paragraph_xml(source, [
        f'<w:p>{paragraph_properties}<w:r><w:t>{source_text}</w:t></w:r></w:p>',
        _paragraph("Adjacent text"),
    ])
    source_hash = sha256_file(source)
    before = _read_document(source)
    inventory = _inventory_with_paragraph_objects([
        {"block_id": "note", "covered_object_ids": ["obj-1"], "text": source_text},
        {"block_id": "next", "covered_object_ids": ["obj-2"], "text": "Adjacent text"},
    ])
    parts = ([_part("fixed_label", prefix)] if prefix else []) + [
        _part("cleanup", "sample"), _part("style_only", "(note)"),
        _part("cleanup", "sample"),
    ]
    result = materialize_template_from_semantics(
        source_docx=source, output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path), inventory=inventory,
        review={"semantic_judgments": [
            _judgment("note", parts),
            _judgment("next", [_part("fixed_label", "Adjacent text")]),
        ]},
    )
    after = _read_document(output)
    assert _visible_paragraph_text(after) == [prefix, "Adjacent text"]
    assert len(list(after.iter(W + "p"))) == 2
    assert ET.tostring(after.find(f"{W}body/{W}p/{W}pPr")) == ET.tostring(
        before.find(f"{W}body/{W}p/{W}pPr")
    )
    assert _slot_aliases(after) == []
    assert result["cleanup_count"] == 1
    assert len(result["cleanup"][0]["span_refs"]) == 3
    assert sha256_file(source) == source_hash


def test_materializer_uses_semantic_parts_to_preserve_inline_fixed_label(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["Tutor:××××"])
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "u-paper-body:block-0013",
                "covered_object_ids": ["obj-tutor"],
                "text": "Tutor:××××",
            },
        ],
    )
    review = {
        "semantic_judgments": [
            _judgment(
                "u-paper-body:block-0013",
                [
                    _part("fixed_label", "Tutor:"),
                    _part("fill_slot", "××××", field_id="advisor.name.en"),
                ],
                resolved_spans=[
                    _resolved_span(
                        "u-paper-body:block-0013",
                        0,
                        "fixed_label",
                        text="Tutor:",
                    ),
                    _resolved_span(
                        "u-paper-body:block-0013",
                        1,
                        "fill_slot",
                        field_id="advisor.name.en",
                        text="××××",
                    ),
                ],
            )
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert result["operation_count"] == 1
    assert _visible_paragraph_text(root) == ["Tutor:【填】"]
    assert _slot_aliases(root) == ["advisor.name.en"]
    receipt = result["mutation_receipts"][0]
    source_entry_id = result["operations"][0]["source_entry_id"]
    assert receipt["before_text_by_block"] == {source_entry_id: "Tutor:××××"}
    assert receipt["after_text_by_block"] == {source_entry_id: "Tutor:【填】"}


def test_materializer_materializes_leaf_section_as_structured_slot(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    text = "请在此处填写附录内容"
    block_id = "u-appendix:block-0001"
    _write_docx(source, [text])
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": block_id,
                "covered_object_ids": ["obj-appendix"],
                "text": text,
            }
        ]
    )
    review = {
        "semantic_judgments": [
            _judgment(
                block_id,
                [_part("fill_slot", text, field_id="appendix.body")],
                resolved_spans=[
                    _resolved_span(
                        block_id,
                        0,
                        "fill_slot",
                        field_id="appendix.body",
                        text=text,
                    )
                ],
            )
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert result["operation_count"] == 1
    assert _slot_aliases(root) == ["appendix.body"]
    assert _visible_paragraph_text(root) == ["【附录内容】"]


def test_materializer_adopts_inline_sdt_slot_block_without_dropping_sibling_label(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            (
                "<w:p>"
                "<w:r><w:t>姓名：</w:t></w:r>"
                "<w:sdt>"
                '<w:sdtPr><w:id w:val="1001"/></w:sdtPr>'
                "<w:sdtContent><w:r><w:t>【姓名】</w:t></w:r></w:sdtContent>"
                "</w:sdt>"
                "</w:p>"
            )
        ],
    )
    inventory = {
        "objects": [
            {
                "object_id": "obj-paragraph",
                "type": "paragraph",
                "locator": "/body/p[1]",
            },
            {"object_id": "obj-run", "type": "run", "locator": "/body/p[1]/r[1]"},
            {
                "object_id": "obj-sdt",
                "type": "sdt",
                "locator": "/body/p[1]/sdt[@sdtId=1001]",
            },
        ],
        "reading_blocks": [
            {
                "block_id": "u-cover:block-0001",
                "covered_object_ids": ["obj-paragraph", "obj-run"],
                "text": "姓名：",
            },
            {
                "block_id": "u-cover:block-0002",
                "covered_object_ids": ["obj-sdt"],
                "text": "【姓名】",
            },
        ],
    }
    review = {
        "semantic_judgments": [
            _fixed_judgment("u-cover:block-0001", "姓名："),
            _judgment(
                "u-cover:block-0002",
                [_part("fill_slot", "【姓名】", field_id="author.name.zh")],
                resolved_spans=[
                    _resolved_span(
                        "u-cover:block-0002",
                        0,
                        "fill_slot",
                        field_id="author.name.zh",
                        text="【姓名】",
                    )
                ],
            ),
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    control = next(root.iter(W + "sdt"))
    alias = control.find(f"{W}sdtPr/{W}alias")
    tag = control.find(f"{W}sdtPr/{W}tag")
    assert result["operation_count"] == 1
    assert _visible_paragraph_text(root) == ["姓名：【姓名】"]
    assert alias is not None and alias.get(f"{W}val") == "author.name.zh"
    accepted_slot_ref = result["operations"][0]["slot_ref"]
    assert tag is not None and tag.get(f"{W}val") == accepted_slot_ref
    assert result["operations"][0]["target"] == "existing_sdt"
    assert result["operations"][0]["span_ref"].startswith("source_entry_id=source-entry-")


def test_materializer_existing_sdt_adoption_rejects_slot_ref_not_derived_from_span_ref(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    control = ET.fromstring(
        f"""<w:sdt xmlns:w="{W_NS}">
        <w:sdtPr><w:id w:val="1001"/></w:sdtPr>
        <w:sdtContent><w:r><w:t>【姓名】</w:t></w:r></w:sdtContent>
        </w:sdt>"""
    )
    span = _resolved_span(
        "u-cover:block-0002",
        0,
        "fill_slot",
        field_id="author.name.zh",
        text="【姓名】",
    )
    span["slot_ref"] = _slot_ref("u-cover:block-0002", 1, "author.name.zh")

    with pytest.raises(ToolFailure) as failure:
        _adopt_existing_sdt_slots(
            control=control,
            block_id="u-cover:block-0002",
            registry=FieldRegistrySnapshot.load(registry_path),
            indexed_ordered_parts_for_block=[
                (0, _part("fill_slot", "【姓名】", field_id="author.name.zh"))
            ],
            resolved_spans=[span],
        )

    assert failure.value.code == "materialization_slot_ref_missing"
    assert control.find(f"{W}sdtPr/{W}alias") is None


def test_materializer_generated_content_policy_receipt_tracks_field_provenance(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["□□摘要……………………………………………………………………………1"])
    review = {
        "semantic_judgments": [
            _judgment(
                "u-toc:block-0001",
                [
                    _part(
                        "generated_content",
                        "□□摘要……………………………………………………………………………1",
                        field_id="generated.toc",
                    )
                ],
                resolved_spans=[
                    _resolved_span(
                        "u-toc:block-0001",
                        0,
                        "generated_content",
                        field_id="generated.toc",
                        text="□□摘要……………………………………………………………………………1",
                    )
                ],
            )
        ]
    }
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "u-toc:block-0001",
                "covered_object_ids": ["obj-1"],
                "text": "□□摘要……………………………………………………………………………1",
            }
        ],
    )

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    assert result["operation_count"] == 0
    policy_receipt = result["policy_receipts"][0]
    assert policy_receipt["action"] == "refresh_generated_content"
    assert policy_receipt["handler"] == "generated_content"
    assert policy_receipt["intent_ref"] == result["shadow_intent_plan"]["intents"][0]["intent_ref"]
    assert policy_receipt["source_judgment_refs"] == ["semantic_judgments[0]"]
    assert policy_receipt["scope_refs"][0]["kind"] == "source_entry"
    assert policy_receipt["field_ids"] == ["generated.toc"]
    assert policy_receipt["span_refs"][0].startswith("source_entry_id=source-entry-")
    assert policy_receipt["mutation"] == "none"
    assert policy_receipt["policy"] == "refresh_from_word_fields_after_fill"
    assert policy_receipt["word_fragments"][0]["text"] == ("□□摘要……………………………………………………………………………1")
    assert result["mutation_receipts"][0]["source_judgment_refs"] == ["semantic_judgments[0]"]
    assert result["mutation_receipts"][0]["field_ids"] == ["generated.toc"]
    assert "slot_refs" not in result["mutation_receipts"][0]
    assert "judgment_refs" not in result["mutation_receipts"][0]


def test_materializer_removes_style_only_span_inside_generated_content(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    source_text = "目□□录"
    _write_docx(source, [source_text])
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "u-toc:block-heading",
                "covered_object_ids": ["obj-1"],
                "text": source_text,
            }
        ],
    )
    review = {
        "semantic_judgments": [
            _judgment(
                "u-toc:block-heading",
                [
                    _part("generated_content", "目", field_id="generated.toc"),
                    _part("style_only", "□□"),
                    _part("generated_content", "录", field_id="generated.toc"),
                ],
            )
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    assert _visible_paragraph_text(_read_document(output)) == ["目录"]
    assert result["operation_count"] == 0
    assert result["cleanup_count"] == 1
    assert result["cleanup"][0]["action"] == "remove_exact_fragments"
    assert result["cleanup"][0]["word_fragments"][0]["text"] == "□□"
    assert result["policy_receipts"][0]["action"] == "refresh_generated_content"


def test_materializer_fails_closed_on_legacy_deferred_binding_shape(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    paragraphs = [
        "毕业论文（设计）中文题目（小二黑体，加粗，居中）",
        "学□□生：×××（或×□×） （五号宋体居中）",
        "□□摘□要（小四黑体）：…… （五号宋体）",
        "□□关键词：×××；×××；×××；×××",
    ]
    _write_docx(source, paragraphs)
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": f"front:block-{index:04d}",
                "covered_object_ids": [f"obj-{index}"],
                "text": text,
            }
            for index, text in enumerate(paragraphs, start=1)
        ],
    )
    review = {
        "semantic_judgments": [
            {
                "judgment_ref": "j-front",
                "semantic_role": "fill_slot",
                "clean_template_treatment": "keep_as_field_hint",
                "covered_reading_block_ids": [
                    "front:block-0001",
                    "front:block-0002",
                    "front:block-0003",
                    "front:block-0004",
                ],
                "judgment": "Registry binding deferred for this mixed front matter group.",
            }
        ]
    }

    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=FieldRegistrySnapshot.load(registry_path),
            inventory=inventory,
            review=review,
        )

    assert caught.value.code == "template_materialization_system_state_invalid"
    assert caught.value.status == "error"
    assert not caught.value.retryable
    assert not output.exists()


def test_materializer_rejects_accepted_incompatible_body_role(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["论文题目"])
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "body:block-0001",
                "covered_object_ids": ["obj-1"],
                "text": "论文题目",
            }
        ],
    )
    review = {
        "semantic_judgments": [
            {
                "scope": {"reading_block_id": "body:block-0001"},
                "parts": [
                    {
                        "text": "论文题目",
                        "role": "body_structure",
                        "field_id": "thesis.title.zh",
                    }
                ],
                "resolved_spans": [
                    _resolved_span(
                        "body:block-0001",
                        0,
                        "body_structure",
                        field_id="thesis.title.zh",
                        text="论文题目",
                    )
                ],
            }
        ]
    }

    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=FieldRegistrySnapshot.load(registry_path),
            inventory=inventory,
            review=review,
        )

    assert caught.value.code == "template_materialization_system_state_invalid"
    assert caught.value.origin == "harness"
    assert "materialization_semantic_review_not_current" in caught.value.message
    assert not output.exists()


def test_materializer_preserves_constants_around_embedded_department_slots(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(
        source,
        [
            "(湖南农业大学××××学院，长沙 410128)",
            "(College of×××××××, Hunan Agricultural University, Changsha 410128, China)",
        ],
    )
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "affiliation:block-0001",
                "covered_object_ids": ["obj-1"],
                "text": "(湖南农业大学××××学院，长沙 410128)",
            },
            {
                "block_id": "affiliation:block-0002",
                "covered_object_ids": ["obj-2"],
                "text": (
                    "(College of×××××××, Hunan Agricultural University, Changsha 410128, China)"
                ),
            },
        ],
    )
    review = {
        "semantic_judgments": [
            _judgment(
                "affiliation:block-0001",
                [
                    _part("fixed_label", "(湖南农业大学"),
                    _part("fill_slot", "××××学院", field_id="author.department"),
                    _part("fixed_label", "，长沙 410128)"),
                ],
                resolved_spans=[
                    _resolved_span(
                        "affiliation:block-0001",
                        0,
                        "fixed_label",
                        text="(湖南农业大学",
                    ),
                    _resolved_span(
                        "affiliation:block-0001",
                        1,
                        "fill_slot",
                        field_id="author.department",
                        text="××××学院",
                    ),
                    _resolved_span(
                        "affiliation:block-0001",
                        2,
                        "fixed_label",
                        text="，长沙 410128)",
                    ),
                ],
            ),
            _judgment(
                "affiliation:block-0002",
                [
                    _part("fixed_label", "(College of"),
                    _part("fill_slot", "×××××××", field_id="author.department.en"),
                    _part(
                        "fixed_label",
                        ", Hunan Agricultural University, Changsha 410128, China)",
                    ),
                ],
                resolved_spans=[
                    _resolved_span(
                        "affiliation:block-0002",
                        0,
                        "fixed_label",
                        text="(College of",
                    ),
                    _resolved_span(
                        "affiliation:block-0002",
                        1,
                        "fill_slot",
                        field_id="author.department.en",
                        text="×××××××",
                    ),
                    _resolved_span(
                        "affiliation:block-0002",
                        2,
                        "fixed_label",
                        text=", Hunan Agricultural University, Changsha 410128, China)",
                    ),
                ],
            ),
        ]
    }

    materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    assert _slot_aliases(root) == ["author.department", "author.department.en"]
    assert _visible_paragraph_text(root) == [
        "(湖南农业大学【填】，长沙 410128)",
        "(College of【填】, Hunan Agricultural University, Changsha 410128, China)",
    ]


def test_materializer_materializes_registry_body_structure(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_body_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(
        source,
        [
            "（以下农理工科类用）",
            "1□前言 （一级标题小三号黑体，顶格书写序数，空一格写标题）",
            "□□…… （正文的中文内容小四号宋体）",
            "2.1□×××××（二级标题四号黑体，顶格书写序数，空一格写标题）",
            "□□（1）……[1]。",
            "（以下文法经管类用）",
            "一、×××××（一级标题小三号黑体，顶格书写）",
        ],
    )
    inventory = _inventory_with_paragraph_objects(
        [
            {
                **{
                    "block_id": f"body:block-{index:04d}",
                    "covered_object_ids": [f"obj-{index}"],
                    "text": text,
                },
                **({"range_id": "body:range-science"} if 2 <= index <= 5 else {}),
            }
            for index, text in enumerate(
                [
                    "（以下农理工科类用）",
                    "1□前言 （一级标题小三号黑体，顶格书写序数，空一格写标题）",
                    "□□…… （正文的中文内容小四号宋体）",
                    "2.1□×××××（二级标题四号黑体，顶格书写序数，空一格写标题）",
                    "□□（1）……[1]。",
                    "（以下文法经管类用）",
                    "一、×××××（一级标题小三号黑体，顶格书写）",
                ],
                start=1,
            )
        ],
    )
    review = {
        "semantic_judgments": [
            _cleanup_judgment("body:block-0001", "（以下农理工科类用）"),
            _body_structure_judgment(
                [
                    ("body:block-0002", "1□前言", "body.heading.outline1"),
                    ("body:block-0003", "□□……", "body.paragraph"),
                    ("body:block-0004", "2.1□×××××", "body.heading.outline2"),
                    ("body:block-0005", "□□（1）……[1]。", "body.numbered_list_item"),
                ],
                range_id="body:range-science",
            ),
            _cleanup_judgment("body:block-0006", "（以下文法经管类用）"),
            _cleanup_judgment("body:block-0007", "一、×××××"),
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    text = "\n".join(_visible_paragraph_text(root))
    operation = result["operations"][0]
    assert operation["action"] == "materialize_structure"
    assert operation["structure_ref"] == "body.chapters"
    assert operation["member_count"] == 4
    assert [item["field_id"] for item in operation["members"]] == [
        "body.heading.outline1",
        "body.paragraph",
        "body.heading.outline2",
        "body.numbered_list_item",
    ]
    assert all(
        item["span_ref"].startswith("source_entry_id=source-entry-")
        and item["slot_ref"] == f"{item['span_ref']};field_id={item['field_id']}"
        for item in operation["members"]
    )
    assert _slot_aliases(root) == [
        "body.heading.outline1",
        "body.paragraph",
        "body.heading.outline2",
        "body.numbered_list_item",
    ]
    assert "以下农理工科类用" not in text
    assert "以下文法经管类用" not in text
    assert "一、×××××" not in text
    assert "【正文章节集合】" not in text
    assert "【章标题】" in text
    assert "【正文段落】" in text
    assert "【一级节标题】" in text
    assert "【数字列表项】" in text


def test_materializer_materializes_explicit_body_structure_members(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_body_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    paragraphs = [
        "1□前言 （一级标题小三号黑体）",
        "□□…… （正文的中文内容小四号宋体）",
        "2.1□×××××（二级标题四号黑体）",
        "一、×××××（一级标题小三号黑体，顶格书写）",
    ]
    _write_docx(source, paragraphs)
    inventory = _inventory_with_paragraph_objects(
        [
            {
                **{
                    "block_id": f"body:block-{index:04d}",
                    "covered_object_ids": [f"obj-{index}"],
                    "text": text,
                },
                **({"range_id": "body:range-science"} if 1 <= index <= 3 else {}),
            }
            for index, text in enumerate(paragraphs, start=1)
        ],
    )
    review = {
        "semantic_judgments": [
            _body_structure_judgment(
                [
                    ("body:block-0001", "1□前言", "body.heading.outline1"),
                    ("body:block-0002", "□□……", "body.paragraph"),
                    ("body:block-0003", "2.1□×××××", "body.heading.outline2"),
                ],
                range_id="body:range-science",
            ),
            _cleanup_judgment("body:block-0004", "一、×××××"),
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    text = "\n".join(_visible_paragraph_text(root))
    members = result["operations"][0]["members"]
    assert [item["field_id"] for item in members] == [
        "body.heading.outline1",
        "body.paragraph",
        "body.heading.outline2",
    ]
    assert all(
        item["span_ref"].startswith("source_entry_id=source-entry-")
        and item["slot_ref"] == f"{item['span_ref']};field_id={item['field_id']}"
        for item in members
    )
    assert result["operations"][0]["judgment_refs"] == [
        "semantic_judgments[0]",
        "semantic_judgments[1]",
        "semantic_judgments[2]",
    ]
    assert "一、×××××" not in text
    assert "【章标题】" in text
    assert "【正文段落】" in text
    assert "【一级节标题】" in text


def test_materializer_keeps_section_break_paragraphs_outside_structure_controls(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_body_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    paragraphs = ["第一章", "章节边界", "第二章"]
    _write_docx_from_paragraph_xml(
        source,
        [
            _paragraph(paragraphs[0]),
            _paragraph(
                paragraphs[1],
                '<w:pPr><w:sectPr><w:type w:val="nextPage"/></w:sectPr></w:pPr>',
            ),
            _paragraph(paragraphs[2]),
        ],
    )
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": f"body:block-{index:04d}",
                "covered_object_ids": [f"obj-{index}"],
                "text": text,
            }
            for index, text in enumerate(paragraphs, start=1)
        ],
    )
    review = {
        "semantic_judgments": [
            _body_structure_judgment(
                [
                    ("body:block-0001", "第一章", "body.heading.outline1"),
                    ("body:block-0003", "第二章", "body.heading.outline1"),
                ]
            ),
            _fixed_judgment("body:block-0002", "章节边界"),
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    body = root.find(f"{W}body")
    assert body is not None
    outer_controls = [child for child in body if child.tag == f"{W}sdt"]
    assert len(outer_controls) == 2
    assert not any(control.find(f".//{W}sectPr") is not None for control in outer_controls)
    section_paragraphs = [
        child
        for child in body
        if child.tag == f"{W}p" and child.find(f"{W}pPr/{W}sectPr") is not None
    ]
    assert len(section_paragraphs) == 1
    assert result["operations"][0]["member_count"] == 2


def test_materializer_coalesces_body_members_separated_only_by_removed_notes(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_body_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    source_text = "×××（正文小四宋体）×××。"
    _write_docx(source, [source_text])
    inventory = _inventory_with_paragraph_objects(
        [
            {
                "block_id": "body:block-0001",
                "covered_object_ids": ["obj-1"],
                "text": source_text,
            }
        ],
    )
    review = {
        "semantic_judgments": [
            _judgment(
                "body:block-0001",
                [
                    _part("body_structure", "×××", field_id="body.paragraph"),
                    _part("style_only", "（正文小四宋体）"),
                    _part("body_structure", "×××", field_id="body.paragraph"),
                    _part("fixed_label", "。"),
                ],
            )
        ]
    }

    result = materialize_template_from_semantics(
        source_docx=source, output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path), inventory=inventory, review=review,
    )
    assert result["operations"][0]["member_count"] == 1
    member = result["operations"][0]["members"][0]
    assert [s["part_index"] for s in member["coalescence"]["source_spans"]] == [0, 2]
    assert [s["part_index"] for s in member["coalescence"]["removed_spans"]] == [1]
    root = _read_document(output)
    assert _slot_aliases(root).count("body.paragraph") == 1
    assert _visible_paragraph_text(root) == ["【正文段落】。"]
    assert _visible_paragraph_text(_read_document(source)) == [source_text]


@pytest.mark.parametrize("field_id", ["body.table", "body.equation"])
def test_materializer_rejects_nested_composite_body_member_before_execution(
    tmp_path: Path, field_id: str,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_body_registry(registry_path)
    with registry_path.open("a") as registry_file:
        registry_file.write(
            f"\n  - field_id: {field_id}\n    label: Composite member\n"
            f"    content_type: {field_id.split('.')[-1]}\n"
            "    parent_field_id: body.chapters\n"
        )
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            (
                "<w:tbl><w:tr><w:tc>"
                '<w:p w14:paraId="BBBB0001"><w:r><w:t>1□前言</w:t></w:r></w:p>'
                "</w:tc></w:tr></w:tbl>"
            )
        ],
    )
    inventory = {
        "objects": [
            {
                "object_id": "obj-heading",
                "type": "run",
                "locator": "/body/tbl[1]/tr[1]/tc[1]/p[@paraId=BBBB0001]/r[1]",
            }
        ],
        "reading_blocks": [
            {
                "block_id": "body:block-0001",
                "covered_object_ids": ["obj-heading"],
                "order": 1,
                "text": "1□前言",
            }
        ],
    }
    review = {
        "semantic_judgments": [
            _body_structure_judgment([("body:block-0001", "1□前言", field_id)])
        ]
    }

    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=FieldRegistrySnapshot.load(registry_path),
            inventory=inventory,
            review=review,
        )

    assert caught.value.code == "template_materialization_execution_unsupported"
    assert caught.value.status == "error"
    assert not caught.value.retryable
    assert "materialization_body_structure_nested_composite_member" in str(caught.value)
    assert caught.value.origin == "tool"
    assert not output.exists()


def test_materializer_uses_exact_unquoted_para_id_fragment_locator(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_body_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            '<w:p w14:paraId="AAAA0001"><w:r><w:t></w:t></w:r></w:p>',
            _paragraph("（以下农理工科类用）"),
            '<w:p w14:paraId="CCCC0003"><w:r><w:t>1□前言</w:t></w:r></w:p>',
        ],
    )
    inventory = {
        "objects": [
            {
                "object_id": "obj-heading",
                "locator": "/body/p[@paraId=CCCC0003]/r[1]",
            }
        ],
        "reading_blocks": [
            {
                "block_id": "body:block-0001",
                "covered_object_ids": ["obj-heading"],
                "text": "1□前言",
            }
        ],
    }
    review = {
        "semantic_judgments": [
            _body_structure_judgment([("body:block-0001", "1□前言", "body.heading.outline1")])
        ]
    }

    materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review=review,
    )

    root = _read_document(output)
    para_ids = _slot_alias_para_ids(root)
    assert para_ids["body.heading.outline1"] == "CCCC0003"
    assert "（以下农理工科类用）" in "\n".join(_visible_paragraph_text(root))


def test_materializer_changes_only_the_accepted_same_text_paragraph(tmp_path: Path) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["×××", "×××"])
    inventory = {
        "objects": [{"object_id": "obj-2", "type": "paragraph", "locator": "/body/p[2]"}],
        "reading_blocks": [
            {
                "block_id": "target:block-0002",
                "covered_object_ids": ["obj-2"],
                "text": "×××",
            }
        ],
    }
    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review={
            "semantic_judgments": [_slot_judgment("target:block-0002", "thesis.title.zh", "×××")]
        },
    )

    assert result["operation_count"] == 1
    assert _visible_paragraph_text(_read_document(output)) == ["×××", "【中文题目】"]


def test_materializer_preflights_all_fragments_before_any_output(tmp_path: Path) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["first", "second"])
    inventory = {
        "objects": [
            {"object_id": "obj-1", "type": "paragraph", "locator": "/body/p[1]"},
            {"object_id": "obj-2", "type": "paragraph", "locator": "/body/p[99]"},
        ],
        "reading_blocks": [
            {"block_id": "b1", "covered_object_ids": ["obj-1"], "text": "first"},
            {"block_id": "b2", "covered_object_ids": ["obj-2"], "text": "second"},
        ],
    }
    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=FieldRegistrySnapshot.load(registry_path),
            inventory=inventory,
            review={
                "semantic_judgments": [
                    _slot_judgment("b1", "thesis.title.zh", "first"),
                    _slot_judgment("b2", "advisor.name.zh", "second"),
                ]
            },
        )

    assert caught.value.code == "materialization_word_fragment_stale"
    assert not output.exists()
    assert _visible_paragraph_text(_read_document(source)) == ["first", "second"]


def test_materializer_retry_from_same_source_is_position_stable(tmp_path: Path) -> None:
    registry_path = tmp_path / "input/field-registry.yaml"
    _write_registry(registry_path)
    registry = FieldRegistrySnapshot.load(registry_path)
    source = tmp_path / "input/template.docx"
    first = tmp_path / "work/first.docx"
    second = tmp_path / "work/second.docx"
    _write_docx(source, ["Title:×××", "untouched"])
    inventory = _inventory_with_paragraph_objects(
        [{"block_id": "b1", "covered_object_ids": ["obj-1"], "text": "Title:×××"}]
    )
    review = {
        "semantic_judgments": [
            _judgment(
                "b1",
                [
                    _part("fixed_label", "Title:"),
                    _part("fill_slot", "×××", field_id="thesis.title.zh"),
                ],
            )
        ]
    }
    first_result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=first,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    second_result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=second,
        registry=registry,
        inventory=inventory,
        review=review,
    )

    assert first_result["operations"] == second_result["operations"]
    assert first.read_bytes() == second.read_bytes()

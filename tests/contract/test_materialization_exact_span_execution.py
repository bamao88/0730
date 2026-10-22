from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from tests.support.source_identity import review_binding, source_partition

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = (
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
        + "</w:body></w:document>"
    )
    relationships = (
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
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)


def _write_docx_with_blank_value_cell(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = (
        f'<w:document xmlns:w="{W_NS}"><w:body><w:tbl><w:tr>'
        "<w:tc><w:p><w:r><w:t>姓名</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p/></w:tc>"
        "</w:tr></w:tbl></w:body></w:document>"
    )
    relationships = (
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
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)


def _write_registry(path: Path) -> FieldRegistrySnapshot:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "registry_id: exact-span-test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
                "  - field_id: body.chapters",
                "    label: 正文章节",
                "    content_type: section",
                "  - field_id: body.paragraph",
                "    label: 正文段落",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.heading.outline4",
                "    label: 四级标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.table",
                "    label: 表格",
                "    content_type: table",
                "    parent_field_id: body.chapters",
                "  - field_id: body.table.caption",
                "    label: 表题",
                "    content_type: text",
                "    parent_field_id: body.table",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _accepted_inputs(
    *,
    source: Path,
    registry: FieldRegistrySnapshot,
    paragraph_index: int,
    locator: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    source_hash = sha256_file(source)
    text = "×××"
    object_id = "object-selected-title"
    source_entry_id = f"source-entry-{sha256_json({'paragraph': paragraph_index})[:24]}"
    actual_locator = locator or f"/body/p[{paragraph_index}]"
    fingerprint = sha256_json(
        {"document_sha256": source_hash, "locator": actual_locator, "text": text}
    )
    object_ref = {
        "document_sha256": source_hash,
        "object_id": object_id,
        "expected_fingerprint": fingerprint,
    }
    vocabulary = registry.pre_input_vocabulary()
    inventory: dict[str, object] = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "objects": [
            {
                "object_id": object_id,
                "object_ref": object_ref,
                "expected_fingerprint": fingerprint,
                "source_entry_id": source_entry_id,
                "type": "paragraph",
                "locator": actual_locator,
                "text": text,
            }
        ],
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": paragraph_index, "inline": 0},
                "provenance": [
                    {
                        "object_id": object_id,
                        "locator": actual_locator,
                        "text_span": [0, len(text)],
                        "object_ref": object_ref,
                        "fingerprint": fingerprint,
                    }
                ],
            }
        ],
        "reading_blocks": [],
    }
    judgments: list[dict[str, object]] = [
        {
            "source_entry_id": source_entry_id,
            "parts": [
                {
                    "text": text,
                    "role": "fill_slot",
                    "field_id": "thesis.title.zh",
                }
            ],
        }
    ]
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    judgments[0]["resolved_spans"] = resolved
    review: dict[str, object] = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": judgments,
        "semantic_judgments_sha256": sha256_json(judgments),
        "resolved_spans": resolved,
    }
    return inventory, review


def _paragraph_texts(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    return [
        "".join(node.text or "" for node in paragraph.iter(f"{W}t"))
        for paragraph in document.iter(f"{W}p")
    ]


def test_materializer_changes_only_the_accepted_same_text_paragraph(tmp_path: Path) -> None:
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["×××", "×××"])
    registry = _write_registry(tmp_path / "input/field-registry.yaml")
    inventory, review = _accepted_inputs(source=source, registry=registry, paragraph_index=2)

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )

    assert result["operation_count"] == 1
    assert _paragraph_texts(output) == ["×××", "【中文题目】"]


def test_materializer_targets_the_accepted_empty_table_cell_whole_entry(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx_with_blank_value_cell(source)
    registry = _write_registry(tmp_path / "input/field-registry.yaml")
    source_hash = sha256_file(source)
    source_entry_id = "source-entry-blank-name-value"
    object_id = "object-blank-name-value"
    locator = "/body/tbl[1]/tr[1]/tc[2]/p[1]"
    fingerprint = sha256_json({"document_sha256": source_hash, "locator": locator, "text": ""})
    object_ref = {
        "document_sha256": source_hash,
        "object_id": object_id,
        "expected_fingerprint": fingerprint,
    }
    vocabulary = registry.pre_input_vocabulary()
    inventory: dict[str, object] = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "objects": [
            {
                "object_id": object_id,
                "object_ref": object_ref,
                "expected_fingerprint": fingerprint,
                "source_entry_id": source_entry_id,
                "type": "paragraph",
                "locator": locator,
                "text": "",
            }
        ],
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": "",
                "entry_type": "structural",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": object_id,
                        "locator": locator,
                        "extent": {"kind": "whole_entry"},
                        "object_ref": object_ref,
                        "fingerprint": fingerprint,
                    }
                ],
            }
        ],
        "reading_blocks": [],
    }
    judgments: list[dict[str, object]] = [
        {
            "source_entry_id": source_entry_id,
            "parts": [
                {
                    "text": "",
                    "role": "fill_slot",
                    "field_id": "thesis.title.zh",
                }
            ],
        }
    ]
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    judgments[0]["resolved_spans"] = resolved
    review: dict[str, object] = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": judgments,
        "semantic_judgments_sha256": sha256_json(judgments),
        "resolved_spans": resolved,
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )

    with zipfile.ZipFile(output) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    cells = list(document.iter(f"{W}tc"))
    assert result["operation_count"] == 1
    assert ["".join(node.text or "" for node in cell.iter(f"{W}t")) for cell in cells] == [
        "姓名",
        "【中文题目】",
    ]
    control = cells[1].find(f".//{W}sdt")
    assert control is not None
    assert control.find(f"{W}sdtPr/{W}alias").get(f"{W}val") == "thesis.title.zh"
    assert result["operations"][0]["span_ref"].endswith(
        f"extent=whole_entry;source_snapshot_sha256={source_hash}"
    )


def test_body_materializer_preserves_order_across_paragraph_and_table_members(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    source.parent.mkdir(parents=True, exist_ok=True)
    document = (
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        "<w:p><w:r><w:t>正文样例</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>表1 示例</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>固定说明</w:t></w:r></w:p>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:body></w:document>"
    )
    relationships = (
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
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
    registry = _write_registry(tmp_path / "input/field-registry.yaml")
    source_hash = sha256_file(source)
    vocabulary = registry.pre_input_vocabulary()
    facts = (
        (
            "source-entry-body-paragraph",
            "obj-body-paragraph",
            "正文样例",
            "/body/p[1]",
            "body.paragraph",
            "body_structure",
            "text",
        ),
        (
            "source-entry-table-caption",
            "obj-table-caption",
            "表1 示例",
            "/body/p[2]",
            "body.table.caption",
            "body_structure",
            "text",
        ),
        (
            "source-entry-table-cell",
            "obj-table-cell",
            "A",
            "/body/tbl[1]/tr[1]/tc[1]/p[1]",
            None,
            "fixed_label",
            "text",
        ),
        (
            "source-entry-table",
            "obj-table",
            "",
            "/body/tbl[1]",
            "body.table",
            "body_structure",
            "table",
        ),
    )
    entries: list[dict[str, object]] = []
    objects: list[dict[str, object]] = []
    judgments: list[dict[str, object]] = []
    for index, (entry_id, object_id, text, locator, field_id, role, entry_type) in enumerate(
        facts,
        start=1,
    ):
        fingerprint = sha256_json(
            {"document_sha256": source_hash, "locator": locator, "text": text}
        )
        object_ref = {
            "document_sha256": source_hash,
            "object_id": object_id,
            "expected_fingerprint": fingerprint,
        }
        provenance: dict[str, object] = {
            "object_id": object_id,
            "locator": locator,
            "object_ref": object_ref,
            "fingerprint": fingerprint,
        }
        if text:
            provenance["text_span"] = [0, len(text)]
        else:
            provenance["extent"] = {"kind": "whole_entry"}
        entries.append(
            {
                "source_entry_id": entry_id,
                "text": text,
                "entry_type": entry_type,
                "source_order": {"block": index, "inline": 0},
                "provenance": [provenance],
            }
        )
        objects.append(
            {
                "object_id": object_id,
                "source_entry_id": entry_id,
                "type": "table" if entry_type == "table" else "paragraph",
                "locator": locator,
                "text": text,
                "object_ref": object_ref,
                "expected_fingerprint": fingerprint,
            }
        )
        part: dict[str, object] = {"text": text, "role": role}
        if field_id is not None:
            part["field_id"] = field_id
        judgments.append({"source_entry_id": entry_id, "parts": [part]})
    inventory: dict[str, object] = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "objects": objects,
        "source_entries": entries,
        "reading_blocks": [],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted: list[dict[str, object]] = []
    for index, judgment in enumerate(judgments):
        accepted.append(
            {
                **judgment,
                "resolved_spans": [span for span in resolved if span["judgment_index"] == index],
            }
        )
    review: dict[str, object] = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": resolved,
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )

    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    aliases = [
        alias.get(f"{W}val") for alias in root.iter(f"{W}alias") if alias.get(f"{W}val") is not None
    ]
    assert result["operation_count"] == 1
    assert result["operations"][0]["structure_ref"] == "body.chapters"
    assert result["operations"][0]["member_count"] == 3
    assert aliases == ["body.paragraph", "body.table.caption", "body.table"]
    assert _paragraph_texts(output) == ["【正文段落】", "【表题】", "固定说明", "A"]


def test_body_materializer_builds_two_inline_interfaces_from_exact_spans(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    text = "□□（1）……[1]。（四级标题不单独占行）"
    _write_docx(source, [text])
    registry = _write_registry(tmp_path / "input/field-registry.yaml")
    source_hash = sha256_file(source)
    vocabulary = registry.pre_input_vocabulary()
    source_entry_id = "source-entry-inline-heading-and-body"
    object_id = "obj-inline-heading-and-body"
    locator = "/body/p[1]/r[1]"
    fingerprint = sha256_json({"document_sha256": source_hash, "locator": locator, "text": text})
    object_ref = {
        "document_sha256": source_hash,
        "object_id": object_id,
        "expected_fingerprint": fingerprint,
    }
    inventory: dict[str, object] = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "objects": [
            {
                "object_id": object_id,
                "source_entry_id": source_entry_id,
                "type": "run",
                "locator": locator,
                "text": text,
                "object_ref": object_ref,
                "expected_fingerprint": fingerprint,
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
    judgment = {
        "source_entry_id": source_entry_id,
        "parts": [
            {"text": "□□（1）", "role": "body_structure", "field_id": "body.heading.outline4"},
            {"text": "……[1]。", "role": "body_structure", "field_id": "body.paragraph"},
            {"text": "（四级标题不单独占行）", "role": "style_only"},
        ],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=[judgment])
    accepted = [{**judgment, "resolved_spans": resolved}]
    review: dict[str, object] = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": resolved,
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )

    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    aliases = [
        alias.get(f"{W}val") for alias in root.iter(f"{W}alias") if alias.get(f"{W}val") is not None
    ]
    assert result["operation_count"] == 1
    assert result["operations"][0]["member_count"] == 2
    assert [member["field_id"] for member in result["operations"][0]["members"]] == [
        "body.heading.outline4",
        "body.paragraph",
    ]
    assert aliases == ["body.heading.outline4", "body.paragraph"]
    assert _paragraph_texts(output) == ["【四级标题】【正文段落】"]


def test_cleanup_coalesces_overlapping_text_ranges_and_deletes_explicit_table(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    source.parent.mkdir(parents=True, exist_ok=True)
    document = (
        f'<w:document xmlns:w="{W_NS}"><w:body><w:p>'
        "<w:r><w:t>说明</w:t></w:r><w:r><w:t>续表</w:t></w:r>"
        "</w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p>"
        "</w:tc></w:tr></w:tbl></w:body></w:document>"
    )
    relationships = (
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
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
    registry = _write_registry(tmp_path / "input/field-registry.yaml")
    source_hash = sha256_file(source)
    vocabulary = registry.pre_input_vocabulary()
    facts = (
        (
            "source-entry-paragraph",
            "obj-paragraph",
            "/body/p[1]",
            "text",
            "说明续表",
            [0, 4],
        ),
        (
            "source-entry-shape",
            "obj-shape",
            "/body/p[1]/r[2]",
            "shape",
            "续表",
            [0, 2],
        ),
        ("source-entry-table", "obj-table", "/body/tbl[1]", "table", "", None),
    )
    entries: list[dict[str, object]] = []
    objects: list[dict[str, object]] = []
    judgments: list[dict[str, object]] = []
    for index, (entry_id, object_id, locator, entry_type, text, text_span) in enumerate(
        facts, start=1
    ):
        object_text = (
            "说明续表" if entry_type == "text" else "续表" if entry_type == "shape" else ""
        )
        fingerprint = sha256_json(
            {"document_sha256": source_hash, "locator": locator, "text": object_text}
        )
        object_ref = {
            "document_sha256": source_hash,
            "object_id": object_id,
            "expected_fingerprint": fingerprint,
        }
        provenance: dict[str, object] = {
            "object_id": object_id,
            "locator": locator,
            "object_ref": object_ref,
            "fingerprint": fingerprint,
        }
        if text_span is None:
            provenance["extent"] = {"kind": "whole_entry"}
        else:
            provenance["text_span"] = text_span
        entries.append(
            {
                "source_entry_id": entry_id,
                "text": text,
                "entry_type": entry_type,
                "source_order": {"block": index, "inline": 0},
                "provenance": [provenance],
            }
        )
        objects.append(
            {
                "object_id": object_id,
                "source_entry_id": entry_id,
                "type": (
                    "paragraph"
                    if entry_type == "text"
                    else "run"
                    if entry_type == "shape"
                    else "table"
                ),
                "locator": locator,
                "text": object_text,
                "object_ref": object_ref,
                "expected_fingerprint": fingerprint,
            }
        )
        judgments.append(
            {
                "source_entry_id": entry_id,
                "parts": [{"text": text, "role": "cleanup"}],
            }
        )
    inventory: dict[str, object] = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "objects": objects,
        "source_entries": entries,
        "reading_blocks": [],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [
        {
            **judgment,
            "resolved_spans": [span for span in resolved if span["judgment_index"] == index],
        }
        for index, judgment in enumerate(judgments)
    ]
    review: dict[str, object] = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": resolved,
    }

    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )

    assert result["cleanup_count"] == 3
    assert all(c["action"] == "remove_exact_fragments" for c in result["cleanup"][:2])
    assert result["cleanup"][2]["action"] == "remove_table"
    assert _paragraph_texts(output) == [""]


def test_materializer_preflights_stale_fragment_before_writing(tmp_path: Path) -> None:
    source = tmp_path / "input/template.docx"
    output = tmp_path / "work/candidate.docx"
    _write_docx(source, ["×××", "untouched"])
    registry = _write_registry(tmp_path / "input/field-registry.yaml")
    inventory, review = _accepted_inputs(
        source=source,
        registry=registry,
        paragraph_index=1,
        locator="/body/p[99]",
    )

    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )

    assert caught.value.code == "materialization_word_fragment_stale"
    assert not output.exists()
    assert _paragraph_texts(source) == ["×××", "untouched"]


def test_materializer_retry_is_position_stable(tmp_path: Path) -> None:
    source = tmp_path / "input/template.docx"
    first = tmp_path / "work/first.docx"
    second = tmp_path / "work/second.docx"
    _write_docx(source, ["untouched", "×××"])
    registry = _write_registry(tmp_path / "input/field-registry.yaml")
    inventory, review = _accepted_inputs(source=source, registry=registry, paragraph_index=2)

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


def test_exact_header_mapping_uses_relationship_order_and_writes_only_selected_part(tmp_path):
    source = tmp_path / "source.docx"
    _write_docx(source, ["×××"])
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr(
            "word/_rels/document.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="h9" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
                'Target="header9.xml"/>'
                '<Relationship Id="h1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
                'Target="header1.xml"/>'
                '<Relationship Id="f3" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
                'Target="footer3.xml"/>'
                "</Relationships>"
            ),
        )
        for part, tag in (("header9.xml", "hdr"), ("header1.xml", "hdr"), ("footer3.xml", "ftr")):
            archive.writestr(
                f"word/{part}",
                f'<w:{tag} xmlns:w="{W_NS}"><w:p><w:r><w:t>×××</w:t></w:r></w:p></w:{tag}>',
            )
    registry = _write_registry(tmp_path / "registry.yaml")
    inventory, review = _accepted_inputs(
        source=source, registry=registry, paragraph_index=1, locator="/header[1]/p[1]"
    )
    output = tmp_path / "candidate.docx"
    materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
        assert after.read("word/header1.xml") == before.read("word/header1.xml")
        assert after.read("word/footer3.xml") == before.read("word/footer3.xml")
        assert b"slot_ref" not in after.read("word/document.xml")
        header = ET.fromstring(after.read("word/header9.xml"))
        tags = [node.get(f"{W}val") for node in header.iter(f"{W}tag")]
        assert tags == [review["resolved_spans"][0]["slot_ref"]]


def test_exact_story_locator_never_searches_same_text_in_other_parts(tmp_path):
    from docfit.tools.word_parts import read_word_stories, resolve_story_locator

    source = tmp_path / "source.docx"
    _write_docx(source, ["×××"])
    with zipfile.ZipFile(source) as archive:
        stories = read_word_stories(archive)
    assert resolve_story_locator(stories, "/header[1]/p[1]") is None
    assert resolve_story_locator(stories, "/body/p[1]") is not None


def test_note_mapping_preserves_separator_positions_and_note_ids(tmp_path):
    from docfit.tools.word_parts import read_word_stories, resolve_story_locator

    source = tmp_path / "source.docx"
    _write_docx(source, ["body"])
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr(
            "word/_rels/document.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="n" '
                'Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/footnotes" '
                'Target="notes.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "word/notes.xml",
            (
                f'<w:footnotes xmlns:w="{W_NS}">'
                '<w:footnote w:id="-1" w:type="separator"><w:p/></w:footnote>'
                '<w:footnote w:id="17"><w:p><w:r><w:t>note</w:t></w:r></w:p></w:footnote>'
                "</w:footnotes>"
            ),
        )
    with zipfile.ZipFile(source) as archive:
        stories = read_word_stories(archive)
    first = resolve_story_locator(stories, "/footnote[1]/p[1]")
    second = resolve_story_locator(stories, "/footnote[2]/p[1]")
    assert first is not None and second is not None
    assert first[0].part_name == second[0].part_name == "word/notes.xml"
    assert first[0].root is second[0].root
    assert "".join(first[1].itertext()) == ""
    assert "".join(second[1].itertext()) == "note"
    assert resolve_story_locator(stories, "/footnote[17]/p[1]") is None


def test_cleanup_last_note_paragraph_preserves_legal_note_container(tmp_path):
    source = tmp_path / "source.docx"
    _write_docx(source, ["body"])
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr(
            "word/_rels/document.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="n" '
                'Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/footnotes" '
                'Target="notes.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "word/notes.xml",
            f'<w:footnotes xmlns:w="{W_NS}">'
            '<w:footnote w:id="17"><w:p><w:r><w:t>×××</w:t></w:r></w:p></w:footnote></w:footnotes>',
        )
    registry = _write_registry(tmp_path / "registry.yaml")
    inventory, review = _accepted_inputs(
        source=source, registry=registry, paragraph_index=1, locator="/footnote[1]/p[1]"
    )
    judgment = {
        "source_entry_id": inventory["source_entries"][0]["source_entry_id"],
        "parts": [{"text": "×××", "role": "cleanup"}],
    }
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=[judgment])
    judgment["resolved_spans"] = resolved
    review.update(
        semantic_judgments=[judgment],
        semantic_judgments_sha256=sha256_json([judgment]),
        resolved_spans=resolved,
    )
    output = tmp_path / "candidate.docx"
    materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    with zipfile.ZipFile(output) as archive:
        note = ET.fromstring(archive.read("word/notes.xml"))[0]
        assert note.get(f"{W}id") == "17"
        assert [child.tag for child in note] == [f"{W}p"]
        assert "".join(note.itertext()) == ""


def test_whole_table_slot_is_rejected_by_readiness_before_any_write(tmp_path):
    from docfit.template.materialization.readiness import materialization_readiness_feedback

    source = tmp_path / "source.docx"
    _write_docx_with_blank_value_cell(source)
    registry = _write_registry(tmp_path / "registry.yaml")
    inventory, review = _accepted_inputs(
        source=source, registry=registry, paragraph_index=1, locator="/body/tbl[1]"
    )
    entry = inventory["source_entries"][0]
    entry.update(text="", entry_type="structural")
    entry["provenance"][0].pop("text_span")
    entry["provenance"][0]["extent"] = {"kind": "whole_entry"}
    inventory.pop("canonical_source_inventory")
    source_partition(inventory)
    judgment = {
        "source_entry_id": entry["source_entry_id"],
        "parts": [
            {"text": "", "role": "fill_slot", "field_id": "thesis.title.zh"},
        ],
    }
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=[judgment])
    judgment["resolved_spans"] = resolved
    review.update(
        **review_binding(inventory),
        semantic_judgments=[judgment],
        semantic_judgments_sha256=sha256_json([judgment]),
        resolved_spans=resolved,
    )
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    assert feedback is not None
    assert "materialization_slot_carrier_unsupported" in {
        item["code"] for item in feedback["blockers"]
    }
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure, match="materialization_slot_carrier_unsupported"):
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert not output.exists()

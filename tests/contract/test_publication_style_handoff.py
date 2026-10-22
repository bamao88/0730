from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from docfit.app.prepare_template import (
    PreparedTemplateTask,
    TemplateAgentExecution,
    _accepted_semantics_allow_source_noop,
    _select_host_candidate_for_accepted_semantics,
    _validate_agent_completion,
)
from docfit.fields import FieldRegistrySnapshot
from docfit.styles.capture import slot_style_contract_id
from docfit.template.artifact import (
    _published_slots,
    publication_slot_protocol_status,
    publish_template_artifact,
)
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from tests.support.source_identity import persist_source_identity, review_binding, source_partition

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SOURCE_ENTRY_ID = "source-entry-u-all-block-0001"
SOURCE_SNAPSHOT_SHA256 = hashlib.sha256(b"PK\x03\x04source").hexdigest()
SPAN_REF = (
    f"source_entry_id={SOURCE_ENTRY_ID};extent=text[5:8];"
    f"source_snapshot_sha256={SOURCE_SNAPSHOT_SHA256}"
)
SLOT_REF = f"{SPAN_REF};field_id=thesis.title.zh"


@pytest.fixture(autouse=True)
def isolate_visual_review_from_style_handoff_contracts(monkeypatch):
    """These tests cover style/provenance; actual visual gates have dedicated tests."""
    monkeypatch.setattr(
        "docfit.template.artifact.validate_final_visual_review", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.require_final_visual_review",
        lambda **kwargs: {"render_ref": "synthetic-render", "reviewed_pages": [1]},
    )


def test_published_slot_uses_its_actual_package_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "header-slot.docx"
    registry = FieldRegistrySnapshot.load(_write_registry(tmp_path))
    header = (
        f'<w:hdr xmlns:w="{W_NS}"><w:sdt><w:sdtPr>'
        f'<w:alias w:val="thesis.title.zh"/><w:tag w:val="{SLOT_REF}"/>'
        "</w:sdtPr><w:sdtContent><w:p/></w:sdtContent></w:sdt></w:hdr>"
    )
    with zipfile.ZipFile(candidate, "w") as archive:
        archive.writestr(
            "word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body/></w:document>'
        )
        archive.writestr("word/header9.xml", header)
        archive.writestr(
            "word/_rels/document.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="header9.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"/>'
            "</Relationships>",
        )
    monkeypatch.setattr(
        "docfit.template.artifact.inspect_document_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(
            objects=(
                SimpleNamespace(kind="sdt", format={"alias": "thesis.title.zh", "tag": SLOT_REF}),
            )
        ),
    )
    slots, _ = _published_slots(candidate_docx=candidate, registry=registry, office=_FakeOffice())
    assert slots[0]["locator"] == {
        "type": "content_control_tag",
        "value": SLOT_REF,
        "story": "header",
        "part": "word/header9.xml",
        "expected_match_count": 1,
    }


def _span_ref(block_id: str, part_index: int) -> str:
    start, end = (0, 5) if part_index == 0 else (5, 8)
    return (
        f"source_entry_id=source-entry-{block_id.replace(':', '-')};"
        f"extent=text[{start}:{end}];"
        f"source_snapshot_sha256={SOURCE_SNAPSHOT_SHA256}"
    )


def _slot_ref(field_id: str, *, block_id: str = "u-all:block-0001", part_index: int = 1) -> str:
    return f"{_span_ref(block_id, part_index)};field_id={field_id}"


def _resolved_span(
    *,
    block_id: str,
    part_index: int,
    role: str,
    text: str,
    field_id: str | None = None,
) -> dict[str, object]:
    span: dict[str, object] = {
        "span_ref": _span_ref(block_id, part_index),
        "scope": {"reading_block_id": block_id},
        "reading_block_id": block_id,
        "part_index": part_index,
        "role": role,
        "text": text,
        "covered_object_ids": ["obj-title"],
    }
    if field_id is not None:
        span["field_id"] = field_id
        span["slot_ref"] = _slot_ref(field_id, block_id=block_id, part_index=part_index)
    return span


def _ordered_slot_judgment(
    field_id: str,
    *,
    block_id: str = "u-all:block-0001",
    label_text: str = "论文题目：",
    slot_text: str = "×××",
) -> dict[str, object]:
    return {
        "source_entry_id": f"source-entry-{block_id.replace(':', '-')}",
        "parts": [
            {"text": label_text, "role": "fixed_label"},
            {"text": slot_text, "role": "fill_slot", "field_id": field_id},
        ],
    }


def _ordered_manual_judgment(
    *,
    block_id: str = "u-all:block-0001",
    text: str = "整页表格",
    role: str = "manual_region",
) -> dict[str, object]:
    return {
        "source_entry_id": f"source-entry-{block_id.replace(':', '-')}",
        "parts": [{"text": text, "role": role}],
    }


def _write_registry(root: Path, *, field_id: str = "thesis.title.zh") -> Path:
    registry = root / "input/field-registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        {
            "field_id": "thesis.title.zh",
            "label": "论文题目",
            "meaning": "title",
            "content_type": "text",
        },
        {
            "field_id": "advisor.name.zh",
            "label": "导师姓名",
            "meaning": "advisor name",
            "content_type": "text",
        },
        {
            "field_id": "advisor.title",
            "label": "导师职称",
            "meaning": "advisor title",
            "content_type": "text",
        },
        {
            "field_id": "body.chapters",
            "label": "正文章节",
            "meaning": "body chapter structure",
            "content_type": "section",
        },
        {
            "field_id": "appendix.body",
            "label": "附录内容",
            "meaning": "structured appendix content",
            "content_type": "section",
        },
        {
            "field_id": "body.heading.outline1",
            "label": "章标题",
            "meaning": "body outline 1 heading",
            "content_type": "text",
            "parent_field_id": "body.chapters",
        },
        {
            "field_id": "body.paragraph",
            "label": "正文段落",
            "meaning": "body paragraph",
            "content_type": "rich_text",
            "parent_field_id": "body.chapters",
        },
        {
            "field_id": "body.table",
            "label": "正文表格",
            "meaning": "body table",
            "content_type": "table",
            "parent_field_id": "body.chapters",
        },
        {
            "field_id": "generated.toc",
            "label": "目录",
            "meaning": "table of contents generated from body headings",
            "content_type": "section",
            "value_sources": ["system_generated"],
        },
    ]
    if field_id not in {str(item["field_id"]) for item in fields}:
        fields.append(
            {
                "field_id": field_id,
                "label": field_id,
                "meaning": field_id,
                "content_type": "text",
            }
        )
    registry.write_text(
        json.dumps(
            {
                "registry_id": "docfit.test.fields",
                "registry_version": "0.1.0",
                "fields": fields,
            }
        ),
        encoding="utf-8",
    )
    return registry


def _prepared(root: Path) -> PreparedTemplateTask:
    template = root / "input/school-template.docx"
    registry = _write_registry(root)
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_bytes(b"PK\x03\x04source")
    return PreparedTemplateTask(
        task_root=root,
        template_path=template,
        requirements_path=None,
        registry_source=registry,
        template_sha256=sha256_file(template),
        requirements_sha256=None,
        registry_sha256=sha256_file(registry),
    )


def _write_docx_with_control(
    path: Path,
    *,
    alias: str | None,
    tag: str | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    properties = '<w:id w:val="1001"/>'
    if alias is not None:
        properties += f'<w:alias w:val="{alias}"/>'
    if tag is not None:
        properties += f'<w:tag w:val="{tag}"/>'
    document = f'''<w:document xmlns:w="{W_NS}">
      <w:body>
        <w:sdt>
          <w:sdtPr>{properties}</w:sdtPr>
          <w:sdtContent><w:p><w:r><w:t>School value</w:t></w:r></w:p></w:sdtContent>
        </w:sdt>
      </w:body>
    </w:document>'''
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


def _write_docx_with_controls(
    path: Path,
    *,
    controls: list[tuple[str | None, str | None]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    control_xml: list[str] = []
    for index, (alias, tag) in enumerate(controls, start=1):
        properties = f'<w:id w:val="{1000 + index}"/>'
        if alias is not None:
            properties += f'<w:alias w:val="{alias}"/>'
        if tag is not None:
            properties += f'<w:tag w:val="{tag}"/>'
        control_xml.append(
            f"""<w:sdt>
          <w:sdtPr>{properties}</w:sdtPr>
          <w:sdtContent><w:p><w:r><w:t>School value {index}</w:t></w:r></w:p></w:sdtContent>
        </w:sdt>"""
        )
    document = f'''<w:document xmlns:w="{W_NS}">
      <w:body>
        {"".join(control_xml)}
      </w:body>
    </w:document>'''
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


def _prepared_with_control(
    root: Path,
    *,
    alias: str | None,
    tag: str | None,
) -> PreparedTemplateTask:
    registry = _write_registry(root)
    template = root / "input/school-template.docx"
    _write_docx_with_control(template, alias=alias, tag=tag)
    return PreparedTemplateTask(
        task_root=root,
        template_path=template,
        requirements_path=None,
        registry_source=registry,
        template_sha256=sha256_file(template),
        requirements_sha256=None,
        registry_sha256=sha256_file(registry),
    )


def test_o1_publication_slot_protocol_rejects_registry_alias_without_harness_slot_ref(
    tmp_path: Path,
) -> None:
    root = tmp_path / "task"
    registry = _write_registry(root)
    candidate = root / "work/candidate.docx"
    _write_docx_with_controls(
        candidate,
        controls=[
            ("thesis.title.zh", SLOT_REF),
            ("advisor.name.zh", None),
        ],
    )

    result = publication_slot_protocol_status(
        candidate_docx=candidate,
        registry=FieldRegistrySnapshot.load(registry),
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "source_candidate_slot_protocol_invalid"
    assert result["invalid_slots"][0]["code"] == "content_control_slot_ref_missing"
    assert result["invalid_slots"][0]["field_id"] == "advisor.name.zh"


def test_o1_publication_slot_protocol_rejects_body_structure_container_field_marker(
    tmp_path: Path,
) -> None:
    root = tmp_path / "task"
    registry = _write_registry(root)
    candidate = root / "work/candidate.docx"
    body_structure_ref = _slot_ref("body.chapters")
    _write_docx_with_controls(
        candidate,
        controls=[
            ("body.chapters", body_structure_ref),
        ],
    )

    result = publication_slot_protocol_status(
        candidate_docx=candidate,
        registry=FieldRegistrySnapshot.load(registry),
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "source_candidate_slot_protocol_invalid"
    assert result["invalid_slots"][0]["code"] == "body_structure_container_field_published"
    assert result["invalid_slots"][0]["field_id"] == "body.chapters"


def test_o1_publication_slot_protocol_accepts_leaf_section_field_marker(
    tmp_path: Path,
) -> None:
    root = tmp_path / "task"
    registry = _write_registry(root)
    candidate = root / "work/candidate.docx"
    appendix_slot_ref = _slot_ref("appendix.body")
    _write_docx_with_controls(candidate, controls=[("appendix.body", appendix_slot_ref)])

    result = publication_slot_protocol_status(
        candidate_docx=candidate,
        registry=FieldRegistrySnapshot.load(registry),
    )

    assert result["status"] == "ok"
    assert result["slots"] == [
        {
            "slot_ref": appendix_slot_ref,
            "span_ref": appendix_slot_ref.removesuffix(";field_id=appendix.body"),
            "field_id": "appendix.body",
        }
    ]


def _complete_semantic_output() -> dict[str, object]:
    return {
        "status": "complete",
        "summary": "semantic judgments accepted",
        "semantic_judgments": [
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [{"text": "论文题目：×××", "role": "manual_region"}],
            }
        ],
    }


def _write_accepted_harness_review(
    root: Path,
    *,
    source_hash: str,
    semantic_judgments: list[dict[str, object]],
    reading_block_text: str = "论文题目：×××",
) -> None:
    harness = root / "work/.docfit/harness"
    harness.mkdir(parents=True, exist_ok=True)
    registry_path = root / "input/field-registry.json"
    vocabulary = (
        FieldRegistrySnapshot.load(registry_path).pre_input_vocabulary()
        if registry_path.is_file()
        else None
    )
    inventory: dict[str, object] = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "source_entries": [
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "text": reading_block_text,
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-title",
                        "locator": "/body/p[1]",
                        "fingerprint": "f" * 64,
                        "object_ref": {
                            "document_sha256": source_hash,
                            "object_id": "obj-title",
                            "expected_fingerprint": "f" * 64,
                        },
                        "text_span": [0, len(reading_block_text)],
                    }
                ],
            }
        ],
        "objects": [
            {
                "object_id": "obj-title",
                "object_ref": {
                    "document_sha256": source_hash,
                    "object_id": "obj-title",
                    "expected_fingerprint": "f" * 64,
                },
                "type": "paragraph",
                "locator": "/body/p[1]",
                "source_entry_id": SOURCE_ENTRY_ID,
            }
        ],
        "reading_blocks": [
            {
                "block_id": "u-all:block-0001",
                "range_id": "u-all:range-0001",
                "unit_id": "u-all",
                "text": reading_block_text,
                "covered_object_ids": ["obj-title"],
                "object_text_spans": [
                    {
                        "object_id": "obj-title",
                        "text": reading_block_text,
                        "text_start": 0,
                        "text_end": len(reading_block_text),
                    }
                ],
            }
        ],
    }
    review: dict[str, object] = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "semantic_judgments_sha256": sha256_json(semantic_judgments),
        "judgment_count": len(semantic_judgments),
        "semantic_judgments": semantic_judgments,
    }
    if vocabulary is not None:
        inventory["field_id_vocabulary"] = vocabulary
        inventory["field_vocabulary_digest"] = vocabulary["digest"]
        review["field_id_vocabulary"] = vocabulary
        review["field_vocabulary_digest"] = vocabulary["digest"]
    if semantic_judgments and all(
        isinstance(item.get("source_entry_id"), str) for item in semantic_judgments
    ):
        source_partition(inventory)
        persist_source_identity(root, inventory)
        review.update(review_binding(inventory))
        resolved = resolve_semantic_judgments(
            inventory=inventory,
            judgments=semantic_judgments,
        )
        semantic_judgments = [
            {
                **judgment,
                "resolved_spans": [
                    span for span in resolved if span.get("judgment_index") == index
                ],
            }
            for index, judgment in enumerate(semantic_judgments)
        ]
        review["semantic_judgments"] = semantic_judgments
        review["semantic_judgments_sha256"] = sha256_json(semantic_judgments)
        review["resolved_spans"] = resolved
    (harness / "object-inventory.json").write_text(
        json.dumps(inventory),
        encoding="utf-8",
    )
    (harness / "semantic-judgments.json").write_text(
        json.dumps(review),
        encoding="utf-8",
    )


def _assert_host_candidate_rejects_legacy_review(prepared: PreparedTemplateTask) -> None:
    with pytest.raises(ToolFailure) as blocked:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert blocked.value.code == "template_materialization_semantics_invalid"
    materialization_dir = prepared.task_root / "work/.docfit/post-unit-materialization"
    assert not (materialization_dir / "candidate-0001.docx").exists()
    assert not (materialization_dir / "materialization.json").exists()


def _write_publication_provenance(
    root: Path,
    *,
    registry: Path,
    source_hash: str,
    field_id: str = "thesis.title.zh",
    slot_ref: str = SLOT_REF,
    span_ref: str = SPAN_REF,
) -> None:
    harness = root / "work/.docfit/harness"
    materialization = root / "work/.docfit/post-unit-materialization"
    harness.mkdir(parents=True, exist_ok=True)
    materialization.mkdir(parents=True, exist_ok=True)
    registry_snapshot = FieldRegistrySnapshot.load(registry)
    vocabulary = registry_snapshot.pre_input_vocabulary()
    inventory = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "source_entries": [
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "text": "论文题目：×××",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-title",
                        "locator": "/body/p[1]",
                        "fingerprint": "f" * 64,
                        "object_ref": {
                            "document_sha256": source_hash,
                            "object_id": "obj-title",
                            "expected_fingerprint": "f" * 64,
                        },
                        "text_span": [0, len("论文题目：×××")],
                    }
                ],
            }
        ],
        "objects": [
            {
                "object_id": "obj-title",
                "object_ref": {
                    "document_sha256": source_hash,
                    "object_id": "obj-title",
                    "expected_fingerprint": "f" * 64,
                },
                "type": "paragraph",
                "locator": "/body/p[1]",
                "source_entry_id": SOURCE_ENTRY_ID,
            }
        ],
        "reading_blocks": [],
    }
    agent_judgments = [
        {
            "source_entry_id": SOURCE_ENTRY_ID,
            "parts": [
                {"text": "论文题目：", "role": "fixed_label"},
                {"text": "×××", "role": "fill_slot", "field_id": field_id},
            ],
        }
    ]
    source_partition(inventory)
    persist_source_identity(root, inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=agent_judgments)
    semantic_judgments = [{**agent_judgments[0], "resolved_spans": resolved}]
    semantic_judgments_sha256 = sha256_json(semantic_judgments)
    accepted_span = next(item for item in resolved if item.get("field_id") == field_id)
    (harness / "object-inventory.json").write_text(
        json.dumps(inventory),
        encoding="utf-8",
    )
    (harness / "semantic-judgments.json").write_text(
        json.dumps(
            {
                **review_binding(inventory),
                "schema_version": 2,
                "document_sha256": source_hash,
                "field_id_vocabulary": vocabulary,
                "field_vocabulary_digest": vocabulary["digest"],
                **review_binding(inventory),
                "semantic_judgments_sha256": semantic_judgments_sha256,
                "judgment_count": len(semantic_judgments),
                "semantic_judgments": semantic_judgments,
                "resolved_spans": resolved,
            }
        ),
        encoding="utf-8",
    )
    operation = {
        "action": "materialize_slot",
        "field_id": field_id,
        "span_ref": span_ref,
        "slot_ref": slot_ref,
        "source_entry_id": accepted_span["source_entry_id"],
        "word_fragments": accepted_span["word_fragments"],
    }
    candidate = root / "work/candidate.docx"
    (materialization / "materialization.json").write_text(
        json.dumps(
            {
                **review_binding(inventory),
                "schema_version": 2,
                "status": "ok",
                "document_sha256": source_hash,
                **review_binding(inventory),
                "semantic_judgments_sha256": semantic_judgments_sha256,
                "field_vocabulary_digest": vocabulary["digest"],
                "field_registry_ref": registry_snapshot.identity(),
                # Synthetic provenance for this isolated publication contract test.
                "effect_verification": {
                    "schema_version": 3, "status": "ok", "reopened_package": True,
                    "source_sha256": source_hash,
                    "semantic_judgments_sha256": semantic_judgments_sha256,
                    "candidate_sha256": sha256_file(candidate),
                },
                "operations": [operation],
                "mutation_receipts": [
                    {
                        "receipt_type": "mutation",
                        "field_ids": [field_id],
                        "span_refs": [span_ref],
                        "slot_refs": [slot_ref],
                        "operation": operation,
                    }
                ],
                "write": {
                    "status": "ok",
                    "output_sha256": sha256_file(candidate),
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "fault", ["missing", "unopened", "candidate", "source", "review", "legacy", "executor_scope"]
)
def test_publication_requires_bound_actual_effect_verification(tmp_path, fault):
    from docfit.template.artifact import _assert_materialization_bound_to_review

    registry_path = _write_registry(tmp_path)
    candidate = tmp_path / "work/candidate.docx"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"synthetic-publication-contract")
    _write_publication_provenance(
        tmp_path, registry=registry_path, source_hash=SOURCE_SNAPSHOT_SHA256
    )
    receipt = json.loads((
        tmp_path / "work/.docfit/post-unit-materialization/materialization.json"
    ).read_text())
    review = json.loads((tmp_path / "work/.docfit/harness/semantic-judgments.json").read_text())
    registry = FieldRegistrySnapshot.load(registry_path)
    _assert_materialization_bound_to_review(
        materialization=receipt, review=review, registry=registry
    )
    proof = receipt["effect_verification"]
    if fault == "missing":
        receipt.pop("effect_verification")
    elif fault == "unopened":
        proof["reopened_package"] = False
    elif fault in {"legacy", "executor_scope"}:
        proof["schema_version"] = 1 if fault == "legacy" else 2
    else:
        key = {"candidate": "candidate_sha256", "source": "source_sha256",
               "review": "semantic_judgments_sha256"}[fault]
        proof[key] = "0" * 64
    with pytest.raises(ToolFailure) as caught:
        _assert_materialization_bound_to_review(
            materialization=receipt, review=review, registry=registry
        )
    assert caught.value.code == "materialization_effect_verification_missing"


def test_o1_agent_completion_rejects_handwritten_style_contract_data(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path / "task")
    execution = TemplateAgentExecution(
        structured_output={
            "status": "complete",
            "summary": "done",
            "semantic_judgments": [{"judgment": "fixed source", "covered_unit_ids": ["u-all"]}],
            "style_contract_set_digest": "a" * 64,
        },
        tool_uses=("mcp__docfit__docfit_evidence",),
        skills_loaded=("docfit-school-extract",),
        session_id="session",
        backend="test",
        num_turns=1,
        duration_ms=1,
        duration_api_ms=1,
    )

    with pytest.raises(ToolFailure) as denied:
        _validate_agent_completion(prepared, execution)

    assert denied.value.status == "error"
    assert denied.value.origin == "postcondition"
    assert denied.value.code == "template_agent_style_contract_denied"


def test_o1_host_candidate_selection_allows_fixed_only_source_noop_without_docfit_slots(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            _ordered_manual_judgment(
                text="论文题目：×××",
                role="fixed_label",
            )
        ],
    )

    assert _accepted_semantics_allow_source_noop(prepared) is True
    assert _select_host_candidate_for_accepted_semantics(prepared) == prepared.template_path


def test_o1_host_candidate_selection_materializes_accepted_field_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[_ordered_slot_judgment("thesis.title.zh")],
    )
    calls: list[dict[str, object]] = []

    def fake_materialize(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        output = kwargs["output_docx"]
        assert isinstance(output, Path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"PK\x03\x04candidate")
        return {
            "schema_version": 2,
            "status": "ok",
            "operation_count": 1,
            "cleanup_count": 0,
            "operations": [
                {
                    "judgment_refs": ["semantic_judgments[0]"],
                    "field_id": "thesis.title.zh",
                    "span_ref": SPAN_REF,
                    "slot_ref": SLOT_REF,
                }
            ],
            "cleanup": [],
            "mutation_receipts": [
                {
                    "receipt_type": "mutation",
                    "handler": "slots",
                    "source_judgment_refs": ["semantic_judgments[0]"],
                    "field_ids": ["thesis.title.zh"],
                    "span_refs": [SPAN_REF],
                    "slot_refs": [SLOT_REF],
                }
            ],
            "receipt_count": 1,
            "write": {"status": "ok", "output_sha256": "c" * 64},
            "shadow_intent_plan": {
                "schema_version": 1,
                "ready": True,
                "intent_count": 1,
                "unsupported_count": 0,
                "intents": [
                    {
                        "intent_ref": "intent-0001",
                        "intent_type": "materialize_slot",
                        "field_ids": ["thesis.title.zh"],
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        fake_materialize,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publication_slot_protocol_status",
        lambda *, candidate_docx, registry: {
            "status": "ok",
            "slot_count": 1,
            "slots": [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                }
            ],
            "failure": None,
        },
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)

    assert candidate == (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    )
    assert calls[0]["source_docx"] == prepared.template_path
    receipt = json.loads(
        (
            prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "ok"
    assert receipt["operation_count"] == 1
    assert receipt["receipt_count"] == 1
    assert receipt["mutation_receipts"][0]["source_judgment_refs"] == ["semantic_judgments[0]"]
    assert receipt["write"]["output_sha256"] == "c" * 64
    assert receipt["shadow_intent_plan"]["intents"][0]["intent_type"] == "materialize_slot"


def test_o1_host_candidate_selection_rejects_legacy_slot_missing_field_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-title",
                "judgment": "title slot",
                "covered_object_ids": ["obj-title"],
                "covered_reading_block_ids": ["u-all:block-0001"],
                "clean_template_treatment": "convert_to_field_slot",
                "semantic_role": "fill_slot",
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_legacy_direct_slot_missing_field_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        reading_block_text="×××",
        semantic_judgments=[
            {
                "judgment_ref": "j-direct-title",
                "judgment": "direct title slot",
                "covered_reading_block_ids": ["u-all:block-0001"],
                "materialization_intent": "materialize_slot",
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_legacy_invalid_direct_intent_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-invalid",
                "judgment": "invalid direct intent",
                "covered_reading_block_ids": ["u-all:block-0001"],
                "materialization_intent": "materialise_slot",
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_legacy_unknown_structure_ref_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-references",
                "judgment": "references entries slot with unsupported structure wrapper",
                "covered_reading_block_ids": ["u-all:block-0001"],
                "clean_template_treatment": "convert_to_field_slot",
                "semantic_role": "fill_slot",
                "registry_field": "thesis.title.zh",
                "structure_ref": "references.list",
                "members": ["thesis.title.zh"],
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_accepted_incompatible_slot_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        reading_block_text="×××",
        semantic_judgments=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [
                    {
                        "text": "×××",
                        "role": "fill_slot",
                        "field_id": "body.chapters",
                    }
                ],
                "resolved_spans": [
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=0,
                        role="fill_slot",
                        text="×××",
                        field_id="body.chapters",
                    )
                ],
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    with pytest.raises(ToolFailure) as blocked:
        _select_host_candidate_for_accepted_semantics(prepared)

    # Persisted reviews cannot bypass the same field/role gate as live submissions.
    assert blocked.value.code == "template_materialization_semantics_invalid"
    assert blocked.value.origin == "harness"
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
    ).exists()
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


def test_o1_host_candidate_selection_rejects_legacy_unknown_field_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        reading_block_text="×××",
        semantic_judgments=[
            {
                "judgment_ref": "j-title",
                "judgment": "title slot",
                "covered_object_ids": ["obj-title"],
                "covered_reading_block_ids": ["u-all:block-0001"],
                "clean_template_treatment": "convert_to_field_slot",
                "semantic_role": "fill_slot",
                "registry_field": {"field_id": "school.unknown.field"},
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_materializes_body_structure_judgments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolBody",
        tag="school.body",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [
                    {
                        "text": "论文题目：×××",
                        "role": "body_structure",
                        "field_id": "body.heading.outline1",
                    }
                ],
                "resolved_spans": [
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=0,
                        role="body_structure",
                        text="论文题目：×××",
                        field_id="body.heading.outline1",
                    )
                ],
            }
        ],
    )
    calls: list[dict[str, object]] = []

    def fake_materialize(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        output = kwargs["output_docx"]
        assert isinstance(output, Path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"PK\x03\x04candidate")
        return {
            "schema_version": 2,
            "status": "ok",
            "operation_count": 1,
            "cleanup_count": 0,
            "operations": [
                {
                    "judgment_refs": ["semantic_judgments[0]"],
                    "action": "materialize_structure",
                    "structure_ref": "body.chapters",
                    "span_ref": "reading_block_id=u-all:block-0001;part_index=0",
                    "members": [
                        {
                            "field_id": "body.heading.outline1",
                            "block_id": "u-all:block-0001",
                            "span_ref": "reading_block_id=u-all:block-0001;part_index=0",
                            "slot_ref": (
                                "reading_block_id=u-all:block-0001;part_index=0;"
                                "field_id=body.heading.outline1"
                            ),
                        }
                    ],
                }
            ],
            "cleanup": [],
            "mutation_receipts": [
                {
                    "receipt_type": "mutation",
                    "handler": "body_structure",
                    "source_judgment_refs": ["semantic_judgments[0]"],
                    "field_ids": ["body.heading.outline1"],
                    "span_refs": ["reading_block_id=u-all:block-0001;part_index=0"],
                    "slot_refs": [
                        (
                            "reading_block_id=u-all:block-0001;part_index=0;"
                            "field_id=body.heading.outline1"
                        ),
                    ],
                }
            ],
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        fake_materialize,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publication_slot_protocol_status",
        lambda *, candidate_docx, registry: {
            "status": "ok",
            "slot_count": 1,
            "slots": [
                {
                    "slot_ref": (
                        "reading_block_id=u-all:block-0001;part_index=0;"
                        "field_id=body.heading.outline1"
                    ),
                    "span_ref": "reading_block_id=u-all:block-0001;part_index=0",
                    "field_id": "body.heading.outline1",
                }
            ],
            "body_structure_count": 1,
            "failure": None,
        },
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)

    assert candidate == (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    )
    assert calls[0]["source_docx"] == prepared.template_path
    receipt = json.loads(
        (
            prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "ok"
    assert receipt["operations"][0]["action"] == "materialize_structure"


def test_o1_host_candidate_selection_allows_generated_only_candidate_without_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared(tmp_path / "task")
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [
                    {
                        "text": "□□摘要……………………………………………………………………………1",
                        "role": "generated_content",
                        "field_id": "generated.toc",
                    }
                ],
                "resolved_spans": [
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=0,
                        role="generated_content",
                        text="□□摘要……………………………………………………………………………1",
                        field_id="generated.toc",
                    )
                ],
            }
        ],
        reading_block_text="□□摘要……………………………………………………………………………1",
    )
    publishability_calls: list[bool] = []

    def fake_materialize(**kwargs: object) -> dict[str, object]:
        output = kwargs["output_docx"]
        assert isinstance(output, Path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"PK\x03\x04candidate")
        return {
            "schema_version": 2,
            "status": "ok",
            "operation_count": 0,
            "cleanup_count": 0,
            "operations": [],
            "cleanup": [],
            "policy_receipts": [
                {
                    "receipt_type": "policy",
                    "handler": "generated_content",
                    "source_judgment_refs": ["semantic_judgments[0]"],
                    "field_ids": ["generated.toc"],
                    "span_refs": ["reading_block_id=u-all:block-0001;part_index=0"],
                }
            ],
            "mutation_receipts": [
                {
                    "receipt_type": "policy",
                    "handler": "generated_content",
                    "source_judgment_refs": ["semantic_judgments[0]"],
                    "field_ids": ["generated.toc"],
                    "span_refs": ["reading_block_id=u-all:block-0001;part_index=0"],
                }
            ],
        }

    def fake_publishability(
        *,
        candidate_docx: Path,
        registry: FieldRegistrySnapshot,
        allow_no_slots: bool = False,
    ) -> dict[str, object]:
        del candidate_docx, registry
        publishability_calls.append(allow_no_slots)
        return {
            "status": "ok",
            "slot_count": 0,
            "school_content_control_count": 0,
            "slots": [],
            "failure": None,
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        fake_materialize,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publication_slot_protocol_status",
        fake_publishability,
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)

    assert candidate == (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    )
    assert publishability_calls == [True]
    receipt = json.loads(
        (
            prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "ok"
    assert receipt["policy_receipts"][0]["field_ids"] == ["generated.toc"]
    assert "slot_refs" not in receipt["policy_receipts"][0]


def test_o1_host_candidate_selection_rejects_legacy_body_missing_semantics_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolBody",
        tag="school.body",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-body",
                "judgment": "body structure",
                "covered_object_ids": ["obj-title"],
                "covered_reading_block_ids": ["u-all:block-0001"],
                "clean_template_treatment": "transfer_style_to_slot",
                "semantic_role": "body_section_structure_template",
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_legacy_body_member_carrier_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolBody",
        tag="school.body",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-body-table",
                "judgment": "table member incorrectly bound to paragraph block",
                "covered_object_ids": ["obj-title"],
                "covered_reading_block_ids": ["u-all:block-0001"],
                "clean_template_treatment": "transfer_style_to_slot",
                "semantic_role": "body_section_structure_template",
                "structure_ref": "body.chapters",
                "members": ["body.table"],
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_legacy_body_variants_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolBody",
        tag="school.body",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-body-a",
                "judgment": "first body track",
                "covered_object_ids": ["obj-title"],
                "covered_reading_block_ids": ["u-all:block-0001"],
                "clean_template_treatment": "transfer_style_to_slot",
                "semantic_role": "body_section_structure_template",
                "structure_ref": "body.chapters",
                "members": ["body.heading.outline1"],
            },
            {
                "judgment_ref": "j-body-b",
                "judgment": "second body track",
                "covered_object_ids": ["obj-title"],
                "covered_reading_block_ids": ["u-all:block-0001"],
                "clean_template_treatment": "transfer_style_to_slot",
                "semantic_role": "body_section_structure_template",
                "structure_ref": "body.chapters",
                "members": ["body.paragraph"],
            },
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_accepted_incompatible_body_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolBody",
        tag="school.body",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        reading_block_text="论文题目",
        semantic_judgments=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [
                    {
                        "text": "论文题目",
                        "role": "body_structure",
                        "field_id": "thesis.title.zh",
                    }
                ],
                "resolved_spans": [
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=0,
                        role="body_structure",
                        text="论文题目",
                        field_id="thesis.title.zh",
                    )
                ],
            }
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        lambda **_kwargs: pytest.fail("readiness gate must block before materialization"),
    )

    with pytest.raises(ToolFailure) as blocked:
        _select_host_candidate_for_accepted_semantics(prepared)

    # Persisted reviews cannot bypass the same field/role gate as live submissions.
    assert blocked.value.code == "template_materialization_semantics_invalid"
    assert blocked.value.origin == "harness"
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
    ).exists()
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


def test_o1_host_candidate_selection_materializes_shared_target_field_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        reading_block_text="指导老师及职称：×××□教授",
        semantic_judgments=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [
                    {"text": "指导老师及职称：", "role": "fixed_label"},
                    {"text": "×××", "role": "fill_slot", "field_id": "advisor.name.zh"},
                    {"text": "□", "role": "cleanup"},
                    {"text": "教授", "role": "fill_slot", "field_id": "advisor.title"},
                ],
                "resolved_spans": [
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=0,
                        role="fixed_label",
                        text="指导老师及职称：",
                    ),
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=1,
                        role="fill_slot",
                        text="×××",
                        field_id="advisor.name.zh",
                    ),
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=2,
                        role="cleanup",
                        text="□",
                    ),
                    _resolved_span(
                        block_id="u-all:block-0001",
                        part_index=3,
                        role="fill_slot",
                        text="教授",
                        field_id="advisor.title",
                    ),
                ],
            }
        ],
    )
    calls: list[dict[str, object]] = []

    def fake_materialize(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        output = kwargs["output_docx"]
        assert isinstance(output, Path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"PK\x03\x04candidate")
        return {
            "schema_version": 2,
            "status": "ok",
            "operation_count": 2,
            "cleanup_count": 0,
            "operations": [
                {
                    "judgment_refs": ["semantic_judgments[0]"],
                    "field_id": "advisor.name.zh",
                    "span_ref": "reading_block_id=u-all:block-0001;part_index=1",
                    "slot_ref": (
                        "reading_block_id=u-all:block-0001;part_index=1;field_id=advisor.name.zh"
                    ),
                },
                {
                    "judgment_refs": ["semantic_judgments[0]"],
                    "field_id": "advisor.title",
                    "span_ref": "reading_block_id=u-all:block-0001;part_index=3",
                    "slot_ref": (
                        "reading_block_id=u-all:block-0001;part_index=3;field_id=advisor.title"
                    ),
                },
            ],
            "cleanup": [],
        }

    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {
            "status": "needs_input",
            "failure": {"message": "source has no DocFit slot"},
        },
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.materialize_template_from_semantics",
        fake_materialize,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.publication_slot_protocol_status",
        lambda *, candidate_docx, registry: {
            "status": "ok",
            "slot_count": 2,
            "slots": [
                {
                    "slot_ref": (
                        "reading_block_id=u-all:block-0001;part_index=1;field_id=advisor.name.zh"
                    ),
                    "span_ref": "reading_block_id=u-all:block-0001;part_index=1",
                    "field_id": "advisor.name.zh",
                },
                {
                    "slot_ref": (
                        "reading_block_id=u-all:block-0001;part_index=3;field_id=advisor.title"
                    ),
                    "span_ref": "reading_block_id=u-all:block-0001;part_index=3",
                    "field_id": "advisor.title",
                },
            ],
            "failure": None,
        },
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)

    assert candidate == (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    )
    assert calls[0]["source_docx"] == prepared.template_path
    receipt = json.loads(
        (
            prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["operation_count"] == 2
    assert receipt["operations"] == [
        {
            "judgment_refs": ["semantic_judgments[0]"],
            "field_id": "advisor.name.zh",
            "span_ref": "reading_block_id=u-all:block-0001;part_index=1",
            "slot_ref": ("reading_block_id=u-all:block-0001;part_index=1;field_id=advisor.name.zh"),
        },
        {
            "judgment_refs": ["semantic_judgments[0]"],
            "field_id": "advisor.title",
            "span_ref": "reading_block_id=u-all:block-0001;part_index=3",
            "slot_ref": ("reading_block_id=u-all:block-0001;part_index=3;field_id=advisor.title"),
        },
    ]


def test_o1_host_candidate_selection_rejects_source_noop_without_accepted_semantics(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="thesis.title.zh",
        tag=SLOT_REF,
    )

    with pytest.raises(ToolFailure) as blocked:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert blocked.value.code == "template_materialization_inventory_missing"


def test_o1_host_candidate_selection_rejects_legacy_direct_intent_before_source_noop(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="thesis.title.zh",
        tag=SLOT_REF,
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-invalid-direct",
                "judgment": "invalid direct intent must not be bypassed by source noop",
                "covered_reading_block_ids": ["u-all:block-0001"],
                "materialization_intent": "materialise_slot",
            }
        ],
    )

    with pytest.raises(ToolFailure) as blocked:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert blocked.value.code == "template_materialization_semantics_invalid"
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
    ).exists()


def test_o1_host_candidate_selection_allows_terminal_manual_unit_source_noop(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            _ordered_manual_judgment(
                text="论文题目：×××",
                role="manual_region",
            )
        ],
    )

    assert _accepted_semantics_allow_source_noop(prepared) is True
    assert _select_host_candidate_for_accepted_semantics(prepared) == prepared.template_path


def test_o1_host_candidate_selection_allows_fixed_style_only_source_noop(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    text = "相关的学术成果目录（三号黑体，居中）"
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        reading_block_text=text,
        semantic_judgments=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [
                    {"text": "相关的学术成果目录", "role": "fixed_label"},
                    {"text": "（三号黑体，居中）", "role": "style_only"},
                ],
            }
        ],
    )

    assert _accepted_semantics_allow_source_noop(prepared) is True
    assert _select_host_candidate_for_accepted_semantics(prepared) == prepared.template_path


def test_o1_host_candidate_selection_allows_real_whole_unit_form_source_noop(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            _ordered_manual_judgment(
                text="论文题目：×××",
                role="manual_region",
            )
        ],
    )

    assert _accepted_semantics_allow_source_noop(prepared) is True
    assert _select_host_candidate_for_accepted_semantics(prepared) == prepared.template_path


def test_o1_host_candidate_selection_allows_terminal_manual_form_block_scope_noop(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            _ordered_manual_judgment(
                text="论文题目：×××",
                role="manual_region",
            )
        ],
    )

    assert _accepted_semantics_allow_source_noop(prepared) is True
    assert _select_host_candidate_for_accepted_semantics(prepared) == prepared.template_path


def test_o1_host_candidate_selection_rejects_legacy_terminal_manual_form_with_delete(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-proposal-keep",
                "judgment": "keep proposal form blocks",
                "covered_reading_block_ids": ["u-proposal:block-0001"],
                "covered_object_ids": ["obj-title"],
                "clean_template_treatment": "keep_as_terminal_form",
                "semantic_role": "school_manual_terminal_form",
            },
            {
                "judgment_ref": "j-proposal-notes",
                "judgment": "delete proposal notes",
                "covered_reading_block_ids": ["u-proposal:block-0002"],
                "covered_object_ids": ["obj-title"],
                "clean_template_treatment": "delete_template_note",
                "semantic_role": "template_note",
            },
        ],
    )

    assert _accepted_semantics_allow_source_noop(prepared) is False
    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_host_candidate_selection_rejects_legacy_non_terminal_source_noop_with_delete(
    tmp_path: Path,
) -> None:
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            {
                "judgment_ref": "j-toc-title",
                "judgment": "keep generated TOC heading",
                "covered_unit_ids": ["u-toc"],
                "covered_object_ids": ["obj-title"],
                "clean_template_treatment": "keep",
                "semantic_role": "generated_toc",
            },
            {
                "judgment_ref": "j-toc-placeholder",
                "judgment": "remove source placeholder entries",
                "covered_unit_ids": ["u-toc"],
                "covered_object_ids": ["obj-title"],
                "clean_template_treatment": "delete",
                "semantic_role": "source_placeholder",
            },
        ],
    )

    assert _accepted_semantics_allow_source_noop(prepared) is False
    _assert_host_candidate_rejects_legacy_review(prepared)


def test_o1_final_validation_accepts_fixed_only_source_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.validate",
        lambda self, args: {"status": "ok", "checks": []},
    )
    prepared = _prepared_with_control(
        tmp_path / "task",
        alias="SchoolTitle",
        tag="school.title",
    )
    _write_accepted_harness_review(
        prepared.task_root,
        source_hash=prepared.template_sha256,
        semantic_judgments=[
            _ordered_manual_judgment(
                text="论文题目：×××",
                role="fixed_label",
            )
        ],
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        lambda _prepared, _output: None,
    )
    execution = TemplateAgentExecution(
        structured_output=_complete_semantic_output(),
        tool_uses=("mcp__docfit__docfit_evidence",),
        skills_loaded=("docfit-school-extract",),
        session_id="session",
        backend="test",
        num_turns=1,
        duration_ms=1,
        duration_api_ms=1,
    )

    candidate, _visual_review, _validation = _validate_agent_completion(
        prepared,
        execution,
    )

    assert candidate == prepared.template_path


def test_o1_publish_rejects_dirty_output_directory_before_writing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    candidate.parent.mkdir(parents=True)
    (root / "output").mkdir()
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    (root / "output/extra.txt").write_text("extra", encoding="utf-8")
    candidate_hash = sha256_file(candidate)

    with pytest.raises(ToolFailure) as dirty:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
        )

    assert dirty.value.code == "template_output_directory_not_clean"
    assert sorted(path.name for path in (root / "output").iterdir()) == ["extra.txt"]


class _FakeStyle:
    style_contract_id = slot_style_contract_id(SLOT_REF)
    contract_digest = "d" * 64

    def as_dict(self) -> dict[str, object]:
        return {
            "style_contract_id": self.style_contract_id,
            "contract_digest": self.contract_digest,
            "application_scope": "text",
            "owned_properties": ["paragraph.alignment"],
            "effective_properties": {"paragraph.alignment": "center"},
            "override_policy": {
                "managed_direct_formatting": "clear_conflicts",
                "unmanaged_properties": "preserve",
            },
            "dependencies": [],
        }


class _FakeStyleSet:
    styles = (_FakeStyle(),)
    digest = "c" * 64


class _FakeObservationSet:
    profile_registry_digest = "p" * 64


class _FakeSchoolCapture:
    observation_set = _FakeObservationSet()
    school_candidates = ({"style_role_id": "style.slot"},)
    known_gaps: tuple[dict[str, object], ...] = ()
    failed_observations: tuple[dict[str, object], ...] = ()
    school_observation_set_digest = "e" * 64
    status = "passed"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "profile_registry_digest": self.observation_set.profile_registry_digest,
            "school_observation_set_digest": self.school_observation_set_digest,
            "failed_observations": [],
        }


class _FakeOffice:
    def validate_snapshot(self, _document: Path) -> dict[str, object]:
        return {"name": "fake-office", "status": "ok"}


def test_o1_publish_rejects_registry_alias_control_without_harness_slot_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    candidate_hash = sha256_file(candidate)

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact.inspect_document_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(
            objects=(
                SimpleNamespace(
                    kind="sdt",
                    format={"alias": "thesis.title.zh", "tag": SLOT_REF},
                ),
                SimpleNamespace(kind="sdt", format={"alias": "advisor.name.zh"}),
            )
        ),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "content_control_slot_ref_missing"
    assert not (root / "output/final-template.docx").exists()
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_rejects_body_structure_container_field_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    candidate_hash = sha256_file(candidate)
    body_structure_ref = _slot_ref("body.chapters")

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact.inspect_document_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(
            objects=(
                SimpleNamespace(
                    kind="sdt",
                    format={"alias": "body.chapters", "tag": body_structure_ref},
                ),
            )
        ),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "body_structure_container_field_published"
    assert not (root / "output/final-template.docx").exists()
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_fill_contract_binds_hash_registry_locators_style_refs_and_exact_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    candidate.parent.mkdir(parents=True)
    (root / "output").mkdir()
    source.write_bytes(b"PK\x03\x04source")
    _write_docx_with_control(candidate, alias="thesis.title.zh", tag=SLOT_REF)
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=source_hash,
    )
    locator = {
        "type": "content_control_tag",
        "value": SLOT_REF,
        "story": "document",
        "part": "word/document.xml",
        "expected_match_count": 1,
    }

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": locator,
                    "handling": "styled",
                }
            ],
            0,
        ),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_contracts",
        lambda _candidate, _slots: (_FakeStyleSet(), {"status": "passed"}),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_observations",
        lambda _candidate, _slots: _FakeSchoolCapture(),
    )

    receipt = publish_template_artifact(
        task_root=root,
        source_docx=source,
        candidate_docx=candidate,
        field_registry=registry,
        validation={"final_sha256": candidate_hash, "status": "ok"},
        visual_review={
            "document_sha256": candidate_hash,
            "render_ref": "render:v2:" + "0" * 64,
            "reviewed_pages": [1],
            "findings": [],
        },
        office=_FakeOffice(),
    )

    assert receipt["published"] is True
    assert sorted(path.name for path in (root / "output").iterdir()) == [
        "fill-contract.yaml",
        "final-template.docx",
    ]
    payload = yaml.safe_load((root / "output/fill-contract.yaml").read_text(encoding="utf-8"))
    assert payload["template_sha256"] == candidate_hash
    assert payload["field_registry_ref"]["sha256"] == sha256_file(registry)
    assert payload["style_contract_set_digest"] == "c" * 64
    assert payload["slots"][0]["locator"] == locator
    assert payload["slots"][0]["slot_ref"] == SLOT_REF
    assert payload["slots"][0]["provenance"]["slot_ref"] == SLOT_REF
    assert payload["slots"][0]["provenance"]["source_entry_id"] == SOURCE_ENTRY_ID
    assert payload["slots"][0]["provenance"]["word_fragments"]
    assert (
        payload["slots"][0]["provenance"]["accepted_result"]["source_judgment_ref"]
        == "semantic_judgments[0]"
    )
    assert payload["slots"][0]["provenance"]["actual_result"]["outcome"] == "applied"
    assert payload["slots"][0]["style_contract_ref"] == {
        "style_contract_id": slot_style_contract_id(SLOT_REF),
        "contract_digest": "d" * 64,
    }
    assert payload["validation"]["final_visual_review"]["document_sha256"] == candidate_hash


def test_o1_publish_rejects_slot_provenance_source_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=candidate_hash,
    )
    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_contracts",
        lambda _candidate, _slots: (_FakeStyleSet(), {"status": "passed"}),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_observations",
        lambda _candidate, _slots: _FakeSchoolCapture(),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "template_initial_inventory_invalid"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_rejects_slot_provenance_missing_resolved_span_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=source_hash,
    )
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["objects"].append(
        {
            "object_id": "obj-unresolved",
            "object_ref": {
                "document_sha256": source_hash,
                "object_id": "obj-unresolved",
                "expected_fingerprint": "e" * 64,
            },
            "type": "run",
            "locator": "/body/p[1]/r[2]",
        }
    )
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_contracts",
        lambda _candidate, _slots: (_FakeStyleSet(), {"status": "passed"}),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_observations",
        lambda _candidate, _slots: _FakeSchoolCapture(),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "template_slot_semantics_invalid"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_allows_span_covering_text_object_not_carrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    _write_docx_with_control(candidate, alias="thesis.title.zh", tag=SLOT_REF)
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=source_hash,
    )
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["objects"] = [
        {
            "object_id": "obj-carrier",
            "object_ref": {
                "document_sha256": source_hash,
                "object_id": "obj-carrier",
                "expected_fingerprint": "e" * 64,
            },
            "type": "paragraph",
            "locator": "/body/p[1]",
            "source_entry_id": SOURCE_ENTRY_ID,
        },
        {
            "object_id": "obj-title",
            "object_ref": {
                "document_sha256": source_hash,
                "object_id": "obj-title",
                "expected_fingerprint": "f" * 64,
            },
            "type": "run",
            "locator": "/body/p[1]/r[1]",
            "source_entry_id": SOURCE_ENTRY_ID,
        },
    ]
    inventory["source_entries"][0]["provenance"] = [
        {
            "object_id": "obj-carrier",
            "locator": "/body/p[1]",
            "fingerprint": "e" * 64,
            "object_ref": inventory["objects"][0]["object_ref"],
            "text_span": [0, len("论文题目：×××")],
        },
        {
            "object_id": "obj-title",
            "locator": "/body/p[1]/r[1]",
            "fingerprint": "f" * 64,
            "object_ref": inventory["objects"][1]["object_ref"],
            "text_span": [0, len("论文题目：×××")],
        },
    ]
    inventory.pop("canonical_source_inventory")
    source_partition(inventory)
    persist_source_identity(root, inventory)
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    review_path = root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    agent_judgments = [
        {key: value for key, value in judgment.items() if key != "resolved_spans"}
        for judgment in review["semantic_judgments"]
    ]
    source_partition(inventory)
    persist_source_identity(root, inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=agent_judgments,
    )
    review["semantic_judgments"] = [{**agent_judgments[0], "resolved_spans": resolved}]
    review["resolved_spans"] = resolved
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    review.update(review_binding(inventory))
    review_path.write_text(json.dumps(review), encoding="utf-8")
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    materialization.update(review_binding(inventory))
    materialization["semantic_judgments_sha256"] = review["semantic_judgments_sha256"]
    materialization["effect_verification"]["semantic_judgments_sha256"] = (
        review["semantic_judgments_sha256"]
    )
    accepted_slot_span = next(
        item for item in resolved if item.get("field_id") == "thesis.title.zh"
    )
    materialization["operations"][0]["word_fragments"] = accepted_slot_span["word_fragments"]
    materialization["mutation_receipts"][0]["operation"] = materialization["operations"][0]
    materialization_path.write_text(json.dumps(materialization), encoding="utf-8")
    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_contracts",
        lambda _candidate, _slots: (_FakeStyleSet(), {"status": "passed"}),
    )
    monkeypatch.setattr(
        "docfit.template.artifact.capture_template_style_observations",
        lambda _candidate, _slots: _FakeSchoolCapture(),
    )

    receipt = publish_template_artifact(
        task_root=root,
        source_docx=source,
        candidate_docx=candidate,
        field_registry=registry,
        validation={"final_sha256": candidate_hash, "status": "ok"},
        visual_review={"document_sha256": candidate_hash},
        office=_FakeOffice(),
    )

    assert receipt["status"] == "ok"
    payload = yaml.safe_load((root / "output/fill-contract.yaml").read_text(encoding="utf-8"))
    assert payload["slots"][0]["slot_ref"] == SLOT_REF


def test_o1_publish_requires_accepted_inventory_vocabulary_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=source_hash,
    )
    (root / "work/.docfit/harness/object-inventory.json").unlink()

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "template_slot_provenance_missing"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_rejects_materialization_vocabulary_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=source_hash,
    )
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    materialization["field_vocabulary_digest"] = "0" * 64
    materialization_path.write_text(json.dumps(materialization), encoding="utf-8")

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "published_slot_materialization_vocabulary_mismatch"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_rejects_materialization_receipt_field_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=source_hash,
    )
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    materialization["mutation_receipts"][0]["field_ids"] = ["advisor.name.zh"]
    materialization_path.write_text(json.dumps(materialization), encoding="utf-8")

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "published_slot_receipt_missing"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_does_not_infer_materialization_operation_from_slot_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_publication_provenance(
        root,
        registry=registry,
        source_hash=source_hash,
    )
    materialization_path = root / "work/.docfit/post-unit-materialization/materialization.json"
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    materialization["operations"][0].pop("field_id")
    materialization_path.write_text(json.dumps(materialization), encoding="utf-8")

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: (
            [
                {
                    "slot_ref": SLOT_REF,
                    "span_ref": SPAN_REF,
                    "field_id": "thesis.title.zh",
                    "content_type": "text",
                    "required": True,
                    "locator": {"type": "content_control_tag", "value": SLOT_REF},
                    "handling": "styled",
                }
            ],
            0,
        ),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash},
            office=_FakeOffice(),
        )

    assert rejected.value.code == "published_slot_operation_mismatch"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_rejects_no_slot_publication_without_accepted_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    registry = _write_registry(root)
    _write_docx_with_controls(source, controls=[])
    source_hash = sha256_file(source)

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: ([], 0),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=source,
            field_registry=registry,
            validation={"final_sha256": source_hash, "status": "ok"},
            visual_review={"document_sha256": source_hash, "findings": []},
            allow_no_slots=True,
            office=_FakeOffice(),
        )

    assert rejected.value.code == "template_no_slot_provenance_missing"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_rejects_no_slot_materialized_candidate_without_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    candidate = root / "work/candidate.docx"
    registry = _write_registry(root)
    source.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"PK\x03\x04source")
    candidate.write_bytes(b"PK\x03\x04candidate")
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    _write_accepted_harness_review(
        root,
        source_hash=source_hash,
        reading_block_text="目录",
        semantic_judgments=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "parts": [
                    {"text": "目录", "role": "generated_content", "field_id": "generated.toc"}
                ],
                "resolved_spans": [
                    {
                        "span_ref": "reading_block_id=u-all:block-0001;part_index=0",
                        "scope": {"reading_block_id": "u-all:block-0001"},
                        "reading_block_id": "u-all:block-0001",
                        "part_index": 0,
                        "role": "generated_content",
                        "field_id": "generated.toc",
                        "slot_ref": (
                            "reading_block_id=u-all:block-0001;part_index=0;field_id=generated.toc"
                        ),
                        "text": "目录",
                        "covered_object_ids": ["obj-title"],
                    }
                ],
            }
        ],
    )

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: ([], 0),
    )

    with pytest.raises(ToolFailure) as rejected:
        publish_template_artifact(
            task_root=root,
            source_docx=source,
            candidate_docx=candidate,
            field_registry=registry,
            validation={"final_sha256": candidate_hash, "status": "ok"},
            visual_review={"document_sha256": candidate_hash, "findings": []},
            allow_no_slots=True,
            office=_FakeOffice(),
        )

    assert rejected.value.code == "template_no_slot_materialization_missing"
    assert not (root / "output/fill-contract.yaml").exists()


def test_o1_publish_allows_accepted_terminal_source_noop_without_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    registry = _write_registry(root)
    _write_docx_with_controls(source, controls=[])
    source_hash = sha256_file(source)
    _write_accepted_harness_review(
        root,
        source_hash=source_hash,
        semantic_judgments=[
            _ordered_manual_judgment(
                text="论文题目：×××",
                role="manual_region",
            )
        ],
    )

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", lambda _path: [])
    monkeypatch.setattr(
        "docfit.template.artifact._published_slots",
        lambda **_kwargs: ([], 0),
    )

    receipt = publish_template_artifact(
        task_root=root,
        source_docx=source,
        candidate_docx=source,
        field_registry=registry,
        validation={"final_sha256": source_hash, "status": "ok"},
        visual_review={"document_sha256": source_hash, "findings": []},
        allow_no_slots=True,
        office=_FakeOffice(),
    )

    assert receipt["counts"] == {
        "slot": 0,
        "remove": 0,
        "manual": 1,
        "gap": 0,
        "unresolved": 0,
    }
    payload = yaml.safe_load((root / "output/fill-contract.yaml").read_text(encoding="utf-8"))
    assert payload["slots"] == []
    assert payload["styles"] == []
    assert payload["provenance"]["no_slot_semantic_provenance"]["source"] == (
        "accepted_no_slot_semantic_review"
    )
    assert payload["provenance"]["no_slot_semantic_provenance"]["roles"] == ["manual_region"]
    assert payload["validation"]["style_capture"]["status"] == "skipped"
    assert (
        payload["validation"]["school_style_observation"]["status"] == "skipped_no_registry_slots"
    )


def test_o1_publication_module_does_not_depend_on_student_content_fixtures() -> None:
    source = Path("src/docfit/template/artifact.py").read_text(encoding="utf-8")

    assert "student_content" not in source
    assert "student-content" not in source
    assert "tests/fixtures" not in source

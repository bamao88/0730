from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.app.prepare_template import (
    PreparedTemplateTask,
    _ensure_post_unit_inventory,
    _select_host_candidate_for_accepted_semantics,
)
from docfit.fields import FieldRegistrySnapshot
from docfit.template.harness import TemplateHarnessService
from docfit.template.reading_packet import (
    agent_visible_unit_reading_packet,
    build_unit_reading_packet,
)
from docfit.template.source_entries import (
    CanonicalSourceInventory,
    build_canonical_source_inventory,
    select_source_entries_for_objects,
)
from docfit.template.source_spans import SourceSpanResolutionError, resolve_semantic_judgments
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.service import DocFitToolService
from tests.support.source_identity import persist_source_identity, review_binding, source_partition

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
MINIMAL_UNITS = ROOT / "evals/fixtures/template-extraction/minimal-units-0820/units"
THREE_SCHOOL_ASSETS = ROOT / "temp/manual-gold-preparation/gold/10-school-assets"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _task_from_docx(
    *,
    tmp_path: Path,
    source_docx: Path,
    unit_id: str,
) -> tuple[PreparedTemplateTask, dict[str, object]]:
    root = tmp_path / "task"
    input_dir = root / "input"
    harness_dir = root / "work/.docfit/harness"
    input_dir.mkdir(parents=True)
    harness_dir.mkdir(parents=True)
    (root / "output").mkdir()
    template = input_dir / "school-template.docx"
    registry = input_dir / "field-registry.yaml"
    shutil.copyfile(source_docx, template)
    shutil.copyfile(REGISTRY, registry)
    prepared = PreparedTemplateTask(
        task_root=root,
        template_path=template,
        requirements_path=None,
        registry_source=registry,
        template_sha256=sha256_file(template),
        requirements_sha256=None,
        registry_sha256=sha256_file(registry),
    )
    inventory = _inventory_for_docx(template, unit_id=unit_id)
    vocabulary = FieldRegistrySnapshot.load(registry).pre_input_vocabulary()
    inventory["field_id_vocabulary"] = vocabulary
    inventory["field_vocabulary_digest"] = vocabulary["digest"]
    (harness_dir / "object-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return prepared, inventory


def _inventory_for_docx(path: Path, *, unit_id: str) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    body = document.find(f"{W}body")
    assert body is not None
    objects: list[dict[str, object]] = []
    reading_blocks: list[dict[str, object]] = []
    top_level_paragraphs = [child for child in list(body) if child.tag == f"{W}p"]
    for index, paragraph in enumerate(top_level_paragraphs, start=1):
        block_id = f"{unit_id}:block-{index:04d}"
        range_id = f"{unit_id}:range-{index:04d}"
        object_id = f"obj-{index:04d}"
        text = "".join(node.text or "" for node in paragraph.iter(f"{W}t"))
        fingerprint = sha256_json({"locator": f"/body/p[{index}]", "text": text})
        objects.append(
            {
                "object_id": object_id,
                "object_ref": {
                    "document_sha256": sha256_file(path),
                    "object_id": object_id,
                    "expected_fingerprint": fingerprint,
                },
                "expected_fingerprint": fingerprint,
                "type": "paragraph",
                "locator": f"/body/p[{index}]",
                "text": text,
            }
        )
        block: dict[str, object] = {
            "block_id": block_id,
            "range_id": range_id,
            "unit_id": unit_id,
            "text": text,
            "covered_object_ids": [object_id],
        }
        if text:
            block["object_text_spans"] = [
                {
                    "object_id": object_id,
                    "text": text,
                    "text_start": 0,
                    "text_end": len(text),
                }
            ]
        reading_blocks.append(block)
    document_sha256 = sha256_file(path)
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=document_sha256,
        inspected_objects=objects,
    )
    source_entries = [entry.to_json() for entry in canonical.source_entries]
    for obj, entry in zip(objects, source_entries, strict=True):
        obj["source_entry_id"] = entry["source_entry_id"]
    inventory = {
        "schema_version": 2,
        "document_sha256": document_sha256,
        "canonical_source_inventory": canonical.to_json(),
        "source_entries": source_entries,
        "object_count": len(objects),
        "reading_block_count": len(reading_blocks),
        "objects": objects,
        "reading_blocks": reading_blocks,
    }
    source_partition(inventory, unit_id=unit_id)
    return inventory


def _write_accepted_review(
    prepared: PreparedTemplateTask,
    judgments: list[dict[str, object]],
) -> None:
    inventory_path = prepared.task_root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    blocks = {
        str(block["block_id"]): block
        for block in inventory["reading_blocks"]
        if isinstance(block, dict)
    }
    objects = {str(obj["object_id"]): obj for obj in inventory["objects"] if isinstance(obj, dict)}
    current_judgments: list[dict[str, object]] = []
    for judgment in judgments:
        parts = judgment.get("parts")
        legacy_spans = judgment.get("resolved_spans")
        assert isinstance(parts, list) and isinstance(legacy_spans, list)
        grouped: list[tuple[str, list[dict[str, str]]]] = []
        for part, span in zip(parts, legacy_spans, strict=True):
            assert isinstance(part, dict) and isinstance(span, dict)
            block_id = span.get("reading_block_id")
            assert isinstance(block_id, str)
            block = blocks[block_id]
            object_ids = block.get("covered_object_ids")
            assert isinstance(object_ids, list) and object_ids
            source_entry_id = objects[str(object_ids[0])].get("source_entry_id")
            assert isinstance(source_entry_id, str)
            if grouped and grouped[-1][0] == source_entry_id:
                grouped[-1][1].append(part)
            else:
                grouped.append((source_entry_id, [part]))
        current_judgments.extend(
            {"source_entry_id": source_entry_id, "parts": grouped_parts}
            for source_entry_id, grouped_parts in grouped
        )
    if inventory.get("fixture_preserve_unselected"):
        selected_ids = {judgment["source_entry_id"] for judgment in current_judgments}
        current_judgments.extend(
            {
                "source_entry_id": entry["source_entry_id"],
                "parts": [{"text": entry["text"], "role": "fixed_label"}],
            }
            for entry in inventory["source_entries"]
            if entry["source_entry_id"] not in selected_ids
        )
        order = {entry["source_entry_id"]: i for i, entry in enumerate(inventory["source_entries"])}
        current_judgments.sort(key=lambda judgment: order[judgment["source_entry_id"]])
    persist_source_identity(prepared.task_root, inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=current_judgments,
    )
    current_judgments = [
        {
            **judgment,
            "resolved_spans": [span for span in resolved if span.get("judgment_index") == index],
        }
        for index, judgment in enumerate(current_judgments)
    ]
    vocabulary = FieldRegistrySnapshot.load(prepared.registry_source).pre_input_vocabulary()
    payload = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": prepared.template_sha256,
        "judgment_count": len(current_judgments),
        "semantic_judgments_sha256": sha256_json(current_judgments),
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": current_judgments,
        "resolved_spans": resolved,
    }
    review_path = prepared.task_root / "work/.docfit/harness/semantic-judgments.json"
    review_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_inventory(
    prepared: PreparedTemplateTask,
    inventory: dict[str, object],
) -> None:
    persist_source_identity(prepared.task_root, inventory)
    inventory_path = prepared.task_root / "work/.docfit/harness/object-inventory.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _accept_with_harness(
    *,
    prepared: PreparedTemplateTask,
    inventory: dict[str, object],
    judgments: list[dict[str, object]],
) -> dict[str, object]:
    source_partition(inventory)
    persist_source_identity(prepared.task_root, inventory)
    harness = TemplateHarnessService(task_root=prepared.task_root)
    inventory_result = harness.handle(
        {
            "action": "submit_object_inventory",
            "document_sha256": inventory["document_sha256"],
            "objects": inventory["objects"],
            "reading_blocks": inventory["reading_blocks"],
            "source_entries": inventory["source_entries"],
            "canonical_source_inventory": inventory["canonical_source_inventory"],
            "unit_boundary_proof": inventory["unit_boundary_proof"],
            "unit_projection_digest": inventory["unit_projection_digest"],
        }
    )
    assert inventory_result["status"] == "ok", inventory_result
    blocks = [block for block in inventory["reading_blocks"] if isinstance(block, dict)]
    objects = {str(obj["object_id"]): obj for obj in inventory["objects"] if isinstance(obj, dict)}
    current_judgments: list[dict[str, object]] = []
    for judgment in judgments:
        if isinstance(judgment.get("source_entry_id"), str):
            current_judgments.append(judgment)
            continue
        scope = judgment.get("scope")
        parts = judgment.get("parts")
        assert isinstance(scope, dict) and isinstance(parts, list)
        range_id = scope.get("reading_range_id")
        range_blocks = [
            block
            for block in blocks
            if block.get("range_id") == range_id or block.get("unit_range_id") == range_id
        ]
        assert len(range_blocks) == len(parts)
        for block, part in zip(range_blocks, parts, strict=True):
            object_ids = block.get("covered_object_ids")
            assert isinstance(object_ids, list) and object_ids
            source_entry_id = objects[str(object_ids[0])]["source_entry_id"]
            current_judgments.append({"source_entry_id": source_entry_id, "parts": [part]})
    if inventory.get("fixture_preserve_unselected"):
        selected_ids = {judgment["source_entry_id"] for judgment in current_judgments}
        current_judgments.extend(
            {
                "source_entry_id": entry["source_entry_id"],
                "parts": [{"text": entry["text"], "role": "fixed_label"}],
            }
            for entry in inventory["source_entries"]
            if entry["source_entry_id"] not in selected_ids
        )
        order = {entry["source_entry_id"]: i for i, entry in enumerate(inventory["source_entries"])}
        current_judgments.sort(key=lambda judgment: order[judgment["source_entry_id"]])
    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": inventory["document_sha256"],
            "semantic_judgments": current_judgments,
        }
    )
    assert result["status"] == "ok", result
    return result


def _receipt(prepared: PreparedTemplateTask) -> dict[str, object]:
    path = prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_hash_bound_candidate(
    prepared: PreparedTemplateTask,
    candidate: Path,
) -> dict[str, object]:
    receipt = _receipt(prepared)
    validate_docx_package(candidate)
    assert receipt["status"] == "ok"
    assert receipt["candidate_sha256"] == sha256_file(candidate)
    assert receipt["write"]["status"] == "ok"
    assert receipt["write"]["executor"] == "ooxml_executor"
    assert receipt["write"]["package_validation"] == "ok"
    assert receipt["write"]["output_sha256"] == receipt["candidate_sha256"]
    assert "agent_revision_packet" not in receipt
    assert receipt["mutation_receipts"]
    return receipt


def _span_ref(block_id: str, part_index: int) -> str:
    return f"reading_block_id={block_id};part_index={part_index}"


def _slot_ref(block_id: str, part_index: int, field_id: str) -> str:
    return f"{_span_ref(block_id, part_index)};field_id={field_id}"


def _object_id_for_block(block_id: str) -> str:
    _prefix, marker, suffix = block_id.rpartition("block-")
    return f"obj-{suffix}" if marker and suffix else "obj-0001"


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
    scope: dict[str, str] | None = None,
) -> dict[str, object]:
    span_scope = scope or {"reading_block_id": block_id}
    if "reading_range_id" in span_scope:
        span_ref = f"reading_range_id={span_scope['reading_range_id']};part_index={part_index}"
    else:
        span_ref = _span_ref(block_id, part_index)
    span: dict[str, object] = {
        "span_ref": span_ref,
        "scope": span_scope,
        "reading_block_id": block_id,
        "part_index": part_index,
        "role": role,
        "text": text,
        "covered_object_ids": [_object_id_for_block(block_id)],
    }
    if field_id is not None:
        span["field_id"] = field_id
        span["slot_ref"] = f"{span_ref};field_id={field_id}"
    return span


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


def _split_slot_parts(
    text: str, *, field_id: str
) -> tuple[
    list[dict[str, str]],
    list[dict[str, object]],
]:
    colon_index = max(text.find("："), text.find(":"))
    if colon_index >= 0 and text[colon_index + 1 :].strip():
        label = text[: colon_index + 1]
        slot_text = text[colon_index + 1 :]
        parts = [
            _part("fixed_label", label),
            _part("fill_slot", slot_text, field_id=field_id),
        ]
        return parts, [
            _resolved_span("", 0, "fixed_label", text=label),
            _resolved_span("", 1, "fill_slot", field_id=field_id, text=slot_text),
        ]
    parts = [_part("fill_slot", text, field_id=field_id)]
    return parts, [_resolved_span("", 0, "fill_slot", field_id=field_id, text=text)]


def _slot_judgment(
    *,
    block_id: str,
    field_id: str = "author.name.zh",
    block_text: str | None = None,
) -> dict[str, object]:
    text = block_text if block_text is not None else "×××"
    parts, spans = _split_slot_parts(text, field_id=field_id)
    resolved_spans: list[dict[str, object]] = []
    for span in spans:
        part_index = span["part_index"]
        assert isinstance(part_index, int)
        role = span["role"]
        assert isinstance(role, str)
        span_field_id = span.get("field_id")
        resolved_spans.append(
            _resolved_span(
                block_id,
                part_index,
                role,
                field_id=span_field_id if isinstance(span_field_id, str) else None,
                text=str(span.get("text", "")),
            )
        )
    return _judgment(block_id, parts, resolved_spans=resolved_spans)


def _cleanup_judgment(block_id: str, text: str) -> dict[str, object]:
    return _judgment(block_id, [_part("cleanup", text)])


def _manual_region_judgment(
    *,
    range_id: str,
    block_id: str,
    text: str,
) -> dict[str, object]:
    return {
        "scope": {"reading_range_id": range_id},
        "parts": [_part("manual_region", text)],
        "resolved_spans": [
            _resolved_span(
                block_id,
                0,
                "manual_region",
                text=text,
                scope={"reading_range_id": range_id},
            )
        ],
    }


def _generated_content_judgment(
    *,
    range_id: str,
    block_id: str,
    text: str,
    field_id: str = "generated.toc",
) -> dict[str, object]:
    return {
        "scope": {"reading_range_id": range_id},
        "parts": [_part("generated_content", text, field_id=field_id)],
        "resolved_spans": [
            _resolved_span(
                block_id,
                0,
                "generated_content",
                field_id=field_id,
                text=text,
                scope={"reading_range_id": range_id},
            )
        ],
    }


def _body_structure_judgment(
    bindings: list[tuple[str, str, str]],
    *,
    range_id: str,
) -> dict[str, object]:
    return {
        "scope": {"reading_range_id": range_id},
        "parts": [
            _part("body_structure", text, field_id=field_id)
            for _block_id, text, field_id in bindings
        ],
        "resolved_spans": [
            _resolved_span(
                block_id,
                index,
                "body_structure",
                field_id=field_id,
                text=text,
                scope={"reading_range_id": range_id},
            )
            for index, (block_id, text, field_id) in enumerate(bindings)
        ],
    }


def _agent_body_structure_judgment(
    bindings: list[tuple[str, str, str]],
    *,
    range_id: str,
) -> dict[str, object]:
    return {
        "scope": {"reading_range_id": range_id},
        "parts": [
            _part("body_structure", text, field_id=field_id)
            for _block_id, text, field_id in bindings
        ],
    }


def _block_text_by_id(inventory: dict[str, object], block_id: str) -> str:
    raw_blocks = inventory.get("reading_blocks")
    assert isinstance(raw_blocks, list)
    for raw_block in raw_blocks:
        assert isinstance(raw_block, dict)
        if raw_block.get("block_id") == block_id:
            text = raw_block.get("text")
            assert isinstance(text, str)
            return text
    raise AssertionError(f"no reading block has id {block_id!r}")


def _block_ids(inventory: dict[str, object]) -> list[str]:
    raw_blocks = inventory.get("reading_blocks")
    assert isinstance(raw_blocks, list)
    return [
        str(raw_block["block_id"])
        for raw_block in raw_blocks
        if isinstance(raw_block, dict) and isinstance(raw_block.get("block_id"), str)
    ]


def _assign_range(
    inventory: dict[str, object],
    *,
    range_id: str,
    block_ids: list[str],
) -> None:
    wanted = set(block_ids)
    raw_blocks = inventory.get("reading_blocks")
    assert isinstance(raw_blocks, list)
    for raw_block in raw_blocks:
        assert isinstance(raw_block, dict)
        if raw_block.get("block_id") in wanted:
            raw_block["range_id"] = range_id


def _assign_unit_range(
    inventory: dict[str, object],
    *,
    unit_range_id: str,
    block_ids: list[str],
) -> None:
    wanted = set(block_ids)
    raw_blocks = inventory.get("reading_blocks")
    assert isinstance(raw_blocks, list)
    for raw_block in raw_blocks:
        assert isinstance(raw_block, dict)
        if raw_block.get("block_id") in wanted:
            raw_block["unit_range_id"] = unit_range_id


def _slice_inventory(
    inventory: dict[str, object],
    *,
    block_ids: list[str],
) -> dict[str, object]:
    # Scope the requested semantic work while retaining the complete initial inventory.
    # The fixture explicitly preserves every unselected source entry below.
    return {**inventory, "fixture_preserve_unselected": True}


def _slot_judgment_for_marker(
    *,
    inventory: dict[str, object],
    marker: str,
    field_id: str = "author.name.zh",
) -> dict[str, object]:
    block_id = _block_id_containing(inventory, marker)
    return _slot_judgment(
        block_id=block_id,
        field_id=field_id,
        block_text=_block_text_by_id(inventory, block_id),
    )


def _block_id_containing(
    inventory: dict[str, object],
    marker: str,
) -> str:
    raw_blocks = inventory.get("reading_blocks")
    assert isinstance(raw_blocks, list)
    for raw_block in raw_blocks:
        assert isinstance(raw_block, dict)
        block_id = raw_block.get("block_id")
        text = raw_block.get("text")
        if isinstance(block_id, str) and isinstance(text, str) and marker in text:
            return block_id
    raise AssertionError(f"no reading block contains marker {marker!r}")


def test_0820_cover_replay_materializes_hash_bound_slot(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=MINIMAL_UNITS / "01-cover/school-template.docx",
        unit_id="u-cover",
    )
    slot_block = _block_id_containing(inventory, "学生姓名")
    inventory = _slice_inventory(inventory, block_ids=[slot_block])
    _write_inventory(prepared, inventory)
    _write_accepted_review(
        prepared,
        [
            _slot_judgment_for_marker(
                inventory=inventory,
                marker="学生姓名",
            )
        ],
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)

    assert receipt["operation_count"] == 1
    slot_receipt = receipt["mutation_receipts"][0]
    assert slot_receipt["handler"] == "slots"
    assert slot_receipt["source_judgment_refs"] == ["semantic_judgments[11]"]
    assert slot_receipt["field_ids"] == ["author.name.zh"]


@pytest.mark.parametrize("whole_entry", [False, True], ids=["literal", "explicit-whole-entry"])
def test_single_value_declaration_materializes_without_copying_private_characters(
    tmp_path: Path, whole_entry: bool,
) -> None:
    # A constructed one-value DOCX checks mechanics, not school-semantic correctness.
    source_text = "\uf06f 学术学位    \uf0fe 专业学位"
    source = tmp_path / "single-value.docx"
    with zipfile.ZipFile(MINIMAL_UNITS / "01-cover/school-template.docx") as original:
        document = ET.fromstring(original.read("word/document.xml"))
        body = document.find(f"{W}body")
        assert body is not None
        for child in list(body):
            if child.tag != f"{W}sectPr":
                body.remove(child)
        paragraph = ET.Element(f"{W}p")
        ET.SubElement(ET.SubElement(paragraph, f"{W}r"), f"{W}t").text = source_text
        body.insert(0, paragraph)
        with zipfile.ZipFile(source, "w") as target:
            for member in original.infolist():
                target.writestr(member, ET.tostring(document, encoding="utf-8")
                                if member.filename == "word/document.xml"
                                else original.read(member.filename))
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path, source_docx=source, unit_id="single-value",
    )
    entry = inventory["source_entries"][0]
    part = {"role": "fill_slot", "field_id": "degree.type",
            **({"whole_entry": True} if whole_entry else {"text": source_text})}
    accepted = _accept_with_harness(prepared=prepared, inventory=inventory, judgments=[{
        "source_entry_id": entry["source_entry_id"], "parts": [part],
    }])
    assert accepted["status"] == "ok", accepted
    review_path = prepared.task_root / "work/.docfit/harness/semantic-judgments.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["semantic_judgments"][0]["parts"] == [{
        "text": source_text, "role": "fill_slot", "field_id": "degree.type",
    }]
    assert len(review["resolved_spans"]) == 1
    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)
    assert receipt["operation_count"] == 1
    assert receipt["mutation_receipts"][0]["field_ids"] == ["degree.type"]


def test_0820_body_replay_materializes_structure_and_alternate_cleanup(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=MINIMAL_UNITS / "04-paper-body/school-template.docx",
        unit_id="u-paper-body",
    )
    science_blocks = [f"u-paper-body:block-{index:04d}" for index in range(21, 30)]
    science_range = "u-paper-body:range-science"
    _assign_range(inventory, range_id=science_range, block_ids=science_blocks)
    humanities_blocks = [f"u-paper-body:block-{index:04d}" for index in range(31, 41)]
    inventory = _slice_inventory(inventory, block_ids=[*science_blocks, *humanities_blocks])
    _write_inventory(prepared, inventory)
    _write_accepted_review(
        prepared,
        [
            _body_structure_judgment(
                [
                    (
                        science_blocks[0],
                        _block_text_by_id(inventory, science_blocks[0]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[1],
                        _block_text_by_id(inventory, science_blocks[1]),
                        "body.paragraph",
                    ),
                    (
                        science_blocks[2],
                        _block_text_by_id(inventory, science_blocks[2]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[3],
                        _block_text_by_id(inventory, science_blocks[3]),
                        "body.heading.outline2",
                    ),
                    (
                        science_blocks[4],
                        _block_text_by_id(inventory, science_blocks[4]),
                        "body.heading.outline3",
                    ),
                    (
                        science_blocks[5],
                        _block_text_by_id(inventory, science_blocks[5]),
                        "body.numbered_list_item",
                    ),
                    (
                        science_blocks[6],
                        _block_text_by_id(inventory, science_blocks[6]),
                        "body.paragraph",
                    ),
                    (
                        science_blocks[7],
                        _block_text_by_id(inventory, science_blocks[7]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[8],
                        _block_text_by_id(inventory, science_blocks[8]),
                        "body.paragraph",
                    ),
                ],
                range_id=science_range,
            ),
            *[
                _cleanup_judgment(block_id, _block_text_by_id(inventory, block_id))
                for block_id in humanities_blocks
            ],
        ],
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)

    body_receipts = [
        item for item in receipt["mutation_receipts"] if item["handler"] == "body_structure"
    ]
    assert receipt["operation_count"] == 1
    assert len(body_receipts) == 1
    assert body_receipts[0]["action"] == "materialize_structure"
    assert body_receipts[0]["source_judgment_refs"] == [
        f"semantic_judgments[{index}]"
        for index, entry in enumerate(inventory["source_entries"])
        if entry["source_entry_id"]
        in {
            span["source_entry_id"]
            for span in json.loads(
                (prepared.task_root / "work/.docfit/harness/semantic-judgments.json").read_text()
            )["resolved_spans"]
            if span["role"] == "body_structure"
        }
    ]
    assert body_receipts[0]["field_ids"] == [
        "body.heading.outline1",
        "body.paragraph",
        "body.heading.outline2",
        "body.heading.outline3",
        "body.numbered_list_item",
    ]
    cleanup_receipts = [
        item for item in receipt["mutation_receipts"] if item["handler"] == "cleanup"
    ]
    assert len(cleanup_receipts) == 10


def test_0820_body_harness_range_replay_materializes_structure(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=MINIMAL_UNITS / "04-paper-body/school-template.docx",
        unit_id="u-paper-body",
    )
    science_blocks = [f"u-paper-body:block-{index:04d}" for index in range(21, 30)]
    science_range = "u-paper-body:range-science"
    _assign_range(inventory, range_id=science_range, block_ids=science_blocks)
    inventory = _slice_inventory(inventory, block_ids=science_blocks)
    _accept_with_harness(
        prepared=prepared,
        inventory=inventory,
        judgments=[
            _agent_body_structure_judgment(
                [
                    (
                        science_blocks[0],
                        _block_text_by_id(inventory, science_blocks[0]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[1],
                        _block_text_by_id(inventory, science_blocks[1]),
                        "body.paragraph",
                    ),
                    (
                        science_blocks[2],
                        _block_text_by_id(inventory, science_blocks[2]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[3],
                        _block_text_by_id(inventory, science_blocks[3]),
                        "body.heading.outline2",
                    ),
                    (
                        science_blocks[4],
                        _block_text_by_id(inventory, science_blocks[4]),
                        "body.heading.outline3",
                    ),
                    (
                        science_blocks[5],
                        _block_text_by_id(inventory, science_blocks[5]),
                        "body.numbered_list_item",
                    ),
                    (
                        science_blocks[6],
                        _block_text_by_id(inventory, science_blocks[6]),
                        "body.paragraph",
                    ),
                    (
                        science_blocks[7],
                        _block_text_by_id(inventory, science_blocks[7]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[8],
                        _block_text_by_id(inventory, science_blocks[8]),
                        "body.paragraph",
                    ),
                ],
                range_id=science_range,
            )
        ],
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)
    stored = json.loads(
        (prepared.task_root / "work/.docfit/harness/semantic-judgments.json").read_text(
            encoding="utf-8"
        )
    )

    assert receipt["operation_count"] == 1
    body_receipts = [
        item for item in receipt["mutation_receipts"] if item["handler"] == "body_structure"
    ]
    assert len(body_receipts) == 1
    assert "body.chapters" not in body_receipts[0]["field_ids"]
    assert body_receipts[0]["field_ids"][0] == "body.heading.outline1"
    stored_spans = [
        span for judgment in stored["semantic_judgments"] for span in judgment["resolved_spans"]
    ]
    assert len(stored_spans) == len(inventory["source_entries"])
    assert all(str(span["span_ref"]).startswith("source_entry_id=") for span in stored_spans)
    assert [span["source_entry_id"] for span in stored_spans] == [
        judgment["source_entry_id"] for judgment in stored["semantic_judgments"]
    ]
    assert "slot_id" not in json.dumps(receipt, ensure_ascii=False)


def test_0820_body_harness_unit_range_replay_materializes_structure(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=MINIMAL_UNITS / "04-paper-body/school-template.docx",
        unit_id="u-paper-body",
    )
    science_blocks = [f"u-paper-body:block-{index:04d}" for index in range(21, 30)]
    unit_range_id = "u-paper-body:range-whole-unit"
    _assign_unit_range(inventory, unit_range_id=unit_range_id, block_ids=science_blocks)
    inventory = _slice_inventory(inventory, block_ids=science_blocks)
    _accept_with_harness(
        prepared=prepared,
        inventory=inventory,
        judgments=[
            _agent_body_structure_judgment(
                [
                    (
                        science_blocks[0],
                        _block_text_by_id(inventory, science_blocks[0]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[1],
                        _block_text_by_id(inventory, science_blocks[1]),
                        "body.paragraph",
                    ),
                    (
                        science_blocks[2],
                        _block_text_by_id(inventory, science_blocks[2]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[3],
                        _block_text_by_id(inventory, science_blocks[3]),
                        "body.heading.outline2",
                    ),
                    (
                        science_blocks[4],
                        _block_text_by_id(inventory, science_blocks[4]),
                        "body.heading.outline3",
                    ),
                    (
                        science_blocks[5],
                        _block_text_by_id(inventory, science_blocks[5]),
                        "body.numbered_list_item",
                    ),
                    (
                        science_blocks[6],
                        _block_text_by_id(inventory, science_blocks[6]),
                        "body.paragraph",
                    ),
                    (
                        science_blocks[7],
                        _block_text_by_id(inventory, science_blocks[7]),
                        "body.heading.outline1",
                    ),
                    (
                        science_blocks[8],
                        _block_text_by_id(inventory, science_blocks[8]),
                        "body.paragraph",
                    ),
                ],
                range_id=unit_range_id,
            )
        ],
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)
    stored = json.loads(
        (prepared.task_root / "work/.docfit/harness/semantic-judgments.json").read_text(
            encoding="utf-8"
        )
    )

    body_receipts = [
        item for item in receipt["mutation_receipts"] if item["handler"] == "body_structure"
    ]
    assert len(body_receipts) == 1
    assert body_receipts[0]["scope_refs"] == [
        {"kind": "source_entry", "ref_id": judgment["source_entry_id"]}
        for judgment in stored["semantic_judgments"]
        if any(part.get("role") == "body_structure" for part in judgment["parts"])
    ]
    stored_spans = [
        span for judgment in stored["semantic_judgments"] for span in judgment["resolved_spans"]
    ]
    assert len(stored_spans) == len(inventory["source_entries"])
    assert all(str(span["span_ref"]).startswith("source_entry_id=") for span in stored_spans)


def test_0820_body_unit_range_materializes_structure_across_cleanup_gaps(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=MINIMAL_UNITS / "04-paper-body/school-template.docx",
        unit_id="u-paper-body",
    )
    science_blocks = [f"u-paper-body:block-{index:04d}" for index in range(21, 27)]
    unit_range_id = "u-paper-body:range-whole-unit"
    _assign_unit_range(inventory, unit_range_id=unit_range_id, block_ids=science_blocks)
    inventory = _slice_inventory(inventory, block_ids=science_blocks)
    parts = [
        _part(
            "body_structure",
            _block_text_by_id(inventory, science_blocks[0]),
            field_id="body.heading.outline1",
        ),
        _part("cleanup", _block_text_by_id(inventory, science_blocks[1])),
        _part("cleanup", _block_text_by_id(inventory, science_blocks[2])),
        _part("cleanup", _block_text_by_id(inventory, science_blocks[3])),
        _part(
            "body_structure",
            _block_text_by_id(inventory, science_blocks[4]),
            field_id="body.heading.outline3",
        ),
        _part(
            "body_structure",
            _block_text_by_id(inventory, science_blocks[5]),
            field_id="body.numbered_list_item",
        ),
    ]
    _accept_with_harness(
        prepared=prepared,
        inventory=inventory,
        judgments=[
            {
                "scope": {"reading_range_id": unit_range_id},
                "parts": parts,
            }
        ],
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)

    body_receipts = [
        item for item in receipt["mutation_receipts"] if item["handler"] == "body_structure"
    ]
    assert [item["action"] for item in body_receipts] == ["materialize_structure"]
    assert "body.chapters" not in body_receipts[0]["field_ids"]
    assert body_receipts[0]["field_ids"][0] == "body.heading.outline1"
    cleanup_receipts = [
        item for item in receipt["mutation_receipts"] if item["handler"] == "cleanup"
    ]
    assert len(cleanup_receipts) == 3
    assert all(item["span_refs"] for item in cleanup_receipts)


def test_njau_references_unit_range_slot_keeps_original_part_index(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=(
            THREE_SCHOOL_ASSETS / "02-njau-undergraduate/logical-pages/07-references.docx"
        ),
        unit_id="unit-references",
    )
    block_ids = [
        block_id
        for block_id in _block_ids(inventory)
        if _block_text_by_id(inventory, block_id).strip()
    ]
    assert len(block_ids) > 3
    unit_range_id = "unit-references:range-whole-unit"
    _assign_unit_range(inventory, unit_range_id=unit_range_id, block_ids=block_ids)
    inventory = _slice_inventory(inventory, block_ids=block_ids)
    parts: list[dict[str, str]] = []
    for index, block_id in enumerate(block_ids):
        text = _block_text_by_id(inventory, block_id)
        if index == 0:
            parts.append(_part("fixed_label", text))
        elif index == len(block_ids) - 1:
            parts.append(_part("fill_slot", text, field_id="references.entries"))
        else:
            parts.append(_part("cleanup", text))
    _accept_with_harness(
        prepared=prepared,
        inventory=inventory,
        judgments=[
            {
                "scope": {"reading_range_id": unit_range_id},
                "parts": parts,
            }
        ],
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)

    slot_receipts = [item for item in receipt["mutation_receipts"] if item["handler"] == "slots"]
    assert len(slot_receipts) == 1
    slot_receipt = slot_receipts[0]
    assert slot_receipt["operation"]["part_index"] == 0
    assert "semantic_part_index" not in slot_receipt["operation"]
    assert len(slot_receipt["slot_refs"]) == 1
    assert slot_receipt["slot_refs"][0].startswith("source_entry_id=")
    assert slot_receipt["slot_refs"][0].endswith(";field_id=references.entries")
    assert receipt["cleanup_count"] == len(block_ids) - 2


@pytest.mark.parametrize(
    ("school", "source_docx", "marker", "field_id"),
    [
        (
            "hunau",
            THREE_SCHOOL_ASSETS / "01-hunau-undergraduate/logical-pages/01-cover.docx",
            "学生姓名",
            "author.name.zh",
        ),
        (
            "njau",
            THREE_SCHOOL_ASSETS / "02-njau-undergraduate/logical-pages/04-abstract-cn.docx",
            "×××（400字左右",
            "abstract.zh",
        ),
        (
            "pku",
            THREE_SCHOOL_ASSETS / "03-pku-graduate/logical-pages/03-abstract-cn.docx",
            "关键词：",
            "keywords.zh",
        ),
    ],
    ids=["hunau", "njau", "pku"],
)
def test_three_school_post_unit_slot_replays_use_same_host_materialization_path(
    tmp_path: Path,
    school: str,
    source_docx: Path,
    marker: str,
    field_id: str,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=source_docx,
        unit_id=f"u-{school}-post-unit",
    )
    slot_block = _block_id_containing(inventory, marker)
    inventory = _slice_inventory(inventory, block_ids=[slot_block])
    _write_inventory(prepared, inventory)
    _write_accepted_review(
        prepared,
        [
            _slot_judgment_for_marker(
                inventory=inventory,
                marker=marker,
                field_id=field_id,
            )
        ],
    )

    candidate = _select_host_candidate_for_accepted_semantics(prepared)
    receipt = _assert_hash_bound_candidate(prepared, candidate)

    assert receipt["operation_count"] == 1
    assert receipt["mutation_receipts"][0]["handler"] == "slots"
    assert receipt["mutation_receipts"][0]["field_ids"] == [field_id]


@pytest.mark.parametrize(
    ("school", "source_docx"),
    [
        (
            "hunau",
            THREE_SCHOOL_ASSETS / "01-hunau-undergraduate/logical-pages/01-cover.docx",
        ),
        (
            "njau",
            THREE_SCHOOL_ASSETS / "02-njau-undergraduate/logical-pages/04-abstract-cn.docx",
        ),
        (
            "pku",
            THREE_SCHOOL_ASSETS / "03-pku-graduate/logical-pages/03-abstract-cn.docx",
        ),
    ],
    ids=["hunau", "njau", "pku"],
)
def test_three_school_current_inspect_packets_carry_vocabulary_without_internal_refs(
    tmp_path: Path,
    school: str,
    source_docx: Path,
) -> None:
    task_root = tmp_path / f"{school}-inspect-packet"
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True)
    template = input_dir / "school-template.docx"
    registry = input_dir / "field-registry.yaml"
    shutil.copyfile(source_docx, template)
    shutil.copyfile(REGISTRY, registry)
    service = DocFitToolService(task_root=task_root)
    inspection = service.inspect(
        {"input_docx": "input/school-template.docx", "include_objects": True}
    )
    objects = [item for item in inspection.get("objects", []) if isinstance(item, dict)]
    locators = [
        locator
        for item in objects
        if isinstance(locator := item.get("locator"), str) and locator.strip()
    ]
    assert locators
    vocabulary = FieldRegistrySnapshot.load(registry).pre_input_vocabulary()

    packet = build_unit_reading_packet(
        unit={"unit_id": f"u-{school}", "unit_name": school},
        scoped_objects=objects,
        field_id_vocabulary=vocabulary,
    )
    visible = agent_visible_unit_reading_packet(packet)
    visible_text = json.dumps(visible, ensure_ascii=False)

    assert packet["field_id_vocabulary"] == vocabulary
    assert packet["field_vocabulary_digest"] == vocabulary["digest"]
    assert packet["reading_blocks"]
    assert visible["field_id_vocabulary"] == vocabulary
    assert visible["reading_blocks"]
    assert all(
        isinstance(block.get("block_id"), str)
        and isinstance(block.get("range_id"), str)
        and isinstance(block.get("text"), str)
        for block in visible["reading_blocks"]
        if isinstance(block, dict)
    )
    for token in (
        "span_id",
        "span_ref",
        "slot_ref",
        "object_id",
        "object_ref",
        "covered_object_ids",
        "object_text_spans",
        "fingerprint",
        "locator",
    ):
        assert token not in visible_text


def test_0820_proposal_manual_table_conflict_rejects_accepted_review(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=MINIMAL_UNITS / "06-proposal/school-template.docx",
        unit_id="u-proposal",
    )
    proposal_range = "u-proposal:range-manual-form"
    proposal_blocks = _block_ids(inventory)
    _assign_range(inventory, range_id=proposal_range, block_ids=proposal_blocks)
    manual_block = proposal_blocks[0]
    _write_inventory(prepared, inventory)
    with pytest.raises(SourceSpanResolutionError):
        _write_accepted_review(
            prepared,
            [
                _manual_region_judgment(
                    range_id=proposal_range,
                    block_id=manual_block,
                    text=_block_text_by_id(inventory, manual_block),
                ),
                _slot_judgment(
                    block_id=_block_id_containing(inventory, "开题报告"),
                    block_text=_block_text_by_id(
                        inventory,
                        _block_id_containing(inventory, "开题报告"),
                    ),
                ),
            ],
        )
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
    ).exists()
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


def test_0820_toc_generated_content_conflict_rejects_accepted_review(
    tmp_path: Path,
) -> None:
    prepared, inventory = _task_from_docx(
        tmp_path=tmp_path,
        source_docx=MINIMAL_UNITS / "03-toc/school-template.docx",
        unit_id="u-toc",
    )
    toc_range = "u-toc:range-generated-content"
    toc_blocks = _block_ids(inventory)
    _assign_range(inventory, range_id=toc_range, block_ids=toc_blocks)
    generated_block = toc_blocks[0]
    slot_block = _block_id_containing(inventory, "摘要")
    _write_inventory(prepared, inventory)
    with pytest.raises(SourceSpanResolutionError):
        _write_accepted_review(
            prepared,
            [
                _generated_content_judgment(
                    range_id=toc_range,
                    block_id=generated_block,
                    text=_block_text_by_id(inventory, generated_block),
                ),
                _slot_judgment(
                    block_id=slot_block,
                    field_id="thesis.title.zh",
                    block_text=_block_text_by_id(inventory, slot_block),
                ),
            ],
        )
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/materialization.json"
    ).exists()
    assert not (
        prepared.task_root / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    ).exists()


THREE_SCHOOL_LOGICAL_PAGES = tuple(sorted(
    path for path in THREE_SCHOOL_ASSETS.glob("*/logical-pages/*.docx")
    if not path.name.startswith("~$")
))


def test_three_school_inventory_replay_manifest_has_all_logical_pages() -> None:
    assert {
        path.parents[1].name: sum(
            candidate.parents[1].name == path.parents[1].name
            for candidate in THREE_SCHOOL_LOGICAL_PAGES
        )
        for path in THREE_SCHOOL_LOGICAL_PAGES
    } == {
        "01-hunau-undergraduate": 10,
        "02-njau-undergraduate": 10,
        "03-pku-graduate": 12,
    }


@pytest.mark.parametrize(
    "source_docx",
    THREE_SCHOOL_LOGICAL_PAGES,
    ids=lambda path: f"{path.parents[1].name}-{path.stem}",
)
def test_three_school_canonical_inventory_is_stable_across_projection_and_retry(
    source_docx: Path,
) -> None:
    source_hash = sha256_file(source_docx)
    inspection = DocFitToolService(task_root=source_docx.parent).inspect(
        {
            "input_docx": str(source_docx),
            "focus": ["structure", "styles", "visible_objects"],
            "include_objects": True,
        }
    )
    inspected_objects = [item for item in inspection.get("objects", []) if isinstance(item, dict)]
    assert inspected_objects
    assert all("source_entry_id" not in item for item in inspected_objects)

    inventory = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=inspected_objects,
    )
    retry = CanonicalSourceInventory.from_json(inventory.to_json())
    object_ids = [str(item["object_id"]) for item in inspected_objects]
    midpoint = max(1, len(object_ids) // 2)
    later_window = object_ids[midpoint:]
    earlier_window = object_ids[:midpoint]

    later_first = select_source_entries_for_objects(inventory, later_window)
    earlier_second = select_source_entries_for_objects(inventory, earlier_window)
    earlier_first = select_source_entries_for_objects(retry, earlier_window)
    later_second = select_source_entries_for_objects(retry, later_window)

    assert inventory.source_snapshot_sha256 == source_hash
    assert retry.inventory_digest == inventory.inventory_digest
    assert [entry.to_json() for entry in earlier_first] == [
        entry.to_json() for entry in earlier_second
    ]
    assert [entry.to_json() for entry in later_first] == [entry.to_json() for entry in later_second]
    assert {
        provenance.object_id
        for entry in inventory.source_entries
        for provenance in entry.provenance
    } == set(object_ids)
    assert all(
        entry.source_entry_id == retry_entry.source_entry_id
        and entry.text == retry_entry.text
        and entry.provenance == retry_entry.provenance
        for entry, retry_entry in zip(
            inventory.source_entries,
            retry.source_entries,
            strict=True,
        )
    )


@pytest.mark.parametrize(
    "source_docx",
    (
        THREE_SCHOOL_ASSETS / "01-hunau-undergraduate/logical-pages/01-cover.docx",
        THREE_SCHOOL_ASSETS / "02-njau-undergraduate/logical-pages/04-abstract-cn.docx",
        THREE_SCHOOL_ASSETS / "03-pku-graduate/logical-pages/08-body.docx",
    ),
    ids=("hunau-app-tool", "njau-app-tool", "pku-app-tool"),
)
def test_three_school_app_harness_tool_reuse_one_persisted_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_docx: Path,
) -> None:
    task_root = tmp_path / source_docx.stem
    input_dir = task_root / "input"
    input_dir.mkdir(parents=True)
    template = input_dir / "school-template.docx"
    registry = input_dir / "field-registry.yaml"
    shutil.copyfile(source_docx, template)
    shutil.copyfile(REGISTRY, registry)
    source_hash = sha256_file(template)
    real_inspection = DocFitToolService(task_root=task_root).inspect(
        {
            "input_docx": str(template),
            "focus": ["structure", "styles", "visible_objects"],
            "include_objects": True,
        }
    )
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash, inspected_objects=real_inspection["objects"]
    )
    inventory = {"document_sha256": source_hash, "canonical_source_inventory": canonical.to_json()}
    checkpoint = source_partition(inventory, unit_id="u-real", unit_name=source_docx.stem)
    persist_source_identity(task_root, inventory, objects=real_inspection["objects"])
    prepared = PreparedTemplateTask(
        task_root=task_root,
        template_path=template,
        requirements_path=None,
        registry_source=registry,
        template_sha256=source_hash,
        requirements_sha256=None,
        registry_sha256=sha256_file(registry),
    )
    inspect_calls = 0

    def replay_inspection(_service: object, _args: dict[str, object]) -> dict[str, object]:
        nonlocal inspect_calls
        inspect_calls += 1
        return real_inspection

    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.inspect",
        replay_inspection,
    )

    first_inventory = _ensure_post_unit_inventory(prepared, checkpoint)
    retry_inventory = _ensure_post_unit_inventory(prepared, checkpoint)
    service = DocFitToolService(task_root=task_root)
    first_packet = service.evidence(
        {"focus": "unit_evidence_packet", "unit_id": "u-real", "limit": 7}
    )
    retry_packet = service.evidence(
        {"focus": "unit_evidence_packet", "unit_id": "u-real", "limit": 7}
    )

    assert inspect_calls == 0
    assert (
        first_inventory["canonical_source_inventory"]
        == retry_inventory["canonical_source_inventory"]
    )
    assert first_packet["evidence"] == retry_packet["evidence"]
    assert (
        first_packet["summary"]["field_vocabulary_digest"]
        == (first_inventory["field_vocabulary_digest"])
    )
    assert (
        json.loads(
            (task_root / "work/.docfit/initial-source-inventory.json").read_text(encoding="utf-8")
        )["canonical_source_inventory"]
        == first_inventory["canonical_source_inventory"]
    )

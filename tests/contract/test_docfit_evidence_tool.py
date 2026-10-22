from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from docfit.fields import FieldRegistrySnapshot
from docfit.template.reading_packet import build_unit_reading_packet
from docfit.template.source_entries import (
    build_canonical_source_inventory,
    project_source_entries_onto_objects,
)
from docfit.template.source_order import order_initial_source_objects
from docfit.template.source_word_format import source_word_format_facts
from docfit.template.unit_source import entry_unit_contexts
from docfit.tools import docfit_evidence
from docfit.tools.runtime import ToolFailure, sha256_file
from docfit.tools.service import DocFitToolService, tool_result
from docfit.tools.surface import (
    DOCFIT_EVIDENCE_SCHEMA,
    DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA,
    EVIDENCE_FOCUS,
    TEMPLATE_SEMANTIC_EVIDENCE_FOCUS,
)
from tests.contract.test_template_materialization_runtime import _write_docx_from_paragraph_xml
from tests.support.source_identity import persist_source_identity, source_partition


def _task_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    _write_docx_from_paragraph_xml(source, ["<w:p/>"])
    _persist_unit_packet(
        root,
        sha256_file(source),
        _fake_inspection(sha256_file(source), "document_map")["objects"],
        include_vocabulary=False,
    )
    return root, sha256_file(source)


def _write_unit_checkpoint(
    root: Path,
    source_hash: str,
) -> None:
    inventory = json.loads((root / "work/.docfit/harness/object-inventory.json").read_text())
    source_partition(inventory)
    persist_source_identity(root, inventory)


def _write_raw_unit_checkpoint(root: Path, checkpoint: dict[str, object]) -> None:
    path = root / "work/.docfit/unit-boundary-checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint), encoding="utf-8")


def _write_registry(root: Path) -> None:
    (root / "input/field-registry.json").write_text(
        json.dumps(
            {
                "registry_id": "docfit.test.fields",
                "registry_version": "0.1.0",
                "fields": [
                    {
                        "field_id": "author.name.zh",
                        "label": "作者中文姓名",
                        "meaning": "学生姓名",
                        "content_type": "text",
                    },
                    {
                        "field_id": "thesis.title.zh",
                        "label": "中文论文题目",
                        "meaning": "论文题目",
                        "content_type": "text",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _persist_unit_packet(
    root: Path,
    source_hash: str,
    objects: list[dict[str, object]],
    *,
    include_vocabulary: bool = True,
) -> None:
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=objects,
    )
    vocabulary = (
        FieldRegistrySnapshot.load(root / "input/field-registry.json").pre_input_vocabulary()
        if include_vocabulary
        else None
    )
    inventory = {
        "schema_version": 2,
        "document_sha256": source_hash,
        "canonical_source_inventory": canonical.to_json(),
        "source_entries": [entry.to_json() for entry in canonical.source_entries],
    }
    proof = source_partition(inventory)
    facts = source_word_format_facts(root / "input/school-template.docx", canonical)
    inventory["unit_reading_packets"] = {}
    for scope in proof["resolved_units"]:
        ids = {span["source_entry_id"] for span in scope["source_spans"]}
        scoped_entries = tuple(
            entry for entry in canonical.source_entries if entry.source_entry_id in ids
        )
        object_ids = {item.object_id for entry in scoped_entries for item in entry.provenance}
        scoped_objects = [item for item in objects
                          if item.get("object_ref", {}).get("object_id") in object_ids]
        projected = project_source_entries_onto_objects(
            scoped_objects, scoped_entries, source_sha256=source_hash,
        )
        packet = build_unit_reading_packet(
            unit=scope,
            scoped_objects=projected,
            source_entries=scoped_entries,
            field_id_vocabulary=vocabulary,
            layout_facts={},
            structure_context={},
            word_format_facts=facts,
        )
        for entry in packet["source_entries"]:
            entry["unit_contexts"] = entry_unit_contexts(
                proof["resolved_units"], entry["source_entry_id"]
            )
        inventory["unit_reading_packets"][scope["unit_id"]] = packet
    persist_source_identity(root, inventory, objects=objects)
    path = root / "work/.docfit/harness/object-inventory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory), encoding="utf-8")


def _resolved_checkpoint_units(root: Path) -> list[dict[str, object]]:
    checkpoint = json.loads(
        (root / "work/.docfit/unit-boundary-checkpoint.json").read_text(encoding="utf-8")
    )
    units = checkpoint.get("resolved_units")
    assert isinstance(units, list)
    return [dict(unit) for unit in units if isinstance(unit, dict)]


def _real_task_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "real-task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    (root / "work").mkdir(parents=True)
    (root / "output").mkdir()
    shutil.copyfile(
        Path(__file__).resolve().parents[2] / "evals/fixtures/smoke/school-template.docx",
        source,
    )
    return root, sha256_file(source)


def test_unit_packet_shows_pixels_from_real_school_picture_entries(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "tests/manual-diagnostics/input/school-template-nannong-undergraduate.docx"
    )
    root = tmp_path / "real-school-task"
    task_source = root / "input/school-template.docx"
    task_source.parent.mkdir(parents=True)
    shutil.copyfile(source, task_source)
    _write_registry(root)
    service = DocFitToolService(task_root=root)
    inspection = service.inspect(
        {
            "input_docx": str(task_source),
            "focus": ["structure", "visible_objects"],
            "include_objects": True,
        }
    )
    ordered = order_initial_source_objects(
        task_source,
        source_sha256=sha256_file(task_source),
        objects=inspection["objects"],
    )
    _persist_unit_packet(root, sha256_file(task_source), ordered)
    packet = json.loads((root / "work/.docfit/harness/object-inventory.json").read_text())[
        "unit_reading_packets"
    ]["u-all"]
    picture_positions = [
        index
        for index, entry in enumerate(packet["source_entries"])
        if entry.get("entry_type") == "picture"
    ]
    assert picture_positions == [2, 4]
    assert [packet["source_entries"][index]["source_entry_id"] for index in picture_positions] == [
        "source-entry-05686695b50646cfb45c11ee",
        "source-entry-be9bd13e6f9a0ffeb8dde62e",
    ]

    result = service.evidence(
        {
            "focus": "unit_evidence_packet",
            "unit_id": "u-all",
            "offset": picture_positions[0],
            "limit": picture_positions[-1] - picture_positions[0] + 1,
        }
    )
    content = tool_result(result, image_paths=service._last_evidence_image_paths)["content"]
    bindings = result["summary"]["picture_evidence"]
    assert [binding["source_entry_id"] for binding in bindings] == [
        packet["source_entries"][position]["source_entry_id"]
        for position in picture_positions
    ]
    assert [binding["content_block_index"] for binding in bindings] == [1, 2]
    assert [block["type"] for block in content] == ["text", "image", "image"]
    assert "locator" not in json.dumps(result)
    first_window = service.evidence(
        {"focus": "unit_evidence_packet", "unit_id": "u-all", "offset": 0, "limit": 1}
    )
    assert len(first_window["evidence"]) == 1
    assert first_window["summary"]["picture_evidence"] == bindings
    assert len(service._last_evidence_image_paths) == 2
    with zipfile.ZipFile(task_source) as archive:
        for block, media in zip(
            content[1:], ("word/media/image1.jpeg", "word/media/image2.png"), strict=True
        ):
            with (
                Image.open(io.BytesIO(base64.b64decode(block["data"]))) as shown,
                Image.open(io.BytesIO(archive.read(media))) as original,
            ):
                assert shown.size == original.size
                assert ImageChops.difference(
                    shown.convert("RGB"), original.convert("RGB")
                ).getbbox() is None


def test_unit_packet_keeps_real_pku_formula_figure_with_its_caption(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "fixtures/template_extraction/pku-graduate-real-source.docx"
    )
    with zipfile.ZipFile(source) as original_package:
        assert hashlib.sha256(original_package.read("word/document.xml")).hexdigest() == (
            "e2a36fa6c034912585c909f7142e72615297c2c6c40eccd4ae1375a826d453c0"
        )
    root = tmp_path / "pku-picture-task"
    task_source = root / "input/school-template.docx"
    task_source.parent.mkdir(parents=True)
    shutil.copyfile(source, task_source)
    _write_registry(root)
    service = DocFitToolService(task_root=root)
    inspection = service.inspect(
        {
            "input_docx": str(task_source),
            "focus": ["structure", "visible_objects"],
            "include_objects": True,
        }
    )
    ordered = order_initial_source_objects(
        task_source,
        source_sha256=sha256_file(task_source),
        objects=inspection["objects"],
    )
    _persist_unit_packet(root, sha256_file(task_source), ordered)
    packet = json.loads((root / "work/.docfit/harness/object-inventory.json").read_text())[
        "unit_reading_packets"
    ]["u-all"]
    entries = packet["source_entries"]
    caption_position = next(
        index
        for index, entry in enumerate(entries)
        if entry.get("text") == "图 2.3\t复制公式时应选择的范围"
    )
    picture = entries[caption_position - 1]
    assert picture["entry_type"] == "picture"
    assert "建议直接复制文档内现有公式" in entries[caption_position - 3]["text"]

    result = service.evidence(
        {
            "focus": "unit_evidence_packet",
            "unit_id": "u-all",
            "offset": caption_position - 3,
            "limit": 5,
        }
    )
    assert [entry["source_entry_id"] for entry in result["evidence"]] == [
        entry["source_entry_id"] for entry in entries[caption_position - 3 : caption_position + 2]
    ]
    bindings = result["summary"]["picture_evidence"]
    assert len(bindings) == 15
    target_binding = next(
        binding for binding in bindings if binding["source_entry_id"] == picture["source_entry_id"]
    )
    content = tool_result(result, image_paths=service._last_evidence_image_paths)["content"]
    assert content[target_binding["content_block_index"]]["type"] == "image"
    with Image.open(
        io.BytesIO(base64.b64decode(content[target_binding["content_block_index"]]["data"]))
    ) as shown:
        shown_rgba = shown.convert("RGBA")
        with zipfile.ZipFile(task_source) as archive:
            matching_media = []
            for name in archive.namelist():
                if not name.startswith("word/media/"):
                    continue
                with Image.open(io.BytesIO(archive.read(name))) as original:
                    if original.size == shown_rgba.size and ImageChops.difference(
                        shown_rgba, original.convert("RGBA")
                    ).getbbox() is None:
                        matching_media.append(name)
    assert matching_media
    assert "locator" not in json.dumps(result)

    first_text_window = service.evidence(
        {"focus": "unit_evidence_packet", "unit_id": "u-all", "offset": 0, "limit": 1}
    )
    assert first_text_window["summary"]["picture_evidence"] == bindings
    assert len(service._last_evidence_image_paths) == 15


def test_real_pku_word_story_heading_and_list_facts_reach_both_agent_views(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "fixtures/template_extraction/pku-graduate-real-source.docx"
    )
    root = tmp_path / "pku-word-format-task"
    task_source = root / "input/school-template.docx"
    task_source.parent.mkdir(parents=True)
    shutil.copyfile(source, task_source)
    _write_registry(root)
    service = DocFitToolService(task_root=root)
    objects = service.inspect({
        "input_docx": str(task_source), "focus": ["structure", "visible_objects"],
        "include_objects": True,
    })["objects"]
    ordered = order_initial_source_objects(
        task_source, source_sha256=sha256_file(task_source), objects=objects
    )
    _persist_unit_packet(root, sha256_file(task_source), ordered)
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text())
    packets = inventory["unit_reading_packets"]
    expected = {
        "第三章\t其他注意事项": (
            "auxiliary-header", {"story": "header", "paragraph_style": "header"},
        ),
        "研究背景": ("u-all", {
            "story": "body", "paragraph_style": "heading 1", "outline_level": 1,
            "list_level": 1, "numbering_format": "chineseCountingThousand",
        }),
        "另一个数字编号": ("u-all", {
            "story": "body", "paragraph_style": "PKU列表正文",
            "list_level": 1, "numbering_format": "decimal",
        }),
    }
    global_rows = inventory["source_entries"]
    for text, (unit_id, word_format) in expected.items():
        unit_rows = packets[unit_id]["source_entries"]
        row = next(row for row in unit_rows if row["text"] == text)
        for focus, index, kwargs in (
            ("document_map", next(i for i, item in enumerate(global_rows)
                                   if item["source_entry_id"] == row["source_entry_id"]), {}),
            ("unit_evidence_packet", unit_rows.index(row), {"unit_id": unit_id}),
        ):
            card = service.evidence({"focus": focus, "offset": index, "limit": 1, **kwargs})
            assert card["evidence"][0]["source_entry_id"] == row["source_entry_id"]
            assert card["evidence"][0]["word_format"] == word_format
            assert all(key not in json.dumps(card["evidence"]) for key in (
                "locator", "object_ref", "fingerprint", "numId",
            ))

    packets["u-all"].pop("word_format_evidence_version")
    inventory_path.write_text(json.dumps(inventory))
    with pytest.raises(ToolFailure) as error:
        service.evidence({"focus": "unit_evidence_packet", "unit_id": "u-all"})
    assert error.value.code == "source_word_format_evidence_missing"


def _write_action_package(root: Path, relative: str, operation: dict[str, object]) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"operations": [operation]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return relative


def _fake_inspection(source_hash: str, focus: str) -> dict[str, object]:
    return {
        "status": "ok",
        "document": {"sha256": source_hash, "paragraph_count": 1},
        "objects": [
            {
                "object_id": "obj-000000000000000000000001",
                "type": "paragraph",
                "locator": "/body/p[1]",
                "focus": focus,
            }
        ],
        "object_count": 1,
        "object_window": {"returned": 1, "total": 1, "has_more": False},
        "risks": [{"code": "fake-risk"}],
        "failure": None,
    }


def _assert_unit_evidence_packet_hides_internal_refs(result: dict[str, object]) -> None:
    encoded = json.dumps(result, ensure_ascii=False)
    for token in (
        "unit_boundary_checkpoint",
        "scope_ref",
        "start_locator",
        "end_locator",
        "locator",
        "reading_block_mappings",
        "covered_object_ids",
        "covered_object_count",
        "coverage_required",
        "coverage_contract",
        "harness_maps_to",
        "object_id",
        "object_ref",
        "target_ref",
        "expected_fingerprint",
        "fingerprint",
        "source_entry_ref",
        "provenance",
        "span_ref",
    ):
        assert token not in encoded


@pytest.mark.parametrize("focus", EVIDENCE_FOCUS)
def test_t1_docfit_evidence_returns_short_hash_bound_cards_for_each_focus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    focus: str,
) -> None:
    root, source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: _fake_inspection(source_hash, focus),
    )
    monkeypatch.setattr(
        service,
        "render",
        lambda _args: (
            {"status": "ok", "render_ref": "render:v2:" + "b" * 64},
            [],
        ),
    )
    monkeypatch.setattr(
        service,
        "visual_review",
        lambda _args: ({"status": "ok", "reviewed_pages": [1]}, []),
    )
    if focus == "visual_page":
        monkeypatch.setattr(
            "docfit.tools.service.inspect_document_snapshot",
            lambda *_args, **_kwargs: "inspection",
        )

        class FakeVisual:
            def objects_on_page(
                self,
                _render_ref: str,
                _inspection: object,
                _page: int,
                *,
                limit: int,
            ):
                assert limit >= 1
                return [], False

        monkeypatch.setattr(service, "visual", lambda: FakeVisual())
    if focus == "unit_evidence_packet":
        _write_unit_checkpoint(root, source_hash)
        _write_registry(root)
        _persist_unit_packet(
            root,
            source_hash,
            [
                {
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "",
                    "object_ref": {"object_id": "obj-000000000000000000000001"},
                }
            ],
        )
    before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

    args = {
        "focus": focus,
        "render_ref": "render:v2:" + "b" * 64,
        "page": 1,
    }
    if focus == "unit_evidence_packet":
        args["unit_id"] = "u-all"

    result = service.evidence(args)

    after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
    assert after == before
    assert result["schema_version"] == "docfit_evidence_card_v1"
    assert result["status"] == "ok"
    assert result["source_hash"] == source_hash
    assert result["focus"] == focus
    assert result["refs"]
    assert result["summary"]
    assert "risks" in result
    assert result["untrusted"] == {
        "marker": "untrusted_docx_source_data",
        "instruction_authority": False,
        "configuration_authority": False,
    }


def test_t1_style_evidence_does_not_bind_registry_or_create_style_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: _fake_inspection(source_hash, "style_evidence"),
    )

    result = service.evidence({"focus": "style_evidence"})

    assert "style_contract_ref" not in result
    assert "registry_field" not in result
    assert result["focus"] == "style_evidence"


def test_t1_evidence_rejects_retired_source_hash_argument(tmp_path: Path) -> None:
    root, source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"source_hash": source_hash, "focus": "document_map"})

    error = caught.value
    assert error.code == "schema_envelope_invalid"
    assert "source_hash" in error.message
    assert error.retryable is True


def test_t1_registry_field_focus_is_not_agent_visible(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    _write_registry(root)
    service = DocFitToolService(task_root=root)

    assert "registry_field" not in EVIDENCE_FOCUS
    assert "registry_field" not in TEMPLATE_SEMANTIC_EVIDENCE_FOCUS
    assert "field_id" not in DOCFIT_EVIDENCE_SCHEMA["properties"]
    assert "semantic_field" not in DOCFIT_EVIDENCE_SCHEMA["properties"]
    assert "field_id" not in DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA["properties"]
    assert "semantic_field" not in DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA["properties"]

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"focus": "registry_field"})

    error = caught.value
    assert error.code == "registry_field_runtime_removed"
    assert "field_id_vocabulary" in error.message


def test_t1_registry_field_semantic_search_is_removed(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    _write_registry(root)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"focus": "registry_field", "semantic_field": "签名 日期"})

    error = caught.value
    assert error.code == "registry_field_runtime_removed"
    assert "field_id_vocabulary.allowed_field_ids" in " ".join(error.suggested_actions)


def test_t1_registry_field_exact_lookup_is_removed(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    _write_registry(root)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"focus": "registry_field", "field_id": "author.name.zh"})

    assert caught.value.code == "registry_field_runtime_removed"


def test_unit_evidence_packet_exposes_pre_input_field_vocabulary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_registry(root)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash},
            "objects": [
                {
                    "object_id": "obj-000000000000000000000001",
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "论文题目",
                    "object_ref": {"object_id": "obj-000000000000000000000001"},
                }
            ],
            "object_count": 1,
            "risks": [],
            "failure": None,
        },
    )
    _persist_unit_packet(
        root,
        source_hash,
        [
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "论文题目",
                "object_ref": {"object_id": "obj-000000000000000000000001"},
            }
        ],
    )

    result = service.evidence(
        {
            "focus": "unit_evidence_packet",
            "unit_id": "u-all",
        }
    )

    vocabulary = result["summary"]["field_id_vocabulary"]
    assert vocabulary["schema_version"] == "docfit_pre_input_field_vocabulary_v1"
    assert vocabulary["registry"]["sha256"] == sha256_file(root / "input/field-registry.json")
    assert vocabulary["allowed_field_ids"] == ["author.name.zh", "thesis.title.zh"]
    assert result["summary"]["field_vocabulary_digest"] == vocabulary["digest"]
    assert result["evidence"][0]["source_entry_id"].startswith("source-entry-")
    assert result["evidence"][0]["text"] == "论文题目"
    _assert_unit_evidence_packet_hides_internal_refs(result)


def test_unit_evidence_packet_requires_pre_input_field_vocabulary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash},
            "objects": [
                {
                    "object_id": "obj-000000000000000000000001",
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "论文题目",
                    "object_ref": {"object_id": "obj-000000000000000000000001"},
                }
            ],
            "object_count": 1,
            "risks": [],
            "failure": None,
        },
    )
    _persist_unit_packet(
        root,
        source_hash,
        [
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "论文题目",
                "object_ref": {"object_id": "obj-000000000000000000000001"},
            }
        ],
        include_vocabulary=False,
    )

    with pytest.raises(ToolFailure) as failure:
        service.evidence(
            {
                "focus": "unit_evidence_packet",
                "unit_id": "u-all",
            }
        )

    assert failure.value.code == "field_registry_missing"
    assert "field_id_vocabulary" in failure.value.message


def test_t1_evidence_defaults_source_hash_from_bound_task_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: _fake_inspection(source_hash, "document_map"),
    )

    result = service.evidence({"focus": "document_map"})

    assert result["status"] == "ok"
    assert result["source_hash"] == source_hash
    assert result["focus"] == "document_map"


def test_t1_registry_field_runtime_lookup_is_removed(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    _write_registry(root)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as error:
        service.evidence(
            {
                "focus": "registry_field",
                "semantic_field": "title",
            }
        )

    assert error.value.code == "registry_field_runtime_removed"


def test_t1_unit_slice_focus_is_retired_fail_closed(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"focus": "unit_slice"})

    error = caught.value
    assert error.code == "unit_slice_runtime_removed"
    assert "unit_evidence_packet" in error.message
    assert all("scope_ref" not in action for action in error.suggested_actions)


def test_t1_unit_evidence_packet_resolves_checkpoint_unit_to_current_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_registry(root)
    service = DocFitToolService(task_root=root)

    inspection_payload = {
        "status": "ok",
        "document": {"sha256": source_hash, "paragraph_count": 3},
        "objects": [
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "cover",
                "object_ref": {
                    "document_sha256": source_hash,
                    "object_id": "obj-cover",
                    "expected_fingerprint": "a" * 64,
                },
            },
            {
                "type": "paragraph",
                "locator": "/body/p[2]",
                "text": "outside",
                "object_ref": {
                    "document_sha256": source_hash,
                    "object_id": "obj-outside",
                    "expected_fingerprint": "b" * 64,
                },
            },
        ],
        "object_count": 2,
        "object_window": {"returned": 2, "total": 2, "has_more": False},
        "risks": [],
        "failure": None,
    }
    monkeypatch.setattr(service, "inspect", lambda _args: inspection_payload)
    _persist_unit_packet(root, source_hash, inspection_payload["objects"][:1])

    result = service.evidence(
        {
            "focus": "unit_evidence_packet",
            "unit_id": "u-all",
        }
    )

    assert result["focus"] == "unit_evidence_packet"
    assert "unit_boundary_checkpoint" not in result["refs"]
    assert "scope_ref" not in result["refs"]
    assert result["summary"]["unit"]["unit_id"] == "u-all"
    assert result["summary"]["evidence_shape"] == "agent_source_entries_v1"
    assert result["summary"]["view_shape"] == "agent_reading_blocks_v1"
    assert result["summary"]["source_entry_count"] == 1
    assert result["summary"]["source_entry_window"]["total"] == 1
    assert "object_window" not in result["summary"]
    assert "object_count" not in result["summary"]
    assert "scoped_object_count" not in result["summary"]
    assert "coverage_contract" not in result["summary"]
    assert result["summary"]["reading_ranges"] == [
        {
            "range_id": "u-all:range-whole-unit",
            "kind": "whole_unit",
            "unit_id": "u-all",
            "block_count": 1,
            "block_ids": ["u-all:block-0001"],
        }
    ]
    assert [item["text"] for item in result["evidence"]] == ["cover"]
    assert result["evidence"][0]["source_entry_id"].startswith("source-entry-")
    assert "coverage_required" not in result["evidence"][0]
    assert "covered_object_count" not in result["evidence"][0]
    _assert_unit_evidence_packet_hides_internal_refs(result)


def test_unit_packet_reads_persisted_canonical_inventory_without_renormalizing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_registry(root)
    raw_objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "  姓名\t张三  ",
            "object_ref": {
                "document_sha256": source_hash,
                "object_id": "obj-cover",
                "expected_fingerprint": "a" * 64,
            },
        }
    ]
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=raw_objects,
    )
    _persist_unit_packet(root, source_hash, raw_objects)
    monkeypatch.setattr(
        service := DocFitToolService(task_root=root),
        "inspect",
        lambda _args: pytest.fail("Tool must not inspect or renormalize a persisted packet"),
    )

    first = service.evidence({"focus": "unit_evidence_packet", "unit_id": "u-all", "limit": 1})
    retry = service.evidence({"focus": "unit_evidence_packet", "unit_id": "u-all", "limit": 1})

    assert first["evidence"] == retry["evidence"]
    assert first["evidence"] == [
        {
            "source_entry_id": canonical.source_entries[0].source_entry_id,
            "text": "  姓名\t张三  ",
            "text_length": 9,
            "leading_whitespace_count": 2,
            "trailing_whitespace_count": 2,
            "leading_whitespace_codepoints": ["U+0020 × 2"],
            "trailing_whitespace_codepoints": ["U+0020 × 2"],
            "entry_type": "text",
            "source_order": {"block": 1, "inline": 0},
            "word_format": {"story": "body"},
            "unit_contexts": first["evidence"][0]["unit_contexts"],
        }
    ]
    assert "extent" not in first["evidence"][0]


def test_unit_packet_fails_closed_when_canonical_inventory_is_missing(
    tmp_path: Path,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_registry(root)

    (root / "work/.docfit/harness/object-inventory.json").unlink()

    with pytest.raises(ToolFailure) as caught:
        DocFitToolService(task_root=root).evidence(
            {"focus": "unit_evidence_packet", "unit_id": "u-all"}
        )

    assert caught.value.code == "canonical_source_inventory_missing"


def test_unit_packet_fails_closed_when_canonical_inventory_source_is_stale(
    tmp_path: Path,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_registry(root)
    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "source",
            "object_ref": {
                "document_sha256": source_hash,
                "object_id": "obj-source",
                "expected_fingerprint": "a" * 64,
            },
        }
    ]
    _persist_unit_packet(root, source_hash, objects)
    inventory_path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    stale = build_canonical_source_inventory(
        source_snapshot_sha256="f" * 64,
        inspected_objects=objects,
    )
    inventory["canonical_source_inventory"] = stale.to_json()
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ToolFailure) as caught:
        DocFitToolService(task_root=root).evidence(
            {"focus": "unit_evidence_packet", "unit_id": "u-all"}
        )

    assert caught.value.code == "canonical_source_inventory_stale"


def test_unit_packet_fails_closed_when_unit_projection_is_stale(
    tmp_path: Path,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_registry(root)
    _persist_unit_packet(
        root,
        source_hash,
        [
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "source",
                "object_ref": {
                    "document_sha256": source_hash,
                    "object_id": "obj-source",
                    "expected_fingerprint": "a" * 64,
                },
            }
        ],
    )
    path = root / "work/.docfit/harness/object-inventory.json"
    inventory = json.loads(path.read_text())
    inventory["unit_projection_digest"] = "f" * 64
    path.write_text(json.dumps(inventory))

    with pytest.raises(ToolFailure) as caught:
        DocFitToolService(task_root=root).evidence(
            {"focus": "unit_evidence_packet", "unit_id": "u-all"}
        )

    assert caught.value.code == "initial_source_binding_invalid"


def test_t1_unit_evidence_packet_rejects_scope_ref_locator_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash},
            "objects": [],
            "object_count": 0,
            "risks": [],
            "failure": None,
        },
    )

    with pytest.raises(ToolFailure) as caught:
        service.evidence(
            {
                "focus": "unit_evidence_packet",
                "scope_ref": "/body/p[1]",
            }
        )

    error = caught.value
    assert error.code == "schema_envelope_invalid"
    assert "scope_ref" in error.message


def test_t1_unit_evidence_packet_rejects_legacy_checkpoint_unit_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_raw_unit_checkpoint(
        root,
        {
            "schema_version": 1,
            "status": "ok",
            "checkpoint": "unit-boundary",
            "source_hash": source_hash,
            "accepted_units": [
                {
                    "unit_id": "u-all",
                    "unit_name": "source",
                    "start_locator": "/body/p[1]",
                    "end_locator": "/body/p[1]",
                }
            ],
            "units": [
                {
                    "unit_id": "u-all",
                    "unit_name": "source",
                    "start_locator": "/body/p[1]",
                    "end_locator": "/body/p[1]",
                }
            ],
        },
    )
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash},
            "objects": [],
            "object_count": 0,
            "risks": [],
            "failure": None,
        },
    )

    with pytest.raises(ToolFailure) as caught:
        service.evidence(
            {
                "focus": "unit_evidence_packet",
                "unit_id": "u-all",
            }
        )

    error = caught.value
    assert error.code == "unit_boundary_proof_invalid"
    assert "accepted_units" not in error.message
    assert "units" not in error.message
    assert all("accepted_units" not in action for action in error.suggested_actions)
    assert all("units" not in action for action in error.suggested_actions)


def test_t1_unit_evidence_packet_rejects_resolved_unit_without_unit_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_raw_unit_checkpoint(
        root,
        {
            "schema_version": 1,
            "status": "ok",
            "checkpoint": "unit-boundary",
            "source_hash": source_hash,
            "resolved_units": [
                {
                    "unit_name": "source",
                    "start_locator": "/body/p[1]",
                    "end_locator": "/body/p[1]",
                }
            ],
        },
    )
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash},
            "objects": [],
            "object_count": 0,
            "risks": [],
            "failure": None,
        },
    )

    with pytest.raises(ToolFailure) as caught:
        service.evidence(
            {
                "focus": "unit_evidence_packet",
                "unit_id": "u-all",
            }
        )

    assert caught.value.code == "unit_boundary_proof_invalid"


def test_t1_unit_evidence_packet_rejects_legacy_scope_ref_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    checkpoint = {
        "schema_version": 1,
        "status": "ok",
        "checkpoint": "unit-boundary",
        "source_hash": source_hash,
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "scope_ref": "/body/p[1]",
            }
        ],
    }
    path = root / "work/.docfit/unit-boundary-checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint), encoding="utf-8")
    service = DocFitToolService(task_root=root)
    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash},
            "objects": [],
            "object_count": 0,
            "risks": [],
            "failure": None,
        },
    )

    with pytest.raises(ToolFailure) as caught:
        service.evidence(
            {
                "focus": "unit_evidence_packet",
                "unit_id": "u-all",
            }
        )

    error = caught.value
    assert error.code == "unit_boundary_proof_invalid"
    assert "scope_ref" not in error.message
    assert "locator" not in error.message
    assert "initial source inventory" in error.message
    assert all("scope_ref" not in action for action in error.suggested_actions)
    assert all("locator" not in action for action in error.suggested_actions)
    assert all("checkpoint" not in action for action in error.suggested_actions)


def test_t1_unit_evidence_packet_merges_adjacent_runs_into_agent_reading_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash = _task_root(tmp_path)
    _write_unit_checkpoint(root, source_hash)
    _write_registry(root)
    service = DocFitToolService(task_root=root)

    monkeypatch.setattr(
        service,
        "inspect",
        lambda _args: {
            "status": "ok",
            "document": {"sha256": source_hash, "paragraph_count": 4},
            "objects": [
                {
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "诚 信 声 明",
                    "style": "Normal",
                    "format": {"alignment": "center", "font.ea": "黑体", "size": "18pt"},
                    "object_ref": {"object_id": "p-title"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[1]",
                    "text": "诚",
                    "format": {"font.ea": "黑体", "size": "18pt"},
                    "object_ref": {"object_id": "r-title-1"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[2]",
                    "text": " ",
                    "format": {"font.ea": "黑体", "size": "18pt"},
                    "object_ref": {"object_id": "r-title-space"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[1]/r[3]",
                    "text": "信 声 明",
                    "format": {"font.ea": "黑体", "size": "18pt"},
                    "object_ref": {"object_id": "r-title-2"},
                },
                {
                    "type": "paragraph",
                    "locator": "/body/p[2]",
                    "text": "                    毕业论文（设计）作者签名：",
                    "format": {"size": "14pt"},
                    "object_ref": {"object_id": "p-signature"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[2]/r[1]",
                    "text": "                    ",
                    "format": {"size": "14pt"},
                    "object_ref": {"object_id": "r-signature-space"},
                },
                {
                    "type": "run",
                    "locator": "/body/p[2]/r[2]",
                    "text": "毕业论文（设计）作者签名：",
                    "format": {"size": "14pt"},
                    "object_ref": {"object_id": "r-signature-label"},
                },
            ],
            "object_count": 7,
            "object_window": {"returned": 7, "total": 7, "has_more": False},
            "risks": [],
            "failure": None,
        },
    )
    persisted_objects = service.inspect({})["objects"]
    assert isinstance(persisted_objects, list)
    _persist_unit_packet(root, source_hash, persisted_objects)

    result = service.evidence(
        {
            "focus": "unit_evidence_packet",
            "unit_id": "u-all",
        }
    )

    assert result["summary"]["evidence_shape"] == "agent_source_entries_v1"
    assert result["summary"]["view_shape"] == "agent_reading_blocks_v1"
    assert [item["text"] for item in result["evidence"]] == [
        "诚 信 声 明",
        "                    毕业论文（设计）作者签名：",
    ]
    assert result["summary"]["reading_ranges"] == [
        {
            "range_id": "u-all:range-whole-unit",
            "kind": "whole_unit",
            "unit_id": "u-all",
            "block_count": 2,
            "block_ids": ["u-all:block-0001", "u-all:block-0002"],
        }
    ]
    assert result["evidence"][0]["semantic_cues"] == [
        "centered_heading_candidate",
        "unit_heading_candidate",
    ]
    assert "signature_area_candidate" in result["evidence"][1]["semantic_cues"]
    assert "field_slot_candidate" in result["evidence"][1]["semantic_cues"]
    assert all(
        isinstance(item.get("source_entry_id"), str)
        and item["source_entry_id"].startswith("source-entry-")
        for item in result["evidence"]
    )
    assert "locator" not in result["evidence"][0]
    assert "object_id" not in result["evidence"][0]
    _assert_unit_evidence_packet_hides_internal_refs(result)


def test_t1_scope_ref_argument_is_retired_from_evidence_tool(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"focus": "document_map", "scope_ref": "/body/p[1]"})

    error = caught.value
    assert error.code == "schema_envelope_invalid"
    assert "scope_ref" in error.message


# Canonical full text paging, repeated text and retry identity are tested through
# document_map in test_full_flow_source_identity.py; candidate pages cannot redefine source IDs.


def test_t1_visual_page_without_render_ref_gives_unit_split_recovery_guidance(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as caught:
        service.evidence({"focus": "visual_page", "page": 1})

    error = caught.value
    assert error.code == "render_ref_missing"
    assert "render_snapshot" in error.suggested_actions
    assert "return_structural_units_if_visual_is_not_blocking" in error.suggested_actions


def test_t1_visual_page_does_not_expose_locator_candidates_to_agent(
    tmp_path: Path,
) -> None:
    root, source_hash = _task_root(tmp_path)

    class FakeVisual:
        def review(self, args: dict[str, object]):
            assert args["mode"] == "pages"
            assert args["pages"] == [6]
            return {"status": "ok", "reviewed_pages": [6]}, []

    service = DocFitToolService(task_root=root, visual=FakeVisual())  # type: ignore[arg-type]

    result = service.evidence(
        {
            "focus": "visual_page",
            "render_ref": "render:v2:" + "b" * 64,
            "page": 6,
            "limit": 12,
        }
    )

    assert "visual_review" in result["summary"]
    assert "page_locator_candidates" not in result["summary"]
    assert "page_locator_candidates_truncated" not in result["summary"]
    assert "page_locator_candidate_count" not in result["summary"]


def test_t1_docfit_evidence_handler_is_read_only_and_uses_service_facade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert docfit_evidence.annotations.readOnlyHint is True
    image_path = tmp_path / "page.png"
    Image.new("RGB", (1, 1), color="white").save(image_path)

    class _FakeService:
        def __init__(self) -> None:
            self._last_evidence_image_paths = [image_path]

        def evidence(self, args: dict[str, object]) -> dict[str, object]:
            return {
                "schema_version": "docfit_evidence_card_v1",
                "status": "ok",
                "source_hash": "a" * 64,
                "focus": args["focus"],
                "refs": {"document": "input/school-template.docx"},
                "summary": {"ok": True},
                "risks": [],
                "untrusted": {"marker": "untrusted_docx_source_data"},
                "failure": None,
            }

    monkeypatch.setattr("docfit.tools.DocFitToolService", _FakeService)

    result = asyncio.run(
        docfit_evidence.handler(
            {
                "schema_version": "docfit_evidence_input_v1",
                "focus": "document_map",
            }
        )
    )

    structured = result["structuredContent"]
    assert structured["status"] == "ok"
    assert structured["focus"] == "document_map"
    assert [item["type"] for item in result["content"]] == ["text", "image"]

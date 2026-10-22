from __future__ import annotations

import json
from pathlib import Path

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.reading_packet import build_unit_reading_packet
from docfit.template.source_entries import (
    build_canonical_source_inventory,
    project_source_entries_onto_objects,
)
from docfit.tools.runtime import sha256_file
from docfit.tools.service import DocFitToolService
from docfit.tools.surface import EVIDENCE_FOCUS
from tests.contract.test_template_materialization_runtime import _write_docx_from_paragraph_xml
from tests.support.source_identity import context_packets, persist_source_identity, source_partition


def _task_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    _write_docx_from_paragraph_xml(source, ["<w:p/>"])
    return root, sha256_file(source)


def _write_registry(root: Path) -> None:
    (root / "input/field-registry.json").write_text(
        json.dumps(
            {
                "registry_id": "docfit.test.fields",
                "registry_version": "0.1.0",
                "fields": [
                    {
                        "field_id": "thesis.title.zh",
                        "label": "中文论文题目",
                        "meaning": "论文题目",
                        "content_type": "text",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _fake_inspection(source_hash: str) -> dict[str, object]:
    return {
        "status": "ok",
        "document": {"sha256": source_hash, "paragraph_count": 1},
        "object_count": 1,
        "object_window": {"returned": 1, "total": 1, "has_more": False},
        "risks": [{"code": "synthetic-risk"}],
        "objects": [
            {
                "object_id": "obj-000000000000000000000001",
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "学校模板源文字",
                "object_ref": {
                    "document_sha256": source_hash,
                    "object_id": "obj-000000000000000000000001",
                    "expected_fingerprint": "b" * 64,
                },
            }
        ],
    }


def _persist_unit_packet(root: Path, source_hash: str) -> None:
    inspection = _fake_inspection(source_hash)
    objects = inspection["objects"]
    assert isinstance(objects, list)
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=objects,
    )
    projected = project_source_entries_onto_objects(
        objects,
        canonical.source_entries,
        source_sha256=source_hash,
    )
    vocabulary = FieldRegistrySnapshot.load(
        root / "input/field-registry.json"
    ).pre_input_vocabulary()
    packet = build_unit_reading_packet(
        unit={"unit_id": "u-all", "unit_name": "source"},
        scoped_objects=projected,
        source_entries=canonical.source_entries,
        field_id_vocabulary=vocabulary,
        layout_facts={},
        structure_context={},
        word_format_facts={},
    )
    inventory = {
        "document_sha256": source_hash,
        "canonical_source_inventory": canonical.to_json(),
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    source_partition(inventory)
    packet["source_entries"] = context_packets(inventory)["u-all"]["source_entries"]
    inventory["unit_reading_packets"] = {"u-all": packet}
    persist_source_identity(root, inventory, objects=objects)
    path = root / "work/.docfit/harness/object-inventory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory))


@pytest.mark.parametrize("focus", EVIDENCE_FOCUS)
def test_docfit_evidence_returns_agent_facing_context_not_semantic_answers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    focus: str,
) -> None:
    root, source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    render_ref = "render:v2:" + "c" * 64

    monkeypatch.setattr(service, "inspect", lambda _args: _fake_inspection(source_hash))
    monkeypatch.setattr(
        service,
        "render",
        lambda _args: (
            {"status": "ok", "render_ref": render_ref, "page_count": 1},
            [],
        ),
    )
    monkeypatch.setattr(
        service,
        "visual_review",
        lambda _args: (
            {"status": "ok", "reviewed_pages": [1], "findings": []},
            [],
        ),
    )
    if focus in {"unit_evidence_packet", "document_map"}:
        _write_registry(root)
        _persist_unit_packet(root, source_hash)
    before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

    args: dict[str, object] = {
        "schema_version": "docfit_evidence_input_v1",
        "focus": focus,
        "limit": 1,
    }
    if focus in {"visual_page", "visual_region"}:
        args["render_ref"] = render_ref
        args["page"] = 1
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

    serialized = json.dumps(result, ensure_ascii=False).casefold()
    for forbidden in (
        "<w:",
        "word/document.xml",
        "semantic_judgment",
        "school_semantic_role",
        "style_contract_ref",
        "fill-contract.gold",
        "final-template.gold",
    ):
        assert forbidden not in serialized

    if focus not in {"render_snapshot", "visual_page", "visual_region"}:
        evidence = result.get("evidence")
        assert isinstance(evidence, list)
        assert evidence
    if focus == "unit_evidence_packet":
        assert all(
            isinstance(item, dict)
            and "target_ref" not in item
            and "object_id" not in item
            and "source_entry_id" in item
            for item in evidence
        )
        for forbidden in (
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
            assert forbidden not in serialized
    elif focus == "document_map":
        assert all(isinstance(item.get("source_entry_id"), str) for item in evidence)
        assert all("target_ref" not in item for item in evidence)
    elif focus not in {"render_snapshot", "visual_page", "visual_region"}:
        assert all(
            isinstance(item, dict) and isinstance(item.get("target_ref"), str) for item in evidence
        )

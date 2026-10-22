"""Containers must not look empty when their text belongs to child entries."""

import json
from dataclasses import replace

from docfit.app.prepare_template import _post_unit_inventory_from_checkpoint
from docfit.template.reading_packet import agent_visible_unit_reading_packet
from docfit.tools.runtime import atomic_write_json, sha256_file
from docfit.tools.service import DocFitToolService
from tests.contract.test_prepare_template_runtime import _initial_objects, _prepared
from tests.contract.test_template_materialization_runtime import _write_docx_from_paragraph_xml


def test_actual_evidence_explains_container_text_ownership_without_duplicating_scope(tmp_path):
    prepared = _prepared(tmp_path)
    _write_docx_from_paragraph_xml(
        prepared.template_path,
        [
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p/></w:tc></w:tr></w:tbl>",
            "<w:p><w:r><w:t>Outside</w:t></w:r></w:p>",
        ],
    )
    prepared = replace(prepared, template_sha256=sha256_file(prepared.template_path))
    specs = [
        ("table", "table", "/body/tbl[1]", "A"),
        ("text", "paragraph", "/body/tbl[1]/tr[1]/tc[1]/p[1]", "A"),
        ("empty", "paragraph", "/body/tbl[1]/tr[1]/tc[2]/p[1]", ""),
        ("outside", "paragraph", "/body/p[1]", "Outside"),
    ]
    objects = [
        dict(type=kind, locator=locator, text=text, object_ref={"object_id": key})
        for key, kind, locator, text in specs
    ]
    checkpoint = _initial_objects(prepared, objects)
    inventory = _post_unit_inventory_from_checkpoint(prepared, checkpoint)
    packet = next(iter(inventory["unit_reading_packets"].values()))
    rows = agent_visible_unit_reading_packet(packet)["source_entries"]
    parent, text, empty, outside = rows
    assert parent["text"] == "" and text["text"] == "A" and empty["text"] == ""
    context = parent["structure_context"]
    assert [x["source_entry_id"] for x in context["descendant_entries"]] == [
        text["source_entry_id"],
        empty["source_entry_id"],
    ]
    assert [x["text"] for x in context["descendant_entries"]] == ["A", ""]
    assert (
        text["structure_context"]["ancestor_entries"][0]["source_entry_id"]
        == parent["source_entry_id"]
    )
    assert outside.get("structure_context") is None
    assert "own text" in context["reading_note"]
    assert all(word not in json.dumps(rows) for word in ["locator", "object_ref", "fingerprint"])
    atomic_write_json(prepared.task_root / "work/.docfit/harness/object-inventory.json", inventory)
    service = DocFitToolService(task_root=prepared.task_root)
    document = service.evidence({"focus": "document_map"})["summary"]["source_entries"]
    unit = service.evidence(
        {"focus": "unit_evidence_packet", "unit_id": packet["unit"]["unit_id"]}
    )["evidence"]
    for view in (document, unit):
        assert [x.get("structure_context") for x in view] == [
            x.get("structure_context") for x in rows
        ]

    import pytest

    from docfit.app.prepare_template import _ensure_post_unit_inventory
    from docfit.tools.runtime import ToolFailure

    packet.pop("structure_evidence_version")
    path = prepared.task_root / "work/.docfit/harness/object-inventory.json"
    atomic_write_json(path, inventory)
    before = path.read_bytes()
    for action in (
        lambda: _ensure_post_unit_inventory(prepared, checkpoint),
        lambda: service.evidence(
            {"focus": "unit_evidence_packet", "unit_id": packet["unit"]["unit_id"]}
        ),
    ):
        with pytest.raises(ToolFailure) as error:
            action()
        assert error.value.code == "source_structure_evidence_missing"
        assert path.read_bytes() == before


def test_revision_keeps_related_text_as_context_without_opening_its_edit_scope():
    from docfit.template.revision_context import build_revision_context
    from tests.contract.test_semantic_revision_context import _case

    inventory, manifest, ledger = _case()
    entry_id = manifest.required_source_entry_ids[0]
    context = {
        "reading_note": "Empty own text does not imply an empty container.",
        "ancestor_entries": [],
        "descendant_entries": [
            {"source_entry_id": "related-entry", "entry_type": "text", "text": "A"}
        ],
    }
    for packet in inventory["unit_reading_packets"].values():
        for entry in packet["source_entries"]:
            if entry["source_entry_id"] == entry_id:
                entry["structure_context"] = context
    result = build_revision_context(
        inventory=inventory,
        batch=manifest.batches[0],
        ledger=ledger,
        feedback={"blockers": [{"source_entry_id": entry_id}]},
        editable_source_entry_ids=(entry_id,),
    )
    entry = next(x for x in result["source_entries"] if x["source_entry_id"] == entry_id)
    assert entry["structure_context"] == context
    assert result["editable_source_entry_ids"] == [entry_id]


def test_nested_containment_uses_xml_not_equal_text_and_rejects_stale_source(tmp_path):
    import pytest

    from docfit.template.source_entries import build_canonical_source_inventory
    from docfit.template.source_structure import source_structure_context, visible_structure_context
    from docfit.tools.runtime import ToolFailure

    source = tmp_path / "source.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            "<w:tbl><w:tr><w:tc><w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r>"
            "</w:p></w:tc></w:tr></w:tbl></w:tc></w:tr></w:tbl>",
            "<w:p><w:r><w:t>A</w:t></w:r></w:p>",
        ],
    )
    objects = [
        dict(type=kind, locator=locator, text=text, object_ref={"object_id": str(i)})
        for i, (kind, locator, text) in enumerate(
            [
                ("table", "/body/tbl[1]", "A"),
                ("table", "/body/tbl[1]/tr[1]/tc[1]/tbl[1]", "A"),
                ("paragraph", "/body/tbl[1]/tr[1]/tc[1]/tbl[1]/tr[1]/tc[1]/p[1]", "A"),
                ("paragraph", "/body/p[1]", "A"),
            ]
        )
    ]
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=sha256_file(source),
        inspected_objects=objects,
    )
    before = canonical.to_json()
    context = source_structure_context(source, canonical)
    outer, inner, text, outside = [e.source_entry_id for e in canonical.source_entries]
    assert [e["source_entry_id"] for e in context[outer]["descendant_entries"]] == [inner, text]
    assert [e["source_entry_id"] for e in context[text]["ancestor_entries"]] == [outer, inner]
    assert outside not in context
    assert canonical.to_json() == before
    context[outer]["descendant_entries"][0]["locator"] = "/secret"
    assert "locator" not in json.dumps(visible_structure_context(context[outer]))
    with pytest.raises(ToolFailure) as error:
        source_structure_context(source, replace(canonical, source_snapshot_sha256="0" * 64))
    assert error.value.code == "source_structure_snapshot_mismatch"

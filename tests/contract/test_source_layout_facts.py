"""Source Word layout must reach the same initial and revision reading surface."""

import json
from dataclasses import replace

from docfit.app.prepare_template import _post_unit_inventory_from_checkpoint
from docfit.template.reading_packet import agent_visible_unit_reading_packet
from docfit.tools.runtime import sha256_file
from tests.contract.test_prepare_template_runtime import _initial_objects, _prepared
from tests.contract.test_template_materialization_runtime import _write_docx_from_paragraph_xml


def test_empty_section_carrier_has_layout_facts_in_actual_post_unit_packet(tmp_path):
    prepared = _prepared(tmp_path)
    _write_docx_from_paragraph_xml(
        prepared.template_path,
        [
            '<w:p><w:pPr><w:sectPr/></w:pPr><w:r><w:br w:type="page"/></w:r></w:p>',
            "<w:p/>",
            '<w:p><w:r><w:br w:type="page"/><w:t>TITLE</w:t></w:r></w:p>',
        ],
    )
    prepared = replace(prepared, template_sha256=sha256_file(prepared.template_path))
    objects = [
        {
            "type": "paragraph",
            "locator": f"/body/p[{i}]",
            "text": text,
            "object_ref": {"object_id": f"p{i}"},
        }
        for i, text in enumerate(["", "", "TITLE"], 1)
    ]
    checkpoint = _initial_objects(prepared, objects)
    inventory = _post_unit_inventory_from_checkpoint(prepared, checkpoint)
    packet = next(iter(inventory["unit_reading_packets"].values()))
    rows = agent_visible_unit_reading_packet(packet)["source_entries"]
    assert "The containing paragraph includes an explicit page break." in rows[0]["layout_facts"]
    assert "The containing paragraph carries section boundary settings." in rows[0]["layout_facts"]
    assert "The containing paragraph has no visible text." in rows[0]["layout_facts"]
    assert not rows[1].get("layout_facts")
    assert "The containing paragraph includes an explicit page break." in rows[2]["layout_facts"]
    assert "The containing paragraph has no visible text." not in rows[2]["layout_facts"]
    assert rows[0]["text"] == "" and rows[2]["text"] == "TITLE"
    from docfit.tools.runtime import atomic_write_json
    from docfit.tools.service import DocFitToolService

    atomic_write_json(prepared.task_root / "work/.docfit/harness/object-inventory.json", inventory)
    service = DocFitToolService(task_root=prepared.task_root)
    boundary_rows = service.evidence({"focus": "document_map"})["summary"]["source_entries"]
    assert [row.get("layout_facts") for row in boundary_rows] == [
        row.get("layout_facts") for row in rows
    ]
    unit = packet["unit"]["unit_id"]
    unit_rows = service.evidence({"focus": "unit_evidence_packet", "unit_id": unit})["evidence"]
    assert [row.get("layout_facts") for row in unit_rows] == [
        row.get("layout_facts") for row in rows
    ]
    visible = json.dumps(rows)
    assert all(word not in visible for word in ["locator", "fingerprint", "object_ref"])

    import pytest

    from docfit.app.prepare_template import _ensure_post_unit_inventory
    from docfit.tools.runtime import ToolFailure

    # Old persisted context must not silently omit the newly required evidence.
    packet.pop("layout_evidence_version")
    inventory_path = prepared.task_root / "work/.docfit/harness/object-inventory.json"
    atomic_write_json(inventory_path, inventory)
    before = inventory_path.read_bytes()
    for action in (
        lambda: _ensure_post_unit_inventory(prepared, checkpoint),
        lambda: service.evidence({"focus": "unit_evidence_packet", "unit_id": unit}),
    ):
        with pytest.raises(ToolFailure) as error:
            action()
        assert error.value.origin == "harness"
        assert error.value.code == "source_layout_evidence_missing"
        assert inventory_path.read_bytes() == before


def test_revision_context_keeps_layout_facts_without_backend_references():
    from docfit.template.revision_context import build_revision_context
    from tests.contract.test_semantic_revision_context import _case

    inventory, manifest, ledger = _case()
    entry_id = manifest.required_source_entry_ids[0]
    facts = ["The containing paragraph carries section boundary settings."]
    for packet in inventory["unit_reading_packets"].values():
        for entry in packet["source_entries"]:
            if entry["source_entry_id"] == entry_id:
                entry["layout_facts"] = facts
    result = build_revision_context(
        inventory=inventory,
        batch=manifest.batches[0],
        ledger=ledger,
        feedback={"blockers": [{"source_entry_id": entry_id}]},
        editable_source_entry_ids=(entry_id,),
    )
    entry = next(x for x in result["source_entries"] if x["source_entry_id"] == entry_id)
    assert entry["layout_facts"] == facts
    assert all(word not in json.dumps(entry) for word in ["locator", "object_ref", "fingerprint"])


def test_layout_facts_distinguish_explicit_breaks_from_render_cache_and_false_flags(tmp_path):
    from docfit.template.source_entries import build_canonical_source_inventory
    from docfit.template.source_layout import source_layout_facts

    source = tmp_path / "input/source.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            '<w:p><w:pPr><w:pageBreakBefore w:val="0"/></w:pPr>'
            "<w:r><w:lastRenderedPageBreak/><w:t>Text</w:t></w:r></w:p>",
            "<w:p><w:pPr><w:pageBreakBefore/></w:pPr><w:r><w:t>Other</w:t>"
            '<w:br w:type="column"/><w:br/><w:cr/></w:r></w:p>',
        ],
    )
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=sha256_file(source),
        inspected_objects=[
            {
                "type": "paragraph",
                "locator": f"/body/p[{i}]",
                "text": text,
                "object_ref": {"object_id": f"p{i}"},
            }
            for i, text in enumerate(["Text", "Other"], 1)
        ],
    )
    facts = source_layout_facts(source, canonical)
    assert canonical.source_entries[0].source_entry_id not in facts
    second = facts[canonical.source_entries[1].source_entry_id]
    assert second == [
        "Paragraph formatting explicitly requests a page break before it.",
        "The containing paragraph includes an explicit column break.",
        "The containing paragraph includes an explicit line break.",
    ]


def test_stale_word_cannot_supply_new_layout_facts(tmp_path):
    import pytest

    from docfit.template.source_entries import build_canonical_source_inventory
    from docfit.template.source_layout import source_layout_facts
    from docfit.tools.runtime import ToolFailure

    source = tmp_path / "input/source.docx"
    _write_docx_from_paragraph_xml(source, ["<w:p><w:r><w:t>Text</w:t></w:r></w:p>"])
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "Text",
                "object_ref": {"object_id": "p1"},
            }
        ],
    )
    with pytest.raises(ToolFailure) as error:
        source_layout_facts(source, canonical)
    assert error.value.origin == "harness"
    assert error.value.code == "source_layout_snapshot_mismatch"

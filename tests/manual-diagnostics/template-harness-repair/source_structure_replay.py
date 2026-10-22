"""Read-only replay of containment context against actual school task evidence."""

import argparse
import json
from pathlib import Path

from docfit.app.prepare_template import PreparedTemplateTask, _post_unit_inventory_from_checkpoint
from docfit.template.reading_packet import agent_visible_unit_reading_packet
from docfit.tools.runtime import sha256_file
from docfit.tools.service import DocFitToolService


def replay(task: Path, output: Path) -> dict:
    task, output = task.resolve(), output.resolve()
    assert not output.is_relative_to(task)
    output.mkdir(parents=True, exist_ok=False)
    source = task / "input/school-template.docx"
    registry = task / "input/field-registry.yaml"
    checkpoint_path = task / "work/.docfit/unit-boundary-checkpoint.json"
    inventory_path = task / "work/.docfit/harness/object-inventory.json"
    observed = [
        source,
        registry,
        checkpoint_path,
        inventory_path,
        task / "work/.docfit/initial-source-inventory.json",
    ]
    judgments = task / "work/.docfit/harness/semantic-judgments.json"
    if judgments.exists():
        observed.append(judgments)
    hashes = {str(path): sha256_file(path) for path in observed}
    prepared = PreparedTemplateTask(
        task_root=task,
        template_path=source,
        requirements_path=None,
        registry_source=registry,
        template_sha256=sha256_file(source),
        requirements_sha256=None,
        registry_sha256=sha256_file(registry),
    )
    old = json.loads(inventory_path.read_text())
    fresh = _post_unit_inventory_from_checkpoint(prepared, json.loads(checkpoint_path.read_text()))
    for key in ("canonical_source_inventory", "source_entries", "unit_projection_digest"):
        assert fresh[key] == old[key], key
    rows = {
        row["source_entry_id"]: row
        for packet in fresh["unit_reading_packets"].values()
        for row in agent_visible_unit_reading_packet(packet)["source_entries"]
    }
    window = DocFitToolService(task_root=task).evidence(
        {"focus": "document_map", "limit": len(rows)}
    )
    document_rows = window["summary"]["source_entries"]
    assert len(document_rows) == len(rows)
    for row in document_rows:
        assert row.get("structure_context") == rows[row["source_entry_id"]].get("structure_context")
    affected = [row for row in rows.values() if row.get("structure_context")]
    unavailable = [
        row for row in affected if "unavailable" in row["structure_context"]["reading_note"]
    ]
    assert not unavailable
    relations = [
        (row["source_entry_id"], child["source_entry_id"])
        for row in affected
        for child in row["structure_context"]["descendant_entries"]
    ]
    for parent, child in relations:
        assert parent in [
            x["source_entry_id"] for x in rows[child]["structure_context"]["ancestor_entries"]
        ]
    assert hashes == {str(path): sha256_file(path) for path in observed}
    result = {
        "verification_level": "real replay of source context; no Agent call or publication",
        "original_bindings": hashes,
        "original_unchanged": True,
        "canonical_identity_text_and_partition_unchanged": True,
        "source_entry_count": len(rows),
        "entries_with_containment_context": len(affected),
        "containment_relations": len(relations),
        "unavailable_entries": len(unavailable),
        "document_map_entries_compared": len(document_rows),
        "entries": affected,
        "product_acceptance": False,
    }
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (output / "projected-inventory.json").write_text(
        json.dumps(fresh, ensure_ascii=False, indent=2)
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.task, args.output)
    print(
        json.dumps({k: v for k, v in result.items() if k not in {"entries", "original_bindings"}})
    )

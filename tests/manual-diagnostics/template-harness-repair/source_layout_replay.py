"""Replay source layout evidence construction without changing an original task."""

import argparse
import json
import time
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
    initial_path = task / "work/.docfit/initial-source-inventory.json"
    inventory_path = task / "work/.docfit/harness/object-inventory.json"
    judgment_path = task / "work/.docfit/harness/semantic-judgments.json"
    manifest_path = task / "work/.docfit/prepare-template-task.json"
    observed = [source, registry, checkpoint_path, initial_path, inventory_path, manifest_path]
    if judgment_path.exists():
        observed.append(judgment_path)
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
    started = time.monotonic()
    fresh = _post_unit_inventory_from_checkpoint(prepared, json.loads(checkpoint_path.read_text()))
    elapsed = time.monotonic() - started
    old = json.loads(inventory_path.read_text())
    assert fresh["canonical_source_inventory"] == old["canonical_source_inventory"]
    assert fresh["source_entries"] == old["source_entries"]
    assert fresh["unit_projection_digest"] == old["unit_projection_digest"]
    rows = {}
    for packet in fresh["unit_reading_packets"].values():
        for row in agent_visible_unit_reading_packet(packet)["source_entries"]:
            rows[row["source_entry_id"]] = row
    service = DocFitToolService(task_root=task)
    window = service.evidence({"focus": "document_map", "limit": len(rows)})
    for row in window["summary"]["source_entries"]:
        assert row.get("layout_facts") == rows[row["source_entry_id"]].get("layout_facts")
    affected = [row for row in rows.values() if row.get("layout_facts")]
    assert hashes == {str(path): sha256_file(path) for path in observed}
    result = {
        "verification_level": "real replay of source evidence; no Agent call or publication",
        "original_bindings": hashes,
        "original_unchanged": True,
        "canonical_identity_text_and_partition_unchanged": True,
        "source_entry_count": len(rows),
        "entries_with_layout_facts": len(affected),
        "unavailable_entry_count": sum(
            any("unavailable" in fact for fact in row["layout_facts"]) for row in affected
        ),
        "new_post_unit_inventory_seconds": elapsed,
        "document_map_entries_compared": len(window["summary"]["source_entries"]),
        "entries": affected,
        "product_acceptance": False,
    }
    (output / "replay.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
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
        json.dumps(
            {k: v for k, v in result.items() if k not in {"entries", "original_bindings"}},
            ensure_ascii=False,
            indent=2,
        )
    )

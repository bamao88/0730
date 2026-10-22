"""Compare frozen inspection order with a fresh Word-ordered initial preparation."""

import argparse
from collections import Counter
from pathlib import Path

from docfit.template.source_entries import build_canonical_source_inventory
from docfit.template.source_order import order_initial_source_objects
from docfit.template.unit_source import INITIAL_INVENTORY_PATH
from docfit.tools.runtime import atomic_write_json, read_json, sha256_file, sha256_json


def replay(task: Path, prepared_task: Path, output: Path) -> dict:
    task, prepared_task, output = task.resolve(), prepared_task.resolve(), output.resolve()
    assert not output.is_relative_to(task) and not output.is_relative_to(prepared_task)
    source = task / "input/school-template.docx"
    paths = [source, task / INITIAL_INVENTORY_PATH,
             prepared_task / "input/school-template.docx", prepared_task / INITIAL_INVENTORY_PATH]
    hashes = {str(p): sha256_file(p) for p in paths}
    initial = read_json(task / INITIAL_INVENTORY_PATH)
    fresh = read_json(prepared_task / INITIAL_INVENTORY_PATH)
    assert sha256_file(source) == sha256_file(prepared_task / "input/school-template.docx")
    ordered = order_initial_source_objects(
        source, source_sha256=sha256_file(source), objects=initial["objects"],
    )
    assert Counter(sha256_json(o) for o in ordered) == Counter(
        sha256_json(o) for o in initial["objects"]
    )
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=sha256_file(source), inspected_objects=ordered,
    ).to_json()
    assert canonical == fresh["canonical_source_inventory"]

    def content(entry):
        return {k: v for k, v in entry.items() if k not in {"source_entry_id", "source_order"}}

    old_entries = initial["canonical_source_inventory"]["source_entries"]
    assert Counter(sha256_json(content(e)) for e in old_entries) == Counter(
        sha256_json(content(e)) for e in canonical["source_entries"]
    )
    old_by_content = {sha256_json(content(e)): e for e in old_entries}
    movements = []
    for entry in canonical["source_entries"]:
        old = old_by_content[sha256_json(content(entry))]
        if old["source_order"] != entry["source_order"]:
            movements.append({
                "old_id": old["source_entry_id"], "new_id": entry["source_entry_id"],
                "entry_type": entry["entry_type"], "old_order": old["source_order"],
                "new_order": entry["source_order"],
                "locators": [p["locator"] for p in entry["provenance"]],
            })
    assert hashes == {p: sha256_file(Path(p)) for p in hashes}
    report = {
        "verification_level": "real frozen-inventory replay compared with actual fresh preparation",
        "original_bindings": hashes, "original_unchanged": True,
        "object_facts_unchanged": True, "source_entry_text_and_provenance_unchanged": True,
        "fresh_officecli_preparation_matches_replay": True,
        "source_entry_count": len(canonical["source_entries"]),
        "moved_entry_count": len(movements), "movements": movements,
        "new_inventory": canonical, "old_proof_reused": False,
        "agent_called": False, "product_acceptance": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output / "verification.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--prepared-task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.task, args.prepared_task, args.output)
    print({k: report[k] for k in (
        "source_entry_count", "moved_entry_count", "fresh_officecli_preparation_matches_replay",
    )})

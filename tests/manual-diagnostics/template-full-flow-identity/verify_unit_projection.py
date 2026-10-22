"""Real input mechanical probes, explicitly not Agent semantic replay."""

import json
from pathlib import Path

from docfit.template.source_entries import CanonicalSourceInventory
from docfit.template.unit_source import load_initial_inventory, resolve_unit_partition
from docfit.tools.runtime import sha256_file

base = Path("temp/full-flow-id-20260922")
results = []
for school in ("hunau", "njau", "pku"):
    root = base / (school + "-initial-read-proof")
    initial = load_initial_inventory(root, sha256_file(root / "input/school-template.docx"))
    canonical = CanonicalSourceInventory.from_json(initial["canonical_source_inventory"])
    entries = canonical.source_entries
    entry = next(e for e in entries if len(e.text) > 3)
    middle = len(entry.text) // 2
    cut = {
        "source_entry_id": entry.source_entry_id,
        "edge": "split",
        "before": entry.text[:middle],
        "after": entry.text[middle:],
    }
    units = [
        {
            "unit_id": "first",
            "unit_name": "mechanical range A",
            "start_boundary": {"source_entry_id": entries[0].source_entry_id, "edge": "start"},
            "end_boundary": cut,
        },
        {
            "unit_id": "second",
            "unit_name": "mechanical range B",
            "start_boundary": cut,
            "end_boundary": {"source_entry_id": entries[-1].source_entry_id, "edge": "end"},
        },
    ]
    projected = resolve_unit_partition(canonical, units)
    shared = [
        s
        for u in projected
        for s in u["source_spans"]
        if s["source_entry_id"] == entry.source_entry_id
    ]
    assert len(shared) == 2 and "".join(s["text"] for s in shared) == entry.text
    assert shared[0]["extent"]["end"] == shared[1]["extent"]["start"] == middle
    ids = {s["source_entry_id"] for u in projected for s in u["source_spans"]}
    assert ids == {e.source_entry_id for e in entries}
    assert load_initial_inventory(root, canonical.source_snapshot_sha256) == initial
    result = {
        "school": school,
        "source_sha256": canonical.source_snapshot_sha256,
        "inventory_digest": canonical.inventory_digest,
        "source_entry_count": len(entries),
        "shared_entry": entry.source_entry_id,
        "split_offset_harness_computed": middle,
        "same_id_both_units": True,
        "coverage_exact": True,
        "level": (
            "real input mechanical boundary projection; "
            "test-authored boundaries, not Agent judgment replay"
        ),
    }
    results.append(result)
    print(json.dumps(result))
(base / "unit-projection-proof.json").write_text(json.dumps(results, indent=2) + "\n")

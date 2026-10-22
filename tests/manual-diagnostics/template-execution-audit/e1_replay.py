"""Replay an unchanged, accepted school task through the E1 materializer only."""

import argparse
import json
from pathlib import Path

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization import materialize_template_from_semantics
from docfit.template.source_spans import review_resolved_spans_match
from docfit.template.unit_source import load_initial_inventory, validate_inventory_partition
from docfit.tools.runtime import sha256_file, sha256_json


def replay(task: Path, output: Path) -> dict:
    task, output = task.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    names = [
        "input/school-template.docx",
        "input/field-registry.yaml",
        "work/.docfit/initial-source-inventory.json",
        "work/.docfit/unit-boundary-checkpoint.json",
        "work/.docfit/harness/object-inventory.json",
        "work/.docfit/harness/semantic-judgments.json",
    ]
    hashes = {name: sha256_file(task / name) for name in names}
    source, registry_path = task / names[0], task / names[1]
    registry = FieldRegistrySnapshot.load(registry_path)
    inventory = json.loads((task / names[4]).read_text())
    review = json.loads((task / names[5]).read_text())
    initial = load_initial_inventory(task, sha256_file(source))
    assert inventory["canonical_source_inventory"] == initial["canonical_source_inventory"]
    validate_inventory_partition(inventory)
    assert inventory["field_id_vocabulary"] == registry.pre_input_vocabulary()
    assert review["semantic_judgments_sha256"] == sha256_json(review["semantic_judgments"])
    assert review_resolved_spans_match(
        inventory=inventory, semantic_judgments=review["semantic_judgments"]
    )
    receipt = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output / "candidate.docx",
        registry=registry,
        inventory=inventory,
        review=review,
    )
    assert hashes == {name: sha256_file(task / name) for name in names}
    (output / "materialization.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    )
    result = {
        "verification_level": "real replay; full materializer; original accepted judgments",
        "task": str(task),
        "input_hashes": hashes,
        "original_unchanged": True,
        "agent_called": False,
        "product_acceptance": False,
        "operation_count": receipt["operation_count"],
        "cleanup_count": receipt["cleanup_count"],
        "effect_verification": receipt["effect_verification"],
    }
    (output / "replay.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.task, args.output), ensure_ascii=False))

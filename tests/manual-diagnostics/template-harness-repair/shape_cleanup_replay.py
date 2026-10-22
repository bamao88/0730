"""Replay one original shape deletion as a Tool slice, never publish a template.

The complete candidate can remain blocked. This deliberately invokes only the
selected execution primitive in memory; it is not a full materialization pass.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.executor import write_materialized_docx
from docfit.template.materialization.handlers.cleanup import exact_shape_cleanup_locator
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.runtime import (
    _remove_exact_cleanup_intent,
    _resolve_all_span_targets,
)
from docfit.template.source_spans import review_resolved_spans_match
from docfit.template.unit_source import load_initial_inventory, validate_inventory_partition
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.word_parts import read_word_stories, resolve_story_locator
from docfit.tools.word_xml import serialize_word_xml


def replay(task: Path, entry_id: str, output: Path) -> dict:
    task = task.resolve()
    output = output.resolve()
    assert not output.is_relative_to(task), "Do not modify the original task."
    output.mkdir(parents=True, exist_ok=False)
    source = task / "input/school-template.docx"
    inventory_path = task / "work/.docfit/harness/object-inventory.json"
    review_path = task / "work/.docfit/harness/semantic-judgments.json"
    registry_path = task / "input/field-registry.yaml"
    observed = [source, inventory_path, review_path, registry_path]
    hashes = {str(path): sha256_file(path) for path in observed}
    inventory = json.loads(inventory_path.read_text())
    review = json.loads(review_path.read_text())
    registry = FieldRegistrySnapshot.load(registry_path)
    initial = load_initial_inventory(task, sha256_file(source))
    assert inventory["canonical_source_inventory"] == initial["canonical_source_inventory"]
    validate_inventory_partition(inventory)
    assert inventory["field_id_vocabulary"] == registry.pre_input_vocabulary()
    assert review["semantic_judgments_sha256"] == sha256_json(review["semantic_judgments"])
    assert review_resolved_spans_match(
        inventory=inventory, semantic_judgments=review["semantic_judgments"],
    )
    compiled = build_shadow_materialization_plan(
        inventory=inventory, review=review, registry=registry,
    )
    selected = [intent for intent in compiled.plan.intents
                if any(span.source_entry_id == entry_id for span in intent.resolved_spans)]
    assert len(selected) == 1
    intent = selected[0]
    locator = exact_shape_cleanup_locator(intent)
    assert locator is not None
    assert not any(
        item.reason_code in {
                          "materialization_cleanup_carrier_conflict",
                          "materialization_semantic_scope_conflict",
                      }
        and any(scope.ref_id == entry_id for scope in item.scope_refs)
        for item in compiled.unsupported
    )
    with zipfile.ZipFile(source) as archive:
        stories = read_word_stories(archive)
        expected_stories = read_word_stories(archive)
    # The oracle removes only the exact accepted XML node; every other node must match.
    expected_story, expected_shape = resolve_story_locator(expected_stories, locator)
    assert expected_story.part_name == "word/document.xml", "This replay slice targets body shapes."
    parent = next(node for node in expected_story.root.iter() if expected_shape in list(node))
    parent.remove(expected_shape)
    slice_plan = replace(compiled.plan, intents=(intent,))
    targets = _resolve_all_span_targets(stories=stories, plan=slice_plan)
    receipt = _remove_exact_cleanup_intent(
        document=targets[intent.resolved_spans[0].span_ref].story.root,
        intent=intent, targets=targets, removed_carriers=set(),
    )
    for key in stories:
        assert ET.tostring(stories[key].root) == ET.tostring(expected_stories[key].root)
    candidate = output / "diagnostic-shape-deletion.docx"
    write_materialized_docx(
        source_docx=source, output_docx=candidate,
        document_xml=serialize_word_xml(stories["body"].root),
    )
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        assert before.namelist() == after.namelist()
        assert all(before.read(name) == after.read(name) for name in before.namelist()
                   if name != "word/document.xml")
    assert hashes == {str(path): sha256_file(path) for path in observed}
    result = {
        "level": "real replay of original shape cleanup; isolated Tool execution slice",
        "full_materialization": False, "agent_called": False, "product_acceptance": False,
        "input_hashes": hashes, "source_entry_id": entry_id, "exact_locator": locator,
        "receipt": receipt, "only_selected_xml_node_removed": True,
        "other_package_parts_unchanged": True, "original_task_unchanged": True,
        "other_compiler_blockers": [item.reason_code for item in compiled.unsupported],
        "candidate": str(candidate), "candidate_sha256": sha256_file(candidate),
    }
    (output / "replay.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--source-entry", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.task, args.source_entry, args.output)
    print(json.dumps({key: result[key] for key in (
        "level", "source_entry_id", "only_selected_xml_node_removed", "original_task_unchanged",
    )}, ensure_ascii=False))

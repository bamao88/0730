"""Replay original picture deletions in isolation, retaining the full review's blockers."""

import argparse
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.accepted_effects import AcceptedEffects
from docfit.template.materialization.effect_verification import (
    verify_written_package,
)
from docfit.template.materialization.executor import write_materialized_docx
from docfit.template.materialization.handlers.cleanup import cleanup_kind
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.materialization.runtime import (
    _remove_exact_cleanup_intent,
    _resolve_all_span_targets,
)
from docfit.template.source_spans import review_resolved_spans_match
from docfit.template.unit_source import load_initial_inventory, validate_inventory_partition
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.word_parts import read_word_stories, resolve_story_locator
from docfit.tools.word_xml import W_NS, serialize_word_xml

W = f"{{{W_NS}}}"


def replay(task: Path, output: Path) -> dict:
    task, output = task.resolve(), output.resolve()
    assert not output.is_relative_to(task)
    output.mkdir(parents=True, exist_ok=False)
    names = [
        "input/school-template.docx",
        "input/field-registry.yaml",
        "work/.docfit/initial-source-inventory.json",
        "work/.docfit/unit-boundary-checkpoint.json",
        "work/.docfit/harness/object-inventory.json",
        "work/.docfit/harness/semantic-judgments.json",
        "work/.docfit/post-unit-materialization/materialization.json",
    ]
    hashes = {name: sha256_file(task / name) for name in names}
    source = task / names[0]
    registry = FieldRegistrySnapshot.load(task / names[1])
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
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    compiled = build_shadow_materialization_plan(
        inventory=inventory, review=review, registry=registry
    )
    selected = tuple(
        i
        for i in compiled.intents
        if i.intent_type.value == "delete_block" and cleanup_kind(i) == "drawing_run"
    )
    assert len(selected) == 2, "This diagnostic replays the original two NJAU picture judgments."
    with zipfile.ZipFile(source) as archive:
        stories, expected = read_word_stories(archive), read_word_stories(archive)
    # Independent oracle: remove the sole drawing child, retaining its run,
    # paragraph, properties, siblings, tables and every other package part.
    for intent in selected:
        fragment = intent.resolved_spans[0].word_fragments[0]
        story, run = resolve_story_locator(expected, fragment["locator"])
        assert story.part_name == "word/document.xml" and run.tag == W + "r"
        drawings = run.findall(W + "drawing")
        assert len(drawings) == 1
        run.remove(drawings[0])
    plan = replace(compiled.plan, intents=selected)
    targets = _resolve_all_span_targets(stories=stories, plan=plan, inventory=inventory)
    spans = [s.to_json() for i in selected for s in i.resolved_spans]
    selected_refs = {s["span_ref"] for s in spans}
    slice_review = {"resolved_spans": spans, "semantic_judgments": [
        j for j in review["semantic_judgments"]
        if all(s["span_ref"] in selected_refs for s in j["resolved_spans"])
    ]}
    authority = AcceptedEffects(stories=stories, inventory=inventory,
                                review=slice_review, registry=registry)
    editor = authority.make_editor(stories)
    removed_ids: set[int] = set()
    receipts = [
        _remove_exact_cleanup_intent(
            document=stories["body"].root, intent=i, targets=targets, removed_carriers=removed_ids
        )
        for i in selected
    ]
    authority.verify(editor)
    for key in stories:
        assert ET.tostring(stories[key].root) == ET.tostring(expected[key].root)
    candidate = output / "diagnostic-picture-deletions.docx"
    write_materialized_docx(
        source_docx=source,
        output_docx=candidate,
        document_xml=serialize_word_xml(stories["body"].root),
        verify=lambda path: verify_written_package(
            path, source=source, changed_roots={"word/document.xml": expected["body"].root}
        ),
    )
    assert hashes == {name: sha256_file(task / name) for name in names}
    result = {
        "verification_level": "real replay; original picture judgments; isolated Tool slice",
        "task": str(task),
        "input_hashes": hashes,
        "original_unchanged": True,
        "full_materialization": False,
        "agent_called": False,
        "product_acceptance": False,
        "picture_count": len(selected),
        "receipts": receipts,
        "only_selected_drawings_removed": True,
        "accepted_scope_verified": True,
        "reopened_package_verified": True,
        "protected_subtree_count": len(authority.verification.protected),
        "full_review_feedback": feedback,
        "candidate_sha256": sha256_file(candidate),
    }
    (output / "replay.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.task, args.output)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "verification_level",
                    "picture_count",
                    "only_selected_drawings_removed",
                    "original_unchanged",
                    "reopened_package_verified",
                )
            },
            ensure_ascii=False,
        )
    )

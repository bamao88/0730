"""Replay original repeated-body interfaces as a Tool slice, not whole-school publication."""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.accepted_effects import AcceptedEffects
from docfit.template.materialization.body_interfaces import body_interfaces, validate_coalescence
from docfit.template.materialization.effect_verification import verify_written_package
from docfit.template.materialization.executor import write_materialized_docx
from docfit.template.materialization.models import MaterializationIntentType
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.runtime import (
    _materialize_body_intents,
    _resolve_all_span_targets,
)
from docfit.template.source_spans import review_resolved_spans_match
from docfit.template.unit_source import (
    load_initial_inventory,
    source_unit_cut_points,
    validate_inventory_partition,
)
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.word_parts import read_word_stories
from docfit.tools.word_xml import serialize_word_xml

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def replay(task: Path, output: Path) -> dict:
    task, output = task.resolve(), output.resolve()
    assert not output.is_relative_to(task)
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
    cuts = source_unit_cut_points(validate_inventory_partition(inventory))
    assert inventory["field_id_vocabulary"] == registry.pre_input_vocabulary()
    assert review["semantic_judgments_sha256"] == sha256_json(review["semantic_judgments"])
    assert review_resolved_spans_match(
        inventory=inventory, semantic_judgments=review["semantic_judgments"],
    )
    compiled = build_shadow_materialization_plan(
        inventory=inventory, review=review, registry=registry,
    )
    selected = tuple(intent for intent in compiled.plan.intents if (
        intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
        and any(len(group.source_spans) > 1 for group in body_interfaces(
            intent.resolved_spans, cut_points=cuts,
        ))
    ))
    assert selected, "The original task has no coalescible body interfaces."
    groups = [group for intent in selected for group in body_interfaces(
        intent.resolved_spans, cut_points=cuts,
    )]
    for group in groups:
        record = group.coalescence()
        if record is not None:
            validate_coalescence(record, anchor=group.anchor, partition=inventory, cut_points=cuts)
    with zipfile.ZipFile(source) as archive:
        stories = read_word_stories(archive)
    document = stories["body"].root
    # Keep original blockers. Only the selected execution primitive is being replayed.
    slice_plan = replace(compiled.plan, intents=selected)
    targets = _resolve_all_span_targets(stories=stories, plan=slice_plan)
    selected_paragraphs = {id(target.body_block) for target in targets.values()}
    protected = [(node, ET.tostring(node)) for node in document.iter(W + "p")
                 if id(node) not in selected_paragraphs]
    paragraph_properties = {
        id(target.body_block): ET.tostring(target.body_block.find(W + "pPr"))
        for target in targets.values()
        if target.body_block is not None and target.body_block.find(W + "pPr") is not None
    }
    spans = [span.to_json() for intent in selected for span in intent.resolved_spans]
    selected_refs = {s["span_ref"] for s in spans}
    slice_review = {"resolved_spans": spans, "semantic_judgments": [
        j for j in review["semantic_judgments"]
        if all(s["span_ref"] in selected_refs for s in j["resolved_spans"])
    ]}
    authority = AcceptedEffects(stories=stories, inventory=inventory,
                                review=slice_review, registry=registry)
    editor = authority.make_editor(stories)
    operations, cleanup = _materialize_body_intents(
        document=document, inventory=inventory, plan=slice_plan, targets=targets, registry=registry,
        editor=editor,
    )
    editor.apply()
    authority.verify(editor)
    members = [member for operation in operations for member in operation.get("members", [])]
    assert len(members) == len(groups)
    assert {member["slot_ref"] for member in members} == {group.slot_ref for group in groups}
    current_nodes = {id(node) for node in document.iter()}
    assert all(
        id(node) in current_nodes and ET.tostring(node) == before for node, before in protected
    )
    for target in targets.values():
        if id(target.body_block) in paragraph_properties:
            assert ET.tostring(target.body_block.find(W + "pPr")) == paragraph_properties[
                id(target.body_block)
            ]
    tags = [tag.get(W + "val") for tag in document.iter(W + "tag")]
    assert all(tags.count(group.slot_ref) == 1 for group in groups)
    for group in groups:
        record = group.coalescence()
        member = next(member for member in members if member["slot_ref"] == group.slot_ref)
        assert member.get("coalescence") == record
        assert all(span.slot_ref not in tags for span in group.source_spans[1:])
    candidate = output / "diagnostic-body-interfaces.docx"
    write_materialized_docx(
        source_docx=source, output_docx=candidate, document_xml=serialize_word_xml(document),
        verify=lambda path: verify_written_package(
            path, source=source, changed_roots={"word/document.xml": document}),
    )
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        assert before.namelist() == after.namelist()
        assert all(before.read(name) == after.read(name) for name in before.namelist()
                   if name != "word/document.xml")
    assert hashes == {str(path): sha256_file(path) for path in observed}
    result = {
        "level": "real replay of original body judgments; isolated Tool execution slice",
        "accepted_scope_verified": True, "reopened_package_verified": True,
        "full_materialization": False, "agent_called": False, "product_acceptance": False,
        "input_hashes": hashes, "physical_interface_count": len(groups),
        "contributing_body_span_count": sum(len(group.source_spans) for group in groups),
        "protected_paragraphs_unchanged": len(protected), "paragraph_properties_unchanged": True,
        "original_task_unchanged": True, "other_package_parts_unchanged": True,
        "operations": operations, "cleanup": cleanup,
        "other_compiler_blockers": [item.reason_code for item in compiled.unsupported],
        "candidate": str(candidate), "candidate_sha256": sha256_file(candidate),
    }
    (output / "replay.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.task, args.output)
    print(json.dumps({key: result[key] for key in (
        "level", "physical_interface_count", "contributing_body_span_count",
        "protected_paragraphs_unchanged", "original_task_unchanged",
    )}, ensure_ascii=False))

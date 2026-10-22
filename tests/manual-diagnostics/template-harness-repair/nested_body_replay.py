"""Replay original table-cell text body interfaces, retaining every full-run blocker."""

import argparse
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.accepted_effects import AcceptedEffects
from docfit.template.materialization.body_interfaces import body_interfaces, body_paragraph_carrier
from docfit.template.materialization.effect_verification import verify_written_package
from docfit.template.materialization.executor import write_materialized_docx
from docfit.template.materialization.models import MaterializationIntentType
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.readiness import materialization_readiness_feedback
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
    watched = [source, inventory_path, review_path, registry_path]
    hashes = {str(p): sha256_file(p) for p in watched}
    inventory, review = json.loads(inventory_path.read_text()), json.loads(review_path.read_text())
    registry = FieldRegistrySnapshot.load(registry_path)
    initial = load_initial_inventory(task, sha256_file(source))
    assert inventory["canonical_source_inventory"] == initial["canonical_source_inventory"]
    cuts = source_unit_cut_points(validate_inventory_partition(inventory))
    assert inventory["field_id_vocabulary"] == registry.pre_input_vocabulary()
    assert review["semantic_judgments_sha256"] == sha256_json(review["semantic_judgments"])
    assert review_resolved_spans_match(
        inventory=inventory, semantic_judgments=review["semantic_judgments"]
    )
    full_feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    compiled = build_shadow_materialization_plan(
        inventory=inventory, review=review, registry=registry
    )

    def supported(intent):
        members = [s for s in intent.resolved_spans if s.role == "body_structure"]
        return (
            intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
            and members
            and all(
                s.field_id
                and registry.lookup(s.field_id).get("content_type") in {"text", "rich_text"}
                and all(
                    (p := body_paragraph_carrier(f.get("locator"))) and "/tc[" in p
                    for f in s.word_fragments
                )
                for s in members
            )
        )

    selected = tuple(i for i in compiled.plan.intents if supported(i))
    assert selected
    slice_plan = replace(compiled.plan, intents=selected)
    with zipfile.ZipFile(source) as archive:
        stories = read_word_stories(archive)
    document = stories["body"].root
    targets = _resolve_all_span_targets(stories=stories, plan=slice_plan)
    selected_paragraphs = {id(t.paragraph) for t in targets.values()}
    protected = [
        (p, ET.tostring(p)) for p in document.iter(W + "p") if id(p) not in selected_paragraphs
    ]
    properties = [
        (p, ET.tostring(p))
        for p in document.iter()
        if p.tag in {W + tag for tag in ("pPr", "tblPr", "tblGrid", "trPr", "tcPr")}
    ]
    containers = [
        (n, tuple(id(child) for child in n))
        for n in document.iter()
        if n.tag in {W + "tbl", W + "tr", W + "tc"}
    ]
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
        document=document,
        inventory=inventory,
        plan=slice_plan,
        targets=targets,
        registry=registry,
        editor=editor,
    )
    editor.apply()
    authority.verify(editor)
    groups = [
        g for intent in selected for g in body_interfaces(intent.resolved_spans, cut_points=cuts)
    ]
    members = [m for op in operations for m in op.get("members", [])]
    assert {m["slot_ref"] for m in members} == {g.slot_ref for g in groups}
    assert len(members) == len(groups)
    nodes = {id(n) for n in document.iter()}
    assert all(id(p) in nodes and ET.tostring(p) == old for p, old in [*protected, *properties])
    assert all(tuple(id(c) for c in n) == children for n, children in containers)
    tags = [t.get(W + "val") for t in document.iter(W + "tag")]
    assert all(tags.count(g.slot_ref) == 1 for g in groups)
    candidate = output / "diagnostic-cell-body-interfaces.docx"
    write_materialized_docx(
        source_docx=source, output_docx=candidate, document_xml=serialize_word_xml(document),
        verify=lambda path: verify_written_package(
            path, source=source, changed_roots={"word/document.xml": document}),
    )
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        assert before.namelist() == after.namelist()
        assert all(
            before.read(name) == after.read(name)
            for name in before.namelist()
            if name != "word/document.xml"
        )
    assert hashes == {str(p): sha256_file(p) for p in watched}
    result = {
        "verification_level": "real replay; unchanged original judgments; Tool execution slice",
        "accepted_scope_verified": True, "reopened_package_verified": True,
        "full_materialization": False,
        "agent_called": False,
        "product_acceptance": False,
        "original_bindings": hashes,
        "original_unchanged": True,
        "physical_interface_count": len(groups),
        "selected_intent_count": len(selected),
        "protected_paragraph_count": len(protected),
        "properties_unchanged": True,
        "table_row_cell_topology_unchanged": True,
        "other_package_parts_unchanged": True,
        "full_readiness_feedback": full_feedback,
        "other_compiler_blockers": [i.reason_code for i in compiled.unsupported],
        "operations": operations,
        "cleanup": cleanup,
        "candidate": str(candidate),
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
                    "physical_interface_count",
                    "protected_paragraph_count",
                    "original_unchanged",
                    "table_row_cell_topology_unchanged",
                )
            },
            ensure_ascii=False,
        )
    )

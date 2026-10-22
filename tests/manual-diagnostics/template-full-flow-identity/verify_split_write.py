"""Actual DOCX writes after a test-authored split of one real Agent-judged entry.

This is logic/contract verification on real input plus actual DOCX mutation. The
new partition is mechanical test input, not a new Agent run or a replay of the
original Agent partition. Original semantic judgments and run evidence stay intact.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from verify_identity import W, paragraph_map, read, shape, verify_inline_ranges

from docfit.app.prepare_template import (
    PreparedTemplateTask,
    _post_unit_inventory_from_checkpoint,
)
from docfit.fields import FieldRegistrySnapshot
from docfit.template.harness import TemplateHarnessService
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.semantic_batches import build_semantic_batch_manifest
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_entries import CanonicalSourceInventory
from docfit.template.unit_source import (
    INITIAL_INVENTORY_PATH,
    UNIT_PROOF_SCHEMA,
    load_initial_inventory,
    proof_binding,
    require_initial_binding,
    resolve_unit_partition,
    validate_unit_proof,
)
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.word_parts import read_word_stories, resolve_story_locator

DEFAULT_ROOT = Path("temp/full-flow-id-20260922/njau-cover-live")
DEFAULT_OUTPUT = Path("temp/full-flow-id-20260922/identity-closure/split-write")
SHARED_ENTRY = "source-entry-d9616f4db3dd070938de96e3"
PROOF_PATH = Path("work/.docfit/unit-boundary-checkpoint.json")
MANIFEST_PATH = Path("work/.docfit/prepare-template-task.json")
INVENTORY_PATH = Path("work/.docfit/harness/object-inventory.json")
REVIEW_PATH = Path("work/.docfit/harness/semantic-judgments.json")
CANDIDATES_PATH = Path("work/.docfit/harness/semantic-batch-candidates.json")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def run_hashes(root):
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def compare_packages(left, right):
    """Compare actual reopened package contents, allowing only XML prefix spelling."""
    with ZipFile(left) as a, ZipFile(right) as b:
        assert set(a.namelist()) == set(b.namelist()), "Package parts differ"
        for name in a.namelist():
            av, bv = a.read(name), b.read(name)
            if name.endswith(".xml"):
                assert shape(ET.fromstring(av)) == shape(ET.fromstring(bv)), name
            else:
                assert av == bv, name
        return len(a.namelist())


def verify_unselected(source, candidate, stories, spans):
    """Check untouched paragraph trees through transparent content-control wrappers.

    body.table in this real run wraps the original table. Its descendant paragraphs
    must still match unless a separate accepted inline part changes that paragraph.
    """
    changed_paragraphs = set()
    changed_parts = {"word/document.xml"}
    for span in spans:
        role = span["role"]
        if role not in {"fill_slot", "cleanup", "style_only", "body_structure"}:
            continue
        if role == "style_only" and not span["text"]:
            continue
        if role == "body_structure":
            assert span["field_id"] == "body.table", "Probe requires table wrapping only"
            continue
        for fragment in span["word_fragments"]:
            resolved = resolve_story_locator(stories, fragment["locator"])
            assert resolved is not None, fragment
            story, element = resolved
            changed_parts.add(story.part_name)
            parents = {id(child): parent for parent in story.root.iter() for child in parent}
            coordinates = {id(p): path for path, p in paragraph_map(story.root).items()}
            while element is not None and element.tag != W + "p":
                element = parents.get(id(element))
            assert element is not None, "Inline mutation must resolve to one original paragraph"
            changed_paragraphs.add((story.part_name, coordinates[id(element)]))

    checked_paragraphs, checked_parts = [], []
    with ZipFile(source) as original, ZipFile(candidate) as actual:
        for name in original.namelist():
            if name not in changed_parts:
                assert original.read(name) == actual.read(name), ("Unselected package part", name)
                checked_parts.append(name)
        for name, story in {story.part_name: story for story in stories.values()}.items():
            output_paragraphs = paragraph_map(ET.fromstring(actual.read(name)))
            for coordinate, paragraph in paragraph_map(story.root).items():
                if (name, coordinate) in changed_paragraphs:
                    continue
                assert coordinate in output_paragraphs, ("Unselected paragraph missing", coordinate)
                assert shape(paragraph) == shape(output_paragraphs[coordinate]), (
                    "Unselected paragraph changed",
                    name,
                    coordinate,
                )
                checked_paragraphs.append({"part": name, "paragraph_path": coordinate})
    return {"paragraphs": checked_paragraphs, "package_parts": checked_parts}


def audit(root, output):
    root, output = root.resolve(), output.resolve()
    assert output != root and root not in output.parents, "Never write into original evidence"
    output.mkdir(parents=True, exist_ok=False)
    original_hashes = run_hashes(root)
    source = root / "input/school-template.docx"
    source_hash = sha256_file(source)
    initial = load_initial_inventory(root, source_hash)
    canonical = CanonicalSourceInventory.from_json(initial["canonical_source_inventory"])
    original_proof = read(root / PROOF_PATH)
    original_units = validate_unit_proof(canonical, original_proof)
    original_inventory, original_review = read(root / INVENTORY_PATH), read(root / REVIEW_PATH)
    require_initial_binding(root, original_inventory)
    assert review_uses_current_semantic_shape(
        inventory=original_inventory,
        review=original_review,
        expected_vocabulary=original_inventory["field_id_vocabulary"],
        expected_document_sha256=source_hash,
    )
    entry = next(item for item in canonical.source_entries if item.source_entry_id == SHARED_ENTRY)
    judgment = next(
        item
        for item in original_review["semantic_judgments"]
        if item["source_entry_id"] == SHARED_ENTRY
    )
    assert [part["role"] for part in judgment["parts"]] == [
        "fixed_label",
        "fill_slot",
        "fixed_label",
        "fill_slot",
    ]
    assert all("/p[" in provenance.locator for provenance in entry.provenance), (
        "Selected entry must be paragraph content, not the table ancestor"
    )
    split_offset = sum(len(part["text"]) for part in judgment["parts"][:2])
    assert "".join(part["text"] for part in judgment["parts"]) == entry.text
    boundary = {
        "source_entry_id": SHARED_ENTRY,
        "edge": "split",
        "before": entry.text[:split_offset],
        "after": entry.text[split_offset:],
    }
    owners = [
        unit
        for unit in original_units
        if any(span["source_entry_id"] == SHARED_ENTRY for span in unit["source_spans"])
    ]
    assert len(owners) == 1, "Expected a previously unsplit real source entry"
    owner = owners[0]
    derived_units = []
    for unit in original_proof["units"]:
        if unit["unit_id"] != owner["unit_id"]:
            derived_units.append(copy.deepcopy(unit))
            continue
        derived_units.extend(
            [
                {
                    **unit,
                    "unit_id": unit["unit_id"] + "-probe-left",
                    "unit_name": "Test-authored mechanical partition: left",
                    "end_boundary": boundary,
                },
                {
                    **unit,
                    "unit_id": unit["unit_id"] + "-probe-right",
                    "unit_name": "Test-authored mechanical partition: right",
                    "start_boundary": boundary,
                },
            ]
        )
    resolved = resolve_unit_partition(canonical, derived_units)
    proof = {
        "schema_version": UNIT_PROOF_SCHEMA,
        "status": "ok",
        "checkpoint": "unit-boundary",
        "source_hash": source_hash,
        "source_inventory_digest": canonical.inventory_digest,
        "unit_projection_digest": sha256_json(resolved),
        "units": derived_units,
        "resolved_units": resolved,
    }
    validate_unit_proof(canonical, proof)
    shared = [
        {"unit_id": unit["unit_id"], **span}
        for unit in resolved
        for span in unit["source_spans"]
        if span["source_entry_id"] == SHARED_ENTRY
    ]
    assert len(shared) == 2 and "".join(span["text"] for span in shared) == entry.text
    assert shared[0]["extent"]["end"] == shared[1]["extent"]["start"] == split_offset

    task = output / "derived-task"
    for relative in (
        Path("input/school-template.docx"),
        Path("input/field-registry.yaml"),
        INITIAL_INVENTORY_PATH,
        MANIFEST_PATH,
    ):
        destination = task / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
    write_json(task / PROOF_PATH, proof)
    prepared = PreparedTemplateTask(
        task_root=task,
        template_path=task / "input/school-template.docx",
        requirements_path=None,
        registry_source=task / "input/field-registry.yaml",
        template_sha256=source_hash,
        requirements_sha256=None,
        registry_sha256=sha256_file(task / "input/field-registry.yaml"),
    )
    projection = _post_unit_inventory_from_checkpoint(prepared, proof)
    harness = TemplateHarnessService(task_root=task)
    inventory_feedback = harness.handle({"action": "submit_object_inventory", **projection})
    assert inventory_feedback["status"] == "ok", inventory_feedback
    inventory = read(task / INVENTORY_PATH)
    assert inventory["source_entries"] == original_inventory["source_entries"]
    assert inventory["canonical_source_inventory"] == initial["canonical_source_inventory"]
    require_initial_binding(task, inventory)
    batch_manifest = build_semantic_batch_manifest(inventory=inventory, checkpoint=proof)
    owners_after = [
        batch for batch in batch_manifest.batches if SHARED_ENTRY in batch.source_entry_ids
    ]
    assert len(owners_after) == 1, "Cross-unit entry acquired multiple semantic batch owners"
    for context in shared:
        packet = inventory["unit_reading_packets"][context["unit_id"]]
        projected_entry = next(
            item for item in packet["source_entries"] if item["source_entry_id"] == SHARED_ENTRY
        )
        assert projected_entry["text"] == entry.text
        assert len(projected_entry["unit_contexts"]) == 2
    write_json(output / "derived-batch-manifest.json", batch_manifest.to_json())

    # Preserve the original Agent payload, including its whitespace transport. The
    # production Harness alone decodes transport and generates accepted spans.
    candidates = read(root / CANDIDATES_PATH)
    raw_judgments = [
        item for batch in candidates["candidates"] for item in batch["semantic_judgments"]
    ]
    raw_digest = sha256_json(raw_judgments)
    write_json(output / "original-agent-judgments.json", raw_judgments)
    feedback = harness.handle(
        {"action": "submit_semantic_judgments", "semantic_judgments": raw_judgments}
    )
    write_json(output / "review-feedback.json", feedback)
    assert feedback["status"] == "ok", feedback
    assert sha256_json(raw_judgments) == raw_digest, "Original Agent payload was mutated"
    review = read(task / REVIEW_PATH)
    assert review["semantic_judgments"] == original_review["semantic_judgments"]
    assert review["resolved_spans"] == original_review["resolved_spans"], (
        "Repartitioning changed accepted identity, extent, or Word fragments"
    )

    writes = []
    with ZipFile(source) as archive:
        stories = read_word_stories(archive)
    entry_order = {
        item.source_entry_id: index for index, item in enumerate(canonical.source_entries)
    }
    for number in (1, 2):
        # Each write starts from the immutable source and reloads persisted proof,
        # inventory, and review; the second is a retry after disk reconstruction.
        initial_again = load_initial_inventory(task, source_hash)
        assert initial_again == initial
        validate_unit_proof(canonical, read(task / PROOF_PATH))
        disk_inventory, disk_review = read(task / INVENTORY_PATH), read(task / REVIEW_PATH)
        require_initial_binding(task, disk_inventory)
        assert review_uses_current_semantic_shape(
            inventory=disk_inventory,
            review=disk_review,
            expected_vocabulary=disk_inventory["field_id_vocabulary"],
            expected_document_sha256=source_hash,
        )
        candidate = output / f"candidate-{number:04d}.docx"
        receipt = materialize_template_from_semantics(
            source_docx=task / "input/school-template.docx",
            output_docx=candidate,
            registry=FieldRegistrySnapshot.load(task / "input/field-registry.yaml"),
            inventory=disk_inventory,
            review=disk_review,
        )
        write_json(output / f"materialization-{number:04d}.json", receipt)
        assert sha256_file(candidate) != source_hash, "Probe must perform an actual DOCX mutation"
        compared_parts = compare_packages(candidate, root / "output/final-template.docx")
        inline = verify_inline_ranges(
            stories, disk_review["resolved_spans"], candidate, entry_order
        )
        selected_inline = verify_inline_ranges(
            stories, judgment["resolved_spans"], candidate, entry_order
        )
        assert len(selected_inline) == 1 and selected_inline[0]["slot_count"] == 2
        untouched = verify_unselected(source, candidate, stories, disk_review["resolved_spans"])
        writes.append(
            {
                "candidate": str(candidate),
                "sha256": sha256_file(candidate),
                "package_parts_equal_original_published_output": compared_parts,
                "selected_original_paragraph": selected_inline,
                "all_verified_inline_paragraphs": inline,
                "unselected": untouched,
            }
        )
    compare_packages(output / "candidate-0001.docx", output / "candidate-0002.docx")
    assert run_hashes(root) == original_hashes, "Original run evidence was changed"
    assert sha256_file(task / "input/school-template.docx") == source_hash
    result = {
        "status": "ok",
        "evidence_level": "logic/contract on real input + actual DOCX mutation",
        "partition_origin": (
            "test-authored mechanical split at an existing real semantic part boundary"
        ),
        "not_claimed": [
            "new E2E agent loop",
            "original Agent partition real replay",
            "product acceptance",
        ],
        "original_root": str(root),
        "derived_root": str(task),
        "source_sha256": source_hash,
        "source_inventory_digest": canonical.inventory_digest,
        "source_entry_id": SHARED_ENTRY,
        "split_offset_harness_computed": split_offset,
        "original_unit_binding": proof_binding(original_proof),
        "derived_unit_binding": proof_binding(proof),
        "shared_spans": shared,
        "original_agent_payload_sha256": raw_digest,
        "original_accepted_semantic_judgments_sha256": original_review["semantic_judgments_sha256"],
        "derived_accepted_semantic_judgments_sha256": review["semantic_judgments_sha256"],
        "accepted_spans_identical": True,
        "initial_source_inventory_unchanged": True,
        "batch_owner": owners_after[0].to_json(),
        "writes": writes,
        "write_retry_package_contents_identical": True,
        "original_evidence_files_unchanged": original_hashes,
    }
    write_json(output / "identity-report.json", result)
    print(
        json.dumps(
            {
                "status": "ok",
                "evidence_level": result["evidence_level"],
                "source_entry_id": SHARED_ENTRY,
                "split_offset": split_offset,
                "actual_writes": len(writes),
                "report": str(output / "identity-report.json"),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=DEFAULT_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Must not exist; original evidence is never overwritten",
    )
    args = parser.parse_args()
    audit(args.root, args.output)

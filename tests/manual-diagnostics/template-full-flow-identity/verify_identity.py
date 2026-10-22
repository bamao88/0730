"""Independent fresh-run identity audit, replay, and unopened-range checks."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import yaml

from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import validate_published_template_artifact
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_entries import CanonicalSourceInventory
from docfit.template.unit_source import (
    load_initial_inventory,
    require_initial_binding,
    validate_unit_proof,
)
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.word_parts import read_word_stories, resolve_story_locator
from docfit.tools.word_xml import visible_word_text

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read(path):
    return json.loads(path.read_text())


def shape(element):
    return (
        element.tag,
        sorted(element.attrib.items()),
        element.text or "",
        [shape(child) for child in element],
    )


def structural_map(root, tags):
    """Independent structural coordinates, treating content-control wrappers as transparent."""
    result = {}

    def children(node):
        for child in node:
            if child.tag == W + "sdt":
                content = child.find(W + "sdtContent")
                assert content is not None, "Malformed content control"
                yield from children(content)
            else:
                yield child

    def visit(node, path):
        if node.tag in {W + tag for tag in tags}:
            assert path not in result
            result[path] = node
        counters = {}
        for child in children(node):
            tag = child.tag.rsplit("}", 1)[-1]
            counters[tag] = counters.get(tag, 0) + 1
            visit(child, f"{path}/{tag}[{counters[tag]}]")

    visit(root, root.tag.rsplit("}", 1)[-1])
    return result


def paragraph_map(root):
    return structural_map(root, {"p"})


def verify_table_slots(stories, spans, final):
    """Check table slot placement independently of the materializer's receipts."""
    checked = []
    with ZipFile(final) as archive:
        for span in spans:
            if span["role"] != "body_structure":
                continue
            assert span["field_id"] == "body.table", "Unverified structure kind"
            assert len(span["word_fragments"]) == 1, "Unverified composite table span"
            story, original = resolve_story_locator(stories, span["word_fragments"][0]["locator"])
            assert original.tag == W + "tbl"
            paths = structural_map(story.root, {"tbl"})
            path = next(key for key, node in paths.items() if node is original)
            final_root = ET.fromstring(archive.read(story.part_name))
            tables = structural_map(final_root, {"tbl"})
            assert path in tables, "Selected table missing at its original structural position"
            table = tables[path]
            parents = {id(child): parent for parent in final_root.iter() for child in parent}
            content = parents[id(table)]
            assert content.tag == W + "sdtContent" and list(content) == [table]
            control = parents[id(content)]
            tag = control.find(W + "sdtPr/" + W + "tag")
            assert tag is not None and tag.get(W + "val") == span["slot_ref"], (
                "Table slot moved to a different original object"
            )

            # Wrapping a table does not authorize changing its grid or cell structure.
            def skeleton(node):
                result = copy.deepcopy(node)
                for parent in list(result.iter()):
                    for child in list(parent):
                        if child.tag == W + "p":
                            parent.remove(child)
                return shape(result)

            assert skeleton(original) == skeleton(table), "Table structure changed"
            checked.append(
                {
                    "source_entry_id": span["source_entry_id"],
                    "slot_ref": span["slot_ref"],
                    "part": story.part_name,
                    "table_path": path,
                }
            )
    return checked


def verify_inline_ranges(stories, spans, final, entry_order):
    """Verify fixed text within mutated paragraphs, replacing controls with identity tokens."""
    grouped = {}
    original_paragraphs = {}
    for span in spans:
        carriers = {}
        for fragment in span["word_fragments"]:
            story, element = resolve_story_locator(stories, fragment["locator"])
            parents = {id(child): parent for parent in story.root.iter() for child in parent}
            while element is not None and element.tag != W + "p":
                element = parents.get(id(element))
            if element is not None:
                paths = {id(p): path for path, p in paragraph_map(story.root).items()}
                key = (story.part_name, paths[id(element)])
                carriers[key] = element
        if len(carriers) != 1:
            assert span["role"] != "fill_slot", "Cannot independently verify slot paragraph"
            continue
        key, paragraph = next(iter(carriers.items()))
        grouped.setdefault(key, []).append(span)
        original_paragraphs[key] = paragraph
    checked = []
    with ZipFile(final) as archive:
        for (part_name, pid), parts in grouped.items():
            if not any(
                part["role"] == "fill_slot"
                or (part["role"] in {"cleanup", "style_only"} and part["text"])
                for part in parts
            ):
                continue
            parts.sort(key=lambda part: (entry_order[part["source_entry_id"]], part["part_index"]))
            assert "".join(part["text"] for part in parts) == visible_word_text(
                original_paragraphs[(part_name, pid)]
            ), "Accepted parts do not cover exact original paragraph for independent verification"
            root = ET.fromstring(archive.read(part_name))
            matches = [p for path, p in paragraph_map(root).items() if path == pid]
            assert len(matches) == 1, ("Modified original paragraph missing", part_name, pid)
            paragraph = copy.deepcopy(matches[0])
            expected = ""
            slot_refs = set()
            for part in parts:
                if part["role"] == "fill_slot":
                    slot_refs.add(part["slot_ref"])
                    expected += "\ue000" + part["slot_ref"] + "\ue001"
                elif part["role"] not in {"cleanup", "style_only"}:
                    expected += part["text"]
            found = set()
            for control in paragraph.iter(W + "sdt"):
                tag = control.find(W + "sdtPr/" + W + "tag")
                ref = tag.get(W + "val") if tag is not None else None
                if ref not in slot_refs:
                    continue
                found.add(ref)
                content = control.find(W + "sdtContent")
                assert content is not None
                content.clear()
                ET.SubElement(ET.SubElement(content, W + "r"), W + "t").text = (
                    "\ue000" + ref + "\ue001"
                )
            assert found == slot_refs, "Output slots are not on their original paragraph"
            assert visible_word_text(paragraph) == expected, (
                "Unselected text or slot order changed within selected paragraph",
                part_name,
                pid,
            )
            checked.append({"part": part_name, "paragraph_path": pid, "slot_count": len(slot_refs)})
    return checked


def audit(root: Path, output: Path):
    source = root / "input/school-template.docx"
    initial = load_initial_inventory(root, sha256_file(source))
    canonical = CanonicalSourceInventory.from_json(initial["canonical_source_inventory"])
    proof = read(root / "work/.docfit/unit-boundary-checkpoint.json")
    units = validate_unit_proof(canonical, proof)
    inventory = read(root / "work/.docfit/harness/object-inventory.json")
    require_initial_binding(root, inventory)
    review = read(root / "work/.docfit/harness/semantic-judgments.json")
    assert review_uses_current_semantic_shape(
        review=review, inventory=inventory, expected_vocabulary=inventory["field_id_vocabulary"]
    )
    spans = review["resolved_spans"]
    entry_ids = {entry.source_entry_id for entry in canonical.source_entries}
    assert {span["source_entry_id"] for span in spans} == entry_ids
    final = root / "output/final-template.docx"
    contract = yaml.safe_load((root / "output/fill-contract.yaml").read_text())
    artifact = validate_published_template_artifact(template_docx=final, fill_contract=contract)
    registry = FieldRegistrySnapshot.load(root / "input/field-registry.yaml")
    replay_dir = output.parent / (root.name + "-replay")
    replay_dir.mkdir(parents=True, exist_ok=True)
    replay_doc = replay_dir / "candidate.docx"
    source_noop = sha256_file(source) == sha256_file(final)
    if source_noop:
        assert not contract["slots"], "A source-noop must not claim new slots"
        shutil.copyfile(source, replay_doc)
        materialization = {"status": "source_noop", "actual_mutation_verified": False}
    else:
        materialization = materialize_template_from_semantics(
            source_docx=source,
            output_docx=replay_doc,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    (replay_dir / "materialization.json").write_text(
        json.dumps(materialization, ensure_ascii=False, indent=2) + "\n"
    )
    with ZipFile(replay_doc) as replay, ZipFile(final) as published:
        assert set(replay.namelist()) == set(published.namelist())
        for name in replay.namelist():
            a, b = replay.read(name), published.read(name)
            if name.endswith(".xml"):
                assert shape(ET.fromstring(a)) == shape(ET.fromstring(b)), ("replay differs", name)
            else:
                assert a == b, ("replay differs", name)
    with ZipFile(source) as archive:
        stories = read_word_stories(archive)
    affected: set[tuple[str, str]] = set()
    affected_parts: set[str] = set()
    mutation_roles = {"fill_slot", "body_structure", "cleanup", "generated_content", "style_only"}
    for span in spans:
        if span.get("role") not in mutation_roles:
            continue
        # Empty style-only structural entries carry no mutation.
        if span.get("role") == "style_only" and not span.get("text"):
            continue
        for fragment in span["word_fragments"]:
            resolved = resolve_story_locator(stories, fragment["locator"])
            assert resolved is not None, ("missing actual source target", fragment)
            story, element = resolved
            affected_parts.add(story.part_name)
            if span["role"] == "body_structure" and element.tag == W + "tbl":
                # A table wrapper is checked separately; its unselected children stay protected.
                continue
            parents = {id(child): parent for parent in story.root.iter() for child in parent}
            paths = {id(p): path for path, p in paragraph_map(story.root).items()}
            for paragraph in element.iter(W + "p"):
                affected.add((story.part_name, paths[id(paragraph)]))
            parent = element
            while parent is not None:
                if parent.tag == W + "p":
                    affected.add((story.part_name, paths[id(parent)]))
                parent = parents.get(id(parent))
    checked = []
    unchanged_parts = []
    unique_stories = {story.part_name: story for story in stories.values()}
    with ZipFile(source) as original, ZipFile(final) as published:
        for name in original.namelist():
            if name not in affected_parts:
                # Main document serialization can alter prefixes without changing its tree.
                if name == "word/document.xml":
                    assert shape(ET.fromstring(original.read(name))) == shape(
                        ET.fromstring(published.read(name))
                    )
                else:
                    assert original.read(name) == published.read(name), (
                        "unselected part changed",
                        name,
                    )
                unchanged_parts.append(name)
        for name, story in unique_stories.items():
            final_tree = ET.fromstring(published.read(name))
            final_by_path = paragraph_map(final_tree)
            for path, paragraph in paragraph_map(story.root).items():
                if (name, path) in affected:
                    continue
                assert path in final_by_path, ("unselected paragraph missing", name, path)
                assert shape(final_by_path[path]) == shape(paragraph), (
                    "unselected paragraph changed",
                    name,
                    path,
                )
                checked.append({"part": name, "paragraph_path": path})
    inline_ranges = (
        verify_inline_ranges(
            stories,
            spans,
            final,
            {entry.source_entry_id: index for index, entry in enumerate(canonical.source_entries)},
        )
        if not source_noop
        else []
    )
    table_slots = verify_table_slots(stories, spans, final) if not source_noop else []
    rejected = []
    old = copy.deepcopy(proof)
    old["schema_version"] = 1
    corrupt = copy.deepcopy(proof)
    span = next(
        s
        for u in corrupt["resolved_units"]
        for s in u["source_spans"]
        if s["extent"]["kind"] == "text"
    )
    span["extent"]["start"] += 1
    corrupt["unit_projection_digest"] = sha256_json(corrupt["resolved_units"])
    for name, value in [("old_proof", old), ("changed_extent_rehashed", corrupt)]:
        try:
            validate_unit_proof(canonical, value)
        except ValueError:
            rejected.append(name)
        else:
            raise AssertionError(("corrupt proof accepted", name))
    result = {
        "root": str(root),
        "source_sha256": sha256_file(source),
        "initial_inventory_digest": canonical.inventory_digest,
        "unit_count": len(units),
        "source_entry_count": len(entry_ids),
        "span_count": len(spans),
        "slot_count": len(contract["slots"]),
        "artifact_check": artifact,
        "replay": "source_noop_preservation" if source_noop else "actual_mutation_ok",
        "replay_output_sha256": sha256_file(replay_doc),
        "untouched_paragraphs": checked,
        "verified_inline_slot_paragraphs": [row for row in inline_ranges if row["slot_count"]],
        "verified_non_slot_cleanup_paragraphs": [
            row for row in inline_ranges if not row["slot_count"]
        ],
        "verified_table_slots": table_slots,
        "unchanged_package_parts": unchanged_parts,
        "negative_rejections": rejected,
        "scope": "source identity and actual Word ranges; no school semantic or visual acceptance",
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if not isinstance(v, (dict, list))}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.root.resolve(), args.output)

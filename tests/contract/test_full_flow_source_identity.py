from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from docfit.app.prepare_template import (
    PrepareTemplateRequest,
    _ensure_post_unit_inventory,
    _validate_unit_boundary_checkpoint,
    prepare_template_task,
)
from docfit.template.source_entries import (
    CanonicalSourceEntry,
    build_canonical_source_inventory,
)
from docfit.template.source_spans import (
    SourceSpan,
    SourceSpanResolutionError,
    TextSourceExtent,
    WholeEntrySourceExtent,
    resolve_semantic_judgments,
    resolve_source_span,
)
from docfit.template.unit_source import (
    INITIAL_INVENTORY_PATH,
    UnitPartitionError,
    load_initial_inventory,
    resolve_unit_partition,
    validate_inventory_partition,
    validate_unit_proof,
)
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file, sha256_json
from docfit.tools.service import DocFitToolService
from tests.contract.test_template_materialization_runtime import _write_docx_from_paragraph_xml
from tests.support.source_identity import persist_source_identity, source_partition


def _objects(source_hash: str) -> list[dict]:
    return [
        {
            "type": "paragraph",
            "text": text,
            "locator": f"/body/p[{i}]",
            "object_ref": {"object_id": f"p{i}", "document_sha256": source_hash},
        }
        for i, text in enumerate(("same", "same", "alpha beta", ""), 1)
    ]


def _fixture(tmp_path: Path):
    source = tmp_path / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    _write_docx_from_paragraph_xml(source, ["<w:p/>"])
    source_hash = sha256_file(source)
    objects = _objects(source_hash)
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=objects,
    )
    inventory = {"document_sha256": source_hash, "canonical_source_inventory": canonical.to_json()}
    ids = [entry.source_entry_id for entry in canonical.source_entries]
    split = {"source_entry_id": ids[2], "edge": "split", "before": "alpha", "after": " beta"}
    units = [
        {
            "unit_id": "a",
            "unit_name": "first",
            "start_boundary": {"source_entry_id": ids[0], "edge": "start"},
            "end_boundary": dict(split),
        },
        {
            "unit_id": "b",
            "unit_name": "second",
            "start_boundary": split,
            "end_boundary": {"source_entry_id": ids[-1], "edge": "end"},
        },
    ]
    proof = source_partition(inventory, units=units)
    persist_source_identity(tmp_path, inventory, objects=objects)
    return canonical, inventory, proof


def test_exact_partition_keeps_shared_entry_identity_and_word_fragments(tmp_path):
    canonical, inventory, proof = _fixture(tmp_path)
    units = validate_unit_proof(canonical, proof)
    first, second = units[0]["source_spans"][-1], units[1]["source_spans"][0]
    assert first["source_entry_id"] == second["source_entry_id"]
    assert first["text"] == "alpha" and second["text"] == " beta"
    assert first["word_fragments"][0]["object_text_end"] == 5
    assert second["word_fragments"][0]["object_text_start"] == 5
    assert (
        canonical.source_entries[0].source_entry_id != canonical.source_entries[1].source_entry_id
    )
    judgments = [
        {
            "source_entry_id": entry.source_entry_id,
            "parts": [
                {"text": part, "role": "fixed_label"}
                for part in (["alpha", " beta"] if entry.text == "alpha beta" else [entry.text])
            ],
        }
        for entry in canonical.source_entries
    ]
    spans = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    assert len(spans) == 5
    judgments[2]["parts"] = [{"text": "alpha beta", "role": "fixed_label"}]
    with pytest.raises(SourceSpanResolutionError) as error:
        resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    assert error.value.blockers[0]["code"] == "ordered_part_crosses_unit_cut"


def test_auxiliary_stories_are_covered_without_becoming_body_units():
    story_paths = (
        "/body/p[1]", "/body/p[2]", "/header[1]/p[1]",
        "/footer[1]/p[1]", "/header[2]/p[1]",
        "/footnote[1]/p[1]", "/endnote[1]/p[1]",
    )
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[
            {"type": "paragraph", "text": f"entry {index}", "locator": locator,
             "object_ref": {"object_id": f"p{index}"}}
            for index, locator in enumerate(story_paths, 1)
        ],
    )
    entries = canonical.source_entries
    inventory = {"document_sha256": "a" * 64, "canonical_source_inventory": canonical.to_json()}
    proof = source_partition(inventory, units=[{
        "unit_id": "paper", "unit_name": "正文",
        "start_boundary": {"source_entry_id": entries[0].source_entry_id, "edge": "start"},
        "end_boundary": {"source_entry_id": entries[1].source_entry_id, "edge": "end"},
    }])
    assert len(proof["resolved_body_units"]) == 1
    assert len(proof["resolved_body_units"][0]["source_spans"]) == 2
    assert {scope["story_kind"] for scope in proof["auxiliary_scopes"]} == {
        "header", "footer", "footnote", "endnote",
    }
    header = next(scope for scope in proof["auxiliary_scopes"] if scope["story_kind"] == "header")
    assert len(header["source_spans"]) == 2
    assert len(header["story_regions"]) == 2
    assert len({span["source_entry_id"] for scope in proof["resolved_units"]
                for span in scope["source_spans"]}) == len(entries)
    assert validate_inventory_partition(inventory) == proof["resolved_units"]
    wrong_endpoint = deepcopy(proof["units"])
    wrong_endpoint[0]["end_boundary"] = {
        "source_entry_id": entries[2].source_entry_id, "edge": "start",
    }
    with pytest.raises(UnitPartitionError) as boundary_error:
        resolve_unit_partition(canonical, wrong_endpoint)
    assert "header entry outside the body" in boundary_error.value.blockers[0]["message"]
    assert boundary_error.value.blockers[0]["source_entries"][0]["source_entry_id"] == (
        entries[2].source_entry_id
    )
    tampered = deepcopy(proof)
    tampered["auxiliary_scopes"] = []
    with pytest.raises(ValueError, match="auxiliary projections"):
        validate_unit_proof(canonical, tampered)
    with pytest.raises(ValueError, match="current initial"):
        validate_unit_proof(canonical, {**proof, "schema_version": "docfit-unit-boundary-proof/v2"})


def test_partition_projection_matches_full_inventory_resolution(tmp_path):
    canonical, inventory, proof = _fixture(tmp_path)
    for unit in resolve_unit_partition(canonical, proof["units"]):
        for span in unit["source_spans"]:
            raw_extent = span["extent"]
            extent = (
                TextSourceExtent(raw_extent["start"], raw_extent["end"])
                if raw_extent["kind"] == "text"
                else WholeEntrySourceExtent()
            )
            expected = resolve_source_span(
                inventory=inventory,
                source_span=SourceSpan(span["source_entry_id"], extent),
            )
            assert span["text"] == expected.expected_source_content
            assert span["word_fragments"] == [item.to_json() for item in expected.word_fragments]
            assert expected.inventory_digest == canonical.inventory_digest


@pytest.mark.parametrize("entry_count", [8, 32])
def test_partition_entry_parsing_scales_linearly(entry_count, monkeypatch):
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[
            {
                "type": "paragraph", "text": f"text {index}",
                "locator": f"/body/p[{index + 1}]",
                "object_ref": {"object_id": f"p{index}", "document_sha256": "a" * 64},
            }
            for index in range(entry_count)
        ],
    )
    calls = 0
    original = CanonicalSourceEntry.from_json

    def counted(cls, value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(CanonicalSourceEntry, "from_json", classmethod(counted))
    resolved = resolve_unit_partition(canonical, [{
        "unit_id": "all", "unit_name": "All",
        "start_boundary": {"source_entry_id": canonical.source_entries[0].source_entry_id,
                           "edge": "start"},
        "end_boundary": {"source_entry_id": canonical.source_entries[-1].source_entry_id,
                         "edge": "end"},
    }])
    assert len(resolved[0]["source_spans"]) == entry_count
    # An operation-count bound avoids timing noise while rejecting the former
    # repeated full-inventory parsing for each individual source entry.
    assert calls <= 4 * entry_count


@pytest.mark.parametrize("mutation", [
    lambda canonical: replace(canonical, inventory_digest="b" * 64),
    lambda canonical: replace(canonical, source_snapshot_sha256="c" * 64),
    lambda canonical: replace(canonical, source_entries=(
        replace(canonical.source_entries[0], text="else"), *canonical.source_entries[1:],
    )),
])
def test_partition_revalidates_complete_binding_on_every_call(tmp_path, mutation):
    canonical, _, proof = _fixture(tmp_path)
    assert resolve_unit_partition(canonical, proof["units"]) == proof["resolved_units"]
    with pytest.raises(ValueError):
        resolve_unit_partition(mutation(canonical), proof["units"])
    assert resolve_unit_partition(canonical, proof["units"]) == proof["resolved_units"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda u: u[0].update(start_locator="/body/p[1]"),
        lambda u: u[0]["start_boundary"].update(seen_text="same"),
        lambda u: u[0]["start_boundary"].update(source_entry_id="absent"),
        lambda u: u[0]["start_boundary"].update(
            source_entry_id=u[0]["end_boundary"]["source_entry_id"]
        ),
        lambda u: u[1]["start_boundary"].update(before="alph", after="a beta"),
        lambda u: u[1]["start_boundary"].update(before="alpha ", after="beta"),
        lambda u: u[0]["end_boundary"].update(before="ALPHA"),
        lambda u: u.reverse(),
        lambda u: u.pop(),
        lambda u: u[0]["start_boundary"].update(edge="end"),
    ],
)
def test_boundaries_fail_closed_for_old_protocol_gap_overlap_order_and_wrong_entry(
    tmp_path, mutation
):
    canonical, _, proof = _fixture(tmp_path)
    units = deepcopy(proof["units"])
    mutation(units)
    with pytest.raises(ValueError):
        resolve_unit_partition(canonical, units)


def test_recomputed_digest_does_not_authorize_swapped_offsets(tmp_path):
    canonical, _, proof = _fixture(tmp_path)
    tampered = deepcopy(proof)
    span = tampered["resolved_units"][0]["source_spans"][-1]
    span["extent"] = {"kind": "text", "start": 5, "end": 10}
    tampered["unit_projection_digest"] = sha256_json(tampered["resolved_units"])
    with pytest.raises(ValueError, match="exact source boundary"):
        validate_unit_proof(canonical, tampered)
    tampered = {**proof, "schema_version": 1}
    with pytest.raises(ValueError, match="current initial"):
        validate_unit_proof(canonical, tampered)


def test_tool_uses_initial_inventory_across_windows_and_retries(tmp_path):
    canonical, _, proof = _fixture(tmp_path)
    service = DocFitToolService(task_root=tmp_path)
    seen = []
    for offset in range(4):
        card = service.evidence({"focus": "document_map", "offset": offset, "limit": 1})
        entry = card["summary"]["source_entries"][0]
        assert (
            entry
            == service.evidence({"focus": "document_map", "offset": offset, "limit": 1})["summary"][
                "source_entries"
            ][0]
        )
        seen.append(entry["source_entry_id"])
    assert seen == [entry.source_entry_id for entry in canonical.source_entries]
    result = service.check({"check": "unit_coverage", "payload": {"units": proof["units"]}})
    assert result["status"] == "ok"
    result = service.check(
        {"check": "unit_coverage", "payload": {"units": proof["resolved_units"]}}
    )
    assert result["status"] == "needs_input"


def test_inventory_source_staleness_and_missing_initial_ledger_rejected(tmp_path):
    _, inventory, _ = _fixture(tmp_path)
    (tmp_path / "input/school-template.docx").write_bytes(b"changed source")
    with pytest.raises(ToolFailure):
        load_initial_inventory(tmp_path, inventory["document_sha256"])
    (tmp_path / INITIAL_INVENTORY_PATH).unlink()
    with pytest.raises(ToolFailure):
        load_initial_inventory(tmp_path, inventory["document_sha256"])


def test_prepare_persists_inventory_before_checkpoint_and_never_reinspects(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    _write_docx_from_paragraph_xml(source, [
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        for text in ("same", "same", "alpha beta", "")
    ])
    calls = []

    def inspect(_service, args):
        calls.append(args)
        return {"objects": _objects(sha256_file(source))}

    monkeypatch.setattr(DocFitToolService, "inspect", inspect)
    prepared = prepare_template_task(
        PrepareTemplateRequest(
            school_template=source,
            output_directory=tmp_path / "task",
        )
    )
    assert len(calls) == 1
    initial_bytes = (prepared.task_root / INITIAL_INVENTORY_PATH).read_bytes()
    initial = load_initial_inventory(prepared.task_root, prepared.template_sha256)
    inventory = {
        "document_sha256": prepared.template_sha256,
        "canonical_source_inventory": initial["canonical_source_inventory"],
    }
    proof = source_partition(inventory)
    atomic_write_json(prepared.task_root / "work/.docfit/unit-boundary-checkpoint.json", proof)
    monkeypatch.setattr(
        DocFitToolService, "inspect", lambda *_: pytest.fail("reinspection forbidden")
    )
    first = _ensure_post_unit_inventory(prepared, proof)
    second = _ensure_post_unit_inventory(prepared, proof)
    assert first["canonical_source_inventory"] == second["canonical_source_inventory"]
    assert (prepared.task_root / INITIAL_INVENTORY_PATH).read_bytes() == initial_bytes
    assert _validate_unit_boundary_checkpoint(prepared, proof) == proof
    assert (
        prepare_template_task(
            PrepareTemplateRequest(
                school_template=source,
                output_directory=prepared.task_root,
            )
        )
        == prepared
    )


def test_shared_entry_has_one_batch_owner_and_all_unit_contexts(tmp_path):
    from docfit.template.semantic_batches import build_semantic_batch_manifest
    from tests.support.source_identity import context_packets

    canonical, inventory, proof = _fixture(tmp_path)
    inventory["field_vocabulary_digest"] = "a" * 64
    inventory["unit_reading_packets"] = context_packets(inventory)
    shared_id = canonical.source_entries[2].source_entry_id
    for limit in (1, 2, 64):
        manifest = build_semantic_batch_manifest(
            inventory=inventory,
            checkpoint=proof,
            max_entries_per_batch=limit,
        )
        assigned = [entry_id for batch in manifest.batches for entry_id in batch.source_entry_ids]
        assert len(assigned) == len(set(assigned)) == len(canonical.source_entries)
        assert set(assigned) == {entry.source_entry_id for entry in canonical.source_entries}
        owner = next(batch for batch in manifest.batches if shared_id in batch.source_entry_ids)
        packet = inventory["unit_reading_packets"][owner.unit_id]
        entry = next(
            entry for entry in packet["source_entries"] if entry["source_entry_id"] == shared_id
        )
        assert entry["text"] == "alpha beta"
        assert [context["text"] for context in entry["unit_contexts"]] == ["alpha", " beta"]
    with pytest.raises(ValueError, match="current initial"):
        build_semantic_batch_manifest(
            inventory=inventory, checkpoint={**proof, "schema_version": 1}
        )
    packet = inventory["unit_reading_packets"]["a"]
    packet["source_entries"][-1]["text"] = "alpha"
    with pytest.raises(ValueError, match="complete source entry"):
        build_semantic_batch_manifest(inventory=inventory, checkpoint=proof)
    inventory["unit_reading_packets"] = context_packets(inventory)
    inventory["unit_reading_packets"]["a"]["source_entries"].pop()
    with pytest.raises(ValueError, match="accepted unit range"):
        build_semantic_batch_manifest(inventory=inventory, checkpoint=proof)


def test_initial_manifest_binding_rejects_rebuilt_inventory_even_with_new_digests(tmp_path):
    canonical, inventory, _ = _fixture(tmp_path)
    atomic_write_json(
        tmp_path / "work/.docfit/prepare-template-task.json",
        {
            "source_inventory_digest": canonical.inventory_digest,
        },
    )
    objects = _objects(inventory["document_sha256"])
    objects[2]["text"] = "new text"
    replacement = build_canonical_source_inventory(
        source_snapshot_sha256=inventory["document_sha256"],
        inspected_objects=objects,
    )
    initial = load_initial_inventory(tmp_path, inventory["document_sha256"])
    initial["canonical_source_inventory"] = replacement.to_json()
    initial["objects"] = objects
    initial["mapping_digest"] = sha256_json(objects)
    atomic_write_json(tmp_path / INITIAL_INVENTORY_PATH, initial)
    with pytest.raises(ToolFailure, match="immutable initial"):
        load_initial_inventory(tmp_path, inventory["document_sha256"])


def test_unit_packet_rejects_clipped_context_and_old_tool_checkpoint(tmp_path):
    from tests.support.source_identity import context_packets

    _, inventory, proof = _fixture(tmp_path)
    inventory["unit_reading_packets"] = context_packets(inventory)
    inventory["unit_reading_packets"]["a"]["source_entries"][-1]["unit_contexts"].pop()
    atomic_write_json(tmp_path / "work/.docfit/harness/object-inventory.json", inventory)
    service = DocFitToolService(task_root=tmp_path)
    with pytest.raises(ToolFailure, match="cross-unit context"):
        service.evidence({"focus": "unit_evidence_packet", "unit_id": "a"})
    proof["schema_version"] = 1
    atomic_write_json(tmp_path / "work/.docfit/unit-boundary-checkpoint.json", proof)
    with pytest.raises(ToolFailure, match="initial source inventory"):
        service.evidence({"focus": "unit_evidence_packet", "unit_id": "a"})


def test_missing_manifest_cannot_authorize_rehashed_initial_inventory(tmp_path):
    _, inventory, _ = _fixture(tmp_path)
    (tmp_path / "work/.docfit/prepare-template-task.json").unlink()
    with pytest.raises(ToolFailure, match="immutable initial"):
        load_initial_inventory(tmp_path, inventory["document_sha256"])

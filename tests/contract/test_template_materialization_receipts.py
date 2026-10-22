from __future__ import annotations

import copy
import zipfile
from pathlib import Path

import pytest

from docfit.content.placement import build_placement
from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import validate_published_template_artifact
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from tests.support.source_identity import source_partition

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_docx(path: Path, *, slot_ref: str | None = None, field_id: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if slot_ref is None:
        body = "<w:p><w:r><w:t>fixed</w:t></w:r></w:p>"
    else:
        body = (
            "<w:sdt><w:sdtPr>"
            f'<w:alias w:val="{field_id}"/><w:tag w:val="{slot_ref}"/>'
            "</w:sdtPr><w:sdtContent><w:p><w:r><w:t>value</w:t></w:r></w:p>"
            "</w:sdtContent></w:sdt>"
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document)


def _write_registry(path: Path) -> FieldRegistrySnapshot:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _contract(
    template: Path,
    registry: FieldRegistrySnapshot,
    *,
    with_slot: bool,
    source_hash: str = "1" * 64,
) -> dict[str, object]:
    template_hash = sha256_file(template)
    inventory_digest = "2" * 64
    semantic_digest = "3" * 64
    vocabulary_digest = "4" * 64
    slot_ref = (
        "source_entry_id=source-entry-1;extent=text[0:5];"
        f"source_snapshot_sha256={source_hash};field_id=thesis.title.zh"
    )
    span_ref = slot_ref.rsplit(";field_id=", 1)[0]
    fingerprint = "9" * 64
    word_fragment: dict[str, object] = {
        "object_id": "object-1",
        "object_ref": {
            "document_sha256": source_hash,
            "expected_fingerprint": fingerprint,
            "object_id": "object-1",
        },
        "locator": "/body/sdt[1]/p[1]/r[1]",
        "text": "value",
        "fingerprint": fingerprint,
        "source_text_start": 0,
        "source_text_end": 5,
        "object_text_start": 0,
        "object_text_end": 5,
    }
    partition = {
        "document_sha256": source_hash,
        "source_entries": [
            {
                "source_entry_id": "source-entry-1",
                "text": "value",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "object-1",
                        "object_ref": word_fragment["object_ref"],
                        "locator": word_fragment["locator"],
                        "fingerprint": fingerprint,
                        "text_span": [0, 5],
                    }
                ],
            }
        ],
    }
    source_partition(partition)
    inventory_digest = partition["canonical_source_inventory"]["inventory_digest"]
    accepted_span: dict[str, object] = {
        "span_ref": span_ref,
        "scope": {"source_entry_id": "source-entry-1"},
        "source_entry_id": "source-entry-1",
        "source_snapshot_sha256": source_hash,
        "source_inventory_digest": inventory_digest,
        "part_index": 0,
        "role": "fill_slot",
        "text": "value",
        "expected_source_content": "value",
        "field_id": "thesis.title.zh",
        "slot_ref": slot_ref,
        "extent": {"kind": "text", "start": 0, "end": 5},
        "text_start": 0,
        "text_end": 5,
        "word_fragments": [word_fragment],
        "covered_object_ids": ["object-1"],
    }
    slot_provenance: dict[str, object] = {
        "field_id": "thesis.title.zh",
        "span_ref": span_ref,
        "slot_ref": slot_ref,
        "source_entry_id": "source-entry-1",
        "source_snapshot_sha256": source_hash,
        "source_inventory_digest": inventory_digest,
        "expected_source_content": "value",
        "word_fragments": [word_fragment],
        "accepted_span": accepted_span,
        "accepted_result": {
            "source_judgment_ref": "semantic_judgments[0]",
            "part_index": 0,
            "semantic_judgments_sha256": semantic_digest,
            "field_vocabulary_digest": vocabulary_digest,
        },
        "actual_result": {
            "outcome": "applied",
            "candidate_before_sha256": source_hash,
            "candidate_after_sha256": template_hash,
            "operation_sha256": "5" * 64,
            "mutation_receipt_sha256": "6" * 64,
        },
    }
    phase6: dict[str, object] = {
        "schema_version": "docfit-template-materialization-provenance/v1",
        "source_sha256": source_hash,
        "source_partition": partition,
        "unit_projection_digest": partition["unit_projection_digest"],
        "template_sha256": template_hash,
        "source_inventory_digest": inventory_digest,
        "semantic_judgments_sha256": semantic_digest,
        "field_vocabulary_digest": vocabulary_digest,
        "field_registry_ref": registry.identity(),
        "materialization_receipt_sha256": "7" * 64,
        "slots": [slot_provenance] if with_slot else [],
    }
    slots: list[dict[str, object]] = []
    if with_slot:
        slots.append(
            {
                "slot_ref": slot_ref,
                "span_ref": span_ref,
                "field_id": "thesis.title.zh",
                "locator": {"type": "content_control_tag", "value": slot_ref},
                "provenance": slot_provenance,
            }
        )
    empty_style_digest = sha256_json(
        {
            "schema_version": "docfit-template-fill-contract/v2",
            "template_sha256": template_hash,
            "styles": [],
        }
    )
    return {
        "schema_version": "docfit-template-fill-contract/v2",
        "contract_id": "contract-1",
        "revision": "1",
        "status": "accepted",
        "template_sha256": template_hash,
        "field_registry_ref": registry.identity(),
        "slots": slots,
        "regions": [],
        "styles": [],
        "style_contract_set_digest": empty_style_digest,
        "provenance": {
            "materialization": phase6,
            "materialization_digest": sha256_json(phase6),
        },
    }


def test_persisted_artifact_contract_traces_slot_to_actual_word_result(
    tmp_path: Path,
) -> None:
    registry = _write_registry(tmp_path / "registry.yaml")
    source_hash = "1" * 64
    slot_ref = (
        "source_entry_id=source-entry-1;extent=text[0:5];"
        f"source_snapshot_sha256={source_hash};field_id=thesis.title.zh"
    )
    template = tmp_path / "final-template.docx"
    _write_docx(template, slot_ref=slot_ref, field_id="thesis.title.zh")
    contract = _contract(template, registry, with_slot=True)

    phase6 = validate_published_template_artifact(
        template_docx=template,
        fill_contract=contract,
    )

    assert phase6["slots"][0]["source_entry_id"] == "source-entry-1"  # type: ignore[index]
    assert phase6["slots"][0]["word_fragments"][0]["text"] == "value"  # type: ignore[index]
    assert phase6["slots"][0]["actual_result"]["candidate_after_sha256"] == (  # type: ignore[index]
        sha256_file(template)
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "legacy",
        "legacy_span",
        "wrong_word",
        "wrong_slot",
        "wrong_span",
        "wrong_source_entry",
        "wrong_fragments",
        "wrong_actual",
        "wrong_receipt",
    ),
)
def test_persisted_artifact_contract_rejects_legacy_and_mismatched_packages(
    tmp_path: Path,
    mutation: str,
) -> None:
    registry = _write_registry(tmp_path / "registry.yaml")
    source_hash = "1" * 64
    slot_ref = (
        "source_entry_id=source-entry-1;extent=text[0:5];"
        f"source_snapshot_sha256={source_hash};field_id=thesis.title.zh"
    )
    template = tmp_path / "final-template.docx"
    _write_docx(template, slot_ref=slot_ref, field_id="thesis.title.zh")
    contract = _contract(template, registry, with_slot=True)
    contract["contract_sha256"] = "8" * 64
    receipt: dict[str, object] = {
        "schema_version": 2,
        "template_sha256": sha256_file(template),
        "fill_contract_sha256": "8" * 64,
        "materialization_digest": contract["provenance"]["materialization_digest"],  # type: ignore[index]
    }
    if mutation == "legacy":
        contract["provenance"] = {}
    elif mutation == "legacy_span":
        legacy_span_ref = (
            "reading_block_id=cover:block-0001;extent=text[0:5];"
            f"source_snapshot_sha256={source_hash}"
        )
        legacy_slot_ref = f"{legacy_span_ref};field_id=thesis.title.zh"
        slot = contract["slots"][0]  # type: ignore[index]
        provenance = slot["provenance"]  # type: ignore[index]
        slot["slot_ref"] = legacy_slot_ref  # type: ignore[index]
        slot["span_ref"] = legacy_span_ref  # type: ignore[index]
        slot["locator"]["value"] = legacy_slot_ref  # type: ignore[index]
        provenance["slot_ref"] = legacy_slot_ref  # type: ignore[index]
        provenance["span_ref"] = legacy_span_ref  # type: ignore[index]
        provenance["accepted_span"]["slot_ref"] = legacy_slot_ref  # type: ignore[index]
        provenance["accepted_span"]["span_ref"] = legacy_span_ref  # type: ignore[index]
        phase6 = contract["provenance"]["materialization"]  # type: ignore[index]
        digest = sha256_json(phase6)
        contract["provenance"]["materialization_digest"] = digest  # type: ignore[index]
        receipt["materialization_digest"] = digest
        _write_docx(template, slot_ref=legacy_slot_ref, field_id="thesis.title.zh")
    elif mutation == "wrong_word":
        _write_docx(template)
    elif mutation == "wrong_slot":
        contract["slots"][0]["slot_ref"] = "adjacent-slot"  # type: ignore[index]
    elif mutation == "wrong_span":
        contract["slots"][0]["span_ref"] = "adjacent-span"  # type: ignore[index]
    elif mutation == "wrong_source_entry":
        changed = copy.deepcopy(contract)
        changed["slots"][0]["provenance"]["source_entry_id"] = "entry-adjacent"  # type: ignore[index]
        contract = changed
    elif mutation == "wrong_fragments":
        changed = copy.deepcopy(contract)
        changed["slots"][0]["provenance"]["word_fragments"][0]["text"] = "same-text"  # type: ignore[index]
        contract = changed
    elif mutation == "wrong_actual":
        changed = copy.deepcopy(contract)
        changed["slots"][0]["provenance"]["actual_result"][  # type: ignore[index]
            "candidate_after_sha256"
        ] = "9" * 64
        contract = changed
    else:
        receipt["materialization_digest"] = "9" * 64

    with pytest.raises(ToolFailure, match="provenance|bound|match"):
        validate_published_template_artifact(
            template_docx=template,
            fill_contract=contract,
            publication_receipt=receipt,
        )


def test_build_placement_consumes_only_current_phase6_package(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path / "registry.yaml")
    template = tmp_path / "final-template.docx"
    _write_docx(template)
    contract = _contract(template, registry, with_slot=False)
    student = {
        "schema_version": "docfit-student-content-model/v2",
        "status": "READY",
        "registry": registry.identity(),
        "source_sha256": "a" * 64,
        "items": [],
        "relations": [],
    }

    placement = build_placement(
        student_content=student,
        contract=contract,
        registry=registry,
        template_docx=template,
    )
    assert placement["status"] == "COMPLETE"

    legacy = copy.deepcopy(contract)
    legacy["provenance"] = {}
    with pytest.raises(ToolFailure, match="provenance"):
        build_placement(
            student_content=student,
            contract=legacy,
            registry=registry,
            template_docx=template,
        )


@pytest.mark.parametrize("mutation", ["old_proof", "swapped_offsets", "source_hash"])
def test_consumer_rejects_rehashed_partition_tampering(tmp_path, mutation):
    registry = _write_registry(tmp_path / "registry.yaml")
    template = tmp_path / "final-template.docx"
    _write_docx(template)
    contract = _contract(template, registry, with_slot=False)
    phase6 = contract["provenance"]["materialization"]
    partition = phase6["source_partition"]
    proof = partition["unit_boundary_proof"]
    if mutation == "old_proof":
        proof["schema_version"] = 1
    elif mutation == "swapped_offsets":
        proof["resolved_units"][0]["source_spans"][0]["extent"] = {
            "kind": "text",
            "start": 1,
            "end": 5,
        }
        digest = sha256_json(proof["resolved_units"])
        proof["unit_projection_digest"] = digest
        partition["unit_projection_digest"] = digest
        phase6["unit_projection_digest"] = digest
    else:
        partition["document_sha256"] = "9" * 64
        phase6["source_sha256"] = "9" * 64
    contract["provenance"]["materialization_digest"] = sha256_json(phase6)
    with pytest.raises(ToolFailure):
        validate_published_template_artifact(template_docx=template, fill_contract=contract)


def test_completed_resume_requires_same_initial_partition(tmp_path, monkeypatch):
    # Isolate initial-partition provenance; visual resume gating has dedicated tests.
    monkeypatch.setattr(
        "docfit.app.prepare_template.validate_final_visual_review", lambda *args, **kwargs: None
    )
    import json

    import yaml

    from docfit.app.prepare_template import PreparedTemplateTask, _load_completed
    from docfit.tools.runtime import atomic_write_json
    from tests.support.source_identity import persist_source_identity

    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    _write_docx(source)
    template = root / "output/final-template.docx"
    _write_docx(template)
    registry = _write_registry(root / "input/field-registry.yaml")
    source_hash = sha256_file(source)
    contract = _contract(template, registry, with_slot=False, source_hash=source_hash)
    partition = contract["provenance"]["materialization"]["source_partition"]
    persist_source_identity(root, partition)
    contract_path = root / "output/fill-contract.yaml"
    contract_path.write_text(yaml.safe_dump(contract))
    publication = {
        "schema_version": 2,
        "template_sha256": sha256_file(template),
        "fill_contract_sha256": sha256_file(contract_path),
        "materialization_digest": contract["provenance"]["materialization_digest"],
    }
    atomic_write_json(root / "work/.docfit/template-publication/build-report.json", publication)
    # Use the same public execution trace path as prepare-template.
    from docfit.app.prepare_template import _TRACE

    atomic_write_json(
        root / _TRACE,
        {
            "architecture": "main_agent_full_context/v1",
            "publication": publication,
            "agent_completion": {"status": "complete"},
        },
    )
    prepared = PreparedTemplateTask(
        task_root=root,
        template_path=source,
        requirements_path=None,
        registry_source=registry.path,
        template_sha256=source_hash,
        requirements_sha256=None,
        registry_sha256=sha256_file(registry.path),
    )
    assert _load_completed(prepared) is not None
    checkpoint_path = root / "work/.docfit/unit-boundary-checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint["schema_version"] = 1
    atomic_write_json(checkpoint_path, checkpoint)
    with pytest.raises(ToolFailure, match="accepted checkpoint"):
        _load_completed(prepared)


@pytest.mark.parametrize("mutation", ["redirected_fragment", "cross_unit_slot"])
def test_consumer_re_resolves_slot_against_original_identity_and_cuts(tmp_path, mutation):
    registry = _write_registry(tmp_path / "registry.yaml")
    source_hash = "1" * 64
    slot_ref = (
        "source_entry_id=source-entry-1;extent=text[0:5];"
        f"source_snapshot_sha256={source_hash};field_id=thesis.title.zh"
    )
    template = tmp_path / "final-template.docx"
    _write_docx(template, slot_ref=slot_ref, field_id="thesis.title.zh")
    contract = _contract(template, registry, with_slot=True)
    phase6 = contract["provenance"]["materialization"]
    if mutation == "redirected_fragment":
        provenance = copy.deepcopy(phase6["slots"][0])
        provenance["word_fragments"][0]["locator"] = "/body/p[2]/r[1]"
        provenance["accepted_span"]["word_fragments"] = copy.deepcopy(provenance["word_fragments"])
        phase6["slots"][0] = provenance
        contract["slots"][0]["provenance"] = copy.deepcopy(provenance)
    else:
        partition = phase6["source_partition"]
        split = {
            "source_entry_id": "source-entry-1",
            "edge": "split",
            "before": "va",
            "after": "lue",
        }
        source_partition(
            partition,
            units=[
                {
                    "unit_id": "a",
                    "unit_name": "first",
                    "start_boundary": {"source_entry_id": "source-entry-1", "edge": "start"},
                    "end_boundary": split,
                },
                {
                    "unit_id": "b",
                    "unit_name": "second",
                    "start_boundary": split,
                    "end_boundary": {"source_entry_id": "source-entry-1", "edge": "end"},
                },
            ],
        )
        phase6["unit_projection_digest"] = partition["unit_projection_digest"]
    contract["provenance"]["materialization_digest"] = sha256_json(phase6)
    with pytest.raises(ToolFailure, match="initial source partition|unit cut"):
        validate_published_template_artifact(template_docx=template, fill_contract=contract)

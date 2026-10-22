"""Constructed DOCX + actual provenance paths, not Agent or product acceptance."""

import json
from copy import deepcopy

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import (
    _accepted_slot_provenance,
    _phase6_contract_provenance,
    validate_published_template_artifact,
)
from docfit.template.materialization import materialize_template_from_semantics
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file, sha256_json
from tests.contract.test_template_materialization_runtime import (
    _canonicalize_materialization_fixture,
    _inventory_with_paragraph_objects,
    _judgment,
    _part,
    _with_current_vocabulary,
    _write_body_registry,
    _write_docx,
    _write_docx_from_paragraph_xml,
)
from tests.support.source_identity import persist_source_identity


def _case(root, *, cell=False):
    source = root / "input/school-template.docx"
    registry_path = root / "input/field-registry.yaml"
    _write_body_registry(registry_path)
    registry = FieldRegistrySnapshot.load(registry_path)
    if cell:
        _write_docx_from_paragraph_xml(source, [
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A(note)B.</w:t></w:r></w:p>"
            "</w:tc><w:tc><w:p><w:r><w:t>Protected cell</w:t></w:r></w:p>"
            "</w:tc></w:tr></w:tbl>",
        ])
    else:
        _write_docx(source, ["A(note)B."])
    inventory = _inventory_with_paragraph_objects([
        {"block_id": "body", "covered_object_ids": ["obj-1"], "text": "A(note)B."},
    ])
    if cell:
        inventory["objects"][0]["locator"] = "/body/tbl[1]/tr[1]/tc[1]/p[1]"
    review = {"semantic_judgments": [_judgment("body", [
        _part("body_structure", "A", field_id="body.paragraph"),
        _part("cleanup", "(note)"),
        _part("body_structure", "B", field_id="body.paragraph"),
        _part("fixed_label", "."),
    ])]}
    inventory, review = _with_current_vocabulary(registry, inventory, review)
    inventory, review = _canonicalize_materialization_fixture(
        source_docx=source, inventory=inventory, review=review,
    )
    persist_source_identity(root, inventory)
    output = root / "work/candidate.docx"
    result = materialize_template_from_semantics(
        source_docx=source, output_docx=output, registry=registry,
        inventory=inventory, review=review,
    )
    result = json.loads(json.dumps(result))  # Persisted JSON has no shared Python object aliases.
    for name, data in [("harness/object-inventory.json", inventory),
                       ("harness/semantic-judgments.json", review),
                       ("post-unit-materialization/materialization.json", result)]:
        atomic_write_json(root / "work/.docfit" / name, data)
    return source, output, registry, inventory, review, result


def _provenance(root, case):
    source, _, registry, inventory, review, materialization = case
    return _accepted_slot_provenance(
        root, registry, source_hash=sha256_file(source), inventory=inventory,
        review=review, materialization=materialization,
    )


def _package(root, case):
    source, output, registry, inventory, review, result = case
    provenance = _provenance(root, case)
    assert len(provenance) == 1
    slots = [{"slot_ref": ref, "span_ref": p["span_ref"], "field_id": p["field_id"],
              "provenance": p} for ref, p in provenance.items()]
    phase6 = _phase6_contract_provenance(
        root=root, source_hash=sha256_file(source), candidate_hash=sha256_file(output),
        registry=registry, slots=slots, inventory=inventory, review=review, materialization=result,
    )
    return {"schema_version": "docfit-template-fill-contract/v2",
            "template_sha256": sha256_file(output), "field_registry_ref": registry.identity(),
            "slots": slots, "provenance": {"materialization": phase6,
                                            "materialization_digest": sha256_json(phase6)}}


@pytest.mark.parametrize("cell", [False, True])
def test_grouped_body_interface_has_one_control_and_all_source_provenance(tmp_path, cell):
    case = _case(tmp_path, cell=cell)
    package = _package(tmp_path, case)
    assert len(package["slots"]) == 1
    record = package["slots"][0]["provenance"]["coalescence"]
    assert [s["text"] for s in record["source_spans"]] == ["A", "B"]
    assert [s["text"] for s in record["removed_spans"]] == ["(note)"]
    assert package["provenance"]["materialization"]["schema_version"].endswith("/v2")
    validate_published_template_artifact(template_docx=case[1], fill_contract=package)


@pytest.mark.parametrize("target", ["operations", "mutation_receipts"])
def test_producer_rejects_lost_coalescence_in_operation_or_receipt(tmp_path, target):
    case = _case(tmp_path)
    item = case[-1][target][0]
    if target == "mutation_receipts":
        item = item["operation"]
    item["members"][0].pop("coalescence")
    with pytest.raises(ToolFailure, match="body interface") as error:
        _provenance(tmp_path, case)
    assert error.value.code == (
        "published_body_interface_mismatch" if target == "operations"
        else "published_body_interface_receipt_mismatch"
    )


@pytest.mark.parametrize("mutation", [
    lambda p: p.pop("coalescence"),
    lambda p: p["coalescence"]["source_spans"].pop(),
    lambda p: p["coalescence"]["removed_spans"].clear(),
    lambda p: p["coalescence"]["removed_spans"][0].update(role="fixed_label"),
    lambda p: p["coalescence"]["source_spans"][1].update(expected_source_content="changed"),
    lambda p: p["coalescence"].update(anchor_slot_ref="wrong"),
])
def test_consumer_rejects_lost_or_tampered_group_even_after_digest_recalculation(
    tmp_path, mutation,
):
    case = _case(tmp_path)
    package = deepcopy(_package(tmp_path, case))
    slot = package["slots"][0]
    mutation(slot["provenance"])
    phase6 = package["provenance"]["materialization"]
    phase6["slots"] = [deepcopy(slot["provenance"])]
    package["provenance"]["materialization_digest"] = sha256_json(phase6)
    with pytest.raises(ToolFailure):
        validate_published_template_artifact(template_docx=case[1], fill_contract=package)


@pytest.mark.parametrize("mutation", [
    lambda phase6: phase6.update(schema_version="docfit-template-materialization-provenance/v1"),
    lambda phase6: phase6.pop("coalesced_body_slot_refs"),
])
def test_coalesced_package_cannot_downgrade_or_hide_its_handoff_contract(tmp_path, mutation):
    case = _case(tmp_path)
    package = _package(tmp_path, case)
    phase6 = package["provenance"]["materialization"]
    mutation(phase6)
    package["provenance"]["materialization_digest"] = sha256_json(phase6)
    with pytest.raises(ToolFailure):
        validate_published_template_artifact(template_docx=case[1], fill_contract=package)

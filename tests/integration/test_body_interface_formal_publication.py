"""Constructed DOCX publication with real OfficeCLI and synthetic visual evidence.

This checks package handoff, not real-school replay, Agent E2E, or visual acceptance.
"""

import json
import shutil

import pytest
import yaml

from docfit.template.artifact import (
    publish_template_artifact,
    validate_published_template_artifact,
)
from docfit.template.final_visual_review import CRITERIA, require_final_visual_review
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file
from tests.contract.test_body_interface_publication import _case
from tests.contract.test_final_visual_review import SyntheticVisual


@pytest.mark.skipif(shutil.which("officecli") is None, reason="OfficeCLI required")
@pytest.mark.parametrize("lose_source_record", [False, True])
@pytest.mark.parametrize("cell", [False, True])
def test_coalesced_interface_publication_keeps_complete_persisted_handoff(
    tmp_path, lose_source_record, cell,
):
    source, candidate, _, _, _, materialization = _case(tmp_path, cell=cell)
    source_hash = sha256_file(source)
    candidate_hash = sha256_file(candidate)
    # Exercise the actual visual gate with explicitly synthetic contract evidence.
    visual = SyntheticVisual(tmp_path)
    with pytest.raises(ToolFailure) as pending:
        require_final_visual_review(
            task_root=tmp_path, source_docx=source, candidate_docx=candidate, visual=visual,
        )
    assert pending.value.code == "final_visual_review_required"
    current = json.loads(
        (tmp_path / "work/.docfit/final-visual-review/current.json").read_text()
    )
    request = json.loads((tmp_path / current["request_path"]).read_text())
    review = request["review_template"]
    review["status"] = "passed"
    review["reviewer"] = {
        "kind": "external_visual_reviewer", "name": "synthetic-contract-fixture",
        "reviewed_at": "2026-09-24T00:00:00+00:00",
    }
    for page in review["pages"]:
        page["checks"] = {
            key: {"status": "passed", "observation": "Synthetic contract assertion only."}
            for key in CRITERIA
        }
    if lose_source_record:
        materialization["mutation_receipts"][0]["operation"]["members"][0].pop("coalescence")
        atomic_write_json(
            tmp_path / "work/.docfit/post-unit-materialization/materialization.json",
            materialization,
        )
    kwargs = dict(
        task_root=tmp_path, source_docx=source, candidate_docx=candidate,
        field_registry=tmp_path / "input/field-registry.yaml",
        validation={"final_sha256": candidate_hash, "status": "ok"}, visual_review=review,
    )
    if lose_source_record:
        with pytest.raises(ToolFailure) as rejected:
            publish_template_artifact(**kwargs)
        assert rejected.value.code == "published_body_interface_receipt_mismatch"
        assert not (tmp_path / "output/final-template.docx").exists()
        assert not (tmp_path / "output/fill-contract.yaml").exists()
        return
    receipt = publish_template_artifact(**kwargs)
    output = tmp_path / "output/final-template.docx"
    contract_path = tmp_path / "output/fill-contract.yaml"
    contract = yaml.safe_load(contract_path.read_text())
    contract["contract_sha256"] = sha256_file(contract_path)
    assert sorted(p.name for p in output.parent.iterdir()) == [
        "fill-contract.yaml", "final-template.docx",
    ]
    assert sha256_file(source) == source_hash
    assert sha256_file(output) == candidate_hash
    assert receipt["counts"]["slot"] == 1
    assert contract["status"] == "candidate_pending_human_acceptance"
    group = contract["slots"][0]["provenance"]["coalescence"]
    assert [span["text"] for span in group["source_spans"]] == ["A", "B"]
    assert [span["text"] for span in group["removed_spans"]] == ["(note)"]
    validate_published_template_artifact(
        template_docx=output, fill_contract=contract, publication_receipt=receipt,
    )

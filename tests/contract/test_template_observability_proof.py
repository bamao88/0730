from __future__ import annotations

import json
from pathlib import Path

import yaml

from docfit.app.agent import project_root
from docfit.evals.template_observability import (
    TEMPLATE_MODULE_IDS,
    TEMPLATE_OBSERVABILITY_PROOF_V1,
    build_template_observability_proof,
)
from docfit.tools.runtime import sha256_file

ROOT = project_root()
CURRENT_TEMPLATE_EXTRACTION_DOCS = (
    ROOT / "docs/contracts/template-extraction.md",
    ROOT / "docs/modules/template-extraction.md",
    ROOT / "docs/status/active/docfit-school-extract-v2.md",
    ROOT / "evals/template-extraction/README.md",
    ROOT / "evals/template-extraction/stage-replay.md",
    ROOT / "docs/adr/0001-template-unit-boundary-visual-first.md",
)
REMOVED_TEMPLATE_FLOW_DOCS = (
    ROOT / "docs/modules/template-extraction-unit-boundary-checkpoint.md",
    ROOT / "docs/modules/template-extraction-post-unit-flow.md",
    ROOT / "docs/modules/template-extraction-runtime-resume.md",
)
REMOVED_REDESIGN_DOCS = (
    ROOT / "docs/plans/docfit-template-extraction-skill-harness-redesign.md",
    ROOT / "docs/plans/docfit-template-extraction-skill-harness-redesign",
    ROOT / "docs/status/active/docfit-template-extraction-skill-harness-redesign-modules.md",
)


def _case_payloads() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for case_path in sorted((ROOT / "evals/template-extraction/cases").glob("*/case.yaml")):
        payload = yaml.safe_load(case_path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        payload["_case_dir"] = case_path.parent
        cases.append(payload)
    return cases


def _accepted_module_status() -> str:
    return "\n".join(f"- {module_id}: passed" for module_id in TEMPLATE_MODULE_IDS)


def test_e1_current_docs_replace_obsolete_redesign_docs() -> None:
    for path in CURRENT_TEMPLATE_EXTRACTION_DOCS:
        assert path.exists(), path
        body = path.read_text(encoding="utf-8")
        assert "docfit-template-extraction-skill-harness-redesign" not in body
        assert "docfit-template-extraction-skill-harness-redesign-modules" not in body

    for path in REMOVED_REDESIGN_DOCS:
        assert not path.exists(), path
    for path in REMOVED_TEMPLATE_FLOW_DOCS:
        assert not path.exists(), path

    module_flow = (ROOT / "docs/modules/template-extraction.md").read_text(
        encoding="utf-8",
    )
    stage_replay = (ROOT / "evals/template-extraction/stage-replay.md").read_text(
        encoding="utf-8",
    )

    assert "Agent" in module_flow
    assert "Tool" in module_flow
    assert "Harness" in module_flow
    assert "UnitBoundaryProof" in module_flow
    assert "--resume-proof" in module_flow
    assert "Post-unit 主流程" in module_flow
    assert "阶段 replay" in stage_replay


def test_e1_three_real_school_cases_have_auditable_accepted_gold_pairs() -> None:
    cases = _case_payloads()

    assert [case["case_id"] for case in cases] == [
        "01-hunau-undergraduate",
        "02-njau-undergraduate",
        "03-pku-graduate",
    ]
    for case in cases:
        case_dir = Path(str(case["_case_dir"]))
        gold = case["gold"]
        assert isinstance(gold, dict)
        receipt = json.loads(
            (case_dir / "candidate-package-receipt.json").read_text(encoding="utf-8")
        )
        approvals = sorted((case_dir / "review").glob("accepted-*/approval-record.yaml"))
        assert len(approvals) == 1
        approval = yaml.safe_load(approvals[0].read_text(encoding="utf-8"))

        template = case_dir / str(gold["template"])
        contract = case_dir / str(gold["contract"])
        assert case["case_status"] == "accepted"
        assert case["gold_review"]["status"] == "accepted"
        assert receipt["gold_review_status"] == "accepted"
        assert receipt["template_sha256"] == sha256_file(template) == gold["template_sha256"]
        assert receipt["contract_sha256"] == sha256_file(contract) == gold["contract_sha256"]
        assert str(approval["approval_conclusion"]).startswith("approved_")
        assert approval["gold_pair"]["template"]["sha256"] == gold["template_sha256"]
        assert approval["gold_pair"]["contract"]["sha256"] == gold["contract_sha256"]


def test_e1_observability_proof_accepts_complete_trace_and_rejects_gold_runtime_context() -> None:
    module_status = _accepted_module_status()
    trace = {
        "architecture": "main_agent_full_context/v1",
        "application_semantic_work_items": 0,
        "sdk_query_count": 1,
        "harness_feedback_attempts": 0,
        "semantic_feedback_attempts": 0,
        "skills_loaded": ["docfit-school-extract"],
        "agent_completion": {
            "status": "complete",
            "summary": "Semantic judgment set is ready for Harness review.",
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "unit-cover:block-0001"},
                    "parts": [
                        {
                            "text": "论文题目",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                    "reason": "Visible template range is a fillable title slot.",
                }
            ],
        },
        "tool_uses": ["mcp__docfit__docfit_evidence"],
    }
    publication = {
        "published": True,
        "artifact_path": "output/final-template.docx",
        "fill_contract_path": "output/fill-contract.yaml",
        "checks": [
            {"name": "validation_bound", "result": "ok"},
            {"name": "visual_review_bound", "result": "ok"},
        ],
        "validation": {"docx_validate": {"status": "ok"}},
    }
    proof = build_template_observability_proof(
        module_status=module_status,
        trace=trace,
        publication=publication,
        eval_cases=_case_payloads(),
        runtime_context={"prompt": "DocFit startup context", "tool_inputs": []},
    )

    assert proof["schema_version"] == TEMPLATE_OBSERVABILITY_PROOF_V1
    assert proof["status"] == "ok"
    assert proof["gold_isolated_from_runtime"] is True
    assert all(proof["modules"].values())
    assert all(proof["vertical_slice"].values())

    legacy_completion = build_template_observability_proof(
        module_status=module_status,
        trace={
            **trace,
            "agent_completion": {
                "status": "complete",
                "summary": "Old shape should not pass.",
                "semantic_judgments": [{"judgment_id": "j1", "judgment": "fixed"}],
            },
        },
        publication=publication,
        eval_cases=_case_payloads(),
        runtime_context={"prompt": "DocFit startup context", "tool_inputs": []},
    )
    assert legacy_completion["status"] == "needs_input"
    assert legacy_completion["vertical_slice"]["semantic_judgment_contract"] is False

    leaked = build_template_observability_proof(
        module_status=module_status,
        trace=trace,
        publication=publication,
        eval_cases=_case_payloads(),
        runtime_context={"prompt": "Use gold-template as the answer."},
    )

    assert leaked["status"] == "needs_input"
    assert leaked["gold_isolated_from_runtime"] is False

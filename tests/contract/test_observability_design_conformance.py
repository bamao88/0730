from __future__ import annotations

from docfit.evals.template_observability import (
    TEMPLATE_MODULE_IDS,
    build_template_observability_proof,
)


def _module_status() -> str:
    return "\n".join(f"- {module_id}: passed" for module_id in TEMPLATE_MODULE_IDS)


def _eval_cases() -> list[dict[str, object]]:
    return [
        {
            "case_id": f"case-{index}",
            "case_status": "accepted",
            "gold": {"template_sha256": "a" * 64},
            "gold_review": {"status": "accepted"},
        }
        for index in range(1, 4)
    ]


def _publication() -> dict[str, object]:
    return {
        "published": True,
        "artifact_path": "output/final-template.docx",
        "fill_contract_path": "output/fill-contract.yaml",
        "checks": [
            {"name": "validation_bound", "result": "ok"},
            {"name": "visual_review_bound", "result": "ok"},
        ],
        "validation": {"docx_validate": {"status": "ok"}},
    }


def _current_semantic_judgments() -> list[dict[str, object]]:
    return [
        {
            "scope": {"reading_block_id": "unit-cover:block-0001"},
            "parts": [
                {"text": "论文题目", "role": "fill_slot", "field_id": "thesis.title.zh"}
            ],
            "reason": "Visible template range is a fillable title slot.",
        }
    ]


def _trace(**overrides: object) -> dict[str, object]:
    trace: dict[str, object] = {
        "architecture": "main_agent_full_context/v1",
        "application_semantic_work_items": 0,
        "sdk_query_count": 2,
        "harness_feedback_attempts": 1,
        "semantic_feedback_attempts": 1,
        "skills_loaded": ["docfit-school-extract"],
        "agent_completion": {
            "status": "complete",
            "summary": "Semantic judgment set is ready for Harness review.",
            "semantic_judgments": _current_semantic_judgments(),
        },
        "tool_uses": ["mcp__docfit__docfit_evidence"],
        "permission_events": [],
    }
    trace.update(overrides)
    return trace


def _proof(trace: dict[str, object]) -> dict[str, object]:
    return build_template_observability_proof(
        module_status=_module_status(),
        trace=trace,
        publication=_publication(),
        eval_cases=_eval_cases(),
        runtime_context={"prompt": "DocFit startup context", "tool_inputs": []},
    )


def test_observability_proof_requires_agent_native_design_handshakes() -> None:
    proof = _proof(_trace())

    assert proof["status"] == "ok"
    assert proof["gold_isolated_from_runtime"] is True
    assert proof["vertical_slice"] == {
        "agent_native_context": True,
        "skill_loaded": True,
        "canonical_tool_surface": True,
        "forbidden_tool_execution_blocked": True,
        "same_session_feedback_loop": True,
        "semantic_judgment_contract": True,
        "host_receipts": True,
        "visual_review_binding": True,
        "completion_gate": True,
        "publication": True,
    }


def test_observability_proof_rejects_legacy_or_unprovable_runtime_context() -> None:
    missing_skill = _proof(_trace(skills_loaded=[]))
    legacy_tool = _proof(
        _trace(
            tool_uses=[
                "mcp__docfit__docfit_evidence",
                "mcp__docfit__docfit_check",
                "mcp__docfit__docfit_apply",
            ]
        )
    )
    legacy_completion = _proof(
        _trace(
            agent_completion={
                "status": "complete",
                "summary": "Old shape should not pass.",
                "semantic_judgments": [{"judgment_id": "j1", "judgment": "fixed"}],
            }
        )
    )
    restarted_feedback = _proof(_trace(sdk_query_count=2, harness_feedback_attempts=2))
    unaudited_bash = _proof(
        _trace(
            tool_uses=[
                "mcp__docfit__docfit_evidence",
                "Bash",
            ]
        )
    )
    denied_bash = _proof(
        _trace(
            tool_uses=[
                "mcp__docfit__docfit_evidence",
                "Bash",
            ],
            permission_events=[
                {
                    "tool_name": "Bash",
                    "decision": "deny",
                    "reason_code": "unmatched_tool_denied",
                }
            ],
        )
    )

    assert missing_skill["status"] == "needs_input"
    assert missing_skill["vertical_slice"]["skill_loaded"] is False
    assert legacy_tool["status"] == "needs_input"
    assert legacy_tool["vertical_slice"]["canonical_tool_surface"] is False
    assert legacy_completion["status"] == "needs_input"
    assert legacy_completion["vertical_slice"]["semantic_judgment_contract"] is False
    assert restarted_feedback["status"] == "needs_input"
    assert restarted_feedback["vertical_slice"]["same_session_feedback_loop"] is False
    assert unaudited_bash["status"] == "needs_input"
    assert unaudited_bash["vertical_slice"]["forbidden_tool_execution_blocked"] is False
    assert denied_bash["status"] == "ok"
    assert denied_bash["vertical_slice"]["forbidden_tool_execution_blocked"] is True

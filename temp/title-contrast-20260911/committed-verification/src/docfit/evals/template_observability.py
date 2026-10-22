"""Template-extraction Eval and observability proof helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from docfit.tools.runtime import JsonObject

TEMPLATE_OBSERVABILITY_PROOF_V1 = "docfit-template-observability-proof/v1"
TEMPLATE_MODULE_IDS = (
    "P0",
    "P1",
    "P2",
    "P3",
    "P4",
    "R1",
    "R2",
    "R3",
    "T1",
    "T2",
    "T3",
    "O1",
    "E1",
)
_GOLD_RUNTIME_TOKENS = (
    "gold-template",
    "gold-contract",
    "final-template.gold",
    "fill-contract.gold",
    "/gold/",
    "accepted answer",
    "accepted_answer",
)


def _contains_forbidden_gold_token(value: Any) -> bool:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()
    except TypeError:
        serialized = str(value).casefold()
    return any(token in serialized for token in _GOLD_RUNTIME_TOKENS)


def _module_status(module_status: str) -> dict[str, bool]:
    return {
        module_id: f"- {module_id}:" in module_status and "passed" in module_status
        for module_id in TEMPLATE_MODULE_IDS
    }


def _completion(trace: Mapping[str, Any]) -> Mapping[str, Any]:
    value = trace.get("agent_completion")
    return value if isinstance(value, Mapping) else {}


def _tool_uses(trace: Mapping[str, Any]) -> set[str]:
    value = trace.get("tool_uses")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return set()
    return {str(item) for item in value}


def _skills_loaded(trace: Mapping[str, Any]) -> set[str]:
    value = trace.get("skills_loaded")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return set()
    return {str(item) for item in value}


def _permission_events(trace: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    value = trace.get("permission_events")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _forbidden_tool_execution_blocked(trace: Mapping[str, Any], tools: set[str]) -> bool:
    forbidden_tools = {
        "Bash",
        "Write",
        "Edit",
        "Web",
        "WebSearch",
        "WebFetch",
    }
    attempted = tools & forbidden_tools
    if not attempted:
        return True
    permissions = _permission_events(trace)
    if not permissions:
        return False
    for tool_name in attempted:
        decisions = {
            str(item.get("decision"))
            for item in permissions
            if item.get("tool_name") == tool_name
        }
        if "allow" in decisions or "deny" not in decisions:
            return False
    return True


def _publication_validation(publication: Mapping[str, Any]) -> Mapping[str, Any]:
    value = publication.get("validation")
    return value if isinstance(value, Mapping) else {}


def _vertical_slice(trace: Mapping[str, Any], publication: Mapping[str, Any]) -> JsonObject:
    completion = _completion(trace)
    tools = _tool_uses(trace)
    skills = _skills_loaded(trace)
    validation = _publication_validation(publication)
    raw_checks = publication.get("checks")
    checks = (
        raw_checks
        if isinstance(raw_checks, Sequence) and not isinstance(raw_checks, str | bytes)
        else ()
    )
    check_names = {
        str(item.get("name"))
        for item in checks
        if isinstance(item, Mapping)
    }
    sdk_query_count = trace.get("sdk_query_count")
    harness_feedback_attempts = trace.get(
        "harness_feedback_attempts",
        trace.get("semantic_feedback_attempts", 0),
    )
    feedback_loop_is_provable = (
        isinstance(sdk_query_count, int)
        and sdk_query_count >= 1
        and isinstance(harness_feedback_attempts, int)
        and harness_feedback_attempts >= 0
        and (
            harness_feedback_attempts == 0
            or sdk_query_count == harness_feedback_attempts + 1
        )
    )
    legacy_tool_uses = {
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
        "mcp__docfit__docx_validate",
    }
    return {
        "agent_native_context": trace.get("architecture") == "main_agent_full_context/v1"
        and trace.get("application_semantic_work_items") == 0,
        "skill_loaded": "docfit-school-extract" in skills,
        "canonical_tool_surface": not bool(tools & legacy_tool_uses)
        and {
            "mcp__docfit__docfit_evidence",
            "mcp__docfit__docfit_check",
        }.issubset(tools),
        "forbidden_tool_execution_blocked": _forbidden_tool_execution_blocked(
            trace,
            tools,
        ),
        "same_session_feedback_loop": feedback_loop_is_provable,
        "coverage": isinstance(completion.get("semantic_judgments"), Sequence)
        and not isinstance(completion.get("semantic_judgments"), str | bytes)
        and bool(completion.get("semantic_judgments")),
        "tool_receipts": bool(
            {
                "mcp__docfit__docfit_evidence",
                "mcp__docfit__docfit_check",
                "mcp__docfit__docfit_apply",
            }
            & tools
        )
        and "mcp__docfit__docfit_apply" in tools,
        "render_visual_review": isinstance(completion.get("candidate_render_ref"), str)
        and bool(completion.get("reviewed_pages")),
        "completion_gate": bool(validation.get("docx_validate"))
        or "validation_bound" in check_names,
        "publication": publication.get("published") is True
        and publication.get("artifact_path") == "output/final-template.docx"
        and publication.get("fill_contract_path") == "output/fill-contract.yaml",
    }


def build_template_observability_proof(
    *,
    module_status: str,
    trace: Mapping[str, Any],
    publication: Mapping[str, Any],
    eval_cases: Sequence[Mapping[str, Any]],
    runtime_context: Mapping[str, Any],
) -> JsonObject:
    """Summarize whether Eval evidence is complete without consuming Gold as runtime input."""

    modules = _module_status(module_status)
    vertical_slice = _vertical_slice(trace, publication)
    accepted_cases: list[str] = []
    for item in eval_cases:
        gold_review = item.get("gold_review")
        if (
            item.get("case_status") == "accepted"
            and isinstance(item.get("gold"), Mapping)
            and isinstance(gold_review, Mapping)
            and gold_review.get("status") == "accepted"
        ):
            accepted_cases.append(str(item.get("case_id")))
    gold_isolated = not _contains_forbidden_gold_token(runtime_context)
    complete = (
        all(modules.values())
        and all(bool(value) for value in vertical_slice.values())
        and len(accepted_cases) >= 3
        and gold_isolated
    )
    return {
        "schema_version": TEMPLATE_OBSERVABILITY_PROOF_V1,
        "status": "ok" if complete else "needs_input",
        "modules": modules,
        "vertical_slice": vertical_slice,
        "accepted_real_school_cases": accepted_cases,
        "gold_isolated_from_runtime": gold_isolated,
        "failure": None
        if complete
        else {
            "code": "template_observability_proof_incomplete",
            "message": "Module, vertical slice, real-case, or Gold isolation evidence is missing.",
        },
    }

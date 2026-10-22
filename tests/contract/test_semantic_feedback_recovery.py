from __future__ import annotations

import copy

import pytest

from docfit.app.prepare_template import _agent_visible_feedback_packet
from docfit.template.harness import TemplateHarnessService
from docfit.template.semantic_recovery import (
    SYSTEM_REVIEW_MESSAGES,
    classify_semantic_feedback,
)


def feedback(code, message="Cannot resolve locator at source position"):
    return {
        "status": "needs_input",
        "feedback": {"type": "span_resolution", "agent_action": "revise"},
        "blockers": [{"code": code, "source_entry_id": "entry-1", "message": message}],
        "failure": {
            "origin": "request",
            "code": "template_ordered_span_resolution_incomplete",
            "retryable": True,
        },
    }


@pytest.mark.parametrize("code", list(SYSTEM_REVIEW_MESSAGES))
def test_mapping_failures_keep_cause_and_do_not_request_semantic_revision(
    tmp_path, monkeypatch, code
):
    original = feedback(code)
    before = copy.deepcopy(original)
    monkeypatch.setattr(
        TemplateHarnessService, "_submit_semantic_judgments", lambda *_args: original
    )
    actual = TemplateHarnessService(task_root=tmp_path).handle(
        {"action": "submit_semantic_judgments"}
    )
    assert actual["status"] == "error"
    assert actual["failure"]["origin"] == "harness"
    assert not actual["failure"]["retryable"]
    assert actual["recovery"]["action"] == "stop"
    assert original == before
    visible = _agent_visible_feedback_packet(actual, next_step="Revise semantic judgments.")
    assert visible["affected"][0]["message"] == SYSTEM_REVIEW_MESSAGES[code]
    assert visible["affected"][0]["source_entry_id"] == "entry-1"
    assert visible["responsibility"] == "harness"
    assert visible["next_step"].startswith("Stop this revision.")
    assert "locator" not in str(visible)
    assert "span_ref" not in str(visible)


@pytest.mark.parametrize("code", ["new_unknown_failure", None, [], {}])
def test_unknown_or_malformed_failure_is_not_a_semantic_retry(code):
    actual = classify_semantic_feedback(feedback(code))
    assert actual["status"] == "error"
    assert actual["recovery"]["owner"] == "harness"


def test_real_annotation_error_preserves_complete_evidence_and_revision_action():
    source = "  " + "文本" * 700 + "\u00a0"
    actual = feedback("ordered_part_text_mismatch", "Submitted part differs from source text.")
    actual["blockers"][0].update(
        {
            "submitted_text": source + "多余",
            "expected_text": source,
            "source_entries": [{"source_entry_id": "entry-1", "text": source}],
        }
    )
    classified = classify_semantic_feedback(actual)
    assert classified["recovery"] == {
        "kind": "semantic_revision",
        "owner": "agent",
        "action": "revise",
    }
    visible = _agent_visible_feedback_packet(
        classified, next_step="Reconsider the affected entries."
    )
    blocker = visible["affected"][0]
    assert blocker["expected_text"] == source
    assert blocker["submitted_text"] == source + "多余"
    assert blocker["source_entries"][0]["text"] == source
    assert visible["responsibility"] == "agent"
    assert visible["next_step"] == "Reconsider the affected entries."


def test_untranslatable_internal_diagnostic_is_not_replaced_by_generic_revision():
    visible = _agent_visible_feedback_packet(
        feedback("new_failure", "locator fingerprint does not resolve"),
        next_step="Revise meanings.",
    )
    assert visible["status"] == "error"
    assert visible["responsibility"] == "harness"
    assert "engineering investigation" in visible["affected"][0]["message"]
    assert "locator" not in str(visible)

from __future__ import annotations

from pathlib import Path

import pytest

from docfit.app.prepare_template import _semantic_feedback_prompt
from docfit.template.judgment_shape import mechanical_feedback
from docfit.tools.runtime import sha256_file
from docfit.tools.service import DocFitToolService


def _task_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK\x03\x04source")
    return root, sha256_file(source)


def _assert_actionable_mechanical_feedback(result: dict[str, object]) -> None:
    assert result["status"] == "needs_input"
    feedback = result["feedback"]
    assert isinstance(feedback, dict)
    assert feedback["mechanical"] is True
    assert feedback["semantic_authority"] is False
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert failure["retryable"] is True
    assert failure["suggested_actions"]
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert blockers
    assert all(isinstance(blocker, dict) and blocker.get("message") for blocker in blockers)


def test_docfit_check_feedback_tells_agent_what_context_to_refresh(
    tmp_path: Path,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    shape_gap = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "judgment_shape",
        }
    )
    completion_gap = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "completion_gate",
        }
    )

    for result in (shape_gap, completion_gap):
        _assert_actionable_mechanical_feedback(result)
    assert {
        blocker["evidence_focus"]
        for blocker in shape_gap["blockers"]
        if isinstance(blocker, dict) and "evidence_focus" in blocker
    } == {"unit_evidence_packet"}
    assert completion_gap["blockers"][0]["evidence_focus"] == "schema_envelope"


@pytest.mark.parametrize(
    ("check", "required_focus"),
    [
        ("style_evidence", "style_evidence"),
    ],
)
def test_docfit_check_missing_inputs_name_the_next_evidence_focus(
    tmp_path: Path,
    check: str,
    required_focus: str,
) -> None:
    root, _source_hash = _task_root(tmp_path)
    result = DocFitToolService(task_root=root).check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": check,
        }
    )

    _assert_actionable_mechanical_feedback(result)
    assert result["blockers"][0]["evidence_focus"] == required_focus


def test_same_session_feedback_prompt_preserves_mechanical_boundary() -> None:
    source_hash = "a" * 64
    feedback = mechanical_feedback(
        feedback_type="coverage",
        code="unit_coverage_incomplete",
        message="Unit coverage is incomplete.",
        source_hash=source_hash,
        blockers=[
            {
                "code": "missing_source_entry_semantic_judgments",
                "source_entry_ids": ["source-entry-1"],
                "field": "semantic_judgments",
                "evidence_focus": "unit_slice",
                "message": "Return coverage for the missing source unit.",
            }
        ],
        suggested_actions=("Call docfit_evidence with focus=unit_slice.",),
    )

    prompt = _semantic_feedback_prompt(feedback)

    assert prompt.startswith("Runtime Harness feedback:")
    assert '"semantic_authority": false' in prompt
    assert "semantic_source_entry_review" in prompt
    assert "reading block" in prompt
    assert "unit_coverage_incomplete" not in prompt
    assert "unit_slice" not in prompt
    assert "Call docfit_evidence" not in prompt
    assert "coverage" not in prompt
    assert "Do not treat this feedback as a semantic grade" in prompt


def test_span_gap_feedback_exposes_invisible_whitespace_without_semantic_advice() -> None:
    feedback = {
        "status": "needs_input",
        "feedback": {
            "type": "span_resolution",
            "mechanical": True,
            "semantic_authority": False,
        },
        "blockers": [
            {
                "code": "ordered_part_text_gap",
                "field": "semantic_judgments[0]",
                "source_entry_id": "source-entry-format-note",
                "uncovered_text": "     ",
                "source_text_length": 123,
                "covered_text_length": 118,
                "uncovered_text_length": 5,
                "uncovered_whitespace_codepoints": ["U+0020 × 5"],
                "message": (
                    "Ordered parts must cover the complete source entry without omissions."
                ),
            }
        ],
    }

    prompt = _semantic_feedback_prompt(feedback)

    assert '"source_text_length": 123' in prompt
    assert '"covered_text_length": 118' in prompt
    assert '"uncovered_text_length": 5' in prompt
    assert '"uncovered_whitespace_codepoints": ["U+0020 × 5"]' in prompt
    assert "including reported boundary whitespace" in prompt
    assert '"semantic_authority": false' in prompt
    assert "Mentioning the whitespace count only in reason does not cover" in prompt
    assert "leading_whitespace or trailing_whitespace" in prompt
    assert "keep text empty and use whitespace.codepoint/count" in prompt
    assert "Choose which part owns the whitespace from the source evidence" in prompt
    assert "as literal characters to an adjacent" not in prompt


def test_span_mismatch_feedback_preserves_part_when_encoding_leading_whitespace() -> None:
    feedback = {
        "status": "needs_input",
        "feedback": {
            "type": "span_resolution",
            "mechanical": True,
            "semantic_authority": False,
        },
        "blockers": [
            {
                "code": "ordered_part_text_mismatch",
                "field": "semantic_judgments[2].parts[0]",
                "source_entry_id": "source-entry-indented-note",
                "expected_text": "    2.此表",
                "submitted_text": "2.此表",
                "mismatch_offset": 0,
                "first_difference": {
                    "expected": {"character": " ", "codepoint": "U+0020", "end_of_text": False},
                    "submitted": {"character": "2", "codepoint": "U+0032", "end_of_text": False},
                },
                "expected_leading_whitespace_count": 4,
                "expected_leading_whitespace_codepoints": ["U+0020 × 4"],
                "message": "Ordered part text must equal the next exact source substring.",
            }
        ],
    }

    prompt = _semantic_feedback_prompt(feedback)

    assert '"expected_leading_whitespace_count": 4' in prompt
    assert '"first_difference": {' in prompt
    assert '"codepoint": "U+0032"' in prompt
    assert '"expected_leading_whitespace_codepoints": ["U+0020 × 4"]' in prompt
    assert "Remove any synthetic text part that contains a role name" in prompt
    assert "leading_whitespace on that same part, preserving its role and field_id" in prompt
    assert "only when your semantic partition requires it" in prompt
    assert "Do not split a fill_slot merely to encode whitespace" in prompt
    assert "prepend the listed expected whitespace as literal characters" not in prompt
    assert "only in reason does not cover" in prompt


def test_semantic_feedback_prompt_does_not_upgrade_retired_registry_binding() -> None:
    feedback = mechanical_feedback(
        feedback_type="registry_binding",
        code="registry_binding_missing",
        message="Old registry binding check failed.",
        source_hash="a" * 64,
        blockers=[
            {
                "code": "registry_binding_missing",
                "field": "registry_binding",
                "evidence_focus": "registry_field",
                "missing_requirement": "registry_binding",
                "message": "Resolve the old registry binding.",
            }
        ],
        suggested_actions=("Call docfit_check with check=registry_binding.",),
    )

    prompt = _semantic_feedback_prompt(feedback)

    assert "field_meaning_review" not in prompt
    assert "registry_binding" not in prompt
    assert "registry_field" not in prompt
    assert "field_id_vocabulary" not in prompt
    assert "mechanical_review" in prompt


def test_semantic_feedback_prompt_names_missing_reading_blocks() -> None:
    feedback = {
        "status": "needs_input",
        "feedback": {
            "type": "coverage",
            "mechanical": True,
            "semantic_authority": False,
        },
        "blockers": [
            {
                "code": "missing_semantic_judgments",
                "reading_blocks": [
                    {
                        "block_id": "cover:block-0001",
                        "range_id": "cover:range-0001",
                        "unit_id": "cover",
                        "text": "附件1 封面基本格式",
                        "covered_object_ids": ["obj-hidden-from-agent"],
                    }
                ],
                "message": "These inventory objects are not covered.",
            }
        ],
        "failure": {
            "suggested_actions": ["cover_missing_reading_blocks=['cover:block-0001']"]
        },
    }

    prompt = _semantic_feedback_prompt(feedback)

    assert "cover:block-0001" in prompt
    assert "cover:range-0001" in prompt
    assert "current accepted unit packet" in prompt
    assert "附件1 封面基本格式" in prompt
    assert "obj-hidden-from-agent" not in prompt


def test_semantic_feedback_prompt_explains_page_level_overlap_repair() -> None:
    feedback = {
        "status": "needs_input",
        "feedback": {
            "type": "coverage",
            "mechanical": True,
            "semantic_authority": False,
        },
        "blockers": [
            {
                "code": "overlapping_semantic_judgments",
                "object_ids": ["obj-hidden-from-agent"],
                "reading_blocks": [
                    {
                        "block_id": "cover:block-0001",
                        "range_id": "cover:range-0001",
                        "unit_id": "cover",
                        "text": "附件1 封面基本格式",
                    }
                ],
                "message": "These inventory objects are covered more than once.",
            }
        ],
    }

    prompt = _semantic_feedback_prompt(feedback)

    assert "cover:block-0001" in prompt
    assert "cover:range-0001" in prompt
    assert "one ordered owner judgment" in prompt
    assert "mixed responsibilities split into parts" in prompt
    assert "obj-hidden-from-agent" not in prompt

"""Boundary errors must reach the Agent with the exact units and source content."""

import json
from copy import deepcopy

import pytest

from docfit.app.prepare_template import _agent_visible_feedback_packet
from docfit.tools.service import DocFitToolService
from tests.contract.test_full_flow_source_identity import _fixture


def _check(root, units):
    before = deepcopy(units)
    result = DocFitToolService(task_root=root).check(
        {
            "check": "unit_coverage",
            "payload": {"units": units},
        }
    )
    assert units == before
    return result, _agent_visible_feedback_packet(result, next_step="Revise unit boundaries.")


def test_all_adjacent_overlaps_reach_actual_agent_feedback_without_changing_boundaries(tmp_path):
    canonical, _, _ = _fixture(tmp_path)
    ids = [entry.source_entry_id for entry in canonical.source_entries]
    units = [
        {
            "unit_id": "a",
            "unit_name": "First",
            "start_boundary": {"source_entry_id": ids[0], "edge": "start"},
            "end_boundary": {"source_entry_id": ids[1], "edge": "end"},
        },
        {
            "unit_id": "b",
            "unit_name": "Second",
            "start_boundary": {"source_entry_id": ids[1], "edge": "start"},
            "end_boundary": {"source_entry_id": ids[2], "edge": "end"},
        },
        {
            "unit_id": "c",
            "unit_name": "Third",
            "start_boundary": {"source_entry_id": ids[2], "edge": "start"},
            "end_boundary": {"source_entry_id": ids[3], "edge": "end"},
        },
    ]
    result, visible = _check(tmp_path, units)
    assert result["status"] == "needs_input"
    assert len(visible["affected"]) == 2
    for index, issue in enumerate(visible["affected"]):
        assert issue["code"] == "unit_boundary_overlap"
        assert issue["unit_ids"] == [units[index]["unit_id"], units[index + 1]["unit_id"]]
        assert issue["source_entries"][0]["source_entry_id"] == ids[index + 1]
        assert issue["source_entries"][0]["text"] == canonical.source_entries[index + 1].text
        assert issue["unit_boundaries"][0]["end_boundary"] == units[index]["end_boundary"]
        assert issue["unit_boundaries"][1]["start_boundary"] == units[index + 1]["start_boundary"]
        assert "overlap" in issue["message"]
    assert not any(
        token in json.dumps(visible)
        for token in (
            "object_ref",
            "locator",
            "fingerprint",
            "source_hash",
            "coverage",
        )
    )
    invalid = deepcopy(units)
    invalid[2]["start_boundary"]["source_entry_id"] = "absent"
    _, mixed = _check(tmp_path, invalid)
    assert sorted(issue["code"] for issue in mixed["affected"]) == [
        "unit_boundary_overlap", "unit_boundary_point_invalid",
    ]
    # A corrected proposal is still accepted under the exact same boundary rules.
    units[0]["end_boundary"] = deepcopy(units[1]["start_boundary"])
    units[1]["end_boundary"] = deepcopy(units[2]["start_boundary"])
    corrected, _ = _check(tmp_path, units)
    assert corrected["status"] == "ok"


@pytest.mark.parametrize(
    "case,code,text",
    [
        ("prefix", "unit_boundary_gap", "same"),
        ("middle_gap", "unit_boundary_gap", " "),
        ("middle_overlap", "unit_boundary_overlap", " "),
        ("suffix", "unit_boundary_gap", ""),
    ],
)
def test_exact_missing_or_repeated_text_including_empty_entry(tmp_path, case, code, text):
    canonical, _, proof = _fixture(tmp_path)
    units = deepcopy(proof["units"])
    ids = [e.source_entry_id for e in canonical.source_entries]
    if case == "prefix":
        units[0]["start_boundary"] = {"source_entry_id": ids[1], "edge": "start"}
    elif case == "middle_gap":
        units[1]["start_boundary"].update(before="alpha ", after="beta")
    elif case == "middle_overlap":
        units[0]["end_boundary"].update(before="alpha ", after="beta")
    else:
        units[-1]["end_boundary"] = {"source_entry_id": ids[-1], "edge": "start"}
    _, visible = _check(tmp_path, units)
    (issue,) = visible["affected"]
    assert issue["code"] == code
    assert [row["text"] for row in issue["source_entries"]] == [text]


def test_invalid_split_is_attached_to_the_submitted_unit_boundary(tmp_path):
    canonical, _, proof = _fixture(tmp_path)
    units = deepcopy(proof["units"])
    units[0]["end_boundary"]["before"] = "wrong"
    _, visible = _check(tmp_path, units)
    (issue,) = visible["affected"]
    assert issue["code"] == "unit_boundary_point_invalid"
    assert issue["field"] == "units[0].end_boundary"
    assert issue["unit_id"] == "a"
    assert issue["source_entries"][0]["text"] == canonical.source_entries[2].text

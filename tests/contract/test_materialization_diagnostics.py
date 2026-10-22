"""Execution diagnostics distinguish absent carriers and report all blocker counts."""

from copy import deepcopy

import pytest

from docfit.template.materialization.readiness import _body_structure_carrier_blockers
from docfit.template.materialization.recovery import readiness_failure
from tests.contract.test_template_materialization_readiness import _current_case, _registry


@pytest.mark.parametrize(
    ("locators", "code"),
    [
        (["/footer[1]/p[1]/r[1]"], "materialization_body_structure_carrier_unsupported"),
        (["/body/p[1]/r[1]", "/body/p[2]/r[1]"],
         "materialization_body_structure_member_crosses_carriers"),
    ],
)
def test_carrier_failure_explains_zero_versus_multiple_without_rewriting_judgment(
    tmp_path, locators, code,
):
    registry = _registry(tmp_path / "registry.yaml")
    _, review = _current_case(registry, role="body_structure", field_id="body.paragraph")
    judgments = deepcopy(review["semantic_judgments"])
    span = judgments[0]["resolved_spans"][0]
    original_fragment = span["word_fragments"][0]
    span["word_fragments"] = [{**original_fragment, "locator": loc} for loc in locators]
    if len(locators) == 2:
        for index, fragment in enumerate(span["word_fragments"]):
            fragment.update(
                object_id=f"obj-{index}", text=span["text"][index * 2:index * 2 + 2],
                source_text_start=index * 2, source_text_end=index * 2 + 2,
                object_text_start=0, object_text_end=2,
                object_ref={**fragment["object_ref"], "object_id": f"obj-{index}"},
            )
        span["covered_object_ids"] = ["obj-0", "obj-1"]
    before = deepcopy(judgments)
    blockers = _body_structure_carrier_blockers(judgments, cut_points={}, registry=registry)
    assert len(blockers) == 1
    assert blockers[0]["code"] == code
    assert blockers[0]["supported_carrier_count"] == (0 if "footer" in locators[0] else 2)
    assert judgments == before
    failure = readiness_failure({"blockers": blockers})
    assert failure.origin == "tool" and not failure.retryable
    if "footer" in locators[0]:
        assert "no supported body carrier" in blockers[0]["message"].lower()
        assert "multi-object" not in blockers[0]["message"]


def test_failure_summary_counts_all_occurrences_and_does_not_hide_later_categories():
    unsupported = "materialization_body_structure_carrier_unsupported"
    conflict = "materialization_cleanup_carrier_conflict"
    failure = readiness_failure({"blockers": [
        *[{"code": unsupported} for _ in range(7)],
        *[{"code": conflict} for _ in range(2)],
    ]})
    assert "9 blockers" in failure.message
    assert f"{unsupported} (7)" in failure.message
    assert f"{conflict} (2)" in failure.message
    assert failure.origin == "tool" and not failure.retryable

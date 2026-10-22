from copy import deepcopy

import pytest

from docfit.template.materialization.body_interfaces import body_interfaces
from docfit.template.materialization.models import AcceptedResolvedSpan
from docfit.template.source_spans import resolve_semantic_judgments
from tests.contract.test_template_materialization_readiness import _current_case, _registry


def _spans(tmp_path, *, middle="cleanup", second_field="body.paragraph"):
    registry = _registry(tmp_path / "registry.yaml")
    inventory, review = _current_case(registry, role="body_structure", field_id="body.paragraph")
    judgment = {"source_entry_id": "source-entry-title", "parts": [
        {"text": "论", "role": "body_structure", "field_id": "body.paragraph"},
        {"text": "文", "role": middle},
        {"text": "题", "role": "body_structure", "field_id": second_field},
        {"text": "目", "role": "body_structure", "field_id": second_field},
    ]}
    if middle == "body_structure":
        judgment["parts"][1]["field_id"] = "body.heading.outline1"
    return [AcceptedResolvedSpan.from_json(s) for s in resolve_semantic_judgments(
        inventory=inventory, judgments=[judgment],
    )]


@pytest.mark.parametrize("middle", ["cleanup", "style_only"])
def test_adjacent_survivors_form_one_interface_without_rewriting_spans(tmp_path, middle):
    spans = _spans(tmp_path, middle=middle)
    before = deepcopy([s.to_json() for s in spans])
    groups = body_interfaces(spans, cut_points={})
    assert len(groups) == 1
    group = groups[0]
    assert [s.part_index for s in group.source_spans] == [0, 2, 3]
    assert [s.part_index for s in group.removed_spans] == [1]
    assert group.anchor.slot_ref == spans[0].slot_ref
    assert group.coalescence()["source_spans"] == [before[i] for i in (0, 2, 3)]
    assert [s.to_json() for s in spans] == before


@pytest.mark.parametrize("middle", ["fixed_label", "manual_region", "generated_content"])
def test_retained_content_is_a_coalescence_barrier(tmp_path, middle):
    # generated_content is tested at the accepted-span boundary, without inventing a field.
    spans = _spans(tmp_path, middle=middle)
    assert [len(g.source_spans) for g in body_interfaces(spans, cut_points={})] == [1, 2]


def test_other_field_is_a_coalescence_barrier(tmp_path):
    spans = _spans(tmp_path, second_field="body.heading.outline1")
    assert [len(g.source_spans) for g in body_interfaces(spans, cut_points={})] == [1, 2]


@pytest.mark.parametrize("cut", [1, 2, 3])
def test_accepted_unit_cut_is_never_crossed(tmp_path, cut):
    spans = _spans(tmp_path)
    groups = body_interfaces(spans, cut_points={"source-entry-title": {cut}})
    assert len(groups) == 2
    for group in groups:
        start = group.source_spans[0].accepted_json["text_start"]
        end = group.source_spans[-1].accepted_json["text_end"]
        assert not start < cut < end


def test_reordering_or_missing_separator_cannot_join_spans(tmp_path):
    spans = _spans(tmp_path)
    assert len(body_interfaces([spans[2], spans[0]], cut_points={})) == 2
    assert len(body_interfaces([spans[0], spans[2]], cut_points={})) == 2


@pytest.mark.parametrize("locator", ["/body/p[2]/r[1]", "/body/tbl[1]/tr[1]/tc[1]/p[1]/r[1]",
                                   "/body/p[1]/r[1]/pict[1]/shape[1]/p[1]/r[1]"])
def test_different_or_composite_carrier_cannot_join_spans(tmp_path, locator):
    spans = _spans(tmp_path)
    changed = spans[2].to_json()
    changed["word_fragments"][0]["locator"] = locator
    spans[2] = AcceptedResolvedSpan.from_json(changed)
    assert len(body_interfaces(spans, cut_points={})) == 3

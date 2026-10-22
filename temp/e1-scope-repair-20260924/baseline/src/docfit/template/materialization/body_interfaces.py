"""Physical body interfaces derived from accepted, ordered source spans.

Deleting accepted cleanup/style notes may make equal field responsibilities
adjacent. Coalescing those survivors changes no source judgment or source span;
all contributing spans and removed separators remain explicit provenance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from docfit.template.materialization.models import AcceptedResolvedSpan
from docfit.template.source_spans import (
    TextSourceExtent,
    parse_source_span_ref,
    resolve_source_span,
)
from docfit.tools.runtime import JsonObject


@dataclass(frozen=True)
class BodyInterface:
    source_spans: tuple[AcceptedResolvedSpan, ...]
    removed_spans: tuple[AcceptedResolvedSpan, ...] = ()

    @property
    def anchor(self) -> AcceptedResolvedSpan:
        return self.source_spans[0]

    @property
    def slot_ref(self) -> str:
        value = self.anchor.slot_ref
        if value is None:
            raise ValueError("A body interface requires an accepted field binding.")
        return value

    def coalescence(self) -> JsonObject | None:
        if len(self.source_spans) == 1:
            return None
        return {
            "rule": "adjacent-body-interface/v1",
            "anchor_slot_ref": self.anchor.slot_ref,
            "source_spans": [span.to_json() for span in self.source_spans],
            "removed_spans": [span.to_json() for span in self.removed_spans],
        }


def body_paragraph_carrier(locator: object) -> str | None:
    """An exact paragraph under body or table cells, excluding drawing/textbox descendants."""
    if not isinstance(locator, str):
        return None
    segments = locator.strip("/").split("/")
    if not segments or segments[0] != "body":
        return None
    index = 1
    while index + 2 < len(segments) and all(
        segments[index + offset].startswith(tag + "[")
        for offset, tag in enumerate(("tbl", "tr", "tc"))
    ):
        index += 3
    if index >= len(segments) or not segments[index].startswith("p["):
        return None
    if any(segment.startswith(("p[", "tbl[", "shape[", "drawing[", "pict["))
           for segment in segments[index + 1:]):
        return None
    return "/" + "/".join(segments[:index + 1])


def _paragraph(span: AcceptedResolvedSpan) -> str | None:
    carriers: set[str] = set()
    for fragment in span.word_fragments:
        carrier = body_paragraph_carrier(fragment.get("locator"))
        if carrier is None:
            return None
        carriers.add(carrier)
    return next(iter(carriers)) if len(carriers) == 1 else None


def _extent(span: AcceptedResolvedSpan) -> TextSourceExtent | None:
    parsed = parse_source_span_ref(span.span_ref)
    return parsed[1].extent if parsed and isinstance(parsed[1].extent, TextSourceExtent) else None


def _can_join(
    group: BodyInterface,
    separators: Sequence[AcceptedResolvedSpan],
    right: AcceptedResolvedSpan,
    *,
    cut_points: dict[str, set[int]],
) -> bool:
    left = group.source_spans[-1]
    anchor = group.anchor
    carrier = _paragraph(anchor)
    chain = (left, *separators, right)
    if carrier is None or anchor.field_id != right.field_id or any(
        span.source_entry_id != anchor.source_entry_id
        or span.source_snapshot_sha256 != anchor.source_snapshot_sha256
        or span.source_inventory_digest != anchor.source_inventory_digest
        or _paragraph(span) != carrier
        for span in chain
    ):
        return False
    anchor_extent = _extent(anchor)
    extents = [_extent(span) for span in chain]
    if anchor_extent is None or any(extent is None for extent in extents):
        return False
    for before, after in zip(chain, chain[1:], strict=False):
        before_extent, after_extent = _extent(before), _extent(after)
        if before_extent is None or after_extent is None or (
            before_extent.end != after_extent.start or before.part_index + 1 != after.part_index
        ):
            return False
    right_extent = _extent(right)
    assert right_extent is not None
    return not any(
        anchor_extent.start < cut < right_extent.end
        for cut in cut_points.get(anchor.source_entry_id, set())
    )


def body_interfaces(
    spans: Sequence[AcceptedResolvedSpan], *, cut_points: dict[str, set[int]],
) -> tuple[BodyInterface, ...]:
    """Coalesce only equal surviving neighbors in one entry, paragraph and unit.

    The caller supplies the validated partition's cuts. Retained content, a
    different field, malformed adjacency or composite carriers remain barriers.
    This does not select a field, change a role, or synthesize a bounding span.
    """
    groups: list[BodyInterface] = []
    separators: list[AcceptedResolvedSpan] = []
    neighbor: BodyInterface | None = None
    for span in spans:
        if span.role in {"cleanup", "style_only"}:
            if neighbor is not None:
                separators.append(span)
            continue
        if span.role != "body_structure" or span.field_id is None:
            neighbor = None
            separators = []
            continue
        if neighbor is not None and _can_join(neighbor, separators, span, cut_points=cut_points):
            neighbor = BodyInterface(
                (*neighbor.source_spans, span), (*neighbor.removed_spans, *separators),
            )
            groups[-1] = neighbor
        else:
            neighbor = BodyInterface((span,))
            groups.append(neighbor)
        separators = []
    return tuple(groups)


def validate_coalescence(
    record: JsonObject, *, anchor: AcceptedResolvedSpan, partition: JsonObject,
    cut_points: dict[str, set[int]],
) -> None:
    """Verify all member ranges, deletion separators and the stable anchor at handoff."""
    raw_sources, raw_removed = record.get("source_spans"), record.get("removed_spans")
    if (
        not isinstance(raw_sources, list) or len(raw_sources) < 2
        or not isinstance(raw_removed, list)
    ):
        raise ValueError("Coalesced body interface lacks complete source ranges.")
    sources = [AcceptedResolvedSpan.from_json(raw) for raw in raw_sources]
    removed = [AcceptedResolvedSpan.from_json(raw) for raw in raw_removed]
    if sources[0].to_json() != anchor.to_json():
        raise ValueError("Coalesced body interface changed its source anchor.")
    if any(span.role not in {"cleanup", "style_only"} for span in removed):
        raise ValueError("Coalesced body interface crosses retained content.")
    if any(span.role != "body_structure" for span in sources):
        raise ValueError("Coalesced body interface contains another semantic role.")
    spans = sorted((*sources, *removed), key=lambda span: span.part_index)
    if len({span.part_index for span in spans}) != len(spans):
        raise ValueError("Coalesced body interface duplicates a source part.")
    for span in spans:
        parsed = parse_source_span_ref(span.span_ref)
        assert parsed is not None
        if not span.matches(resolve_source_span(inventory=partition, source_span=parsed[1])):
            raise ValueError("Coalesced body interface differs from its source partition.")
    groups = body_interfaces(spans, cut_points=cut_points)
    if len(groups) != 1 or groups[0].coalescence() != record:
        raise ValueError("Coalesced body interface is not a continuous surviving field range.")

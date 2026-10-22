"""Exact source-entry span resolution shared by Harness review consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docfit.template.source_entries import (
    CanonicalSourceInventory,
    validate_canonical_source_entries,
)
from docfit.tools.runtime import JsonObject, sha256_json


@dataclass(frozen=True, slots=True)
class TextSourceExtent:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class WholeEntrySourceExtent:
    """The sole extent of a source entry that has no text coordinates."""


SourceExtent = TextSourceExtent | WholeEntrySourceExtent


@dataclass(frozen=True, slots=True)
class SourceSpan:
    source_entry_id: str
    extent: SourceExtent


@dataclass(frozen=True, slots=True)
class WordFragment:
    object_id: str
    locator: str
    source_start: int | None
    source_end: int | None
    object_start: int | None
    object_end: int | None
    text: str
    object_ref: JsonObject | None
    fingerprint: str | None

    def to_json(self) -> JsonObject:
        result: JsonObject = {
            "object_id": self.object_id,
            "locator": self.locator,
            "text": self.text,
        }
        if self.source_start is None:
            result["extent"] = {"kind": "whole_entry"}
        else:
            result.update(
                {
                    "source_text_start": self.source_start,
                    "source_text_end": self.source_end,
                    "object_text_start": self.object_start,
                    "object_text_end": self.object_end,
                }
            )
        if self.object_ref is not None:
            result["object_ref"] = dict(self.object_ref)
        if self.fingerprint is not None:
            result["fingerprint"] = self.fingerprint
        return result


@dataclass(frozen=True, slots=True)
class ResolvedSourceSpan:
    source_snapshot_sha256: str
    inventory_digest: str
    source_span: SourceSpan
    expected_source_content: str
    word_fragments: tuple[WordFragment, ...]


class SourceSpanResolutionError(ValueError):
    def __init__(self, blockers: list[JsonObject]) -> None:
        super().__init__("Source spans could not be resolved exactly.")
        self.blockers = blockers


def resolve_semantic_judgments(
    *,
    inventory: JsonObject,
    judgments: list[JsonObject],
) -> list[JsonObject]:
    """Resolve Agent ordered parts without search, trimming, or parent fallback."""

    from docfit.template.unit_source import source_unit_cut_points, validate_inventory_partition

    units = validate_inventory_partition(inventory)
    cut_points = source_unit_cut_points(units)
    source_snapshot_sha256 = _source_snapshot_sha256(inventory)
    entries = validate_canonical_source_entries(inventory.get("source_entries"))
    entries_by_id = {entry.source_entry_id: entry for entry in entries}
    _validate_object_source_entries(inventory, set(entries_by_id))
    inventory_digest = _inventory_digest(inventory)
    resolved: list[JsonObject] = []
    blockers: list[JsonObject] = []
    seen_source_entry_ids: set[str] = set()

    for judgment_index, judgment in enumerate(judgments):
        source_entry_id = judgment.get("source_entry_id")
        if not isinstance(source_entry_id, str) or source_entry_id not in entries_by_id:
            blockers.append(
                _blocker(
                    "ordered_part_source_entry_unknown",
                    judgment_index,
                    None,
                    "The semantic judgment does not name a current canonical source entry.",
                )
            )
            continue
        if source_entry_id in seen_source_entry_ids:
            blockers.append(
                {
                    **_blocker(
                        "source_span_duplicate_entry_judgment",
                        judgment_index,
                        None,
                        (
                            "Each canonical source entry must be partitioned by exactly "
                            "one judgment."
                        ),
                    ),
                    "source_entry_ids": [source_entry_id],
                }
            )
            continue
        seen_source_entry_ids.add(source_entry_id)
        entry = entries_by_id[source_entry_id]
        parts = judgment.get("parts")
        if not isinstance(parts, list):
            continue
        if entry.text == "":
            _resolve_structural_judgment(
                inventory=inventory,
                entry=entry,
                judgment=judgment,
                judgment_index=judgment_index,
                source_snapshot_sha256=source_snapshot_sha256,
                inventory_digest=inventory_digest,
                resolved=resolved,
                blockers=blockers,
            )
            continue
        cursor = 0
        text_mismatch = False
        for part_index, part in enumerate(parts):
            if not isinstance(part, dict) or not isinstance(part.get("text"), str):
                continue
            part_text = part["text"]
            if part_text == "":
                blockers.append(
                    {
                        **_blocker(
                            "ordered_part_empty_for_text_entry",
                            judgment_index,
                            part_index,
                            (
                                "An empty part can target only a canonical empty "
                                "whole-entry source entry."
                            ),
                        ),
                        "source_entry_id": source_entry_id,
                        "source_text_length": len(entry.text),
                    }
                )
                continue
            end = cursor + len(part_text)
            if end > len(entry.text) or entry.text[cursor:end] != part_text:
                expected_text = entry.text[cursor:end]
                mismatch_offset = _first_mismatch_offset(
                    expected_text, part_text, absolute_start=cursor
                )
                blockers.append(
                    {
                        **_blocker(
                            "ordered_part_text_mismatch",
                            judgment_index,
                            part_index,
                            (
                                "Ordered part text must equal the source substring at the "
                                "next exact offset."
                            ),
                        ),
                        "source_entry_id": source_entry_id,
                        "expected_text": expected_text,
                        "submitted_text": part_text,
                        "source_text_length": len(entry.text),
                        "expected_text_length": len(expected_text),
                        "submitted_text_length": len(part_text),
                        "mismatch_offset": mismatch_offset,
                        "first_difference": _character_difference(
                            expected_text, part_text, mismatch_offset - cursor
                        ),
                        **_expected_boundary_whitespace_affordance(entry.text[cursor:]),
                        "text_start": cursor,
                        "text_end": end,
                    }
                )
                # A mismatched part has no accepted end offset. Comparing later
                # parts at the unchanged cursor invents errors in a valid suffix.
                # Recheck the remaining partition after this mismatch is repaired.
                text_mismatch = True
                break
            if any(cursor < cut < end for cut in cut_points.get(source_entry_id, set())):
                blockers.append(
                    {
                        **_blocker(
                            "ordered_part_crosses_unit_cut",
                            judgment_index,
                            part_index,
                            "Split ordered parts at every accepted unit boundary.",
                        ),
                        "source_entry_id": source_entry_id,
                    }
                )
                cursor = end
                continue
            source_span = SourceSpan(source_entry_id, TextSourceExtent(cursor, end))
            try:
                exact = resolve_source_span(
                    inventory=inventory,
                    source_span=source_span,
                    source_snapshot_sha256=source_snapshot_sha256,
                    inventory_digest=inventory_digest,
                )
            except SourceSpanResolutionError as error:
                for blocker in error.blockers:
                    blockers.append(
                        {
                            **blocker,
                            "field": f"semantic_judgments[{judgment_index}].parts[{part_index}]",
                        }
                    )
                cursor = end
                continue
            span_ref = source_span_ref(
                source_snapshot_sha256=source_snapshot_sha256,
                source_span=source_span,
            )
            span: JsonObject = {
                "span_ref": span_ref,
                "scope": {"source_entry_id": source_entry_id},
                "judgment_index": judgment_index,
                "part_index": part_index,
                "role": part.get("role"),
                "text": part_text,
                "source_entry_id": source_entry_id,
                "text_start": cursor,
                "text_end": end,
                "extent": {"kind": "text", "start": cursor, "end": end},
                "expected_source_content": exact.expected_source_content,
                "source_snapshot_sha256": exact.source_snapshot_sha256,
                "source_inventory_digest": exact.inventory_digest,
                "word_fragments": [item.to_json() for item in exact.word_fragments],
                "covered_object_ids": list(
                    dict.fromkeys(item.object_id for item in exact.word_fragments)
                ),
            }
            field_id = part.get("field_id")
            if isinstance(field_id, str) and field_id.strip():
                normalized_field_id = field_id.strip()
                span["field_id"] = normalized_field_id
                span["slot_ref"] = f"{span_ref};field_id={normalized_field_id}"
            resolved.append(span)
            cursor = end
        if not text_mismatch and cursor != len(entry.text):
            blockers.append(
                {
                    **_blocker(
                        "ordered_part_text_gap",
                        judgment_index,
                        None,
                        "Ordered parts must cover the complete source entry without omissions.",
                    ),
                    "source_entry_id": source_entry_id,
                    "text_start": cursor,
                    "text_end": len(entry.text),
                    "uncovered_text": entry.text[cursor:],
                    "source_text_length": len(entry.text),
                    "covered_text_length": cursor,
                    "uncovered_text_length": len(entry.text) - cursor,
                    **_whitespace_gap_affordance(entry.text[cursor:]),
                }
            )

    missing_source_entry_ids = [
        entry.source_entry_id
        for entry in entries
        if entry.source_entry_id not in seen_source_entry_ids
    ]
    if missing_source_entry_ids:
        blockers.append(
            {
                "code": "source_span_missing_entry_judgment",
                "source_entry_ids": missing_source_entry_ids,
                "message": ("Every canonical source entry must have exactly one ordered judgment."),
            }
        )

    if blockers:
        raise SourceSpanResolutionError(blockers)
    return resolved


def _first_mismatch_offset(
    expected: str,
    submitted: str,
    *,
    absolute_start: int,
) -> int:
    for offset, (expected_character, submitted_character) in enumerate(
        zip(expected, submitted, strict=False)
    ):
        if expected_character != submitted_character:
            return absolute_start + offset
    return absolute_start + min(len(expected), len(submitted))


def _character_difference(expected: str, submitted: str, offset: int) -> JsonObject:
    result: JsonObject = {}
    for name, text in (("expected", expected), ("submitted", submitted)):
        character = text[offset : offset + 1]
        result[name] = {
            "character": character,
            "codepoint": f"U+{ord(character):04X}" if character else None,
            "end_of_text": not character,
        }
    return result


def _whitespace_gap_affordance(text: str) -> JsonObject:
    if not text or not text.isspace():
        return {}
    return {"uncovered_whitespace_codepoints": _codepoint_runs(text)}


def _expected_boundary_whitespace_affordance(text: str) -> JsonObject:
    leading = len(text) - len(text.lstrip())
    trailing = len(text) - len(text.rstrip())
    result: JsonObject = {}
    if leading:
        result["expected_leading_whitespace_count"] = leading
        result["expected_leading_whitespace_codepoints"] = _codepoint_runs(text[:leading])
    if trailing:
        result["expected_trailing_whitespace_count"] = trailing
        result["expected_trailing_whitespace_codepoints"] = _codepoint_runs(
            text[len(text) - trailing :]
        )
    return result


def _codepoint_runs(text: str) -> list[str]:
    runs: list[str] = []
    for character in text:
        codepoint = f"U+{ord(character):04X}"
        if runs and runs[-1].startswith(f"{codepoint} × "):
            count = int(runs[-1].rsplit(" ", 1)[-1]) + 1
            runs[-1] = f"{codepoint} × {count}"
        elif runs and runs[-1] == codepoint:
            runs[-1] = f"{codepoint} × 2"
        else:
            runs.append(codepoint)
    return runs


def resolve_source_span(
    *,
    inventory: JsonObject,
    source_span: SourceSpan,
    source_snapshot_sha256: str | None = None,
    inventory_digest: str | None = None,
) -> ResolvedSourceSpan:
    entries = validate_canonical_source_entries(inventory.get("source_entries"))
    entry = next(
        (item for item in entries if item.source_entry_id == source_span.source_entry_id),
        None,
    )
    if entry is None:
        raise SourceSpanResolutionError(
            [{"code": "source_span_entry_unknown", "source_entry_id": source_span.source_entry_id}]
        )
    if isinstance(source_span.extent, WholeEntrySourceExtent):
        return _resolve_whole_entry_span(
            inventory=inventory,
            entry=entry,
            source_span=source_span,
            source_snapshot_sha256=source_snapshot_sha256,
            inventory_digest=inventory_digest,
        )
    if entry.text == "" or (
        source_span.extent.start < 0
        or source_span.extent.end <= source_span.extent.start
        or source_span.extent.end > len(entry.text)
    ):
        raise SourceSpanResolutionError(
            [{"code": "source_span_out_of_bounds", "source_entry_id": source_span.source_entry_id}]
        )

    candidates = [
        item
        for item in entry.provenance
        if item.text_span is not None
        and item.text_span[1] > source_span.extent.start
        and item.text_span[0] < source_span.extent.end
    ]
    selected: list[tuple[int, Any]] = []
    for offset in range(source_span.extent.start, source_span.extent.end):
        covering = [
            item
            for item in candidates
            if item.text_span is not None and item.text_span[0] <= offset < item.text_span[1]
        ]
        if not covering:
            raise SourceSpanResolutionError(
                [
                    {
                        "code": "source_span_fragment_gap",
                        "source_entry_id": source_span.source_entry_id,
                    }
                ]
            )
        max_depth = max(_locator_depth(item.locator) for item in covering)
        finest = [item for item in covering if _locator_depth(item.locator) == max_depth]
        identities = {(item.object_id, item.locator, item.text_span) for item in finest}
        if len(identities) != 1:
            raise SourceSpanResolutionError(
                [
                    {
                        "code": "source_span_fragment_ambiguous",
                        "source_entry_id": source_span.source_entry_id,
                    }
                ]
            )
        selected.append((offset, finest[0]))

    fragments: list[WordFragment] = []
    group_start = source_span.extent.start
    group_item = selected[0][1]
    for offset, item in selected[1:]:
        if item != group_item:
            fragments.append(_word_fragment(entry.text, group_item, group_start, offset))
            group_start = offset
            group_item = item
    fragments.append(_word_fragment(entry.text, group_item, group_start, source_span.extent.end))
    return ResolvedSourceSpan(
        source_snapshot_sha256=source_snapshot_sha256 or _source_snapshot_sha256(inventory),
        inventory_digest=inventory_digest or _inventory_digest(inventory),
        source_span=source_span,
        expected_source_content=entry.text[source_span.extent.start : source_span.extent.end],
        word_fragments=tuple(fragments),
    )


def review_resolved_spans_match(
    *,
    inventory: JsonObject,
    semantic_judgments: list[JsonObject],
) -> bool:
    agent_judgments = [
        {key: value for key, value in judgment.items() if key != "resolved_spans"}
        for judgment in semantic_judgments
    ]
    try:
        expected = resolve_semantic_judgments(
            inventory=inventory,
            judgments=agent_judgments,
        )
    except (SourceSpanResolutionError, ValueError):
        return False
    actual = [
        span
        for judgment in semantic_judgments
        for span in judgment.get("resolved_spans", [])
        if isinstance(span, dict)
    ]
    return actual == expected


def source_span_ref(
    *,
    source_snapshot_sha256: str,
    source_span: SourceSpan,
) -> str:
    """Derive a stable ref from immutable source identity and exact extent."""

    extent = source_span.extent
    encoded_extent = (
        f"text[{extent.start}:{extent.end}]"
        if isinstance(extent, TextSourceExtent)
        else "whole_entry"
    )
    return (
        f"source_entry_id={source_span.source_entry_id};"
        f"extent={encoded_extent};"
        f"source_snapshot_sha256={source_snapshot_sha256}"
    )


def parse_source_span_ref(value: str) -> tuple[str, SourceSpan] | None:
    """Parse only the canonical text SourceSpan reference representation."""

    segments = value.split(";")
    if len(segments) != 3 or any(segment.count("=") != 1 for segment in segments):
        return None
    parsed = dict(segment.split("=", 1) for segment in segments)
    if set(parsed) != {"source_entry_id", "extent", "source_snapshot_sha256"}:
        return None
    source_entry_id = parsed["source_entry_id"]
    source_snapshot_sha256 = parsed["source_snapshot_sha256"]
    extent = parsed["extent"]
    if (
        not source_entry_id.startswith("source-entry-")
        or len(source_snapshot_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_snapshot_sha256)
    ):
        return None
    if extent == "whole_entry":
        return source_snapshot_sha256, SourceSpan(
            source_entry_id=source_entry_id,
            extent=WholeEntrySourceExtent(),
        )
    if not extent.startswith("text[") or not extent.endswith("]"):
        return None
    bounds = extent[5:-1].split(":", 1)
    if len(bounds) != 2 or not all(bound.isdigit() for bound in bounds):
        return None
    start, end = (int(bound) for bound in bounds)
    if end <= start:
        return None
    return source_snapshot_sha256, SourceSpan(
        source_entry_id=source_entry_id,
        extent=TextSourceExtent(start, end),
    )


def _resolve_structural_judgment(
    *,
    inventory: JsonObject,
    entry: Any,
    judgment: JsonObject,
    judgment_index: int,
    source_snapshot_sha256: str,
    inventory_digest: str,
    resolved: list[JsonObject],
    blockers: list[JsonObject],
) -> None:
    parts = judgment.get("parts")
    if (
        not isinstance(parts, list)
        or len(parts) != 1
        or not isinstance(parts[0], dict)
        or parts[0].get("text") != ""
    ):
        blockers.append(
            {
                **_blocker(
                    "whole_entry_part_invalid",
                    judgment_index,
                    None,
                    (
                        "A structural source entry must use exactly one empty-text part; "
                        "its role carries the Agent's semantic judgment."
                    ),
                ),
                "source_entry_id": entry.source_entry_id,
            }
        )
        return
    part = parts[0]
    source_span = SourceSpan(entry.source_entry_id, WholeEntrySourceExtent())
    try:
        exact = resolve_source_span(
            inventory=inventory,
            source_span=source_span,
            source_snapshot_sha256=source_snapshot_sha256,
            inventory_digest=inventory_digest,
        )
    except SourceSpanResolutionError as error:
        blockers.extend(
            {
                **blocker,
                "field": f"semantic_judgments[{judgment_index}].parts[0]",
            }
            for blocker in error.blockers
        )
        return
    span_ref = source_span_ref(
        source_snapshot_sha256=source_snapshot_sha256,
        source_span=source_span,
    )
    span: JsonObject = {
        "span_ref": span_ref,
        "scope": {"source_entry_id": entry.source_entry_id},
        "judgment_index": judgment_index,
        "part_index": 0,
        "role": part.get("role"),
        "text": "",
        "source_entry_id": entry.source_entry_id,
        "extent": {"kind": "whole_entry"},
        "expected_source_content": "",
        "source_snapshot_sha256": exact.source_snapshot_sha256,
        "source_inventory_digest": exact.inventory_digest,
        "word_fragments": [item.to_json() for item in exact.word_fragments],
        "covered_object_ids": list(dict.fromkeys(item.object_id for item in exact.word_fragments)),
    }
    field_id = part.get("field_id")
    if isinstance(field_id, str) and field_id.strip():
        normalized_field_id = field_id.strip()
        span["field_id"] = normalized_field_id
        span["slot_ref"] = f"{span_ref};field_id={normalized_field_id}"
    resolved.append(span)


def _resolve_whole_entry_span(
    *,
    inventory: JsonObject,
    entry: Any,
    source_span: SourceSpan,
    source_snapshot_sha256: str | None,
    inventory_digest: str | None,
) -> ResolvedSourceSpan:
    provenance = [item for item in entry.provenance if item.extent_kind == "whole_entry"]
    if entry.text != "" or len(provenance) != len(entry.provenance) or not provenance:
        raise SourceSpanResolutionError(
            [
                {
                    "code": "source_span_extent_kind_mismatch",
                    "source_entry_id": source_span.source_entry_id,
                }
            ]
        )
    # A blank block can be reported together with nested empty runs. The source
    # entry represents the whole structural block, so its outermost reversible
    # carrier is the exact target; nested aliases do not create competing spans.
    outer_depth = min(_locator_depth(item.locator) for item in provenance)
    outer_carriers = [item for item in provenance if _locator_depth(item.locator) == outer_depth]
    identities = {(item.object_id, item.locator) for item in outer_carriers}
    if len(identities) != 1:
        raise SourceSpanResolutionError(
            [
                {
                    "code": "source_span_fragment_ambiguous",
                    "source_entry_id": source_span.source_entry_id,
                }
            ]
        )
    item = outer_carriers[0]
    fragment = WordFragment(
        object_id=item.object_id,
        locator=item.locator,
        source_start=None,
        source_end=None,
        object_start=None,
        object_end=None,
        text="",
        object_ref=item.object_ref,
        fingerprint=item.fingerprint,
    )
    return ResolvedSourceSpan(
        source_snapshot_sha256=source_snapshot_sha256 or _source_snapshot_sha256(inventory),
        inventory_digest=inventory_digest or _inventory_digest(inventory),
        source_span=source_span,
        expected_source_content="",
        word_fragments=(fragment,),
    )


def _source_snapshot_sha256(inventory: JsonObject) -> str:
    canonical = inventory.get("canonical_source_inventory")
    value = (
        canonical.get("source_snapshot_sha256")
        if isinstance(canonical, dict)
        else inventory.get("document_sha256")
    )
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source inventory must bind a source snapshot sha256.")
    return value.strip()


def _validate_object_source_entries(
    inventory: JsonObject,
    source_entry_ids: set[str],
) -> None:
    raw_objects = inventory.get("objects")
    if not isinstance(raw_objects, list):
        return
    for item in raw_objects:
        if not isinstance(item, dict):
            raise ValueError("Harness inventory objects must be objects.")
        source_entry_id = item.get("source_entry_id")
        if not isinstance(source_entry_id, str) or source_entry_id not in source_entry_ids:
            raise ValueError("Every Harness inventory object must map to a canonical source entry.")


def _inventory_digest(inventory: JsonObject) -> str:
    canonical = inventory.get("canonical_source_inventory")
    if isinstance(canonical, dict):
        parsed = CanonicalSourceInventory.from_json(canonical)
        projected_entries = validate_canonical_source_entries(inventory.get("source_entries"))
        canonical_by_id = {entry.source_entry_id: entry for entry in parsed.source_entries}
        if any(canonical_by_id.get(entry.source_entry_id) != entry for entry in projected_entries):
            raise ValueError("Harness source entries do not match the canonical inventory.")
        if inventory.get("document_sha256") != parsed.source_snapshot_sha256:
            raise ValueError("Harness inventory does not match the canonical source snapshot.")
        return parsed.inventory_digest
    return sha256_json(
        {
            "source_snapshot_sha256": _source_snapshot_sha256(inventory),
            "source_entries": inventory.get("source_entries"),
        }
    )


def _locator_depth(locator: str) -> int:
    return len([part for part in locator.split("/") if part])


def _word_fragment(entry_text: str, provenance: Any, start: int, end: int) -> WordFragment:
    assert provenance.text_span is not None
    provenance_start, _provenance_end = provenance.text_span
    return WordFragment(
        object_id=provenance.object_id,
        locator=provenance.locator,
        source_start=start,
        source_end=end,
        object_start=start - provenance_start,
        object_end=end - provenance_start,
        text=entry_text[start:end],
        object_ref=provenance.object_ref,
        fingerprint=provenance.fingerprint,
    )


def _blocker(
    code: str,
    judgment_index: int,
    part_index: int | None,
    message: str,
) -> JsonObject:
    field = f"semantic_judgments[{judgment_index}]"
    if part_index is not None:
        field += f".parts[{part_index}]"
    return {"code": code, "field": field, "message": message}

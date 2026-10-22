"""Canonical source entry model for template source localization."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, cast

from docfit.tools.runtime import JsonObject, sha256_json

SOURCE_ENTRY_SCHEMA_VERSION = "docfit-canonical-source-entry/v1"
SOURCE_INVENTORY_SCHEMA_VERSION = "docfit-canonical-source-inventory/v1"
SOURCE_ENTRY_ID_PREFIX = "source-entry-"
OBJECT_ID_BACKEND_ALIAS_ROLE = "backend_alias"
_COVERAGE_KINDS = {
    "break",
    "fieldChar",
    "instrText",
    "paragraph",
    "picture",
    "run",
    "sdt",
    "shape",
    "tab",
    "table",
}
_FINE_TEXT_SPAN_KINDS = {"run", "sdt"}
_STRUCTURAL_EXTENT_KINDS = {"break", "fieldChar", "instrText", "picture", "tab"}
_FORBIDDEN_FIELD_KEYS = frozenset(
    {
        "field_id",
        "field_ids",
        "registry_field_id",
        "registry_field_ids",
        "semantic_field",
    }
)


@dataclass(frozen=True, slots=True)
class SourceOrder:
    block: int
    inline: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.block, int)
            or isinstance(self.block, bool)
            or self.block < 0
            or not isinstance(self.inline, int)
            or isinstance(self.inline, bool)
            or self.inline < 0
        ):
            raise ValueError("source_order must contain non-negative integer block and inline.")

    @classmethod
    def from_json(cls, value: Any) -> SourceOrder:
        if not isinstance(value, dict):
            raise ValueError("source_order must be an object.")
        # __post_init__ validates untrusted values, including missing keys.
        return cls(block=cast(int, value.get("block")), inline=cast(int, value.get("inline")))

    def to_json(self) -> JsonObject:
        return {"block": self.block, "inline": self.inline}


@dataclass(frozen=True, slots=True)
class SourceEntryProvenance:
    object_id: str
    locator: str
    text_span: tuple[int, int] | None = None
    object_ref: JsonObject | None = None
    fingerprint: str | None = None
    extent_kind: str = "text"

    def __post_init__(self) -> None:
        object_id = _non_empty_string(self.object_id, "provenance.object_id")
        locator = _non_empty_string(self.locator, "provenance.locator")
        if self.extent_kind not in {"text", "whole_entry"}:
            raise ValueError("provenance extent kind must be text or whole_entry.")
        if self.extent_kind == "whole_entry":
            if self.text_span is not None:
                raise ValueError("whole_entry provenance must not use fake text offsets.")
        else:
            if self.text_span is None:
                raise ValueError("text provenance requires text_span.")
            start, end = self.text_span
            if not isinstance(start, int) or isinstance(start, bool):
                raise ValueError("provenance.text_span start must be an integer.")
            if not isinstance(end, int) or isinstance(end, bool):
                raise ValueError("provenance.text_span end must be an integer.")
            if start < 0 or end < start:
                raise ValueError("provenance.text_span must be an ordered non-negative span.")
        object.__setattr__(self, "object_id", object_id)
        object.__setattr__(self, "locator", locator)

    @classmethod
    def from_json(cls, value: Any) -> SourceEntryProvenance:
        if not isinstance(value, dict):
            raise ValueError("provenance entries must be objects.")
        _reject_field_keys(value, context="provenance")
        extent = value.get("extent")
        extent_kind = extent.get("kind") if isinstance(extent, dict) else "text"
        span = value.get("text_span")
        text_span: tuple[int, int] | None = None
        if extent_kind == "text":
            if (
                not isinstance(span, list | tuple)
                or len(span) != 2
                or not all(isinstance(item, int) and not isinstance(item, bool) for item in span)
            ):
                raise ValueError("provenance.text_span must be a two-item integer array.")
            text_span = (span[0], span[1])
        elif extent_kind != "whole_entry" or span is not None:
            raise ValueError("structural provenance requires extent.kind=whole_entry.")
        object_ref = value.get("object_ref")
        fingerprint = value.get("fingerprint")
        return cls(
            object_id=cast(str, value.get("object_id")),
            locator=cast(str, value.get("locator")),
            text_span=text_span,
            object_ref=dict(object_ref) if isinstance(object_ref, dict) else None,
            fingerprint=fingerprint.strip()
            if isinstance(fingerprint, str) and fingerprint.strip()
            else None,
            extent_kind=cast(str, extent_kind),
        )

    def to_json(self) -> JsonObject:
        result: JsonObject = {
            "object_id": self.object_id,
            "locator": self.locator,
        }
        if self.extent_kind == "whole_entry":
            result["extent"] = {"kind": "whole_entry"}
        elif self.text_span is not None:
            result["text_span"] = [self.text_span[0], self.text_span[1]]
        if self.object_ref:
            result["object_ref"] = dict(self.object_ref)
        if self.fingerprint is not None:
            result["fingerprint"] = self.fingerprint
        return result


@dataclass(frozen=True, slots=True)
class CanonicalSourceEntry:
    source_entry_id: str
    text: str
    entry_type: str
    source_order: SourceOrder
    provenance: tuple[SourceEntryProvenance, ...]

    def __post_init__(self) -> None:
        source_entry_id = _non_empty_string(self.source_entry_id, "source_entry_id")
        if not source_entry_id.startswith(SOURCE_ENTRY_ID_PREFIX):
            raise ValueError("source_entry_id must use the source-entry- prefix.")
        if not isinstance(self.text, str):
            raise ValueError("text must be a string.")
        entry_type = _non_empty_string(self.entry_type, "entry_type")
        if not isinstance(self.source_order, SourceOrder):
            raise ValueError("source_order must be a SourceOrder.")
        if not self.provenance:
            raise ValueError("provenance must contain at least one raw source object.")
        for item in self.provenance:
            if not isinstance(item, SourceEntryProvenance):
                raise ValueError("provenance must contain SourceEntryProvenance values.")
            if item.text_span is not None:
                _start, end = item.text_span
                if end > len(self.text):
                    raise ValueError("provenance.text_span must be inside source entry text.")
        object.__setattr__(self, "source_entry_id", source_entry_id)
        object.__setattr__(self, "entry_type", entry_type)

    @classmethod
    def from_json(cls, value: Any) -> CanonicalSourceEntry:
        if not isinstance(value, dict):
            raise ValueError("canonical source entry must be an object.")
        _reject_field_keys(value, context="source_entry")
        raw_provenance = value.get("provenance")
        if not isinstance(raw_provenance, list) or not raw_provenance:
            raise ValueError("provenance must be a non-empty array.")
        provenance = tuple(
            SourceEntryProvenance.from_json(item) for item in raw_provenance
        )
        return cls(
            source_entry_id=cast(str, value.get("source_entry_id")),
            text=cast(str, value.get("text")),
            entry_type=cast(str, value.get("entry_type")),
            source_order=SourceOrder.from_json(value.get("source_order")),
            provenance=provenance,
        )

    def to_json(self) -> JsonObject:
        return {
            "source_entry_id": self.source_entry_id,
            "text": self.text,
            "entry_type": self.entry_type,
            "source_order": self.source_order.to_json(),
            "extent": (
                {"kind": "text", "start": 0, "end": len(self.text)}
                if self.text
                else {"kind": "whole_entry"}
            ),
            "provenance": [item.to_json() for item in self.provenance],
        }


@dataclass(frozen=True, slots=True)
class CanonicalSourceInventory:
    source_snapshot_sha256: str
    source_entries: tuple[CanonicalSourceEntry, ...]
    inventory_digest: str

    @classmethod
    def from_json(cls, value: Any) -> CanonicalSourceInventory:
        if not isinstance(value, dict):
            raise ValueError("canonical source inventory must be an object.")
        if value.get("schema_version") != SOURCE_INVENTORY_SCHEMA_VERSION:
            raise ValueError("canonical source inventory schema_version is unsupported.")
        source_snapshot_sha256 = _source_snapshot_sha256(
            value.get("source_snapshot_sha256")
        )
        entries = validate_canonical_source_entries(value.get("source_entries"))
        expected_digest = _source_inventory_digest(
            source_snapshot_sha256=source_snapshot_sha256,
            source_entries=entries,
        )
        digest = _non_empty_string(value.get("inventory_digest"), "inventory_digest")
        if digest != expected_digest:
            raise ValueError("canonical source inventory digest does not match its contents.")
        return cls(
            source_snapshot_sha256=source_snapshot_sha256,
            source_entries=entries,
            inventory_digest=digest,
        )

    def to_json(self) -> JsonObject:
        return {
            "schema_version": SOURCE_INVENTORY_SCHEMA_VERSION,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "entry_count": len(self.source_entries),
            "source_entries": [entry.to_json() for entry in self.source_entries],
            "inventory_digest": self.inventory_digest,
        }


def source_entry_id_for_entry(
    *,
    source_sha256: str,
    text: str,
    entry_type: str,
    source_order: SourceOrder,
    provenance: tuple[SourceEntryProvenance, ...],
) -> str:
    """Create a stable ID for one normalized source entry, not one raw object."""

    payload = {
        "source_sha256": _non_empty_string(source_sha256, "source_sha256"),
        "text": text,
        "entry_type": _non_empty_string(entry_type, "entry_type"),
        "source_order": source_order.to_json(),
        "provenance": [
            {
                "object_id": item.object_id,
                "locator": item.locator,
                **(
                    {"text_span": [item.text_span[0], item.text_span[1]]}
                    if item.text_span is not None
                    else {"extent": {"kind": "whole_entry"}}
                ),
            }
            for item in provenance
        ],
    }
    return f"{SOURCE_ENTRY_ID_PREFIX}{sha256_json(payload)[:24]}"


def validate_canonical_source_entries(entries: Any) -> tuple[CanonicalSourceEntry, ...]:
    if not isinstance(entries, list):
        raise ValueError("source_entries must be an array.")
    parsed = tuple(CanonicalSourceEntry.from_json(item) for item in entries)
    ids = [item.source_entry_id for item in parsed]
    if len(ids) != len(set(ids)):
        raise ValueError("source_entry_id values must be unique.")
    orders = [(item.source_order.block, item.source_order.inline) for item in parsed]
    if len(orders) != len(set(orders)):
        raise ValueError("source_order values must be unique.")
    return parsed


def build_canonical_source_inventory(
    *,
    source_snapshot_sha256: str,
    inspected_objects: list[Any],
) -> CanonicalSourceInventory:
    """Build the one snapshot-bound source inventory before any unit projection."""

    source_hash = _source_snapshot_sha256(source_snapshot_sha256)
    seen_object_ids: set[str] = set()
    for index, raw in enumerate(inspected_objects):
        if not isinstance(raw, dict):
            raise ValueError(
                "canonical_source_inventory_missing_provenance: "
                f"inspected_objects[{index}] must be an object."
            )
        locator = locator_for_item(raw)
        object_id = object_id_for_item(raw)
        if not locator or object_id is None:
            raise ValueError(
                "canonical_source_inventory_missing_provenance: "
                f"inspected_objects[{index}] requires locator and object_ref.object_id."
            )
        if object_id in seen_object_ids:
            raise ValueError(
                "canonical_source_inventory_contradictory_provenance: "
                f"duplicate object_id {object_id}."
            )
        seen_object_ids.add(object_id)
    entries: list[CanonicalSourceEntry] = []
    groups = _structuralize_ancestor_container_groups(
        _group_scoped_objects(inspected_objects)
    )
    for group in groups:
        unsupported_kinds = sorted(
            {
                kind_for_item(item)
                for item in group
                if kind_for_item(item) not in _COVERAGE_KINDS
            }
        )
        if unsupported_kinds:
            raise ValueError(
                "canonical_source_inventory_unsupported_structure: "
                f"{', '.join(unsupported_kinds)}"
            )
        text = _text_for_group(group)
        source_order = SourceOrder(block=len(entries) + 1, inline=0)
        provenance = _source_entry_provenance_for_group(group, entry_text=text)
        if not provenance:
            raise ValueError("canonical source entry has no reversible Word provenance.")
        entry_type = _entry_type_for_group(group)
        source_entry_id = source_entry_id_for_entry(
            source_sha256=source_hash,
            text=text,
            entry_type=entry_type,
            source_order=source_order,
            provenance=provenance,
        )
        entries.append(
            CanonicalSourceEntry(
                source_entry_id=source_entry_id,
                text=text,
                entry_type=entry_type,
                source_order=source_order,
                provenance=provenance,
            )
        )
    source_entries = tuple(entries)
    return CanonicalSourceInventory(
        source_snapshot_sha256=source_hash,
        source_entries=source_entries,
        inventory_digest=_source_inventory_digest(
            source_snapshot_sha256=source_hash,
            source_entries=source_entries,
        ),
    )


def select_source_entries_for_objects(
    inventory: CanonicalSourceInventory,
    object_ids: list[str] | tuple[str, ...] | set[str],
) -> tuple[CanonicalSourceEntry, ...]:
    """Project entries from an existing inventory without creating IDs or text."""

    selected_ids = set(object_ids)
    return tuple(
        entry
        for entry in inventory.source_entries
        if any(item.object_id in selected_ids for item in entry.provenance)
    )


def source_entry_by_object_id(
    entries: tuple[CanonicalSourceEntry, ...],
) -> dict[str, CanonicalSourceEntry]:
    mapping: dict[str, CanonicalSourceEntry] = {}
    for entry in entries:
        for provenance in entry.provenance:
            mapping.setdefault(provenance.object_id, entry)
    return mapping


def project_source_entries_onto_objects(
    scoped_objects: list[Any],
    entries: tuple[CanonicalSourceEntry, ...],
    *,
    source_sha256: str,
) -> list[Any]:
    """Attach normalized source_entry_id values to raw objects for legacy projections."""

    entry_by_object_id = source_entry_by_object_id(entries)
    projected: list[Any] = []
    for item in scoped_objects:
        if not isinstance(item, dict):
            projected.append(item)
            continue
        object_id = object_id_for_item(item)
        if object_id is None:
            projected.append(item)
            continue
        entry = entry_by_object_id.get(object_id)
        if entry is None:
            projected.append(item)
            continue
        projected.append(
            {
                **item,
                "source_entry_id": entry.source_entry_id,
                "source_entry_ref": source_entry_ref_for_entry(
                    entry,
                    source_sha256=source_sha256,
                ),
            }
        )
    return projected


def source_entry_ref_for_entry(
    entry: CanonicalSourceEntry,
    *,
    source_sha256: str,
) -> JsonObject:
    return {
        "source_entry_id": entry.source_entry_id,
        "source_sha256": _non_empty_string(source_sha256, "source_sha256"),
        "entry_type": entry.entry_type,
        "source_order": entry.source_order.to_json(),
        "provenance": [item.to_json() for item in entry.provenance],
    }


def object_id_for_item(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    object_id = item.get("object_id")
    if isinstance(object_id, str) and object_id.strip():
        return object_id.strip()
    object_ref = item.get("object_ref")
    if isinstance(object_ref, dict):
        nested = object_ref.get("object_id")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def locator_for_item(item: Any) -> str:
    locator = item.get("locator") if isinstance(item, dict) else None
    return locator if isinstance(locator, str) else ""


def kind_for_item(item: Any) -> str:
    item_type = item.get("type") if isinstance(item, dict) else None
    return item_type if isinstance(item_type, str) else ""


def _block_locator(locator: str) -> str:
    for marker in ("/r[", "/hyperlink[", "/fldSimple["):
        if marker in locator:
            return locator.split(marker, 1)[0]
    return locator


def _group_scoped_objects(scoped_objects: list[Any]) -> list[list[JsonObject]]:
    groups: OrderedDict[str, list[JsonObject]] = OrderedDict()
    for item in scoped_objects:
        if not isinstance(item, dict):
            continue
        locator = locator_for_item(item)
        if not locator:
            continue
        group_locator = (
            locator
            if kind_for_item(item) in {"picture", "shape"}
            else _block_locator(locator)
        )
        groups.setdefault(group_locator, []).append(item)
    return list(groups.values())


def _group_locator(group: list[JsonObject]) -> str:
    if not group:
        return ""
    locator = locator_for_item(group[0])
    return (
        locator
        if kind_for_item(group[0]) in {"picture", "shape"}
        else _block_locator(locator)
    )


def _normalized_text_for_container_comparison(value: str) -> str:
    return "".join(value.split())


def _structuralize_ancestor_container_groups(
    groups: list[list[JsonObject]],
) -> list[list[JsonObject]]:
    """Keep aggregate containers as structure when descendants own their text."""

    roots = [_group_locator(group) for group in groups]
    ancestor_container_indexes = {
        index
        for index, (root, group) in enumerate(zip(roots, groups, strict=True))
        if root
        and any(
            kind_for_item(item) in {"sdt", "table"}
            and locator_for_item(item).rstrip("/") == root.rstrip("/")
            for item in group
        )
        and any(
            candidate.rstrip("/") != root.rstrip("/")
            and candidate.startswith(f"{root.rstrip('/')}/")
            for candidate in roots
            if candidate
        )
    }
    normalized: list[list[JsonObject]] = []
    for index, (root, group) in enumerate(zip(roots, groups, strict=True)):
        if index not in ancestor_container_indexes:
            normalized.append(group)
            continue
        container_text = _text_for_group(group)
        descendant_text = "".join(
            _text_for_group(candidate_group)
            for candidate_index, (candidate_root, candidate_group) in enumerate(
                zip(roots, groups, strict=True)
            )
            if candidate_index not in ancestor_container_indexes
            and candidate_root.startswith(f"{root.rstrip('/')}/")
        )
        if (
            not container_text
            or not descendant_text
            or _normalized_text_for_container_comparison(container_text)
            != _normalized_text_for_container_comparison(descendant_text)
        ):
            normalized.append(group)
            continue
        normalized.append(
            [
                {**item, "text": ""}
                if kind_for_item(item) in {"sdt", "table"}
                and locator_for_item(item).rstrip("/") == root.rstrip("/")
                else item
                for item in group
            ]
        )
    return normalized


def _text_for_group(items: list[JsonObject]) -> str:
    paragraph_text = next(
        (
            item["text"]
            for item in items
            if kind_for_item(item) == "paragraph"
            and isinstance(item.get("text"), str)
        ),
        None,
    )
    fine_texts = [
        item["text"]
        for item in items
        if kind_for_item(item) in _FINE_TEXT_SPAN_KINDS
        and isinstance(item.get("text"), str)
    ]
    if isinstance(paragraph_text, str) and paragraph_text:
        return paragraph_text
    if fine_texts:
        combined_fine_text = "".join(fine_texts)
        if combined_fine_text:
            return combined_fine_text
    structural_text = "".join(
        item["text"]
        for item in items
        if kind_for_item(item) in _COVERAGE_KINDS
        and kind_for_item(item) not in _STRUCTURAL_EXTENT_KINDS
        and kind_for_item(item) != "paragraph"
        and isinstance(item.get("text"), str)
    )
    if structural_text:
        return structural_text
    return paragraph_text if isinstance(paragraph_text, str) else ""


def _entry_type_for_group(group: list[JsonObject]) -> str:
    kinds = [kind_for_item(item) for item in group if kind_for_item(item)]
    if not kinds:
        return "text"
    if "paragraph" in kinds or "run" in kinds or "instrText" in kinds:
        return "text"
    if "table" in kinds:
        return "table"
    if "picture" in kinds:
        return "picture"
    return kinds[0]


def _source_entry_provenance_for_group(
    group: list[JsonObject],
    *,
    entry_text: str,
) -> tuple[SourceEntryProvenance, ...]:
    raw_spans = _object_spans_for_group(group=group, entry_text=entry_text)
    provenance: list[SourceEntryProvenance] = []
    seen_object_ids: set[str] = set()
    for item in group:
        object_id = object_id_for_item(item)
        locator = locator_for_item(item)
        if object_id is None or not locator or object_id in seen_object_ids:
            continue
        text_span = raw_spans.get(object_id)
        item_text = item.get("text")
        structural = (
            kind_for_item(item) in _STRUCTURAL_EXTENT_KINDS
            or not isinstance(item_text, str)
            or item_text == ""
        )
        if text_span is None and not structural:
            raise ValueError(
                "canonical_source_inventory_unsupported_text_alignment: "
                f"{locator} cannot be mapped without changing source text."
            )
        object_ref = item.get("object_ref")
        expected_fingerprint = (
            object_ref.get("expected_fingerprint")
            if isinstance(object_ref, dict)
            and isinstance(object_ref.get("expected_fingerprint"), str)
            else item.get("expected_fingerprint")
        )
        provenance.append(
            SourceEntryProvenance(
                object_id=object_id,
                locator=locator,
                text_span=text_span,
                object_ref=dict(object_ref) if isinstance(object_ref, dict) else None,
                fingerprint=expected_fingerprint
                if isinstance(expected_fingerprint, str) and expected_fingerprint.strip()
                else None,
                extent_kind="whole_entry" if text_span is None else "text",
            )
        )
        seen_object_ids.add(object_id)
    return tuple(provenance)


def _object_spans_for_group(
    *,
    group: list[JsonObject],
    entry_text: str,
) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for item in group:
        if kind_for_item(item) not in _COVERAGE_KINDS:
            continue
        object_id = object_id_for_item(item)
        if object_id is None:
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if not text:
            continue
        if text == entry_text:
            spans[object_id] = (0, len(entry_text))
            continue
    fine_spans = _aligned_text_spans(
        entry_text=entry_text,
        items=[
            item
            for item in group
            if kind_for_item(item) in _FINE_TEXT_SPAN_KINDS
        ],
    )
    spans.update(fine_spans)
    if spans:
        return spans
    return _aligned_text_spans(
        entry_text=entry_text,
        items=[
            item
            for item in group
            if kind_for_item(item) in _COVERAGE_KINDS
        ],
    )


def _aligned_text_spans(
    *,
    entry_text: str,
    items: list[JsonObject],
) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    cursor = 0
    for item in items:
        object_id = object_id_for_item(item)
        if object_id is None:
            continue
        raw_text = item.get("text")
        if not isinstance(raw_text, str):
            continue
        text = raw_text
        if not text:
            continue
        start = entry_text.find(text, cursor)
        if start < 0:
            return {}
        end = start + len(text)
        spans[object_id] = (start, end)
        cursor = end
    if not spans:
        return {}
    return spans


def _source_snapshot_sha256(value: Any) -> str:
    source_hash = _non_empty_string(value, "source_snapshot_sha256")
    if len(source_hash) != 64 or any(
        character not in "0123456789abcdef" for character in source_hash
    ):
        raise ValueError("source_snapshot_sha256 must be a lowercase SHA-256 hex digest.")
    return source_hash


def _source_inventory_digest(
    *,
    source_snapshot_sha256: str,
    source_entries: tuple[CanonicalSourceEntry, ...],
) -> str:
    return sha256_json(
        {
            "schema_version": SOURCE_INVENTORY_SCHEMA_VERSION,
            "source_snapshot_sha256": source_snapshot_sha256,
            "source_entries": [entry.to_json() for entry in source_entries],
        }
    )


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value.strip()


def _reject_field_keys(value: JsonObject, *, context: str) -> None:
    forbidden = sorted(_FORBIDDEN_FIELD_KEYS.intersection(value))
    if forbidden:
        raise ValueError(
            f"{context} must not contain content field binding keys: {forbidden}."
        )

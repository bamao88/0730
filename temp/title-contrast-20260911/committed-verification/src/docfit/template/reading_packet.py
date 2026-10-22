"""Build Agent-readable unit packets from post-unit source objects."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from docfit.template.source_entries import CanonicalSourceEntry

JsonObject = dict[str, Any]

READING_PACKET_VERSION = "docfit_unit_reading_packet_v1"
READING_BLOCK_SHAPE = "agent_reading_blocks_v1"
SOURCE_ENTRY_READING_SHAPE = "agent_source_entries_v1"
READING_COVERAGE_CONTRACT: JsonObject = {
    "agent_covers": (
        "source_entries[].source_entry_id with ordered parts[].text over each "
        "source_entries[].text value; reading_blocks/ranges are view context only"
    ),
    "harness_maps_to": "canonical source entry inventory and resolved source spans",
}

_AGENT_VISIBLE_READING_BLOCK_KEYS = (
    "block_id",
    "range_id",
    "unit_range_id",
    "order",
    "text",
    "semantic_cues",
    "style_summary",
)
_AGENT_VISIBLE_READING_RANGE_KEYS = (
    "range_id",
    "kind",
    "unit_id",
    "block_count",
    "block_ids",
)
_AGENT_VISIBLE_LAYOUT_CONTEXT_KEYS = (
    "order",
    "text",
    "semantic_cues",
    "style_summary",
)
_COVERAGE_KINDS = {"paragraph", "run", "table", "picture", "sdt", "shape"}
_FINE_TEXT_SPAN_KINDS = {"run", "sdt"}
_STYLE_KEYS = (
    "alignment",
    "font.ea",
    "font.latin",
    "font",
    "size",
    "bold",
    "italic",
)


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


def source_entry_id_for_item(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    source_entry_id = item.get("source_entry_id")
    if isinstance(source_entry_id, str) and source_entry_id.strip():
        return source_entry_id.strip()
    source_entry_ref = item.get("source_entry_ref")
    if isinstance(source_entry_ref, dict):
        nested = source_entry_ref.get("source_entry_id")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def locator_for_item(item: Any) -> str:
    locator = item.get("locator") if isinstance(item, dict) else None
    return locator if isinstance(locator, str) else ""


def kind_for_item(item: Any) -> str:
    item_type = item.get("type") if isinstance(item, dict) else None
    return item_type if isinstance(item_type, str) else ""


def _agent_visible_value(value: Any) -> Any | None:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, list):
        strings = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return strings
    if isinstance(value, dict):
        compact = {
            key: item.strip()
            for key, item in value.items()
            if isinstance(key, str) and isinstance(item, str) and item.strip()
        }
        return compact
    return None


def _agent_visible_projection(item: Any, *, keys: tuple[str, ...]) -> JsonObject:
    if not isinstance(item, dict):
        return {}
    visible: JsonObject = {}
    for key in keys:
        value = _agent_visible_value(item.get(key))
        if value not in (None, "", [], {}):
            visible[key] = value
    return visible


def agent_visible_unit_reading_packet(packet: JsonObject) -> JsonObject:
    """Project an internal reading packet to the runtime Agent semantic surface."""
    visible: JsonObject = {
        "schema_version": str(packet.get("schema_version") or READING_PACKET_VERSION),
        "unit": _agent_visible_projection(
            packet.get("unit"),
            keys=("unit_id", "unit_name"),
        ),
        "reading_blocks": [
            item
            for raw in packet.get("reading_blocks", [])
            if (item := _agent_visible_projection(raw, keys=_AGENT_VISIBLE_READING_BLOCK_KEYS))
        ],
        "reading_ranges": [
            item
            for raw in packet.get("reading_ranges", [])
            if (item := _agent_visible_projection(raw, keys=_AGENT_VISIBLE_READING_RANGE_KEYS))
        ],
        "layout_context": [
            item
            for raw in packet.get("layout_context", [])
            if (item := _agent_visible_projection(raw, keys=_AGENT_VISIBLE_LAYOUT_CONTEXT_KEYS))
        ],
    }
    source_entries = _agent_visible_source_entries(packet.get("source_entries"))
    if source_entries:
        visible["source_entries"] = source_entries
    field_id_vocabulary = packet.get("field_id_vocabulary")
    if isinstance(field_id_vocabulary, dict):
        visible["field_id_vocabulary"] = field_id_vocabulary
    digest = packet.get("field_vocabulary_digest")
    if isinstance(digest, str) and digest.strip():
        visible["field_vocabulary_digest"] = digest.strip()
    return visible


def _agent_visible_source_entries(value: Any) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    entries: list[JsonObject] = []
    for raw in value:
        item = _source_entry_payload(raw)
        if not item:
            continue
        source_entry_id = item.get("source_entry_id")
        text = item.get("text")
        if not isinstance(source_entry_id, str) or not source_entry_id.strip():
            continue
        if not isinstance(text, str):
            continue
        visible: JsonObject = {
            "source_entry_id": source_entry_id.strip(),
            "text": text,
        }
        entry_type = item.get("entry_type")
        if isinstance(entry_type, str) and entry_type.strip():
            visible["entry_type"] = entry_type.strip()
        source_order = item.get("source_order")
        if isinstance(source_order, dict):
            block = source_order.get("block")
            inline = source_order.get("inline")
            if isinstance(block, int) and not isinstance(block, bool) and isinstance(
                inline,
                int,
            ) and not isinstance(inline, bool):
                visible["source_order"] = {"block": block, "inline": inline}
        semantic_cues = item.get("semantic_cues")
        if isinstance(semantic_cues, list):
            cues = [
                cue.strip()
                for cue in semantic_cues
                if isinstance(cue, str) and cue.strip()
            ]
            if cues:
                visible["semantic_cues"] = cues
        style_summary = _agent_visible_value(item.get("style_summary"))
        if isinstance(style_summary, dict) and style_summary:
            visible["style_summary"] = style_summary
        entries.append(visible)
    return entries


def locator_covers(parent: str, child: str) -> bool:
    normalized = parent.rstrip("/")
    return child == normalized or child.startswith(f"{normalized}/")


def locator_related(first: str, second: str) -> bool:
    return first == second or first.startswith(f"{second}/") or second.startswith(f"{first}/")


def _ordered_body_block_locators(objects: list[Any]) -> list[str]:
    locators: OrderedDict[str, None] = OrderedDict()
    for item in objects:
        if not isinstance(item, dict):
            continue
        locator = locator_for_item(item)
        if not locator.startswith("/body/"):
            continue
        block_locator = _block_locator(locator)
        if block_locator:
            locators.setdefault(block_locator, None)
    return list(locators)


def _span_endpoint_block_index(
    boundary_locator: str,
    *,
    block_locators: list[str],
    endpoint: str,
) -> int | None:
    boundary_block = _block_locator(boundary_locator)
    candidates = [
        index
        for index, block_locator in enumerate(block_locators)
        if locator_related(block_locator, boundary_locator)
        or locator_related(block_locator, boundary_block)
    ]
    if not candidates:
        return None
    return min(candidates) if endpoint == "start" else max(candidates)


def objects_for_locator_span(
    objects: list[Any],
    *,
    start_locator: str,
    end_locator: str,
) -> list[Any]:
    block_locators = _ordered_body_block_locators(objects)
    start_index = _span_endpoint_block_index(
        start_locator,
        block_locators=block_locators,
        endpoint="start",
    )
    end_index = _span_endpoint_block_index(
        end_locator,
        block_locators=block_locators,
        endpoint="end",
    )
    if start_index is not None and end_index is not None:
        lower, upper = sorted((start_index, end_index))
        selected_blocks = set(block_locators[lower : upper + 1])
        return [
            item
            for item in objects
            if isinstance(item, dict)
            and isinstance(item.get("locator"), str)
            and str(item["locator"]).startswith("/body/")
            and _block_locator(str(item["locator"])) in selected_blocks
        ]

    indexes = [
        index
        for index, item in enumerate(objects)
        if isinstance(item, dict)
        and isinstance(item.get("locator"), str)
        and (
            locator_related(str(item["locator"]), start_locator)
            or locator_related(str(item["locator"]), end_locator)
        )
    ]
    if not indexes:
        return []
    first = min(indexes)
    last = max(indexes)
    return [
        item
        for item in objects[first : last + 1]
        if isinstance(item, dict)
        and isinstance(item.get("locator"), str)
        and str(item["locator"]).startswith("/body/")
    ]


def _block_locator(locator: str) -> str:
    for marker in ("/r[", "/hyperlink[", "/fldSimple["):
        if marker in locator:
            return locator.split(marker, 1)[0]
    return locator


def _text_for_group(items: list[JsonObject]) -> str:
    paragraph_text = next(
        (
            str(item["text"])
            for item in items
            if kind_for_item(item) == "paragraph"
            and isinstance(item.get("text"), str)
            and item["text"]
        ),
        None,
    )
    if paragraph_text is not None:
        return paragraph_text
    combined = "".join(
        str(item.get("text", "")) for item in items if isinstance(item.get("text"), str)
    )
    return combined


def _aligned_object_text_spans(
    *,
    block_text: str,
    items: list[JsonObject],
    covered_object_ids: set[str],
) -> list[JsonObject]:
    spans: list[JsonObject] = []
    cursor = 0
    for item in items:
        object_id = object_id_for_item(item)
        if object_id is None or object_id not in covered_object_ids:
            continue
        raw_text = item.get("text")
        if not isinstance(raw_text, str):
            continue
        text = raw_text
        if not text:
            continue
        start = block_text.find(text, cursor)
        if start < 0 or block_text[cursor:start]:
            return []
        end = start + len(text)
        spans.append(
            {
                "object_id": object_id,
                "text_start": start,
                "text_end": end,
                "text": text,
            }
        )
        cursor = end
    if not spans or block_text[cursor:]:
        return []
    return spans


def _object_text_spans_for_group(
    *,
    group: list[JsonObject],
    block_text: str,
    block_object_ids: list[str],
) -> list[JsonObject]:
    covered_object_ids = set(block_object_ids)
    fine_items = [
        item
        for item in group
        if kind_for_item(item) in _FINE_TEXT_SPAN_KINDS
    ]
    fine_spans = _aligned_object_text_spans(
        block_text=block_text,
        items=fine_items,
        covered_object_ids=covered_object_ids,
    )
    if fine_spans:
        return fine_spans
    coverage_items = [
        item
        for item in group
        if kind_for_item(item) in _COVERAGE_KINDS
        and kind_for_item(item) not in _FINE_TEXT_SPAN_KINDS
    ]
    return _aligned_object_text_spans(
        block_text=block_text,
        items=coverage_items,
        covered_object_ids=covered_object_ids,
    )


def _style_summary(items: list[JsonObject]) -> JsonObject:
    summary: JsonObject = {}
    for item in items:
        raw_format = item.get("format_hint")
        if not isinstance(raw_format, dict):
            raw_format = item.get("format")
        if not isinstance(raw_format, dict):
            continue
        for key in _STYLE_KEYS:
            value = raw_format.get(key)
            if isinstance(value, str) and value.strip() and key not in summary:
                summary[key] = value.strip()
    style = next(
        (
            item.get("style")
            for item in items
            if isinstance(item.get("style"), str) and item["style"].strip()
        ),
        None,
    )
    if isinstance(style, str):
        summary.setdefault("style", style.strip())
    return summary


def _semantic_cues(text: str, style: JsonObject, *, kinds: set[str]) -> list[str]:
    compact = "".join(text.split())
    cues: list[str] = []
    alignment = str(style.get("alignment", "")).casefold()
    if alignment == "center" and text:
        cues.append("centered_heading_candidate")
    if len(compact) <= 40 and any(
        token in compact for token in ("声明", "目录", "摘要", "正文", "参考文献")
    ):
        cues.append("unit_heading_candidate")
    if "签名" in compact:
        cues.append("signature_area_candidate")
        cues.append("field_slot_candidate")
    if {"年", "月", "日"} <= set(compact):
        cues.append("date_area_candidate")
        cues.append("field_slot_candidate")
    if text.endswith((":", "：")):
        cues.append("label_candidate")
    if any(token in compact for token in ("本人郑重声明", "法律结果", "知识产权争议")):
        cues.append("fixed_declaration_text_candidate")
    if any(
        token in compact for token in ("填写说明", "模板说明", "请填写", "示例", "样例", "删除")
    ):
        cues.append("instruction_or_sample_candidate")
    if not text:
        cues.append("blank_layout_candidate")
    if kinds & {"table", "shape", "picture", "sdt"}:
        cues.append("carrier_or_layout_candidate")
    return list(dict.fromkeys(cues))


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


def build_unit_reading_packet(
    *,
    unit: JsonObject,
    scoped_objects: list[Any],
    coverage_object_ids: list[str] | None = None,
    source_entries: list[Any] | tuple[Any, ...] | None = None,
    field_id_vocabulary: JsonObject | None = None,
) -> JsonObject:
    raw_unit_id = unit.get("unit_id")
    if not isinstance(raw_unit_id, str) or not raw_unit_id.strip():
        raise ValueError("unit.unit_id is required to build unit reading packet ids.")
    unit_id = raw_unit_id.strip()
    unit_range_id = f"{unit_id}:range-whole-unit"
    coverage_filter = set(coverage_object_ids or [])
    reading_blocks: list[JsonObject] = []
    mappings: list[JsonObject] = []
    layout_context: list[JsonObject] = []
    source_entry_payloads = {
        str(payload["source_entry_id"]): payload
        for raw in source_entries or ()
        if (payload := _source_entry_payload(raw)) is not None
        and isinstance(payload.get("source_entry_id"), str)
    }

    for group in _group_scoped_objects(scoped_objects):
        block_object_ids: list[str] = []
        block_source_entry_ids: list[str] = []
        kinds = {kind_for_item(item) for item in group if kind_for_item(item)}
        for item in group:
            current_id = object_id_for_item(item)
            if current_id is None:
                continue
            if coverage_filter:
                if current_id in coverage_filter:
                    block_object_ids.append(current_id)
                    source_entry_id = source_entry_id_for_item(item)
                    if source_entry_id is not None:
                        block_source_entry_ids.append(source_entry_id)
            elif kind_for_item(item) in _COVERAGE_KINDS:
                block_object_ids.append(current_id)
                source_entry_id = source_entry_id_for_item(item)
                if source_entry_id is not None:
                    block_source_entry_ids.append(source_entry_id)

        unique_group_entry_ids = list(dict.fromkeys(block_source_entry_ids))
        canonical_payload = (
            source_entry_payloads.get(unique_group_entry_ids[0])
            if len(unique_group_entry_ids) == 1
            else None
        )
        canonical_text = canonical_payload.get("text") if canonical_payload else None
        text = canonical_text if isinstance(canonical_text, str) else _text_for_group(group)
        style = _style_summary(group)
        if not text:
            layout_context.append(
                {
                    "order": len(reading_blocks) + len(layout_context) + 1,
                    "text": text,
                    "semantic_cues": _semantic_cues(text, style, kinds=kinds),
                    "coverage_required": False,
                    **(
                        {"covered_object_count": len(dict.fromkeys(block_object_ids))}
                        if block_object_ids
                        else {}
                    ),
                }
            )
            continue
        if not block_object_ids:
            if "paragraph" in kinds:
                layout_context.append(
                    {
                        "order": len(reading_blocks) + len(layout_context) + 1,
                        "text": text,
                        "semantic_cues": _semantic_cues(text, style, kinds=kinds),
                        "coverage_required": False,
                    }
                )
            continue

        block_id = f"{unit_id}:block-{len(reading_blocks) + 1:04d}"
        range_id = f"{unit_id}:range-{len(reading_blocks) + 1:04d}"
        block: JsonObject = {
            "block_id": block_id,
            "range_id": range_id,
            "unit_range_id": unit_range_id,
            "order": len(reading_blocks) + 1,
            "text": text,
            "semantic_cues": _semantic_cues(text, style, kinds=kinds),
            "coverage_required": True,
            "covered_object_count": len(dict.fromkeys(block_object_ids)),
        }
        if style:
            block["style_summary"] = style
        reading_blocks.append(block)
        object_text_spans = _object_text_spans_for_group(
            group=group,
            block_text=text,
            block_object_ids=block_object_ids,
        )
        source_entry_by_object_id = {
            object_id: source_entry_id
            for item in group
            if (object_id := object_id_for_item(item)) is not None
            and (source_entry_id := source_entry_id_for_item(item)) is not None
        }
        source_entry_text_spans = _source_entry_text_spans(
            object_text_spans,
            source_entry_by_object_id=source_entry_by_object_id,
        )
        mappings.append(
            {
                "block_id": block_id,
                "range_id": range_id,
                "unit_range_id": unit_range_id,
                "unit_id": unit_id,
                "order": block["order"],
                **(
                    {"unit_name": str(unit["unit_name"]).strip()}
                    if isinstance(unit.get("unit_name"), str)
                    and str(unit["unit_name"]).strip()
                    else {}
                ),
                "text": text,
                "covered_object_ids": list(dict.fromkeys(block_object_ids)),
                **(
                    {"covered_source_entry_ids": list(dict.fromkeys(block_source_entry_ids))}
                    if block_source_entry_ids
                    else {}
                ),
                **({"object_text_spans": object_text_spans} if object_text_spans else {}),
                **(
                    {"source_entry_text_spans": source_entry_text_spans}
                    if source_entry_text_spans
                    else {}
                ),
            }
        )

    packet: JsonObject = {
        "schema_version": READING_PACKET_VERSION,
        "unit": {
            key: unit[key]
            for key in ("unit_id", "unit_name")
            if isinstance(unit.get(key), str) and str(unit[key]).strip()
        },
        "reading_blocks": reading_blocks,
        "reading_ranges": [
            {
                "range_id": unit_range_id,
                "kind": "whole_unit",
                "unit_id": unit_id,
                "block_count": len(reading_blocks),
                "block_ids": [
                    str(block["block_id"])
                    for block in reading_blocks
                    if isinstance(block.get("block_id"), str)
                ],
            }
        ]
        if reading_blocks
        else [],
        "reading_block_mappings": mappings,
        "layout_context": layout_context,
        "coverage_contract": dict(READING_COVERAGE_CONTRACT),
    }
    projected_source_entries = _source_entry_reading_projection(
        source_entries,
        reading_blocks=reading_blocks,
        mappings=mappings,
    )
    if projected_source_entries:
        packet["source_entries"] = projected_source_entries
    if field_id_vocabulary is not None:
        packet["field_id_vocabulary"] = field_id_vocabulary
        digest = field_id_vocabulary.get("digest")
        if isinstance(digest, str) and digest.strip():
            packet["field_vocabulary_digest"] = digest.strip()
    return packet


def _source_entry_payload(value: Any) -> JsonObject | None:
    if isinstance(value, CanonicalSourceEntry):
        return value.to_json()
    if isinstance(value, dict):
        return value
    return None


def _source_entry_reading_projection(
    source_entries: list[Any] | tuple[Any, ...] | None,
    *,
    reading_blocks: list[JsonObject],
    mappings: list[JsonObject],
) -> list[JsonObject]:
    if source_entries is None:
        return []
    blocks_by_id = {
        str(block["block_id"]): block
        for block in reading_blocks
        if isinstance(block.get("block_id"), str)
    }
    block_by_source_entry_id: dict[str, JsonObject] = {}
    for mapping in mappings:
        covered = mapping.get("covered_source_entry_ids")
        block_id = mapping.get("block_id")
        if not isinstance(covered, list) or not isinstance(block_id, str):
            continue
        block = blocks_by_id.get(block_id)
        if block is None:
            continue
        for source_entry_id in covered:
            if isinstance(source_entry_id, str) and source_entry_id.strip():
                block_by_source_entry_id.setdefault(source_entry_id.strip(), block)

    projected: list[JsonObject] = []
    for raw in source_entries:
        payload = _source_entry_payload(raw)
        if payload is None:
            continue
        source_entry_id = payload.get("source_entry_id")
        text = payload.get("text")
        if not isinstance(source_entry_id, str) or not source_entry_id.strip():
            continue
        if not isinstance(text, str):
            continue
        item: JsonObject = {
            "source_entry_id": source_entry_id.strip(),
            "text": text,
        }
        entry_type = payload.get("entry_type")
        if isinstance(entry_type, str) and entry_type.strip():
            item["entry_type"] = entry_type.strip()
        source_order = payload.get("source_order")
        if isinstance(source_order, dict):
            block = source_order.get("block")
            inline = source_order.get("inline")
            if (
                isinstance(block, int)
                and not isinstance(block, bool)
                and isinstance(inline, int)
                and not isinstance(inline, bool)
            ):
                item["source_order"] = {"block": block, "inline": inline}
        extent = payload.get("extent")
        if isinstance(extent, dict) and extent.get("kind") in {"text", "whole_entry"}:
            item["extent"] = dict(extent)
        block = block_by_source_entry_id.get(source_entry_id.strip())
        if block is not None:
            semantic_cues = block.get("semantic_cues")
            if isinstance(semantic_cues, list):
                cues = [
                    cue.strip()
                    for cue in semantic_cues
                    if isinstance(cue, str) and cue.strip()
                ]
                if cues:
                    item["semantic_cues"] = cues
            style_summary = block.get("style_summary")
            if isinstance(style_summary, dict) and style_summary:
                item["style_summary"] = dict(style_summary)
        projected.append(item)
    return projected


def _source_entry_text_spans(
    object_text_spans: list[JsonObject],
    *,
    source_entry_by_object_id: dict[str, str],
) -> list[JsonObject]:
    spans: list[JsonObject] = []
    for span in object_text_spans:
        object_id = span.get("object_id")
        if not isinstance(object_id, str):
            continue
        source_entry_id = source_entry_by_object_id.get(object_id)
        if source_entry_id is None:
            continue
        entry_span = {
            key: value
            for key, value in span.items()
            if key != "object_id"
        }
        entry_span["source_entry_id"] = source_entry_id
        spans.append(entry_span)
    return spans

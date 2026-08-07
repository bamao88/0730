"""Map OfficeCLI semantic objects and text selectors to LibreOffice PDF coordinates."""

from __future__ import annotations

import re
from typing import Any

from docfit.tools.inspection import Inspection
from docfit.tools.runtime import JsonObject, ToolFailure


def normalize_text(value: str) -> str:
    return "".join(value.split()).casefold()


def build_anchor_index(inspection: Inspection) -> JsonObject:
    anchors: list[JsonObject] = []
    objects = inspection.objects
    for index, item in enumerate(objects):
        before = next(
            (value.text for value in reversed(objects[:index]) if value.text.strip()),
            None,
        )
        after = next((value.text for value in objects[index + 1 :] if value.text.strip()), None)
        structure: JsonObject = {"locator": item.locator}
        table = re.fullmatch(r"/body/tbl\[(\d+)\]", item.locator)
        paragraph = re.search(r"/body/p(?:\[@paraId=[^]]+\]|\[(\d+)\])", item.locator)
        if table:
            structure["table_index"] = int(table.group(1))
        if paragraph and paragraph.group(1):
            structure["paragraph_index"] = int(paragraph.group(1))
        anchors.append(
            {
                "object_ref": item.object_ref,
                "kind": item.kind,
                "primary_text": item.text,
                "before_text": before,
                "after_text": after,
                "structural_context": structure,
            }
        )
    return {
        "schema_version": 2,
        "document_sha256": inspection.document_sha256,
        "anchors": anchors,
    }


def locate_text(
    index: JsonObject,
    text: str,
    *,
    occurrence: int | None = None,
) -> JsonObject:
    if not text.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="empty_text_selector",
            message="A text region selector requires non-empty text.",
        )
    matches = _matches(index, text)
    if not matches:
        return {"mapping_quality": "mapping_unavailable", "candidate_pages": []}
    if occurrence is not None:
        if occurrence < 1 or occurrence > len(matches):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="text_occurrence_out_of_range",
                message="The requested text occurrence does not exist in this render.",
            )
        return matches[occurrence - 1]
    if len(matches) == 1:
        return matches[0]
    return {
        "mapping_quality": "mapping_unavailable",
        "candidate_pages": sorted({int(item["page"]) for item in matches}),
        "candidate_count": len(matches),
    }


def locate_object(
    index: JsonObject,
    anchors: JsonObject,
    reference: Any,
) -> JsonObject:
    if not isinstance(reference, dict):
        return _object_input_error()
    if reference.get("document_sha256") != anchors.get("document_sha256"):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="stale_object_ref",
            message="The object_ref belongs to another DOCX snapshot; inspect again.",
            suggested_actions=("inspect_document_again",),
        )
    values = anchors.get("anchors")
    if not isinstance(values, list):
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="semantic_anchor_index_invalid",
            message="The render has no valid OfficeCLI semantic anchor index.",
        )
    anchor = next(
        (
            item
            for item in values
            if isinstance(item, dict)
            and isinstance(item.get("object_ref"), dict)
            and item["object_ref"].get("object_id") == reference.get("object_id")
        ),
        None,
    )
    if anchor is None or anchor.get("object_ref") != reference:
        return _object_input_error()
    primary = anchor.get("primary_text")
    if isinstance(primary, str) and primary.strip():
        candidates = _matches(index, primary)
        if len(candidates) == 1:
            result = dict(candidates[0])
            result["mapping_basis"] = [primary]
            return result
        resolved = _disambiguate(index, candidates, anchor)
        if resolved is not None:
            resolved["mapping_quality"] = "contextual"
            resolved["mapping_basis"] = [
                value
                for value in (primary, anchor.get("before_text"), anchor.get("after_text"))
                if isinstance(value, str) and value
            ]
            return resolved
        return {
            "mapping_quality": "mapping_unavailable",
            "candidate_pages": (
                sorted({int(item["page"]) for item in candidates})
                if candidates
                else _all_pages(index)
            ),
        }
    before = anchor.get("before_text")
    after = anchor.get("after_text")
    if isinstance(before, str) and isinstance(after, str):
        before_matches = _matches(index, before)
        after_matches = _matches(index, after)
        spans: list[JsonObject] = []
        for first in before_matches:
            for second in after_matches:
                if first["page"] != second["page"]:
                    continue
                first_box = first["bbox_pdf"]
                second_box = second["bbox_pdf"]
                if first_box[3] <= second_box[1]:
                    spans.append(
                        {
                            "page": first["page"],
                            "bbox_pdf": [
                                min(first_box[0], second_box[0]),
                                first_box[3],
                                max(first_box[2], second_box[2]),
                                second_box[1],
                            ],
                            "mapping_quality": "contextual",
                            "mapping_basis": [before, after],
                        }
                    )
        if len(spans) == 1:
            return spans[0]
        return {
            "mapping_quality": "mapping_unavailable",
            "candidate_pages": (
                sorted({int(item["page"]) for item in spans})
                or sorted(
                    {
                        int(item["page"])
                        for item in (*before_matches, *after_matches)
                    }
                )
                or _all_pages(index)
            ),
        }
    return {"mapping_quality": "mapping_unavailable", "candidate_pages": _all_pages(index)}


def _all_pages(index: JsonObject) -> list[int]:
    pages = index.get("pages")
    if not isinstance(pages, list):
        return []
    return [
        page
        for item in pages
        if isinstance(item, dict)
        and isinstance((page := item.get("page")), int)
        and page >= 1
    ]


def _matches(index: JsonObject, text: str) -> list[JsonObject]:
    target = normalize_text(text)
    pages = index.get("pages")
    if not isinstance(pages, list):
        return []
    results: list[JsonObject] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("words"), list):
            continue
        words = page["words"]
        for start in range(len(words)):
            combined = ""
            raw = ""
            boxes: list[list[float]] = []
            for word in words[start:]:
                if not isinstance(word, dict) or not isinstance(word.get("text"), str):
                    break
                combined += normalize_text(word["text"])
                raw += word["text"]
                bbox = word.get("bbox_pdf")
                if not isinstance(bbox, list) or len(bbox) != 4:
                    break
                boxes.append([float(value) for value in bbox])
                if combined == target:
                    results.append(
                        {
                            "page": page.get("page"),
                            "bbox_pdf": _union(boxes),
                            "mapping_quality": (
                                "exact_text" if raw == text else "normalized_text"
                            ),
                            "word_start": start,
                            "word_end": start + len(boxes) - 1,
                        }
                    )
                    break
                if len(combined) >= len(target):
                    break
    return results


def _disambiguate(
    index: JsonObject,
    candidates: list[JsonObject],
    anchor: JsonObject,
) -> JsonObject | None:
    before = anchor.get("before_text")
    after = anchor.get("after_text")
    before_matches = _matches(index, before) if isinstance(before, str) and before else []
    after_matches = _matches(index, after) if isinstance(after, str) and after else []
    scored: list[tuple[int, JsonObject]] = []
    for candidate in candidates:
        score = 0
        for item in before_matches:
            if item["page"] == candidate["page"] and item["word_end"] < candidate["word_start"]:
                score += 1
        for item in after_matches:
            if item["page"] == candidate["page"] and item["word_start"] > candidate["word_end"]:
                score += 1
        scored.append((score, candidate))
    if not scored:
        return None
    best = max(score for score, _ in scored)
    winners = [candidate for score, candidate in scored if score == best and score > 0]
    return dict(winners[0]) if len(winners) == 1 else None


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _object_input_error() -> JsonObject:
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="object_ref_not_in_render",
        message="The object_ref is not part of the DOCX snapshot bound to this render.",
        suggested_actions=("inspect_document_again",),
    )

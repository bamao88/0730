"""Readable, self-contained context for revising a semantic candidate."""

from __future__ import annotations

from copy import deepcopy

from docfit.template.reading_packet import agent_visible_unit_reading_packet
from docfit.template.semantic_batches import SemanticBatch, SemanticBatchCandidateLedger
from docfit.tools.runtime import JsonObject, ToolFailure


def _visible_judgment(value: object) -> JsonObject | None:
    if not isinstance(value, dict) or not isinstance(value.get("source_entry_id"), str):
        return None
    result = {
        key: deepcopy(value[key])
        for key in ("source_entry_id", "reason", "open_questions")
        if key in value
    }
    if isinstance(value.get("parts"), list):
        result["parts"] = [
            {
                key: deepcopy(part[key])
                for key in (
                    "text", "role", "field_id", "whitespace",
                    "leading_whitespace", "trailing_whitespace",
                    "whole_entry",
                )
                if key in part
            }
            for part in value["parts"]
            if isinstance(part, dict)
        ]
    return result


def build_revision_context(
    *,
    inventory: JsonObject,
    batch: SemanticBatch,
    ledger: SemanticBatchCandidateLedger,
    feedback: JsonObject,
    editable_source_entry_ids: tuple[str, ...] | None,
    previous_submission: JsonObject | None = None,
) -> JsonObject:
    """Include full affected text, neighboring evidence and previous decisions.

    Selection is mechanical. No role or field is inferred from source wording.
    Rejected output is projected onto the same semantic surface as accepted
    candidates; execution references never become a revision task for the Agent.
    """
    requested = set(editable_source_entry_ids or batch.source_entry_ids)
    related = set(requested)
    for blocker in feedback.get("blockers", []):
        if not isinstance(blocker, dict):
            continue
        if isinstance(blocker.get("source_entry_id"), str):
            related.add(blocker["source_entry_id"])
        related_ids = blocker.get("source_entry_ids")
        if isinstance(related_ids, list):
            related.update(item for item in related_ids if isinstance(item, str))
    entries: dict[str, JsonObject] = {}
    units: list[JsonObject] = []
    packets = inventory.get("unit_reading_packets", {})
    for packet in packets.values():
        visible = agent_visible_unit_reading_packet(packet)
        rows = visible.get("source_entries", [])
        indexes = {index for index, row in enumerate(rows) if row["source_entry_id"] in related}
        if not indexes:
            continue
        units.append({"unit": visible["unit"], "layout_context": visible["layout_context"]})
        window = {neighbor for index in indexes for neighbor in (index - 1, index, index + 1)}
        for index, row in enumerate(rows):
            if index in window:
                entries.setdefault(row["source_entry_id"], row)
    if not requested.issubset(entries):
        raise ToolFailure(
            status="error",
            origin="harness",
            code="semantic_revision_context_missing",
            message="The revision cannot be sent without the requested source text.",
        )
    previous = [
        projected
        for candidate in ledger.candidates
        for judgment in candidate.semantic_judgments
        if judgment.get("source_entry_id") in entries
        and (projected := _visible_judgment(judgment)) is not None
    ]
    if editable_source_entry_ids is not None and not requested.issubset(
        {judgment["source_entry_id"] for judgment in previous}
    ):
        raise ToolFailure(
            status="error",
            origin="harness",
            code="semantic_revision_baseline_missing",
            message="A scoped revision requires the previous judgments for that scope.",
        )
    result: JsonObject = {
        "editable_source_entry_ids": list(editable_source_entry_ids or batch.source_entry_ids),
        "source_entries": list(entries.values()),
        "previous_judgments": previous,
        "context_units": units,
        "field_id_vocabulary": deepcopy(inventory["field_id_vocabulary"]),
    }
    if previous_submission is not None:
        submitted_judgments = previous_submission.get("semantic_judgments")
        result["previous_submission"] = [
            projected
            for judgment in (submitted_judgments if isinstance(submitted_judgments, list) else [])
            if (projected := _visible_judgment(judgment)) is not None
        ]
    return result

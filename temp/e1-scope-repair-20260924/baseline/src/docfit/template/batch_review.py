"""Early vocabulary and source-text review shared with the aggregate phase gate."""

from __future__ import annotations

from typing import Any

from docfit.template.harness import (
    _decode_semantic_parts,
    _ordered_semantic_parts_feedback,
    _resolve_ordered_span_refs,
)
from docfit.template.semantic_recovery import classify_semantic_feedback

JsonObject = dict[str, Any]


def batch_text_feedback(
    *,
    inventory: JsonObject,
    judgments: list[JsonObject],
    required_source_entry_ids: tuple[str, ...],
) -> JsonObject | None:
    """Call after batch shape/scope validation; do not accept the aggregate here.

    The shared resolver reports missing entries outside this batch. Only that
    expected absence is filtered. All faults in the submitted text or its Word
    mapping remain blockers; cross-batch review still runs on the complete set.
    """
    feedback = _ordered_semantic_parts_feedback(inventory, judgments)
    if feedback is not None:
        return classify_semantic_feedback(feedback)
    decoded, feedback = _decode_semantic_parts(inventory, judgments)
    if feedback is None:
        _, feedback = _resolve_ordered_span_refs(inventory, decoded)
    if feedback is None:
        return None
    required = set(required_source_entry_ids)
    blockers: list[JsonObject] = []
    for blocker in feedback["blockers"]:
        if blocker.get("code") == "source_span_missing_entry_judgment":
            missing = [key for key in blocker["source_entry_ids"] if key in required]
            if missing:
                blockers.append({**blocker, "source_entry_ids": missing})
        else:
            blockers.append(blocker)
    if not blockers:
        return None
    return classify_semantic_feedback({**feedback, "blockers": blockers})

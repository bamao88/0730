"""Read-only native checks for the captured-packet SDK diagnostic.

This module replays saved product inventory/provenance. It does not run
prepare-template, persist accepted judgments, check readiness, or materialize Word.
It contains no expected roles, field choices, field counts, or replacement text.

Call verify_inventory(the_actual_evidence_card) before checking any output.
feedback_for_output returns the native shape/span feedback, or uses the product's
standard mechanical envelope for native source-coverage blockers. None means only
these checks passed; native span/coverage checks permit whitespace-only gaps.

The runner must pass feedback through the existing Agent-visible projection:

    from docfit.app.prepare_template import _semantic_feedback_prompt
    verify_inventory(packet)
    feedback = feedback_for_output(output)
    if feedback is not None:
        await client.query(_semantic_feedback_prompt(feedback))
        # Consume receive_response on the same still-open client.

Record raw feedback outside Agent input; do not send it directly to the Agent.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from docfit.template.harness import (
    _coverage_feedback_metadata,
    _ordered_semantic_parts_feedback,
    _resolve_ordered_span_refs,
    _source_entry_coverage_feedback,
)
from docfit.template.judgment_shape import mechanical_feedback


INVENTORY_PATH = (
    Path(__file__).resolve().parents[2]
    / "temp/title-field-meaning-20260911/run-2/task"
    / "work/.docfit/harness/object-inventory.json"
)
_inventory_bytes = INVENTORY_PATH.read_bytes()
INVENTORY_SHA256 = sha256(_inventory_bytes).hexdigest()
_inventory = json.loads(_inventory_bytes)
_verified = False


def _entry_text_pairs(entries: Any) -> list[tuple[str, str]]:
    if not isinstance(entries, list) or not entries:
        raise ValueError("Diagnostic binding requires non-empty source entries.")
    pairs = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Diagnostic source entry must be an object.")
        entry_id, text = entry.get("source_entry_id"), entry.get("text")
        if not isinstance(entry_id, str) or not entry_id or not isinstance(text, str):
            raise ValueError("Diagnostic source entry must contain an ID and exact text.")
        pairs.append((entry_id, text))
    if len({entry_id for entry_id, _ in pairs}) != len(pairs):
        raise ValueError("Diagnostic source entry IDs must be unique.")
    return pairs


def verify_inventory(packet: dict[str, Any]) -> None:
    """Require the actual full evidence card to match the saved inventory.

    This is diagnostic binding validation, not feedback for the semantic Agent.
    A mismatch raises and must stop the replay; it must not become Agent feedback.
    """
    global _verified
    _verified = False
    if packet.get("status") != "ok" or packet.get("focus") != "unit_evidence_packet":
        raise ValueError("Expected a successful captured unit_evidence_packet card.")
    if packet.get("source_hash") != _inventory.get("document_sha256"):
        raise ValueError("Captured packet and saved inventory have different source hashes.")
    if _entry_text_pairs(packet.get("evidence")) != _entry_text_pairs(
        _inventory.get("source_entries")
    ):
        raise ValueError("Captured source entry IDs, order, or exact text differ from inventory.")
    summary = packet.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Captured packet has no summary.")
    if summary.get("field_vocabulary_digest") != _inventory.get("field_vocabulary_digest"):
        raise ValueError("Captured packet and saved inventory have different vocabulary digests.")
    if summary.get("field_id_vocabulary") != _inventory.get("field_id_vocabulary"):
        raise ValueError("Captured packet and saved inventory have different field vocabularies.")
    _verified = True


def feedback_for_output(output: dict[str, Any]) -> dict[str, Any] | None:
    """Return native mechanical feedback, without writing the product task root.

    _ordered_semantic_parts_feedback: shape/ref/role/vocabulary feedback or None.
    _resolve_ordered_span_refs: (resolved spans, native span feedback or None).
    _source_entry_coverage_feedback: native blockers and suggested actions.
    mechanical_feedback: standard envelope for those coverage blockers.
    """
    if not _verified:
        raise RuntimeError("Call verify_inventory with this SDK run's actual packet first.")
    if not isinstance(output, dict):
        raise ValueError("Diagnostic output must be the actual structured result object.")
    inventory = deepcopy(_inventory)
    judgments = deepcopy(output.get("semantic_judgments"))
    feedback = _ordered_semantic_parts_feedback(inventory, judgments)
    if feedback is not None:
        return feedback
    spans, feedback = _resolve_ordered_span_refs(inventory, judgments)
    if feedback is not None:
        return feedback
    coverage = _source_entry_coverage_feedback(inventory, spans)
    if not coverage["blockers"]:
        return None
    metadata = _coverage_feedback_metadata()
    # Same failure code/message and metadata as native _submit_semantic_judgments;
    # native blockers/actions pass unchanged through the standard product builder.
    return mechanical_feedback(
        feedback_type=metadata["type"],
        code="template_semantic_judgment_coverage_incomplete",
        message=(
            "Every canonical source entry must be covered by non-overlapping "
            "semantic spans, and each accepted span must expand to provenance."
        ),
        blockers=coverage["blockers"],
        suggested_actions=coverage["suggested_actions"],
        agent_action=metadata["agent_action"],
    )

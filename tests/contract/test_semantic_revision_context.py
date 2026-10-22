from __future__ import annotations

import copy
import json

import pytest

from docfit.template.harness import _decode_whitespace_parts
from docfit.template.revision_context import build_revision_context
from docfit.template.semantic_batches import (
    SemanticBatchCandidateLedger,
    build_semantic_batch_manifest,
    record_semantic_batch_candidate,
)
from docfit.template.source_entries import build_canonical_source_inventory
from docfit.tools.runtime import ToolFailure
from tests.support.source_identity import context_packets, source_partition


def _case():
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[
            {
                "type": "paragraph",
                "locator": f"/body/p[{index}]",
                "text": text,
                "object_ref": {"object_id": f"p{index}", "document_sha256": "a" * 64},
            }
            for index, text in enumerate(
                ["前文", "  " + "正文" * 800 + "\u00a0", "邻文", "相关判断"], 1
            )
        ],
    )
    vocabulary = {"allowed_field_ids": ["author.name.zh"]}
    inventory = {
        "document_sha256": "a" * 64,
        "canonical_source_inventory": canonical.to_json(),
        "field_vocabulary_digest": "b" * 64,
        "field_id_vocabulary": vocabulary,
    }
    proof = source_partition(inventory)
    inventory["unit_reading_packets"] = context_packets(inventory)
    manifest = build_semantic_batch_manifest(
        inventory=inventory, checkpoint=proof, max_entries_per_batch=2
    )
    ledger = SemanticBatchCandidateLedger.empty(manifest)
    for batch in manifest.batches:
        ledger = record_semantic_batch_candidate(
            manifest=manifest,
            ledger=ledger,
            batch_id=batch.batch_id,
            structured_output={
                "status": "complete",
                "summary": "candidate",
                "semantic_judgments": [
                    {
                        "source_entry_id": entry.source_entry_id,
                        "parts": [
                            {"text": entry.text, "role": "fixed_label"},
                        ],
                    }
                    for entry in canonical.source_entries
                    if entry.source_entry_id in batch.source_entry_ids
                ],
            },
            allowed_field_ids=("author.name.zh",),
        )
    return inventory, manifest, ledger


def test_revision_context_keeps_full_text_prior_decisions_and_related_scopes():
    inventory, manifest, ledger = _case()
    before = copy.deepcopy(inventory)
    ids = manifest.required_source_entry_ids
    context = build_revision_context(
        inventory=inventory,
        batch=manifest.batches[0],
        ledger=ledger,
        feedback={"blockers": [{"source_entry_ids": [ids[1], ids[3]]}]},
        editable_source_entry_ids=(ids[1],),
    )
    entries = {row["source_entry_id"]: row for row in context["source_entries"]}
    assert entries[ids[1]]["text"] == "  " + "正文" * 800 + "\u00a0"
    assert len(entries) == 4  # neighbors plus the conflicting entry in another batch
    assert context["editable_source_entry_ids"] == [ids[1]]
    assert context["previous_judgments"] == [
        judgment for candidate in ledger.candidates for judgment in candidate.semantic_judgments
    ]
    assert context["field_id_vocabulary"] == inventory["field_id_vocabulary"]
    assert inventory == before
    for internal in ("locator", "object_ref", "fingerprint", "candidate_digest", "manifest_digest"):
        assert internal not in json.dumps(context)


def test_rejected_submission_is_distinct_from_preserved_candidate():
    inventory, manifest, ledger = _case()
    entry_id = manifest.required_source_entry_ids[1]
    context = build_revision_context(
        inventory=inventory,
        batch=manifest.batches[0],
        ledger=ledger,
        feedback={"blockers": [{"source_entry_id": entry_id}]},
        editable_source_entry_ids=(entry_id,),
        previous_submission={
            "semantic_judgments": [
                {
                    "source_entry_id": entry_id,
                    "locator": "/bad",
                    "parts": [
                        {
                            "text": "wrong",
                            "role": "cleanup",
                            "object_ref": "forbidden",
                        }
                    ],
                }
            ]
        },
    )
    assert context["previous_submission"] == [
        {
            "source_entry_id": entry_id,
            "parts": [{"text": "wrong", "role": "cleanup"}],
        }
    ]
    assert all(
        judgment["parts"][0]["role"] == "fixed_label" for judgment in context["previous_judgments"]
    )


def test_revision_context_preserves_boundary_transport_in_baseline_and_rejected_output():
    inventory, manifest, ledger = _case()
    entry_id = manifest.required_source_entry_ids[1]
    part = {
        "text": "正文" * 800,
        "role": "fill_slot",
        "field_id": "author.name.zh",
        "leading_whitespace": [{"codepoint": "U+0020", "count": 2}],
        "trailing_whitespace": [{"codepoint": "U+00A0", "count": 1}],
    }
    prior = next(j for c in ledger.candidates for j in c.semantic_judgments
                 if j["source_entry_id"] == entry_id)
    prior["parts"] = [copy.deepcopy(part)]
    rejected = {"source_entry_id": entry_id,
                "parts": [{**copy.deepcopy(part), "object_ref": "internal"}]}
    context = build_revision_context(
        inventory=inventory, batch=manifest.batches[0], ledger=ledger,
        feedback={"blockers": [{"source_entry_id": entry_id}]},
        editable_source_entry_ids=(entry_id,),
        previous_submission={"semantic_judgments": [rejected]},
    )
    for key in ("previous_judgments", "previous_submission"):
        visible = next(j for j in context[key] if j["source_entry_id"] == entry_id)
        assert visible["parts"] == [part]
        decoded, failure = _decode_whitespace_parts([visible])
        assert failure is None
        assert decoded[0]["parts"] == [{
            "text": "  " + "正文" * 800 + "\u00a0",
            "role": "fill_slot", "field_id": "author.name.zh",
        }]
        visible["parts"][0]["leading_whitespace"][0]["count"] = 9
    assert prior["parts"] == [part]
    assert rejected["parts"][0]["leading_whitespace"][0]["count"] == 2


@pytest.mark.parametrize("missing", ["source", "baseline"])
def test_incomplete_revision_context_is_host_failure(missing):
    inventory, manifest, ledger = _case()
    if missing == "source":
        inventory["unit_reading_packets"] = {}
    else:
        ledger = SemanticBatchCandidateLedger.empty(manifest)
    with pytest.raises(ToolFailure) as caught:
        build_revision_context(
            inventory=inventory,
            batch=manifest.batches[0],
            ledger=ledger,
            feedback={"blockers": []},
            editable_source_entry_ids=(manifest.required_source_entry_ids[1],),
        )
    assert caught.value.origin == "harness"
    assert caught.value.status == "error"
    assert not caught.value.retryable


def test_revision_context_preserves_word_story_and_format_facts():
    inventory, manifest, ledger = _case()
    entry_id = manifest.required_source_entry_ids[1]
    facts = {"story": "header", "paragraph_style": "header"}
    for packet in inventory["unit_reading_packets"].values():
        for entry in packet["source_entries"]:
            if entry["source_entry_id"] == entry_id:
                entry["word_format"] = facts
    context = build_revision_context(
        inventory=inventory,
        batch=manifest.batches[0],
        ledger=ledger,
        feedback={"blockers": [{"source_entry_id": entry_id}]},
        editable_source_entry_ids=(entry_id,),
    )
    entry = next(item for item in context["source_entries"] if item["source_entry_id"] == entry_id)
    assert entry["word_format"] == facts
    assert "locator" not in json.dumps(context)

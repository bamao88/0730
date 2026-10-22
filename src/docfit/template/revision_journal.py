"""Task-local semantic revision evidence; never an Agent conversation runtime.

Events are immutable, ordered, and bound to the current manifest. A candidate
commit is written before its ledger projection so an interrupted projection can
be recovered without treating a raw submission as an accepted candidate.
"""

from __future__ import annotations

import copy
import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from docfit.template.revision_scope import expand_revision_scopes
from docfit.template.semantic_batches import (
    SemanticBatchCandidateLedger,
    SemanticBatchManifest,
    record_semantic_batch_candidate,
    semantic_source_entry_ids_for_feedback,
)
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_json

JsonObject = dict[str, Any]
_SCHEMA = "docfit-semantic-revision-event/v1"


def _failure(message: str) -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="harness",
        code="semantic_revision_journal_invalid",
        message=message,
        retryable=False,
        suggested_actions=("Restart the semantic stage in a new task from validated inputs.",),
    )


def _judgments(ledger: SemanticBatchCandidateLedger) -> dict[str, JsonObject]:
    return {
        row["source_entry_id"]: row
        for candidate in ledger.candidates
        for row in candidate.semantic_judgments
    }


def judgment_diff(
    before: SemanticBatchCandidateLedger,
    after: SemanticBatchCandidateLedger,
) -> list[JsonObject]:
    old, new = _judgments(before), _judgments(after)
    return [
        {"source_entry_id": key, "before": old.get(key), "after": new.get(key)}
        for key in dict.fromkeys([*old, *new])
        if old.get(key) != new.get(key)
    ]


class SemanticRevisionJournal:
    def __init__(
        self,
        *,
        directory: Path,
        ledger_path: Path,
        manifest: SemanticBatchManifest,
        allowed_field_ids: tuple[str, ...],
        evidence_mode: Literal["runtime", "replay"] = "runtime",
    ) -> None:
        self.directory = directory
        self.ledger_path = ledger_path
        self.manifest = manifest
        self.allowed_field_ids = allowed_field_ids
        self.evidence_mode = evidence_mode
        self.events: list[JsonObject] = []
        self.ledger = SemanticBatchCandidateLedger.empty(manifest)
        try:
            with self._lock():
                self._restore()
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise _failure(f"Cannot restore semantic revision evidence: {error}") from error

    @contextmanager
    def _lock(self) -> Iterator[None]:
        if self.directory.is_symlink():
            raise ValueError("Revision directory must not be a symlink.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.directory / ".lock").open("a") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_ledger(self, value: object) -> SemanticBatchCandidateLedger:
        return SemanticBatchCandidateLedger.from_json(
            value,
            manifest=self.manifest,
            allowed_field_ids=self.allowed_field_ids,
        )

    def _restore(self) -> None:
        previous_digest: str | None = None
        previous_ledger = self.ledger
        for index, path in enumerate(sorted(self.directory.glob("*.json")), 1):
            if path.name != f"{index:08d}.json" or path.is_symlink():
                raise ValueError("Revision events are missing, unordered, or linked.")
            event = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
                raise ValueError("Revision event must be an object with structured data.")
            unsigned = {key: value for key, value in event.items() if key != "event_digest"}
            if (
                event.get("schema_version") != _SCHEMA
                or event.get("evidence_mode") != self.evidence_mode
                or event.get("manifest_digest") != self.manifest.manifest_digest
                or event.get("sequence") != index
                or event.get("previous_event_digest") != previous_digest
                or event.get("event_digest") != sha256_json(unsigned)
            ):
                raise ValueError("Revision event binding or digest is invalid.")
            data = event["data"]
            self._validate_data(event["kind"], data)
            if event["kind"] == "candidate_recorded":
                if data["parent_ledger_digest"] != self.ledger.to_json()["ledger_digest"]:
                    raise ValueError("Candidate parent is stale.")
                next_ledger = self._read_ledger(data["ledger"])
                if data["diff"] != judgment_diff(self.ledger, next_ledger):
                    raise ValueError("Candidate diff does not match its versions.")
                request = self._request(data["request_id"])
                if (
                    request["base_ledger_digest"] != data["parent_ledger_digest"]
                    or request["base_candidate_sequence"] != self._candidate_sequence()
                ):
                    raise ValueError("Candidate was submitted against a stale request.")
                if next_ledger != self._submitted_candidate(data["request_id"]):
                    raise ValueError("Recorded candidate differs from the submitted judgment.")
                previous_ledger, self.ledger = self.ledger, next_ledger
            self.events.append(event)
            previous_digest = event["event_digest"]
        if self.ledger_path.is_symlink():
            raise ValueError("Candidate projection must not be a symlink.")
        if self.ledger_path.exists():
            disk = self._read_ledger(json.loads(self.ledger_path.read_text(encoding="utf-8")))
            if not self.events and disk.candidates:
                raise ValueError("Historical candidates lack revision evidence; cannot invent it.")
            if disk not in (self.ledger, previous_ledger):
                raise ValueError("Candidate projection diverges from revision history.")
        atomic_write_json(self.ledger_path, self.ledger.to_json())

    def _candidate_sequence(self) -> int:
        return next(
            (
                event["sequence"]
                for event in reversed(self.events)
                if event["kind"] == "candidate_recorded"
            ),
            0,
        )

    def _request(self, request_id: int) -> JsonObject:
        if not isinstance(request_id, int) or not 1 <= request_id <= len(self.events):
            raise ValueError("Revision request does not exist.")
        event = self.events[request_id - 1]
        if event["kind"] != "request":
            raise ValueError("Revision reference is not a request.")
        data: JsonObject = event["data"]
        return data

    def _submitted_candidate(self, request_id: int) -> SemanticBatchCandidateLedger:
        request = self._request(request_id)
        responses = [
            event["data"]
            for event in self.events
            if event["kind"] == "response" and event["data"]["request_id"] == request_id
        ]
        if len(responses) != 1 or responses[0]["is_error"]:
            raise ValueError("Candidate requires exactly one successful structured response.")
        scope = request["editable_source_entry_ids"]
        return record_semantic_batch_candidate(
            manifest=self.manifest,
            ledger=self.ledger,
            batch_id=request["batch_id"],
            structured_output=responses[0]["structured_output"],
            allowed_field_ids=self.allowed_field_ids,
            editable_source_entry_ids=tuple(scope) if scope is not None else None,
        )

    def _validate_data(self, kind: str, data: JsonObject) -> None:
        if kind == "budget_policy":
            if (
                set(data)
                != {
                    "max_queries",
                    "max_problem_failures",
                    "max_identical_failures",
                    "max_query_seconds",
                }
                or any(
                    not isinstance(value, int) or isinstance(value, bool) or value <= 0
                    for value in data.values()
                )
                or any(event["kind"] == "budget_policy" for event in self.events)
            ):
                raise ValueError(
                    "Revision limits must be positive, unique and fixed for this task."
                )
        elif kind == "request":
            if (
                data["base_ledger_digest"] != self.ledger.to_json()["ledger_digest"]
                or data["base_candidate_sequence"] != self._candidate_sequence()
                or data["batch_id"] not in {batch.batch_id for batch in self.manifest.batches}
                or not isinstance(data["prompt"], str)
            ):
                raise ValueError("Revision request is stale or invalid.")
        elif kind in ("response", "local_rejected", "needs_input", "candidate_recorded"):
            self._request(data["request_id"])
            if kind == "response":
                if any(
                    event["kind"] == "response"
                    and event["data"]["request_id"] == data["request_id"]
                    for event in self.events
                ):
                    raise ValueError("Request already has a response.")
            elif kind in ("local_rejected", "needs_input"):
                responses = [
                    event["data"]
                    for event in self.events
                    if event["kind"] == "response"
                    and event["data"]["request_id"] == data["request_id"]
                ]
                if len(responses) != 1:
                    raise ValueError("Verdict has no unique response.")
                output = responses[0]["structured_output"]
                if kind == "local_rejected" and (
                    data["output"] != output or not isinstance(data["feedback"], dict)
                ):
                    raise ValueError("Rejected output differs from its response.")
                if kind == "needs_input" and (
                    not isinstance(output, dict) or output.get("status") != "needs_input"
                ):
                    raise ValueError("Needs-input verdict differs from its response.")
        elif kind == "local_review":
            self._request(data["request_id"])
            responses = [
                event
                for event in self.events
                if event["kind"] == "response" and event["data"]["request_id"] == data["request_id"]
            ]
            if len(responses) != 1 or not (
                data["feedback"] is None or isinstance(data["feedback"], dict)
            ):
                raise ValueError("Local review requires one response and structured feedback.")
        elif kind == "scope_expanded":
            request = self._request(data["request_id"])
            responses = [
                event["data"]
                for event in self.events
                if event["kind"] == "response" and event["data"]["request_id"] == data["request_id"]
            ]
            if len(responses) != 1 or responses[0]["is_error"]:
                raise ValueError("Revision expansion requires one valid response.")
            pending = self.pending_revisions()
            pending.pop(request["batch_id"], None)
            batch = next(
                item for item in self.manifest.batches if item.batch_id == request["batch_id"]
            )
            expected = expand_revision_scopes(
                manifest=self.manifest,
                ledger=self.ledger,
                batch=batch,
                editable_source_entry_ids=(
                    tuple(request["editable_source_entry_ids"])
                    if request["editable_source_entry_ids"] is not None
                    else None
                ),
                output=responses[0]["structured_output"],
                pending=pending,
                current_feedback=request["feedback"],
            )
            if data["revisions"] != expected:
                raise ValueError("Expanded revision scope differs from its request.")
        elif kind in ("global_review", "global_review_failed", "run_failed"):
            if data["ledger_digest"] != self.ledger.to_json()["ledger_digest"]:
                raise ValueError("Review refers to a stale candidate.")
        else:
            raise ValueError("Unsupported semantic revision event kind.")

    def _append(self, kind: str, data: JsonObject) -> int:
        self._validate_data(kind, data)
        paths = sorted(self.directory.glob("*.json"))
        if len(paths) != len(self.events):
            raise ValueError("Another writer advanced the semantic revision history.")
        if paths:
            last = json.loads(paths[-1].read_text(encoding="utf-8"))
            if last != self.events[-1]:
                raise ValueError("Semantic revision history changed during execution.")
        sequence = len(self.events) + 1
        event: JsonObject = {
            "schema_version": _SCHEMA,
            "evidence_mode": self.evidence_mode,
            "manifest_digest": self.manifest.manifest_digest,
            "sequence": sequence,
            "created_at": datetime.now(UTC).isoformat(),
            "previous_event_digest": self.events[-1]["event_digest"] if self.events else None,
            "kind": kind,
            "data": copy.deepcopy(data),
        }
        event["event_digest"] = sha256_json(event)
        atomic_write_json(self.directory / f"{sequence:08d}.json", event)
        self.events.append(event)
        return sequence

    def record(self, kind: str, data: JsonObject) -> int:
        try:
            with self._lock():
                return self._append(kind, data)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise _failure(f"Cannot persist semantic revision evidence: {error}") from error

    def request(
        self,
        *,
        batch_id: str,
        prompt: str,
        feedback: JsonObject | None,
        editable_source_entry_ids: tuple[str, ...] | None,
    ) -> int:
        return self.record(
            "request",
            {
                "batch_id": batch_id,
                "prompt": prompt,
                "feedback": feedback,
                "editable_source_entry_ids": (
                    list(editable_source_entry_ids)
                    if editable_source_entry_ids is not None
                    else None
                ),
                "base_ledger_digest": self.ledger.to_json()["ledger_digest"],
                "base_candidate_sequence": self._candidate_sequence(),
            },
        )

    def commit(self, ledger: SemanticBatchCandidateLedger, *, request_id: int) -> None:
        try:
            with self._lock():
                request = self._request(request_id)
                parent = self.ledger.to_json()["ledger_digest"]
                if (
                    request["base_ledger_digest"] != parent
                    or request["base_candidate_sequence"] != self._candidate_sequence()
                ):
                    raise ValueError("Revision request has a stale candidate baseline.")
                disk = self._read_ledger(json.loads(self.ledger_path.read_text(encoding="utf-8")))
                if disk != self.ledger:
                    raise ValueError("Candidate projection changed before commit.")
                self._read_ledger(ledger.to_json())
                if ledger != self._submitted_candidate(request_id):
                    raise ValueError("Candidate differs from the submitted judgment.")
                self._append(
                    "candidate_recorded",
                    {
                        "request_id": request_id,
                        "parent_ledger_digest": parent,
                        "ledger": ledger.to_json(),
                        "diff": judgment_diff(self.ledger, ledger),
                    },
                )
                # The event is authoritative; a failed projection is recovered on reopening.
                self.ledger = ledger
                atomic_write_json(self.ledger_path, ledger.to_json())
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise _failure(f"Cannot commit semantic candidate: {error}") from error

    def pending_revisions(self) -> dict[str, JsonObject]:
        """Reconstruct unfinished semantic work without accepting unreviewed responses."""
        pending: dict[str, JsonObject] = {}
        for event in self.events:
            data = event["data"]
            if event["kind"] == "scope_expanded":
                pending.update(copy.deepcopy(data["revisions"]))
            elif event["kind"] == "global_review":
                pending.clear()
                if data["feedback"] is not None:
                    ids = set(
                        semantic_source_entry_ids_for_feedback(
                            manifest=self.manifest,
                            feedback=data["feedback"],
                        )
                    )
                    for batch in self.manifest.batches:
                        scope = [key for key in batch.source_entry_ids if key in ids]
                        if scope:
                            pending[batch.batch_id] = {
                                "editable_source_entry_ids": scope,
                                "feedback": copy.deepcopy(data["feedback"]),
                            }
            elif event["kind"] in ("local_rejected", "candidate_recorded"):
                request = self._request(data["request_id"])
                if event["kind"] == "candidate_recorded":
                    pending.pop(request["batch_id"], None)
                else:
                    pending[request["batch_id"]] = {
                        "feedback": copy.deepcopy(data["feedback"]),
                        "previous_submission": copy.deepcopy(data["output"]),
                        "editable_source_entry_ids": request["editable_source_entry_ids"],
                    }
        return pending

    def local_revision(self, batch_id: str) -> JsonObject | None:
        return self.pending_revisions().get(batch_id)

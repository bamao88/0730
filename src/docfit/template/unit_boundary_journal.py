"""Durable boundary-stage evidence, separate from SDK conversation/session state."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docfit.tools.runtime import JsonObject, ToolFailure, atomic_write_json, read_json, sha256_json

_SCHEMA = "docfit-unit-boundary-revision/v1"


def _failure(error: Exception) -> ToolFailure:
    return ToolFailure(
        status="error", origin="harness", code="unit_boundary_journal_invalid",
        message=f"Cannot preserve unit-boundary revision evidence: {error}", retryable=False,
    )


def proposal_diff(before: Any, after: Any) -> JsonObject:
    """Position-based unit diff also preserves duplicate IDs and malformed submissions."""
    old = before if isinstance(before, dict) else {}
    new = after if isinstance(after, dict) else {}
    fields = [
        {"field": key, "before_present": key in old, "after_present": key in new,
         "before": old.get(key), "after": new.get(key)}
        for key in sorted(set(old) | set(new))
        if (key != "units" or not isinstance(old.get(key, []), list)
            or not isinstance(new.get(key, []), list))
        and (key not in old or key not in new or old[key] != new[key])
    ]
    old_units, new_units = old.get("units", []), new.get("units", [])
    units = []
    if isinstance(old_units, list) and isinstance(new_units, list):
        for index in range(max(len(old_units), len(new_units))):
            left = old_units[index] if index < len(old_units) else None
            right = new_units[index] if index < len(new_units) else None
            if left != right:
                units.append({"index": index, "before": left, "after": right})
    return {"fields": fields, "units": units}


def read_unit_boundary_journal(directory: Path, *, binding: JsonObject) -> list[JsonObject]:
    """Verify a saved history without rewriting it or promoting any submitted proposal."""
    events: list[JsonObject] = []
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Missing or linked boundary history.")
        for index, path in enumerate(sorted(directory.glob("*.json")), 1):
            event = read_json(path)
            if (
                path.is_symlink() or path.name != f"{index:08d}.json"
                or event.get("schema_version") != _SCHEMA
                or event.get("run_id") != directory.name
                or event.get("binding") != binding
                or event.get("sequence") != index
                or event.get("previous_event_digest") != (
                    events[-1]["event_digest"] if events else None
                )
                or event.get("event_digest") != sha256_json({
                    k: v for k, v in event.items() if k != "event_digest"
                })
            ):
                raise ValueError("Boundary history binding, order or digest differs.")
            _validate_event(event["kind"], event["data"], events)
            events.append(event)
        return events
    except (OSError, ValueError, TypeError, KeyError, ToolFailure) as error:
        raise _failure(error) from error


def _validate_event(kind: str, data: JsonObject, events: list[JsonObject]) -> None:
    if not isinstance(data, dict):
        raise ValueError("Boundary event data must be an object.")

    def referenced(key: str, expected_kind: str) -> JsonObject:
        sequence = data.get(key)
        if type(sequence) is not int or not 1 <= sequence <= len(events):
            raise ValueError("Boundary event refers to a missing parent.")
        event = events[sequence - 1]
        if event["kind"] != expected_kind:
            raise ValueError("Boundary event refers to the wrong parent type.")
        return event

    if kind == "request":
        if not isinstance(data.get("prompt"), str):
            raise ValueError("Boundary request must preserve its actual prompt.")
    elif kind == "response":
        referenced("request_sequence", "request")
        previous = next((e for e in reversed(events) if e["kind"] == "response"), None)
        if data["previous_response_sequence"] != (previous["sequence"] if previous else None):
            raise ValueError("Boundary response ancestry differs.")
        before = previous["data"]["structured_output"] if previous else None
        if data["diff"] != proposal_diff(before, data["structured_output"]):
            raise ValueError("Boundary proposal diff differs from the stored submissions.")
    elif kind in {"review", "review_failed"}:
        referenced("response_sequence", "response")
    elif kind == "checkpoint":
        if referenced("review_sequence", "review")["data"]["feedback"] is not None:
            raise ValueError("Cannot mark a rejected proposal as a checkpoint.")
    elif kind != "failed":
        raise ValueError("Unknown boundary evidence event kind.")


def validate_boundary_checkpoint_journal(
    root: Path, checkpoint: JsonObject, *, binding: JsonObject,
) -> None:
    """New proofs must resolve their actual accepted review and persisted checkpoint event."""
    reference = checkpoint.get("revision_evidence")
    if not isinstance(reference, dict):
        raise ValueError("Boundary revision reference is missing or malformed.")
    run_id = reference.get("run_id")
    if (
        not isinstance(run_id, str) or len(run_id) != 32
        or any(char not in "0123456789abcdef" for char in run_id)
    ):
        raise ValueError("Boundary revision run ID is invalid.")
    events = read_unit_boundary_journal(
        root / "work/.docfit/unit-boundary-revisions" / run_id, binding=binding,
    )
    matching = [e for e in events if e["kind"] == "checkpoint"
                and e["data"]["checkpoint_digest"] == sha256_json(checkpoint)]
    if len(matching) != 1:
        raise ValueError("Boundary checkpoint lacks its matching revision event.")
    review = events[matching[0]["data"]["review_sequence"] - 1]
    response = events[review["data"]["response_sequence"] - 1]
    submitted = response["data"]["structured_output"]
    if (
        review["event_digest"] != reference.get("review_event_digest")
        or review["data"]["feedback"] is not None
        or not isinstance(submitted, dict) or submitted.get("units") != checkpoint.get("units")
    ):
        raise ValueError("Boundary checkpoint differs from its accepted proposal.")


class UnitBoundaryJournal:
    def __init__(self, directory: Path, *, binding: JsonObject) -> None:
        self.directory = directory
        self.binding = deepcopy(binding)
        self.events: list[JsonObject] = []
        try:
            if directory.parent.is_symlink():
                raise ValueError("Boundary history parent must not be linked.")
            directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        except (OSError, ValueError) as error:
            raise _failure(error) from error

    def record(self, kind: str, data: JsonObject) -> int:
        try:
            data = deepcopy(data)
            if kind == "response":
                previous = next((e for e in reversed(self.events) if e["kind"] == kind), None)
                data["previous_response_sequence"] = previous["sequence"] if previous else None
                data["diff"] = proposal_diff(
                    previous["data"]["structured_output"] if previous else None,
                    data["structured_output"],
                )
            _validate_event(kind, data, self.events)
            if read_unit_boundary_journal(self.directory, binding=self.binding) != self.events:
                raise ValueError("Boundary evidence changed during execution.")
            sequence = len(self.events) + 1
            event = {
                "schema_version": _SCHEMA, "run_id": self.directory.name,
                "binding": self.binding, "sequence": sequence,
                "created_at": datetime.now(UTC).isoformat(),
                "previous_event_digest": self.events[-1]["event_digest"] if self.events else None,
                "kind": kind, "data": data,
            }
            event["event_digest"] = sha256_json(event)
            atomic_write_json(self.directory / f"{sequence:08d}.json", event)
            self.events.append(event)
            return sequence
        except (OSError, ValueError, TypeError, KeyError, ToolFailure) as error:
            raise _failure(error) from error

    def review_binding(self, sequence: int) -> JsonObject:
        return {"run_id": self.directory.name,
                "review_event_digest": self.events[sequence - 1]["event_digest"]}

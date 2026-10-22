"""Durable limits for semantic revision work, derived from task-local evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from docfit.template.revision_journal import SemanticRevisionJournal
from docfit.tools.runtime import ToolFailure, sha256_json

JsonObject = dict[str, Any]
_TEXT_CODES = frozenset(
    {
        "ordered_part_text_mismatch",
        "ordered_part_text_gap",
        "ordered_part_text_not_found",
        "ordered_part_empty_for_text_entry",
        "whole_entry_part_invalid",
        "ordered_part_crosses_unit_cut",
        "ordered_part_whitespace_transport_invalid",
    }
)


def _stop(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="harness",
        code=code,
        message=message,
        retryable=False,
        suggested_actions=("Inspect the saved judgments, feedback and budget evidence.",),
    )


def _entry_ids(blocker: JsonObject, output: JsonObject, scope: tuple[str, ...]) -> tuple[str, ...]:
    ids = set()
    if isinstance(blocker.get("source_entry_id"), str):
        ids.add(blocker["source_entry_id"])
    raw_ids = blocker.get("source_entry_ids", [])
    if isinstance(raw_ids, list):
        ids.update(item for item in raw_ids if isinstance(item, str))
    # Shape errors may only identify an array position. Resolve against the actual
    # submission, then clamp to the requested scope so invented IDs cannot reset a limit.
    field = blocker.get("field")
    judgments = output.get("semantic_judgments", [])
    match = re.match(r"semantic_judgments\[(\d+)\]", field) if isinstance(field, str) else None
    if match and isinstance(judgments, list):
        index = int(match[1])
        if index < len(judgments) and isinstance(judgments[index], dict):
            entry_id = judgments[index].get("source_entry_id")
            if isinstance(entry_id, str):
                ids.add(entry_id)
    selected = tuple(key for key in scope if key in ids)
    return selected or scope


def _problems(
    feedback: JsonObject,
    output: JsonObject,
    scope: tuple[str, ...],
) -> dict[tuple[str, str], str]:
    raw_judgments = output.get("semantic_judgments")
    judgments = {
        item["source_entry_id"]: item
        for item in (raw_judgments if isinstance(raw_judgments, list) else [])
        if isinstance(item, dict) and isinstance(item.get("source_entry_id"), str)
    }
    problems: dict[tuple[str, str], str] = {}
    for blocker in feedback.get("blockers", []):
        if not isinstance(blocker, dict):
            continue
        code = blocker.get("code", "unknown")
        if code == "related_semantic_revision_requested":
            continue
        # Text failures keep one identity even if the error changes from gap to
        # mismatch or the Agent changes a role, reason, part count or array position.
        category = (
            "source_text_partition"
            if isinstance(code, str) and code in _TEXT_CODES
            else "judgment_contract"
        )
        for entry_id in _entry_ids(blocker, output, scope):
            parts = judgments.get(entry_id, {}).get("parts", [])
            if category == "source_text_partition":
                evidence = (
                    [
                        {key: part[key] for key in ("text", "whitespace") if key in part}
                        for part in parts
                        if isinstance(part, dict)
                    ]
                    if isinstance(parts, list)
                    else parts
                )
            else:
                evidence = (
                    [
                        {
                            key: part[key]
                            for key in ("text", "whitespace", "role", "field_id")
                            if key in part
                        }
                        for part in parts
                        if isinstance(part, dict)
                    ]
                    if isinstance(parts, list)
                    else parts
                )
            problems[(entry_id, category)] = sha256_json(evidence)
    return problems


@dataclass(frozen=True)
class RevisionBudget:
    max_queries: int
    max_problem_failures: int = 7
    max_identical_failures: int = 3
    max_query_seconds: int = 3600

    def bind(self, journal: SemanticRevisionJournal) -> None:
        policy = {
            "max_queries": self.max_queries,
            "max_problem_failures": self.max_problem_failures,
            "max_identical_failures": self.max_identical_failures,
            "max_query_seconds": self.max_query_seconds,
        }
        saved = [event for event in journal.events if event["kind"] == "budget_policy"]
        if not saved:
            journal.record("budget_policy", policy)
        elif len(saved) != 1 or saved[0]["data"] != policy:
            raise _stop(
                "semantic_budget_policy_changed", "Resume cannot change the saved revision limits."
            )

    def query_seconds(
        self, journal: SemanticRevisionJournal, *, now: datetime | None = None
    ) -> float:
        now = now or datetime.now(UTC)
        requests: dict[int, datetime] = {}
        elapsed = 0.0
        for event in journal.events:
            at = datetime.fromisoformat(event["created_at"])
            if event["kind"] == "request":
                requests[event["sequence"]] = at
            elif event["kind"] == "response":
                start = requests.pop(event["data"]["request_id"], None)
                if start is not None:
                    elapsed += max(0.0, (at - start).total_seconds())
            elif event["kind"] == "run_failed":
                elapsed += sum(
                    max(0.0, (at - start).total_seconds()) for start in requests.values()
                )
                requests.clear()
        # An unrecorded crash has no trustworthy end time. Charge the outstanding
        # interval conservatively rather than resetting it on resume.
        return elapsed + sum(max(0.0, (now - start).total_seconds()) for start in requests.values())

    def remaining_seconds(self, journal: SemanticRevisionJournal) -> float:
        # The live phase deadline includes SDK setup and checks between queries.
        # Reconstructing query intervals alone can leave a positive remainder
        # after that deadline expired. An explicitly exhausted task stays stopped.
        if any(
            event["kind"] == "run_failed"
            and event["data"].get("failure", {}).get("code")
            == "semantic_query_time_budget_exhausted"
            for event in journal.events
        ):
            raise _stop(
                "semantic_query_time_budget_exhausted",
                "The saved semantic time allowance was exhausted; resume cannot renew it.",
            )
        remaining = self.max_query_seconds - self.query_seconds(journal)
        if remaining <= 0:
            raise _stop(
                "semantic_query_time_budget_exhausted",
                "The saved semantic query time limit is exhausted.",
            )
        return remaining

    def check_request(
        self,
        journal: SemanticRevisionJournal,
        *,
        source_entry_ids: tuple[str, ...],
    ) -> None:
        if sum(event["kind"] == "request" for event in journal.events) >= self.max_queries:
            raise _stop(
                "semantic_query_budget_exhausted",
                "The saved semantic query count limit is exhausted.",
            )
        self.remaining_seconds(journal)
        histories: dict[tuple[str, str], list[str]] = {}
        ledger_output: JsonObject = {"semantic_judgments": []}
        for event in journal.events:
            data = event["data"]
            if event["kind"] == "candidate_recorded":
                ledger_output = {
                    "semantic_judgments": [
                        row
                        for candidate in data["ledger"]["candidates"]
                        for row in candidate["semantic_judgments"]
                    ]
                }
            if event["kind"] == "local_rejected":
                request = journal.events[data["request_id"] - 1]["data"]
                batch = next(
                    b for b in journal.manifest.batches if b.batch_id == request["batch_id"]
                )
                scope = tuple(request["editable_source_entry_ids"] or batch.source_entry_ids)
                output = data["output"]
                feedback = data["feedback"]
            elif event["kind"] == "global_review" and data["feedback"] is not None:
                scope = journal.manifest.required_source_entry_ids
                output = ledger_output
                feedback = data["feedback"]
            else:
                continue
            for key, fingerprint in _problems(feedback, output, scope).items():
                histories.setdefault(key, []).append(fingerprint)
        requested = set(source_entry_ids)
        for (entry_id, category), fingerprints in histories.items():
            if entry_id not in requested:
                continue
            if len(fingerprints) >= self.max_problem_failures:
                raise _stop(
                    "semantic_problem_budget_exhausted",
                    f"Revision limit reached for {entry_id}: {category}.",
                )
            recent = fingerprints[-self.max_identical_failures :]
            if len(recent) == self.max_identical_failures and len(set(recent)) == 1:
                raise _stop(
                    "semantic_revision_no_progress",
                    f"Repeated unchanged failure for {entry_id}: {category}.",
                )

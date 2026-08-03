from __future__ import annotations

import inspect
from dataclasses import fields
from typing import get_args, get_type_hints

from docfit.observability.correlation import (
    DirectRelationship,
    RunCorrelation,
    correlate_observation_run,
)
from docfit.observability.events import ObservationEvent


def test_correlation_boundary_accepts_only_sanitized_events() -> None:
    hints = get_type_hints(correlate_observation_run)

    assert get_args(hints["events"])[0] is ObservationEvent


def test_correlation_projection_has_no_raw_or_path_escape_hatch() -> None:
    forbidden = {
        "prompt",
        "tool_input",
        "tool_output",
        "tool_response",
        "body",
        "text",
        "content",
        "path",
        "cwd",
        "transcript_path",
        "raw",
        "exception",
    }

    assert forbidden.isdisjoint(field.name for field in fields(RunCorrelation))
    assert forbidden.isdisjoint(field.name for field in fields(DirectRelationship))


def test_relationship_contract_contains_direct_proof_not_inference_fields() -> None:
    relationship_fields = {field.name for field in fields(DirectRelationship)}

    assert {"parent", "child", "proof_fields", "status"} <= relationship_fields
    assert {"nearest", "similar_name", "expected_order", "workflow_step"}.isdisjoint(
        relationship_fields
    )


def test_correlation_module_does_not_import_platform_or_storage_layers() -> None:
    module = inspect.getmodule(correlate_observation_run)
    assert module is not None
    source = inspect.getsource(module)

    assert "local_debug" not in source
    assert "AppleScript" not in source
    assert "sqlite3" not in source
    assert "storage" not in source

from __future__ import annotations

import subprocess
import sys
from dataclasses import fields
from pathlib import Path
from typing import get_type_hints

import pytest

from docfit.app.agent import build_agent_options
from docfit.app.cli import build_parser, main
from docfit.observability.events import ObservationEvent, SanitizationReceipt
from docfit.observability.models import ObservationRecorder
from docfit.observability.runtime import (
    OBSERVATION_QUEUE_MAX_BYTES,
    OBSERVATION_QUEUE_MAX_EVENTS,
    OBSERVATION_QUEUE_P0_RESERVED_EVENTS,
    OBSERVATION_WRITER_BATCH_BYTES,
    OBSERVATION_WRITER_BATCH_EVENTS,
)
from docfit.observability.sdk_sources import (
    FORBIDDEN_PERSISTED_SDK_FIELDS,
    SDK_SOURCE_CONTRACTS,
    installed_sdk_contract_gaps,
)
from docfit.observability.storage import (
    DEFAULT_STORAGE_LIMITS,
    OBSERVATION_STORAGE_BATCH_MAX_BYTES,
    OBSERVATION_STORAGE_BATCH_MAX_EVENTS,
    delete_observation_run,
    initialize_observation_store,
    observation_reader,
)


def test_installed_sdk_exposes_required_direct_source_ids() -> None:
    assert installed_sdk_contract_gaps() == ()
    assert {contract.symbol for contract in SDK_SOURCE_CONTRACTS} >= {
        "AssistantMessage",
        "ToolUseBlock",
        "ToolResultBlock",
        "ResultMessage",
        "PreToolUseHookInput",
        "PostToolUseHookInput",
        "PostToolUseFailureHookInput",
        "SubagentStartHookInput",
        "SubagentStopHookInput",
        "ToolPermissionContext",
    }
    assert {
        "prompt",
        "tool_input",
        "tool_response",
        "error",
        "result",
        "transcript_path",
        "agent_transcript_path",
        "cwd",
    } <= FORBIDDEN_PERSISTED_SDK_FIELDS


def test_core_conversion_import_does_not_load_local_debug_platform_adapters() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import docfit.app.convert; "
                "assert not any(name.startswith('docfit.observability.local_debug') "
                "for name in sys.modules)"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr


def test_core_conversion_import_does_not_load_observer_web_or_gui_automation() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import docfit.app.convert; "
                "forbidden=('docfit.observability.web','win32com','appscript',"
                "'pyautogui'); "
                "assert not any(name == item or name.startswith(item + '.') "
                "for name in sys.modules for item in forbidden)"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr


def test_sdk_attempt_environment_is_explicit_and_session_store_is_disabled() -> None:
    options = build_agent_options(
        agent_env={"CLAUDE_CONFIG_DIR": "/private/docfit-sdk-attempt"}
    )

    assert options.env["CLAUDE_CONFIG_DIR"] == "/private/docfit-sdk-attempt"
    assert options.session_store is None


def test_convert_observation_cli_defaults_off_and_accepts_auto() -> None:
    parser = build_parser()
    common = [
        "convert",
        "--input",
        "input.docx",
        "--school-template",
        "template.docx",
        "--school-requirements",
        "requirements.txt",
        "--output",
        "out",
    ]

    assert parser.parse_args(common).observation == "off"
    assert parser.parse_args([*common, "--observation", "auto"]).observation == "auto"


def test_observe_cli_has_port_but_no_remote_host(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()

    assert parser.parse_args(["observe"]).port == 0
    assert parser.parse_args(["observe", "--port", "43123"]).port == 43123
    with pytest.raises(SystemExit):
        parser.parse_args(["observe", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        parser.parse_args(["observe", "--port", "70000"])

    assert main(["observe", "--port", "0"]) == 2
    error = capsys.readouterr().err
    assert "observer_web_not_ready" in error


def test_storage_schema_contains_only_safe_projection_fields(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")

    with observation_reader(database) as reader:
        columns = {
            row[1]
            for table in ("observation_runs", "observation_events")
            for row in reader.execute(f"PRAGMA table_info({table})")
        }

    assert {
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
    }.isdisjoint(columns)
    assert {"run_id", "task_ref", "session_id", "tool_use_id", "agent_id"} <= columns
    assert "payload_json" in columns


def test_recorder_boundary_accepts_only_safe_events_and_drop_receipts() -> None:
    record_hints = get_type_hints(ObservationRecorder.record)
    drop_hints = get_type_hints(ObservationRecorder.note_drop)

    assert record_hints["event"] is ObservationEvent
    assert drop_hints["receipt"] is SanitizationReceipt
    assert {
        "prompt",
        "tool_input",
        "tool_response",
        "path",
        "raw",
    }.isdisjoint(field.name for field in fields(ObservationEvent))


def test_o0_storage_and_queue_limits_match_approved_contract() -> None:
    assert OBSERVATION_QUEUE_MAX_EVENTS == 1024
    assert OBSERVATION_QUEUE_MAX_BYTES == 16 * 1024 * 1024
    assert OBSERVATION_QUEUE_P0_RESERVED_EVENTS >= 64
    assert OBSERVATION_QUEUE_P0_RESERVED_EVENTS >= OBSERVATION_QUEUE_MAX_EVENTS // 10
    assert OBSERVATION_WRITER_BATCH_EVENTS == OBSERVATION_STORAGE_BATCH_MAX_EVENTS == 64
    assert (
        OBSERVATION_WRITER_BATCH_BYTES
        == OBSERVATION_STORAGE_BATCH_MAX_BYTES
        == 1024 * 1024
    )
    assert DEFAULT_STORAGE_LIMITS.max_run_events == 10_000
    assert DEFAULT_STORAGE_LIMITS.max_run_bytes == 64 * 1024 * 1024
    assert DEFAULT_STORAGE_LIMITS.max_database_bytes == 512 * 1024 * 1024
    assert DEFAULT_STORAGE_LIMITS.max_completed_runs == 500
    assert DEFAULT_STORAGE_LIMITS.completed_retention_days == 30
    assert DEFAULT_STORAGE_LIMITS.minimum_free_bytes == 1024 * 1024 * 1024
    assert DEFAULT_STORAGE_LIMITS.minimum_free_ratio == 0.05


def test_observer_delete_api_has_no_task_or_transcript_target() -> None:
    hints = get_type_hints(delete_observation_run)

    assert set(hints) == {"database", "run_id", "return"}
    assert hints["database"] is Path
    assert hints["run_id"] is str

from __future__ import annotations

import subprocess
import sys

import pytest

from docfit.app.cli import build_parser, main
from docfit.observability.sdk_sources import (
    FORBIDDEN_PERSISTED_SDK_FIELDS,
    SDK_SOURCE_CONTRACTS,
    installed_sdk_contract_gaps,
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

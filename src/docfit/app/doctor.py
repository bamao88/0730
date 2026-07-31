"""Deterministic and local-product readiness checks for DocFit."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal, cast

from docfit.app.agent import (
    BUILTIN_TOOLS,
    DIRECTORY_POLICY,
    LOGGING_POLICY,
    SKILL_NAME,
    build_agent_options,
    project_root,
)
from docfit.app.settings import (
    AgentConfigurationError,
    agent_env_file_is_private,
    configured_backend_names,
    merged_agent_environment,
)
from docfit.tools import FULL_TOOL_NAMES, MCP_SERVER_NAME
from docfit.tools.image_smoke import make_smoke_png

from .smoke import SMOKE_CASES, receipt_directory

CheckStatus = Literal["PASS", "NOT_READY", "FAIL"]
Requirement = Literal["base", "agent-smoke", "provider"]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: CheckStatus
    detail: str
    required_for: tuple[Requirement, ...]


@dataclass(frozen=True)
class DoctorReport:
    requirement: Requirement
    gate: Literal["PASS", "NOT_READY"]
    overall_status: CheckStatus
    checks: tuple[DoctorCheck, ...]

    @property
    def exit_code(self) -> int:
        return 0 if self.gate == "PASS" else 1


def _sdk_version() -> str | None:
    try:
        return version("claude-agent-sdk")
    except PackageNotFoundError:
        return None


def _font_count() -> int:
    roots = (
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        Path("/usr/share/fonts"),
    )
    suffixes = {".otf", ".ttf", ".ttc"}
    return sum(
        1
        for root in roots
        if root.is_dir()
        for path in root.rglob("*")
        if path.suffix.casefold() in suffixes
    )


def _receipt_check(root: Path, sdk_version: str | None) -> DoctorCheck:
    missing: list[str] = []
    invalid: list[str] = []
    for case_name in SMOKE_CASES:
        path = receipt_directory(root) / f"{case_name}.json"
        if not path.is_file():
            missing.append(case_name)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            invalid.append(case_name)
            continue
        if payload.get("status") != "PASS" or payload.get("sdk_version") != sdk_version:
            invalid.append(case_name)
    if not missing and not invalid:
        return DoctorCheck(
            "agent_smoke_receipts",
            "PASS",
            "All three live smoke receipts match the installed SDK version.",
            ("agent-smoke",),
        )
    detail_parts = []
    if missing:
        detail_parts.append(f"missing: {', '.join(missing)}")
    if invalid:
        detail_parts.append(f"invalid or stale: {', '.join(invalid)}")
    return DoctorCheck(
        "agent_smoke_receipts",
        "NOT_READY",
        "; ".join(detail_parts),
        ("agent-smoke",),
    )


def run_doctor(
    requirement: Requirement = "base",
    *,
    root: Path | None = None,
    environment: Mapping[str, str] | None = None,
    env_file: Path | None = None,
    python_version: tuple[int, int] | None = None,
) -> DoctorReport:
    project = root or project_root()
    current_python = python_version or (sys.version_info.major, sys.version_info.minor)
    sdk_version = _sdk_version()
    checks: list[DoctorCheck] = []

    configuration_error: str | None = None
    try:
        agent_environment, selected_env_file = merged_agent_environment(
            environment,
            env_file=env_file,
        )
        backend_names = configured_backend_names(agent_environment)
    except AgentConfigurationError as error:
        agent_environment = {}
        selected_env_file = env_file
        backend_names = ()
        configuration_error = str(error)

    checks.append(
        DoctorCheck(
            "python",
            "PASS" if current_python == (3, 12) else "FAIL",
            f"Python {current_python[0]}.{current_python[1]}; M0 requires 3.12.",
            ("base", "agent-smoke", "provider"),
        )
    )
    checks.append(
        DoctorCheck(
            "claude_agent_sdk",
            "PASS" if sdk_version else "FAIL",
            f"claude-agent-sdk {sdk_version}" if sdk_version else "Package is not installed.",
            ("base", "agent-smoke", "provider"),
        )
    )

    required_files = (
        project / "pyproject.toml",
        project / "uv.lock",
        project / ".python-version",
        project / ".claude" / "skills" / SKILL_NAME / "SKILL.md",
    )
    missing_files = [
        str(path.relative_to(project)) for path in required_files if not path.is_file()
    ]
    checks.append(
        DoctorCheck(
            "configuration_files",
            "FAIL" if missing_files else "PASS",
            (
                f"Missing: {', '.join(missing_files)}"
                if missing_files
                else "Project metadata, lock, Python pin, and project Skill are present."
            ),
            ("base", "agent-smoke", "provider"),
        )
    )
    permission_ok = os.access(project, os.R_OK | os.W_OK)
    checks.append(
        DoctorCheck(
            "directory_permissions",
            "PASS" if permission_ok else "FAIL",
            (
                f"Project root is "
                f"{'readable and writable' if permission_ok else 'not writable'}: {project}"
            ),
            ("base", "agent-smoke", "provider"),
        )
    )

    try:
        options = build_agent_options(cwd=project)
        mcp_names = tuple(options.mcp_servers) if isinstance(options.mcp_servers, dict) else ()
        config_ok = (
            tuple(options.tools or ()) == BUILTIN_TOOLS
            and tuple(options.allowed_tools) == FULL_TOOL_NAMES
            and mcp_names == (MCP_SERVER_NAME,)
            and options.setting_sources == ["project"]
            and options.skills == [SKILL_NAME]
        )
    except Exception:
        config_ok = False
    checks.append(
        DoctorCheck(
            "sdk_configuration",
            "PASS" if config_ok else "FAIL",
            (
                "Only Skill and AskUserQuestion are visible; one DocFit server exposes five "
                "pre-approved names."
                if config_ok
                else "SDK permission or discovery configuration does not match the M0 contract."
            ),
            ("base", "agent-smoke", "provider"),
        )
    )
    policy_ok = DIRECTORY_POLICY == (
        "input_read_only",
        "work_writable",
        "output_writable",
        "outside_task_denied",
    )
    checks.append(
        DoctorCheck(
            "directory_policy",
            "PASS" if policy_ok else "FAIL",
            (
                "M0 exposes no filesystem built-ins; the future Tool boundary fixes input "
                "as read-only and work/output as writable."
            ),
            ("base", "agent-smoke", "provider"),
        )
    )
    checks.append(
        DoctorCheck(
            "logging_policy",
            "PASS" if LOGGING_POLICY == "metadata_only_no_document_body" else "FAIL",
            "CLI and smoke receipts record metadata only, never document body content.",
            ("base", "agent-smoke", "provider"),
        )
    )

    image = make_smoke_png()
    image_ok = image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) > 500
    checks.append(
        DoctorCheck(
            "image_tool_payload",
            "PASS" if image_ok else "FAIL",
            f"Generated deterministic PNG payload ({len(image)} bytes).",
            ("base", "agent-smoke"),
        )
    )
    checks.append(
        DoctorCheck(
            "iteration_rendering",
            "PASS" if image_ok else "FAIL",
            "The M0 synthetic page image path is available for Agent iteration evidence.",
            ("base", "agent-smoke"),
        )
    )
    if selected_env_file is None:
        env_file_status: CheckStatus = "PASS" if backend_names else "NOT_READY"
        env_file_detail = (
            "Agent credentials were supplied by the current process environment."
            if backend_names
            else "No shared Agent environment file was selected."
        )
    elif agent_env_file_is_private(selected_env_file):
        env_file_status = "PASS"
        env_file_detail = f"Shared Agent environment is present with mode 0600: {selected_env_file}"
    elif selected_env_file.is_file():
        env_file_status = "NOT_READY"
        env_file_detail = (
            f"Shared Agent environment must have mode 0600: {selected_env_file}"
        )
    else:
        env_file_status = "NOT_READY"
        env_file_detail = f"Shared Agent environment is absent: {selected_env_file}"
    checks.append(
        DoctorCheck(
            "agent_environment_file",
            env_file_status,
            env_file_detail,
            ("agent-smoke",),
        )
    )
    checks.append(
        DoctorCheck(
            "agent_backend_credentials",
            "PASS" if backend_names and configuration_error is None else "NOT_READY",
            (
                f"Configured Agent backends in priority order: {', '.join(backend_names)}."
                if backend_names
                else (
                    f"Agent environment is invalid: {configuration_error}"
                    if configuration_error
                    else (
                        "No Kimi or MiniMax credential is configured; "
                        "deterministic CI remains valid."
                    )
                )
            ),
            ("agent-smoke",),
        )
    )
    checks.append(_receipt_check(project, sdk_version))

    font_count = _font_count()
    checks.append(
        DoctorCheck(
            "fonts",
            "PASS" if font_count else "NOT_READY",
            f"Discovered {font_count} local font files." if font_count else "No local fonts found.",
            ("provider",),
        )
    )
    checks.append(
        DoctorCheck(
            "provider",
            "NOT_READY",
            (
                "Delivery DOCX rendering and Provider support checks are intentionally "
                "reserved for M1."
            ),
            ("provider",),
        )
    )

    active = tuple(check for check in checks if requirement in check.required_for)
    gate: Literal["PASS", "NOT_READY"] = (
        "PASS" if all(check.status == "PASS" for check in active) else "NOT_READY"
    )
    statuses = {check.status for check in checks}
    overall: CheckStatus = (
        "FAIL" if "FAIL" in statuses else "NOT_READY" if "NOT_READY" in statuses else "PASS"
    )
    return DoctorReport(
        requirement=requirement,
        gate=gate,
        overall_status=overall,
        checks=tuple(checks),
    )


def doctor_main(requirement: str | None = None, *, as_json: bool = False) -> int:
    selected = "base" if requirement is None else cast(Requirement, requirement)
    report = run_doctor(selected)
    if as_json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        for check in report.checks:
            print(f"{check.status:>9}  {check.name}: {check.detail}")
        print(f"\nGate {report.requirement}: {report.gate} (overall: {report.overall_status})")
    return report.exit_code

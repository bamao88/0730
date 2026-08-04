"""Deterministic and provider readiness checks for DocFit."""

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
    AUTO_APPROVED_TOOL_NAMES,
    BUILTIN_TOOLS,
    DIRECTORY_POLICY,
    LOGGING_POLICY,
    MAIN_AGENT_READ_POLICY,
    READ_ONLY_SUBAGENT_TOOLS,
    SKILL_NAMES,
    SUBAGENT_NAME,
    TRUSTED_BASIC_TOOLS,
    build_agent_options,
    build_unit_analyst_definition,
    project_root,
)
from docfit.app.settings import (
    AgentConfigurationError,
    agent_env_file_is_private,
    configured_backend_names,
    merged_agent_environment,
)
from docfit.tools import MCP_SERVER_NAME
from docfit.tools.adobe import AdobePdfServicesAdapter
from docfit.tools.image_smoke import make_smoke_png
from docfit.tools.images import poppler_versions
from docfit.tools.officecli import (
    OFFICECLI_EXPECTED_SHA256,
    OFFICECLI_EXPECTED_VERSION,
    OfficeCliAdapter,
)
from docfit.tools.runtime import ToolFailure, sha256_file

from .smoke import SMOKE_CASE_VERSIONS, SMOKE_CASES, receipt_directory

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
        if (
            payload.get("status") != "PASS"
            or payload.get("sdk_version") != sdk_version
            or payload.get("case_version", 1) != SMOKE_CASE_VERSIONS[case_name]
        ):
            invalid.append(case_name)
    if not missing and not invalid:
        return DoctorCheck(
            "agent_smoke_receipts",
            "PASS",
            f"All {len(SMOKE_CASES)} live smoke receipts match the installed SDK version.",
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
        *(project / ".claude" / "skills" / skill_name / "SKILL.md" for skill_name in SKILL_NAMES),
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
                else "Project metadata, lock, Python pin, and both domain Skills are present."
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
        hooks = options.hooks or {}
        agent_hooks = hooks.get("PreToolUse", [])
        unit_analyst = build_unit_analyst_definition()
        config_ok = (
            tuple(options.tools or ()) == BUILTIN_TOOLS
            and tuple(options.allowed_tools) == AUTO_APPROVED_TOOL_NAMES
            and mcp_names == (MCP_SERVER_NAME,)
            and options.setting_sources == ["project"]
            and options.skills == list(SKILL_NAMES)
            and options.agents is not None
            and tuple(options.agents) == (SUBAGENT_NAME,)
            and options.agents[SUBAGENT_NAME] == unit_analyst
            and tuple(hooks) == ("PreToolUse",)
            and len(agent_hooks) == 2
            and agent_hooks[0].matcher == "Read|Glob|Grep"
            and agent_hooks[1].matcher == "Agent"
            and tuple(unit_analyst.tools or ()) == READ_ONLY_SUBAGENT_TOOLS
            and unit_analyst.skills == []
            and unit_analyst.memory is None
        )
    except Exception:
        config_ok = False
    checks.append(
        DoctorCheck(
            "sdk_configuration",
            "PASS" if config_ok else "FAIL",
            (
                "Skill, path-bounded Read/Glob/Grep, trusted Bash/Write, AskUserQuestion, "
                "and Agent are visible; Agent is type-gated to one read-only definition and "
                "Bash, Write, plus the five DocFit names are pre-approved."
                if config_ok
                else "SDK permission or discovery configuration does not match the P1 contract."
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
            ("The Tool boundary fixes input as read-only and work/output as writable."),
            ("base", "agent-smoke", "provider"),
        )
    )
    trusted_basic_tools_ok = TRUSTED_BASIC_TOOLS == ("Bash", "Write")
    checks.append(
        DoctorCheck(
            "main_agent_trusted_basic_tools",
            "PASS" if trusted_basic_tools_ok else "FAIL",
            (
                "Bash and Write are visible and auto-approved for the main Agent without a "
                "DocFit path gate; the read-only unit analyst still receives neither tool."
            ),
            ("base", "agent-smoke", "provider"),
        )
    )
    read_policy_ok = MAIN_AGENT_READ_POLICY == (
        "project_skill_references_read_only",
        "product_knowledge_package_read_only",
        "current_task_input_read_only",
        "current_task_work_read_only",
        "current_task_output_read_only",
        "realpath_before_authorization",
        "sensitive_outside_and_symlink_escape_denied",
    )
    checks.append(
        DoctorCheck(
            "main_agent_read_policy",
            "PASS" if read_policy_ok else "FAIL",
            (
                "Read, Glob, and Grep require canonical paths under project Skill references, "
                "product Knowledge, or the current task; sensitive and escaping paths are denied."
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
            "The synthetic page image path is available for Agent iteration evidence.",
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
        env_file_detail = f"Shared Agent environment must have mode 0600: {selected_env_file}"
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

    try:
        office = OfficeCliAdapter()
        office_hash = sha256_file(office.executable)
        office_ok = (
            office.version == OFFICECLI_EXPECTED_VERSION
            and office_hash == OFFICECLI_EXPECTED_SHA256
        )
        office_detail = (
            f"OfficeCLI {office.version}; executable hash "
            f"{'matches' if office_hash == OFFICECLI_EXPECTED_SHA256 else 'does not match'} "
            "the locked M1 binary."
        )
    except ToolFailure as error:
        office_ok = False
        office_detail = error.message
    checks.append(
        DoctorCheck(
            "officecli_backend",
            "PASS" if office_ok else "NOT_READY",
            office_detail,
            ("provider",),
        )
    )

    try:
        adobe = AdobePdfServicesAdapter.from_environment(environment, env_file=env_file)
        adobe_ok = True
        adobe_detail = (
            f"Adobe PDF Services SDK {adobe.version}; service-principal configuration is ready."
        )
    except ToolFailure as error:
        adobe_ok = False
        adobe_detail = error.message
    checks.append(
        DoctorCheck(
            "adobe_pdf_services_backend",
            "PASS" if adobe_ok else "NOT_READY",
            adobe_detail,
            ("provider",),
        )
    )

    poppler = poppler_versions()
    poppler_ok = all(poppler.values())
    checks.append(
        DoctorCheck(
            "pdf_page_derivation",
            "PASS" if poppler_ok else "NOT_READY",
            (
                f"pdftoppm: {poppler['pdftoppm']}; pdfinfo: {poppler['pdfinfo']}."
                if poppler_ok
                else "pdftoppm and pdfinfo are both required for converted PDF page derivation."
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

"""Small deterministic M3 core Eval runner; not a workflow or evaluation platform."""

from __future__ import annotations

import json
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docfit.app.convert import REQUIRED_CONVERSION_TOOLS
from docfit.evals.fixtures import build_core_fixtures
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    read_json,
    sha256_file,
)
from docfit.tools.service import DocFitToolService


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    """One observable core-eval result without document bodies or model traces."""

    case_id: str
    layer: str
    status: str
    duration_seconds: float
    assertions: int
    metrics: JsonObject = field(default_factory=dict)
    failure: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class CoreEvalReport:
    """Serializable deterministic result plus explicit unexecuted product gates."""

    schema_version: int
    suite: str
    deterministic_status: str
    started_at: str
    duration_seconds: float
    fixture_hashes: JsonObject
    cases: tuple[EvalCaseResult, ...]
    metrics: JsonObject
    local_product_gates: JsonObject
    manual_gates: JsonObject
    report_path: str

    @property
    def passed(self) -> bool:
        return self.deterministic_status == "PASS"


class _FalseSuccessOffice(OfficeCliAdapter):
    """Test double that reports a successful batch while changing nothing."""

    def __init__(self, delegate: OfficeCliAdapter) -> None:
        self._delegate = delegate
        self.executable = delegate.executable
        self.timeout_seconds = delegate.timeout_seconds
        self.version = delegate.version

    def evidence(self) -> JsonObject:
        return self._delegate.evidence()

    def query(self, document: Path, selector: str) -> tuple[JsonObject, ...]:
        return self._delegate.query(document, selector)

    def get_document(self, document: Path) -> JsonObject:
        return self._delegate.get_document(document)

    def batch(self, document: Path, commands: list[JsonObject]) -> JsonObject:
        return {"reported_success": True, "command_count": len(commands)}

    def validate(self, document: Path) -> JsonObject:
        return self._delegate.validate(document)


def _ref(result: JsonObject, *, text: str | None = None, kind: str | None = None) -> JsonObject:
    objects = result.get("objects")
    if not isinstance(objects, list):
        raise AssertionError("inspection returned no object array")
    for item in objects:
        if not isinstance(item, dict):
            continue
        if text is not None and item.get("text") != text:
            continue
        if kind is not None and item.get("type") != kind:
            continue
        reference = item.get("object_ref")
        if isinstance(reference, dict):
            return reference
    raise AssertionError("expected object ref was not found")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run_case(case_id: str, layer: str, operation: Callable[[], JsonObject]) -> EvalCaseResult:
    started = time.monotonic()
    try:
        outcome = operation()
    except ToolFailure as error:
        return EvalCaseResult(
            case_id=case_id,
            layer=layer,
            status="FAIL",
            duration_seconds=round(time.monotonic() - started, 3),
            assertions=0,
            failure={"kind": "tool_failure", "origin": error.origin, "code": error.code},
        )
    except (AssertionError, OSError, ValueError, json.JSONDecodeError) as error:
        return EvalCaseResult(
            case_id=case_id,
            layer=layer,
            status="FAIL",
            duration_seconds=round(time.monotonic() - started, 3),
            assertions=0,
            failure={"kind": type(error).__name__, "code": "eval_assertion_failed"},
        )
    assertions = outcome.pop("assertions", 0)
    _assert(isinstance(assertions, int), "case assertion count must be an integer")
    return EvalCaseResult(
        case_id=case_id,
        layer=layer,
        status="PASS",
        duration_seconds=round(time.monotonic() - started, 3),
        assertions=assertions,
        metrics=outcome,
    )


def _fixture_hashes(fixtures: JsonObject) -> JsonObject:
    return {
        key: value
        for key, value in fixtures.items()
        if key.endswith("sha256") or key == "risk_fixture_count"
    }


def run_core_eval(repository: Path) -> CoreEvalReport:
    """Run deterministic Tool/Skill/App checks and write a metadata-only report."""

    repository = repository.resolve()
    started_wall = datetime.now(UTC)
    started = time.monotonic()
    fixtures = build_core_fixtures(repository)
    office = OfficeCliAdapter()
    service = DocFitToolService(office=office)
    run_root = Path(tempfile.mkdtemp(prefix="core-", dir=repository / ".tmp"))
    student = Path(str(fixtures["student"]))
    template = Path(str(fixtures["template"]))
    source_hash = str(fixtures["student_sha256"])
    state: dict[str, Any] = {}

    def tool_happy_path() -> JsonObject:
        inspection = service.inspect(
            {"task_root": str(repository), "input_docx": str(student)}
        )
        template_inspection = service.inspect(
            {"task_root": str(repository), "input_docx": str(template)}
        )
        _assert(inspection["status"] == "ok", "student inspection failed")
        _assert(template_inspection["status"] == "ok", "template inspection failed")
        plan = read_json(Path(str(fixtures["edit_plan"])))
        output = run_root / "edited.docx"
        edit = service.edit(
            {
                "task_root": str(repository),
                "input_docx": str(student),
                "output_docx": str(output),
                "operations": plan["operations"],
            }
        )
        _assert(edit["status"] == "ok" and edit["committed"] is True, "edit failed")
        _assert(sha256_file(student) == source_hash, "source changed")
        edited = service.inspect(
            {"task_root": str(repository), "input_docx": str(output)}
        )
        _assert(
            any(
                isinstance(item, dict) and item.get("text") == "Synthetic Student"
                for item in edited["objects"]
            ),
            "cross-run replacement is absent",
        )
        render = service.render(
            {
                "task_root": str(repository),
                "input_docx": str(output),
                "render_intent": "edit_feedback",
                "output_dir": str(run_root / "edit-feedback"),
                "focus_object_refs": [_ref(edited, kind="table")],
            }
        )
        reference = render["render_ref"]
        page_count = reference["page_count"]
        _assert(isinstance(page_count, int) and page_count >= 1, "render has no pages")
        review, images = service.visual_review(
            {
                "task_root": str(repository),
                "render_ref": render["render_ref_path"],
                "mode": "pages",
                "pages": list(range(1, page_count + 1)),
            }
        )
        _assert(review["status"] == "ok", "visual review failed")
        _assert(len(images) == page_count, "visual review did not return every page")
        layout = read_json(Path(str(reference["artifacts"]["layout_map"])))
        mapped = [
            item
            for page in layout["pages"]
            for item in page["elements"]
            if isinstance(item, dict)
        ]
        _assert(len(mapped) == 1, "table bbox was not mapped")
        _assert(mapped[0]["mapping_quality"] == "approximate", "bbox quality is incorrect")
        _assert(len(mapped[0]["bbox"]) == 4, "bbox is incomplete")
        validation = service.validate(
            {
                "task_root": str(repository),
                "source_docx": str(student),
                "source_sha256": source_hash,
                "final_docx": str(output),
            }
        )
        _assert(validation["status"] == "ok", "validation call failed")
        _assert(
            any(item.get("code") == "verification_gap" for item in validation["warnings"]),
            "missing Adobe delivery evidence was not preserved as a verification gap",
        )
        state.update({"inspection": inspection, "edited": output})
        return {
            "assertions": 13,
            "tool_calls": 7,
            "rendered_pages": page_count,
            "reviewed_pages": len(images),
            "layout_mappings": len(mapped),
            "render_cache_hit": bool(render["cache_hit"]),
        }

    def cross_run_risk() -> JsonObject:
        source = repository / "evals/fixtures/risks/cross-run-placeholder.docx"
        inspection = service.inspect(
            {"task_root": str(repository), "input_docx": str(source)}
        )
        output = run_root / "cross-run-edited.docx"
        edit = service.edit(
            {
                "task_root": str(repository),
                "input_docx": str(source),
                "output_docx": str(output),
                "operations": [
                    {
                        "action": "replace_text",
                        "target_ref": _ref(inspection, text="NAME_SLOT"),
                        "expected_text": "NAME_SLOT",
                        "replacement": "Synthetic Student",
                    }
                ],
            }
        )
        after = service.inspect(
            {"task_root": str(repository), "input_docx": str(output)}
        )
        _assert(edit["committed"] is True, "cross-run edit was not committed")
        _assert(
            any(item.get("text") == "Synthetic Student" for item in after["objects"]),
            "cross-run placeholder remained",
        )
        return {"assertions": 2, "tool_calls": 3}

    def stale_ref_risk() -> JsonObject:
        inspection = state.get("inspection")
        if not isinstance(inspection, dict):
            raise AssertionError("happy-path inspection is unavailable")
        stale = dict(_ref(inspection, text="Synthetic Thesis Title"))
        stale["document_sha256"] = "0" * 64
        output = run_root / "stale-must-not-exist.docx"
        try:
            service.edit(
                {
                    "task_root": str(repository),
                    "input_docx": str(student),
                    "output_docx": str(output),
                    "operations": [
                        {"action": "apply_style", "target_ref": stale, "style": "Heading1"}
                    ],
                }
            )
        except ToolFailure as error:
            _assert(error.status == "needs_input", "stale ref returned the wrong status")
        else:
            raise AssertionError("stale ref was accepted")
        _assert(not output.exists(), "stale-ref edit published an output")
        return {"assertions": 3, "tool_calls": 1}

    def provider_false_success_risk() -> JsonObject:
        inspection = state.get("inspection")
        if not isinstance(inspection, dict):
            raise AssertionError("happy-path inspection is unavailable")
        output = run_root / "false-success-must-not-exist.docx"
        false_service = DocFitToolService(office=_FalseSuccessOffice(office))
        try:
            false_service.edit(
                {
                    "task_root": str(repository),
                    "input_docx": str(student),
                    "output_docx": str(output),
                    "operations": [
                        {
                            "action": "set_properties",
                            "target_ref": _ref(inspection, text="Synthetic Thesis Title"),
                            "properties": {"alignment": "center"},
                        }
                    ],
                }
            )
        except ToolFailure as error:
            _assert(error.origin == "postcondition", "false success had wrong attribution")
            _assert(error.code == "properties_not_applied", "false success had wrong code")
        else:
            raise AssertionError("Provider false success was accepted")
        _assert(not output.exists(), "false-success edit published an output")
        return {"assertions": 3, "tool_calls": 1}

    def complex_fixture_risks() -> JsonObject:
        long_title = service.inspect(
            {
                "task_root": str(repository),
                "input_docx": "evals/fixtures/risks/blank-page-long-title.docx",
            }
        )
        complex_objects = service.inspect(
            {
                "task_root": str(repository),
                "input_docx": "evals/fixtures/risks/table-picture-layout.docx",
            }
        )
        _assert(long_title["document"]["paragraphs"] >= 2, "long-title fixture is empty")
        _assert(complex_objects["document"]["tables"] == 1, "table fixture is incomplete")
        _assert(
            complex_objects["document"]["graphic_objects"] >= 1,
            "picture relationship fixture is incomplete",
        )
        return {"assertions": 3, "tool_calls": 2}

    def skill_contracts() -> JsonObject:
        conversion_skill = (
            repository / ".claude/skills/convert-thesis/SKILL.md"
        ).read_text(encoding="utf-8")
        extraction_skill = (
            repository / ".claude/skills/docfit-school-extract/SKILL.md"
        ).read_text(encoding="utf-8")
        required_conversion_phrases = (
            "current-task school materials",
            "five DocFit Tools",
            "optionally delegate",
            "Do not force delegation",
            "main Agent",
        )
        required_extraction_phrases = (
            "current-task",
            "never a persistent school package",
            "optional read-only delegation",
            "Analyze directly",
            "Do not create fixed",
        )
        for phrase in required_conversion_phrases:
            _assert(phrase in conversion_skill, "conversion Skill contract drifted")
        for phrase in required_extraction_phrases:
            _assert(phrase in extraction_skill, "extraction Skill contract drifted")
        for scenario in sorted((repository / "evals/skills").glob("*.json")):
            payload = read_json(scenario)
            _assert(payload.get("scope") in {"simple", "complex", "mixed"}, "invalid scope")
            _assert(isinstance(payload.get("assertions"), list), "Skill assertions missing")
        _assert(len(list((repository / "evals/skills").glob("*.json"))) == 3, "Skill cases missing")
        return {"assertions": 13, "skill_cases": 3}

    def app_contract() -> JsonObject:
        _assert(
            {
                "Skill",
                "mcp__docfit__docx_inspect",
                "mcp__docfit__docx_edit",
                "mcp__docfit__docx_render",
                "mcp__docfit__docx_visual_review",
                "mcp__docfit__docx_validate",
            }
            == REQUIRED_CONVERSION_TOOLS,
            "conversion Tool completion contract drifted",
        )
        case = read_json(repository / "evals/e2e/synthetic-core/case.json")
        _assert(case.get("fixture") == "synthetic", "core e2e fixture must stay synthetic")
        _assert(
            case.get("requires_adobe_candidate") is True,
            "Adobe delivery gate was weakened",
        )
        _assert(case.get("requires_all_page_review") is True, "visual gate was weakened")
        return {"assertions": 4, "e2e_cases": 1}

    cases = (
        _run_case("tool-happy-path", "tool", tool_happy_path),
        _run_case("cross-run-placeholder", "tool", cross_run_risk),
        _run_case("stale-object-ref", "tool", stale_ref_risk),
        _run_case("provider-false-success", "tool", provider_false_success_risk),
        _run_case("complex-object-fixtures", "tool", complex_fixture_risks),
        _run_case("skill-static-contracts", "skill", skill_contracts),
        _run_case("thin-app-e2e-contract", "app", app_contract),
    )
    deterministic_status = "PASS" if all(case.status == "PASS" for case in cases) else "FAIL"
    report_path = repository / ".docfit/evals/core/latest.json"
    duration = round(time.monotonic() - started, 3)
    metrics: JsonObject = {
        "case_count": len(cases),
        "passed": sum(case.status == "PASS" for case in cases),
        "failed": sum(case.status == "FAIL" for case in cases),
        "assertions": sum(case.assertions for case in cases),
        "tool_calls": sum(
            int(case.metrics.get("tool_calls", 0)) for case in cases
        ),
        "rendered_pages": sum(
            int(case.metrics.get("rendered_pages", 0)) for case in cases
        ),
        "reviewed_pages": sum(
            int(case.metrics.get("reviewed_pages", 0)) for case in cases
        ),
    }
    report = CoreEvalReport(
        schema_version=1,
        suite="core",
        deterministic_status=deterministic_status,
        started_at=started_wall.isoformat(),
        duration_seconds=duration,
        fixture_hashes=_fixture_hashes(fixtures),
        cases=cases,
        metrics=metrics,
        local_product_gates={
            "claude_agent_sdk_e2e": "NOT_RUN_BY_DETERMINISTIC_SUITE",
            "adobe_pdf_services_baseline_candidate": "NOT_RUN_BY_DETERMINISTIC_SUITE",
            "authorized_or_deidentified_real_sample": "NOT_RUN_BY_DETERMINISTIC_SUITE",
        },
        manual_gates={
            "delivery_high_risk_page_review": "NOT_RUN_BY_DETERMINISTIC_SUITE",
            "checklist": "evals/manual/delivery-high-risk-checklist.md",
        },
        report_path=str(report_path),
    )
    atomic_write_json(report_path, asdict(report))
    return report

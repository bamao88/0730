from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from docfit.tools import docfit_check
from docfit.tools.runtime import ToolFailure, sha256_file
from docfit.tools.service import DocFitToolService
from docfit.tools.surface import CHECK_KINDS
from tests.contract.test_full_flow_source_identity import _fixture as _source_fixture


def _task_root(tmp_path: Path) -> tuple[Path, str, Path]:
    root = tmp_path / "task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK\x03\x04source")
    return root, sha256_file(source), source


def _real_task_root(tmp_path: Path) -> tuple[Path, str, Path]:
    root = tmp_path / "real-task"
    source = root / "input/school-template.docx"
    source.parent.mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).resolve().parents[2] / "evals/fixtures/smoke/school-template.docx",
        source,
    )
    return root, sha256_file(source), source


def _write_json(root: Path, relative: str, payload: object) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return relative


def _write_registry(root: Path, *, field_ids: tuple[str, ...]) -> None:
    fields = [
        {
            "field_id": field_id,
            "label": field_id,
            "meaning": "test field",
            "content_type": "text",
        }
        for field_id in field_ids
    ]
    _write_json(
        root,
        "input/field-registry.json",
        {
            "registry_id": "docfit.test.fields",
            "registry_version": "0.1.0",
            "fields": fields,
        },
    )


def _valid_judgment_payload() -> dict[str, object]:
    return {
        "semantic_judgments": [
            {
                "judgment_id": "j-fill-school-name",
                "responsibility": "fill_interface",
                "covered_object_ids": ["obj-1"],
                "registry_field": {"field_id": "school_name"},
                "interface_ref": "interface:school_name",
                "evidence": [{"object_id": "obj-1"}],
            }
        ]
    }


def _assert_semantic_authority_false(result: dict[str, object]) -> None:
    feedback = result.get("feedback")
    assert isinstance(feedback, dict)
    assert feedback["mechanical"] is True
    assert feedback["semantic_authority"] is False


def _snapshot(root: Path) -> dict[str, tuple[str, str]]:
    snapshot: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("dir", "")
        else:
            snapshot[relative] = ("file", sha256_file(path))
    return snapshot


def test_t2_docfit_check_handler_is_read_only_and_uses_service_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert docfit_check.annotations.readOnlyHint is True

    class _FakeService:
        def check(self, args: dict[str, object]) -> dict[str, object]:
            return {
                "schema_version": "mechanical_feedback_v1",
                "status": "ok",
                "check": args["check"],
                "source_hash": "a" * 64,
                "feedback": {
                    "type": "docfit_check",
                    "mechanical": True,
                    "semantic_authority": False,
                },
                "checks": [{"name": args["check"], "result": "ok"}],
                "warnings": [],
                "failure": None,
            }

    monkeypatch.setattr("docfit.tools.DocFitToolService", _FakeService)

    result = asyncio.run(
        docfit_check.handler(
            {
                "schema_version": "docfit_check_input_v1",
                "check": "hash_binding",
            }
        )
    )

    structured = result["structuredContent"]
    assert structured["status"] == "ok"
    assert structured["check"] == "hash_binding"
    _assert_semantic_authority_false(structured)


@pytest.mark.parametrize("check", CHECK_KINDS)
def test_t2_every_check_returns_semantic_authority_false(
    tmp_path: Path,
    check: str,
) -> None:
    if check == "unit_coverage":
        root = tmp_path / "task"
        _source_fixture(root)
    else:
        root, _source_hash, _source = _task_root(tmp_path)
    judgment_ref = _write_json(root, "work/judgments.json", _valid_judgment_payload())
    service = DocFitToolService(task_root=root)
    args: dict[str, object] = {
        "schema_version": "docfit_check_input_v1",
        "check": check,
    }
    if check == "judgment_shape":
        args["payload_ref"] = judgment_ref
    if check == "unit_coverage":
        # Valid host state, invalid proposal: this is mechanical Agent feedback.
        args["payload"] = {"units": []}

    result = service.check(args)

    _assert_semantic_authority_false(result)


def test_t2_negative_feedback_covers_expected_blocker_codes(tmp_path: Path) -> None:
    root, source_hash, source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    with pytest.raises(ToolFailure) as retired_source_hash:
        service.check({"source_hash": source_hash, "check": "hash_binding"})
    assert retired_source_hash.value.code == "schema_envelope_invalid"
    assert "source_hash" in retired_source_hash.value.message

    with pytest.raises(ToolFailure) as retired_scope_ref:
        service.check({"scope_ref": "input/school-template.docx", "check": "hash_binding"})
    assert retired_scope_ref.value.code == "schema_envelope_invalid"
    assert "scope_ref" in retired_scope_ref.value.message

    source.write_bytes(b"PK\x03\x04changed")
    shape_gap = service.check(
        {
            "check": "judgment_shape",
        }
    )
    assert shape_gap["failure"]["code"] == "check_kind_retired"
    assert shape_gap["blockers"][0]["field"] == "check"

    missing_target = service.check({"check": "completion_gate"})
    assert missing_target["failure"]["code"] == "completion_gap"
    assert "missing_target" in {blocker["code"] for blocker in missing_target["blockers"]}

    registry_gap = service.check({"check": "registry_binding"})
    assert registry_gap["failure"]["code"] == "check_kind_retired"

    style_gap = service.check({"check": "style_evidence"})
    assert style_gap["failure"]["code"] == "style_evidence_insufficient"


def test_t2_check_defaults_source_hash_from_bound_task_root(tmp_path: Path) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "hash_binding",
        }
    )

    assert result["status"] == "ok"
    assert result["source_hash"] == source_hash
    _assert_semantic_authority_false(result)


def test_t2_candidate_validation_accepts_candidate_hash_without_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, object]] = []

    def fake_validate(args: dict[str, object]) -> dict[str, object]:
        seen.append(args)
        return {
            "schema_version": 1,
            "status": "ok",
            "checks": [],
            "warnings": [],
            "failure": None,
            "source_sha256": source_hash,
            "final_sha256": source_hash,
        }

    monkeypatch.setattr(service, "validate", fake_validate)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "candidate_hash": source_hash,
            "check": "candidate_validation",
        }
    )

    assert result["status"] == "ok"
    assert result["check"] == "candidate_validation"
    assert result["candidate_hash"] == source_hash
    assert seen[-1]["source_docx"] == "input/school-template.docx"
    assert seen[-1]["final_docx"] == "input/school-template.docx"
    assert result["validation"]["final_sha256"] == source_hash
    _assert_semantic_authority_false(result)


def test_t2_completion_gate_reports_missing_reviewed_pages_without_payload(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    class FakeStore:
        def resolve_render(self, _render_ref: str):
            return Path("/tmp/render"), {"page_count": 1, "document_sha256": source_hash}

    class FakeVisual:
        store = FakeStore()

    service._visual = FakeVisual()  # type: ignore[assignment]
    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "candidate_hash": source_hash,
            "check": "completion_gate",
            "render_ref": "render:v2:" + "a" * 64,
        }
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "completion_evidence_missing"
    assert any(blocker["field"] == "reviewed_pages" for blocker in result["blockers"])
    assert any("reviewed_pages=[1]" in item for item in result["failure"]["suggested_actions"])
    assert any("Do not repeat" in item for item in result["failure"]["suggested_actions"])
    _assert_semantic_authority_false(result)


def test_t2_visual_coverage_reports_missing_render_and_reviewed_pages_without_payload(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "candidate_hash": source_hash,
            "check": "visual_coverage",
        }
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "completion_evidence_missing"
    assert {blocker["field"] for blocker in result["blockers"]} == {
        "render_ref",
        "reviewed_pages",
    }
    assert any(
        "docfit_check(visual_coverage)" in item for item in result["failure"]["suggested_actions"]
    )
    _assert_semantic_authority_false(result)


def test_t2_completion_gate_accepts_candidate_hash_render_and_reviewed_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)
    seen: list[dict[str, object]] = []

    def fake_validate(args: dict[str, object]) -> dict[str, object]:
        seen.append(args)
        return {
            "schema_version": 1,
            "status": "ok",
            "checks": [],
            "warnings": [],
            "failure": None,
            "source_sha256": source_hash,
            "final_sha256": source_hash,
        }

    monkeypatch.setattr(service, "validate", fake_validate)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "candidate_hash": source_hash,
            "check": "completion_gate",
            "render_ref": "render:v2:" + "a" * 64,
            "reviewed_pages": [1],
        }
    )

    assert result["status"] == "ok"
    assert result["check"] == "completion_gate"
    assert seen[-1]["required_visual_coverage"] == "all_final_pages"
    assert seen[-1]["visual_review"] == {
        "document_sha256": source_hash,
        "render_ref": "render:v2:" + "a" * 64,
        "reviewed_pages": [1],
        "findings": [],
    }
    _assert_semantic_authority_false(result)


def test_t2_legacy_judgment_shape_check_is_retired(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "judgment_shape",
        }
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "check_kind_retired"
    assert any(blocker["field"] == "check" for blocker in result["blockers"])
    assert any("scope, ordered parts" in item for item in result["failure"]["suggested_actions"])
    _assert_semantic_authority_false(result)


def test_t2_closure_aggregation_check_is_retired_fail_closed(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    payload_ref = _write_json(
        root,
        "work/old-closures.json",
        {
            "context_profile": "cover-v1",
            "expected_scope_ids": ["cover"],
            "closures": [
                {
                    "schema_version": "scoped_closure_v1",
                    "source_hash": source_hash,
                    "closure_id": "closure-cover",
                    "assigned_scope": {
                        "scope_id": "cover",
                        "object_ids": ["obj-1"],
                    },
                    "status": "complete",
                }
            ],
        },
    )
    service = DocFitToolService(task_root=root)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "closure_aggregation",
            "payload_ref": payload_ref,
        }
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "check_kind_retired"
    assert result["blockers"][0]["field"] == "check"
    assert "Subagent scoped-closure payloads" in result["blockers"][0]["message"]
    _assert_semantic_authority_false(result)


def test_t2_coverage_closure_check_is_retired_from_post_unit_contract(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "coverage_closure",
        }
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "check_kind_retired"
    assert result["blockers"][0]["field"] == "check"
    assert "host Harness" in " ".join(result["failure"]["suggested_actions"])
    _assert_semantic_authority_false(result)


def test_t2_action_plan_check_is_retired_from_post_unit_contract(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    service = DocFitToolService(task_root=root)

    result = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "candidate_hash": source_hash,
            "check": "action_plan",
            "payload": {"semantic_judgments": []},
        }
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "check_kind_retired"
    assert result["blockers"][0]["field"] == "check"
    assert any("semantic_judgments" in item for item in result["failure"]["suggested_actions"])
    assert not any(
        "action_requirement" in item or "action_plan" in item
        for item in result["failure"]["suggested_actions"]
    )
    _assert_semantic_authority_false(result)


def test_t2_registry_binding_check_is_retired_fail_closed(
    tmp_path: Path,
) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    _write_registry(root, field_ids=("author.name.zh",))
    service = DocFitToolService(task_root=root)

    missing_field = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "registry_binding",
        }
    )
    with_valid_registry_field = service.check(
        {
            "schema_version": "docfit_check_input_v1",
            "check": "registry_binding",
            "field_id": "author.name.zh",
        }
    )

    assert missing_field["status"] == "needs_input"
    assert missing_field["failure"]["code"] == "check_kind_retired"
    assert with_valid_registry_field["status"] == "needs_input"
    assert with_valid_registry_field["failure"]["code"] == "check_kind_retired"
    assert "field_id_vocabulary" in with_valid_registry_field["failure"]["suggested_actions"][0]
    _assert_semantic_authority_false(missing_field)
    _assert_semantic_authority_false(with_valid_registry_field)


# Exact partition, repeated-text, internal-cut, gap/overlap and stale-proof coverage
# lives in test_full_flow_source_identity.py and exercises the public unit_coverage Tool.


def test_t2_docfit_check_does_not_write_files(tmp_path: Path) -> None:
    root, source_hash, _source = _task_root(tmp_path)
    payload_ref = _write_json(root, "work/payload.json", {"ok": True})
    service = DocFitToolService(task_root=root)
    args_by_check: dict[str, dict[str, object]] = {
        check: {
            "schema_version": "docfit_check_input_v1",
            "check": check,
        }
        for check in CHECK_KINDS
    }
    for check in (
        "visual_coverage",
        "candidate_validation",
        "completion_gate",
        "publication_readiness",
    ):
        args_by_check[check]["payload_ref"] = payload_ref

    before = _snapshot(root)
    for args in args_by_check.values():
        if args["check"] == "unit_coverage":
            # Missing host state is an exception, and must still remain read-only.
            with pytest.raises(ToolFailure) as caught:
                service.check(args)
            assert caught.value.code == "initial_source_inventory_invalid"
            assert caught.value.origin == "harness"
        else:
            service.check(args)

    assert _snapshot(root) == before

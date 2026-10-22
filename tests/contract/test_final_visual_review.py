from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from docfit.template.final_visual_review import (
    CRITERIA,
    REVIEW_SCHEMA,
    require_final_visual_review,
    validate_final_visual_review,
)
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file
from docfit.visual.evidence import EvidenceStore, render_reference


class SyntheticVisual:
    """Contract fixture only: no renderer or visual judgment model is invoked."""

    def __init__(self, root):
        self.task_root = root
        self.store = EvidenceStore(root)
        self.requested_pages = []

    def render(self, args):
        document_hash = sha256_file(Path(args["input_docx"]))
        identity = {"document_sha256": document_hash, "fixture": True}
        reference = render_reference(identity)
        try:
            _, manifest = self.store.resolve_render(reference)
        except ToolFailure:
            temporary = self.store.temporary_render(reference)
            pdf = temporary / "document.pdf"
            pdf.write_bytes(b"%PDF-synthetic-contract-fixture")
            manifest = {
                "schema_version": 2,
                "render_ref": reference,
                "document_sha256": document_hash,
                "page_count": 6,
                "fidelity": "approximate",
                "renderer": {"name": "libreoffice"},
                "files": self.store.file_inventory(temporary, [pdf]),
            }
            atomic_write_json(temporary / "manifest.json", manifest)
            self.store.publish_render(temporary, reference)
        return manifest, []

    def review(self, args):
        pages = args["pages"]
        assert len(pages) <= 4
        self.requested_pages.append(pages)
        views = []
        for page in pages:

            def build(path, number=page):
                Image.new("RGB", (20, 20), (number, 0, 0)).save(path)
                return {"page": number}

            views.append(
                self.store.get_or_create_view(
                    render_ref=args["render_ref"],
                    identity={
                        "render_ref": args["render_ref"],
                        "view": "page",
                        "page": page,
                        "dpi": 144,
                    },
                    stem=f"page-{page}",
                    build=build,
                )
            )
        return {"evidence": [{"evidence_ref": view.reference} for view in views]}, [
            v.path for v in views
        ]


@pytest.fixture
def case(tmp_path):
    source, candidate = tmp_path / "source.docx", tmp_path / "candidate.docx"
    source.write_bytes(b"synthetic-source")
    candidate.write_bytes(b"synthetic-candidate")
    visual = SyntheticVisual(tmp_path)
    kwargs = dict(task_root=tmp_path, source_docx=source, candidate_docx=candidate, visual=visual)
    with pytest.raises(ToolFailure) as caught:
        require_final_visual_review(**kwargs)
    assert caught.value.code == "final_visual_review_required"
    assert caught.value.status == "needs_input"
    current = json.loads((tmp_path / "work/.docfit/final-visual-review/current.json").read_text())
    request = json.loads((tmp_path / current["request_path"]).read_text())
    review = copy.deepcopy(request["review_template"])
    review["status"] = "passed"
    review["reviewer"] = {
        "kind": "external_visual_reviewer",
        "name": "synthetic-test-fixture",
        "reviewed_at": "2026-09-23T00:00:00+00:00",
    }
    for row in review["pages"]:
        row["checks"] = {
            key: {"status": "passed", "observation": "Synthetic contract assertion."}
            for key in CRITERIA
        }
    return kwargs, current, request, review


def validate(case, review=None):
    kwargs, _, _, baseline = case
    validate_final_visual_review(
        baseline if review is None else review,
        candidate_hash=sha256_file(kwargs["candidate_docx"]),
        source_hash=sha256_file(kwargs["source_docx"]),
        store=kwargs["visual"].store,
    )


def test_prepares_every_source_and_final_page_before_requiring_review(case):
    kwargs, current, request, review = case
    assert kwargs["visual"].requested_pages == [[1, 2, 3, 4], [5, 6]] * 2
    assert len(request["source_pages"]) == len(request["candidate_pages"]) == 6
    assert request["review_template"]["status"] == "pending"
    assert not (kwargs["task_root"] / current["review_path"]).exists()
    assert not (kwargs["task_root"] / "output/final-template.docx").exists()
    validate(case)
    atomic_write_json(kwargs["task_root"] / current["review_path"], review)
    result = require_final_visual_review(**kwargs)
    assert result["reviewed_pages"] == [1, 2, 3, 4, 5, 6]
    # A new candidate gets a new request, retaining but invalidating the old review.
    kwargs["candidate_docx"].write_bytes(b"changed-candidate")
    with pytest.raises(ToolFailure) as caught:
        require_final_visual_review(**kwargs)
    assert caught.value.code == "final_visual_review_required"
    assert json.loads((kwargs["task_root"] / current["review_path"]).read_text()) == review


@pytest.mark.parametrize(
    "defect",
    [
        "legacy",
        "pending",
        "blocked",
        "stale",
        "missing_page",
        "duplicate_page",
        "no_reviewer",
        "empty_observation",
        "uncertain",
        "blocking",
        "thumbnail",
        "image_corrupt",
        "render_corrupt",
        "wrong_page",
    ],
)
def test_missing_stale_incomplete_or_blocked_review_is_rejected(case, defect):
    kwargs, _, _, baseline = case
    review = copy.deepcopy(baseline)
    if defect == "legacy":
        review = {
            "document_sha256": review["document_sha256"],
            "reviewed_pages": list(range(1, 7)),
            "findings": [],
        }
    elif defect in ("pending", "blocked"):
        review["status"] = defect
    elif defect == "stale":
        review["document_sha256"] = "f" * 64
    elif defect == "missing_page":
        review["pages"].pop()
    elif defect == "duplicate_page":
        review["pages"][-1] = copy.deepcopy(review["pages"][0])
    elif defect == "no_reviewer":
        review.pop("reviewer")
    elif defect in ("empty_observation", "uncertain"):
        review["pages"][0]["checks"][CRITERIA[0]][
            "observation" if defect == "empty_observation" else "status"
        ] = "" if defect == "empty_observation" else "uncertain"
    elif defect == "blocking":
        review["findings"] = [{"status": "open", "blocking": True, "message": "Overflow"}]
    elif defect == "wrong_page":
        review["pages"][0]["evidence_ref"] = review["pages"][1]["evidence_ref"]
    elif defect == "thumbnail":
        view = kwargs["visual"].store.get_or_create_view(
            render_ref=review["render_ref"],
            identity={"render_ref": review["render_ref"], "view": "page", "page": 1, "dpi": 72},
            stem="thumbnail",
            build=lambda p: Image.new("RGB", (10, 10)).save(p) or {"page": 1},
        )
        review["pages"][0]["evidence_ref"] = view.reference
    elif defect == "image_corrupt":
        kwargs["visual"].store.resolve_view(review["pages"][0]["evidence_ref"]).path.write_bytes(
            b"bad"
        )
    elif defect == "render_corrupt":
        path, _ = kwargs["visual"].store.resolve_render(review["render_ref"])
        (path / "document.pdf").write_bytes(b"changed")
    with pytest.raises(ToolFailure):
        validate(case, review)


def test_schema_is_separate_from_product_acceptance(case):
    _, _, request, review = case
    assert review["schema_version"] == REVIEW_SCHEMA
    assert "does not sign off the product" in request["instructions"]
    assert "accepted_semantics_path" in request


def test_default_host_completion_requires_review_before_validation(case, monkeypatch):
    from types import SimpleNamespace

    from docfit.app.prepare_template import _validate_host_candidate

    kwargs, current, _, review = case
    prepared = SimpleNamespace(
        task_root=kwargs["task_root"],
        template_path=kwargs["source_docx"],
        template_sha256=sha256_file(kwargs["source_docx"]),
    )
    calls = []
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.visual", lambda self: kwargs["visual"]
    )

    def validate_doc(self, args):
        calls.append(args)
        assert args["required_visual_coverage"] == "all_final_pages"
        assert args["visual_review"]["schema_version"] == REVIEW_SCHEMA
        assert args["candidate_render_ref"] == review["render_ref"]
        return {"status": "ok", "checks": []}

    monkeypatch.setattr("docfit.app.prepare_template.DocFitToolService.validate", validate_doc)
    with pytest.raises(ToolFailure) as caught:
        _validate_host_candidate(prepared, kwargs["candidate_docx"])
    assert caught.value.code == "final_visual_review_required"
    assert not calls
    atomic_write_json(kwargs["task_root"] / current["review_path"], review)
    result, validation = _validate_host_candidate(prepared, kwargs["candidate_docx"])
    assert result["status"] == "passed" and validation["status"] == "ok"
    assert len(calls) == 1


@pytest.mark.parametrize("status", ["legacy", "pending", "blocked", "passed"])
def test_direct_publisher_cannot_bypass_visual_review(case, monkeypatch, status):
    from docfit.template.artifact import publish_template_artifact

    kwargs, _, _, original = case
    review = copy.deepcopy(original)
    if status == "legacy":
        review = {"document_sha256": review["document_sha256"]}
    else:
        review["status"] = status
    # The gate runs before Word/style work. This sentinel marks its far side;
    # no fake document is claimed to be a publishable artifact.
    monkeypatch.setattr("docfit.template.artifact.FieldRegistrySnapshot.load", lambda _: object())

    class AfterVisualGate(Exception):
        pass

    def stop_after_gate(_):
        raise AfterVisualGate

    monkeypatch.setattr("docfit.template.artifact.validate_docx_package", stop_after_gate)
    with pytest.raises(AfterVisualGate if status == "passed" else ToolFailure):
        publish_template_artifact(
            task_root=kwargs["task_root"],
            source_docx=kwargs["source_docx"],
            candidate_docx=kwargs["candidate_docx"],
            field_registry=kwargs["source_docx"],
            validation={"final_sha256": sha256_file(kwargs["candidate_docx"]), "status": "ok"},
            visual_review=review,
        )
    assert not (kwargs["task_root"] / "output/final-template.docx").exists()


@pytest.mark.parametrize("has_review", [False, True])
def test_completed_task_resume_rechecks_saved_visual_review(case, monkeypatch, has_review):
    from types import SimpleNamespace

    from docfit.app.prepare_template import _PUBLICATION, _TRACE, _load_completed

    kwargs, _, _, review = case
    root = kwargs["task_root"]
    artifact = root / "output/final-template.docx"
    artifact.parent.mkdir()
    artifact.write_bytes(kwargs["candidate_docx"].read_bytes())
    contract = {"validation": {"final_visual_review": review}} if has_review else {}
    atomic_write_json(root / _PUBLICATION, contract)
    atomic_write_json(root / "work/.docfit/template-publication/build-report.json", {})
    atomic_write_json(
        root / _TRACE,
        {"architecture": "main_agent_full_context/v1", "publication": {}, "agent_completion": {}},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template.validate_published_template_artifact",
        lambda **kw: {"source_partition": {}},
    )
    monkeypatch.setattr("docfit.app.prepare_template.require_initial_binding", lambda *a: None)
    prepared = SimpleNamespace(task_root=root, template_sha256=sha256_file(kwargs["source_docx"]))
    if has_review:
        assert _load_completed(prepared) is not None
    else:
        with pytest.raises(ToolFailure) as caught:
            _load_completed(prepared)
        assert caught.value.code == "final_visual_review_missing"


def test_renderer_unavailable_stays_an_environment_failure(case, monkeypatch):
    kwargs, _, _, _ = case

    def unavailable(args):
        raise ToolFailure(
            status="error",
            origin="environment",
            code="renderer_unavailable",
            message="Synthetic environment failure",
        )

    monkeypatch.setattr(kwargs["visual"], "render", unavailable)
    with pytest.raises(ToolFailure) as caught:
        require_final_visual_review(**kwargs)
    assert caught.value.origin == "environment"
    assert caught.value.code == "renderer_unavailable"


def test_waiting_review_reuses_exact_candidate_until_accepted_inputs_change(tmp_path):
    from types import SimpleNamespace

    from docfit.app.prepare_template import (
        _POST_UNIT_MATERIALIZATION_RECEIPT,
        _resume_materialized_candidate,
    )

    prepared = SimpleNamespace(task_root=tmp_path)
    candidate = tmp_path / "work/.docfit/post-unit-materialization/candidate-0001.docx"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"immutable-candidate")
    binding = {"source_sha256": "a" * 64, "semantic_judgments_sha256": "b" * 64}
    receipt = {
        "schema_version": 2,
        "status": "ok",
        "materialization_input_binding": binding,
        "candidate_docx": str(candidate.relative_to(tmp_path)),
        "candidate_sha256": sha256_file(candidate),
    }
    atomic_write_json(tmp_path / _POST_UNIT_MATERIALIZATION_RECEIPT, receipt)
    assert _resume_materialized_candidate(prepared, binding) is None
    receipt.update(
        document_sha256=binding["source_sha256"],
        semantic_judgments_sha256=binding["semantic_judgments_sha256"],
        write={"output_sha256": sha256_file(candidate)},
        effect_verification={
            "schema_version": 3, "status": "ok", "reopened_package": True,
            "source_sha256": binding["source_sha256"],
            "semantic_judgments_sha256": binding["semantic_judgments_sha256"],
            "candidate_sha256": sha256_file(candidate),
        },
    )
    atomic_write_json(tmp_path / _POST_UNIT_MATERIALIZATION_RECEIPT, receipt)
    assert _resume_materialized_candidate(prepared, binding) == candidate
    for old_version in (1, 2):
        receipt["effect_verification"]["schema_version"] = old_version
        atomic_write_json(tmp_path / _POST_UNIT_MATERIALIZATION_RECEIPT, receipt)
        assert _resume_materialized_candidate(prepared, binding) is None
    receipt["effect_verification"]["schema_version"] = 3
    atomic_write_json(tmp_path / _POST_UNIT_MATERIALIZATION_RECEIPT, receipt)
    assert (
        _resume_materialized_candidate(prepared, {**binding, "semantic_judgments_sha256": "c" * 64})
        is None
    )
    candidate.write_bytes(b"changed-without-a-new-review")
    with pytest.raises(ToolFailure) as caught:
        _resume_materialized_candidate(prepared, binding)
    assert caught.value.code == "template_materialization_candidate_changed"
    candidate.unlink()
    with pytest.raises(ToolFailure):
        _resume_materialized_candidate(prepared, binding)


@pytest.mark.parametrize(
    "validation",
    [
        {"status": "needs_input"},
        {"status": "error"},
        {"status": "ok", "checks": [{"blocking": True}]},
        {"status": "ok", "failure": {"code": "validation_failed"}},
        {"status": "ok", "checks": "invalid"},
    ],
)
def test_publisher_rejects_failed_objective_validation_even_with_visual_pass(
    case, monkeypatch, validation
):
    from docfit.template.artifact import publish_template_artifact

    kwargs, _, _, review = case
    monkeypatch.setattr("docfit.template.artifact.FieldRegistrySnapshot.load", lambda _: object())
    with pytest.raises(ToolFailure) as caught:
        publish_template_artifact(
            task_root=kwargs["task_root"],
            source_docx=kwargs["source_docx"],
            candidate_docx=kwargs["candidate_docx"],
            field_registry=kwargs["source_docx"],
            validation={"final_sha256": sha256_file(kwargs["candidate_docx"]), **validation},
            visual_review=review,
        )
    assert caught.value.code == "template_validation_blocked"
    assert not (kwargs["task_root"] / "output/final-template.docx").exists()

from __future__ import annotations

import asyncio
import json
import shutil
import zipfile
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from PIL import Image

from docfit.template.comparison import TemplateComparisonService
from docfit.template.compile_artifact import compile_artifact_decisions
from docfit.template.observation import TemplateObservationService
from docfit.template.ports import RenderedDocument
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.template_tools import template_build

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = PROJECT_ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"


class _CandidateRenderer:
    def render(
        self,
        document: Path,
        *,
        visual_level: str,
        output: Path,
    ) -> RenderedDocument:
        assert visual_level == "candidate_verification"
        pages_directory = output / "pages"
        pages_directory.mkdir()
        page = pages_directory / "page-0001.png"
        Image.new("RGB", (80, 120), "white").save(page)
        return RenderedDocument((page,), {"name": "fake-boundary"})


def _prepare_spec(task_root: Path) -> tuple[dict[str, object], Path]:
    source = task_root / "input/template.docx"
    registry = task_root / "input/content-fields.yaml"
    observed = TemplateObservationService().create(
        {
            "input_docx": "input/template.docx",
            "visual_level": "none",
            "focus": ["structure", "slot_candidates"],
        },
        task_root=task_root,
    )
    compared = TemplateComparisonService(_CandidateRenderer()).final_review(
        {
            "review_mode": "final_review",
            "final_snapshot_ref": observed["snapshot_ref"],
            "visual_level": "candidate_verification",
        },
        task_root=task_root,
    )
    first_object = observed["objects"][0]
    decisions = {
        "schema_version": 1,
        "final_snapshot_ref": observed["snapshot_ref"],
        "template_sha256": sha256_file(source),
        "field_registry_ref": {
            "path": "input/content-fields.yaml",
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.1.0",
            "sha256": sha256_file(registry),
        },
        "marker_protocol": "docfit-content-control-marker/v1",
        "sources": [
            {
                "source_id": "school-template",
                "path": "input/template.docx",
                "sha256": sha256_file(source),
                "authority": "supplied_school_template",
                "scope": "template_structure",
            }
        ],
        "protected_regions": [
            {
                "region_id": "protected.student_name_label",
                "owner": "protected",
                "required": True,
                "execution_locator": {
                    "snapshot_ref": observed["snapshot_ref"],
                    "object_id": first_object["object_id"],
                    "expected_fingerprint": first_object["expected_fingerprint"],
                },
                "artifact_locator": {
                    "type": "text_anchor",
                    "story": "document",
                    "part": "word/document.xml",
                    "left_anchor": "姓名：",
                    "occurrence": 1,
                    "expected_match_count": 1,
                },
                "expected_fingerprint": first_object["expected_fingerprint"],
                "source_refs": ["school-template"],
                "expected_style": {},
            }
        ],
        "slots": [
            {
                "slot_id": "docfit.cover.student_name",
                "owner": "slot",
                "field_id": "author.name.zh",
                "content_type": "text",
                "required": True,
                "cardinality": "one",
                "execution_locator": {
                    "snapshot_ref": observed["snapshot_ref"],
                    "object_id": first_object["object_id"],
                    "expected_fingerprint": first_object["expected_fingerprint"],
                },
                "artifact_locator": {
                    "type": "content_control_tag",
                    "value": "docfit.cover.student_name",
                    "story": "document",
                    "part": "word/document.xml",
                    "paragraph_index": 0,
                    "left_anchor": "姓名：",
                    "occurrence": 1,
                    "expected_match_count": 1,
                },
                "marker": {
                    "alias": "author.name.zh",
                    "tag": "docfit.cover.student_name",
                },
                "expected_value_style": {},
                "source_refs": ["school-template"],
                "style_claim_refs": [],
            }
        ],
        "remove_regions": [],
        "manual": [],
        "gaps": [],
        "unresolved": [],
        "style_claims": [],
        "mutation_evidence_chain": [],
        "final_review": {
            "final_snapshot_ref": observed["snapshot_ref"],
            "comparison_ref": compared["comparison_ref"],
            "visual_level": "candidate_verification",
            "page_count": 1,
            "image_dispositions": [
                {
                    "required_image_id": "image-final-page-0001",
                    "disposition": "accepted",
                    "finding_refs": [],
                }
            ],
            "finding_dispositions": [],
        },
    }
    decision_path = task_root / "work/decisions/artifact-decisions.yaml"
    decision_path.parent.mkdir()
    decision_path.write_text(yaml.safe_dump(decisions, allow_unicode=True), encoding="utf-8")
    spec_path = task_root / "work/compiled/artifact-spec.json"
    spec_path.parent.mkdir()
    compiled = compile_artifact_decisions(
        task_root=task_root,
        input_path=decision_path,
        output_path=spec_path,
    )
    return compiled, spec_path


def test_zero_mutation_build_publishes_exact_four_file_artifact(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    (task_root / "input").mkdir(parents=True)
    (task_root / "work").mkdir()
    (task_root / "output").mkdir()
    shutil.copyfile(FIXTURE, task_root / "input/template.docx")
    shutil.copyfile(REGISTRY, task_root / "input/content-fields.yaml")
    source_hash = sha256_file(task_root / "input/template.docx")
    compiled, spec_path = _prepare_spec(task_root)

    result = asyncio.run(
        template_build.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "final_snapshot_ref": compiled["task_binding"]["snapshot_ref"],
                "artifact_spec_path": str(spec_path.relative_to(task_root)),
                "output_dir": "output/template-artifact",
            }
        )
    )["structuredContent"]

    artifact = task_root / "output/template-artifact"
    assert result["call_status"] == "ok"
    assert result["result_state"] == "built"
    assert result["artifact_status"] == "built"
    assert result["published"] is True
    assert {path.name for path in artifact.iterdir()} == {
        "clean-template.docx",
        "fill-contract.json",
        "visual-review.json",
        "build-report.json",
    }
    assert sha256_file(artifact / "clean-template.docx") == source_hash
    with zipfile.ZipFile(artifact / "clean-template.docx") as archive:
        assert "word/document.xml" in archive.namelist()
    contract = json.loads((artifact / "fill-contract.json").read_text())
    schema = json.loads(
        (PROJECT_ROOT / "evals/template-extraction/schemas/fill-contract.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(contract)
    assert contract["schema_version"] == "docfit-template-fill-contract/v1"
    assert contract["template_sha256"] == source_hash
    assert contract["slots"][0]["field_id"] == "author.name.zh"
    assert contract["slots"][0]["locator"]["value"] == "docfit.cover.student_name"
    report = json.loads((artifact / "build-report.json").read_text())
    assert report["artifact_status"] == "built"
    assert report["file_hashes"]["fill-contract.json"] == sha256_file(
        artifact / "fill-contract.json"
    )
    assert sha256_file(task_root / "input/template.docx") == source_hash


def test_build_rejects_existing_output_without_overwrite(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    (task_root / "input").mkdir(parents=True)
    (task_root / "work").mkdir()
    (task_root / "output/template-artifact").mkdir(parents=True)
    shutil.copyfile(FIXTURE, task_root / "input/template.docx")
    shutil.copyfile(REGISTRY, task_root / "input/content-fields.yaml")
    compiled, spec_path = _prepare_spec(task_root)

    result = asyncio.run(
        template_build.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "final_snapshot_ref": compiled["task_binding"]["snapshot_ref"],
                "artifact_spec_path": str(spec_path.relative_to(task_root)),
                "output_dir": "output/template-artifact",
            }
        )
    )["structuredContent"]

    assert result["call_status"] == "needs_input"
    assert result["failure"]["code"] == "output_exists"
    assert list((task_root / "output/template-artifact").iterdir()) == []


def test_build_revalidates_marker_semantics_in_digest_valid_spec(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    (task_root / "input").mkdir(parents=True)
    (task_root / "work").mkdir()
    (task_root / "output").mkdir()
    shutil.copyfile(FIXTURE, task_root / "input/template.docx")
    shutil.copyfile(REGISTRY, task_root / "input/content-fields.yaml")
    compiled, _ = _prepare_spec(task_root)
    compiled["slots"][0]["marker"]["alias"] = "thesis.title.zh"
    compiled.pop("spec_digest")
    compiled["spec_digest"] = sha256_json(compiled)
    bad_spec = task_root / "work/compiled/bad-artifact-spec.json"
    bad_spec.write_text(json.dumps(compiled), encoding="utf-8")

    result = asyncio.run(
        template_build.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "final_snapshot_ref": compiled["task_binding"]["snapshot_ref"],
                "artifact_spec_path": str(bad_spec.relative_to(task_root)),
                "output_dir": "output/template-artifact",
            }
        )
    )["structuredContent"]

    assert result["call_status"] == "needs_input"
    assert result["failure"]["code"] == "marker_protocol_mismatch"
    assert not (task_root / "output/template-artifact").exists()

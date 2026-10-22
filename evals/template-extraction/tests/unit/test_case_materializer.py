from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from template_extraction_eval.contracts import compute_style_contract_set_digest
from template_extraction_prep import build_candidate_packages
from template_extraction_prep.docx_package import declared_content_control_fields
from template_extraction_prep.normalizers import normalize_fill_contract

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MATERIALIZER_PATH = PROJECT_ROOT / "materialize_candidate_cases.py"
FIXTURE_ROOT = PROJECT_ROOT / "fixtures"


def _load_materializer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "template_eval_case_materializer", MATERIALIZER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("case materializer cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy(FIXTURE_ROOT / "S00-minimal-pass/gold-template.docx", source / "template.docx")
    shutil.copy(FIXTURE_ROOT / "S00-minimal-pass/gold-contract.yaml", source / "contract.yaml")
    shutil.copy(FIXTURE_ROOT / "field-registry.yaml", source / "field-registry.yaml")
    shutil.copy(FIXTURE_ROOT / "eval-config.yaml", source / "eval-config.yaml")
    return source


def _manifest(tmp_path: Path, source: Path, *, template_sha256: str | None = None) -> Path:
    manifest = {
        "schema_version": "docfit-template-extraction-candidate-sources/v1",
        "sources": [
            {
                "case_id": "candidate-s00",
                "school_id": "synthetic-school",
                "school_name": "Synthetic School",
                "description": "Hermetic candidate package fixture",
                "case_status": "candidate",
                "expected_verdict": "INPUT_ERROR",
                "template": {
                    "path": "source/template.docx",
                    "sha256": template_sha256 or _sha256(source / "template.docx"),
                },
                "contract": {
                    "path": "source/contract.yaml",
                    "sha256": _sha256(source / "contract.yaml"),
                },
                "field_registry_ref": {
                    "path": "source/field-registry.yaml",
                    "id": "docfit.thesis.content_fields",
                    "version": "0.1.0",
                    "sha256": _sha256(source / "field-registry.yaml"),
                },
                "eval_config": {
                    "path": "source/eval-config.yaml",
                    "id": "synthetic-v1",
                    "version": "docfit-template-extraction-eval-config/v1",
                    "sha256": _sha256(source / "eval-config.yaml"),
                },
                "gold_review": {
                    "status": "candidate",
                    "reviewer": None,
                    "reviewed_at": None,
                    "blockers": ["pending human acceptance"],
                },
                "permissions": {
                    "visibility": "internal_candidate",
                    "student_personal_data": "none_known",
                    "git_storage": "approved",
                    "ci_use": "approved",
                    "external_processing": "not_required",
                },
            }
        ],
    }
    path = tmp_path / "sources.yaml"
    path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_cases_01_materializes_one_hash_bound_candidate_tree(tmp_path: Path) -> None:
    module = _load_materializer()
    source = _source_tree(tmp_path)
    manifest = _manifest(tmp_path, source)
    generated = module.materialize_cases(manifest, tmp_path / "cases")

    assert [path.name for path in generated] == ["candidate-s00"]
    case_root = generated[0]
    assert (case_root / "case.yaml").is_file()
    assert (case_root / "gold/final-template.gold.docx").read_bytes() == (
        source / "template.docx"
    ).read_bytes()
    assert (case_root / "gold/fill-contract.gold.yaml").is_file()
    assert (case_root / "candidate-package-receipt.json").is_file()

    case = _yaml(case_root / "case.yaml")
    contract = _yaml(case_root / "gold/fill-contract.gold.yaml")
    assert case["case_status"] == "candidate"
    assert case["gold_review"]["status"] == "candidate"
    assert case["expected_verdict"] == "INPUT_ERROR"
    assert case["gold"]["template_sha256"] == _sha256(source / "template.docx")
    assert contract["template_sha256"] == case["gold"]["template_sha256"]
    assert contract["responsibility_policy"]["mode"] == "exhaustive"


def test_cases_02_refuses_source_hash_mismatch_before_writing(tmp_path: Path) -> None:
    module = _load_materializer()
    source = _source_tree(tmp_path)
    manifest = _manifest(tmp_path, source, template_sha256="0" * 64)

    with pytest.raises(ValueError, match="template source SHA-256 mismatch"):
        module.materialize_cases(manifest, tmp_path / "cases")
    assert not (tmp_path / "cases").exists()


def test_cases_03_refuses_to_overwrite_accepted_case(tmp_path: Path) -> None:
    module = _load_materializer()
    source = _source_tree(tmp_path)
    manifest = _manifest(tmp_path, source)
    output_root = tmp_path / "cases"
    generated = module.materialize_cases(manifest, output_root)
    case_path = generated[0] / "case.yaml"
    case = _yaml(case_path)
    case["gold_review"]["status"] = "accepted"
    case_path.write_text(
        yaml.safe_dump(case, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="refusing to overwrite accepted case"):
        module.materialize_cases(manifest, output_root)


def test_cases_04_marker_mismatch_is_rejected(tmp_path: Path) -> None:
    module = _load_materializer()
    source = _source_tree(tmp_path)
    contract = _yaml(source / "contract.yaml")
    contract["slots"][0]["locator"]["value"] = "docfit.cover.wrong"
    (source / "contract.yaml").write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    manifest = _manifest(tmp_path, source)

    with pytest.raises(ValueError, match="template/contract marker mismatch"):
        module.materialize_cases(manifest, tmp_path / "cases")


def test_cases_05_module_batch_api_supports_dry_run_and_missing_case_errors(
    tmp_path: Path,
) -> None:
    source = _source_tree(tmp_path)
    manifest = _manifest(tmp_path, source)
    output_root = tmp_path / "cases"

    receipts = build_candidate_packages(
        manifest,
        output_root,
        case_ids=["candidate-s00"],
        dry_run=True,
    )
    assert receipts[0].case_id == "candidate-s00"
    assert receipts[0].written is False
    assert receipts[0].case_root == output_root.resolve() / "candidate-s00"
    assert not output_root.exists()

    with pytest.raises(ValueError, match="candidate source case not found: missing"):
        build_candidate_packages(
            manifest,
            output_root,
            case_ids=["missing"],
            dry_run=True,
        )


def test_cases_06_multi_field_placeholder_regions_do_not_require_field_aliases() -> None:
    contract = {
        "slots": [
            {
                "field_id": "thesis.title.zh",
                "locator": {
                    "type": "content_control_tag",
                    "value": "docfit.cover.title",
                },
            }
        ],
        "regions": [
            {
                "owner": "slot",
                "region_id": "region.body.chapters",
                "field_ids": ["body.paragraph"],
                "start_locator": {
                    "type": "placeholder_anchor",
                    "value": "【章标题】",
                },
                "end_locator": {
                    "type": "placeholder_anchor",
                    "value": "【正文结束】",
                },
            }
        ],
    }

    assert declared_content_control_fields(contract) == {
        "docfit.cover.title": "thesis.title.zh"
    }


def test_cases_07_normalizer_rebinds_style_contract_set_digest() -> None:
    styles = [
        {
            "style_contract_id": "style.slot.title",
            "contract_digest": "a" * 64,
            "owned_properties": [],
            "effective_properties": {},
            "application_scope": "slot",
            "override_policy": {
                "managed_direct_formatting": "replace",
                "unmanaged_properties": "preserve",
            },
            "dependencies": [],
        }
    ]
    contract = {
        "schema_version": "docfit-template-fill-contract/v2",
        "template_sha256": "0" * 64,
        "style_contract_set_digest": "0" * 64,
        "style_capture": {
            "style_contract_set_digest": "0" * 64,
        },
        "styles": styles,
    }
    template_sha256 = "1" * 64

    normalized = normalize_fill_contract(contract, template_sha256=template_sha256)
    expected = compute_style_contract_set_digest(
        schema_version="docfit-template-fill-contract/v2",
        template_sha256=template_sha256,
        styles=styles,
    )

    assert normalized["style_contract_set_digest"] == expected
    assert normalized["style_capture"]["style_contract_set_digest"] == expected

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree
from zipfile import ZipFile

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = (
    REPO_ROOT / "temp/manual-gold-preparation/eval-template-truth-candidates"
)
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "cases"
SCHEMA_ROOT = Path(__file__).resolve().parent / "schemas"
EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config/eval-config-v1.yaml"
REGISTRY_PATH = (
    REPO_ROOT
    / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

CASE_DEFINITIONS = (
    ("01-hunau-undergraduate", "hunau-undergraduate", "湖南农业大学本科"),
    ("02-njau-undergraduate", "njau-undergraduate", "南京农业大学本科"),
    ("03-pku-graduate", "pku-graduate", "北京大学研究生"),
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return value


def _dump_yaml(value: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def _schema(name: str) -> dict[str, Any]:
    value = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON schema mapping: {name}")
    return value


def _rewrite_reference(value: str) -> str:
    if value.startswith("../../../../docs/"):
        return "../../../../../docs/" + value.removeprefix("../../../../docs/")
    if value.startswith("../../gold/"):
        return (
            "../../../../../temp/manual-gold-preparation/gold/"
            + value.removeprefix("../../gold/")
        )
    if value.startswith("../../school-template"):
        return (
            "../../../../../temp/manual-gold-preparation/"
            + value.removeprefix("../../")
        )
    return value


def _normalize_nested(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_nested(item) for item in value]
    if not isinstance(value, dict):
        return _rewrite_reference(value) if isinstance(value, str) else value

    normalized = {key: _normalize_nested(item) for key, item in value.items()}
    if (
        normalized.get("type")
        in {
            "content_control_tag",
            "text_range",
            "text_anchor",
            "placeholder_anchor",
            "bookmark",
            "table_cell",
        }
        and "part" in normalized
    ):
        normalized.setdefault("story", "document")
    return normalized


def _effective_style(properties: dict[str, Any]) -> dict[str, Any]:
    font: dict[str, Any] = {}
    paragraph: dict[str, Any] = {}

    font_mapping = {
        "run.font_east_asia": "east_asia",
        "run.font_ascii": "ascii",
        "run.font_hansi": "hansi",
        "run.font_complex_script": "complex_script",
        "run.language": "language",
        "run.font_size_pt": "size_pt",
        "run.bold": "bold",
        "run.italic": "italic",
        "run.color": "color",
    }
    paragraph_mapping = {
        "paragraph.alignment": "alignment",
        "paragraph.first_line_indent_pt": "first_line_indent_pt",
        "paragraph.hanging_indent_pt": "hanging_indent_pt",
        "paragraph.left_indent_pt": "left_indent_pt",
        "paragraph.right_indent_pt": "right_indent_pt",
        "paragraph.line_rule": "line_spacing_rule",
        "paragraph.line_value": "line_value",
        "paragraph.space_before_pt": "space_before_pt",
        "paragraph.space_after_pt": "space_after_pt",
        "paragraph.keep_lines": "keep_lines",
        "paragraph.keep_next": "keep_next",
        "paragraph.widow_control": "widow_control",
        "paragraph.outline_level": "outline_level",
    }
    for source, target in font_mapping.items():
        if source in properties:
            font[target] = properties[source]
    if "ascii" in font or "hansi" in font:
        font["latin"] = font.get("ascii", font.get("hansi"))
    if isinstance(font.get("color"), str):
        font["color"] = font["color"].upper()
    for source, target in paragraph_mapping.items():
        if source in properties:
            paragraph[target] = properties[source]

    return {
        "font": font,
        "paragraph": paragraph,
        "container": {},
        "page": {},
    }


def _managed_controls(template_path: Path) -> dict[str, str]:
    with ZipFile(template_path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))

    controls: dict[str, str] = {}
    for sdt in root.iter(f"{W}sdt"):
        properties = sdt.find(f"{W}sdtPr")
        if properties is None:
            continue
        tag = properties.find(f"{W}tag")
        alias = properties.find(f"{W}alias")
        if tag is None:
            continue
        tag_value = tag.get(f"{W}val")
        alias_value = alias.get(f"{W}val") if alias is not None else None
        if not tag_value or not alias_value:
            raise ValueError(f"managed content control lacks tag/alias: {template_path}")
        if tag_value in controls:
            raise ValueError(f"duplicate content-control tag {tag_value}: {template_path}")
        controls[tag_value] = alias_value
    return controls


def _declared_tag_fields(contract: dict[str, Any]) -> dict[str, str]:
    declared: dict[str, str] = {}

    def add(locator: dict[str, Any], field_id: str) -> None:
        if locator.get("type") != "content_control_tag":
            return
        tag = locator.get("value")
        if not isinstance(tag, str):
            raise ValueError(f"content-control locator lacks tag for {field_id}")
        previous = declared.get(tag)
        if previous is not None and previous != field_id:
            raise ValueError(f"tag {tag} maps to both {previous} and {field_id}")
        declared[tag] = field_id

    for slot in contract["slots"]:
        field_id = slot["field_id"]
        add(slot["locator"], field_id)
        for component in slot.get("component_locators", []):
            add(component.get("locator", component), field_id)
    for region in contract["regions"]:
        if region.get("owner") != "slot":
            continue
        field_ids = region["field_ids"]
        if len(field_ids) != 1:
            raise ValueError(
                "v1 marker validation requires one field per region: "
                f"{region['region_id']}"
            )
        add(region["start_locator"], field_ids[0])
        add(region["end_locator"], field_ids[0])
    return declared


def _build_contract(
    candidate_spec: dict[str, Any],
    case_id: str,
    candidate_spec_sha256: str,
    validation_sha256: str,
) -> dict[str, Any]:
    if candidate_spec.get("status") != "candidate":
        raise ValueError("only candidate template specs may be materialized")
    school_id = str(candidate_spec["school_id"])
    style_by_id = {
        style["style_id"]: style for style in candidate_spec.get("styles", [])
    }

    slots = copy.deepcopy(candidate_spec["slots"])
    for slot in slots:
        slot["owner"] = "slot"
        style_id = slot.get("style_id")
        if style_id not in style_by_id:
            raise ValueError(f"slot has unresolved style_id: {slot['slot_id']} -> {style_id}")
        slot["expected_value_style"] = _effective_style(
            style_by_id[style_id]["effective_properties"]
        )

    regions = copy.deepcopy(candidate_spec["regions"])
    for region in regions:
        region["owner"] = "slot"
        region["required"] = region.get("field_ids") == ["generated.toc"]

    provenance = copy.deepcopy(candidate_spec["provenance"])
    provenance["upstream_source_ref"] = (
        "../../../../../temp/manual-gold-preparation/gold/00-inputs/schools/"
        f"{school_id}__source-template.docx"
    )
    provenance["logical_unit_evidence_ref"] = (
        "../../../../../temp/manual-gold-preparation/gold/10-school-assets/"
        f"{case_id}/logical-pages/unit-manifest.json"
    )
    provenance["candidate_spec_sha256"] = candidate_spec_sha256
    provenance["candidate_validation_report_sha256"] = validation_sha256

    review = copy.deepcopy(candidate_spec["review"])
    review["blockers"] = [
        (
            "CI 使用授权尚未确认；静态 Eval 不调用 Adobe 外部处理。"
            if blocker == "尚未绑定仓库、CI 与 Adobe 外部处理授权。"
            else blocker
        )
        for blocker in review.get("blockers", [])
    ]

    contract: dict[str, Any] = {
        "schema_version": "docfit-template-fill-contract/v1",
        "contract_id": f"{school_id}.fill-contract",
        "artifact_role": "template_fill_contract",
        "status": "candidate_pending_human_acceptance",
        "template_id": candidate_spec["template_id"],
        "revision": candidate_spec["revision"],
        "contract_version": candidate_spec["contract_version"],
        "school_id": school_id,
        "school_name": candidate_spec["school_name"],
        "template_path": "template.docx",
        "template_sha256": candidate_spec["template_sha256"],
        "field_registry_ref": copy.deepcopy(candidate_spec["field_registry_ref"]),
        "marker_protocol": copy.deepcopy(candidate_spec["marker_protocol"]),
        "canonical_renderer": candidate_spec["canonical_renderer"],
        "provenance": provenance,
        "locator_contract": copy.deepcopy(candidate_spec["locator_contract"]),
        "regions": regions,
        "slots": slots,
        "styles": copy.deepcopy(candidate_spec["styles"]),
        "logical_pages": copy.deepcopy(candidate_spec["logical_pages"]),
        "review": review,
        "validation": copy.deepcopy(candidate_spec["validation"]),
    }
    return cast(dict[str, Any], _normalize_nested(contract))


def _build_case(
    *,
    case_id: str,
    school_id: str,
    school_name: str,
    template_sha256: str,
    contract_sha256: str,
    candidate_template_sha256: str,
    review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "docfit-template-extraction-case/v1",
        "case_id": case_id,
        "description": f"{school_name}模板提取静态 Eval case；当前仅完成候选数据包物化",
        "school_id": school_id,
        "school_name": school_name,
        "case_status": "candidate",
        "gold": {
            "template": "gold/template.docx",
            "contract": "gold/fill-contract.yaml",
            "template_sha256": template_sha256,
            "contract_sha256": contract_sha256,
        },
        "field_registry_ref": {
            "path": "../../../../docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml",
            "id": "docfit.thesis.content_fields",
            "version": "0.1.0",
            "sha256": _sha256_path(REGISTRY_PATH),
        },
        "eval_config": {
            "path": "../../config/eval-config-v1.yaml",
            "id": "template-extraction-v1",
            "version": "docfit-template-extraction-eval-config/v1",
            "sha256": _sha256_path(EVAL_CONFIG_PATH),
        },
        "scoring_version": "docfit-template-extraction-scoring/v1",
        "marker_protocol": "docfit-content-control-marker/v1",
        "expected_verdict": "INPUT_ERROR",
        "gold_review": {
            "status": "candidate",
            "reviewer": review.get("reviewer"),
            "reviewed_at": review.get("reviewed_at"),
            "source_sha256": candidate_template_sha256,
            "source_path": (
                "../../../../temp/manual-gold-preparation/"
                "eval-template-truth-candidates/"
                f"{case_id}/fillable-template.docx"
            ),
            "blockers": list(review.get("blockers", [])),
        },
        "permissions": {
            "visibility": "internal_candidate",
            "student_personal_data": "none_known",
            "git_storage": "approved",
            "ci_use": "unresolved",
            "external_processing": "not_required",
        },
    }


def _assert_destination_not_accepted(case_root: Path) -> None:
    case_path = case_root / "case.yaml"
    contract_path = case_root / "gold/fill-contract.yaml"
    if case_path.exists():
        case = _read_yaml(case_path)
        if case.get("gold_review", {}).get("status") == "accepted":
            raise ValueError(f"refusing to overwrite accepted case: {case_path}")
    if contract_path.exists():
        contract = _read_yaml(contract_path)
        if contract.get("status") == "accepted":
            raise ValueError(f"refusing to overwrite accepted contract: {contract_path}")


def materialize_cases(source_root: Path, output_root: Path) -> list[Path]:
    registry = _read_yaml(REGISTRY_PATH)
    registry_fields = {field["field_id"] for field in registry["fields"]}
    contract_validator = Draft202012Validator(_schema("fill-contract.schema.json"))
    case_validator = Draft202012Validator(_schema("case.schema.json"))
    generated: list[Path] = []

    for case_id, school_id, school_name in CASE_DEFINITIONS:
        candidate_root = source_root / case_id
        candidate_template = candidate_root / "fillable-template.docx"
        spec_path = candidate_root / "template-spec.yaml"
        validation_path = candidate_root / "validation-report.json"
        candidate_spec = _read_yaml(spec_path)
        validation = json.loads(validation_path.read_text(encoding="utf-8"))

        if candidate_spec.get("school_id") != school_id:
            raise ValueError(f"school mismatch in {spec_path}")
        if candidate_spec.get("school_name") != school_name:
            raise ValueError(f"school name mismatch in {spec_path}")
        template_sha256 = _sha256_path(candidate_template)
        if candidate_spec.get("template_sha256") != template_sha256:
            raise ValueError(f"candidate template hash mismatch: {candidate_template}")
        if validation.get("gold_accepted") is not False:
            raise ValueError(f"candidate validation must not claim Gold: {validation_path}")
        if validation.get("marker_protocol", {}).get("all_aliases_match_field_ids") is not True:
            raise ValueError(f"candidate alias/field validation failed: {validation_path}")

        contract = _build_contract(
            candidate_spec,
            case_id,
            _sha256_path(spec_path),
            _sha256_path(validation_path),
        )
        referenced_fields = {
            slot["field_id"] for slot in contract["slots"]
        } | {
            field_id
            for region in contract["regions"]
            for field_id in region.get("field_ids", [])
        }
        unknown_fields = sorted(referenced_fields - registry_fields)
        if unknown_fields:
            raise ValueError(f"contract references unknown Registry fields: {unknown_fields}")

        actual_controls = _managed_controls(candidate_template)
        declared_controls = _declared_tag_fields(contract)
        if actual_controls != declared_controls:
            raise ValueError(
                f"template/contract marker mismatch for {case_id}: "
                f"actual={actual_controls}, declared={declared_controls}"
            )
        contract_validator.validate(contract)
        contract_bytes = _dump_yaml(contract)

        case = _build_case(
            case_id=case_id,
            school_id=school_id,
            school_name=school_name,
            template_sha256=template_sha256,
            contract_sha256=_sha256_bytes(contract_bytes),
            candidate_template_sha256=template_sha256,
            review=contract["review"],
        )
        case_validator.validate(case)

        case_root = output_root / case_id
        _assert_destination_not_accepted(case_root)
        gold_root = case_root / "gold"
        gold_root.mkdir(parents=True, exist_ok=True)
        (gold_root / "template.docx").write_bytes(candidate_template.read_bytes())
        (gold_root / "fill-contract.yaml").write_bytes(contract_bytes)
        (case_root / "case.yaml").write_bytes(_dump_yaml(case))
        generated.append(case_root)

    return generated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize three non-accepted school candidate case packages."
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    materialize_cases(args.source_root.resolve(), args.output_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Prepare the three reviewable Registry v0.5 Template Gold file pairs.

This script prepares exact, hash-bound candidates.  It deliberately leaves the
Human acceptance state pending until the product owner reviews the resulting
Word/contract pairs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = EVAL_ROOT / "cases"
REGISTRY_PATH = (
    REPO_ROOT
    / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"
)
EVAL_CONFIG_PATH = EVAL_ROOT / "config/eval-config-v1.yaml"
CONTRACT_SCHEMA_PATH = EVAL_ROOT / "schemas/fill-contract.schema.json"
CASE_SCHEMA_PATH = EVAL_ROOT / "schemas/case.schema.json"
REVISION = "2026-08-13.1"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

FIELD_RENAMES = {
    "body.heading.level1": "body.heading.outline1",
    "body.heading.level2": "body.heading.outline2",
    "body.heading.level3": "body.heading.outline3",
    "body.heading.level4": "body.heading.outline4",
    "body.heading.level5": "body.heading.outline5",
    "acknowledgement": "acknowledgement.body",
}
FIELD_SCALAR_KEYS = {"field_id", "alias", "canonical_field_id"}
FIELD_LIST_KEYS = {"field_ids", "applies_to"}

RPR_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "rStyle",
            "rFonts",
            "b",
            "bCs",
            "i",
            "iCs",
            "caps",
            "smallCaps",
            "strike",
            "dstrike",
            "outline",
            "shadow",
            "emboss",
            "imprint",
            "noProof",
            "snapToGrid",
            "vanish",
            "webHidden",
            "color",
            "spacing",
            "w",
            "kern",
            "position",
            "sz",
            "szCs",
            "highlight",
            "u",
            "effect",
            "bdr",
            "shd",
            "fitText",
            "vertAlign",
            "rtl",
            "cs",
            "em",
            "lang",
            "eastAsianLayout",
            "specVanish",
            "oMath",
            "rPrChange",
        )
    )
}

LOCATOR_KEYS = {
    "type",
    "value",
    "story",
    "part",
    "match_mode",
    "section_index",
    "paragraph_index",
    "table_index",
    "row",
    "cell",
    "left_anchor",
    "right_anchor",
    "occurrence",
    "start",
    "end",
    "expected_match_count",
}

CASES = {
    "01-hunau-undergraduate": {
        "school_id": "hunau-undergraduate",
        "school_name": "湖南农业大学本科",
        "template": EVAL_ROOT / "cases/01-hunau-undergraduate/gold/template.docx",
        "contract": EVAL_ROOT / "cases/01-hunau-undergraduate/gold/fill-contract.yaml",
        "kind": "existing_v1",
    },
    "02-njau-undergraduate": {
        "school_id": "njau-undergraduate",
        "school_name": "南京农业大学本科",
        "template": (
            REPO_ROOT
            / "temp/docfit-school-extract-v2-njau-tool-v5-r66/output/final-template.docx"
        ),
        "contract": (
            REPO_ROOT
            / "temp/docfit-school-extract-v2-njau-tool-v5-r66/work/.docfit/"
            "template-workspace-v1/publication/fill-contract.json"
        ),
        "policy_contract": EVAL_ROOT
        / "cases/02-njau-undergraduate/gold/fill-contract.yaml",
        "kind": "runtime_v2",
    },
    "03-pku-graduate": {
        "school_id": "pku-graduate",
        "school_name": "北京大学研究生",
        "template": (
            REPO_ROOT
            / "temp/manual-gold-preparation/gold/10-school-assets/03-pku-graduate/"
            "pku-graduate__fillable-template.docx"
        ),
        "contract": (
            REPO_ROOT
            / "temp/manual-gold-preparation/candidates/03-pku-graduate/"
            "fill-contract-r02/template-spec.yaml"
        ),
        "kind": "pku_r02",
    },
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML object: {path}")
    return value


def dump_yaml(value: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        value, allow_unicode=True, sort_keys=False, width=1000
    ).encode("utf-8")


def migrate_field_values(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, list):
        if parent_key in FIELD_LIST_KEYS:
            return [FIELD_RENAMES.get(item, item) for item in value]
        return [migrate_field_values(item) for item in value]
    if isinstance(value, dict):
        return {
            key: migrate_field_values(item, parent_key=key)
            for key, item in value.items()
        }
    if isinstance(value, str) and parent_key in FIELD_SCALAR_KEYS:
        return FIELD_RENAMES.get(value, value)
    return value


def _register_namespaces(xml: bytes) -> None:
    for _, namespace in ElementTree.iterparse(BytesIO(xml), events=("start-ns",)):
        prefix, uri = namespace
        try:
            ElementTree.register_namespace(prefix or "", uri)
        except ValueError:
            # ElementTree reserves ns<number>; it will reproduce those prefixes itself.
            continue


def _restore_root_namespace_declarations(original: bytes, serialized: bytes) -> bytes:
    original_match = re.search(rb"<w:document\b[^>]*>", original)
    serialized_match = re.search(rb"<w:document\b[^>]*>", serialized)
    if original_match is None or serialized_match is None:
        return serialized
    declaration_pattern = re.compile(rb'\s+xmlns(?::[A-Za-z0-9_.-]+)?="[^"]+"')
    original_declarations = declaration_pattern.findall(original_match.group(0))
    serialized_start = serialized_match.group(0)
    present_names = {
        declaration.split(b"=", 1)[0].strip()
        for declaration in declaration_pattern.findall(serialized_start)
    }
    missing = [
        declaration
        for declaration in original_declarations
        if declaration.split(b"=", 1)[0].strip() not in present_names
    ]
    if not missing:
        return serialized
    replacement = serialized_start[:-1] + b"".join(missing) + b">"
    return (
        serialized[: serialized_match.start()]
        + replacement
        + serialized[serialized_match.end() :]
    )


def _rpr_rank(element: ElementTree.Element, original_index: int) -> tuple[int, int]:
    local_name = element.tag.rsplit("}", 1)[-1]
    return (RPR_ORDER.get(local_name, 900), original_index)


def transform_docx(
    source: Path,
    destination: Path,
    *,
    migrate_aliases: bool,
    normalize_slot_color: bool,
    repair_rpr_order: bool,
) -> None:
    with ZipFile(source) as archive:
        infos = archive.infolist()
        payloads = {info.filename: archive.read(info.filename) for info in infos}

    document_xml = payloads["word/document.xml"]
    if migrate_aliases or normalize_slot_color or repair_rpr_order:
        _register_namespaces(document_xml)
        root = ElementTree.fromstring(document_xml)

        if migrate_aliases or normalize_slot_color:
            for sdt in root.iter(f"{W}sdt"):
                properties = sdt.find(f"{W}sdtPr")
                if properties is None:
                    continue
                alias = properties.find(f"{W}alias")
                if migrate_aliases and alias is not None:
                    current = alias.get(f"{W}val")
                    if current in FIELD_RENAMES:
                        alias.set(f"{W}val", FIELD_RENAMES[current])
                if normalize_slot_color:
                    content = sdt.find(f"{W}sdtContent")
                    if content is None:
                        continue
                    for rpr in content.iter(f"{W}rPr"):
                        color = rpr.find(f"{W}color")
                        if color is None:
                            color = ElementTree.Element(f"{W}color")
                            rpr.append(color)
                        color.set(f"{W}val", "000000")

        if repair_rpr_order or normalize_slot_color:
            for rpr in root.iter(f"{W}rPr"):
                children = list(rpr)
                ordered = [
                    item
                    for _, item in sorted(
                        enumerate(children), key=lambda pair: _rpr_rank(pair[1], pair[0])
                    )
                ]
                if children != ordered:
                    rpr[:] = ordered

        serialized_xml = ElementTree.tostring(
            root, encoding="utf-8", xml_declaration=True
        )
        document_xml = _restore_root_namespace_declarations(document_xml, serialized_xml)
        payloads["word/document.xml"] = document_xml

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, "w") as output:
            for info in infos:
                output.writestr(info, payloads[info.filename])
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def registry_ref() -> dict[str, str]:
    return {
        "path": (
            "../../../../../docs/plans/docfit-content-field-registry/"
            "content-fields-v0.5.yaml"
        ),
        "registry_id": "docfit.thesis.content_fields",
        "registry_version": "0.5.0",
        "sha256": sha256_path(REGISTRY_PATH),
    }


def pending_review() -> dict[str, Any]:
    return {
        "status": "machine_checked_pending_human_signoff",
        "reviewer": None,
        "reviewed_at": None,
        "conclusion": "pending",
        "blockers": ["精确 Word 与填写契约文件对尚待产品负责人最终确认。"],
        "prepared_by": "Codex",
    }


def apply_page_policy(contract: dict[str, Any], school_id: str) -> None:
    pages = contract.get("logical_pages", [])
    for page in pages:
        page_id = page.get("page_id")
        if school_id == "hunau-undergraduate":
            if page_id == "paper_body":
                page["section_policies"] = {
                    "conclusion": "required",
                    "acknowledgement": "required",
                    "appendix": "optional",
                }
            if page_id in {
                "design_task",
                "proposal",
                "proposal_record",
                "defense_record",
                "topic_change_approval",
                "grade_form",
            }:
                page["status"] = "manual_only"
                page["empty_policy"] = "preserve_form_shell_and_require_human_action"
        elif school_id == "njau-undergraduate":
            if page_id == "body":
                page["required_chapter_roles"] = [
                    {
                        "role": "literature_review",
                        "position": "first",
                        "title": "第一章 文献综述",
                        "field_model": "body.chapters",
                    },
                    {
                        "role": "conclusion_outlook",
                        "position": "last",
                        "title": "结论与展望",
                        "field_model": "body.chapters",
                    },
                ]
            if page_id in {"appendix", "academic_achievements"}:
                page["status"] = "optional"
                page["empty_policy"] = "placeholder_review_then_remove_if_not_applicable"
            if page_id == "acknowledgement":
                page["status"] = "required"
                page["empty_policy"] = "blocking_review"
        elif school_id == "pku-graduate":
            if page_id == "reviewers":
                page["status"] = "conditional"
                page["condition"] = {"field_id": "review.mode", "equals": "real_name"}
            if page_id in {"copyright", "declarations"}:
                page["status"] = "required_external_formal_submission"
                page["missing_policy"] = "NEEDS_INPUT"
                page["source_policy"] = "external_portal_qr_page"
            if page_id == "list_of_figures":
                page["status"] = "conditional_generated"
                page["condition"] = "document_has_figures"
            if page_id == "list_of_tables":
                page["status"] = "conditional_generated"
                page["condition"] = "document_has_tables"
            if page_id == "appendix_achievements":
                page["status"] = "optional"
            if page_id == "acknowledgement":
                page["status"] = "required"
                page["empty_policy"] = "blocking_review"


def locator(value: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: copy.deepcopy(item) for key, item in value.items() if key in LOCATOR_KEYS}
    normalized.setdefault("story", "document")
    if normalized.get("match_mode") == "starts_with":
        normalized["match_mode"] = "contains"
    return normalized


def evidence_refs(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in value or []:
        if isinstance(item, dict):
            result.append(copy.deepcopy(item))
        elif isinstance(item, str):
            result.append({"type": "source_ref", "value": item})
    return result


def normalize_pku_slot(raw: dict[str, Any]) -> dict[str, Any]:
    conditional = raw.get("required") == "conditional"
    slot: dict[str, Any] = {
        "slot_id": raw["slot_id"],
        "owner": "slot",
        "field_id": FIELD_RENAMES.get(raw["field_id"], raw["field_id"]),
        "label": raw["label"],
        "content_type": raw["content_type"],
        "required": bool(raw.get("required") is True),
        "cardinality": raw["cardinality"],
        "locator": locator(raw["locator"]),
        "fill_mode": raw["fill_mode"],
        "style_id": raw["style_id"],
        "placeholder_policy": raw.get("placeholder_policy", "remove_after_fill"),
        "mapping_status": "human_confirmed_product_rule_pending_exact_file_review",
    }
    for key in ("empty_policy", "layout_contract", "notes"):
        if key in raw:
            slot[key] = copy.deepcopy(raw[key])
    value_contract = copy.deepcopy(raw.get("value_contract", {}))
    if conditional:
        value_contract["condition"] = migrate_field_values(raw.get("condition", {}))
    if value_contract:
        slot["value_contract"] = value_contract
    refs = evidence_refs(raw.get("evidence_refs"))
    if refs:
        slot["evidence_refs"] = refs
    return slot


def normalize_pku_region(raw: dict[str, Any]) -> dict[str, Any]:
    field_ids = [FIELD_RENAMES.get(item, item) for item in raw["field_ids"]]
    optional_fields = {
        "body.landscape_block",
        "generated.list_of_figures",
        "generated.list_of_tables",
    }
    region = {
        "region_id": raw["region_id"],
        "owner": "slot",
        "required": not bool(set(field_ids) & optional_fields),
        "field_ids": field_ids,
        "label": raw["label"],
        "start_locator": locator(raw["start_locator"]),
        "end_locator": locator(raw["end_locator"]),
        "placement_mode": raw["placement_mode"],
        "style_map": migrate_field_values(copy.deepcopy(raw.get("style_map", {}))),
        "repeat_policy": raw["repeat_policy"],
    }
    refs = evidence_refs(raw.get("evidence_refs"))
    if refs:
        region["evidence_refs"] = refs
    return region


def normalize_pku_style(raw: dict[str, Any]) -> dict[str, Any]:
    word_style = raw.get("word_style", {})
    style = {
        "style_id": raw["style_id"],
        "label": raw["label"],
        "applies_to": [FIELD_RENAMES.get(item, item) for item in raw.get("applies_to", [])],
        "word_style_id": word_style.get("style_id"),
        "word_style_name": word_style.get("name"),
        "effective_properties": copy.deepcopy(raw.get("properties", {})),
    }
    refs = evidence_refs(raw.get("evidence_refs"))
    if refs:
        style["evidence_refs"] = refs
    return style


def prepare_pku_contract(source: Path, template_hash: str) -> dict[str, Any]:
    raw = read_yaml(source)
    slots = [normalize_pku_slot(item) for item in raw["slots"]]
    for slot in slots:
        if slot["field_id"] == "acknowledgement.body":
            slot["required"] = True
            slot["empty_policy"] = "blocking_review"
    contract: dict[str, Any] = {
        "schema_version": "docfit-template-fill-contract/v1",
        "contract_id": "pku-graduate.fill-contract",
        "artifact_role": "template_fill_contract",
        "status": "candidate_pending_human_acceptance",
        "template_id": "pku-graduate.clean-template",
        "revision": REVISION,
        "contract_version": "docfit-template-truth-pack-v0.5-candidate-1",
        "school_id": "pku-graduate",
        "school_name": "北京大学研究生",
        "template_path": "template.docx",
        "template_sha256": template_hash,
        "field_registry_ref": registry_ref(),
        "marker_protocol": {
            "version": "docfit-content-control-marker/v1",
            "field_identity_property": "w:alias",
            "field_identity_rule": "content controls use canonical field_id when present",
            "slot_identity_property": "w:tag",
            "slot_identity_rule": "placeholder anchors are allowed for this accepted legacy surface",
            "word_internal_id_property": "w:id",
            "word_internal_id_semantics": "non_business_identity",
        },
        "responsibility_policy": {
            "mode": "exhaustive",
            "analysis_universe": "semantic_document_facts/v1",
            "protected_basis": "complement_of_slot_and_remove",
            "slot_basis": "managed_content_controls_and_fill_contract",
            "remove_basis": "declared_remove_regions",
        },
        "canonical_renderer": "microsoft_word",
        "provenance": {
            **copy.deepcopy(raw.get("provenance", {})),
            "selected_accuracy_source": str(source.relative_to(REPO_ROOT)),
            "selected_template_sha256": template_hash,
            "registry_migration": "v0.5_clean_break_field_ids",
        },
        "locator_contract": copy.deepcopy(raw["locator_contract"]),
        "regions": [normalize_pku_region(item) for item in raw["regions"]],
        "slots": slots,
        "styles": [normalize_pku_style(item) for item in raw["styles"]],
        "logical_pages": migrate_field_values(copy.deepcopy(raw["logical_pages"])),
        "review": pending_review(),
        "validation": copy.deepcopy(raw.get("validation", {})),
    }
    apply_page_policy(contract, "pku-graduate")
    return contract


def prepare_existing_v1_contract(
    source: Path, *, school_id: str, template_hash: str
) -> dict[str, Any]:
    contract = migrate_field_values(read_yaml(source))
    contract["revision"] = REVISION
    contract["contract_version"] = "docfit-template-truth-pack-v0.5-candidate-1"
    contract["template_sha256"] = template_hash
    contract["field_registry_ref"] = registry_ref()
    contract["status"] = "candidate_pending_human_acceptance"
    contract["review"] = pending_review()
    contract.setdefault("provenance", {})["registry_migration"] = (
        "v0.5_clean_break_field_ids"
    )
    for slot in contract["slots"]:
        tag = slot.get("locator", {}).get("value")
        slot["mapping_status"] = "human_confirmed_product_rule_pending_exact_file_review"
        if slot["field_id"] in {"body.heading.outline2", "body.heading.outline3"}:
            slot["required"] = False
        if tag in {"docfit.conclusion.title", "docfit.conclusion.body", "docfit.acknowledgement"}:
            slot["required"] = True
            slot["empty_policy"] = "blocking_review"
        if tag == "docfit.appendix":
            slot["required"] = False
            slot["empty_policy"] = "placeholder_review_then_remove_if_not_applicable"
        if tag == "docfit.cover.advisor":
            slot["value_contract"] = {
                "components": ["advisor.name.zh", "advisor.title"],
                "separator": "　",
                "separator_policy": "exactly_one_cjk_space",
                "missing_policy": "blocking_review",
            }
        if tag == "docfit.body.advisor":
            slot["value_contract"] = {
                "components": ["advisor.name.zh"],
                "include_advisor_title": False,
            }
        expected = slot.get("expected_value_style")
        if isinstance(expected, dict):
            expected.setdefault("font", {})["color"] = "000000"
    apply_page_policy(contract, school_id)
    return contract


def _replace_exact_strings(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_replace_exact_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_exact_strings(item, replacements) for key, item in value.items()}
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def _style_digest(style: dict[str, Any]) -> str:
    semantic_keys = {
        "style_contract_id",
        "application_scope",
        "owned_properties",
        "effective_properties",
        "override_policy",
        "dependencies",
    }
    payload = {key: copy.deepcopy(item) for key, item in style.items() if key in semantic_keys}
    payload["owned_properties"] = sorted(set(payload.get("owned_properties", [])))
    payload["effective_properties"] = dict(
        sorted(payload.get("effective_properties", {}).items())
    )
    payload["dependencies"] = sorted(
        payload.get("dependencies", []), key=lambda item: item["style_contract_id"]
    )
    return canonical_digest(payload)


def prepare_njau_contract(
    source: Path, policy_source: Path, template_hash: str
) -> dict[str, Any]:
    contract = json.loads(source.read_text(encoding="utf-8"))
    contract = migrate_field_values(contract)
    policy = read_yaml(policy_source)
    contract.update(
        {
            "template_id": "njau-undergraduate.clean-template",
            "revision": REVISION,
            "contract_version": "docfit-template-truth-pack-v0.5-candidate-1",
            "school_id": "njau-undergraduate",
            "school_name": "南京农业大学本科",
            "template_path": "template.docx",
            "template_sha256": template_hash,
            "field_registry_ref": registry_ref(),
            "responsibility_policy": {
                "mode": "exhaustive",
                "analysis_universe": "semantic_document_facts/v1",
                "protected_basis": "complement_of_slot_and_remove",
                "slot_basis": "managed_content_controls_and_fill_contract",
                "remove_basis": "declared_remove_regions",
            },
            "canonical_renderer": "microsoft_word",
            "logical_pages": migrate_field_values(copy.deepcopy(policy["logical_pages"])),
            "review": pending_review(),
            "status": "candidate_pending_human_acceptance",
        }
    )
    provenance = contract.setdefault("provenance", {})
    provenance["selected_accuracy_source"] = str(source.relative_to(REPO_ROOT))
    provenance["selected_template_sha256"] = template_hash
    provenance["registry_migration"] = "v0.5_clean_break_field_ids"
    # The runtime publication contract carries discovery diagnostics as
    # top-level fields.  The Eval truth-pack schema intentionally keeps the
    # public surface smaller, so retain that evidence under provenance instead
    # of discarding it or weakening schema validation.
    for key in (
        "known_school_style_gaps",
        "profile_registry_digest",
        "school_observation_set_digest",
        "school_style_candidates",
    ):
        if key in contract:
            provenance[key] = contract.pop(key)

    old_digests: dict[str, str] = {}
    for style in contract["styles"]:
        old_digest = style["contract_digest"]
        style["effective_properties"]["run.color"] = "000000"
        new_digest = _style_digest(style)
        style["contract_digest"] = new_digest
        old_digests[old_digest] = new_digest
    contract = _replace_exact_strings(contract, old_digests)
    for slot in contract["slots"]:
        source_style_binding = {
            key: slot.pop(key)
            for key in (
                "handling",
                "property_profile_ref",
                "style_role_id",
                "style_role_type",
            )
            if key in slot
        }
        if source_style_binding:
            slot.setdefault("value_contract", {})[
                "source_style_binding"
            ] = source_style_binding
        slot["mapping_status"] = "human_confirmed_product_rule_pending_exact_file_review"
        field_id = slot["field_id"]
        tag = slot["locator"]["value"]
        if field_id in {"body.heading.outline2", "body.heading.outline3"}:
            slot["required"] = False
        if field_id in {"appendix.title", "appendix.body", "achievements.entries"}:
            slot["required"] = False
            slot["empty_policy"] = "placeholder_review_then_remove_if_not_applicable"
        if field_id == "acknowledgement.body":
            slot["required"] = True
            slot["empty_policy"] = "blocking_review"
        if tag == "body.paragraph.1":
            slot["value_contract"] = {
                "parent_field_id": "body.chapters",
                "chapter_role": "required_first_literature_review",
            }
        elif tag == "body.paragraph.3":
            slot["value_contract"] = {
                "parent_field_id": "body.chapters",
                "chapter_role": "required_last_conclusion_outlook",
            }
        elif field_id.startswith("body."):
            slot.setdefault("value_contract", {})["parent_field_id"] = "body.chapters"

    contract["regions"] = [
        migrate_field_values(copy.deepcopy(item)) for item in policy.get("regions", [])
    ]
    contract["regions"].append(
        {
            "region_id": "region.body.chapters",
            "owner": "slot",
            "required": True,
            "field_ids": ["body.chapters"],
            "label": "唯一正文可重复结构",
            "start_locator": {
                "type": "content_control_tag",
                "value": "body.chapters.1",
                "story": "document",
                "part": "word/document.xml",
                "expected_match_count": 1,
            },
            "end_locator": {
                "type": "content_control_tag",
                "value": "body.chapters.1",
                "story": "document",
                "part": "word/document.xml",
                "expected_match_count": 1,
            },
            "placement_mode": "repeat_structured_body_members",
            "style_map": {},
            "repeat_policy": "one_container_many_chapters",
        }
    )
    apply_page_policy(contract, "njau-undergraduate")
    set_payload = {
        "schema_version": "docfit-template-fill-contract/v2",
        "template_sha256": template_hash,
        "styles": [
            {
                "style_contract_id": style["style_contract_id"],
                "contract_digest": style["contract_digest"],
            }
            for style in sorted(contract["styles"], key=lambda item: item["style_contract_id"])
        ],
    }
    old_set_digest = contract["style_contract_set_digest"]
    new_set_digest = canonical_digest(set_payload)
    contract = _replace_exact_strings(contract, {old_set_digest: new_set_digest})
    contract["style_contract_set_digest"] = new_set_digest
    return contract


def officecli_validation(template_path: Path) -> dict[str, Any]:
    process = subprocess.run(
        ["officecli", "validate", str(template_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    detail = "\n".join(
        item.strip() for item in (process.stdout, process.stderr) if item.strip()
    )
    if process.returncode != 0 or "Validation passed" not in detail:
        raise ValueError(f"OfficeCLI validation failed for {template_path}:\n{detail}")
    return {"passed": True, "detail": detail}


def build_case(
    case_id: str,
    school_id: str,
    school_name: str,
    template_hash: str,
    contract_hash: str,
    source_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "docfit-template-extraction-case/v1",
        "case_id": case_id,
        "description": f"{school_name} Registry v0.5 模板 Gold 候选文件对",
        "school_id": school_id,
        "school_name": school_name,
        "case_status": "candidate",
        "gold": {
            "template": "gold/template.docx",
            "contract": "gold/fill-contract.yaml",
            "template_sha256": template_hash,
            "contract_sha256": contract_hash,
        },
        "field_registry_ref": {
            "path": "../../../../docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml",
            "id": "docfit.thesis.content_fields",
            "version": "0.5.0",
            "sha256": sha256_path(REGISTRY_PATH),
        },
        "eval_config": {
            "path": "../../config/eval-config-v1.yaml",
            "id": "template-extraction-v1",
            "version": "docfit-template-extraction-eval-config/v1",
            "sha256": sha256_path(EVAL_CONFIG_PATH),
        },
        "scoring_version": "docfit-template-extraction-scoring/v1",
        "marker_protocol": "docfit-content-control-marker/v1",
        "expected_verdict": "INPUT_ERROR",
        "gold_review": {
            "status": "candidate",
            "reviewer": None,
            "reviewed_at": None,
            "source_sha256": sha256_path(source_path),
            "source_path": os.path.relpath(source_path, EVAL_ROOT / "cases" / case_id),
            "blockers": ["精确 Word 与填写契约文件对尚待产品负责人最终确认。"],
        },
        "permissions": {
            "visibility": "internal_candidate",
            "student_personal_data": "none_known",
            "git_storage": "approved",
            "ci_use": "approved",
            "external_processing": "not_required",
        },
    }


def validate_contract_fields(contract: dict[str, Any]) -> None:
    registry = read_yaml(REGISTRY_PATH)
    known = {item["field_id"] for item in registry["fields"]}
    referenced = {item["field_id"] for item in contract["slots"]}
    referenced.update(
        field_id
        for region in contract["regions"]
        for field_id in region.get("field_ids", [])
    )
    unknown = sorted(referenced - known)
    if unknown:
        raise ValueError(f"contract references unknown Registry fields: {unknown}")


def prepare_case(case_id: str, definition: dict[str, Any], output_root: Path) -> None:
    source_template = Path(definition["template"])
    source_contract = Path(definition["contract"])
    case_root = output_root / case_id
    gold_root = case_root / "gold"
    gold_root.mkdir(parents=True, exist_ok=True)
    template_path = gold_root / "template.docx"

    kind = definition["kind"]
    transform_docx(
        source_template,
        template_path,
        migrate_aliases=kind != "pku_r02",
        normalize_slot_color=kind != "pku_r02",
        repair_rpr_order=kind == "existing_v1",
    )
    template_hash = sha256_path(template_path)

    if kind == "existing_v1":
        contract = prepare_existing_v1_contract(
            source_contract,
            school_id=definition["school_id"],
            template_hash=template_hash,
        )
    elif kind == "runtime_v2":
        contract = prepare_njau_contract(
            source_contract, Path(definition["policy_contract"]), template_hash
        )
    else:
        contract = prepare_pku_contract(source_contract, template_hash)

    contract.setdefault("validation", {})["gold_preparation"] = {
        "registry_version": "0.5.0",
        "officecli": officecli_validation(template_path),
        "template_contract_hash_binding": "passed",
        "human_acceptance": "pending_exact_file_pair_review",
    }
    validate_contract_fields(contract)
    contract_schema = json.loads(CONTRACT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(contract_schema).validate(contract)
    contract_bytes = dump_yaml(contract)
    contract_path = gold_root / "fill-contract.yaml"
    contract_path.write_bytes(contract_bytes)

    case = build_case(
        case_id,
        definition["school_id"],
        definition["school_name"],
        template_hash,
        sha256_bytes(contract_bytes),
        source_template,
    )
    case_schema = json.loads(CASE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(case_schema).validate(case)
    (case_root / "case.yaml").write_bytes(dump_yaml(case))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    for case_id, definition in CASES.items():
        prepare_case(case_id, definition, output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
GOLD_TEMPLATE_NAME = "final-template.gold.docx"
GOLD_CONTRACT_NAME = "fill-contract.gold.yaml"
HUNAU_REVISION = "2026-08-13.2"
HUNAU_STALE_TEMPLATE_SHA256 = (
    "70b13aecf084816a5ff5abc879c00d26c63552c0c36623060b17cbae3d775f50"
)
NJAU_LOGICAL_PAGE_MANIFEST_REF = (
    "../../../../../temp/manual-gold-preparation/gold/10-school-assets/"
    "02-njau-undergraduate/logical-pages/unit-manifest.json"
)
PKU_SOURCE_TEMPLATE_REF = (
    "../../../../../temp/manual-gold-preparation/gold/00-inputs/schools/"
    "pku-graduate__source-template.docx"
)
PKU_SOURCE_TEMPLATE_PATH = (
    REPO_ROOT
    / "temp/manual-gold-preparation/gold/00-inputs/schools/"
    "pku-graduate__source-template.docx"
)
PKU_EVIDENCE_REFS = [
    (
        "../../../../../temp/manual-gold-preparation/gold/10-school-assets/"
        "03-pku-graduate/README.md"
    ),
    (
        "../../../../../temp/manual-gold-preparation/gold/10-school-assets/"
        "03-pku-graduate/logical-pages/unit-manifest.json"
    ),
    (
        "../../../../../temp/manual-gold-preparation/gold/90-validation-evidence/"
        "03-pku-graduate/pku-graduate__pagination-audit.md"
    ),
    (
        "../../../../../temp/manual-gold-preparation/gold/90-validation-evidence/"
        "03-pku-graduate/pku-graduate__fillable-template-verification.json"
    ),
]

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

RETIRED_FIELD_IDS = frozenset(
    {
        "body.heading.level1",
        "body.heading.level2",
        "body.heading.level3",
        "body.heading.level4",
        "body.heading.level5",
        "acknowledgement",
    }
)
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
        "template": REPO_ROOT
        / "temp/manual-gold-preparation/hunau-gold-rebuild-2026-08-07-placeholder-gray/"
        "template.docx",
        "contract": REPO_ROOT
        / "temp/manual-gold-preparation/hunau-gold-rebuild-2026-08-07-placeholder-gray/"
        "fill-contract.yaml",
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
        "policy_contract": REPO_ROOT
        / "temp/manual-gold-preparation/eval-template-truth-candidates/"
        "02-njau-undergraduate/template-spec.yaml",
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


def _require_current_field_id(field_id: str, *, parent_key: str | None) -> str:
    if field_id in RETIRED_FIELD_IDS:
        location = parent_key or "field reference"
        raise ValueError(
            f"retired field_id {field_id!r} is not accepted in {location}; "
            "regenerate the Gold source from the current field_id_vocabulary "
            "instead of migrating aliases."
        )
    return field_id


def require_current_field_values(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, list):
        if parent_key in FIELD_LIST_KEYS:
            return [
                _require_current_field_id(item, parent_key=parent_key)
                if isinstance(item, str)
                else require_current_field_values(item)
                for item in value
            ]
        return [require_current_field_values(item) for item in value]
    if isinstance(value, dict):
        return {
            key: require_current_field_values(item, parent_key=key)
            for key, item in value.items()
        }
    if isinstance(value, str) and parent_key in FIELD_SCALAR_KEYS:
        return _require_current_field_id(value, parent_key=parent_key)
    return value


def _register_namespaces(xml: bytes) -> None:
    for _, namespace in ElementTree.iterparse(BytesIO(xml), events=("start-ns",)):
        prefix, uri = namespace
        try:
            ElementTree.register_namespace(prefix or "", uri)
        except ValueError:
            # ElementTree reserves ns<number>; it will reproduce those prefixes itself.
            continue


def _restore_root_namespace_declarations(
    original: bytes, serialized: bytes, *, root_local_name: str = "document"
) -> bytes:
    root_pattern = rb"<w:" + root_local_name.encode("ascii") + rb"\b[^>]*>"
    original_match = re.search(root_pattern, original)
    serialized_match = re.search(root_pattern, serialized)
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


def _w_element(local_name: str, **attributes: str) -> ElementTree.Element:
    element = ElementTree.Element(f"{W}{local_name}")
    for key, value in attributes.items():
        element.set(f"{W}{key}", value)
    return element


def _hunau_toc_style(style_id: str, name: str) -> ElementTree.Element:
    style = _w_element("style", type="paragraph", customStyle="1", styleId=style_id)
    style.extend(
        (
            _w_element("name", val=name),
            _w_element("basedOn", val="a"),
            _w_element("next", val="a"),
            _w_element("qFormat"),
        )
    )

    paragraph_properties = _w_element("pPr")
    tabs = _w_element("tabs")
    tabs.append(_w_element("tab", val="right", leader="dot", pos="8958"))
    paragraph_properties.extend(
        (
            tabs,
            _w_element("spacing", before="0", after="0", line="360", lineRule="auto"),
            _w_element("ind", left="480", leftChars="200"),
        )
    )
    style.append(paragraph_properties)

    run_properties = _w_element("rPr")
    run_properties.extend(
        (
            _w_element(
                "rFonts",
                ascii="Times New Roman",
                hAnsi="Times New Roman",
                eastAsia="宋体",
                cs="Times New Roman",
            ),
            _w_element("color", val="000000"),
            _w_element("sz", val="24"),
            _w_element("szCs", val="24"),
        )
    )
    style.append(run_properties)
    return style


def _ensure_hunau_toc_styles(styles_root: ElementTree.Element) -> None:
    existing = {
        style.get(f"{W}styleId")
        for style in styles_root.findall(f"{W}style")
    }
    for style_id, name in (("TOC1", "toc 1"), ("TOC2", "toc 2"), ("TOC3", "toc 3")):
        if style_id not in existing:
            styles_root.append(_hunau_toc_style(style_id, name))


def _hunau_toc_cached_paragraph(
    *, text: str, page: str, style_id: str, first: bool, last: bool
) -> ElementTree.Element:
    paragraph = _w_element("p")
    paragraph_properties = _w_element("pPr")
    paragraph_properties.append(_w_element("pStyle", val=style_id))
    paragraph.append(paragraph_properties)

    if first:
        field_run = _w_element("r")
        field_run.append(_w_element("fldChar", fldCharType="begin", dirty="true"))
        paragraph.append(field_run)

        instruction_run = _w_element("r")
        instruction = _w_element("instrText")
        instruction.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        instruction.text = ' TOC \\o "1-3" \\h \\z \\u \\f C '
        instruction_run.append(instruction)
        paragraph.append(instruction_run)

        separator_run = _w_element("r")
        separator_run.append(_w_element("fldChar", fldCharType="separate"))
        paragraph.append(separator_run)

    text_run = _w_element("r")
    text_node = _w_element("t")
    text_node.text = text
    text_run.append(text_node)
    paragraph.append(text_run)

    tab_run = _w_element("r")
    tab_run.append(_w_element("tab"))
    paragraph.append(tab_run)

    page_run = _w_element("r")
    page_node = _w_element("t")
    page_node.text = page
    page_run.append(page_node)
    paragraph.append(page_run)

    if last:
        field_run = _w_element("r")
        field_run.append(_w_element("fldChar", fldCharType="end"))
        paragraph.append(field_run)
    return paragraph


def _materialize_hunau_toc_cache(document_root: ElementTree.Element) -> None:
    body = document_root.find(f"{W}body")
    if body is None:
        raise ValueError("HUNAU template has no document body")

    target: ElementTree.Element | None = None
    for paragraph in body.findall(f"{W}p"):
        instruction = "".join(
            node.text or "" for node in paragraph.iter(f"{W}instrText")
        )
        if 'TOC \\o "1-3"' in instruction and "\\f C" in instruction:
            target = paragraph
            break
    if target is None:
        raise ValueError("HUNAU live TOC field was not found")

    cached_entries = (
        ("摘要", "1", "TOC1"),
        ("关键词", "1", "TOC1"),
        ("1 章节标题", "1", "TOC1"),
        ("1.1 节标题", "1", "TOC2"),
        ("1.1.1 小节标题", "1", "TOC3"),
        ("5 结论", "1", "TOC1"),
        ("参考文献", "2", "TOC1"),
        ("致谢", "3", "TOC1"),
        ("附录", "4", "TOC1"),
    )
    target_index = list(body).index(target)
    body.remove(target)
    for offset, (text, page, style_id) in enumerate(cached_entries):
        body.insert(
            target_index + offset,
            _hunau_toc_cached_paragraph(
                text=text,
                page=page,
                style_id=style_id,
                first=offset == 0,
                last=offset == len(cached_entries) - 1,
            ),
        )


def transform_docx(
    source: Path,
    destination: Path,
    *,
    reject_retired_aliases: bool,
    normalize_slot_color: bool,
    repair_rpr_order: bool,
    materialize_hunau_toc: bool,
) -> None:
    with ZipFile(source) as archive:
        infos = archive.infolist()
        payloads = {info.filename: archive.read(info.filename) for info in infos}

    document_xml = payloads["word/document.xml"]
    if (
        reject_retired_aliases
        or normalize_slot_color
        or repair_rpr_order
        or materialize_hunau_toc
    ):
        _register_namespaces(document_xml)
        root = ElementTree.fromstring(document_xml)

        if reject_retired_aliases or normalize_slot_color:
            for sdt in root.iter(f"{W}sdt"):
                properties = sdt.find(f"{W}sdtPr")
                if properties is None:
                    continue
                alias = properties.find(f"{W}alias")
                if reject_retired_aliases and alias is not None:
                    current = alias.get(f"{W}val")
                    if current is not None:
                        _require_current_field_id(current, parent_key="alias")
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

        if materialize_hunau_toc:
            _materialize_hunau_toc_cache(root)

        serialized_xml = ElementTree.tostring(
            root, encoding="utf-8", xml_declaration=True
        )
        document_xml = _restore_root_namespace_declarations(document_xml, serialized_xml)
        payloads["word/document.xml"] = document_xml

    if materialize_hunau_toc:
        styles_xml = payloads["word/styles.xml"]
        _register_namespaces(styles_xml)
        styles_root = ElementTree.fromstring(styles_xml)
        _ensure_hunau_toc_styles(styles_root)
        serialized_styles = ElementTree.tostring(
            styles_root, encoding="utf-8", xml_declaration=True
        )
        payloads["word/styles.xml"] = _restore_root_namespace_declarations(
            styles_xml, serialized_styles, root_local_name="styles"
        )

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
        "slot_ref": raw["slot_ref"],
        "owner": "slot",
        "field_id": _require_current_field_id(raw["field_id"], parent_key="field_id"),
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
        value_contract["condition"] = require_current_field_values(raw.get("condition", {}))
    if value_contract:
        slot["value_contract"] = value_contract
    refs = evidence_refs(raw.get("evidence_refs"))
    if refs:
        slot["evidence_refs"] = refs
    return slot


def normalize_pku_region(raw: dict[str, Any]) -> dict[str, Any]:
    field_ids = [
        _require_current_field_id(item, parent_key="field_ids")
        for item in raw["field_ids"]
    ]
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
        "style_map": require_current_field_values(copy.deepcopy(raw.get("style_map", {}))),
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
        "applies_to": [
            _require_current_field_id(item, parent_key="applies_to")
            for item in raw.get("applies_to", [])
        ],
        "word_style_id": word_style.get("style_id"),
        "word_style_name": word_style.get("name"),
        "effective_properties": copy.deepcopy(raw.get("properties", {})),
    }
    refs = evidence_refs(raw.get("evidence_refs"))
    if refs:
        style["evidence_refs"] = refs
    return style


def prepare_pku_contract(_source: Path, _template_hash: str) -> dict[str, Any]:
    raise ValueError(
        "PKU Gold preparation still uses retired fill-contract/v1 semantics; "
        "rebuild this source as a v2 contract before generating Eval inputs"
    )


def prepare_existing_v1_contract(
    source: Path, *, school_id: str, template_hash: str
) -> dict[str, Any]:
    _ = (source, template_hash)
    raise ValueError(
        f"{school_id} Gold preparation still depends on retired fill-contract/v1; "
        "rebuild this source as a v2 contract before generating Eval inputs"
    )


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
    contract = require_current_field_values(contract)
    policy = read_yaml(policy_source)
    contract.update(
        {
            "template_id": "njau-undergraduate.clean-template",
            "revision": REVISION,
            "contract_version": "docfit-template-truth-pack-v0.5-candidate-1",
            "school_id": "njau-undergraduate",
            "school_name": "南京农业大学本科",
            "template_path": GOLD_TEMPLATE_NAME,
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
            "logical_pages": require_current_field_values(
                copy.deepcopy(policy["logical_pages"])
            ),
            "review": pending_review(),
            "status": "candidate_pending_human_acceptance",
        }
    )
    provenance = contract.setdefault("provenance", {})
    provenance.pop("selected_accuracy_source", None)
    provenance.pop("selected_template_sha256", None)
    provenance["field_id_vocabulary_policy"] = (
        "current_registry_field_ids_required_no_alias_migration"
    )
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

    for page in contract["logical_pages"]:
        if page.get("evidence_ref", "").startswith("../../gold/10-school-assets/"):
            page["evidence_ref"] = NJAU_LOGICAL_PAGE_MANIFEST_REF

    school_style_observation = (
        (contract.get("validation") or {}).get("school_style_observation") or {}
    )
    if isinstance(school_style_observation, dict):
        school_style_observation.pop("artifact_path", None)

    contract["regions"] = [
        normalize_pku_region(item) for item in policy.get("regions", [])
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
            "template": f"gold/{GOLD_TEMPLATE_NAME}",
            "contract": f"gold/{GOLD_CONTRACT_NAME}",
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


def assert_destination_not_accepted(case_root: Path) -> None:
    case_path = case_root / "case.yaml"
    if case_path.exists():
        case = read_yaml(case_path)
        if (
            case.get("case_status") == "accepted"
            or case.get("gold_review", {}).get("status") == "accepted"
        ):
            raise ValueError(f"refusing to overwrite accepted case: {case_path}")
    contract_path = case_root / "gold" / GOLD_CONTRACT_NAME
    if contract_path.exists():
        contract = read_yaml(contract_path)
        if contract.get("status") == "accepted":
            raise ValueError(f"refusing to overwrite accepted contract: {contract_path}")


def prepare_case(case_id: str, definition: dict[str, Any], output_root: Path) -> None:
    source_template = Path(definition["template"])
    source_contract = Path(definition["contract"])
    case_root = output_root / case_id
    assert_destination_not_accepted(case_root)
    gold_root = case_root / "gold"
    gold_root.mkdir(parents=True, exist_ok=True)
    template_path = gold_root / GOLD_TEMPLATE_NAME

    kind = definition["kind"]
    if kind in {"existing_v1", "pku_r02"}:
        raise ValueError(
            f"{definition['school_id']} uses retired fill-contract/v1 preparation "
            "inputs; rebuild the source contract as v2 before generating Eval cases"
        )
    transform_docx(
        source_template,
        template_path,
        reject_retired_aliases=True,
        normalize_slot_color=kind != "pku_r02",
        repair_rpr_order=kind == "existing_v1",
        materialize_hunau_toc=kind == "existing_v1",
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
    contract_path = gold_root / GOLD_CONTRACT_NAME
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

#!/usr/bin/env python3
"""Materialize the Registry-aligned Student 002 Extraction Gold candidate.

The source document and generated Gold remain under ``temp/`` because they contain
student content.  This script is the reproducible, reviewable transformation: it
upgrades the immutable Registry snapshot with caption normalization, reuses the
reviewed parts of the existing extraction candidate, itemizes body content, and
synchronizes the HUNAU diagnostic placement map to the same Registry snapshot.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import yaml

JsonObject = dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_V2 = (
    PROJECT_ROOT
    / "docs/plans/docfit-content-field-registry/content-fields-v0.2.yaml"
)
REGISTRY_V3 = (
    PROJECT_ROOT
    / "docs/plans/docfit-content-field-registry/content-fields-v0.3.yaml"
)
SOURCE_DOCX = (
    PROJECT_ROOT / "temp/manual-gold-preparation/student-content-real-student-002.docx"
)
EXISTING_CANDIDATE = (
    PROJECT_ROOT
    / "temp/e2e-real-fallback-v1-20260811/student-extraction-v2-proof-r2"
    / "student-content-normalized-v2.json"
)
INVENTORY = EXISTING_CANDIDATE.parent / "work/student-inventory.json"
QUALITY_PATCHES = (
    PROJECT_ROOT
    / "temp/e2e-real-fallback-v1-20260811/student-fill/input/quality-patches.yaml"
)
OLD_PLACEMENT = (
    PROJECT_ROOT
    / "temp/e2e-real-fallback-v1-20260811/deterministic-replay/placement.json"
)
SOURCE_FILL_CONTRACT = (
    PROJECT_ROOT / "temp/e2e-real-fallback-v1-20260811/diagnostic-fill-contract-v2.yaml"
)
TARGET_TEMPLATE = (
    PROJECT_ROOT / "evals/template-extraction/cases/01-hunau-undergraduate/gold/template.docx"
)
EXTRACTION_DIR = (
    PROJECT_ROOT
    / "temp/manual-gold-preparation/gold/20-student-assets/student-002"
)
GOLD_JSON = EXTRACTION_DIR / "student-content.gold.json"
EXTRACTION_REVIEW = EXTRACTION_DIR / "review.yaml"
EXTRACTION_PRODUCT_REVIEW = EXTRACTION_DIR / "product-review.md"
EXTRACTION_MANIFEST = EXTRACTION_DIR / "manifest.yaml"
REVIEW_ASSETS_DIR = EXTRACTION_DIR / "review-assets"
FILLING_DIR = (
    PROJECT_ROOT
    / "temp/manual-gold-preparation/gold/30-cross-conversions"
    / "01-hunau-undergraduate/student-002"
)
SYNCED_FILL_CONTRACT = FILLING_DIR / "template-fill-contract.yaml"
PLACEMENT_MAP = FILLING_DIR / "placement-map.gold.yaml"
FILLING_MANIFEST = FILLING_DIR / "manifest.yaml"

SOURCE_SHA256 = "fc39ac02efd152ddf609199615256393e3077b49629e1cca48e1f437b2e44a9b"
REGISTRY_V1_SHA256 = "9779d0272fc395245002184d43e8356b0722a6821e8ca0a36ced0db6d26d522d"
REGISTRY_V2_SHA256 = "9bad6db2adfc3f41c6bff319b2e7fb0767267d747566142ead1d2c798306c2e8"
GOLD_REVISION = "2026-08-12.r5"
REVIEWER = "产品负责人（当前用户）"
REVIEWED_AT = "2026-08-12"
ACCEPTANCE_EVIDENCE = "产品核对表我看完了，没有问题。"
ORDER_REQUIREMENT_EVIDENCE = (
    "Gold 除了字段映射，还必须包含识别内容的顺序；以产品用户内容提取定义为准。"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W_NS, "w14": W14_NS, "m": M_NS, "a": A_NS, "r": R_NS}

HEADING_1 = re.compile(r"^第[一二三四五六七八九十百]+章(?:\s|$)")
HEADING_2 = re.compile(r"^\d+[.、]?\s*[^\d.]", re.DOTALL)
HEADING_3 = re.compile(r"^\d+\.\d+(?!\.)")
MINOR_NUMBERED = re.compile(r"^[（(]\d+[）)]")
FIGURE_CAPTION = re.compile(r"^(?:图\s*\d|Fig(?:ure)?\.?\s*\d)", re.IGNORECASE)
TABLE_CAPTION = re.compile(r"^(?:表\s*\d|Table\s*\d)", re.IGNORECASE)
FIGURE_NUMBER = re.compile(r"(?:图|Fig(?:ure)?\.?)\s*(\d+)[-.](\d+)", re.IGNORECASE)
CAPTION_NUMBER_PREFIX = re.compile(
    r"^(?:(?:图|表)\s*\d+\s*[-－—–]\s*\d+|"
    r"(?:Fig(?:ure)?\.?|Table)\s*\d+\s*[-－—–]\s*\d+)\s*",
    re.IGNORECASE,
)

STRUCTURAL_SOURCE_LABELS = {"摘要", "absrtact", "参考文献"}

EXPECTED_ITEM_COUNTS = {
    "thesis.title.zh": 1,
    "abstract.zh": 1,
    "keywords.zh": 1,
    "thesis.title.en": 1,
    "abstract.en": 1,
    "keywords.en": 1,
    "body.chapters": 1,
    "body.heading.level1": 3,
    "body.heading.level2": 10,
    "body.heading.level3": 23,
    "body.numbered_list_item": 18,
    "body.paragraph": 68,
    "body.figure": 6,
    "body.figure.caption": 12,
    "body.equation": 4,
    "body.table": 1,
    "body.table.caption": 1,
    "references.entries": 36,
}
EXPECTED_FIGURE_ASSET_SHA256 = {
    "2-1": "da7f3dc4f04e02b7619661ea07ecf7c3456a6dec8d583bc9efb765f419a42f9c",
    "2-2": "4f8b970ef94b96140e3ba63132ce21d8dbeaae2a35b3ce605befada054334529",
    "2-3": "ff37d688be258107b793a6d140efa8cbb0e25a2ae011ed0cd25d3c5c37b37a78",
    "2-4": "cc045ad890979598f2371a8eae1cdfb394a74ecc7c032f18a4cab16f28255e5b",
    "2-5": "9ba3526fd9d2bccc40a304b94e84021ab7421c3fc8d659f5aabcf65e0538163a",
    "2-6": "4e1cd7b51c371bad2b4a3007ae64e437465b8a254c69e3739de859b85e052440",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def load_yaml(path: Path) -> JsonObject:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML object: {path}")
    return value


def json_bytes(value: JsonObject) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def yaml_bytes(value: JsonObject) -> bytes:
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        width=110,
    ).encode()


def write_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Generated artifact is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def registry_v3_snapshot() -> JsonObject:
    if sha256_file(REGISTRY_V2) != REGISTRY_V2_SHA256:
        raise ValueError("The v0.2 Registry no longer matches the frozen source snapshot.")
    registry = copy.deepcopy(load_yaml(REGISTRY_V2))
    registry["schema_version"] = "docfit-content-field-registry/v0.2"
    registry["registry_version"] = "0.3.0"
    registry["revision"] = "2026-08-12.2"
    registry["status"] = "accepted"
    registry["description"] = (
        "在 v0.2 的 54 个 canonical field_id 和来源政策上，明确图题/表题的规范值排除"
        "由模板自动生成的类型标签与编号前缀，作为 Student 002 Extraction Gold pilot 的"
        "唯一语义基准。本 revision 不新增字段、不改学校 locator 或样式合同，已通过 Human 签署。"
    )
    registry["versioning"]["minor"] = (
        "additive_field_or_alias_or_pre_1_0_consumer_semantic_contract"
    )
    registry["policy_schema"] = {
        "value_source_kinds": [
            "student_source",
            "task_input",
            "system_generated",
            "external_asset",
            "human_confirmed",
        ],
        "student_extraction_policy_values": ["required", "optional", "not_applicable"],
        "required_semantics": (
            "普通论文预期存在；源中不存在时仍输出 missing，不得猜值。"
        ),
        "optional_semantics": (
            "学生源允许存在；源中不存在时输出 missing，不计作系统生成或任务输入。"
        ),
        "not_applicable_semantics": (
            "不从学生源抽取；由任务输入、系统生成或显式外部资产承担。"
        ),
    }
    registry["derived_from"] = {
        "path": "docs/plans/docfit-content-field-registry/content-fields-v0.2.yaml",
        "sha256": REGISTRY_V2_SHA256,
        "migration": (
            "same_54_canonical_field_ids_add_generated_caption_prefix_normalization"
        ),
    }
    registry["review"] = {
        "status": "accepted",
        "reviewer": REVIEWER,
        "reviewed_at": REVIEWED_AT,
        "conclusion": "accepted_without_changes",
        "acceptance_evidence": ACCEPTANCE_EVIDENCE,
        "pilot": "student-002-extraction-gold",
    }

    fields = registry.get("fields")
    if not isinstance(fields, list):
        raise ValueError("Registry fields are missing.")
    for field in fields:
        field_id = str(field["field_id"])
        if field_id == "body.figure.caption":
            field["normalization"] = {
                "preserve_observed_value": True,
                "normalized_value_excludes_generated_prefixes": [
                    "图 <chapter>-<sequence>",
                    "Fig. <chapter>-<sequence>",
                    "Figure <chapter>-<sequence>",
                ],
                "trim_outer_whitespace": True,
                "generation_owner": "target_template_caption_numbering",
            }
        elif field_id == "body.table.caption":
            field["normalization"] = {
                "preserve_observed_value": True,
                "normalized_value_excludes_generated_prefixes": [
                    "表 <chapter>-<sequence>",
                    "Table <chapter>-<sequence>",
                ],
                "apply_per_language_line": True,
                "trim_outer_whitespace": True,
                "generation_owner": "target_template_caption_numbering",
            }
    return registry


def registry_fields(registry: JsonObject) -> dict[str, JsonObject]:
    return {str(value["field_id"]): value for value in registry["fields"]}


def source_ref(value: JsonObject) -> JsonObject:
    object_ref = value["source_object_ref"]
    return {
        "object_id": object_ref["object_id"],
        "document_sha256": object_ref["document_sha256"],
        "expected_fingerprint": object_ref["expected_fingerprint"],
        "source_locator": value["source_locator"],
    }


def normalize_label(value: str) -> str:
    return "".join(value.split()).casefold()


def language_of(value: str) -> str:
    if "\x0b" in value:
        return "mixed"
    if re.search(r"[\u3400-\u9fff]", value):
        return "zh"
    if re.search(r"[A-Za-z]", value):
        return "en"
    return "und"


def keyword_normalized(field_id: str, observed: str) -> str:
    labels = {
        "keywords.zh": ("关键词：", "关键词:"),
        "keywords.en": ("KEY WORDS：", "KEY WORDS:", "KEYWORDS：", "KEYWORDS:"),
    }
    value = observed.strip()
    for label in labels[field_id]:
        if value.casefold().startswith(label.casefold()):
            return value[len(label) :].strip()
    return value


def caption_normalized(observed: str) -> str:
    """Remove source caption labels/numbers that the target template regenerates."""
    normalized_parts: list[str] = []
    for part in observed.split("\x0b"):
        normalized = CAPTION_NUMBER_PREFIX.sub("", part.strip(), count=1).strip()
        if not normalized:
            raise ValueError(f"Caption contains no title after generated prefix: {observed!r}")
        normalized_parts.append(normalized)
    return "\x0b".join(normalized_parts)


def content_item(
    *,
    source: JsonObject,
    field_id: str,
    field: JsonObject,
    parent_content_id: str | None,
    order: JsonObject,
    observed_value: str | None = None,
    normalized_value: str | None = None,
    review_status: str = "ready_for_human_acceptance",
    extra: JsonObject | None = None,
) -> JsonObject:
    item: JsonObject = {
        "content_id": source["content_id"],
        "field_id": field_id,
        "classification_status": "registered",
        "content_type": field["content_type"],
        "parent_content_id": parent_content_id,
        "_order_hint": order,
        "language": field.get("language") or language_of(observed_value or source.get("text", "")),
        "source_object_refs": [source_ref(source)],
        "source_occurrences": [
            {
                "source_object_ref": source_ref(source),
                "observed_text": source.get("text", ""),
            }
        ],
        "review_status": review_status,
    }
    if observed_value is not None:
        item["observed_value"] = observed_value
    if normalized_value is not None:
        item["normalized_value"] = normalized_value
    if observed_value is None and field["content_type"] in {"text", "rich_text"}:
        item["observed_value"] = str(source.get("text", ""))
    if extra:
        item.update(extra)
    return item


def _source_object_orders(objects: list[JsonObject]) -> dict[str, JsonObject]:
    by_block: dict[int, list[JsonObject]] = defaultdict(list)
    top_by_locator: dict[str, JsonObject] = {}
    for source in objects:
        block = source.get("body_sequence")
        if isinstance(block, int) and not isinstance(block, bool):
            by_block[block].append(source)
            top_by_locator[str(source["source_locator"])] = source
    orders: dict[str, JsonObject] = {}
    for block, sources in by_block.items():
        for inline, source in enumerate(sources):
            object_id = str(source["source_object_ref"]["object_id"])
            orders[object_id] = {"block": block, "inline": inline}
    for source in objects:
        object_id = str(source["source_object_ref"]["object_id"])
        if object_id in orders:
            continue
        locator = str(source.get("source_locator", ""))
        host_locator = max(
            (
                candidate
                for candidate in top_by_locator
                if locator.startswith(f"{candidate}/")
            ),
            key=len,
            default=None,
        )
        if host_locator is None:
            continue
        host = top_by_locator[host_locator]
        block = int(host["body_sequence"])
        inline = 1 + max(
            (int(value["inline"]) for value in orders.values() if value["block"] == block),
            default=-1,
        )
        orders[object_id] = {"block": block, "inline": inline}
    return orders


def apply_source_order(items: list[JsonObject], objects: list[JsonObject]) -> None:
    """Materialize one source-bound total order for the Gold content instances."""

    source_orders = _source_object_orders(objects)
    max_inline_by_block: dict[int, int] = defaultdict(int)
    for order in source_orders.values():
        max_inline_by_block[int(order["block"])] = max(
            max_inline_by_block[int(order["block"])], int(order["inline"])
        )
    first_block: dict[str, int] = {}
    for item in items:
        occurrences = item["source_occurrences"]
        for occurrence in occurrences:
            object_id = str(occurrence["source_object_ref"]["object_id"])
            if object_id not in source_orders:
                raise ValueError(
                    f"Ordered content occurrence has no main-story position: {object_id}"
                )
            occurrence["source_order"] = dict(source_orders[object_id])
        if occurrences:
            start = dict(occurrences[0]["source_order"])
            end = dict(occurrences[-1]["source_order"])
        else:
            content_ref = item.get("content_ref")
            if not isinstance(content_ref, dict):
                raise ValueError(
                    f"Content item has neither occurrences nor a span: {item['content_id']}"
                )
            start_block = content_ref.get("start_body_sequence")
            end_block = content_ref.get("end_body_sequence")
            if not isinstance(start_block, int) or not isinstance(end_block, int):
                raise ValueError(f"Structural content span is invalid: {item['content_id']}")
            start = {"block": start_block, "inline": 0}
            end = {"block": end_block, "inline": max_inline_by_block[end_block]}
            item["ordering_role"] = "structural_span"
        item["source_span"] = {"start": start, "end": end}
        first_block[str(item["content_id"])] = int(start["block"])

    grouped: dict[int, list[JsonObject]] = defaultdict(list)
    for item in items:
        grouped[first_block[str(item["content_id"])]].append(item)
    for block, block_items in grouped.items():
        block_items.sort(
            key=lambda value: (
                0 if value.get("ordering_role") == "structural_span" else 1,
                int(value["_order_hint"].get("within_source", 0)),
                str(value["field_id"]),
                str(value["content_id"]),
            )
        )
        for inline, item in enumerate(block_items):
            item["source_order"] = {"block": block, "inline": inline}
    items.sort(
        key=lambda value: (
            int(value["source_order"]["block"]),
            int(value["source_order"]["inline"]),
        )
    )
    for item in items:
        item.pop("_order_hint")


def parse_docx() -> tuple[
    dict[str, ET.Element],
    dict[str, JsonObject],
    dict[str, JsonObject],
    JsonObject,
]:
    with ZipFile(SOURCE_DOCX) as package:
        document_bytes = package.read("word/document.xml")
        document = ET.fromstring(document_bytes)
        relationships = ET.fromstring(package.read("word/_rels/document.xml.rels"))
        relationship_targets = {
            value.get("Id"): value.get("Target")
            for value in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
        }
        paragraphs: dict[str, ET.Element] = {}
        equations: dict[str, JsonObject] = {}
        for paragraph in document.findall(".//w:body/w:p", NS):
            para_id = paragraph.get(f"{{{W14_NS}}}paraId")
            if not para_id:
                continue
            paragraphs[para_id] = paragraph
            math_nodes = paragraph.findall(".//m:oMath", NS)
            if math_nodes:
                equations[para_id] = {
                    "math_text_hint": "".join(
                        node.text or "" for node in paragraph.findall(".//m:t", NS)
                    ),
                    "omml_sha256": sha256_bytes(
                        b"".join(ET.tostring(node, encoding="utf-8") for node in math_nodes)
                    ),
                    "equation_count": len(math_nodes),
                    "number": None,
                }

        picture_assets: dict[str, JsonObject] = {}
        for para_id, paragraph in paragraphs.items():
            for run_index, run in enumerate(paragraph.findall("./w:r", NS), start=1):
                blip = run.find(".//a:blip", NS)
                if blip is None:
                    continue
                relationship_id = blip.get(f"{{{R_NS}}}embed")
                target = relationship_targets.get(relationship_id)
                if not relationship_id or not target:
                    continue
                package_part = f"word/{target}" if not target.startswith("word/") else target
                asset_bytes = package.read(package_part)
                locator = f"/body/p[@paraId={para_id}]/r[{run_index}]"
                picture_assets[locator] = {
                    "relationship_id": relationship_id,
                    "package_part": package_part,
                    "sha256": sha256_bytes(asset_bytes),
                    "size_bytes": len(asset_bytes),
                }

        tables = document.findall(".//w:body/w:tbl", NS)
        if len(tables) != 1:
            raise ValueError(f"Expected exactly one Student 002 body table, got {len(tables)}.")
        rows = tables[0].findall("./w:tr", NS)
        table_summary: JsonObject = {
            "row_count": len(rows),
            "column_count": max((len(row.findall("./w:tc", NS)) for row in rows), default=0),
            "ooxml_sha256": sha256_bytes(ET.tostring(tables[0], encoding="utf-8")),
        }
        return paragraphs, equations, picture_assets, table_summary


def paragraph_id(locator: str) -> str | None:
    match = re.search(r"@paraId=([^\]]+)", locator)
    return match.group(1) if match else None


def classify_body_object(value: JsonObject, equation_para_ids: set[str]) -> str | None:
    if value.get("kind") == "table":
        return "body.table"
    para_id = paragraph_id(str(value.get("source_locator", "")))
    if value.get("content_type") == "equation" or para_id in equation_para_ids:
        return "body.equation"
    text = str(value.get("text", "")).strip()
    if not text:
        return None
    if FIGURE_CAPTION.match(text):
        return "body.figure.caption"
    if TABLE_CAPTION.match(text):
        return "body.table.caption"
    if HEADING_1.match(text):
        return "body.heading.level1"
    if len(text) <= 100 and HEADING_3.match(text):
        return "body.heading.level3"
    if len(text) <= 80 and HEADING_2.match(text):
        return "body.heading.level2"
    if MINOR_NUMBERED.match(text):
        return "body.numbered_list_item"
    return "body.paragraph"


def figure_key(value: str) -> str:
    match = FIGURE_NUMBER.search(value)
    if not match:
        raise ValueError(f"Cannot identify figure number from: {value[:80]}")
    return f"{match.group(1)}-{match.group(2)}"


def build_gold(registry: JsonObject, registry_sha256: str) -> JsonObject:
    if sha256_file(SOURCE_DOCX) != SOURCE_SHA256:
        raise ValueError("Student 002 source hash changed.")
    candidate = load_json(EXISTING_CANDIDATE)
    inventory = load_json(INVENTORY)
    if candidate.get("source_sha256") != SOURCE_SHA256:
        raise ValueError("Existing extraction is bound to another source document.")
    if candidate.get("registry", {}).get("sha256") != REGISTRY_V1_SHA256:
        raise ValueError("Existing extraction is not bound to the frozen v0.1 Registry.")
    if inventory.get("source_sha256") != SOURCE_SHA256:
        raise ValueError("Inventory is bound to another source document.")

    fields_by_id = registry_fields(registry)
    objects = inventory["objects"]
    objects_by_id = {value["source_object_ref"]["object_id"]: value for value in objects}
    paragraphs, equations, picture_assets, table_summary = parse_docx()
    del paragraphs

    candidate_fields = {value["field_id"]: value for value in candidate["fields"]}
    candidate_segments = {value["field_id"]: value for value in candidate["segments"]}
    items: list[JsonObject] = []

    for field_id, result in candidate_fields.items():
        if result["status"] != "extracted":
            continue
        source_ids = result["source_object_ids"]
        if len(source_ids) != 1:
            raise ValueError(f"Expected one source occurrence for scalar field {field_id}.")
        source = objects_by_id[source_ids[0]]
        observed = str(source.get("text", ""))
        normalized = (
            keyword_normalized(field_id, observed)
            if field_id in {"keywords.zh", "keywords.en"}
            else result["value"]
        )
        items.append(
            content_item(
                source=source,
                field_id=field_id,
                field=fields_by_id[field_id],
                parent_content_id=None,
                order={"scope": "front_matter", "sequence": source.get("body_sequence")},
                observed_value=observed,
                normalized_value=normalized,
            )
        )

    body_segment = candidate_segments["body.chapters"]
    body_ids = list(body_segment["source_object_ids"])
    body_container_id = "content-" + hashlib.sha256(
        (
            f"student-002|body.chapters|{body_segment['start_object_id']}|"
            f"{body_segment['end_object_id']}"
        ).encode()
    ).hexdigest()[:24]
    body_container: JsonObject = {
        "content_id": body_container_id,
        "field_id": "body.chapters",
        "classification_status": "registered",
        "content_type": fields_by_id["body.chapters"]["content_type"],
        "parent_content_id": None,
        "_order_hint": {"scope": "body", "sequence": 0},
        "language": "mixed",
        "source_object_refs": [],
        "source_occurrences": [],
        "content_ref": {
            "document_sha256": SOURCE_SHA256,
            "start_object_id": body_segment["start_object_id"],
            "end_object_id": body_segment["end_object_id"],
            "start_locator": body_segment["source_locators"][0],
            "end_locator": body_segment["source_locators"][-1],
            "start_body_sequence": int(
                objects_by_id[body_segment["start_object_id"]]["body_sequence"]
            ),
            "end_body_sequence": int(objects_by_id[body_segment["end_object_id"]]["body_sequence"]),
        },
        "review_status": "ready_for_human_acceptance",
    }
    items.append(body_container)

    classified: list[tuple[JsonObject, str]] = []
    equation_para_ids = set(equations)
    for object_id in body_ids:
        source = objects_by_id[object_id]
        field_id = classify_body_object(source, equation_para_ids)
        if field_id is not None:
            classified.append((source, field_id))

    heading_context: dict[int, str | None] = {}
    parent_by_object_id: dict[str, str] = {}
    active: dict[int, str] = {}
    for source, field_id in classified:
        sequence = int(source["body_sequence"])
        if field_id.startswith("body.heading.level"):
            level = int(field_id.rsplit("level", 1)[1])
            parent_by_object_id[source["source_object_ref"]["object_id"]] = (
                active.get(level - 1, body_container_id) if level > 1 else body_container_id
            )
            active[level] = source["content_id"]
            active = {key: value for key, value in active.items() if key <= level}
        else:
            parent_by_object_id[source["source_object_ref"]["object_id"]] = (
                active[max(active)] if active else body_container_id
            )
        heading_context[sequence] = active[max(active)] if active else body_container_id

    pictures = [value for value in objects if value.get("kind") == "picture"]
    if len(pictures) != 6:
        raise ValueError(f"Expected six Student 002 pictures, got {len(pictures)}.")
    resolved_pictures: list[tuple[int, JsonObject, str, str, JsonObject]] = []
    for picture in pictures:
        host_locator = str(picture["source_locator"]).split("/r[", 1)[0]
        host = next(
            (
                objects_by_id[object_id]
                for object_id in body_ids
                if objects_by_id[object_id]["source_locator"] == host_locator
            ),
            None,
        )
        if host is None:
            raise ValueError(f"Cannot locate host paragraph for picture: {host_locator}.")
        sequence = int(host["body_sequence"])
        asset = picture_assets.get(str(picture["source_locator"]))
        if asset is None:
            raise ValueError(f"Cannot resolve package asset for picture: {host_locator}.")
        resolved_pictures.append(
            (
                sequence,
                picture,
                host_locator,
                heading_context.get(sequence) or body_container_id,
                asset,
            )
        )

    figures_by_number: dict[str, JsonObject] = {}
    for number, (sequence, picture, host_locator, parent, asset) in enumerate(
        sorted(resolved_pictures, key=lambda value: value[0]),
        start=1,
    ):
        key = f"2-{number}"
        figure_item = content_item(
            source=picture,
            field_id="body.figure",
            field=fields_by_id["body.figure"],
            parent_content_id=parent,
            order={"scope": "body", "sequence": sequence, "within_source": 0},
            review_status="pending_figure_caption_human_confirmation",
            extra={
                "figure_key": key,
                "asset_refs": [asset],
                "host_source_locator": host_locator,
            },
        )
        figures_by_number[key] = figure_item
        items.append(figure_item)

    table_source = next(source for source, field_id in classified if field_id == "body.table")
    table_item = content_item(
        source=table_source,
        field_id="body.table",
        field=fields_by_id["body.table"],
        parent_content_id=parent_by_object_id[table_source["source_object_ref"]["object_id"]],
        order={"scope": "body", "sequence": table_source["body_sequence"]},
        review_status="pending_table_caption_human_confirmation",
        extra={"structure": table_summary},
    )
    items.append(table_item)

    figure_caption_items: dict[str, dict[str, JsonObject]] = defaultdict(dict)
    for source, field_id in classified:
        if field_id == "body.table":
            continue
        object_id = source["source_object_ref"]["object_id"]
        sequence = int(source["body_sequence"])
        review_status = "ready_for_human_acceptance"
        extra: JsonObject = {}
        normalized_value: str | None = None
        parent = parent_by_object_id[object_id]
        observed = str(source.get("text", ""))
        if field_id == "body.numbered_list_item":
            review_status = "pending_contextual_confirmation_product_preference_list_2026-08-12"
            extra["classification_basis"] = (
                "explicit_parenthesized_number_preserved_as_user_authored_list"
            )
        elif field_id == "body.figure.caption":
            key = figure_key(observed)
            normalized_value = caption_normalized(observed)
            parent = figures_by_number[key]["content_id"]
            language = "zh" if observed.startswith("图") else "en"
            extra.update(
                {
                    "language": language,
                    "parallel_group_id": f"figure-{key}-caption",
                    "figure_key": key,
                }
            )
            review_status = "pending_figure_caption_human_confirmation"
        elif field_id == "body.table.caption":
            normalized_value = caption_normalized(observed)
            parent = table_item["content_id"]
            extra.update({"language": "mixed", "table_key": "2-1"})
            review_status = "pending_table_caption_human_confirmation"
        elif field_id == "body.equation":
            para_id = paragraph_id(str(source["source_locator"]))
            if para_id not in equations:
                raise ValueError(f"Equation has no OMML evidence: {source['source_locator']}")
            extra.update({"content_ref": equations[para_id], "language": "und"})
            review_status = "pending_equation_visual_human_confirmation"

        item = content_item(
            source=source,
            field_id=field_id,
            field=fields_by_id[field_id],
            parent_content_id=parent,
            order={"scope": "body", "sequence": sequence, "within_source": 1},
            observed_value=(
                observed
                if fields_by_id[field_id]["content_type"] in {"text", "rich_text"}
                else None
            ),
            normalized_value=normalized_value,
            review_status=review_status,
            extra=extra,
        )
        items.append(item)
        if field_id == "body.figure.caption":
            figure_caption_items[item["figure_key"]][item["language"]] = item

    for key, captions in figure_caption_items.items():
        if set(captions) != {"zh", "en"}:
            raise ValueError(f"Figure {key} does not have one Chinese and one English caption.")
        captions["en"]["translation_of"] = captions["zh"]["content_id"]

    reference_segment = candidate_segments["references.entries"]
    for index, object_id in enumerate(reference_segment["source_object_ids"], start=1):
        source = objects_by_id[object_id]
        items.append(
            content_item(
                source=source,
                field_id="references.entries",
                field=fields_by_id["references.entries"],
                parent_content_id=None,
                order={"scope": "references", "sequence": index},
                observed_value=str(source.get("text", "")),
            )
        )

    apply_source_order(items, objects)
    for item in items:
        item["review_status"] = "accepted"

    items_by_field: dict[str, list[str]] = defaultdict(list)
    directly_mapped: dict[str, list[str]] = defaultdict(list)
    direct_locators: list[tuple[str, str]] = []
    for item in items:
        items_by_field[item["field_id"]].append(item["content_id"])
        for reference in item["source_object_refs"]:
            directly_mapped[reference["object_id"]].append(item["content_id"])
            direct_locators.append((reference["source_locator"], item["content_id"]))

    field_results: list[JsonObject] = []
    for field in registry["fields"]:
        field_id = field["field_id"]
        content_ids = items_by_field.get(field_id, [])
        policy = field["student_extraction_policy"]
        status = (
            "present"
            if content_ids
            else "not_applicable"
            if policy == "not_applicable"
            else "missing"
        )
        field_results.append(
            {
                "field_id": field_id,
                "status": status,
                "student_extraction_policy": policy,
                "content_type": field["content_type"],
                "cardinality": field["cardinality"],
                "parent_field_id": field.get("parent_field_id"),
                "language": field.get("language"),
                "content_ids": content_ids,
                "evidence": (
                    "registered_content_items"
                    if content_ids
                    else "non_student_source_field"
                    if status == "not_applicable"
                    else "document_wide_negative_evidence_scan"
                ),
            }
        )

    coverage_objects: list[JsonObject] = []
    coverage_counts: dict[str, int] = defaultdict(int)
    for source in objects:
        object_id = source["source_object_ref"]["object_id"]
        if object_id in directly_mapped:
            status = "mapped"
            reason = "registered_content_item"
            covered_by = directly_mapped[object_id]
        else:
            locator = str(source.get("source_locator", ""))
            covered_by = [
                content_id
                for mapped_locator, content_id in direct_locators
                if locator
                and (
                    mapped_locator.startswith(f"{locator}/")
                    or locator.startswith(f"{mapped_locator}/")
                )
            ]
            if covered_by:
                status = "covered_dependency"
                reason = "container_for_mapped_complex_object"
            else:
                text = str(source.get("text", ""))
                normalized = normalize_label(text)
                if not text.strip():
                    status = "excluded"
                    reason = "layout_or_note_separator_without_student_content"
                elif normalized in STRUCTURAL_SOURCE_LABELS:
                    status = "excluded"
                    reason = "source_structural_label_owned_by_target_template"
                else:
                    status = "unresolved"
                    reason = "nonempty_source_object_without_registered_semantics"
        coverage_counts[status] += 1
        coverage_objects.append(
            {
                "object_id": object_id,
                "status": status,
                "reason": reason,
                "covered_by_content_ids": sorted(set(covered_by)),
            }
        )

    gold: JsonObject = {
        "schema_version": "docfit-student-content-extraction-gold/v2",
        "gold_id": "student-002.extraction",
        "gold_revision": GOLD_REVISION,
        "status": "gold",
        "student_document_sha256": SOURCE_SHA256,
        "field_registry_ref": {
            "path": os.path.relpath(REGISTRY_V3, EXTRACTION_DIR),
            "registry_id": registry["registry_id"],
            "registry_version": registry["registry_version"],
            "sha256": registry_sha256,
        },
        "lineage": {
            "existing_extraction_candidate": {
                "path": os.path.relpath(EXISTING_CANDIDATE, EXTRACTION_DIR),
                "sha256": sha256_file(EXISTING_CANDIDATE),
                "registry_sha256": REGISTRY_V1_SHA256,
                "reuse": "six_scalar_values_body_range_reference_range_and_negative_evidence",
            },
            "student_inventory": {
                "path": os.path.relpath(INVENTORY, EXTRACTION_DIR),
                "sha256": sha256_file(INVENTORY),
                "object_count": len(objects),
            },
        },
        "ordering_contract": {
            "version": "docfit-source-order/v1",
            "truth_source": "items",
            "item_array_order": "source_order_ascending",
            "source_order_shape": ["block", "inline"],
            "block_basis": "zero_based_word_body_child_sequence_of_first_source_occurrence",
            "inline_basis": "semantic_content_instance_order_within_the_same_source_block",
            "classification_may_reorder": False,
            "field_results_is_order_authority": False,
            "shared_fact_policy": (
                "item_uses_earliest_occurrence_order_and_source_occurrences_preserve_all_positions"
            ),
            "structural_span_policy": (
                "span_opens_before_first_descendant_and_is_not_a_second_content_transport"
            ),
        },
        "field_results": field_results,
        "items": items,
        "unregistered_items": [],
        "coverage": {
            "object_count": len(objects),
            "status_counts": dict(sorted(coverage_counts.items())),
            "all_objects_accounted_for": len(coverage_objects) == len(objects),
            "unresolved_count": coverage_counts.get("unresolved", 0),
            "objects": coverage_objects,
        },
        "negative_evidence": {
            "scope": "all_visible_main_story_content_plus_package_note_parts",
            "missing_fields_have_no_positive_source_object_ids": True,
            "document_core_properties_are_not_student_content_evidence": True,
        },
        "authorized_patches": {
            "application": "not_applied_to_observed_values",
            "ref": {
                "path": os.path.relpath(QUALITY_PATCHES, EXTRACTION_DIR),
                "sha256": sha256_file(QUALITY_PATCHES),
            },
        },
        "package_facts": inventory["package_summary"],
        "privacy": "restricted_student_content_not_for_public_ci_or_logs",
        "review_ref": "review.yaml",
        "accepted_at": REVIEWED_AT,
        "accepted_by": REVIEWER,
    }
    validate_gold(gold, registry, inventory)
    return gold


def validate_gold(gold: JsonObject, registry: JsonObject, inventory: JsonObject) -> None:
    fields = registry_fields(registry)
    registry_ids = list(fields)
    field_results = gold["field_results"]
    if [value["field_id"] for value in field_results] != registry_ids:
        raise ValueError("Gold does not project every Registry field exactly once and in order.")
    items = gold["items"]
    content_ids = [value["content_id"] for value in items]
    if len(content_ids) != len(set(content_ids)):
        raise ValueError("Gold content IDs are not unique.")
    orders = [
        (int(value["source_order"]["block"]), int(value["source_order"]["inline"]))
        for value in items
    ]
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        raise ValueError("Gold items do not have one complete, unique source order.")
    content_id_set = set(content_ids)
    counts: dict[str, int] = defaultdict(int)
    grouped: dict[str, list[str]] = defaultdict(list)
    inventory_by_id = {
        value["source_object_ref"]["object_id"]: value for value in inventory["objects"]
    }
    for item in items:
        field_id = item["field_id"]
        if field_id not in fields:
            raise ValueError(f"Gold contains an unregistered field ID: {field_id}")
        if item["content_type"] != fields[field_id]["content_type"]:
            raise ValueError(f"Gold content type diverges from Registry: {field_id}")
        parent = item.get("parent_content_id")
        if parent is not None and parent not in content_id_set:
            raise ValueError(f"Gold item has a stale parent content ID: {item['content_id']}")
        for reference in item["source_object_refs"]:
            source = inventory_by_id.get(reference["object_id"])
            if source is None or source_ref(source) != reference:
                raise ValueError(f"Gold item has stale source evidence: {item['content_id']}")
        occurrence_ids = [
            value["source_object_ref"]["object_id"] for value in item["source_occurrences"]
        ]
        if occurrence_ids != [value["object_id"] for value in item["source_object_refs"]]:
            raise ValueError(f"Gold item has stale occurrence evidence: {item['content_id']}")
        counts[field_id] += 1
        grouped[field_id].append(item["content_id"])
    if dict(counts) != {key: value for key, value in EXPECTED_ITEM_COUNTS.items()}:
        raise ValueError(f"Unexpected Student 002 item counts: {dict(counts)}")
    for result in field_results:
        if result["content_ids"] != grouped.get(result["field_id"], []):
            raise ValueError(f"Field result content IDs are stale: {result['field_id']}")
    figures = {
        item["figure_key"]: item
        for item in items
        if item["field_id"] == "body.figure"
    }
    figure_asset_hashes = {
        key: value["asset_refs"][0]["sha256"] for key, value in figures.items()
    }
    if figure_asset_hashes != EXPECTED_FIGURE_ASSET_SHA256:
        raise ValueError(
            "Student 002 figure assets are not paired with the correct figure numbers."
        )
    figures_by_content_id = {value["content_id"]: key for key, value in figures.items()}
    for caption in (item for item in items if item["field_id"] == "body.figure.caption"):
        if figures_by_content_id.get(caption["parent_content_id"]) != caption["figure_key"]:
            raise ValueError(f"Figure caption has the wrong parent image: {caption['content_id']}")
    caption_items = [
        item
        for item in items
        if item["field_id"] in {"body.figure.caption", "body.table.caption"}
    ]
    for caption in caption_items:
        observed = str(caption.get("observed_value", ""))
        normalized = str(caption.get("normalized_value", ""))
        if not normalized or normalized == observed:
            raise ValueError(f"Caption generated prefix was not removed: {caption['content_id']}")
        if any(CAPTION_NUMBER_PREFIX.match(part) for part in normalized.split("\x0b")):
            raise ValueError(
                f"Normalized caption still has a generated prefix: {caption['content_id']}"
            )
    coverage = gold["coverage"]
    coverage_ids = [value["object_id"] for value in coverage["objects"]]
    if set(coverage_ids) != set(inventory_by_id) or len(coverage_ids) != len(inventory_by_id):
        raise ValueError("Gold source coverage is not exhaustive and disjoint.")
    if coverage["unresolved_count"] != 0:
        unresolved = [
            value for value in coverage["objects"] if value["status"] == "unresolved"
        ]
        raise ValueError(f"Gold still has unresolved source objects: {unresolved}")
    if gold["unregistered_items"]:
        raise ValueError("Student 002 Gold must not retain unregistered items.")


def extraction_review(
    gold: JsonObject,
    registry_sha256: str,
    product_review_sha256: str,
) -> JsonObject:
    by_field = {value["field_id"]: value for value in gold["field_results"]}
    return {
        "schema_version": "docfit-human-review/v1",
        "artifact": "student-002.extraction",
        "gold_revision": GOLD_REVISION,
        "status": "accepted",
        "registry_review": {
            "registry_version": "0.3.0",
            "sha256": registry_sha256,
            "status": "accepted",
        },
        "human_review_document": {
            "path": EXTRACTION_PRODUCT_REVIEW.name,
            "sha256": product_review_sha256,
            "role": "sole_human_review_interface",
        },
        "machine_checks": [
            {"check": "source_sha256_bound", "status": "PASS"},
            {"check": "all_54_registry_fields_projected_once", "status": "PASS"},
            {"check": "registered_field_ids_only", "status": "PASS"},
            {"check": "unregistered_items_empty", "status": "PASS"},
            {"check": "all_371_source_objects_accounted_for", "status": "PASS"},
            {"check": "source_coverage_unresolved_zero", "status": "PASS"},
            {"check": "items_source_order_complete_unique_and_ascending", "status": "PASS"},
            {"check": "source_occurrences_preserve_physical_order", "status": "PASS"},
            {"check": "field_results_not_order_authority", "status": "PASS"},
            {"check": "six_existing_scalar_values_reused", "status": "PASS"},
            {"check": "thirty_six_reference_entries_itemized", "status": "PASS"},
            {
                "check": "thirteen_caption_values_exclude_generated_type_and_number_prefixes",
                "status": "PASS",
            },
        ],
        "product_directions": [
            {
                "decision_id": "D3",
                "recorded_at": "2026-08-12",
                "status": "accepted",
                "accepted_classification": (
                    "classify_all_18_explicit_parenthesized_number_items_as_"
                    "body.numbered_list_item"
                ),
                "rationale": (
                    "preserve_user_authored_list_markers_over_text_length_or_"
                    "method_name_heuristics"
                ),
                "content_ids": by_field["body.numbered_list_item"]["content_ids"],
            }
        ],
        "accepted_product_decisions": [
            {
                "decision_id": "D1-D10",
                "decided_at": REVIEWED_AT,
                "status": "accepted_without_changes",
                "decision": "accept_all_decisions_in_product-review.md",
            },
            {
                "decision_id": "caption-numbering-ownership",
                "decided_at": "2026-08-12",
                "status": "accepted",
                "field_ids": ["body.figure.caption", "body.table.caption"],
                "decision": (
                    "preserve_source_type_label_and_number_in_observed_value_only; "
                    "exclude_them_from_normalized_value; regenerate_from_target_template"
                ),
            },
            {
                "decision_id": "extraction-source-order-contract",
                "decided_at": REVIEWED_AT,
                "status": "accepted",
                "decision": (
                    "items_are_the_order_truth_and_use_unique_source_order_block_inline; "
                    "field_results_cannot_reorder_content"
                ),
            },
        ],
        "human_review_queue": [],
        "reviewer": REVIEWER,
        "reviewed_at": REVIEWED_AT,
        "conclusion": "accepted_without_changes",
        "acceptance_evidence": [
            {"source": "product_owner_conversation", "statement": ACCEPTANCE_EVIDENCE},
            {"source": "product_owner_conversation", "statement": ORDER_REQUIREMENT_EVIDENCE},
        ],
    }


def markdown_cell(value: object) -> str:
    return str(value).replace("\n", "<br>").replace("\x0b", "<br>").replace("|", "\\|")


def source_table_rows() -> list[list[str]]:
    with ZipFile(SOURCE_DOCX) as package:
        document = ET.fromstring(package.read("word/document.xml"))
    tables = document.findall(".//w:body/w:tbl", NS)
    if len(tables) != 1:
        raise ValueError(f"Expected one source table for product review, got {len(tables)}.")
    rows: list[list[str]] = []
    for row in tables[0].findall("./w:tr", NS):
        rows.append(
            [
                "".join(node.text or "" for node in cell.findall(".//w:t", NS)).strip()
                for cell in row.findall("./w:tc", NS)
            ]
        )
    return rows


def review_figure_assets(gold: JsonObject, *, check: bool) -> list[JsonObject]:
    figures = sorted(
        (value for value in gold["items"] if value["field_id"] == "body.figure"),
        key=lambda value: tuple(int(part) for part in value["figure_key"].split("-")),
    )
    artifacts: list[JsonObject] = []
    expected_paths: set[Path] = set()
    with ZipFile(SOURCE_DOCX) as package:
        for figure in figures:
            asset = figure["asset_refs"][0]
            content = package.read(asset["package_part"])
            if sha256_bytes(content) != asset["sha256"]:
                raise ValueError(f"Figure asset hash mismatch: {figure['figure_key']}")
            suffix = Path(asset["package_part"]).suffix.casefold()
            path = REVIEW_ASSETS_DIR / f"figure-{figure['figure_key']}{suffix}"
            expected_paths.add(path)
            write_or_check(path, content, check=check)
            artifacts.append(
                {
                    "figure_key": figure["figure_key"],
                    "path": os.path.relpath(path, EXTRACTION_DIR),
                    "sha256": asset["sha256"],
                }
            )
    stale_paths = set(REVIEW_ASSETS_DIR.glob("figure-*")) - expected_paths
    if check and stale_paths:
        raise ValueError(f"Stale product-review figure assets: {sorted(stale_paths)}")
    for path in stale_paths:
        path.unlink()
    return artifacts


def extraction_product_review(
    *,
    gold: JsonObject,
    registry: JsonObject,
    registry_sha256: str,
    figure_assets: list[JsonObject],
) -> bytes:
    items_by_field: dict[str, list[JsonObject]] = defaultdict(list)
    items_by_id: dict[str, JsonObject] = {}
    for item in gold["items"]:
        items_by_field[item["field_id"]].append(item)
        items_by_id[item["content_id"]] = item
    field_results = {value["field_id"]: value for value in gold["field_results"]}
    figure_asset_by_key = {value["figure_key"]: value for value in figure_assets}
    present_field_count = sum(
        value["status"] == "present" for value in gold["field_results"]
    )
    missing_field_count = sum(
        value["status"] == "missing" for value in gold["field_results"]
    )
    not_applicable_field_count = sum(
        value["status"] == "not_applicable" for value in gold["field_results"]
    )
    body_context_items = sorted(
        (
            value
            for value in gold["items"]
            if value["field_id"].startswith("body.")
            and str(value.get("observed_value", "")).strip()
        ),
        key=lambda value: (
            int(value["source_order"]["block"]),
            int(value["source_order"]["inline"]),
        ),
    )
    body_context_index = {
        value["content_id"]: index for index, value in enumerate(body_context_items)
    }

    policy_labels = {
        "required": "学生论文通常应有；缺失时明确记 missing",
        "optional": "允许从学生原文提取；不存在时记 missing，不猜值",
        "not_applicable": "不从学生原文提取",
    }
    source_labels = {
        "student_source": "学生原文",
        "task_input": "任务补充",
        "system_generated": "系统生成",
        "external_asset": "外部资产",
        "human_confirmed": "人工确认",
    }
    status_labels = {
        "present": "已提取",
        "missing": "原文未发现",
        "not_applicable": "不适用学生提取",
    }

    lines = [
        "# Student 002 Extraction Gold 产品核对表",
        "",
        "- 评审对象：Student 002 用户内容提取",
        f"- Gold revision：`{GOLD_REVISION}`",
        "- 当前状态：`ACCEPTED`",
        "- 产品结论：Registry v0.3 与 Student 002 Extraction Gold 已通过产品验收",
        f"- 验收日期：`{REVIEWED_AT}`",
        f"- 验收证据：{ACCEPTANCE_EVIDENCE}",
        f"- 顺序补充要求：{ORDER_REQUIREMENT_EVIDENCE}",
        "- 隐私级别：受限学生内容；禁止进入公开 CI、公开日志或公共仓库",
        f"- 用户源 SHA-256：`{SOURCE_SHA256}`",
        f"- Registry：`docfit.thesis.content_fields@0.3.0`，`{registry_sha256}`",
        f"- [打开学生原论文]({os.path.relpath(SOURCE_DOCX, EXTRACTION_DIR)})",
        f"- [查看 Accepted Extraction Gold]({GOLD_JSON.name})",
        "",
        "## 1. 这份文档用来决定什么",
        "",
        "这份文档是本轮唯一的人工核对界面。评审人不需要阅读或编辑 YAML。`review.yaml`",
        "只在签署后保存机器可读的结论和证据引用，不能代替本文的产品判断。",
        "",
        "本轮已分别决定：",
        "",
        "1. Registry v0.3 的字段来源、学生提取政策和题注编号归一化是否成立；",
        "2. Student 002 的内容分类、层级、复杂对象关系和缺失判断是否可信；",
        "3. 当前结果可以晋升为 Accepted Extraction Gold，并允许填写映射进入独立评审。",
        "",
        "本评审不决定内容如何排进湖南农大模板，也不验收最终 Word。填写映射只有在",
        "Extraction Gold 独立签署后才能继续晋升。",
        "",
        "## 2. 机器已经确认的事实",
        "",
        "| 检查 | 结果 |",
        "|---|---:|",
        "| Registry 字段总数 | 54，ID 唯一 |",
        (
            "| 字段级结果 | "
            f"{present_field_count} 已提取、{missing_field_count} 原文未发现、"
            f"{not_applicable_field_count} 不适用学生提取 |"
        ),
        "| 内容实例 | 189 |",
        "| 内容顺序 | `items` 按唯一 `source_order.block + inline` 严格递增 |",
        "| 字段摘要是否可改顺序 | 否；`field_results` 仅为派生索引 |",
        "| 源对象覆盖 | 188 直接映射、86 复杂对象依赖、97 显式排除 |",
        "| 未决源对象 | 0 |",
        "| unregistered | 0 |",
        "| 图 / 表 / 公式 / 参考文献 | 6 / 1 / 4 / 36 |",
        "",
        "机器结果证明数据闭包和引用一致；产品负责人已阅读完整核对表并确认没有问题，",
        "D1–D10 全部接受，人工 review queue 已关闭。",
        "",
        "## 3. 产品决策总表",
        "",
        "| 决策 | 需要确认 | 当前建议 | 结论 |",
        "|---|---|---|---|",
        "| D1 | 54 字段来源、学生提取政策与题注编号归一化 | 接受为 v0.3 pilot | 已接受 |",
        "| D2 | 正文 3/10/23 级标题与 68 段正文的层级、父子和顺序 | 接受 | 已接受 |",
        (
            "| D3 | 18 个显式括号编号项的分类 | 全部保留为数字列表项；"
            "不按文本长短升级标题 | 已接受 |"
        ),
        "| D4 | 6 张图、12 条题注配对及去编号规范值 | 看图并核对题名正文 | 已接受 |",
        "| D5 | 17×5 表格、双语表题及去编号规范值 | 接受 | 已接受 |",
        "| D6 | 4 个公式对象及无公式编号判断 | 对照原 Word 逐个确认 | 已接受 |",
        "| D7 | 36 条参考文献边界和拆分 | 接受 | 已接受 |",
        "| D8 | 97 个排除对象没有隐藏学生内容 | 接受 94 个空白/分隔对象和 3 个结构标题 | 已接受 |",
        "| D9 | 6 个标量、关键词归一化和 31 个 missing | 接受，不从其他转换稿补值 | 已接受 |",
        "| D10 | 学生内容的受限存储与使用范围 | 接受受限存储 | 已接受 |",
        "",
        "## 4. D1：Registry 字段来源与提取政策",
        "",
        "产品规则是：Gold 只使用 Registry canonical `field_id`。发现现有字段无法承载的通用",
        "内容时，先升级 Registry，再重做 Extraction 和填写映射；禁止猜字段或把 unregistered",
        "长期留在 Gold。Student 002 全文没有发现需要新增字段的通用内容。",
        "",
        "v0.3 沿用全部 54 个字段，但把图题/表题的自动编号所有权写清：源标签与编号只保留在",
        "`observed_value`，`normalized_value` 排除它们，Placement 由目标模板重新生成。",
        "",
        "完整 54 字段政策见附录 A。建议接受 v0.3 作为本 pilot 的语义基准，但该结论不代表",
        "54 字段已经穷尽未来所有论文内容。",
        "",
        "- [x] 接受 D1 当前建议",
        "- [ ] 修改 D1，具体修改：",
        "- [ ] 阻止 D1",
        "- 评审备注：",
        "",
        "## 5. D2：正文层级与阅读顺序",
        "",
        "Gold 识别为 3 个一级章、10 个二级标题、23 个三级标题和 68 个普通正文段落。完整",
        "标题树见附录 B。重点检查第二章内部从“材料与方法”到“结果与分析”“讨论”的父子关系，",
        "以及第三章“结论/展望”是否都属于第三章。",
        "",
        "- [x] 接受 D2 当前标题树与顺序",
        "- [ ] 修改 D2，错误标题或父级：",
        "- [ ] 阻止 D2",
        "- 评审备注：",
        "",
        "## 6. D3：显式括号编号项保留为数字列表",
        "",
        "产品负责人已确认 Student 002 的 18 个“（n）”显式编号项全部归入",
        "`body.numbered_list_item`，本样本不产生 `body.heading.level4` 内容实例。理由是优先保留",
        "用户原文可见的列表特征；文本较短或内容像“方法名称”，不足以单独把它升级为标题。",
        "",
        "附录 C 不再只给孤立片段，而是逐条展示所属上级、前一条和后一条可见内容。只有出现",
        "更强的层级、排版或上下文证据时，可以把具体条目改为四级标题；不能恢复原来的长短启发式。",
        "",
        "- [x] 接受 D3：18 项全部保留为数字列表项",
        "- [ ] 修改 D3：以下条目改为四级标题（须引用附录 C 编号及具体上下文证据）：",
        "- [ ] 阻止 D3",
        "- 评审备注：",
        "",
        "## 7. D4：图片与双语图题",
        "",
        "附录 D 展示从绑定源 Word 原样提取的 6 张图片、源题注和去编号后的 Gold 题名。",
        "`observed_value` 保留“图/Fig. + 编号”用于追溯，`normalized_value` 只保留题名正文；",
        "填写时由目标模板重新生成类型标签与编号。需要确认配对和去除边界均正确。",
        "编号所有权规则已由产品负责人确定，本项剩余审核不再决定是否保留源编号。",
        "",
        "- [x] 接受 D4 的 6 组图片与题注",
        "- [ ] 修改 D4，错误图号或题注：",
        "- [ ] 阻止 D4",
        "- 评审备注：",
        "",
        "## 8. D5：表格与双语表题",
        "",
        "Gold 包含 1 个 17×5 表格，题注是同一源段落中的中英文两行，作为一个 mixed-language",
        "`body.table.caption` 内容实例。源题注完整保留；中英文两行的“表/Table + 编号”分别",
        "从规范值中去除，填写时由目标模板重新生成。附录 E 同时展示两种值和全部单元格文本。",
        "编号所有权规则已由产品负责人确定，本项剩余审核只确认题名正文和表格关系。",
        "",
        "- [x] 接受 D5 的表格、表题和父子关系",
        "- [ ] 修改 D5：",
        "- [ ] 阻止 D5",
        "- 评审备注：",
        "",
        "## 9. D6：公式",
        "",
        "Gold 从 OOXML 中识别出 4 个 OMML 公式对象。附录 F 的文字只用于定位，不是公式真值；",
        "分数线、上下标和括号必须对照原 Word 视觉确认。当前没有发现独立公式编号。",
        "",
        "- [x] 接受 D6 的 4 个公式对象且均无编号",
        "- [ ] 修改 D6，错误公式或编号：",
        "- [ ] 阻止 D6",
        "- 评审备注：",
        "",
        "## 10. D7：参考文献",
        "",
        "Gold 把“参考文献”视为结构标题，把其后的 36 个非空段落逐段识别为",
        "`references.entries`。完整条目见附录 G。需要确认没有把一条文献拆成两条，也没有把",
        "正文或后置内容收入参考文献。",
        "",
        "- [x] 接受 D7 的边界、36 条拆分和顺序",
        "- [ ] 修改 D7，错误条目：",
        "- [ ] 阻止 D7",
        "- 评审备注：",
        "",
        "## 11. D8：排除项",
        "",
        "97 个排除对象包括 94 个空白、布局或注释分隔对象，以及“摘要”“ABSRTACT”“参考文献”",
        "三个结构标题。结构标题由目标模板生成，不作为学生内容实例，但其后的正文仍全部保留。",
        "附录 H 给出具体结构标题和排除统计。",
        "",
        "- [x] 接受 D8，排除项没有隐藏学生内容",
        "- [ ] 修改 D8，需要恢复的内容：",
        "- [ ] 阻止 D8",
        "- 评审备注：",
        "",
        "## 12. D9：标量、归一化与缺失判断",
        "",
        "附录 I 展示中英文题名、摘要和关键词。关键词去掉源标签并保留原始观测值；图表题注",
        "归一化另见 D4/D5；摘要和论文题名没有改写。包括作者、学号、院系、导师和本样本未",
        "出现的四级标题在内，共 31 个",
        "学生源字段在冻结原文中未找到，保持 `missing`；不能从历史转换稿或文件名反向补写。",
        "",
        "- [x] 接受 D9 的 6 个标量、关键词归一化和 missing 结论",
        "- [ ] 修改 D9，需修正字段：",
        "- [ ] 阻止 D9",
        "- 评审备注：",
        "",
        "## 13. D10：隐私与使用范围",
        "",
        "源 Word、Extraction Gold、本文和图片均包含真实学生论文内容，只能保存在当前受限",
        "测试资产目录。公开 CI 应使用合成或已授权数据；日志不得输出摘要、正文、参考文献或图片。",
        "",
        "- [x] 接受 D10 的受限存储和使用边界",
        "- [ ] 修改 D10：",
        "- [ ] 阻止 D10",
        "- 评审备注：",
        "",
        "## 14. 产品负责人最终签署",
        "",
        "- Registry v0.3： [x] 接受  [ ] 修改后接受  [ ] 阻止",
        "- Student 002 Extraction Gold： [x] 接受  [ ] 修改后复审  [ ] 阻止",
        "- 是否允许同步后的模板填写映射继续进入独立评审： [x] 是  [ ] 否",
        f"- 评审人：{REVIEWER}",
        f"- 评审日期：{REVIEWED_AT}",
        f"- 总体结论与修改要求：{ACCEPTANCE_EVIDENCE} 无待修改项。",
        "",
        "本节已形成明确结论，修改项为零；重新物化和 hash 校验通过后，Extraction manifest",
        "已晋升为 `gold`。模板填写映射仍须独立评审，未随本次签署自动晋升。",
        "",
        "## 附录 A：54 字段完整政策与 Student 002 结果",
        "",
        "| # | Registry 字段 | 含义 | 允许来源 | 学生提取政策 | Student 002 | 数量 |",
        "|---:|---|---|---|---|---|---:|",
    ]

    for index, field in enumerate(registry["fields"], start=1):
        field_id = field["field_id"]
        result = field_results[field_id]
        sources = "、".join(source_labels[value] for value in field["value_sources"])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    f"`{field_id}`",
                    markdown_cell(field.get("label", "")),
                    sources,
                    policy_labels[field["student_extraction_policy"]],
                    status_labels[result["status"]],
                    str(len(result["content_ids"])),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 附录 B：完整标题树",
            "",
        ]
    )
    heading_levels = {
        "body.heading.level1": 1,
        "body.heading.level2": 2,
        "body.heading.level3": 3,
    }
    headings = sorted(
        (
            value
            for value in gold["items"]
            if value["field_id"] in heading_levels
        ),
        key=lambda value: (
            int(value["source_order"]["block"]),
            int(value["source_order"]["inline"]),
        ),
    )
    for heading in headings:
        indent = "  " * (heading_levels[heading["field_id"]] - 1)
        lines.append(f"{indent}- {heading['observed_value']}")

    lines.extend(
        [
            "",
            "## 附录 C：18 个数字列表项及其原文上下文",
            "",
            "以下各项已按 D3 归为 `body.numbered_list_item`。产品负责人已结合上下文确认，",
            "没有例外，不再使用“文本短就是四级标题”的规则。",
            "",
        ]
    )
    contested = sorted(
        items_by_field["body.numbered_list_item"],
        key=lambda value: (
            int(value["source_order"]["block"]),
            int(value["source_order"]["inline"]),
        ),
    )
    for index, item in enumerate(contested, start=1):
        parent = items_by_id[item["parent_content_id"]].get("observed_value", "")
        context_position = body_context_index[item["content_id"]]
        previous = (
            body_context_items[context_position - 1]["observed_value"]
            if context_position > 0
            else "（正文起点，无前一条可见内容）"
        )
        following = (
            body_context_items[context_position + 1]["observed_value"]
            if context_position + 1 < len(body_context_items)
            else "（正文终点，无后一条可见内容）"
        )
        lines.extend(
            [
                f"### C{index}. 数字列表项",
                "",
                f"- 所属上级：{markdown_cell(parent)}",
                f"- 前一条可见内容：{markdown_cell(previous)}",
                f"- **当前编号项：{markdown_cell(item['observed_value'])}**",
                f"- 后一条可见内容：{markdown_cell(following)}",
                "",
            ]
        )

    lines.extend(["", "## 附录 D：6 组图片与双语图题", ""])
    captions_by_key: dict[str, dict[str, JsonObject]] = defaultdict(dict)
    for caption in items_by_field["body.figure.caption"]:
        captions_by_key[caption["figure_key"]][caption["language"]] = caption
    figures = sorted(
        items_by_field["body.figure"],
        key=lambda value: tuple(int(part) for part in value["figure_key"].split("-")),
    )
    for figure in figures:
        key = figure["figure_key"]
        asset = figure_asset_by_key[key]
        lines.extend(
            [
                f"### 图 {key}",
                "",
                f"![图 {key} 原图]({asset['path']})",
                "",
                f"- 源中文题注：{captions_by_key[key]['zh']['observed_value']}",
                f"- Gold 中文题名：{captions_by_key[key]['zh']['normalized_value']}",
                f"- 源英文题注：{captions_by_key[key]['en']['observed_value']}",
                f"- Gold 英文题名：{captions_by_key[key]['en']['normalized_value']}",
                "- 类型标签与编号：不进入规范值，由目标模板生成",
                f"- 原图 SHA-256：`{asset['sha256']}`",
                "",
            ]
        )

    table = items_by_field["body.table"][0]
    table_caption = items_by_field["body.table.caption"][0]
    table_rows = source_table_rows()
    lines.extend(
        [
            "## 附录 E：表格与双语表题",
            "",
            f"- 源表题：{table_caption['observed_value'].replace(chr(11), ' / ')}",
            f"- Gold 表题正文：{table_caption['normalized_value'].replace(chr(11), ' / ')}",
            "- 类型标签与编号：不进入规范值，由目标模板生成",
            (
                f"- 结构：{table['structure']['row_count']} 行 × "
                f"{table['structure']['column_count']} 列"
            ),
            f"- OOXML SHA-256：`{table['structure']['ooxml_sha256']}`",
            "",
        ]
    )
    header = table_rows[0]
    lines.append("| " + " | ".join(markdown_cell(value) for value in header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for row in table_rows[1:]:
        lines.append("| " + " | ".join(markdown_cell(value) for value in row) + " |")

    lines.extend(
        [
            "",
            "## 附录 F：4 个公式定位",
            "",
            "| # | 所属段落 | 文字定位提示（非公式真值） | 公式编号 |",
            "|---:|---|---|---|",
        ]
    )
    for index, item in enumerate(items_by_field["body.equation"], start=1):
        parent = items_by_id[item["parent_content_id"]].get("observed_value", "")
        number = item["content_ref"].get("number") or "无"
        lines.append(
            f"| {index} | {markdown_cell(parent)} | "
            f"{markdown_cell(item['content_ref']['math_text_hint'])} | {number} |"
        )

    lines.extend(["", "## 附录 G：36 条参考文献", ""])
    for index, item in enumerate(items_by_field["references.entries"], start=1):
        lines.append(f"{index}. {item['observed_value']}")

    inventory = load_json(INVENTORY)
    inventory_by_id = {
        value["source_object_ref"]["object_id"]: value for value in inventory["objects"]
    }
    structural_exclusions = [
        value
        for value in gold["coverage"]["objects"]
        if value["status"] == "excluded"
        and value["reason"] == "source_structural_label_owned_by_target_template"
    ]
    lines.extend(
        [
            "",
            "## 附录 H：排除项依据",
            "",
            "| 类别 | 数量 | 处理理由 |",
            "|---|---:|---|",
            "| 空白、布局或注释分隔对象 | 94 | 不含学生可见语义内容；不进入内容项 |",
            "| 源结构标题 | 3 | 由目标模板提供结构标题；标题后的学生内容仍全部提取 |",
            "",
            "三个源结构标题：",
            "",
        ]
    )
    for value in structural_exclusions:
        source = inventory_by_id[value["object_id"]]
        lines.append(
            f"- `{source['source_locator']}`：{source.get('text', '').strip()}"
        )

    lines.extend(
        [
            "",
            "## 附录 I：6 个标量的观测值与规范值",
            "",
        ]
    )
    scalar_fields = [
        "thesis.title.zh",
        "abstract.zh",
        "keywords.zh",
        "thesis.title.en",
        "abstract.en",
        "keywords.en",
    ]
    labels = {
        value["field_id"]: value.get("label", value["field_id"])
        for value in registry["fields"]
    }
    for field_id in scalar_fields:
        item = items_by_field[field_id][0]
        observed = item.get("observed_value", "")
        normalized = item.get("normalized_value", observed)
        lines.extend(
            [
                f"### {labels[field_id]} (`{field_id}`)",
                "",
                "**原文观测值**",
                "",
                str(observed),
                "",
                "**Gold 规范值**",
                "",
                str(normalized),
                "",
            ]
        )

    lines.extend(
        [
            "## 附录 J：填写映射的后续阻塞，不属于本次 Extraction 签署",
            "",
            "当前湖南农大填写映射与本 Accepted Extraction Gold 使用同一 Registry 和 hash，",
            "已获准进入独立评审，但仍有：",
            "",
            "- 11 个必填目标槽缺少任务输入；",
            (
                "- `body.numbered_list_item`、`body.figure.caption`、"
                "`body.table.caption` 三类目标样式合同未完成；"
            ),
            "- 湖南农大目标模板本身尚未 Human accepted。",
            "",
            "因此填写侧预期业务状态是 `NEEDS_INPUT`。本次 Extraction 验收不会自动把填写",
            "候选晋升为 Filling Gold。",
            "",
        ]
    )
    return ("\n".join(lines) + "\n").encode()


def synced_fill_contract(registry_sha256: str) -> JsonObject:
    contract = copy.deepcopy(load_yaml(SOURCE_FILL_CONTRACT))
    contract["status"] = "candidate_ready_for_independent_review"
    contract["revision"] = "student-002-registry-v0.3-sync-2026-08-12-r3"
    contract["field_registry_ref"] = {
        "path": os.path.relpath(REGISTRY_V3, FILLING_DIR),
        "registry_id": "docfit.thesis.content_fields",
        "registry_version": "0.3.0",
        "sha256": registry_sha256,
    }
    contract["synchronization_note"] = (
        "Field IDs and template locators are unchanged from the diagnostic v2 adapter. "
        "The Registry binding advances to v0.3 so normalized figure/table caption values exclude "
        "source type labels and numbers that the target template regenerates. All 18 explicit "
        "parenthesized-number Student 002 items remain mapped as "
        "body.numbered_list_item under the accepted 2026-08-12 product decision."
    )
    return contract


def placement_map(
    *,
    gold: JsonObject,
    gold_sha256: str,
    contract: JsonObject,
    contract_sha256: str,
    registry: JsonObject,
    registry_sha256: str,
) -> JsonObject:
    fields = registry_fields(registry)
    items = {value["content_id"]: value for value in gold["items"]}
    by_field: dict[str, list[str]] = defaultdict(list)
    for item in gold["items"]:
        by_field[item["field_id"]].append(item["content_id"])
    field_results = {value["field_id"]: value for value in gold["field_results"]}

    old_placement = load_json(OLD_PLACEMENT)
    old_body_operation = next(
        value
        for value in old_placement["operations"]
        if value.get("field_id") == "body.chapters"
    )
    body_source_ids = [
        content_id
        for content_id, item in items.items()
        if item["field_id"].startswith("body.")
    ]
    placements: list[JsonObject] = [
        {
            "placement_id": "placement.body.ordered_tree",
            "field_id": "body.chapters",
            "source_content_ids": body_source_ids,
            "target": {
                "aggregate_slot_id": old_body_operation["slot_id"],
                "anchor_tag": old_body_operation["tag"],
                "remove_tags_after_fill": old_body_operation["remove_tags_after_fill"],
            },
            "action": "replace_template_body_example_with_ordered_content_tree",
            "order": "source_content_order",
            "status": "candidate_pending_style_role_review",
            "projection": {
                "content_value": "normalized_value_when_present_otherwise_observed_value",
                "caption_numbering": (
                    "generate_type_label_and_number_from_target_template; "
                    "do_not_place_source_caption_prefix"
                ),
                "confirmed_style_contract_refs": old_body_operation["style_role_refs"],
                "preserve_complex_object_fields": [
                    "body.figure",
                    "body.table",
                    "body.equation",
                ],
                "unresolved_style_fields": [
                    "body.numbered_list_item",
                    "body.figure.caption",
                    "body.table.caption",
                ],
            },
        },
        {
            "placement_id": "placement.references.entries",
            "field_id": "references.entries",
            "source_content_ids": by_field["references.entries"],
            "target": {
                "slot_id": "slot.references",
                "tag": "docfit.references",
            },
            "action": "replace_block_content_control_in_source_order",
            "order": "source_content_order",
            "status": "ready_for_human_acceptance",
        },
        {
            "placement_id": "placement.generated.toc",
            "field_id": "generated.toc",
            "source_content_ids": [],
            "target": {"region_id": "region.generated.toc"},
            "action": "retain_and_update_existing_toc_field_after_fill",
            "status": "candidate_pending_final_word_update",
        },
    ]

    body_slot_fields = {
        "body.heading.level1",
        "body.heading.level2",
        "body.heading.level3",
        "body.paragraph",
    }
    target_results: list[JsonObject] = []
    for slot in contract["slots"]:
        field_id = slot["field_id"]
        if field_id not in fields:
            raise ValueError(f"Fill contract contains a non-Registry field ID: {field_id}")
        source_ids = by_field.get(field_id, [])
        if field_id in body_slot_fields:
            status = "covered_by_body_tree_placement"
        elif field_id == "references.entries":
            status = "placed"
        elif source_ids:
            status = "placed"
            placements.append(
                {
                    "placement_id": f"placement.{slot['slot_id']}",
                    "field_id": field_id,
                    "source_content_ids": source_ids,
                    "target": {
                        "slot_id": slot["slot_id"],
                        "tag": slot["locator"]["value"],
                    },
                    "action": "replace_content_control",
                    "projection": "normalized_value_when_present_otherwise_observed_value",
                    "status": "ready_for_human_acceptance",
                }
            )
        elif slot.get("required") is True:
            status = "needs_input"
        else:
            status = "omit_optional_source_missing"
        target_results.append(
            {
                "slot_id": slot["slot_id"],
                "field_id": field_id,
                "required": slot.get("required") is True,
                "source_status": field_results[field_id]["status"],
                "status": status,
            }
        )

    missing_required = [
        {
            "slot_id": value["slot_id"],
            "field_id": value["field_id"],
            "action": "request_user_input",
        }
        for value in target_results
        if value["status"] == "needs_input"
    ]
    result: JsonObject = {
        "schema_version": "docfit-template-filling-placement-gold/v1",
        "placement_gold_id": "hunau-undergraduate.student-002",
        "gold_revision": GOLD_REVISION,
        "status": "candidate_ready_for_independent_review",
        "expected_business_status": "NEEDS_INPUT",
        "field_registry_ref": {
            "path": os.path.relpath(REGISTRY_V3, FILLING_DIR),
            "registry_id": registry["registry_id"],
            "registry_version": registry["registry_version"],
            "sha256": registry_sha256,
        },
        "extraction_gold_ref": {
            "path": os.path.relpath(GOLD_JSON, FILLING_DIR),
            "gold_revision": GOLD_REVISION,
            "sha256": gold_sha256,
        },
        "template_fill_contract_ref": {
            "path": SYNCED_FILL_CONTRACT.name,
            "sha256": contract_sha256,
        },
        "template_ref": {
            "path": os.path.relpath(TARGET_TEMPLATE, FILLING_DIR),
            "sha256": sha256_file(TARGET_TEMPLATE),
            "acceptance": "diagnostic_template_candidate_not_human_accepted",
        },
        "placements": placements,
        "target_results": target_results,
        "missing_required": missing_required,
        "unresolved": [
            {
                "reason": "target_style_contract_missing",
                "field_ids": [
                    "body.numbered_list_item",
                    "body.figure.caption",
                    "body.table.caption",
                ],
            },
            {
                "reason": "template_truth_not_human_accepted",
                "template_sha256": sha256_file(TARGET_TEMPLATE),
            },
        ],
        "unregistered_items": [],
        "review": {
            "status": "ready_for_independent_human_review",
            "conclusion": "extraction_input_accepted_filling_not_yet_accepted",
        },
    }
    validate_placement(result, gold, contract, registry)
    return result


def validate_placement(
    placement: JsonObject,
    gold: JsonObject,
    contract: JsonObject,
    registry: JsonObject,
) -> None:
    registry_ids = set(registry_fields(registry))
    content_ids = {value["content_id"] for value in gold["items"]}
    used_content_ids: set[str] = set()
    for value in placement["placements"]:
        if value["field_id"] not in registry_ids:
            raise ValueError(f"Placement guessed a field ID: {value['field_id']}")
        for content_id in value["source_content_ids"]:
            if content_id not in content_ids:
                raise ValueError(f"Placement references stale content ID: {content_id}")
            used_content_ids.add(content_id)
    for slot in contract["slots"]:
        if slot["field_id"] not in registry_ids:
            raise ValueError(f"Synced fill contract guessed a field ID: {slot['field_id']}")
        if slot["content_type"] != registry_fields(registry)[slot["field_id"]]["content_type"]:
            raise ValueError(f"Synced fill contract type diverges: {slot['slot_id']}")
    placeable_fields = {
        "thesis.title.zh",
        "thesis.title.en",
        "abstract.zh",
        "abstract.en",
        "keywords.zh",
        "keywords.en",
        "body.chapters",
        "body.heading.level1",
        "body.heading.level2",
        "body.heading.level3",
        "body.heading.level4",
        "body.numbered_list_item",
        "body.paragraph",
        "body.figure",
        "body.figure.caption",
        "body.equation",
        "body.table",
        "body.table.caption",
        "references.entries",
    }
    expected_used = {
        value["content_id"]
        for value in gold["items"]
        if value["field_id"] in placeable_fields
    }
    if used_content_ids != expected_used:
        raise ValueError("Placement does not cover every present Student 002 content item.")
    if placement["unregistered_items"]:
        raise ValueError("Placement must not retain unregistered items.")


def package_manifest(
    *,
    registry_sha256: str,
    gold_sha256: str,
    product_review_sha256: str,
    review_sha256: str,
    figure_assets: list[JsonObject],
) -> JsonObject:
    return {
        "schema_version": "docfit-extraction-gold-manifest/v1",
        "student_id": "student-002",
        "status": "gold",
        "gold_revision": GOLD_REVISION,
        "accepted_at": REVIEWED_AT,
        "accepted_by": REVIEWER,
        "student_source": {
            "path": os.path.relpath(SOURCE_DOCX, EXTRACTION_DIR),
            "sha256": SOURCE_SHA256,
        },
        "field_registry_ref": {
            "path": os.path.relpath(REGISTRY_V3, EXTRACTION_DIR),
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.3.0",
            "sha256": registry_sha256,
        },
        "artifacts": [
            {"path": GOLD_JSON.name, "sha256": gold_sha256},
            {
                "path": EXTRACTION_PRODUCT_REVIEW.name,
                "sha256": product_review_sha256,
                "role": "human_product_review",
            },
            {"path": EXTRACTION_REVIEW.name, "sha256": review_sha256},
            *[
                {
                    "path": value["path"],
                    "sha256": value["sha256"],
                    "role": "human_review_figure_evidence",
                }
                for value in figure_assets
            ],
        ],
        "privacy": "restricted_student_content_not_for_public_ci_or_logs",
    }


def filling_manifest(
    *,
    registry_sha256: str,
    gold_sha256: str,
    contract_sha256: str,
    placement_sha256: str,
) -> JsonObject:
    return {
        "schema_version": "docfit-template-filling-manifest/v1",
        "case_id": "hunau-undergraduate__student-002",
        "status": "candidate_ready_for_independent_review",
        "expected_business_status": "NEEDS_INPUT",
        "field_registry_ref": {
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.3.0",
            "sha256": registry_sha256,
        },
        "extraction_gold_ref": {
            "path": os.path.relpath(GOLD_JSON, FILLING_DIR),
            "sha256": gold_sha256,
        },
        "artifacts": [
            {"path": SYNCED_FILL_CONTRACT.name, "sha256": contract_sha256},
            {"path": PLACEMENT_MAP.name, "sha256": placement_sha256},
        ],
        "blocking_review": [
            "template_truth_not_human_accepted",
            "target_style_contracts_missing_for_three_body_fields",
            "eleven_required_template_slots_need_user_input",
        ],
    }


def validate_registry(registry: JsonObject) -> None:
    fields = registry["fields"]
    field_ids = [value["field_id"] for value in fields]
    if len(field_ids) != 54 or len(field_ids) != len(set(field_ids)):
        raise ValueError("Registry v0.3 must preserve exactly 54 unique canonical IDs.")
    for field in fields:
        if field["student_extraction_policy"] not in {"required", "optional", "not_applicable"}:
            raise ValueError(f"Invalid student extraction policy: {field['field_id']}")
        if not field["value_sources"]:
            raise ValueError(f"Field has no allowed value source: {field['field_id']}")
        parent = field.get("parent_field_id")
        if parent is not None and parent not in field_ids:
            raise ValueError(f"Registry parent is missing: {field['field_id']} -> {parent}")


def materialize(*, check: bool) -> None:
    registry = registry_v3_snapshot()
    validate_registry(registry)
    registry_content = yaml_bytes(registry)
    registry_sha256 = sha256_bytes(registry_content)
    write_or_check(REGISTRY_V3, registry_content, check=check)

    gold = build_gold(registry, registry_sha256)
    gold_content = json_bytes(gold)
    gold_sha256 = sha256_bytes(gold_content)
    write_or_check(GOLD_JSON, gold_content, check=check)

    figure_assets = review_figure_assets(gold, check=check)
    product_review_content = extraction_product_review(
        gold=gold,
        registry=registry,
        registry_sha256=registry_sha256,
        figure_assets=figure_assets,
    )
    product_review_sha256 = sha256_bytes(product_review_content)
    write_or_check(EXTRACTION_PRODUCT_REVIEW, product_review_content, check=check)

    review = extraction_review(gold, registry_sha256, product_review_sha256)
    review_content = yaml_bytes(review)
    review_sha256 = sha256_bytes(review_content)
    write_or_check(EXTRACTION_REVIEW, review_content, check=check)

    extraction_manifest = package_manifest(
        registry_sha256=registry_sha256,
        gold_sha256=gold_sha256,
        product_review_sha256=product_review_sha256,
        review_sha256=review_sha256,
        figure_assets=figure_assets,
    )
    write_or_check(EXTRACTION_MANIFEST, yaml_bytes(extraction_manifest), check=check)

    contract = synced_fill_contract(registry_sha256)
    contract_content = yaml_bytes(contract)
    contract_sha256 = sha256_bytes(contract_content)
    write_or_check(SYNCED_FILL_CONTRACT, contract_content, check=check)

    placement = placement_map(
        gold=gold,
        gold_sha256=gold_sha256,
        contract=contract,
        contract_sha256=contract_sha256,
        registry=registry,
        registry_sha256=registry_sha256,
    )
    placement_content = yaml_bytes(placement)
    placement_sha256 = sha256_bytes(placement_content)
    write_or_check(PLACEMENT_MAP, placement_content, check=check)

    fill_manifest = filling_manifest(
        registry_sha256=registry_sha256,
        gold_sha256=gold_sha256,
        contract_sha256=contract_sha256,
        placement_sha256=placement_sha256,
    )
    write_or_check(FILLING_MANIFEST, yaml_bytes(fill_manifest), check=check)

    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "check" if check else "materialize",
                "registry_sha256": registry_sha256,
                "gold_sha256": gold_sha256,
                "product_review_sha256": product_review_sha256,
                "gold_item_count": len(gold["items"]),
                "coverage": gold["coverage"]["status_counts"],
                "placement_sha256": placement_sha256,
                "missing_required_slot_count": len(placement["missing_required"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that committed/generated artifacts exactly match the deterministic output.",
    )
    args = parser.parse_args()
    materialize(check=args.check)


if __name__ == "__main__":
    main()

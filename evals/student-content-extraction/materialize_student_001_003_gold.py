#!/usr/bin/env python3
# ruff: noqa: E501
"""Materialize accepted Registry-aligned Extraction Gold for Student 001 and 003.

Student 002 remains the accepted Gold baseline.  This materializer parses the two
remaining immutable source DOCX files directly, creates a complete source-object
inventory, projects every Registry field, extracts reviewable image assets, and
builds product-facing review records, and records the product owner's acceptance.
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
REGISTRY_V3 = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.3.yaml"
REGISTRY_V4 = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.4.yaml"
GOLD_ROOT = PROJECT_ROOT / "temp/manual-gold-preparation/gold"
ASSET_ROOT = GOLD_ROOT / "20-student-assets"

REGISTRY_V3_SHA256 = "a6df179b7a4112672b275289df2e43870ca9a363cb3e46b74a77e9921cff570b"
GOLD_REVISION = "2026-08-12.r2"
REVIEWER = "产品负责人（当前用户）"
REVIEWED_AT = "2026-08-12"
ACCEPTANCE_EVIDENCE = "我看了一下，这些识别都没有问题。"
ORDER_REQUIREMENT_EVIDENCE = (
    "Gold 除了字段映射，还必须包含识别内容的顺序；以产品用户内容提取定义为准。"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W_NS, "w14": W14_NS, "a": A_NS, "r": R_NS}

CAPTION_PREFIX = re.compile(
    r"^(?:(?:图|表)\s*(?:\d+(?:\s*[-－—–]\s*\d+)?\s*)?|"
    r"(?:Fig(?:ure)?\.?|Table)\s*(?:\d+(?:\s*[-－—–]\s*\d+)?\s*)?)",
    re.IGNORECASE,
)
PARENTHESIZED_NUMBER = re.compile(r"^[（(]\d+[）)]")


STUDENTS: dict[str, JsonObject] = {
    "student-001": {
        "source": PROJECT_ROOT
        / "temp/manual-gold-preparation/student-content-real-student-001.docx",
        "source_sha256": "2e3d6310611cbe2fafddbda18e7b83387b5f3ea3d1f0f3163154d6ec129a6f60",
        "body_range": (110, 328),
        "front_fields": {
            "thesis.title.zh": {"paragraphs": [88]},
            "abstract.zh": {"paragraphs": [90, 91], "join": "\n\n"},
            "keywords.zh": {"paragraphs": [92], "normalizer": "keywords_zh"},
            "thesis.title.en": {"paragraphs": [101]},
            "abstract.en": {"paragraphs": [103, 104, 105], "join": "\n\n"},
            "keywords.en": {"paragraphs": [106], "normalizer": "keywords_en"},
        },
        "headings": {
            1: [110, 166, 240, 316],
            2: [
                112,
                127,
                131,
                133,
                140,
                167,
                185,
                191,
                216,
                233,
                241,
                253,
                266,
                276,
                299,
                317,
                322,
                327,
            ],
            3: [
                114,
                121,
                135,
                137,
                141,
                145,
                169,
                175,
                178,
                182,
                187,
                189,
                193,
                195,
                197,
                218,
                222,
                224,
                226,
                229,
                231,
                235,
                238,
                242,
                247,
                254,
                267,
                277,
                285,
                300,
                323,
                325,
            ],
        },
        "visible_heading_labels": {
            114: "1.1 PGPR促进植物生长的直接作用",
            121: "1.2 PGPR促进植物生长的间接作用",
            166: "第二章 材料与方法",
            169: "1.1 实验材料",
            175: "1.2 菌株的活化与保存",
            178: "1.3 菌株的功能验证",
            182: "1.4 PGP6的抗生素最小抑菌浓度实验",
            187: "1.1 实验材料",
            193: "1.1 实验材料",
            195: "1.2 打靶片段引物设计",
            218: "1.1 实验材料",
            222: "1.2 电转化",
            224: "1.3 PGP6感受态细胞的制备",
            226: "1.4 PGP6-pKD46感受态细胞的制备",
            235: "1.1 实验材料",
            240: "第三章 结果与分析",
            242: "1.1 生长素标准曲线的制定",
            247: "1.2 菌株PGP6的抗生素最小抑菌浓度实验",
            254: "1.1 IAA合成候选基因的定位",
            267: "1.1 trpA、trpB、trpA与trpB、patB及iaaH的打靶片段",
            285: "1.2 pKD46辅助质粒的温敏去除及验证",
            316: "第四章 结论与展望",
        },
        "numbered_lists": [170, 171, 172, 173, 174, 188, 194, 219, 220, 221, 236, 237],
        "visible_list_prefixes": {236: "（1）", 237: "（2）"},
        "figures": [
            {"captions": [147, 148], "source_key": "1-1"},
            {"captions": [245, 246], "source_key": "2-1"},
            {"captions": [258, 259], "source_key": "3-1"},
            {"captions": [261, 262], "source_key": "3-2"},
            {"captions": [271, 272], "source_key": "4-1"},
            {"captions": [274, 275], "source_key": "4-2"},
            {"captions": [281, 282], "source_key": "5-1"},
            {"captions": [283, 284], "source_key": "5-2"},
            {"captions": [290, 291], "source_key": "5-3"},
            {"captions": [293, 294], "source_key": "5-4"},
            {"captions": [297, 298], "source_key": "5-5"},
            {"captions": [309, 310], "source_key": "6-1"},
        ],
        "body_tables": [
            {"body_index": 199, "captions": [200, 201], "source_key": "unnumbered-1"},
            {"body_index": 209, "captions": [210, 211], "source_key": "unnumbered-2"},
            {"body_index": 213, "captions": [214, 215], "source_key": "unnumbered-3"},
            {"body_index": 249, "captions": [250, 251], "source_key": "1-1"},
            {"body_index": 263, "captions": [264, 265], "source_key": "2-1"},
            {"body_index": 305, "captions": [306, 307], "source_key": "3-1"},
        ],
        "references": list(range(341, 386)),
        "appendix_title": [388],
        "appendix_body_table": 389,
        "acknowledgement": [391, 392, 393],
        "excluded_paragraphs": {
            **{index: "generated_toc_cached_text" for index in range(25, 84)},
            3: "template_owned_declaration_heading",
            5: "template_owned_declaration_fixed_text",
            8: "blank_user_signature_line",
            16: "template_owned_declaration_heading",
            18: "template_owned_declaration_fixed_text",
            20: "blank_user_signature_line",
            21: "blank_user_signature_line",
            89: "target_template_structural_label",
            102: "target_template_structural_label",
            340: "target_template_structural_label",
            390: "target_template_structural_label",
        },
        "excluded_tables": {0: "blank_source_cover_template_shell"},
        "excluded_picture_parts": {
            "word/media/image1.jpeg": "source_school_branding_not_student_content",
            "word/media/image2.png": "source_school_branding_not_student_content",
        },
        "expected_counts": {
            "thesis.title.zh": 1,
            "abstract.zh": 1,
            "keywords.zh": 1,
            "thesis.title.en": 1,
            "abstract.en": 1,
            "keywords.en": 1,
            "body.chapters": 1,
            "body.heading.level1": 4,
            "body.heading.level2": 18,
            "body.heading.level3": 32,
            "body.paragraph": 69,
            "body.numbered_list_item": 12,
            "body.figure": 12,
            "body.figure.caption": 24,
            "body.table": 6,
            "body.table.caption": 12,
            "references.entries": 45,
            "appendix.title": 1,
            "appendix.body": 1,
            "acknowledgement.body": 1,
        },
    },
    "student-003": {
        "source": PROJECT_ROOT
        / "temp/manual-gold-preparation/student-content-real-student-003.docx",
        "source_sha256": "cf49d90832c44d2f28e7fe6940217f4afe7c637f179b3610c75801b900e7d290",
        "body_range": (81, 148),
        "front_fields": {
            "thesis.title.zh": {"paragraphs": [4, 65]},
            "author.name.zh": {
                "paragraphs": [9, 66],
                "normalized": "袁一文",
            },
            "author.student_id": {
                "paragraphs": [10],
                "normalized": "202240490218",
            },
            "author.department": {
                "paragraphs": [13, 68],
                "normalized": "农学院",
            },
            "advisor.name.zh": {
                "paragraphs": [12, 67],
                "normalized": "胡亚军",
            },
            "submission.date": {
                "paragraphs": [17],
                "normalized": "2026年5月",
            },
            "abstract.zh": {"paragraphs": [70], "normalizer": "abstract_zh"},
            "keywords.zh": {"paragraphs": [72], "normalizer": "keywords_zh"},
            "thesis.title.en": {"paragraphs": [6]},
            "author.name.en": {
                "paragraphs": [74],
                "normalized": "yuanyiwen",
            },
            "advisor.name.en": {
                "paragraphs": [75],
                "normalized": "huyajun",
            },
            "abstract.en": {"paragraphs": [78], "normalizer": "abstract_en"},
            "keywords.en": {"paragraphs": [79], "normalizer": "keywords_en"},
            "advisor.title": {"paragraphs": [12], "normalized": "教授"},
            "author.cohort_class": {
                "paragraphs": [11],
                "normalized": "2022级种子（2）班",
            },
            "author.department.en": {
                "paragraphs": [76],
                "normalized": "College of Agrivulture",
            },
        },
        "headings": {
            1: [81, 91, 105, 145, 147],
            2: [82, 84, 89, 92, 99, 106, 116],
            3: [85, 87, 93, 95, 97, 100, 103, 117, 122, 129],
        },
        "visible_heading_labels": {},
        "numbered_lists": [],
        "visible_list_prefixes": {},
        "figures": [
            {"table_index": 110, "captions": [111, 112], "source_key": "1"},
            {"table_index": 113, "captions": [114, 115], "source_key": "2"},
            {"table_index": 119, "captions": [120, 121], "source_key": "3"},
            {"table_index": 126, "captions": [127, 128], "source_key": "4"},
            {"table_index": 133, "captions": [134, 135], "source_key": "5"},
            {"table_index": 136, "captions": [137, 138], "source_key": "6"},
        ],
        "body_tables": [
            {"body_index": 143, "captions": [141, 142], "source_key": "3-1"},
        ],
        "references": [
            *range(151, 174),
            175,
            176,
            177,
            179,
            180,
            181,
        ],
        "appendix_title": [],
        "appendix_body_table": None,
        "acknowledgement": [186],
        "excluded_paragraphs": {
            1: "source_school_branding_not_student_content",
            2: "source_template_document_type_label",
            16: "source_template_location_label",
            20: "template_owned_declaration_heading",
            21: "template_owned_declaration_heading",
            24: "template_owned_declaration_fixed_text",
            28: "blank_user_signature_line",
            29: "blank_user_signature_line",
            73: "unfilled_source_template_placeholder",
            150: "target_template_structural_label",
            185: "target_template_structural_label",
        },
        "excluded_tables": {},
        "excluded_picture_parts": {},
        "expected_counts": {
            "thesis.title.zh": 1,
            "author.name.zh": 1,
            "author.student_id": 1,
            "author.department": 1,
            "advisor.name.zh": 1,
            "submission.date": 1,
            "abstract.zh": 1,
            "keywords.zh": 1,
            "thesis.title.en": 1,
            "author.name.en": 1,
            "advisor.name.en": 1,
            "abstract.en": 1,
            "keywords.en": 1,
            "advisor.title": 1,
            "author.cohort_class": 1,
            "author.department.en": 1,
            "body.chapters": 1,
            "body.heading.level1": 5,
            "body.heading.level2": 7,
            "body.heading.level3": 10,
            "body.paragraph": 21,
            "body.figure": 6,
            "body.figure.caption": 12,
            "body.table": 1,
            "body.table.caption": 2,
            "references.entries": 29,
            "acknowledgement.body": 1,
        },
    },
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: JsonObject) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def yaml_bytes(value: JsonObject) -> bytes:
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        width=110,
    ).encode()


def load_yaml(path: Path) -> JsonObject:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return value


def write_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Generated artifact is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def registry_v4_snapshot() -> JsonObject:
    if sha256_file(REGISTRY_V3) != REGISTRY_V3_SHA256:
        raise ValueError("Accepted Registry v0.3 no longer matches its frozen hash.")
    registry = copy.deepcopy(load_yaml(REGISTRY_V3))
    registry["registry_version"] = "0.4.0"
    registry["revision"] = "2026-08-12.3"
    registry["status"] = "accepted"
    registry["description"] = (
        "在 accepted v0.3 的 54 个 canonical field_id 上，补齐多资产语义图、"
        "可缺失源编号的题注前缀、题注结构配对、Word 自动列表编号、修订最终视图与"
        "批注排除规则；由 Student 001/003 Extraction 扩样触发并经产品负责人验收。"
    )
    registry["derived_from"] = {
        "path": "docs/plans/docfit-content-field-registry/content-fields-v0.3.yaml",
        "sha256": REGISTRY_V3_SHA256,
        "migration": (
            "same_54_canonical_field_ids_add_multi_asset_figure_optional_source_caption_number_"
            "and_revision_view_contract"
        ),
    }
    registry["review"] = {
        "status": "accepted",
        "reviewer": REVIEWER,
        "reviewed_at": REVIEWED_AT,
        "conclusion": "accepted_for_student_001_and_003_extraction_gold",
        "acceptance_evidence": ACCEPTANCE_EVIDENCE,
        "pilots": ["student-001-extraction", "student-003-extraction"],
    }
    registry["source_document_view_policy"] = {
        "word_revision_view": "final_visible",
        "inserted_text": "included_in_observed_content_and_retained_as_revision_evidence",
        "deleted_text": "excluded_from_observed_content_but_accounted_for_as_revision_evidence",
        "comments": "review_metadata_not_student_thesis_content",
        "human_gate": (
            "Any ambiguous or semantically conflicting tracked change blocks Gold promotion."
        ),
    }
    registry["source_numbering_policy"] = {
        "numbered_list_evidence": [
            "explicit_parenthesized_marker_in_text",
            "word_numPr_with_numbering_definition",
        ],
        "observed_value": (
            "Retain the visible list marker; when Word generates it, also retain the raw text payload "
            "and numbering definition evidence."
        ),
        "target_generation": "Target template owns final list and heading numbering mechanics.",
    }
    fields = registry.get("fields")
    if not isinstance(fields, list):
        raise ValueError("Registry fields are missing.")
    by_id = {str(field["field_id"]): field for field in fields}
    figure = by_id["body.figure"]
    figure["meaning"] = "正文中由同一组题注共同描述的语义插图；可由一个或多个源图片资产组成。"
    figure["notes"] = (
        "一个 content item 可绑定一项或多项 asset_refs；多面板或并排图片若共享同一组题注，"
        "按一个语义图提取。仅用于承载图片的无文本表格是布局容器，不另算 body.table。"
    )
    figure["composition"] = {
        "semantic_unit": "captioned_figure",
        "asset_cardinality": "one_or_more",
        "layout_only_image_grid_is_body_table": False,
    }
    table = by_id["body.table"]
    table["notes"] = (
        "保留语义数据表结构；只承载图片排列且无数据单元格语义的表格是 figure 布局容器，"
        "不得重复提取为 body.table。具体边框、表头和样式由模板规范约束。"
    )
    for field_id, labels in (
        ("body.figure.caption", ["图", "Fig.", "Figure"]),
        ("body.table.caption", ["表", "Table"]),
    ):
        field = by_id[field_id]
        field["meaning"] = (
            "描述父级图或表的题注正文；源中可位于对象前后，目标位置和编号由模板决定。"
        )
        normalization = field.setdefault("normalization", {})
        normalization["preserve_observed_value"] = True
        normalization["source_prefix_grammar"] = {
            "type_labels": labels,
            "source_number": "optional",
            "number_examples": ["2", "2-4", "2－4", "2—4"],
            "remove_from_normalized_value": True,
        }
        normalization["trim_outer_whitespace"] = True
        normalization["generation_owner"] = "target_template_caption_numbering"
        field["caption_binding"] = {
            "primary_evidence": "source_structure_adjacency_and_layout",
            "source_number_role": "trace_evidence_not_object_identity",
            "number_mismatch": "retain_observed_and_require_human_confirmation",
        }
    if len(fields) != 54 or len(by_id) != 54:
        raise ValueError("Registry v0.4 must preserve the accepted 54 canonical IDs.")
    return registry


def element_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//w:t", NS)).strip()


def make_source_object(
    *,
    student_id: str,
    source_sha256: str,
    kind: str,
    locator: str,
    fingerprint: str,
    text: str,
    scope: str,
    body_sequence: int | None = None,
    extra: JsonObject | None = None,
) -> JsonObject:
    object_id = (
        "obj-"
        + hashlib.sha256(f"{student_id}|{kind}|{locator}|{fingerprint}".encode()).hexdigest()[:24]
    )
    value: JsonObject = {
        "source_object_ref": {
            "object_id": object_id,
            "document_sha256": source_sha256,
        },
        "kind": kind,
        "scope": scope,
        "source_locator": locator,
        "expected_fingerprint": fingerprint,
        "text": text,
    }
    if body_sequence is not None:
        value["body_sequence"] = body_sequence
    if extra:
        value.update(extra)
    return value


def parse_relationships(package: ZipFile) -> dict[str, str]:
    root = ET.fromstring(package.read("word/_rels/document.xml.rels"))
    return {
        str(value.get("Id")): str(value.get("Target"))
        for value in root.findall(f"{{{PKG_REL_NS}}}Relationship")
    }


def package_part(target: str) -> str:
    normalized = target.lstrip("/")
    return normalized if normalized.startswith("word/") else f"word/{normalized}"


def table_cells(table: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.findall("./w:tr", NS):
        rows.append([element_text(cell) for cell in row.findall("./w:tc", NS)])
    return rows


def inventory_docx(student_id: str, config: JsonObject) -> tuple[JsonObject, dict[str, bytes]]:
    source = Path(config["source"])
    source_sha256 = str(config["source_sha256"])
    if sha256_file(source) != source_sha256:
        raise ValueError(f"{student_id} source hash changed.")
    objects: list[JsonObject] = []
    assets: dict[str, bytes] = {}
    with ZipFile(source) as package:
        relationship_targets = parse_relationships(package)
        document = ET.fromstring(package.read("word/document.xml"))
        body = document.find("w:body", NS)
        if body is None:
            raise ValueError(f"{student_id} has no Word body.")
        top_level_by_index: dict[int, JsonObject] = {}
        revision_hosts: dict[int, JsonObject] = {}
        table_ordinal = 0
        for body_index, child in enumerate(list(body)):
            if child.tag == f"{{{W_NS}}}p":
                para_id = child.get(f"{{{W14_NS}}}paraId")
                if not para_id:
                    raise ValueError(f"{student_id} paragraph {body_index} has no paraId.")
                locator = f"/body/p[@paraId={para_id}]"
                style = child.find("./w:pPr/w:pStyle", NS)
                num_id = child.find("./w:pPr/w:numPr/w:numId", NS)
                ilvl = child.find("./w:pPr/w:numPr/w:ilvl", NS)
                fingerprint = sha256_bytes(ET.tostring(child, encoding="utf-8"))
                paragraph = make_source_object(
                    student_id=student_id,
                    source_sha256=source_sha256,
                    kind="paragraph",
                    locator=locator,
                    fingerprint=fingerprint,
                    text=element_text(child),
                    scope="main_story",
                    body_sequence=body_index,
                    extra={
                        "paragraph_style_id": (
                            style.get(f"{{{W_NS}}}val") if style is not None else None
                        ),
                        "numbering": (
                            {
                                "num_id": num_id.get(f"{{{W_NS}}}val"),
                                "level": (ilvl.get(f"{{{W_NS}}}val") if ilvl is not None else None),
                            }
                            if num_id is not None
                            else None
                        ),
                    },
                )
                objects.append(paragraph)
                top_level_by_index[body_index] = paragraph
                host = paragraph
            elif child.tag == f"{{{W_NS}}}tbl":
                table_ordinal += 1
                locator = f"/body/tbl[{table_ordinal}]"
                cells = table_cells(child)
                fingerprint = sha256_bytes(ET.tostring(child, encoding="utf-8"))
                table = make_source_object(
                    student_id=student_id,
                    source_sha256=source_sha256,
                    kind="table",
                    locator=locator,
                    fingerprint=fingerprint,
                    text="\n".join("\t".join(row) for row in cells),
                    scope="main_story",
                    body_sequence=body_index,
                    extra={
                        "structure": {
                            "row_count": len(cells),
                            "column_count": max((len(row) for row in cells), default=0),
                            "cells": cells,
                            "ooxml_sha256": fingerprint,
                        }
                    },
                )
                objects.append(table)
                top_level_by_index[body_index] = table
                host = table
            else:
                continue

            for revision_kind in ("ins", "del"):
                for revision in child.findall(f".//w:{revision_kind}", NS):
                    revision_hosts[id(revision)] = host

            image_number = 0
            for blip in child.findall(".//a:blip", NS):
                relationship_id = blip.get(f"{{{R_NS}}}embed")
                target = relationship_targets.get(str(relationship_id))
                if not relationship_id or not target:
                    continue
                image_number += 1
                part = package_part(target)
                asset_bytes = package.read(part)
                asset_sha256 = sha256_bytes(asset_bytes)
                locator = f"{host['source_locator']}/image[{image_number}]"
                picture = make_source_object(
                    student_id=student_id,
                    source_sha256=source_sha256,
                    kind="picture",
                    locator=locator,
                    fingerprint=asset_sha256,
                    text="",
                    scope="main_story",
                    body_sequence=body_index,
                    extra={
                        "host_object_id": host["source_object_ref"]["object_id"],
                        "relationship_id": relationship_id,
                        "package_part": part,
                        "asset_sha256": asset_sha256,
                        "size_bytes": len(asset_bytes),
                    },
                )
                objects.append(picture)
                assets[picture["source_object_ref"]["object_id"]] = asset_bytes

        revision_counts: dict[str, int] = defaultdict(int)
        for revision_kind in ("ins", "del"):
            for ordinal, revision in enumerate(
                document.findall(f".//w:{revision_kind}", NS), start=1
            ):
                revision_counts[revision_kind] += 1
                text_nodes = revision.findall(".//w:t", NS)
                if revision_kind == "del":
                    text_nodes += revision.findall(".//w:delText", NS)
                text = "".join(node.text or "" for node in text_nodes).strip()
                fingerprint = sha256_bytes(ET.tostring(revision, encoding="utf-8"))
                locator = f"/revisions/{revision_kind}[{ordinal}]"
                host = revision_hosts.get(id(revision))
                objects.append(
                    make_source_object(
                        student_id=student_id,
                        source_sha256=source_sha256,
                        kind=f"revision_{revision_kind}",
                        locator=locator,
                        fingerprint=fingerprint,
                        text=text,
                        scope="revision_metadata",
                        extra={
                            "revision_id": revision.get(f"{{{W_NS}}}id"),
                            "author": revision.get(f"{{{W_NS}}}author"),
                            "date": revision.get(f"{{{W_NS}}}date"),
                            "host_object_id": (
                                host["source_object_ref"]["object_id"] if host else None
                            ),
                            "host_source_locator": host["source_locator"] if host else None,
                            "host_body_sequence": host.get("body_sequence") if host else None,
                        },
                    )
                )

        comments_count = 0
        if "word/comments.xml" in package.namelist():
            comments = ET.fromstring(package.read("word/comments.xml"))
            for ordinal, comment in enumerate(comments.findall("w:comment", NS), start=1):
                comments_count += 1
                text = element_text(comment)
                fingerprint = sha256_bytes(ET.tostring(comment, encoding="utf-8"))
                comment_id = comment.get(f"{{{W_NS}}}id")
                objects.append(
                    make_source_object(
                        student_id=student_id,
                        source_sha256=source_sha256,
                        kind="comment",
                        locator=f"/comments/comment[@id={comment_id or ordinal}]",
                        fingerprint=fingerprint,
                        text=text,
                        scope="review_metadata",
                        extra={"comment_id": comment_id},
                    )
                )

        header_footer_count = 0
        for part in sorted(
            name
            for name in package.namelist()
            if (name.startswith("word/header") or name.startswith("word/footer"))
            and name.endswith(".xml")
        ):
            root = ET.fromstring(package.read(part))
            text = element_text(root)
            if not text:
                continue
            header_footer_count += 1
            fingerprint = sha256_bytes(package.read(part))
            objects.append(
                make_source_object(
                    student_id=student_id,
                    source_sha256=source_sha256,
                    kind="header_footer",
                    locator=f"/{part}",
                    fingerprint=fingerprint,
                    text=text,
                    scope="header_footer",
                    extra={"package_part": part},
                )
            )

        inventory: JsonObject = {
            "schema_version": "docfit-student-source-inventory/v1",
            "student_id": student_id,
            "source_path": os.path.relpath(source, ASSET_ROOT / student_id),
            "source_sha256": source_sha256,
            "view": "word_final_visible",
            "objects": objects,
            "package_summary": {
                "top_level_body_children": len(list(body)),
                "paragraph_objects": sum(value["kind"] == "paragraph" for value in objects),
                "table_objects": sum(value["kind"] == "table" for value in objects),
                "picture_objects": sum(value["kind"] == "picture" for value in objects),
                "revision_insert_objects": revision_counts.get("ins", 0),
                "revision_delete_objects": revision_counts.get("del", 0),
                "comment_objects": comments_count,
                "nonempty_header_footer_objects": header_footer_count,
                "inventory_object_count": len(objects),
            },
        }
        del top_level_by_index
        return inventory, assets


def source_ref(source: JsonObject) -> JsonObject:
    value = dict(source["source_object_ref"])
    value["expected_fingerprint"] = source["expected_fingerprint"]
    value["source_locator"] = source["source_locator"]
    return value


def language_of(value: str) -> str:
    has_zh = bool(re.search(r"[\u3400-\u9fff]", value))
    has_en = bool(re.search(r"[A-Za-z]", value))
    if has_zh and has_en:
        return "mixed"
    if has_zh:
        return "zh"
    if has_en:
        return "en"
    return "und"


def normalize_value(kind: str | None, value: str) -> str:
    if kind == "keywords_zh":
        return re.sub(r"^关键词\s*[：:]\s*", "", value).strip()
    if kind == "keywords_en":
        return re.sub(r"^(?:KEY\s*WORDS|KEYWORDS|Key\s*words)\s*[：:]\s*", "", value).strip()
    if kind == "abstract_zh":
        return re.sub(r"^摘\s*要\s*[：:]\s*", "", value).strip()
    if kind == "abstract_en":
        return re.sub(r"^Abstract\s*[：:]\s*", "", value, flags=re.IGNORECASE).strip()
    return value.strip()


def caption_normalized(value: str) -> str:
    return CAPTION_PREFIX.sub("", value, count=1).strip()


def caption_source_number(value: str) -> str | None:
    match = re.match(
        r"^(?:图|表|Fig(?:ure)?\.?|Table)\s*(\d+(?:\s*[-－—–]\s*\d+)?)",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return re.sub(r"\s*[-－—–]\s*", "-", match.group(1)).strip()


def field_map(registry: JsonObject) -> dict[str, JsonObject]:
    return {str(value["field_id"]): value for value in registry["fields"]}


def content_item(
    *,
    student_id: str,
    field: JsonObject,
    sources: list[JsonObject],
    occurrence: str,
    order: JsonObject,
    parent_content_id: str | None,
    observed_value: str | None = None,
    normalized_value: str | None = None,
    extra: JsonObject | None = None,
) -> JsonObject:
    source_ids = [source["source_object_ref"]["object_id"] for source in sources]
    content_id = (
        "content-"
        + hashlib.sha256(
            f"{student_id}|{field['field_id']}|{occurrence}|{'|'.join(source_ids)}".encode()
        ).hexdigest()[:24]
    )
    value: JsonObject = {
        "content_id": content_id,
        "field_id": field["field_id"],
        "classification_status": "registered",
        "content_type": field["content_type"],
        "parent_content_id": parent_content_id,
        "_order_hint": order,
        "language": field.get("language") or language_of(observed_value or ""),
        "source_object_refs": [source_ref(source) for source in sources],
        "review_status": "accepted",
    }
    if observed_value is not None:
        value["observed_value"] = observed_value
    if normalized_value is not None:
        value["normalized_value"] = normalized_value
    value["source_occurrences"] = [
        {
            "source_object_ref": source_ref(source),
            "observed_text": source.get("text", ""),
        }
        for source in sources
    ]
    if extra:
        value.update(extra)
    return value


def _source_object_orders(objects: list[JsonObject]) -> dict[str, JsonObject]:
    """Return deterministic physical orders for every main-story source object."""

    by_block: dict[int, list[JsonObject]] = defaultdict(list)
    top_by_locator: dict[str, JsonObject] = {}
    for source in objects:
        block = source.get("body_sequence")
        if isinstance(block, int) and not isinstance(block, bool):
            by_block[block].append(source)
            if source.get("kind") in {"paragraph", "table"}:
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
        block = int(top_by_locator[host_locator]["body_sequence"])
        inline = 1 + max(
            (int(value["inline"]) for value in orders.values() if value["block"] == block),
            default=-1,
        )
        orders[object_id] = {"block": block, "inline": inline}
    return orders


def _semantic_text_position(item: JsonObject, objects_by_id: dict[str, JsonObject]) -> int:
    """Order multiple semantic facts extracted from the same physical source object."""

    needle = str(item.get("normalized_value") or "").strip()
    if not needle:
        return 0
    positions: list[int] = []
    for reference in item["source_object_refs"]:
        source = objects_by_id[str(reference["object_id"])]
        position = str(source.get("text", "")).find(needle)
        if position >= 0:
            positions.append(position)
    return min(positions, default=0)


def apply_source_order(items: list[JsonObject], objects: list[JsonObject]) -> None:
    """Replace legacy logical hints with one source-bound total content order."""

    source_orders = _source_object_orders(objects)
    objects_by_id = {
        str(value["source_object_ref"]["object_id"]): value for value in objects
    }
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
        occurrences.sort(
            key=lambda value: (
                int(value["source_order"]["block"]),
                int(value["source_order"]["inline"]),
                str(value["source_object_ref"]["object_id"]),
            )
        )
        if occurrences:
            start = dict(occurrences[0]["source_order"])
            end = dict(occurrences[-1]["source_order"])
        else:
            content_ref = item.get("content_ref")
            if not isinstance(content_ref, dict):
                raise ValueError(f"Content item has neither occurrences nor a span: {item['content_id']}")
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
                _semantic_text_position(value, objects_by_id),
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


def build_candidate(
    student_id: str,
    config: JsonObject,
    registry: JsonObject,
    registry_sha256: str,
    inventory: JsonObject,
) -> JsonObject:
    fields = field_map(registry)
    objects = inventory["objects"]
    paragraphs = {
        int(value["body_sequence"]): value for value in objects if value["kind"] == "paragraph"
    }
    tables = {int(value["body_sequence"]): value for value in objects if value["kind"] == "table"}
    pictures = [value for value in objects if value["kind"] == "picture"]
    items: list[JsonObject] = []

    for field_id, spec in config["front_fields"].items():
        sources = [paragraphs[index] for index in spec["paragraphs"]]
        joined = (
            str(spec["join"]).join(str(source["text"]) for source in sources)
            if "join" in spec
            else str(sources[0]["text"])
        )
        normalized = spec.get("normalized")
        if normalized is None and spec.get("normalizer"):
            normalized = normalize_value(str(spec["normalizer"]), joined)
        items.append(
            content_item(
                student_id=student_id,
                field=fields[field_id],
                sources=sources,
                occurrence=field_id,
                order={"scope": "front_matter", "sequence": min(spec["paragraphs"])},
                parent_content_id=None,
                observed_value=joined,
                normalized_value=str(normalized) if normalized is not None else None,
                extra={"normalization_basis": spec.get("normalizer")}
                if normalized is not None
                else None,
            )
        )

    body_start, body_end = config["body_range"]
    body_item = content_item(
        student_id=student_id,
        field=fields["body.chapters"],
        sources=[],
        occurrence="body-container",
        order={"scope": "body", "sequence": 0},
        parent_content_id=None,
        extra={
            "language": "mixed",
            "content_ref": {
                "document_sha256": config["source_sha256"],
                "start_body_sequence": body_start,
                "end_body_sequence": body_end,
                "start_locator": paragraphs[body_start]["source_locator"],
                "end_locator": paragraphs[body_end]["source_locator"],
            },
        },
    )
    items.append(body_item)

    heading_by_sequence: dict[int, JsonObject] = {}
    active: dict[int, str] = {}
    heading_levels = {
        index: level for level, indices in config["headings"].items() for index in indices
    }
    for sequence in sorted(heading_levels):
        level = heading_levels[sequence]
        source = paragraphs[sequence]
        parent = (
            body_item["content_id"]
            if level == 1
            else active.get(level - 1, body_item["content_id"])
        )
        item = content_item(
            student_id=student_id,
            field=fields[f"body.heading.level{level}"],
            sources=[source],
            occurrence=f"heading-{sequence}",
            order={"scope": "body", "sequence": sequence, "within_source": 1},
            parent_content_id=parent,
            observed_value=str(source["text"]),
            extra={
                "visible_source_label": config["visible_heading_labels"].get(
                    sequence, source["text"]
                ),
                "visible_label_basis": (
                    "reconstructed_from_word_numbering_definition_and_toc_cache"
                    if sequence in config["visible_heading_labels"]
                    else "literal_paragraph_text"
                ),
                "source_numbering": source.get("numbering"),
            },
        )
        heading_by_sequence[sequence] = item
        items.append(item)
        active[level] = item["content_id"]
        active = {key: value for key, value in active.items() if key <= level}

    sorted_headings = sorted(heading_by_sequence)

    def parent_at(sequence: int) -> str:
        current: dict[int, str] = {}
        for heading_sequence in sorted_headings:
            if heading_sequence > sequence:
                break
            level = heading_levels[heading_sequence]
            current[level] = heading_by_sequence[heading_sequence]["content_id"]
            current = {key: value for key, value in current.items() if key <= level}
        return current[max(current)] if current else body_item["content_id"]

    caption_sequences = {index for figure in config["figures"] for index in figure["captions"]} | {
        index for table in config["body_tables"] for index in table["captions"]
    }
    list_sequences = set(config["numbered_lists"])
    body_paragraph_sequences = [
        sequence
        for sequence in range(body_start, body_end + 1)
        if sequence in paragraphs
        and paragraphs[sequence]["text"]
        and sequence not in heading_levels
        and sequence not in caption_sequences
        and sequence not in list_sequences
    ]
    for sequence in body_paragraph_sequences:
        source = paragraphs[sequence]
        items.append(
            content_item(
                student_id=student_id,
                field=fields["body.paragraph"],
                sources=[source],
                occurrence=f"paragraph-{sequence}",
                order={"scope": "body", "sequence": sequence, "within_source": 2},
                parent_content_id=parent_at(sequence),
                observed_value=str(source["text"]),
                extra={
                    "tracked_revision_view": (
                        "final_visible" if student_id == "student-003" else "no_revisions"
                    )
                },
            )
        )

    for sequence in config["numbered_lists"]:
        source = paragraphs[sequence]
        prefix = str(config["visible_list_prefixes"].get(sequence, ""))
        observed = f"{prefix}{source['text']}"
        basis = (
            "word_numPr_visible_parenthesized_marker"
            if prefix
            else "explicit_parenthesized_number_in_text"
        )
        if not prefix and not PARENTHESIZED_NUMBER.match(str(source["text"])):
            raise ValueError(f"{student_id} list item lacks list evidence at {sequence}.")
        items.append(
            content_item(
                student_id=student_id,
                field=fields["body.numbered_list_item"],
                sources=[source],
                occurrence=f"list-{sequence}",
                order={"scope": "body", "sequence": sequence, "within_source": 2},
                parent_content_id=parent_at(sequence),
                observed_value=observed,
                extra={
                    "raw_text_payload": source["text"],
                    "classification_basis": basis,
                    "source_numbering": source.get("numbering"),
                },
            )
        )

    body_pictures = [
        value
        for value in pictures
        if body_start <= int(value["body_sequence"]) <= body_end
        and value["package_part"] not in config["excluded_picture_parts"]
    ]
    body_pictures.sort(key=lambda value: (int(value["body_sequence"]), value["source_locator"]))
    used_picture_ids: set[str] = set()
    for figure_number, figure_spec in enumerate(config["figures"], start=1):
        if "table_index" in figure_spec:
            table_source = tables[int(figure_spec["table_index"])]
            table_object_id = table_source["source_object_ref"]["object_id"]
            figure_pictures = [
                value for value in body_pictures if value.get("host_object_id") == table_object_id
            ]
            sources = [table_source, *figure_pictures]
            sequence = int(figure_spec["table_index"])
        else:
            if figure_number > len(body_pictures):
                raise ValueError(f"{student_id} has too few body pictures.")
            figure_pictures = [body_pictures[figure_number - 1]]
            sources = figure_pictures
            sequence = int(figure_pictures[0]["body_sequence"])
        if not figure_pictures:
            raise ValueError(f"{student_id} figure {figure_number} has no source asset.")
        for picture in figure_pictures:
            used_picture_ids.add(picture["source_object_ref"]["object_id"])
        figure_item = content_item(
            student_id=student_id,
            field=fields["body.figure"],
            sources=sources,
            occurrence=f"figure-{figure_number}",
            order={"scope": "body", "sequence": sequence, "within_source": 3},
            parent_content_id=parent_at(sequence),
            extra={
                "figure_key": f"figure-{figure_number:02d}",
                "source_caption_key": figure_spec["source_key"],
                "composition": (
                    "multi_asset_figure" if len(figure_pictures) > 1 else "single_asset_figure"
                ),
                "asset_refs": [
                    {
                        "source_object_id": picture["source_object_ref"]["object_id"],
                        "package_part": picture["package_part"],
                        "sha256": picture["asset_sha256"],
                        "size_bytes": picture["size_bytes"],
                    }
                    for picture in figure_pictures
                ],
            },
        )
        items.append(figure_item)
        caption_items: list[JsonObject] = []
        for caption_order, caption_sequence in enumerate(figure_spec["captions"], start=1):
            source = paragraphs[caption_sequence]
            observed = str(source["text"])
            language = "zh" if caption_order == 1 else "en"
            caption_item = content_item(
                student_id=student_id,
                field=fields["body.figure.caption"],
                sources=[source],
                occurrence=f"figure-{figure_number}-caption-{language}",
                order={
                    "scope": "body",
                    "sequence": caption_sequence,
                    "within_source": 4,
                },
                parent_content_id=figure_item["content_id"],
                observed_value=observed,
                normalized_value=caption_normalized(observed),
                extra={
                    "language": language,
                    "parallel_group_id": f"{student_id}-figure-{figure_number}-caption",
                    "figure_key": figure_item["figure_key"],
                    "source_caption_number": caption_source_number(observed),
                    "binding_basis": "source_sequence_adjacency_not_caption_number_identity",
                },
            )
            caption_items.append(caption_item)
            items.append(caption_item)
        caption_items[1]["translation_of"] = caption_items[0]["content_id"]

    if used_picture_ids != {value["source_object_ref"]["object_id"] for value in body_pictures}:
        raise ValueError(f"{student_id} body pictures are not mapped exactly once.")

    for table_number, table_spec in enumerate(config["body_tables"], start=1):
        sequence = int(table_spec["body_index"])
        source = tables[sequence]
        table_item = content_item(
            student_id=student_id,
            field=fields["body.table"],
            sources=[source],
            occurrence=f"table-{table_number}",
            order={"scope": "body", "sequence": sequence, "within_source": 3},
            parent_content_id=parent_at(sequence),
            extra={
                "table_key": f"table-{table_number:02d}",
                "source_caption_key": table_spec["source_key"],
                "structure": source["structure"],
            },
        )
        items.append(table_item)
        caption_items = []
        for caption_order, caption_sequence in enumerate(table_spec["captions"], start=1):
            caption_source = paragraphs[caption_sequence]
            observed = str(caption_source["text"])
            language = "zh" if caption_order == 1 else "en"
            caption_item = content_item(
                student_id=student_id,
                field=fields["body.table.caption"],
                sources=[caption_source],
                occurrence=f"table-{table_number}-caption-{language}",
                order={
                    "scope": "body",
                    "sequence": caption_sequence,
                    "within_source": 4,
                },
                parent_content_id=table_item["content_id"],
                observed_value=observed,
                normalized_value=caption_normalized(observed),
                extra={
                    "language": language,
                    "parallel_group_id": f"{student_id}-table-{table_number}-caption",
                    "table_key": table_item["table_key"],
                    "source_caption_number": caption_source_number(observed),
                    "source_position": "after_table"
                    if student_id == "student-001"
                    else "before_table",
                    "binding_basis": "source_sequence_adjacency_not_caption_number_identity",
                },
            )
            caption_items.append(caption_item)
            items.append(caption_item)
        caption_items[1]["translation_of"] = caption_items[0]["content_id"]

    for reference_number, sequence in enumerate(config["references"], start=1):
        source = paragraphs[sequence]
        if not source["text"]:
            raise ValueError(f"{student_id} empty reference at body sequence {sequence}.")
        items.append(
            content_item(
                student_id=student_id,
                field=fields["references.entries"],
                sources=[source],
                occurrence=f"reference-{reference_number}",
                order={"scope": "references", "sequence": reference_number},
                parent_content_id=None,
                observed_value=str(source["text"]),
            )
        )

    appendix_title_sequences = config["appendix_title"]
    appendix_parent: str | None = None
    if appendix_title_sequences:
        source = paragraphs[int(appendix_title_sequences[0])]
        appendix_title = content_item(
            student_id=student_id,
            field=fields["appendix.title"],
            sources=[source],
            occurrence="appendix-title",
            order={"scope": "appendix", "sequence": 1},
            parent_content_id=None,
            observed_value=str(source["text"]),
        )
        appendix_parent = appendix_title["content_id"]
        items.append(appendix_title)
    appendix_table_sequence = config["appendix_body_table"]
    if appendix_table_sequence is not None:
        source = tables[int(appendix_table_sequence)]
        items.append(
            content_item(
                student_id=student_id,
                field=fields["appendix.body"],
                sources=[source],
                occurrence="appendix-body",
                order={"scope": "appendix", "sequence": 2},
                parent_content_id=appendix_parent,
                extra={
                    "language": "mixed",
                    "structure": source["structure"],
                    "content_ref": {
                        "kind": "structured_table_inside_appendix",
                        "source_locator": source["source_locator"],
                    },
                },
            )
        )

    acknowledgement_sequences = config["acknowledgement"]
    if acknowledgement_sequences:
        sources = [paragraphs[index] for index in acknowledgement_sequences]
        observed = "\n\n".join(str(source["text"]) for source in sources)
        items.append(
            content_item(
                student_id=student_id,
                field=fields["acknowledgement.body"],
                sources=sources,
                occurrence="acknowledgement",
                order={"scope": "acknowledgement", "sequence": 1},
                parent_content_id=None,
                observed_value=observed,
                extra={
                    "source_completeness": (
                        "present_but_suspicious_fragment"
                        if student_id == "student-003"
                        else "present"
                    )
                },
            )
        )

    apply_source_order(items, objects)

    mapped: dict[str, list[str]] = defaultdict(list)
    items_by_field: dict[str, list[str]] = defaultdict(list)
    for item in items:
        items_by_field[item["field_id"]].append(item["content_id"])
        for reference in item["source_object_refs"]:
            mapped[reference["object_id"]].append(item["content_id"])

    field_results: list[JsonObject] = []
    for field in registry["fields"]:
        field_id = str(field["field_id"])
        content_ids = items_by_field.get(field_id, [])
        policy = str(field["student_extraction_policy"])
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

    object_by_id = {value["source_object_ref"]["object_id"]: value for value in objects}
    covered_children: dict[str, list[str]] = defaultdict(list)
    for object_id, content_ids in mapped.items():
        source = object_by_id[object_id]
        host_id = source.get("host_object_id")
        if host_id:
            covered_children[str(host_id)].extend(content_ids)

    coverage_objects: list[JsonObject] = []
    coverage_counts: dict[str, int] = defaultdict(int)
    for source in objects:
        object_id = source["source_object_ref"]["object_id"]
        status: str
        reason: str
        covered_by = mapped.get(object_id, [])
        if covered_by:
            status = "mapped"
            reason = "registered_content_item"
        elif covered_children.get(object_id):
            status = "covered_dependency"
            reason = "host_container_for_mapped_picture_asset"
            covered_by = covered_children[object_id]
        elif source["kind"] == "revision_ins":
            status = "covered_dependency"
            reason = "inserted_text_included_in_final_visible_paragraph_text"
            covered_by = mapped.get(str(source.get("host_object_id")), [])
        elif source["kind"] == "revision_del":
            status = "excluded"
            reason = "deleted_text_excluded_by_final_visible_revision_policy"
        elif source["kind"] == "comment":
            status = "excluded"
            reason = "review_comment_metadata_not_student_thesis_content"
        elif source["kind"] == "header_footer":
            status = "excluded"
            reason = "source_pagination_or_template_furniture"
        elif (
            source["kind"] == "paragraph"
            and int(source["body_sequence"]) in config["excluded_paragraphs"]
        ):
            status = "excluded"
            reason = config["excluded_paragraphs"][int(source["body_sequence"])]
        elif (
            source["kind"] == "table" and int(source["body_sequence"]) in config["excluded_tables"]
        ):
            status = "excluded"
            reason = config["excluded_tables"][int(source["body_sequence"])]
        elif (
            source["kind"] == "picture"
            and source["package_part"] in config["excluded_picture_parts"]
        ):
            status = "excluded"
            reason = config["excluded_picture_parts"][source["package_part"]]
        elif not str(source.get("text", "")).strip():
            status = "excluded"
            reason = "layout_separator_without_student_content"
        else:
            status = "unresolved"
            reason = "nonempty_source_object_without_registered_semantics_or_exclusion"
        coverage_counts[status] += 1
        coverage_objects.append(
            {
                "object_id": object_id,
                "kind": source["kind"],
                "source_locator": source["source_locator"],
                "status": status,
                "reason": reason,
                "covered_by_content_ids": sorted(set(covered_by)),
            }
        )

    candidate: JsonObject = {
        "schema_version": "docfit-student-content-extraction-gold/v2",
        "gold_id": f"{student_id}.extraction",
        "gold_revision": GOLD_REVISION,
        "status": "gold",
        "student_document_sha256": config["source_sha256"],
        "field_registry_ref": {
            "path": os.path.relpath(REGISTRY_V4, ASSET_ROOT / student_id),
            "registry_id": registry["registry_id"],
            "registry_version": registry["registry_version"],
            "sha256": registry_sha256,
            "status": "accepted",
        },
        "lineage": {
            "accepted_extraction_contract": {
                "student_id": "student-002",
                "gold_revision": "2026-08-12.r4",
                "registry_version": "0.3.0",
                "reuse": (
                    "field_projection_content_item_source_coverage_caption_numbering_"
                    "and_product_review_contract"
                ),
            },
            "student_inventory": {
                "path": "source-inventory.json",
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
            "scope": (
                "all_visible_main_story_content_plus_tracked_revisions_comments_and_nonempty_"
                "header_footer_parts"
            ),
            "missing_fields_have_no_positive_source_object_ids": True,
            "other_conversion_outputs_were_not_used_to_backfill_values": True,
        },
        "package_facts": inventory["package_summary"],
        "privacy": "restricted_student_content_not_for_public_ci_or_logs",
        "review_ref": "product-review.md",
        "accepted_at": REVIEWED_AT,
        "accepted_by": REVIEWER,
        "acceptance_evidence": [ACCEPTANCE_EVIDENCE, ORDER_REQUIREMENT_EVIDENCE],
    }
    validate_candidate(candidate, registry, inventory, config)
    return candidate


def validate_candidate(
    candidate: JsonObject,
    registry: JsonObject,
    inventory: JsonObject,
    config: JsonObject,
) -> None:
    fields = field_map(registry)
    if [value["field_id"] for value in candidate["field_results"]] != list(fields):
        raise ValueError("Candidate does not project all Registry fields once and in order.")
    items = candidate["items"]
    content_ids = [value["content_id"] for value in items]
    if len(content_ids) != len(set(content_ids)):
        raise ValueError("Candidate content IDs are not unique.")
    object_ids = {value["source_object_ref"]["object_id"] for value in inventory["objects"]}
    orders = [
        (int(value["source_order"]["block"]), int(value["source_order"]["inline"]))
        for value in items
    ]
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        raise ValueError("Candidate items do not have one complete, unique source order.")
    grouped: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        field_id = str(item["field_id"])
        if field_id not in fields:
            raise ValueError(f"Candidate uses unregistered field: {field_id}")
        if item["content_type"] != fields[field_id]["content_type"]:
            raise ValueError(f"Content type mismatch: {field_id}")
        if item.get("parent_content_id") and item["parent_content_id"] not in content_ids:
            raise ValueError(f"Stale parent content ID: {item['content_id']}")
        for reference in item["source_object_refs"]:
            if reference["object_id"] not in object_ids:
                raise ValueError(f"Stale source object ID: {item['content_id']}")
        occurrence_ids = [
            value["source_object_ref"]["object_id"] for value in item["source_occurrences"]
        ]
        if occurrence_ids != [value["object_id"] for value in item["source_object_refs"]]:
            raise ValueError(f"Source occurrence evidence is stale: {item['content_id']}")
        occurrence_orders = [
            (int(value["source_order"]["block"]), int(value["source_order"]["inline"]))
            for value in item["source_occurrences"]
        ]
        if occurrence_orders != sorted(occurrence_orders):
            raise ValueError(f"Source occurrences are not ordered: {item['content_id']}")
        counts[field_id] += 1
        grouped[field_id].append(item["content_id"])
    if dict(counts) != config["expected_counts"]:
        raise ValueError(f"Unexpected item counts: {dict(counts)}")
    for result in candidate["field_results"]:
        if result["content_ids"] != grouped.get(result["field_id"], []):
            raise ValueError(f"Stale field result IDs: {result['field_id']}")
    if candidate["unregistered_items"]:
        raise ValueError("Candidate cannot retain unregistered items.")
    if candidate["coverage"]["unresolved_count"]:
        unresolved = [
            value for value in candidate["coverage"]["objects"] if value["status"] == "unresolved"
        ]
        raise ValueError(f"Candidate has unresolved source objects: {unresolved[:5]}")


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def markdown_table(cells: list[list[str]]) -> str:
    if not cells:
        return "（空表）"
    width = max(len(row) for row in cells)
    rows = [row + [""] * (width - len(row)) for row in cells]
    header = rows[0]
    lines = [
        "| " + " | ".join(markdown_cell(value) for value in header) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(markdown_cell(value) for value in row) + " |" for row in rows[1:]
    )
    return "\n".join(lines)


def item_counts(candidate: JsonObject) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in candidate["items"]:
        counts[str(item["field_id"])] += 1
    return dict(counts)


def review_asset_outputs(
    student_id: str,
    candidate: JsonObject,
    inventory: JsonObject,
    asset_bytes: dict[str, bytes],
) -> tuple[list[JsonObject], dict[str, bytes]]:
    object_by_id = {
        value["source_object_ref"]["object_id"]: value for value in inventory["objects"]
    }
    outputs: dict[str, bytes] = {}
    manifest_entries: list[JsonObject] = []
    figures = [value for value in candidate["items"] if value["field_id"] == "body.figure"]
    for figure_number, figure in enumerate(figures, start=1):
        asset_refs = figure["asset_refs"]
        for asset_number, asset in enumerate(asset_refs, start=1):
            source = object_by_id[asset["source_object_id"]]
            suffix = Path(str(source["package_part"])).suffix.lower() or ".bin"
            panel = "" if len(asset_refs) == 1 else f"-panel-{chr(96 + asset_number)}"
            filename = f"figure-{figure_number:02d}{panel}{suffix}"
            content = asset_bytes[asset["source_object_id"]]
            outputs[filename] = content
            manifest_entries.append(
                {
                    "path": f"review-assets/{filename}",
                    "sha256": sha256_bytes(content),
                    "role": "human_review_figure_evidence",
                    "figure_key": figure["figure_key"],
                }
            )
    return manifest_entries, outputs


def heading_tree(candidate: JsonObject) -> str:
    lines: list[str] = []
    for item in candidate["items"]:
        field_id = str(item["field_id"])
        if not field_id.startswith("body.heading.level"):
            continue
        level = int(field_id.rsplit("level", 1)[1])
        label = item.get("visible_source_label") or item.get("observed_value")
        lines.append(f"{'  ' * (level - 1)}- {label}")
    return "\n".join(lines)


def field_result_table(candidate: JsonObject, registry: JsonObject) -> str:
    by_id = {value["field_id"]: value for value in candidate["field_results"]}
    counts = item_counts(candidate)
    lines = [
        "| # | Registry 字段 | 含义 | 结果 | 数量 |",
        "|---:|---|---|---|---:|",
    ]
    for index, field in enumerate(registry["fields"], start=1):
        field_id = str(field["field_id"])
        result = by_id[field_id]
        status = {
            "present": "已提取",
            "missing": "原文未发现",
            "not_applicable": "不适用学生提取",
        }[result["status"]]
        lines.append(
            f"| {index} | `{field_id}` | {markdown_cell(field['meaning'])} | {status} | {counts.get(field_id, 0)} |"
        )
    return "\n".join(lines)


def source_context(candidate: JsonObject, item: JsonObject) -> tuple[str, str, str]:
    body_items = [
        value
        for value in candidate["items"]
        if str(value["field_id"]).startswith("body.") and value.get("observed_value")
    ]
    body_items.sort(
        key=lambda value: (
            int(value["source_order"]["block"]),
            int(value["source_order"]["inline"]),
        )
    )
    index = body_items.index(item)
    previous = body_items[index - 1].get("observed_value", "") if index else "（正文起点）"
    following = (
        body_items[index + 1].get("observed_value", "")
        if index + 1 < len(body_items)
        else "（正文终点）"
    )
    parent_id = item.get("parent_content_id")
    parent = next((value for value in candidate["items"] if value["content_id"] == parent_id), None)
    parent_text = (
        parent.get("visible_source_label") or parent.get("observed_value") if parent else "正文"
    )
    return str(parent_text), str(previous), str(following)


def product_review(
    student_id: str,
    config: JsonObject,
    candidate: JsonObject,
    registry: JsonObject,
    registry_sha256: str,
    inventory: JsonObject,
    review_assets: list[JsonObject],
) -> bytes:
    counts = item_counts(candidate)
    present = sum(result["status"] == "present" for result in candidate["field_results"])
    missing = sum(result["status"] == "missing" for result in candidate["field_results"])
    not_applicable = sum(
        result["status"] == "not_applicable" for result in candidate["field_results"]
    )
    coverage = candidate["coverage"]["status_counts"]
    figures = [value for value in candidate["items"] if value["field_id"] == "body.figure"]
    figure_captions = [
        value for value in candidate["items"] if value["field_id"] == "body.figure.caption"
    ]
    tables = [value for value in candidate["items"] if value["field_id"] == "body.table"]
    table_captions = [
        value for value in candidate["items"] if value["field_id"] == "body.table.caption"
    ]
    references = [
        value for value in candidate["items"] if value["field_id"] == "references.entries"
    ]
    list_items = [
        value for value in candidate["items"] if value["field_id"] == "body.numbered_list_item"
    ]
    front_items = [
        value
        for value in candidate["items"]
        if int(value["source_order"]["block"]) < int(config["body_range"][0])
    ]
    asset_path_by_figure: dict[str, list[str]] = defaultdict(list)
    for asset in review_assets:
        asset_path_by_figure[asset["figure_key"]].append(asset["path"])

    lines = [
        f"# {student_id.replace('-', ' ').title()} Extraction Gold 产品验收记录",
        "",
        f"- 评审对象：{student_id} 用户内容提取 Gold",
        f"- Gold revision：`{GOLD_REVISION}`",
        "- 当前状态：`ACCEPTED / GOLD`",
        f"- 评审人：{REVIEWER}",
        f"- 评审日期：`{REVIEWED_AT}`",
        f"- 验收原话：{ACCEPTANCE_EVIDENCE}",
        f"- 顺序补充要求：{ORDER_REQUIREMENT_EVIDENCE}",
        f"- 用户源 SHA-256：`{config['source_sha256']}`",
        f"- Registry：`docfit.thesis.content_fields@0.4.0`（accepted），`{registry_sha256}`",
        f"- [打开学生原论文](../../../student-content-real-{student_id}.docx)",
        "- [查看机器 Gold](student-content.gold.json)",
        "",
        "## 1. 这份文档用来决定什么",
        "",
        "这是本轮人工核对结果与 Gold 晋升记录，不需要阅读或编辑 YAML。机器文件证明字段、引用、",
        "顺序和覆盖闭包；语义分类、复杂对象关系和异常源内容已经产品负责人确认。",
        "本轮不决定内容放进哪所学校模板，也不验收最终 Word。",
        "",
        "## 2. 机器已经确认的事实",
        "",
        "| 检查 | 结果 |",
        "|---|---:|",
        "| Registry 字段总数 | 54，ID 唯一 |",
        f"| 字段级结果 | {present} 已提取、{missing} 原文未发现、{not_applicable} 不适用学生提取 |",
        f"| 内容实例 | {len(candidate['items'])} |",
        "| 内容顺序 | `items` 按唯一 `source_order.block + inline` 严格递增 |",
        "| 字段摘要是否可改顺序 | 否；`field_results` 仅为派生索引 |",
        f"| 源对象覆盖 | {coverage.get('mapped', 0)} 直接映射、{coverage.get('covered_dependency', 0)} 依赖覆盖、{coverage.get('excluded', 0)} 显式排除 |",
        "| 未决源对象 | 0 |",
        "| unregistered | 0 |",
        f"| 图 / 源图片资产 / 表 / 参考文献 | {len(figures)} / {sum(len(value['asset_refs']) for value in figures)} / {len(tables)} / {len(references)} |",
        "",
        "机器闭包与产品验收均已通过；本文件对应的 Extraction 已晋升 Gold。",
        "",
        "## 3. 产品决策总表",
        "",
        "| 决策 | 需要确认 | 当前建议 |",
        "|---|---|---|",
        "| D1 | Registry v0.4 通用增量 | 接受多资产图、可选源编号题注、结构配对与修订最终视图 |",
        "| D2 | 封面、摘要与复合字段 | 保留原文，不从转换稿补值；只做有证据的标签剥离/复合字段抽取 |",
        "| D3 | 正文标题树、段落和列表 | 按完整上下文接受当前层级；保留显式或 Word 自动列表特征 |",
        "| D4 | 图、源图片资产和双语图题 | 以结构/相邻关系配对，源编号仅作追溯，目标模板重新编号 |",
        "| D5 | 数据表、双语表题与附录表 | 布局图表不重复算表；题注前缀从规范值去除 |",
        "| D6 | 参考文献边界 | 每个非空文献段落作为一条，保留原文顺序 |",
        "| D7 | 后置内容 | 按原文保留附录/致谢；不擅自补全残缺文本 |",
        "| D8 | 排除项与 Word 修订/批注 | 模板固定文字、目录缓存、删除文本、批注和页码不作为用户论文内容 |",
        "| D9 | 隐私与 Gold 晋升 | 保持受限；只有全部决定通过后再改状态和文件名 |",
        "",
        "## 4. D1：Registry v0.4 通用增量",
        "",
        "Student 002 已验收的 v0.3 和 Gold 保持不可变。本次没有新增字段，也没有修改 54 个",
        "canonical ID；v0.4 只补齐扩样暴露出的通用承载规则：",
        "",
        "1. 一张语义图可以绑定一个或多个源图片资产；共享同一题注组的并排/多面板图片不拆成多张语义图；",
        "2. 图题/表题的源类型标签后可以没有编号，规范值仍去掉类型标签与可选编号；",
        "3. 题注以源结构、邻接和版面证据绑定，源编号不作为唯一身份；编号冲突必须展示给 Human；",
        "4. Word 修订按 final-visible 视图抽取：插入文字进入内容，删除文字只保留审计证据，批注属于评阅元数据；",
        "5. Word 自动生成的括号列表编号与显式括号编号具有同等列表证据。",
        "",
        "- [x] 接受 D1 当前建议并允许 v0.4 晋升",
        "- [ ] 修改 D1，具体修改：",
        "- [ ] 阻止 D1",
        "- 评审备注：",
        "",
        "## 5. D2：封面、摘要与复合字段",
        "",
    ]
    for item in front_items:
        observed = markdown_cell(item.get("observed_value", ""))
        normalized = markdown_cell(item.get("normalized_value", "（与原文相同）"))
        lines.append(f"- `{item['field_id']}`：原文“{observed}”；规范值“{normalized}”")
        observations = item.get("source_occurrences", [])
        if observations:
            occurrence_text = "；".join(
                f"{index}. [{value['source_order']['block']}, {value['source_order']['inline']}] "
                f"{markdown_cell(value['observed_text'])}"
                for index, value in enumerate(observations, start=1)
            )
            lines.append(f"  - 来源共 {len(observations)} 处：{occurrence_text}")
    if student_id == "student-001":
        lines.extend(
            [
                "",
                "Student 001 的封面是空白学校表单，姓名、学号、学院、专业、导师、职称和日期均",
                "没有填写，因此保持 missing；不能从文件名、其他转换稿或论文致谢反推。",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "重点核对：`2022级种子（2）班`只进入 `author.cohort_class`，没有把“种子”猜成",
                "`author.major`；英文院系规范值保留源拼写 `Agrivulture`，不自动改成 `Agriculture`；",
                "英文摘要页的 `Title of Graduation Paper` 是未填写模板占位符，未覆盖封面的真实英文题目。",
            ]
        )
    lines.extend(
        [
            "",
            "- [x] 接受 D2 当前提取、规范值和 missing 判断",
            "- [ ] 修改 D2，具体字段与正确值：",
            "- [ ] 阻止 D2",
            "- 评审备注：",
            "",
            "## 6. D3：正文层级、段落与数字列表",
            "",
            f"Gold 包含 {counts.get('body.heading.level1', 0)}/{counts.get('body.heading.level2', 0)}/{counts.get('body.heading.level3', 0)} 个一/二/三级标题、{counts.get('body.paragraph', 0)} 个正文段落和 {len(list_items)} 个数字列表项。完整标题树如下：",
            "正文内容项同时按冻结 Word 的 `source_order.block + source_order.inline` 排列；字段分类、父子关系和 `field_results` 都不能改变这一数组顺序。",
            "",
            heading_tree(candidate),
            "",
        ]
    )
    if list_items:
        lines.append("数字列表逐项上下文：")
        lines.append("")
        for index, item in enumerate(list_items, start=1):
            parent, previous, following = source_context(candidate, item)
            lines.extend(
                [
                    f"### L{index}. {item['observed_value']}",
                    "",
                    f"- 所属上级：{parent}",
                    f"- 前一条可见内容：{previous}",
                    f"- 后一条可见内容：{following}",
                    f"- 分类证据：`{item['classification_basis']}`",
                    "",
                ]
            )
    else:
        lines.extend(["原文没有数字列表项；没有为了凑字段把三级标题或普通段落改成列表。", ""])
    lines.extend(
        [
            "- [x] 接受 D3 当前标题树、正文顺序和列表分类",
            "- [ ] 修改 D3，错误项及完整上下文：",
            "- [ ] 阻止 D3",
            "- 评审备注：",
            "",
            "## 7. D4：图片、组合关系与双语图题",
            "",
            "`observed_value` 保留源“图/Fig./Figure + 编号”，`normalized_value` 只保留题名正文；",
            "填写时由目标模板重新生成标签与编号。下列配对按源结构和邻接顺序完成，不能仅凭",
            "源编号，因为原稿存在中英文编号不一致。",
            "",
        ]
    )
    caption_by_parent: dict[str, list[JsonObject]] = defaultdict(list)
    for caption in figure_captions:
        caption_by_parent[str(caption["parent_content_id"])].append(caption)
    for index, figure in enumerate(figures, start=1):
        lines.extend(
            [
                f"### F{index}. {figure['figure_key']}（源中文键 {figure['source_caption_key']}）",
                "",
                f"- 组合：`{figure['composition']}`；源图片资产 {len(figure['asset_refs'])} 个",
            ]
        )
        for asset_path in asset_path_by_figure[figure["figure_key"]]:
            filename = Path(asset_path).name
            lines.extend([f"![{figure['figure_key']} {filename}](review-assets/{filename})", ""])
        for caption in sorted(
            caption_by_parent[figure["content_id"]], key=lambda value: value["language"] == "en"
        ):
            lines.append(
                f"- {caption['language']} 原文：{caption['observed_value']}；规范值：{caption['normalized_value']}"
            )
        paired_captions = sorted(
            caption_by_parent[figure["content_id"]],
            key=lambda value: value["language"] == "en",
        )
        zh_number = paired_captions[0].get("source_caption_number")
        en_number = paired_captions[1].get("source_caption_number")
        number_status = "一致" if zh_number == en_number else "不一致，按邻接配对并等待本项确认"
        lines.append(f"- 源编号检查：中文 `{zh_number}` / 英文 `{en_number}` → **{number_status}**")
        lines.append("")
    lines.extend(
        [
            "- [x] 接受 D4 的语义图分组、资产和双语题注配对",
            "- [ ] 修改 D4，错误图组/题注：",
            "- [ ] 阻止 D4",
            "- 评审备注：",
            "",
            "## 8. D5：数据表、双语表题与附录表",
            "",
        ]
    )
    table_caption_by_parent: dict[str, list[JsonObject]] = defaultdict(list)
    for caption in table_captions:
        table_caption_by_parent[str(caption["parent_content_id"])].append(caption)
    for index, table in enumerate(tables, start=1):
        structure = table["structure"]
        lines.extend(
            [
                f"### T{index}. {table['table_key']}（源键 {table['source_caption_key']}，{structure['row_count']}×{structure['column_count']}）",
                "",
            ]
        )
        for caption in sorted(
            table_caption_by_parent[table["content_id"]],
            key=lambda value: value["language"] == "en",
        ):
            lines.append(
                f"- {caption['language']} 原文：{caption['observed_value']}；规范值：{caption['normalized_value']}；源位置：`{caption['source_position']}`"
            )
        paired_captions = sorted(
            table_caption_by_parent[table["content_id"]],
            key=lambda value: value["language"] == "en",
        )
        zh_number = paired_captions[0].get("source_caption_number")
        en_number = paired_captions[1].get("source_caption_number")
        number_status = (
            "双方均无编号"
            if zh_number is None and en_number is None
            else "一致"
            if zh_number == en_number
            else "不一致"
        )
        lines.append(f"- 源编号检查：中文 `{zh_number}` / 英文 `{en_number}` → **{number_status}**")
        lines.extend(["", markdown_table(structure["cells"]), ""])
    appendix_items = [value for value in candidate["items"] if value["field_id"] == "appendix.body"]
    if appendix_items:
        appendix = appendix_items[0]
        lines.extend(
            [
                "### 附录结构表",
                "",
                "附录中的引物表由 `appendix.body` 承载，不重复伪装成正文章节内的 `body.table`。",
                "",
                markdown_table(appendix["structure"]["cells"]),
                "",
            ]
        )
    if student_id == "student-003":
        lines.extend(
            [
                "六个 1×2 无文本表格只用于并排两张图片，已经归入六个多资产语义图，未重复计入数据表。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "前三个 PCR 表的中英文题注在源中只有“表/Table”标签、没有编号，且题注位于表后；",
                "v0.4 仍把标签从规范值去掉，由目标模板在目标位置生成完整编号。",
                "",
            ]
        )
    lines.extend(
        [
            "- [x] 接受 D5 的表格边界、题注配对和规范值",
            "- [ ] 修改 D5：",
            "- [ ] 阻止 D5",
            "- 评审备注：",
            "",
            "## 9. D6：参考文献",
            "",
            f"Gold 把“参考文献”作为结构标题排除，将其后的 {len(references)} 个非空段落逐段提取为 `references.entries`：",
            "",
        ]
    )
    for index, reference in enumerate(references, start=1):
        lines.append(f"{index}. {reference['observed_value']}")
    lines.extend(
        [
            "",
            "- [x] 接受 D6 的边界、拆分和顺序",
            "- [ ] 修改 D6，错误条目：",
            "- [ ] 阻止 D6",
            "- 评审备注：",
            "",
            "## 10. D7：附录与致谢",
            "",
        ]
    )
    appendix_title = [
        value for value in candidate["items"] if value["field_id"] == "appendix.title"
    ]
    acknowledgement = [
        value for value in candidate["items"] if value["field_id"] == "acknowledgement.body"
    ]
    lines.append(
        f"- 附录：{appendix_title[0]['observed_value'] if appendix_title else '原文未发现'}"
    )
    lines.append(
        f"- 致谢原文：{acknowledgement[0]['observed_value'] if acknowledgement else '原文未发现'}"
    )
    if student_id == "student-003":
        lines.append(
            "- 完整性判断：源致谢只有“本论文是”，仍按原文保留为 `present_but_suspicious_fragment`；不补写、不改成 missing。"
        )
    lines.extend(
        [
            "",
            "- [x] 接受 D7 当前后置内容和完整性标记",
            "- [ ] 修改 D7：",
            "- [ ] 阻止 D7",
            "- 评审备注：",
            "",
            "## 11. D8：排除项、修订与批注",
            "",
            f"覆盖清单共 {candidate['coverage']['object_count']} 个对象；{coverage.get('excluded', 0)} 个显式排除，0 个未决。",
            "模板固定声明、空签名线、结构标题、空白分隔、学校标识、目录缓存和页码不作为",
            "学生论文内容，但均在覆盖清单中有明确理由。",
            "",
        ]
    )
    facts = inventory["package_summary"]
    if facts["revision_insert_objects"] or facts["revision_delete_objects"]:
        lines.extend(
            [
                f"源文档含 {facts['revision_insert_objects']} 个插入修订、{facts['revision_delete_objects']} 个删除修订和 {facts['comment_objects']} 条批注。",
                "Gold 使用 Word final-visible 视图：插入文字进入段落，删除文字不进入内容，批注不进入用户论文语义。",
                "批注原文如下，仅用于确认它们是评阅元数据：",
                "",
            ]
        )
        for source in inventory["objects"]:
            if source["kind"] == "comment":
                lines.append(f"- comment {source.get('comment_id')}：{source['text']}")
        lines.append("")
    lines.extend(
        [
            "- [x] 接受 D8 的排除边界和 final-visible 修订视图",
            "- [ ] 修改 D8，需要恢复或排除的对象：",
            "- [ ] 阻止 D8",
            "- 评审备注：",
            "",
            "## 12. D9：隐私与晋升",
            "",
            "源 Word、Gold JSON、本文、参考文献和图片都是真实学生内容，只能保存在当前受限",
            "测试资产目录，不得进入公开 CI 或公共日志。D1–D9 已全部通过，机器 Gold、review 和 hash 已同步。",
            "",
            "- [x] 接受 D9",
            "- [ ] 修改 D9：",
            "- [ ] 阻止 D9",
            "- 评审备注：",
            "",
            "## 13. 产品负责人最终签署",
            "",
            "- Registry v0.4： [x] 接受  [ ] 修改后接受  [ ] 阻止",
            f"- {student_id} Extraction： [x] 接受并晋升 Gold  [ ] 修改后复审  [ ] 阻止",
            "- 是否允许后续模板填写映射进入独立准备： [x] 是  [ ] 否",
            f"- 评审人：{REVIEWER}",
            f"- 评审日期：{REVIEWED_AT}",
            f"- 总体结论：{ACCEPTANCE_EVIDENCE}；并按补充要求加入可机器验证的源顺序。",
            "",
            "## 附录 A：54 字段完整结果",
            "",
            field_result_table(candidate, registry),
            "",
        ]
    )
    return ("\n".join(lines).rstrip() + "\n").encode()


def review_yaml(
    student_id: str,
    gold_sha256: str,
    inventory_sha256: str,
    product_review_sha256: str,
    registry_sha256: str,
    candidate: JsonObject,
) -> JsonObject:
    facts = candidate["package_facts"]
    return {
        "schema_version": "docfit-human-review/v1",
        "artifact": f"{student_id}.extraction",
        "gold_revision": GOLD_REVISION,
        "status": "accepted",
        "registry_review": {
            "registry_version": "0.4.0",
            "sha256": registry_sha256,
            "status": "accepted",
        },
        "human_review_document": {
            "path": "product-review.md",
            "sha256": product_review_sha256,
            "role": "sole_human_review_interface",
        },
        "machine_artifacts": {
            "gold": {"path": "student-content.gold.json", "sha256": gold_sha256},
            "inventory": {"path": "source-inventory.json", "sha256": inventory_sha256},
        },
        "machine_checks": [
            {"check": "source_sha256_bound", "status": "PASS"},
            {"check": "all_54_registry_fields_projected_once", "status": "PASS"},
            {"check": "registered_field_ids_only", "status": "PASS"},
            {"check": "unregistered_items_empty", "status": "PASS"},
            {
                "check": f"all_{candidate['coverage']['object_count']}_source_objects_accounted_for",
                "status": "PASS",
            },
            {"check": "source_coverage_unresolved_zero", "status": "PASS"},
            {"check": "items_source_order_complete_unique_and_ascending", "status": "PASS"},
            {"check": "source_occurrences_preserve_physical_order", "status": "PASS"},
            {"check": "field_results_not_order_authority", "status": "PASS"},
            {
                "check": "caption_values_exclude_generated_type_and_optional_number_prefix",
                "status": "PASS",
            },
            {
                "check": "tracked_revision_final_visible_view",
                "status": "PASS"
                if facts["revision_insert_objects"] or facts["revision_delete_objects"]
                else "NOT_APPLICABLE",
            },
        ],
        "human_review_queue": [
            {"decision_id": f"D{index}", "status": "accepted", "review_in": "product-review.md"}
            for index in range(1, 10)
        ],
        "reviewer": REVIEWER,
        "reviewed_at": REVIEWED_AT,
        "conclusion": "accepted_and_promoted_to_gold",
        "acceptance_evidence": [ACCEPTANCE_EVIDENCE, ORDER_REQUIREMENT_EVIDENCE],
    }


def package_manifest(
    student_id: str,
    config: JsonObject,
    registry_sha256: str,
    gold_sha256: str,
    inventory_sha256: str,
    product_review_sha256: str,
    review_sha256: str,
    review_assets: list[JsonObject],
) -> JsonObject:
    return {
        "schema_version": "docfit-extraction-gold-manifest/v1",
        "student_id": student_id,
        "status": "gold",
        "gold_revision": GOLD_REVISION,
        "student_source": {
            "path": f"../../../student-content-real-{student_id}.docx",
            "sha256": config["source_sha256"],
        },
        "field_registry_ref": {
            "path": "../../../../../docs/plans/docfit-content-field-registry/content-fields-v0.4.yaml",
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.4.0",
            "sha256": registry_sha256,
            "status": "accepted",
        },
        "artifacts": [
            {"path": "student-content.gold.json", "sha256": gold_sha256},
            {"path": "source-inventory.json", "sha256": inventory_sha256},
            {
                "path": "product-review.md",
                "sha256": product_review_sha256,
                "role": "human_product_review",
            },
            {"path": "review.yaml", "sha256": review_sha256},
            *review_assets,
        ],
        "privacy": "restricted_student_content_not_for_public_ci_or_logs",
        "accepted_at": REVIEWED_AT,
        "accepted_by": REVIEWER,
    }


def materialize_student(
    student_id: str,
    config: JsonObject,
    registry: JsonObject,
    registry_sha256: str,
    *,
    check: bool,
) -> JsonObject:
    output_dir = ASSET_ROOT / student_id
    inventory, asset_bytes = inventory_docx(student_id, config)
    inventory_content = json_bytes(inventory)
    inventory_sha256 = sha256_bytes(inventory_content)
    write_or_check(output_dir / "source-inventory.json", inventory_content, check=check)

    candidate = build_candidate(student_id, config, registry, registry_sha256, inventory)
    candidate["lineage"]["student_inventory"]["sha256"] = inventory_sha256
    candidate_content = json_bytes(candidate)
    candidate_sha256 = sha256_bytes(candidate_content)
    write_or_check(output_dir / "student-content.gold.json", candidate_content, check=check)

    review_assets, asset_outputs = review_asset_outputs(
        student_id, candidate, inventory, asset_bytes
    )
    for filename, content in asset_outputs.items():
        write_or_check(output_dir / "review-assets" / filename, content, check=check)

    product_review_content = product_review(
        student_id,
        config,
        candidate,
        registry,
        registry_sha256,
        inventory,
        review_assets,
    )
    product_review_sha256 = sha256_bytes(product_review_content)
    write_or_check(output_dir / "product-review.md", product_review_content, check=check)

    review = review_yaml(
        student_id,
        candidate_sha256,
        inventory_sha256,
        product_review_sha256,
        registry_sha256,
        candidate,
    )
    review_content = yaml_bytes(review)
    review_sha256 = sha256_bytes(review_content)
    write_or_check(output_dir / "review.yaml", review_content, check=check)

    manifest = package_manifest(
        student_id,
        config,
        registry_sha256,
        candidate_sha256,
        inventory_sha256,
        product_review_sha256,
        review_sha256,
        review_assets,
    )
    manifest_content = yaml_bytes(manifest)
    write_or_check(output_dir / "manifest.yaml", manifest_content, check=check)
    return {
        "student_id": student_id,
        "gold_sha256": candidate_sha256,
        "inventory_sha256": inventory_sha256,
        "product_review_sha256": product_review_sha256,
        "review_sha256": review_sha256,
        "manifest_sha256": sha256_bytes(manifest_content),
        "item_count": len(candidate["items"]),
        "source_object_count": candidate["coverage"]["object_count"],
        "review_asset_count": len(review_assets),
    }


def materialize(*, check: bool) -> None:
    registry = registry_v4_snapshot()
    registry_content = yaml_bytes(registry)
    registry_sha256 = sha256_bytes(registry_content)
    write_or_check(REGISTRY_V4, registry_content, check=check)
    summaries = [
        materialize_student(
            student_id,
            config,
            registry,
            registry_sha256,
            check=check,
        )
        for student_id, config in STUDENTS.items()
    ]
    print(
        json.dumps(
            {
                "registry_v0.4_sha256": registry_sha256,
                "status": "checked" if check else "materialized",
                "students": summaries,
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
        help="Fail if any generated Gold artifact is missing or stale.",
    )
    args = parser.parse_args()
    materialize(check=args.check)


if __name__ == "__main__":
    main()

"""Build deterministic, synthetic DOCX fixtures for template-extraction Eval.

The builder never reads or writes formal Gold cases. It creates only the S00-S13
fixtures below the explicitly selected output root.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import yaml

FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


@dataclass(frozen=True)
class DocumentOptions:
    label: str = "姓名："
    label_size_pt: float = 12
    include_slot: bool = True
    slot_field_id: str = "author.name.zh"
    slot_tag: str = "docfit.cover.student_name"
    slot_text: str = "【姓名】"
    include_extra_slot: bool = False
    duplicate_anchor: bool = False
    forbidden_text: str | None = None
    include_image: bool = False
    include_unsupported: bool = False
    include_table: bool = False
    include_semantic_objects: bool = False


@dataclass(frozen=True)
class SampleDefinition:
    sample_id: str
    description: str
    expected_verdict: str
    gold: DocumentOptions
    actual: DocumentOptions
    boundary_override: str | None = None
    invalid_actual: bool = False


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _run(text: str, *, size_pt: float | None = None) -> str:
    preserve = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    properties = ""
    if size_pt is not None:
        half_points = int(round(size_pt * 2))
        properties = f'<w:rPr><w:sz w:val="{half_points}"/><w:szCs w:val="{half_points}"/></w:rPr>'
    return f"<w:r>{properties}<w:t{preserve}>{_xml_escape(text)}</w:t></w:r>"


def _slot(field_id: str, tag: str, text: str, internal_id: int) -> str:
    return (
        "<w:sdt>"
        "<w:sdtPr>"
        f'<w:alias w:val="{_xml_escape(field_id)}"/>'
        f'<w:tag w:val="{_xml_escape(tag)}"/>'
        f'<w:id w:val="{internal_id}"/>'
        "<w:text/>"
        "</w:sdtPr>"
        f"<w:sdtContent>{_run(text)}</w:sdtContent>"
        "</w:sdt>"
    )


def _image_paragraph() -> str:
    return (
        "<w:p><w:r><w:drawing><wp:inline>"
        '<wp:extent cx="9525" cy="9525"/>'
        '<wp:docPr id="1" name="Synthetic one-pixel image"/>'
        "<a:graphic><a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
        "<pic:pic><pic:nvPicPr><pic:cNvPr id=\"1\" name=\"tiny.png\"/>"
        "<pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed=\"rIdImage\"/>"
        "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
        "<pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"9525\" cy=\"9525\"/>"
        "</a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></pic:spPr>"
        "</pic:pic></a:graphicData></a:graphic>"
        "</wp:inline></w:drawing></w:r></w:p>"
    )


def _table() -> str:
    return (
        "<w:tbl><w:tblPr><w:tblW w:w=\"5000\" w:type=\"dxa\"/></w:tblPr>"
        "<w:tblGrid><w:gridCol w:w=\"2500\"/><w:gridCol w:w=\"2500\"/></w:tblGrid>"
        "<w:tr><w:tc><w:tcPr><w:gridSpan w:val=\"2\"/></w:tcPr><w:p>"
        f"{_run('合并表头')}</w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p>"
        f"{_run('A')}</w:p></w:tc><w:tc><w:p>{_run('B')}</w:p></w:tc></w:tr></w:tbl>"
    )


def _semantic_objects_paragraph() -> str:
    return (
        "<w:p>"
        '<w:bookmarkStart w:id="7" w:name="SyntheticBookmark"/>'
        f"{_run('书签内容')}"
        '<w:bookmarkEnd w:id="7"/>'
        '<w:fldSimple w:instr=" DATE ">'
        f"{_run('2026-08-06')}</w:fldSimple>"
        "<m:oMath><m:r><m:t>x+1</m:t></m:r></m:oMath>"
        "</w:p>"
    )


def _document_xml(options: DocumentOptions) -> bytes:
    first_paragraph = ["<w:p>", _run(options.label, size_pt=options.label_size_pt)]
    if options.include_slot:
        first_paragraph.append(
            _slot(options.slot_field_id, options.slot_tag, options.slot_text, 1001)
        )
    first_paragraph.append("</w:p>")

    body = ["".join(first_paragraph)]
    if options.duplicate_anchor:
        body.append(f"<w:p>{_run(options.label)}</w:p>")
    if options.include_extra_slot:
        body.append(
            "<w:p>"
            + _run("学号：")
            + _slot("author.student_id", "docfit.cover.student_id", "【学号】", 1002)
            + "</w:p>"
        )
    if options.forbidden_text is not None:
        body.append(f"<w:p>{_run(options.forbidden_text)}</w:p>")
    if options.include_image:
        body.append(_image_paragraph())
    if options.include_unsupported:
        body.append('<w:altChunk r:id="rIdAlt"/>')
    if options.include_table:
        body.append(_table())
    if options.include_semantic_objects:
        body.append(_semantic_objects_paragraph())
    body.append(
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        f"<w:body>{''.join(body)}</w:body></w:document>"
    )
    return document.encode("utf-8")


def _styles_xml() -> bytes:
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NS}">'
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/>'
        '<w:sz w:val="24"/><w:szCs w:val="24"/><w:color w:val="000000"/>'
        "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
        '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
        "</w:pPr></w:pPrDefault></w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        "</w:styles>"
    )
    return styles.encode("utf-8")


def _content_types(options: DocumentOptions) -> bytes:
    defaults = [
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    if options.include_image:
        defaults.append('<Default Extension="png" ContentType="image/png"/>')
    if options.include_unsupported:
        defaults.append('<Default Extension="html" ContentType="text/html"/>')
    value = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{CONTENT_TYPES_NS}">'
        + "".join(defaults)
        + '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )
    return value.encode("utf-8")


def _package_relationships() -> bytes:
    value = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{REL_NS}">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    return value.encode("utf-8")


def _document_relationships(options: DocumentOptions) -> bytes:
    relationships = [
        '<Relationship Id="rIdStyles" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    ]
    if options.include_image:
        relationships.append(
            '<Relationship Id="rIdImage" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="media/tiny.png"/>'
        )
    if options.include_unsupported:
        relationships.append(
            '<Relationship Id="rIdAlt" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk" '
            'Target="afchunk.html"/>'
        )
    value = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{REL_NS}">{"".join(relationships)}</Relationships>'
    )
    return value.encode("utf-8")


def _zip_write(archive: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def write_docx(path: Path, options: DocumentOptions, *, omit_main_document: bool = False) -> None:
    entries: dict[str, bytes] = {
        "[Content_Types].xml": _content_types(options),
        "_rels/.rels": _package_relationships(),
        "word/_rels/document.xml.rels": _document_relationships(options),
        "word/styles.xml": _styles_xml(),
    }
    if not omit_main_document:
        entries["word/document.xml"] = _document_xml(options)
    if options.include_image:
        entries["word/media/tiny.png"] = TINY_PNG
    if options.include_unsupported:
        entries["word/afchunk.html"] = b"<html><body>Unsupported visible object</body></html>"
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as archive:
        for name in sorted(entries):
            _zip_write(archive, name, entries[name])


def validate_docx_package(path: Path, *, require_main_document: bool = True) -> None:
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"corrupt ZIP entry in {path}")
        names = set(archive.namelist())
        required = {"[Content_Types].xml", "_rels/.rels"}
        if require_main_document:
            required.add("word/document.xml")
        missing = required - names
        if missing:
            raise ValueError(f"missing required DOCX parts in {path}: {sorted(missing)}")
        for name in names:
            if name.endswith((".xml", ".rels")):
                ElementTree.fromstring(archive.read(name))


def _registry() -> dict[str, Any]:
    return {
        "schema_version": "docfit-content-field-registry/v0.1",
        "registry_id": "docfit.thesis.content_fields",
        "registry_version": "0.1.0",
        "status": "development_baseline",
        "open_world": True,
        "description": "Synthetic Registry fixture; not production Registry or Gold.",
        "fields": [
            {
                "field_id": "author.name.zh",
                "label": "作者中文姓名",
                "meaning": "合成作者姓名字段。",
                "content_type": "text",
                "cardinality": "one",
                "language": "zh",
            },
            {
                "field_id": "author.student_id",
                "label": "学号",
                "meaning": "合成学号字段。",
                "content_type": "text",
                "cardinality": "one",
            },
        ],
    }


def _style(size_pt: float = 12) -> dict[str, Any]:
    return {
        "font": {
            "east_asia": "宋体",
            "latin": "Times New Roman",
            "size_pt": size_pt,
            "bold": False,
            "italic": False,
            "color": "000000",
        },
        "paragraph": {
            "alignment": None,
            "line_spacing_rule": "auto",
            "line_spacing_pt": 12,
            "space_before_pt": 0,
            "space_after_pt": 0,
        },
        "container": {},
        "page": {
            "page_width_pt": 595.3,
            "page_height_pt": 841.9,
            "margin_top_pt": 72,
            "margin_bottom_pt": 72,
        },
    }


def _locator_for_label(options: DocumentOptions) -> dict[str, Any]:
    locator: dict[str, Any] = {
        "type": "text_anchor",
        "story": "document",
        "part": "word/document.xml",
        "left_anchor": options.label,
        "expected_match_count": 1,
    }
    if not options.duplicate_anchor:
        locator["paragraph_index"] = 0
        locator["occurrence"] = 1
    return locator


def _slot_contract(field_id: str, tag: str, *, left_anchor: str = "姓名：") -> dict[str, Any]:
    return {
        "slot_id": "slot.cover.student_name",
        "owner": "slot",
        "field_id": field_id,
        "content_type": "text",
        "required": True,
        "cardinality": "one",
        "locator": {
            "type": "content_control_tag",
            "value": tag,
            "story": "document",
            "part": "word/document.xml",
            "paragraph_index": 0,
            "left_anchor": left_anchor,
            "occurrence": 1,
            "expected_match_count": 1,
        },
        "expected_value_style": _style(),
    }


def _contract(
    *,
    contract_id: str,
    template_sha256: str,
    registry_sha256: str,
    options: DocumentOptions,
    boundary_override: str | None = None,
    responsibility_policy: bool = False,
) -> dict[str, Any]:
    regions: list[dict[str, Any]] = [
        {
            "region_id": "protected.student_name_label",
            "owner": "protected",
            "required": True,
            "locator": _locator_for_label(options),
            "text": options.label,
            "expected_style": _style(options.label_size_pt),
        }
    ]
    if options.forbidden_text is not None:
        regions.append(
            {
                "region_id": "remove.instructions",
                "owner": "remove",
                "required": True,
                "locator": {
                    "type": "text_anchor",
                    "story": "document",
                    "part": "word/document.xml",
                    "left_anchor": options.forbidden_text,
                    "occurrence": 1,
                    "expected_match_count": 1,
                },
                "forbidden_text": options.forbidden_text,
            }
        )
    if options.include_image:
        regions.append(
            {
                "region_id": "protected.synthetic_image",
                "owner": "protected",
                "required": True,
                "locator": {
                    "type": "text_range",
                    "story": "document",
                    "part": "word/document.xml",
                    "paragraph_index": 1,
                    "expected_match_count": 1,
                },
                "object_kind": "image",
                "object_sha256": _sha256_bytes(TINY_PNG),
            }
        )
    if options.include_unsupported:
        regions.append(
            {
                "region_id": "protected.unsupported_altchunk",
                "owner": "protected",
                "required": True,
                "locator": {
                    "type": "text_range",
                    "story": "document",
                    "part": "word/document.xml",
                    "paragraph_index": 1,
                    "expected_match_count": 1,
                },
                "object_kind": "unsupported",
            }
        )
    slots: list[dict[str, Any]] = []
    if options.include_slot:
        slots.append(
            _slot_contract(
                options.slot_field_id,
                options.slot_tag,
                left_anchor=boundary_override or options.label,
            )
        )
    if options.include_extra_slot:
        extra = _slot_contract("author.student_id", "docfit.cover.student_id", left_anchor="学号：")
        extra["slot_id"] = "slot.cover.student_id"
        extra["locator"]["paragraph_index"] = 1
        slots.append(extra)
    contract = {
        "schema_version": "docfit-template-fill-contract/v1",
        "contract_id": contract_id,
        "template_sha256": template_sha256,
        "field_registry_ref": {
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.1.0",
            "sha256": registry_sha256,
        },
        "marker_protocol": "docfit-content-control-marker/v1",
        "regions": regions,
        "slots": slots,
    }
    if responsibility_policy:
        contract["responsibility_policy"] = {
            "mode": "exhaustive",
            "analysis_universe": "semantic_document_facts/v1",
            "protected_basis": "complement_of_slot_and_remove",
            "slot_basis": "managed_content_controls_and_fill_contract",
            "remove_basis": "declared_remove_regions",
        }
    return contract


def _definitions() -> list[SampleDefinition]:
    base = DocumentOptions()
    return [
        SampleDefinition("S00-minimal-pass", "minimal exact Actual-Gold match", "PASS", base, base),
        SampleDefinition(
            "S01-protected-text-changed",
            "one protected label changes",
            "FAIL",
            base,
            replace(base, label="学生："),
        ),
        SampleDefinition(
            "S02-protected-style-changed",
            "one protected font size changes",
            "FAIL",
            base,
            replace(base, label_size_pt=14),
        ),
        SampleDefinition(
            "S03-slot-missing",
            "the only required slot is removed",
            "FAIL",
            base,
            replace(base, include_slot=False),
        ),
        SampleDefinition(
            "S04-slot-extra",
            "one undeclared slot is added",
            "FAIL",
            base,
            replace(base, include_extra_slot=True),
        ),
        SampleDefinition(
            "S05-slot-field-wrong",
            "the slot maps to another registered field",
            "FAIL",
            base,
            replace(base, slot_field_id="author.student_id"),
        ),
        SampleDefinition(
            "S06-slot-boundary-wrong",
            "the slot locator boundary omits the protected colon anchor",
            "FAIL",
            base,
            base,
            boundary_override="姓名",
        ),
        SampleDefinition(
            "S07-ambiguous-anchor",
            "a locator without occurrence matches duplicate anchors",
            "UNKNOWN",
            replace(base, duplicate_anchor=True),
            replace(base, duplicate_anchor=True),
        ),
        SampleDefinition(
            "S08-forbidden-residue",
            "forbidden instruction text remains in Actual",
            "FAIL",
            replace(base, forbidden_text="请在此填写"),
            replace(base, forbidden_text="请在此填写"),
        ),
        SampleDefinition(
            "S09-protected-image-missing",
            "a protected image relationship is removed",
            "FAIL",
            replace(base, include_image=True),
            base,
        ),
        SampleDefinition(
            "S10-unsupported-object",
            "a visible altChunk is explicitly unsupported",
            "UNKNOWN",
            replace(base, include_unsupported=True),
            replace(base, include_unsupported=True),
        ),
        SampleDefinition(
            "S11-invalid-input",
            "Actual lacks the main DOCX part and has an invalid contract",
            "INPUT_ERROR",
            base,
            base,
            invalid_actual=True,
        ),
        SampleDefinition(
            "S12-simple-table-structure",
            "a deterministic 2x2 table with a horizontal merge",
            "PASS",
            replace(base, include_table=True),
            replace(base, include_table=True),
        ),
        SampleDefinition(
            "S13-simple-formula-field-bookmark",
            "a minimal formula, field, and bookmark",
            "PASS",
            replace(base, include_semantic_objects=True),
            replace(base, include_semantic_objects=True),
        ),
    ]


def _write_yaml(path: Path, value: Any) -> None:
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )


def build_samples(output_root: Path, scoring_path: Path) -> dict[str, Any]:
    output_root = output_root.resolve()
    scoring_path = scoring_path.resolve()
    if output_root.exists():
        for definition in _definitions():
            sample_dir = output_root / definition.sample_id
            if sample_dir.exists():
                shutil.rmtree(sample_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    registry_path = output_root / "field-registry.yaml"
    _write_yaml(registry_path, _registry())
    registry_sha256 = _sha256_file(registry_path)
    scoring_sha256 = _sha256_file(scoring_path)
    eval_config = {
        "schema_version": "docfit-template-extraction-eval-config/v1",
        "config_id": "synthetic-v1",
        "marker_protocol": {
            "version": "docfit-content-control-marker/v1",
            "field_identity_property": "w:alias",
            "slot_identity_property": "w:tag",
            "internal_id_property": "w:id",
        },
        "tolerances": {"font_size_pt": 0.01, "distance_pt": 0.05, "color_channel": 0},
        "normalization": [
            "ignore_zip_timestamps",
            "ignore_word_internal_sdt_id",
            "merge_equivalent_runs",
        ],
        "scoring_ref": {
            "path": "../config/scoring-v1.yaml",
            "version": "docfit-template-extraction-scoring/v1",
            "sha256": scoring_sha256,
        },
    }
    eval_config_path = output_root / "eval-config.yaml"
    _write_yaml(eval_config_path, eval_config)
    eval_config_sha256 = _sha256_file(eval_config_path)

    sample_records: list[dict[str, Any]] = []
    for definition in _definitions():
        sample_dir = output_root / definition.sample_id
        sample_dir.mkdir(parents=True, exist_ok=True)
        gold_template = sample_dir / "gold-template.docx"
        actual_template = sample_dir / "actual-template.docx"
        write_docx(gold_template, definition.gold)
        write_docx(
            actual_template,
            definition.actual,
            omit_main_document=definition.invalid_actual,
        )
        validate_docx_package(gold_template)
        validate_docx_package(
            actual_template,
            require_main_document=not definition.invalid_actual,
        )

        gold_contract = _contract(
            contract_id=f"{definition.sample_id.lower()}.gold",
            template_sha256=_sha256_file(gold_template),
            registry_sha256=registry_sha256,
            options=definition.gold,
            responsibility_policy=True,
        )
        actual_contract = _contract(
            contract_id=f"{definition.sample_id.lower()}.actual",
            template_sha256=_sha256_file(actual_template),
            registry_sha256=registry_sha256,
            options=definition.actual,
            boundary_override=definition.boundary_override,
        )
        if definition.sample_id == "S08-forbidden-residue":
            # Gold declares the forbidden pattern but the Gold document itself must remain clean.
            write_docx(gold_template, replace(definition.gold, forbidden_text=None))
            validate_docx_package(gold_template)
            gold_contract["template_sha256"] = _sha256_file(gold_template)
        if definition.invalid_actual:
            actual_contract.pop("template_sha256")
            actual_contract["slots"][0].pop("field_id")

        gold_contract_path = sample_dir / "gold-contract.yaml"
        actual_contract_path = sample_dir / "actual-contract.yaml"
        _write_yaml(gold_contract_path, gold_contract)
        _write_yaml(actual_contract_path, actual_contract)
        case = {
            "schema_version": "docfit-template-extraction-case/v1",
            "case_id": definition.sample_id.lower(),
            "description": definition.description,
            "gold": {"template": "gold-template.docx", "contract": "gold-contract.yaml"},
            "field_registry_ref": {
                "path": "../field-registry.yaml",
                "id": "docfit.thesis.content_fields",
                "version": "0.1.0",
                "sha256": (
                    "0" * 64 if definition.invalid_actual else registry_sha256
                ),
            },
            "eval_config": {
                "path": "../eval-config.yaml",
                "id": "synthetic-v1",
                "version": "docfit-template-extraction-eval-config/v1",
                "sha256": eval_config_sha256,
            },
            "scoring_version": "docfit-template-extraction-scoring/v1",
            "expected_verdict": definition.expected_verdict,
            "gold_review": {"status": "synthetic", "reviewer": None, "reviewed_at": None},
        }
        case_path = sample_dir / "case.yaml"
        _write_yaml(case_path, case)

        assets = {}
        for path in sorted(sample_dir.iterdir()):
            if path.is_file():
                assets[path.name] = {"sha256": _sha256_file(path), "size": path.stat().st_size}
        sample_records.append(
            {
                "sample_id": definition.sample_id,
                "description": definition.description,
                "expected_verdict": definition.expected_verdict,
                "assets": assets,
            }
        )

    manifest = {
        "schema_version": "docfit-template-extraction-synthetic-fixtures/v1",
        "generated_by": "fixtures/build_samples.py",
        "deterministic_zip_timestamp": "2020-01-01T00:00:00Z",
        "contains_real_student_data": False,
        "formal_gold": False,
        "registry_sha256": registry_sha256,
        "eval_config_sha256": eval_config_sha256,
        "scoring_sha256": scoring_sha256,
        "samples": sample_records,
    }
    _write_yaml(output_root / "manifest.yaml", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Synthetic fixture output directory (defaults to this script's directory).",
    )
    parser.add_argument(
        "--scoring",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "scoring-v1.yaml",
        help="Versioned scoring configuration whose hash is bound into fixtures.",
    )
    args = parser.parse_args(argv)
    manifest = build_samples(args.output_root, args.scoring)
    print(json.dumps({"sample_count": len(manifest["samples"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

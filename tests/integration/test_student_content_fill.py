from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

from docfit.app.student_content_fill import (
    StudentContentExtractionRequest,
    StudentContentFillRequest,
    StudentExtractionExecution,
    run_student_content_extraction,
    run_student_content_fill,
)
from docfit.content.fill import fill_template
from docfit.styles import StyleContractSet, style_contract_digest
from docfit.tools.inspection import inspect_document
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import ToolFailure, sha256_file

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _style(
    style_contract_id: str,
    properties: dict[str, str | float | bool] | None = None,
) -> dict[str, object]:
    effective = properties or {"paragraph.alignment": "left"}
    value: dict[str, object] = {
        "style_contract_id": style_contract_id,
        "application_scope": "paragraph",
        "owned_properties": sorted(effective),
        "effective_properties": effective,
        "override_policy": {
            "managed_direct_formatting": "clear_conflicts",
            "unmanaged_properties": "preserve",
        },
        "dependencies": [],
        "word_style_id": "Normal",
    }
    value["contract_digest"] = style_contract_digest(value)
    return value


def _style_contracts(template: Path, *styles: dict[str, object]) -> StyleContractSet:
    return StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": sha256_file(template),
            "styles": list(styles),
        }
    )


def _style_ref(style: dict[str, object]) -> dict[str, object]:
    return {
        "style_contract_id": style["style_contract_id"],
        "contract_digest": style["contract_digest"],
    }


def _bind_placement_styles(
    placement: dict[str, object], contracts: StyleContractSet
) -> None:
    placement["contract"] = {"style_contract_set_digest": contracts.digest}


def _officecli(*arguments: str) -> None:
    executable = shutil.which("officecli")
    if executable is None:
        pytest.skip("Student-content integration requires locked OfficeCLI.")
    environment = dict(os.environ)
    environment["OFFICECLI_SKIP_UPDATE"] = "1"
    environment["OFFICECLI_RESIDENT_FLUSH"] = "each"
    completed = subprocess.run(
        [executable, *arguments, "--json"],
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["success"] is True


def _make_docx(path: Path, *paragraphs: str) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    for paragraph in paragraphs:
        _officecli(
            "add",
            str(path),
            "/body",
            "--type",
            "paragraph",
            "--prop",
            f"text={paragraph}",
        )


def _wrap_paragraphs_as_controls(path: Path, tags: tuple[str, ...]) -> None:
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document = ET.fromstring(parts["word/document.xml"])
    body = document.find(f"{{{W_NS}}}body")
    assert body is not None
    paragraphs = body.findall(f"{{{W_NS}}}p")
    assert len(paragraphs) >= len(tags)
    for paragraph, tag in zip(paragraphs, tags, strict=True):
        index = list(body).index(paragraph)
        body.remove(paragraph)
        control = ET.Element(f"{{{W_NS}}}sdt")
        properties = ET.SubElement(control, f"{{{W_NS}}}sdtPr")
        tag_element = ET.SubElement(properties, f"{{{W_NS}}}tag")
        tag_element.set(f"{{{W_NS}}}val", tag)
        content = ET.SubElement(control, f"{{{W_NS}}}sdtContent")
        content.append(paragraph)
        body.insert(index, control)
    parts["word/document.xml"] = ET.tostring(
        document,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def _set_content_control_color(path: Path, tag: str, color: str) -> None:
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document = ET.fromstring(parts["word/document.xml"])
    for control in document.iter(f"{{{W_NS}}}sdt"):
        tag_element = control.find(f"{{{W_NS}}}sdtPr/{{{W_NS}}}tag")
        if tag_element is None or tag_element.get(f"{{{W_NS}}}val") != tag:
            continue
        run = next(control.iter(f"{{{W_NS}}}r"))
        properties = run.find(f"{{{W_NS}}}rPr")
        if properties is None:
            properties = ET.Element(f"{{{W_NS}}}rPr")
            run.insert(0, properties)
        color_element = properties.find(f"{{{W_NS}}}color")
        if color_element is None:
            color_element = ET.SubElement(properties, f"{{{W_NS}}}color")
        color_element.set(f"{{{W_NS}}}val", color)
        break
    else:
        raise AssertionError(f"Missing synthetic content-control tag: {tag}")
    parts["word/document.xml"] = ET.tostring(
        document,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def _content_control_color(path: Path, tag: str) -> str | None:
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    for control in document.iter(f"{{{W_NS}}}sdt"):
        tag_element = control.find(f"{{{W_NS}}}sdtPr/{{{W_NS}}}tag")
        if tag_element is None or tag_element.get(f"{{{W_NS}}}val") != tag:
            continue
        color = next(control.iter(f"{{{W_NS}}}color"), None)
        return color.get(f"{{{W_NS}}}val") if color is not None else None
    return None


def _add_numbering_to_first_paragraph(path: Path) -> None:
    relationship_namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
    content_type_namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document = ET.fromstring(parts["word/document.xml"])
    paragraph = document.find(f".//{{{W_NS}}}body/{{{W_NS}}}p")
    assert paragraph is not None
    properties = paragraph.find(f"{{{W_NS}}}pPr")
    if properties is None:
        properties = ET.Element(f"{{{W_NS}}}pPr")
        paragraph.insert(0, properties)
    numbering_properties = ET.SubElement(properties, f"{{{W_NS}}}numPr")
    level = ET.SubElement(numbering_properties, f"{{{W_NS}}}ilvl")
    level.set(f"{{{W_NS}}}val", "0")
    number_id = ET.SubElement(numbering_properties, f"{{{W_NS}}}numId")
    number_id.set(f"{{{W_NS}}}val", "7")
    parts["word/document.xml"] = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    parts["word/numbering.xml"] = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:numbering xmlns:w="{W_NS}">
 <w:abstractNum w:abstractNumId="3">
  <w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
 </w:abstractNum>
 <w:num w:numId="7"><w:abstractNumId w:val="3"/></w:num>
</w:numbering>""".encode()
    relationships = ET.fromstring(parts["word/_rels/document.xml.rels"])
    relationship = ET.SubElement(
        relationships,
        f"{{{relationship_namespace}}}Relationship",
    )
    relationship.set("Id", "rId999")
    relationship.set(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering",
    )
    relationship.set("Target", "numbering.xml")
    parts["word/_rels/document.xml.rels"] = ET.tostring(
        relationships, encoding="utf-8", xml_declaration=True
    )
    content_types = ET.fromstring(parts["[Content_Types].xml"])
    override = ET.SubElement(content_types, f"{{{content_type_namespace}}}Override")
    override.set("PartName", "/word/numbering.xml")
    override.set(
        "ContentType",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml",
    )
    parts["[Content_Types].xml"] = ET.tostring(
        content_types, encoding="utf-8", xml_declaration=True
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def _strip_numbering(path: Path) -> None:
    content_type_namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts.pop("word/numbering.xml", None)
    relationships = ET.fromstring(parts["word/_rels/document.xml.rels"])
    for item in list(relationships):
        if item.get("Type", "").endswith("/numbering"):
            relationships.remove(item)
    parts["word/_rels/document.xml.rels"] = ET.tostring(
        relationships, encoding="utf-8", xml_declaration=True
    )
    content_types = ET.fromstring(parts["[Content_Types].xml"])
    for item in list(content_types):
        if (
            item.tag == f"{{{content_type_namespace}}}Override"
            and item.get("PartName") == "/word/numbering.xml"
        ):
            content_types.remove(item)
    parts["[Content_Types].xml"] = ET.tostring(
        content_types, encoding="utf-8", xml_declaration=True
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def test_fill_template_replaces_text_and_block_control_without_mutating_inputs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "student.docx"
    template = tmp_path / "template.docx"
    output = tmp_path / "candidate.docx"
    _make_docx(source, "Student body paragraph")
    _make_docx(template, "TITLE PLACEHOLDER", "BODY PLACEHOLDER")
    _wrap_paragraphs_as_controls(
        template,
        ("docfit.cover.title_en", "docfit.body.chapter_title"),
    )
    _set_content_control_color(template, "docfit.cover.title_en", "7F7F7F")
    office = OfficeCliAdapter()
    source_inspection = inspect_document(source, office)
    source_paragraph = next(item for item in source_inspection.objects if item.kind == "paragraph")
    source_hash = sha256_file(source)
    template_hash = sha256_file(template)
    title_style = _style("style.cover.title")
    body_style = _style("style.body.chapter_body")
    contracts = _style_contracts(template, title_style, body_style)
    placement = {
        "status": "PARTIAL",
        "source_sha256": source_hash,
        "template_sha256": template_hash,
        "operations": [
            {
                "action": "replace_text_content_control",
                "tag": "docfit.cover.title_en",
                "value": "Verified title",
                "style_contract_ref": _style_ref(title_style),
            },
            {
                "action": "replace_block_content_control",
                "field_id": "body.ordered_items",
                "tag": "docfit.body.chapter_title",
                "source_locators": [source_paragraph.locator],
                "remove_tags_after_fill": [],
                "style_contract_ref": _style_ref(body_style),
            },
        ],
    }
    _bind_placement_styles(placement, contracts)

    result = fill_template(
        source_docx=source,
        template_docx=template,
        placement=placement,
        style_contracts=contracts,
        output_docx=output,
    )

    assert result["status"] == "PARTIAL"
    assert result["text_controls_replaced"] == 1
    assert result["block_operations"][0]["dependency_closure_complete"] is True
    assert result["block_operations"][0]["styles_copied"] == 0
    assert result["block_operations"][0]["source_style_references_stripped"] >= 0
    assert result["block_operations"][0]["inserted_body_refs"][0]["target_locator"].startswith(
        "/body/p[@paraId="
    )
    assert sha256_file(source) == source_hash
    assert sha256_file(template) == template_hash
    inspected = inspect_document(output, office)
    visible = "\n".join(item.text for item in inspected.objects)
    assert "Verified title" in visible
    assert "Student body paragraph" in visible
    assert "TITLE PLACEHOLDER" not in visible
    assert "BODY PLACEHOLDER" not in visible
    assert office.validate(output)["passed"] is True


def test_fill_template_rejects_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "student.docx"
    template = tmp_path / "template.docx"
    output = tmp_path / "candidate.docx"
    source.write_bytes(b"source")
    template.write_bytes(b"template")
    output.write_bytes(b"existing")
    style = _style("style.test")
    contracts = _style_contracts(template, style)
    placement = {
        "source_sha256": sha256_file(source),
        "template_sha256": sha256_file(template),
    }
    _bind_placement_styles(placement, contracts)

    with pytest.raises(ToolFailure) as failure:
        fill_template(
            source_docx=source,
            template_docx=template,
            placement=placement,
            style_contracts=contracts,
            output_docx=output,
        )

    assert failure.value.code == "fill_output_exists"


def test_fill_creates_numbering_infrastructure_when_template_has_none(
    tmp_path: Path,
) -> None:
    source = tmp_path / "student.docx"
    template = tmp_path / "template.docx"
    output = tmp_path / "candidate.docx"
    _make_docx(source, "Numbered student paragraph")
    _add_numbering_to_first_paragraph(source)
    _make_docx(template, "BODY PLACEHOLDER")
    _strip_numbering(template)
    _wrap_paragraphs_as_controls(template, ("docfit.body.chapter_title",))
    office = OfficeCliAdapter()
    paragraph = next(
        item for item in inspect_document(source, office).objects if item.kind == "paragraph"
    )
    body_style = _style("style.body.chapter_body")
    contracts = _style_contracts(template, body_style)
    placement = {
        "status": "PARTIAL",
        "source_sha256": sha256_file(source),
        "template_sha256": sha256_file(template),
        "operations": [
            {
                "action": "replace_block_content_control",
                "field_id": "body.ordered_items",
                "tag": "docfit.body.chapter_title",
                "source_locators": [paragraph.locator],
                "remove_tags_after_fill": [],
                "style_contract_ref": _style_ref(body_style),
            }
        ],
    }
    _bind_placement_styles(placement, contracts)
    fill_template(
        source_docx=source,
        template_docx=template,
        placement=placement,
        style_contracts=contracts,
        output_docx=output,
    )

    with zipfile.ZipFile(output) as archive:
        assert "word/numbering.xml" in archive.namelist()
        relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    assert any(item.get("Type", "").endswith("/numbering") for item in relationships)
    assert office.validate(output)["passed"] is True


def test_fill_template_rejects_stale_source_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "student.docx"
    template = tmp_path / "template.docx"
    source.write_bytes(b"source")
    template.write_bytes(b"template")
    style = _style("style.test")
    contracts = _style_contracts(template, style)

    with pytest.raises(ToolFailure) as failure:
        fill_template(
            source_docx=source,
            template_docx=template,
            placement={
                "source_sha256": "0" * 64,
                "template_sha256": sha256_file(template),
            },
            style_contracts=contracts,
            output_docx=tmp_path / "candidate.docx",
        )

    assert failure.value.code == "fill_source_stale"


def test_independent_student_content_app_publishes_partial_candidate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "student.docx"
    template = tmp_path / "template.docx"
    registry_path = tmp_path / "registry.yaml"
    contract_path = tmp_path / "fill-contract.yaml"
    output = tmp_path / "output"
    _make_docx(source, "Verified title", "Student body paragraph")
    _make_docx(
        template,
        "TITLE PLACEHOLDER",
        "BODY TITLE PLACEHOLDER",
        "BODY TEXT PLACEHOLDER",
    )
    _wrap_paragraphs_as_controls(
        template,
        (
            "docfit.cover.title_en",
            "docfit.body.chapter_title",
            "docfit.body.chapter_body",
        ),
    )
    registry_path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.1.0",
                "fields": [
                    {
                        "field_id": "thesis.title.en",
                        "label": "English title",
                        "meaning": "The student's English thesis title.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.heading.level1",
                        "label": "Level-one body heading",
                        "meaning": "A first-level heading in the thesis body.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.paragraph",
                        "label": "Body paragraph",
                        "meaning": "A normal paragraph in the thesis body.",
                        "content_type": "rich_text",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    registry = {
        "path": "registry.yaml",
        "registry_id": "docfit.thesis.content_fields",
        "registry_version": "0.1.0",
        "sha256": sha256_file(registry_path),
    }
    title_style = _style(
        "style.cover.title",
        {"run.color": "000000", "run.font_size_pt": 12.0},
    )
    chapter_title_style = _style(
        "style.body.chapter_title",
        {"paragraph.alignment": "left", "run.color": "000000"},
    )
    body_style = _style(
        "style.body.chapter_body",
        {
            "paragraph.alignment": "left",
            "run.color": "000000",
            "run.font_size_pt": 12.0,
        },
    )
    contracts = _style_contracts(template, title_style, chapter_title_style, body_style)
    contract_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "docfit-template-fill-contract/v2",
                "contract_id": "synthetic",
                "status": "candidate_pending_human_acceptance",
                "revision": "1",
                "template_sha256": sha256_file(template),
                "field_registry_ref": registry,
                "regions": [],
                "styles": [title_style, chapter_title_style, body_style],
                "style_contract_set_digest": contracts.digest,
                "slots": [
                    {
                        "slot_id": "slot.title",
                        "field_id": "thesis.title.en",
                        "required": True,
                        "style_contract_ref": _style_ref(title_style),
                        "locator": {
                            "type": "content_control_tag",
                            "value": "docfit.cover.title_en",
                        },
                    },
                    {
                        "slot_id": "slot.body",
                        "field_id": "body.heading.level1",
                        "required": True,
                        "style_contract_ref": _style_ref(chapter_title_style),
                        "locator": {
                            "type": "content_control_tag",
                            "value": "docfit.body.chapter_title",
                        },
                    },
                    {
                        "slot_id": "slot.body.text",
                        "field_id": "body.paragraph",
                        "required": True,
                        "style_contract_ref": _style_ref(body_style),
                        "locator": {
                            "type": "content_control_tag",
                            "value": "docfit.body.chapter_body",
                        },
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    async def fake_runner(prompt, prepared, schema, transcripts):
        del transcripts
        assert prepared.source_sha256 in prompt
        assert '"schema_version": 3' in prompt
        assert "ordered_source_content_items" in prompt
        assert "Do not return any source_order" in prompt
        assert str(template.resolve()) not in prompt
        assert prepared.source_docx.is_relative_to(prepared.task_root)
        items = prepared.inventory["content_items"]
        title_id = next(
            item["source_content_id"]
            for item in items
            if item["observed_text"] == "Verified title"
        )
        body_id = next(
            item["source_content_id"]
            for item in items
            if item["observed_text"] == "Student body paragraph"
        )
        assert schema["properties"]["annotations"]["items"]["properties"][
            "source_content_id"
        ]["enum"] == [
            item["source_content_id"] for item in items
        ]
        return StudentExtractionExecution(
            structured_output={
                "schema_version": 3,
                "annotations": [
                    {
                        "source_content_id": title_id,
                        "classification_status": "classified",
                        "field_id": "thesis.title.en",
                        "value": "Verified title",
                        "confidence": 1.0,
                        "note": "Synthetic exact title.",
                    },
                    {
                        "source_content_id": body_id,
                        "classification_status": "classified",
                        "field_id": "body.paragraph",
                        "value": None,
                        "confidence": 1.0,
                        "note": "Synthetic body.",
                    },
                ],
                "relations": [],
                "summary": "Synthetic extraction.",
                "uncertainties": [],
            },
            backend="synthetic",
            session_id="synthetic-session",
            tool_uses=(),
            skills_loaded=(),
        )

    report = asyncio.run(
        run_student_content_fill(
            StudentContentFillRequest(
                source,
                template,
                contract_path,
                registry_path,
                output,
            ),
            runner=fake_runner,
        )
    )

    assert report["status"] == "PARTIAL", report
    assert Path(report["candidate_docx"]).is_file()
    assert Path(report["candidate_pdf"]).is_file()
    assert Path(report["student_content"]).is_file()
    assert Path(report["placement"]).is_file()
    assert Path(report["quality_projection"]).is_file()
    projection = json.loads(Path(report["quality_projection"]).read_text())
    assert projection["text_replacements"] == []
    assert projection["content_invariants"]["template_style_set_preserved"] is True
    fill_result = json.loads(Path(report["fill_result"]).read_text())
    assert fill_result["text_controls_formatted"] == 0
    assert report["style_occurrence_counts"]["failed"] == 0
    assert report["style_occurrence_counts"]["unresolved"] == 0
    assert Path(report["style_audit"]).is_file()
    assert (
        _content_control_color(Path(report["candidate_docx"]), "docfit.cover.title_en")
        == "000000"
    )
    assert report["missing_required_count"] == 1
    assert "required_slots_missing" in report["partial_reasons"]
    assert "template_fill_contract_not_human_accepted" in report["partial_reasons"]
    assert json.loads((output / "run-report.json").read_text())["status"] == "PARTIAL"


def test_extraction_module_runs_without_template_or_fill_contract(tmp_path: Path) -> None:
    source = tmp_path / "student.docx"
    registry_path = tmp_path / "registry.yaml"
    output = tmp_path / "extraction-output"
    _make_docx(source, "Verified title", "Student body paragraph")
    registry_path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.1.0",
                "fields": [
                    {
                        "field_id": "thesis.title.en",
                        "label": "English title",
                        "meaning": "The student's English thesis title.",
                        "content_type": "text",
                    },
                    {
                        "field_id": "body.paragraph",
                        "label": "Body paragraph",
                        "meaning": "A normal paragraph in the thesis body.",
                        "content_type": "rich_text",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    async def fake_runner(prompt, prepared, schema, transcripts):
        del schema, transcripts
        assert prepared.task_root == output.resolve()
        assert "template" not in prompt.casefold()
        annotations = []
        for item in prepared.inventory["content_items"]:
            title = item["observed_text"] == "Verified title"
            annotations.append({
                "source_content_id": item["source_content_id"],
                "classification_status": "classified",
                "field_id": "thesis.title.en" if title else "body.paragraph",
                "value": "Verified title" if title else None,
                "confidence": 1.0,
                "note": "Synthetic exact annotation.",
            })
        return StudentExtractionExecution(
            structured_output={
                "schema_version": 3,
                "annotations": annotations,
                "relations": [],
                "summary": "Synthetic extraction.",
                "uncertainties": [],
            },
            backend="synthetic",
            session_id="synthetic-extraction-session",
            tool_uses=(),
            skills_loaded=(),
        )

    report = asyncio.run(
        run_student_content_extraction(
            StudentContentExtractionRequest(source, registry_path, output),
            runner=fake_runner,
        )
    )

    assert report["status"] == "READY", report
    assert not any("template" in path.name.casefold() for path in output.rglob("*"))
    model = json.loads((output / "student-content.json").read_text())
    assert [item["source_order"]["block"] for item in model["items"]] == [1, 2]
    assert model["source_coverage"]["all_source_objects_accounted_for"] is True

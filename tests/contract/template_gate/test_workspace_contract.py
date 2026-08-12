from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.styles.profiles import DEFAULT_STYLE_PROPERTY_PROFILES
from docfit.template.object_mutation import (
    ObjectMutation,
    TocEntry,
    mutate_objects,
)
from docfit.template.workspace import TemplateWorkspaceService, _context_knowledge_signals
from docfit.tools.inspection import InspectedObject, Inspection
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.template_schemas.workspace import (
    TEMPLATE_REQUEST_CURRENT_CONTEXT_SCHEMA,
    TEMPLATE_SUBMIT_CURRENT_DECISION_SCHEMA,
)
from docfit.tools.template_tools import (
    TEMPLATE_FULL_TOOL_NAMES,
    TEMPLATE_LOGICAL_TOOL_NAMES,
    TEMPLATE_REVIEW_LOGICAL_TOOL_NAMES,
    TEMPLATE_SEMANTIC_LOGICAL_TOOL_NAMES,
    TEMPLATE_TOOLS,
)
from docfit.visual.service import VisualEvidenceService

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "evals/template-extraction/fixtures"
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"
XML = "{http://www.w3.org/XML/1998/namespace}"


class FakeVisual:
    def __init__(self) -> None:
        self.last_review: JsonObject | None = None

    def render(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
        return (
            {
                "render_ref": f"render:test:{Path(str(args['input_docx'])).stem}",
                "page_count": 2,
                "overview": None,
            },
            [],
        )

    def review(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
        self.last_review = dict(args)
        if args.get("mode") == "pages":
            if args.get("cursor") is None:
                return (
                    {
                        "evidence": [{"page": 1}],
                        "next_cursor": "fake-final-page-2",
                        "mode": "pages",
                    },
                    [Path("/tmp/final-page-1.png")],
                )
            return (
                {
                    "evidence": [{"page": 2}],
                    "next_cursor": None,
                    "mode": "pages",
                },
                [Path("/tmp/final-page-2.png")],
            )
        pages = args.get("pages", [1])
        return (
            {
                "evidence": [{"page": pages[0]}],
                "next_cursor": None,
                "mode": args["mode"],
            },
            [Path("/tmp/current-region.png")],
        )

    def objects_on_page(
        self,
        _render_ref: str,
        inspection: object,
        _page: int,
        *,
        limit: int,
    ) -> tuple[list[JsonObject], bool]:
        objects = [
            {"object_ref": item.object_ref, "type": item.kind, "text": item.text}
            for item in inspection.objects  # type: ignore[attr-defined]
        ]
        return objects[:limit], len(objects) > limit

    def physical_locations(
        self,
        _render_ref: str,
        inspection: object,
        object_refs: list[JsonObject],
    ) -> list[JsonObject]:
        by_id = {
            item.object_ref["object_id"]: item
            for item in inspection.objects  # type: ignore[attr-defined]
        }
        located: list[JsonObject] = []
        for index, reference in enumerate(object_refs):
            item = by_id[reference["object_id"]]
            top = float(index * 30)
            located.append(
                {
                    "object_ref": item.object_ref,
                    "page": 1,
                    "bbox_pdf": [72.0, top, 500.0, top + 18.0],
                    "mapping_quality": "exact_text",
                }
            )
        return located


class PageSplitVisual(FakeVisual):
    def physical_locations(
        self,
        _render_ref: str,
        inspection: object,
        object_refs: list[JsonObject],
    ) -> list[JsonObject]:
        located = super().physical_locations(_render_ref, inspection, object_refs)
        split = min(3, max(1, len(located) - 1))
        for index, item in enumerate(located):
            page = 1 if index < split else 2
            local_index = index if page == 1 else index - split
            top = float(local_index * 30)
            item.update(
                {
                    "page": page,
                    "bbox_pdf": [72.0, top, 500.0, top + 18.0],
                }
            )
        return located


class MissingFirstRegionVisual(FakeVisual):
    def __init__(self) -> None:
        super().__init__()
        self.reviews: list[JsonObject] = []

    def review(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
        self.reviews.append(dict(args))
        if len(self.reviews) == 1:
            return (
                {
                    "evidence": [
                        {
                            "mapping_quality": "mapping_unavailable",
                            "candidate_pages": [1],
                        }
                    ],
                    "next_cursor": None,
                    "mode": args["mode"],
                },
                [],
            )
        return super().review(args)


class FailingVisual(FakeVisual):
    def review(self, args: JsonObject) -> tuple[JsonObject, list[Path]]:
        raise ToolFailure(
            status="error",
            origin="renderer",
            code="visual_renderer_failed",
            message="Synthetic changed-region render failure.",
        )


def _task(tmp_path: Path, fixture: str = "S08-forbidden-residue") -> tuple[Path, Path]:
    root = tmp_path / "task"
    (root / "input").mkdir(parents=True)
    (root / "work").mkdir()
    (root / "output").mkdir()
    source = root / "input/school-template.docx"
    shutil.copyfile(FIXTURES / fixture / "actual-template.docx", source)
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    styles = ET.fromstring(parts["word/styles.xml"])
    properties = styles.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr")
    assert properties is not None
    color = properties.find(f"{W}color")
    if color is not None:
        properties.remove(color)
    parts["word/styles.xml"] = ET.tostring(
        styles,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(source, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])
    return root, source


def _inject_vml_textbox(document: Path, text: str) -> None:
    with zipfile.ZipFile(document) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(f"{W}body")
    assert body is not None
    paragraph = ET.Element(f"{W}p")
    paragraph_properties = ET.SubElement(paragraph, f"{W}pPr")
    ET.SubElement(paragraph_properties, f"{W}snapToGrid")
    ET.SubElement(paragraph_properties, f"{W}spacing", {f"{W}after": "0"})
    run = ET.SubElement(paragraph, f"{W}r")
    pict = ET.SubElement(run, f"{W}pict")
    shape = ET.SubElement(
        pict,
        f"{V}shape",
        {"id": "docfit-test-shape", "style": "width:300pt;height:40pt"},
    )
    textbox = ET.SubElement(shape, f"{V}textbox")
    content = ET.SubElement(textbox, f"{W}txbxContent")
    inner_paragraph = ET.SubElement(content, f"{W}p")
    inner_run = ET.SubElement(inner_paragraph, f"{W}r")
    ET.SubElement(inner_run, f"{W}t").text = text
    section = body.find(f"{W}sectPr")
    body.insert(list(body).index(section) if section is not None else len(body), paragraph)
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(document, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])


def _append_plain_paragraphs(document: Path, texts: list[str]) -> None:
    with zipfile.ZipFile(document) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(f"{W}body")
    assert body is not None
    section = body.find(f"{W}sectPr")
    position = list(body).index(section) if section is not None else len(body)
    for text in texts:
        paragraph = ET.Element(f"{W}p")
        run = ET.SubElement(paragraph, f"{W}r")
        ET.SubElement(run, f"{W}t").text = text
        body.insert(position, paragraph)
        position += 1
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(document, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])


def _append_label_and_blank_paragraph(document: Path) -> None:
    with zipfile.ZipFile(document) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(f"{W}body")
    assert body is not None
    paragraph = ET.Element(f"{W}p")
    label = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(label, f"{W}t").text = "指导教师："
    blank = ET.SubElement(paragraph, f"{W}r")
    blank_properties = ET.SubElement(blank, f"{W}rPr")
    ET.SubElement(blank_properties, f"{W}u", {f"{W}val": "single"})
    ET.SubElement(blank, f"{W}t", {f"{XML}space": "preserve"}).text = "                        "
    section = body.find(f"{W}sectPr")
    body.insert(list(body).index(section) if section is not None else len(body), paragraph)
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(document, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])


def _append_styled_paragraphs(document: Path, values: list[tuple[str, str]]) -> None:
    """Append visibly different school samples without changing the fixture styles part."""

    with zipfile.ZipFile(document) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(f"{W}body")
    assert body is not None
    section = body.find(f"{W}sectPr")
    position = list(body).index(section) if section is not None else len(body)
    for index, (text, color_value) in enumerate(values, start=1):
        paragraph = ET.Element(f"{W}p")
        properties = ET.SubElement(paragraph, f"{W}pPr")
        ET.SubElement(properties, f"{W}spacing", {f"{W}before": str(index * 20)})
        run = ET.SubElement(paragraph, f"{W}r")
        run_properties = ET.SubElement(run, f"{W}rPr")
        ET.SubElement(run_properties, f"{W}rFonts", {f"{W}eastAsia": "宋体"})
        ET.SubElement(run_properties, f"{W}color", {f"{W}val": color_value})
        ET.SubElement(run_properties, f"{W}sz", {f"{W}val": str(20 + index * 2)})
        ET.SubElement(run, f"{W}t").text = text
        body.insert(position, paragraph)
        position += 1
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(document, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])


def _append_toc_and_titles(
    document: Path,
    *,
    cached_levels: tuple[int, ...] = (1, 2, 3),
    unselected_sources: bool = False,
) -> None:
    with zipfile.ZipFile(document) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    styles = ET.fromstring(parts["word/styles.xml"])
    hyperlink = ET.SubElement(
        styles,
        f"{W}style",
        {f"{W}type": "character", f"{W}styleId": "Hyperlink"},
    )
    ET.SubElement(hyperlink, f"{W}name", {f"{W}val": "Hyperlink"})
    hyperlink_run = ET.SubElement(hyperlink, f"{W}rPr")
    ET.SubElement(hyperlink_run, f"{W}color", {f"{W}val": "0000FF"})
    ET.SubElement(hyperlink_run, f"{W}u", {f"{W}val": "single"})
    for level in range(1, 4):
        style = ET.SubElement(
            styles,
            f"{W}style",
            {f"{W}type": "paragraph", f"{W}styleId": f"TOC{level}"},
        )
        ET.SubElement(style, f"{W}name", {f"{W}val": f"toc {level}"})
        ET.SubElement(style, f"{W}basedOn", {f"{W}val": "Normal"})
        paragraph_properties = ET.SubElement(style, f"{W}pPr")
        if level == 1:
            tabs = ET.SubElement(paragraph_properties, f"{W}tabs")
            ET.SubElement(
                tabs,
                f"{W}tab",
                {f"{W}val": "right", f"{W}leader": "dot", f"{W}pos": "9060"},
            )
            ET.SubElement(
                paragraph_properties,
                f"{W}spacing",
                {f"{W}line": "400", f"{W}lineRule": "exact"},
            )
        else:
            ET.SubElement(
                paragraph_properties,
                f"{W}ind",
                {f"{W}left": str(420 * (level - 1))},
            )
        run_properties = ET.SubElement(style, f"{W}rPr")
        if level == 1:
            ET.SubElement(run_properties, f"{W}b")
        ET.SubElement(run_properties, f"{W}sz", {f"{W}val": "28"})
        ET.SubElement(run_properties, f"{W}szCs", {f"{W}val": "28"})
    if unselected_sources:
        heading = ET.SubElement(
            styles,
            f"{W}style",
            {f"{W}type": "paragraph", f"{W}styleId": "UnselectedHeading1"},
        )
        ET.SubElement(heading, f"{W}name", {f"{W}val": "heading 1"})
        ET.SubElement(heading, f"{W}basedOn", {f"{W}val": "Normal"})
    parts["word/styles.xml"] = ET.tostring(
        styles,
        encoding="utf-8",
        xml_declaration=True,
    )
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(f"{W}body")
    assert body is not None
    section = body.find(f"{W}sectPr")
    position = list(body).index(section) if section is not None else len(body)
    cached_rows = [
        (level, text)
        for level, text in [(1, "第X章 XXX"), (2, "1 XXX"), (3, "1.1 XXX")]
        if level in cached_levels
    ]
    for row_index, (level, text) in enumerate(cached_rows):
        paragraph = ET.Element(f"{W}p")
        properties = ET.SubElement(paragraph, f"{W}pPr")
        ET.SubElement(properties, f"{W}pStyle", {f"{W}val": f"TOC{level}"})
        if level != 3:
            tabs = ET.SubElement(properties, f"{W}tabs")
            ET.SubElement(
                tabs,
                f"{W}tab",
                {f"{W}val": "right", f"{W}leader": "dot", f"{W}pos": "9060"},
            )
        ET.SubElement(
            properties,
            f"{W}spacing",
            {f"{W}line": "400", f"{W}lineRule": "exact"},
        )
        if level == 1:
            begin = ET.SubElement(paragraph, f"{W}r")
            ET.SubElement(begin, f"{W}fldChar", {f"{W}fldCharType": "begin"})
            instruction = ET.SubElement(paragraph, f"{W}r")
            ET.SubElement(instruction, f"{W}instrText").text = ' TOC \\o "1-3" '
            separate = ET.SubElement(paragraph, f"{W}r")
            ET.SubElement(separate, f"{W}fldChar", {f"{W}fldCharType": "separate"})
        run = ET.SubElement(paragraph, f"{W}r")
        run_properties = ET.SubElement(run, f"{W}rPr")
        ET.SubElement(run_properties, f"{W}rStyle", {f"{W}val": "Hyperlink"})
        ET.SubElement(run_properties, f"{W}b", {f"{W}val": "0"})
        ET.SubElement(run_properties, f"{W}color", {f"{W}val": "3333FF"})
        ET.SubElement(run_properties, f"{W}sz", {f"{W}val": "28"})
        ET.SubElement(run_properties, f"{W}szCs", {f"{W}val": "28"})
        ET.SubElement(run, f"{W}t").text = text
        ET.SubElement(run, f"{W}tab")
        ET.SubElement(run, f"{W}t").text = str(level)
        if row_index == len(cached_rows) - 1:
            ET.SubElement(run, f"{W}fldChar", {f"{W}fldCharType": "end"})
        body.insert(position, paragraph)
        position += 1
    if unselected_sources:
        toc_title = ET.Element(f"{W}p")
        toc_title_properties = ET.SubElement(toc_title, f"{W}pPr")
        ET.SubElement(
            toc_title_properties,
            f"{W}pStyle",
            {f"{W}val": "UnselectedHeading1"},
        )
        toc_title_run = ET.SubElement(toc_title, f"{W}r")
        ET.SubElement(toc_title_run, f"{W}t").text = "目  录"
        body.insert(position, toc_title)
        position += 1

        body_paragraph = ET.Element(f"{W}p")
        body_properties = ET.SubElement(body_paragraph, f"{W}pPr")
        ET.SubElement(body_properties, f"{W}outlineLvl", {f"{W}val": "2"})
        body_run = ET.SubElement(body_paragraph, f"{W}r")
        ET.SubElement(body_run, f"{W}t").text = "【未入选正文】"
        body.insert(position, body_paragraph)
        position += 1
    title_texts = [
        "【中文摘要】",
        "【英文摘要】",
        "【一级章标题】",
        "【二级标题】",
        "【三级标题】",
        "【附录标题】",
    ]
    for text in title_texts:
        paragraph = ET.Element(f"{W}p")
        run = ET.SubElement(paragraph, f"{W}r")
        ET.SubElement(run, f"{W}t").text = text
        body.insert(position, paragraph)
        position += 1
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(document, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])


def _append_section_boundary_instruction(document: Path) -> None:
    with zipfile.ZipFile(document) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(f"{W}body")
    assert body is not None
    final_section = body.find(f"{W}sectPr")
    position = list(body).index(final_section) if final_section is not None else len(body)
    boundary = ET.Element(f"{W}p")
    properties = ET.SubElement(boundary, f"{W}pPr")
    section = ET.SubElement(properties, f"{W}sectPr")
    ET.SubElement(section, f"{W}type", {f"{W}val": "nextPage"})
    run = ET.SubElement(boundary, f"{W}r")
    ET.SubElement(run, f"{W}t").text = "应删除的目录页说明"
    body.insert(position, boundary)
    title = ET.Element(f"{W}p")
    title_run = ET.SubElement(title, f"{W}r")
    ET.SubElement(title_run, f"{W}t").text = "摘  要"
    body.insert(position + 1, title)
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(document, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])


def _service(
    tmp_path: Path, fixture: str = "S08-forbidden-residue"
) -> tuple[TemplateWorkspaceService, FakeVisual, Path]:
    root, source = _task(tmp_path, fixture)
    visual = FakeVisual()
    return (
        TemplateWorkspaceService(
            task_root=root,
            field_registry=REGISTRY,
            visual=visual,  # type: ignore[arg-type]
        ),
        visual,
        source,
    )


def _finish_local_work(service: TemplateWorkspaceService, source: Path) -> None:
    progress = service._read_progress(sha256_file(source))
    progress.update(
        {
            "region_index": len(service._source_regions()),
            "pending_object_ref": None,
            "pending_edit_intents": [],
            "current_region_edited": False,
        }
    )
    service._write_progress(progress)


def _record_clean_batch(service: TemplateWorkspaceService, batch: JsonObject) -> JsonObject:
    return service.record_final_review_verdict(
        document_ref=batch["document_ref"],
        render_ref=batch["render_ref"],
        page_count=batch["page_count"],
        verdicts=[
            {"page": page, "verdict": "clean", "defects": []}
            for page in batch["batch_pages"]
        ],
    )


def test_agent_surface_is_role_scoped_and_hides_application_flow_control() -> None:
    assert TEMPLATE_LOGICAL_TOOL_NAMES == (
        "template_get_current_work_item",
        "template_request_current_context",
        "template_submit_current_decision",
        "template_report_ambiguity",
        "template_get_review_batch",
    )
    assert TEMPLATE_LOGICAL_TOOL_NAMES[:4] == TEMPLATE_SEMANTIC_LOGICAL_TOOL_NAMES
    assert TEMPLATE_LOGICAL_TOOL_NAMES[4:] == TEMPLATE_REVIEW_LOGICAL_TOOL_NAMES
    assert (
        tuple(f"mcp__docfit__{name}" for name in TEMPLATE_LOGICAL_TOOL_NAMES)
        == TEMPLATE_FULL_TOOL_NAMES
    )
    assert tuple(tool.name for tool in TEMPLATE_TOOLS) == TEMPLATE_LOGICAL_TOOL_NAMES
    schemas = " ".join(str(tool.input_schema) for tool in TEMPLATE_TOOLS).casefold()
    for forbidden in (
        "yaml",
        "compiler",
        "plan_path",
        "output_docx",
        "attempt",
        "publish",
        "document_ref",
        "region_ref",
        "cursor",
    ):
        assert forbidden not in schemas
    assert TEMPLATE_TOOLS[0].input_schema["properties"] == {}
    assert set(TEMPLATE_TOOLS[1].input_schema["properties"]) == {
        "object_id",
        "visual_scope",
        "field_query",
        "text_query",
    }
    assert set(TEMPLATE_TOOLS[2].input_schema["properties"]) == {
        "outcome",
        "reason",
        "operations",
    }
    assert set(TEMPLATE_TOOLS[3].input_schema["properties"]) == {
        "reason",
        "missing_evidence",
    }
    assert TEMPLATE_TOOLS[4].input_schema["properties"] == {}
    operation_schema = TEMPLATE_TOOLS[2].input_schema["properties"]["operations"]["items"]
    assert set(operation_schema["properties"]["action"]["enum"]) == {
        "materialize_slot",
        "materialize_structure",
        "normalize_effective_format",
        "refresh_toc",
        "clear_content",
        "remove_object",
        "ensure_page_start",
    }
    assert "object_ref" not in schemas
    assert "clear_direct_format" not in schemas


def test_open_next_and_search_expose_only_one_local_visual_region(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path, "S07-ambiguous-anchor")
    _append_plain_paragraphs(source, [f"相邻对象{index}" for index in range(8)])

    opened, images = service.view({"action": "open"})
    next_region, next_images = service.view(
        {
            "action": "next",
            "region_ref": opened["current_region"]["region_ref"],
            "region_outcome": "preserve",
            "reason": "This fixture region is fixed school content.",
        }
    )
    searched, _ = service.view(
        {
            "action": "search",
            "document_ref": opened["document_ref"],
            "query": "姓名",
        }
    )

    assert images == [Path("/tmp/current-region.png")]
    assert next_images == [Path("/tmp/current-region.png")]
    assert "objects" not in opened
    assert "current_page" not in opened
    assert opened["visual"] == {
        "scope": "target_region",
        "full_page_returned": False,
    }
    assert opened["current_region"]["target"]["object_ref"]
    assert isinstance(opened["current_region"]["target"]["document_order"], int)
    assert set(opened["current_region"]["target"]["object_ref"]) == {"object_id"}
    assert all(
        set(item["object_ref"]) == {"object_id"}
        for item in opened["current_region"]["adjacent_objects"]
    )
    assert all(
        isinstance(item["document_order"], int)
        for item in opened["current_region"]["adjacent_objects"]
    )
    assert len(opened["current_region"]["adjacent_objects"]) <= 32
    assert set(opened["current_region"]) == {
        "region_ref",
        "index",
        "count",
        "target",
        "parent_object",
        "adjacent_objects",
        "knowledge_signals",
        "evidence",
    }
    assert len(opened["current_region"]["knowledge_signals"]) <= 1
    assert next_region["current_region"]["region_ref"] != opened["current_region"]["region_ref"]
    assert next_region["navigation"]["completed_regions"] == 1
    assert searched["match_count"] > 1
    assert len(searched["matches"]) <= 5
    assert all(isinstance(item["document_order"], int) for item in searched["matches"])


def test_checkpoint_summary_keeps_toc_sample_feedback_across_sessions() -> None:
    inspection = Inspection(
        document_sha256="a" * 64,
        objects=(
            InspectedObject(
                locator="/body/p[1]",
                kind="paragraph",
                text="摘  要\tⅠ",
                style="TOC 1",
                format={},
                object_ref={"object_id": "obj-summary-1"},
            ),
            InspectedObject(
                locator="/body/p[2]",
                kind="paragraph",
                text="第X章 XXX\tXX",
                style="TOC 1",
                format={},
                object_ref={"object_id": "obj-summary-2"},
            ),
            InspectedObject(
                locator="/body/sdt[1]",
                kind="sdt",
                text="【一级章标题】",
                style=None,
                format={
                    "alias": "body.heading.level1",
                    "tag": "body.heading.level1.1",
                },
                object_ref={"object_id": "obj-summary-3"},
            ),
            InspectedObject(
                locator="/body/p[3]",
                kind="paragraph",
                text="第 X 章 结论与展望\t6",
                style="TOC 1",
                format={},
                object_ref={"object_id": "obj-summary-4"},
            ),
        ),
        summary={},
        risks=(),
        warnings=(),
        provider={},
    )

    summary = TemplateWorkspaceService._checkpoint_summary(inspection)

    assert summary["toc"] == {
        "entry_count": 3,
        "sample_marker_count": 1,
        "sample_marker_examples": ["第X章 XXX\tXX"],
        "missing_body_heading_types": ["body.heading.level1"],
        "refresh_needed": True,
    }


def test_heading_context_routes_body_structure_before_instruction_color() -> None:
    heading = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="2 结果与分析（四号黑体）",
        style="标题 2",
        format={"effective.color": "#0000FF"},
        object_ref={},
    )

    assert _context_knowledge_signals([heading]) == ["body-structure"]


def test_collection_landmark_routes_collection_knowledge_before_heading_style() -> None:
    heading = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="参考文献",
        style="heading 1",
        format={},
        object_ref={},
    )
    sample = InspectedObject(
        locator="/body/p[2]",
        kind="paragraph",
        text="[1] 示例条目",
        style="Normal",
        format={"effective.color": "#0000FF"},
        object_ref={},
    )

    assert _context_knowledge_signals([sample, heading]) == [
        "collection-and-optional-sections"
    ]


def test_collection_words_inside_body_prose_do_not_route_collection_knowledge() -> None:
    paragraph = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="本文参考文献部分综合讨论既有研究，并在正文中继续展开分析。",
        style="Normal",
        format={},
        object_ref={},
    )

    assert _context_knowledge_signals([paragraph]) == []


def test_next_requires_an_explicit_agent_outcome_and_committed_handling(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    opened, _ = service.view({"action": "open"})
    region_ref = opened["current_region"]["region_ref"]

    with pytest.raises(ToolFailure) as missing:
        service.view({"action": "next", "region_ref": region_ref})
    assert missing.value.code == "region_outcome_missing"

    with pytest.raises(ToolFailure) as uncommitted:
        service.view(
            {
                "action": "next",
                "region_ref": region_ref,
                "region_outcome": "handled",
            }
        )
    assert uncommitted.value.code == "region_edit_not_committed"

    with pytest.raises(ToolFailure) as no_reason:
        service.view(
            {
                "action": "next",
                "region_ref": region_ref,
                "region_outcome": "preserve",
            }
        )
    assert no_reason.value.code == "region_preserve_reason_missing"

    advanced, _ = service.view(
        {
            "action": "next",
            "region_ref": region_ref,
            "region_outcome": "preserve",
            "reason": "The visible school identity must remain unchanged.",
        }
    )
    assert advanced["navigation"]["completed_regions"] == 1


def test_next_accepts_handled_after_the_region_has_a_committed_edit(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    opened, _ = service.view({"action": "open"})
    selected = opened["current_region"]["target"]

    changed, _ = service.edit(
        {"operations": [{"action": "clear_content", "object_ref": selected["object_ref"]}]}
    )
    advanced, _ = service.view(
        {
            "action": "next",
            "region_ref": changed["current_region"]["region_ref"],
            "region_outcome": "handled",
        }
    )

    assert advanced["navigation"]["completed_regions"] == 1


def test_finished_navigation_returns_one_bounded_toc_refresh_task(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_toc_and_titles(source)
    document_hash, document = service._register_source()
    inspection = service._inspection(document)

    pending, images = service._pending_generated_content(
        document_hash.rsplit(":", 1)[-1],
        inspection,
    )

    assert images == [Path("/tmp/current-region.png")]
    assert pending is not None
    assert pending["field_id"] == "generated.toc"
    assert pending["required_body_heading_candidates"] == []
    assert set(pending["target"]["object_ref"]) == {"object_id"}
    assert 1 <= len(pending["title_candidates"]) <= 24
    assert all(set(item["object_ref"]) == {"object_id"} for item in pending["title_candidates"])
    assert "non-semantic suggestions" in pending["guidance"]


def test_failed_toc_intent_returns_regenerated_fresh_candidates(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    _append_toc_and_titles(source)
    service._register_source()
    source_hash = sha256_file(source)
    progress = service._read_progress(source_hash)
    progress.update(
        {
            "region_index": len(service._source_regions()),
            "pending_edit_intents": [
                {
                    "action": "refresh_toc",
                    "field_id": "generated.toc",
                    "last_failure": {"code": "target_not_found", "message": "stale ref"},
                }
            ],
        }
    )
    service._write_progress(progress)

    reopened, _ = service.view({"action": "open"})

    assert reopened["pending_edit_intents"][0]["action"] == "refresh_toc"
    assert reopened["pending_generated_content"]["field_id"] == "generated.toc"
    assert reopened["pending_generated_content"]["target"]["object_ref"]
    assert reopened["pending_generated_content"]["title_candidates"]


def test_checkpoint_toc_feedback_detects_wrong_body_heading_level() -> None:
    objects = (
        InspectedObject(
            locator="/body/p[1]",
            kind="paragraph",
            text="【二级标题】\t1",
            style="toc 1",
            format={},
            object_ref={"object_id": "obj-level-1"},
        ),
        InspectedObject(
            locator="/body/sdt[1]",
            kind="sdt",
            text="【二级标题】",
            style=None,
            format={
                "alias": "body.heading.level2",
                "tag": "body.heading.level2.1",
            },
            object_ref={"object_id": "obj-level-2"},
        ),
    )
    inspection = Inspection(
        document_sha256="b" * 64,
        objects=objects,
        summary={},
        risks=(),
        warnings=(),
        provider={},
    )

    summary = TemplateWorkspaceService._checkpoint_summary(inspection)

    assert summary["toc"]["missing_body_heading_types"] == ["body.heading.level2"]
    assert summary["toc"]["refresh_needed"] is True


def test_navigation_regions_never_mix_objects_from_different_visual_pages(
    tmp_path: Path,
) -> None:
    root, source = _task(tmp_path, "S07-ambiguous-anchor")
    _append_plain_paragraphs(source, [f"视觉对象{index}" for index in range(8)])
    visual = PageSplitVisual()
    service = TemplateWorkspaceService(
        task_root=root,
        field_registry=REGISTRY,
        visual=visual,  # type: ignore[arg-type]
    )

    service.view({"action": "open"})

    blueprint = json.loads(service.region_blueprint_path.read_text(encoding="utf-8"))
    assert blueprint["layout_strategy"] == "page-proximity-v1"
    assert len(blueprint["regions"]) >= 2
    assert all(len({anchor["page"] for anchor in region}) == 1 for region in blueprint["regions"])


def test_navigation_splits_large_vertical_gaps_on_the_same_page() -> None:
    anchors: list[JsonObject] = [
        {"page": 1, "bbox_pdf": [72.0, 10.0, 500.0, 28.0], "text": "上部"},
        {"page": 1, "bbox_pdf": [72.0, 160.0, 500.0, 178.0], "text": "下部一"},
        {"page": 1, "bbox_pdf": [72.0, 190.0, 500.0, 208.0], "text": "下部二"},
    ]

    regions = TemplateWorkspaceService._cluster_physical_regions(anchors)

    assert [[item["text"] for item in region] for region in regions] == [
        ["上部"],
        ["下部一", "下部二"],
    ]


def test_unmappable_paragraph_never_falls_back_to_an_unrelated_region(
    tmp_path: Path,
) -> None:
    root, _ = _task(tmp_path, "S07-ambiguous-anchor")
    visual = MissingFirstRegionVisual()
    service = TemplateWorkspaceService(
        task_root=root,
        field_registry=REGISTRY,
        visual=visual,  # type: ignore[arg-type]
    )

    opened, images = service.view({"action": "open"})
    advanced, _ = service.view(
        {
            "action": "next",
            "region_ref": opened["current_region"]["region_ref"],
            "region_outcome": "preserve",
            "reason": "This fixture region is fixed school content.",
        }
    )

    assert images == []
    assert len(visual.reviews) == 1
    assert advanced["navigation"]["completed_regions"] == 1


def test_open_resumes_latest_document_and_pending_region_without_transcript(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    opened, _ = service.view({"action": "open"})
    selected = opened["current_region"]["target"]

    changed, _ = service.edit(
        {"operations": [{"action": "clear_content", "object_ref": selected["object_ref"]}]}
    )

    resumed = TemplateWorkspaceService(
        task_root=service.task_root,
        field_registry=REGISTRY,
        visual=FakeVisual(),  # type: ignore[arg-type]
    )
    reopened, _ = resumed.view({"action": "open"})

    assert reopened["document_ref"] == changed["document_ref"]
    assert reopened["resume"] == {
        "resumed": True,
        "source": "application_checkpoint",
        "prior_transcript_loaded": False,
    }
    assert reopened["current_region"]["region_ref"] == changed["current_region"]["region_ref"]


def test_local_region_includes_actionable_runs_for_adjacent_paragraphs(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)

    opened, _ = service.view({"action": "open"})
    adjacent_runs = {
        item["text"]
        for item in opened["current_region"]["adjacent_objects"]
        if item["type"] == "run"
    }

    assert "姓名：" in adjacent_runs
    assert "请在此填写" in adjacent_runs


def test_local_region_gives_blank_run_its_immediate_parent_label(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    paragraph = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="题目：",
        style="封面字段",
        format={},
        object_ref={"object_id": "obj-parent"},
    )
    label = InspectedObject(
        locator="/body/p[1]/r[1]",
        kind="run",
        text="题目：",
        style=None,
        format={},
        object_ref={"object_id": "obj-label"},
    )
    blank_value = InspectedObject(
        locator="/body/p[1]/r[2]",
        kind="run",
        text="",
        style=None,
        format={},
        object_ref={"object_id": "obj-value"},
    )
    inspection = Inspection(
        document_sha256="a" * 64,
        objects=(paragraph, label, blank_value),
        summary={},
        risks=(),
        warnings=(),
        provider={},
    )

    context = service._local_context(inspection, blank_value)

    assert context["target"]["parent_context"] == {
        "type": "paragraph",
        "text": "题目：",
        "style": "封面字段",
        "object_ref": {"object_id": "obj-parent"},
        "document_order": 0,
    }
    adjacent_label = next(item for item in context["adjacent_objects"] if item["text"] == "题目：")
    assert adjacent_label["parent_context"]["text"] == "题目："


def test_page_object_exposes_bounded_style_facts_needed_for_agent_judgment() -> None:
    item = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="本行红字是填写说明",
        style="正文",
        format={
            "color": "#FF0000",
            "effective.font.eastAsia": "宋体",
            "effective.size": 12,
            "alignment": "center",
            "marginLeft": 99,
        },
        object_ref={"document_sha256": "a" * 64, "object_id": "obj-test"},
    )

    compact = VisualEvidenceService._compact_page_object(item)

    assert compact["style"] == "正文"
    assert compact["format_hint"] == {
        "alignment": "center",
        "color": "#FF0000",
        "effective.font.eastAsia": "宋体",
        "effective.size": 12,
    }
    assert "marginLeft" not in compact["format_hint"]


def test_registry_batches_only_current_objects_from_one_version(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    document_ref, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(item for item in inspection.objects if "姓名" in item.text)
    second = next(item for item in inspection.objects if "请在此填写" in item.text)

    result = service.registry_query(
        {
            "lookups": [
                {"object_id": second.object_ref["object_id"], "field_id": "abstract.zh"},
                {
                    "object_id": second.object_ref["object_id"],
                    "field_id": "body.heading.level1",
                },
            ],
            "searches": [{"object_id": selected.object_ref["object_id"], "query": "中文姓名"}],
        }
    )

    assert result["document_ref"] == document_ref
    assert len(result["results"]) == 3
    assert result["results"][0]["matches"][0]["field_id"] == "abstract.zh"
    assert result["results"][1]["matches"][0]["semantic_object_type"] == {
        "type_id": "body.heading.level1",
        "role": "heading",
        "repeatable": True,
        "parent_type": "body.chapters",
        "toc_level": 1,
    }
    assert result["results"][2]["matches"][0]["field_id"] == "author.name.zh"
    assert "fields" not in result


def test_registry_keeps_batch_useful_when_agent_guesses_a_partial_field_id(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item for item in service._inspection(document).objects if "请在此填写" in item.text
    )

    result = service.registry_query(
        {
            "lookups": [
                {
                    "object_id": selected.object_ref["object_id"],
                    "field_id": "thesis.title",
                },
                {
                    "object_id": selected.object_ref["object_id"],
                    "field_id": "author.name",
                },
            ]
        }
    )

    assert [item["operation"] for item in result["results"]] == [
        "suggest",
        "suggest",
    ]
    assert result["results"][0]["matches"][0]["field_id"] == "thesis.title.zh"
    assert result["results"][1]["matches"][0]["field_id"] == "author.name.zh"


def test_registry_search_ranks_domain_terms_in_an_agent_phrase(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)

    title = service.registry.search("cover title student thesis")
    author = service.registry.search("cover author student name")

    assert title[0]["field_id"] == "thesis.title.zh"
    assert author[0]["field_id"] == "author.name.zh"
    assert service.registry.search("学生 学院")[0]["field_id"] == "author.department"
    assert service.registry.search("指导教师 职称")[0]["field_id"] == "advisor.title"


def test_registry_search_lane_has_no_optional_lookup_fields(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item for item in service._inspection(document).objects if "请在此填写" in item.text
    )

    result = service.registry_query(
        {
            "searches": [
                {
                    "object_id": selected.object_ref["object_id"],
                    "query": "thesis title on cover",
                }
            ]
        }
    )

    assert result["results"][0]["operation"] == "search"
    assert result["results"][0]["matches"][0]["field_id"] == "thesis.title.zh"


def test_agent_decision_schemas_use_flat_short_object_ids(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = service._inspection(document).objects[0]
    result = service.registry_query(
        {
            "lookups": [
                {
                    "object_id": selected.object_ref["object_id"],
                    "field_id": "thesis.title.zh",
                }
            ]
        }
    )

    object_id_schema = TEMPLATE_REQUEST_CURRENT_CONTEXT_SCHEMA["properties"]["object_id"]
    assert object_id_schema == {
        "type": "string",
        "pattern": "^obj-[0-9a-f]{24}$",
    }
    operation = TEMPLATE_SUBMIT_CURRENT_DECISION_SCHEMA["properties"]["operations"][
        "items"
    ]
    assert set(operation["properties"]) >= {
        "object_id",
        "field_id",
        "action",
    }
    assert "object_ref" not in str(TEMPLATE_SUBMIT_CURRENT_DECISION_SCHEMA)
    assert result["results"][0]["operation"] == "lookup"


def test_batch_edit_is_atomic_returns_local_region_feedback_and_preserves_source(
    tmp_path: Path,
) -> None:
    service, visual, source = _service(tmp_path)
    source_hash = sha256_file(source)
    _, document = service._register_source()
    inspection = service._inspection(document)
    fillable = next(
        item for item in inspection.objects if item.kind == "run" and "请在此填写" in item.text
    )
    label = next(
        item for item in inspection.objects if item.kind == "run" and item.text == "姓名："
    )

    result, images = service.edit(
        {
            "operations": [
                {
                    "action": "clear_content",
                    "object_ref": label.object_ref,
                },
                {
                    "action": "materialize_slot",
                    "object_ref": fillable.object_ref,
                    "field_id": "abstract.zh",
                },
            ],
        }
    )

    assert result["committed"] is True
    assert result["document_sha256"] != source_hash
    assert result["effects"] == {
        "operations": 2,
        "actions": {"clear_content": 1, "materialize_slot": 1},
        "slots_created": 1,
        "absorbed_operations": [],
        "target_adjustments": [],
        "preserved_boundaries": [],
        "migrated_boundaries": [],
        "page_start_results": [],
        "style_scope_changes": [],
        "toc_source_levels": [],
        "toc_suppressed_sources": [],
        "effective_format_changes": [],
    }
    assert "applied" not in result
    assert "slots" not in result
    assert result["current_region"]["target"]["object_ref"]
    assert images == [Path("/tmp/current-region.png")]
    assert visual.last_review is not None
    assert visual.last_review["mode"] == "regions"
    assert sha256_file(source) == source_hash
    assert not any((service.task_root / "output").iterdir())
    assert not (service.task_root / "work/decisions").exists()
    assert not (service.task_root / "work/compiled").exists()
    _, changed_path = service._resolve_document(result["document_ref"])
    changed = service._inspection(changed_path)
    slot = next(
        item
        for item in changed.objects
        if item.kind == "sdt" and item.format.get("alias") == "abstract.zh"
    )
    assert slot.text == "【中文摘要】"


def test_materialize_slot_narrows_a_label_paragraph_to_its_unique_blank_value_run(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_label_and_blank_paragraph(source)
    _, document = service._register_source()
    paragraph = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "paragraph" and item.text.startswith("指导教师：")
    )

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": paragraph.object_ref,
                    "field_id": "advisor.name.zh",
                    "effective_format": {"color": "black", "underline": "none"},
                }
            ]
        }
    )

    assert result["committed"] is True
    assert len(result["effects"]["target_adjustments"]) == 1
    adjustment = result["effects"]["target_adjustments"][0]
    assert adjustment["action"] == "materialize_slot"
    assert adjustment["reason"] == "unique_widest_blank_value_run"
    assert adjustment["requested_object_id"] == paragraph.object_ref["object_id"]
    assert adjustment["effective_object_id"] != paragraph.object_ref["object_id"]
    _, changed_path = service._resolve_document(result["document_ref"])
    paragraphs = [
        item
        for item in service._inspection(changed_path).objects
        if item.kind == "paragraph" and item.text.startswith("指导教师：")
    ]
    assert paragraphs
    assert paragraphs[0].text == "指导教师："
    slot = next(
        item
        for item in service._inspection(changed_path).objects
        if item.kind == "sdt" and item.format.get("alias") == "advisor.name.zh"
    )
    assert slot.text.strip() == "【导师中文姓名】"


def test_materialize_slot_trusts_paragraph_when_blank_value_runs_are_ambiguous(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_label_and_blank_paragraph(source)
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    paragraph = next(
        item
        for item in root.iter(f"{W}p")
        if "".join(node.text or "" for node in item.iter(f"{W}t")).startswith("指导教师：")
    )
    blank = max(
        (
            run
            for run in paragraph.findall(f"{W}r")
            if not "".join(node.text or "" for node in run.iter(f"{W}t")).strip()
        ),
        key=lambda run: len("".join(node.text or "" for node in run.iter(f"{W}t"))),
    )
    paragraph.append(ET.fromstring(ET.tostring(blank)))
    parts["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(source, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])
    _, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "paragraph" and item.text.startswith("指导教师：")
    )

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": selected.object_ref,
                    "field_id": "advisor.name.zh",
                }
            ]
        }
    )

    assert result["committed"] is True
    assert result["effects"]["target_adjustments"] == []
    _, changed_path = service._resolve_document(result["document_ref"])
    slots = [
        item
        for item in service._inspection(changed_path).objects
        if item.kind == "sdt" and item.format.get("alias") == "advisor.name.zh"
    ]
    assert len(slots) == 1
    assert slots[0].text == "【导师中文姓名】"


def test_materialize_paragraph_moves_ranges_outside_slot_and_discards_render_history(
    tmp_path: Path,
) -> None:
    source = tmp_path / "materialize-boundary-source.docx"
    output = tmp_path / "materialize-boundary-output.docx"
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body><w:p>'
        '<w:bookmarkStart w:id="1" w:name="toc-source"/>'
        '<w:commentRangeStart w:id="2"/><w:r><w:lastRenderedPageBreak/>'
        '<w:t>附录名称</w:t></w:r><w:commentRangeEnd w:id="2"/>'
        '<w:bookmarkEnd w:id="1"/></w:p><w:sectPr/></w:body></w:document>'
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
    paragraph = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="附录名称",
        style=None,
        format={},
        object_ref={"object_id": "obj-appendix-title"},
    )

    effects = mutate_objects(
        source,
        output,
        mutations=[
            ObjectMutation(
                selected=paragraph,
                action="materialize_slot",
                field_id="appendix.title",
                slot_id="appendix.title.1",
                placeholder_text="【附录标题】",
            )
        ],
    )

    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    changed = root.find(f"{W}body/{W}p")
    assert changed is not None
    assert [item.tag for item in changed] == [
        f"{W}bookmarkStart",
        f"{W}commentRangeStart",
        f"{W}sdt",
        f"{W}commentRangeEnd",
        f"{W}bookmarkEnd",
    ]
    assert next(changed.iter(f"{W}lastRenderedPageBreak"), None) is None
    assert "".join(node.text or "" for node in changed.iter(f"{W}t")) == "【附录标题】"
    assert effects["migrated_boundaries"] == [
        {
            "kind": "bookmark_range",
            "object_id": "obj-appendix-title",
            "representation": "outside_content_control",
        },
        {
            "kind": "comment_range",
            "object_id": "obj-appendix-title",
            "representation": "outside_content_control",
        },
    ]


def test_changed_region_failure_does_not_promote_unreviewed_checkpoint(
    tmp_path: Path,
) -> None:
    root, source = _task(tmp_path)
    service = TemplateWorkspaceService(
        task_root=root,
        field_registry=REGISTRY,
        visual=FailingVisual(),  # type: ignore[arg-type]
    )
    _, document = service._register_source()
    source_hash = sha256_file(source)
    progress_before = service._read_progress(source_hash)
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "run" and "请在此填写" in item.text
    )

    with pytest.raises(ToolFailure) as caught:
        service.edit(
            {
                "operations": [
                    {
                        "action": "materialize_slot",
                        "object_ref": selected.object_ref,
                        "field_id": "abstract.en",
                    }
                ]
            }
        )

    assert caught.value.code == "visual_renderer_failed"
    assert service._read_progress(source_hash) == progress_before
    assert not service.receipts.exists() or not any(service.receipts.iterdir())
    versions = list(service.versions.glob("*.docx"))
    assert len(versions) == 2
    assert any(path.stem != source_hash for path in versions)


def test_materialize_slot_preserves_underlined_blank_run_width_budget(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    _append_label_and_blank_paragraph(source)
    _, document = service._register_source()
    inspection = service._inspection(document)
    paragraph = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text.startswith("指导教师：")
    )
    blank = next(
        item
        for item in inspection.objects
        if item.kind == "run"
        and item.locator.startswith(f"{paragraph.locator}/")
        and not item.text.strip()
    )

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": blank.object_ref,
                    "field_id": "advisor.name.zh",
                }
            ]
        }
    )

    _, changed_path = service._resolve_document(result["document_ref"])
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
    control = next(
        sdt
        for sdt in document_root.iter(f"{W}sdt")
        if (alias := sdt.find(f"{W}sdtPr/{W}alias")) is not None
        and alias.get(f"{W}val") == "advisor.name.zh"
    )
    assert "".join(node.text or "" for node in control.iter(f"{W}t")) == (
        "【导师中文姓名】        "
    )
    assert control.find(f".//{W}u").get(f"{W}val") == "single"


def test_atomic_edit_rejects_conflicting_actions_on_the_same_object(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "run" and "请在此填写" in item.text
    )

    with pytest.raises(ToolFailure) as caught:
        service.edit(
            {
                "operations": [
                    {
                        "action": "materialize_slot",
                        "object_ref": selected.object_ref,
                        "field_id": "abstract.en",
                    },
                    {
                        "action": "remove_object",
                        "object_ref": selected.object_ref,
                    },
                ]
            }
        )

    assert caught.value.code == "batch_operations_conflict"


@pytest.mark.parametrize("clear_first", [True, False])
def test_materialize_slot_absorbs_same_target_clear_content(
    tmp_path: Path,
    *,
    clear_first: bool,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "run" and "请在此填写" in item.text
    )
    clear = {"action": "clear_content", "object_ref": selected.object_ref}
    materialize = {
        "action": "materialize_slot",
        "object_ref": selected.object_ref,
        "field_id": "abstract.en",
        "effective_format": {"color": "black", "underline": "none"},
    }

    result, _ = service.edit(
        {"operations": [clear, materialize] if clear_first else [materialize, clear]}
    )

    assert result["committed"] is True
    assert result["effects"]["operations"] == 1
    assert result["effects"]["actions"] == {"materialize_slot": 1}
    assert result["effects"]["absorbed_operations"][0]["reason"] == (
        "materialized_target_replaces_content"
    )
    _, changed_path = service._resolve_document(result["document_ref"])
    slot = next(
        item
        for item in service._inspection(changed_path).objects
        if item.kind == "sdt" and item.format.get("alias") == "abstract.en"
    )
    assert slot.text == "【英文摘要】"


def test_materialize_slot_absorbs_same_target_effective_format_normalization(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "run" and "请在此填写" in item.text
    )

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": selected.object_ref,
                    "field_id": "abstract.en",
                },
                {
                    "action": "normalize_effective_format",
                    "object_ref": selected.object_ref,
                    "effective_format": {"color": "black", "underline": "none"},
                },
            ],
        }
    )

    assert result["committed"] is True
    assert result["effects"]["operations"] == 1
    assert result["effects"]["absorbed_operations"][0]["reason"] == (
        "effective_format_merged_into_compound_action"
    )
    assert result["effects"]["effective_format_changes"][0]["requested"] == {
        "color": "black",
        "underline": "none",
    }


def test_child_cleanup_and_parent_effective_format_commit_together(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(source, [("保留标题（删除说明）", "0000FF")])
    _, document = service._register_source()
    inspection = service._inspection(document)
    parent = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "保留标题（删除说明）"
    )
    child = next(
        item
        for item in inspection.objects
        if item.kind == "run" and item.locator.startswith(f"{parent.locator}/")
    )

    result, _ = service.edit(
        {
            "operations": [
                {"action": "clear_content", "object_ref": child.object_ref},
                {
                    "action": "normalize_effective_format",
                    "object_ref": parent.object_ref,
                    "effective_format": {"color": "black", "underline": "none"},
                },
            ]
        }
    )

    assert result["committed"] is True
    assert result["effects"]["actions"] == {
        "clear_content": 1,
        "normalize_effective_format": 1,
    }
    assert result["effects"]["operations"] == 2


def test_structure_materialization_absorbs_redundant_descendant_cleanup(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(
        source,
        [
            ("第 X 章 样例标题", "FF0000"),
            ("1 节标题", "FF0000"),
            ("1.1 小节标题", "FF0000"),
            ("正文样例", "0000FF"),
        ],
    )
    _, document = service._register_source()
    inspection = service._inspection(document)
    heading = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "第 X 章 样例标题"
    )
    heading_run = next(
        item
        for item in inspection.objects
        if item.kind == "run" and item.locator.startswith(f"{heading.locator}/")
    )
    paragraph = next(
        item for item in inspection.objects if item.kind == "paragraph" and item.text == "正文样例"
    )
    level2 = next(
        item for item in inspection.objects if item.kind == "paragraph" and item.text == "1 节标题"
    )
    level3 = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "1.1 小节标题"
    )

    result, _ = service.edit(
        {
            "operations": [
                {"action": "remove_object", "object_ref": heading_run.object_ref},
                {
                    "action": "materialize_structure",
                    "object_ref": heading.object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": heading.object_ref,
                            "field_id": "body.heading.level1",
                            "effective_format": {"color": "black"},
                        },
                        {
                            "object_ref": level2.object_ref,
                            "field_id": "body.heading.level2",
                            "effective_format": {"color": "black"},
                        },
                        {
                            "object_ref": level3.object_ref,
                            "field_id": "body.heading.level3",
                            "effective_format": {"color": "black"},
                        },
                        {
                            "object_ref": paragraph.object_ref,
                            "field_id": "body.paragraph",
                            "effective_format": {"color": "black"},
                        },
                    ],
                },
            ]
        }
    )

    assert result["effects"]["actions"] == {"materialize_structure": 1}
    assert result["effects"]["operations"] == 1
    absorbed = result["effects"]["absorbed_operations"]
    assert len(absorbed) == 1
    assert absorbed[0]["action"] == "remove_object"
    assert absorbed[0]["target"] == heading_run.public()
    assert absorbed[0]["absorbed_by"]["action"] == "materialize_structure"
    assert absorbed[0]["reason"] == "materialized_parent_replaces_content"
    assert result["structures"][0]["field_id"] == "body.chapters"


def test_structure_preserves_empty_layout_paragraphs_between_semantic_members(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(
        source,
        [
            ("第 X 章", "FF0000"),
            ("", "0000FF"),
            ("1 节标题", "FF0000"),
            ("1.1 小节标题", "FF0000"),
            ("正文样例", "0000FF"),
        ],
    )
    _, document = service._register_source()
    inspection = service._inspection(document)
    heading = next(
        item for item in inspection.objects if item.kind == "paragraph" and item.text == "第 X 章"
    )
    paragraph = next(
        item for item in inspection.objects if item.kind == "paragraph" and item.text == "正文样例"
    )
    level2 = next(
        item for item in inspection.objects if item.kind == "paragraph" and item.text == "1 节标题"
    )
    level3 = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "1.1 小节标题"
    )

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": heading.object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": heading.object_ref,
                            "field_id": "body.heading.level1",
                        },
                        {
                            "object_ref": level2.object_ref,
                            "field_id": "body.heading.level2",
                        },
                        {
                            "object_ref": level3.object_ref,
                            "field_id": "body.heading.level3",
                        },
                        {
                            "object_ref": paragraph.object_ref,
                            "field_id": "body.paragraph",
                        },
                    ],
                }
            ]
        }
    )

    _, changed_path = service._resolve_document(result["document_ref"])
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
    structure = next(
        sdt
        for sdt in document_root.iter(f"{W}sdt")
        if (alias := sdt.find(f"{W}sdtPr/{W}alias")) is not None
        and alias.get(f"{W}val") == "body.chapters"
    )
    assert len(structure.findall(f"{W}sdtContent/{W}p")) == 5


def test_structure_absorbs_redundant_member_slot_operations(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("第一章 样例", "FF0000", "body.heading.level1"),
        ("1.1 样例", "FF0000", "body.heading.level2"),
        ("1.1.1 样例", "FF0000", "body.heading.level3"),
        ("正文样例", "0000FF", "body.paragraph"),
    ]
    _append_styled_paragraphs(source, [(text, color) for text, color, _ in samples])
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _, _ in samples}
    }
    members = [
        {"object_ref": selected[text].object_ref, "field_id": field_id}
        for text, _, field_id in samples
    ]

    result, _ = service.edit(
        {
            "operations": [
                *[
                    {
                        "action": "materialize_slot",
                        "object_ref": selected[text].object_ref,
                        "field_id": field_id,
                        "effective_format": {"color": "black", "underline": "none"},
                    }
                    for text, _, field_id in samples
                ],
                {
                    "action": "materialize_structure",
                    "object_ref": selected[samples[0][0]].object_ref,
                    "field_id": "body.chapters",
                    "members": members,
                },
            ]
        }
    )

    assert result["committed"] is True
    assert result["effects"]["operations"] == 1
    assert result["effects"]["actions"] == {"materialize_structure": 1}
    absorbed = result["effects"]["absorbed_operations"]
    assert len(absorbed) == len(samples)
    assert {item["reason"] for item in absorbed} == {
        "materialization_absorbed_by_structure_member"
    }
    assert result["materialized_members"] == sorted(field_id for _, _, field_id in samples)
    assert len(result["effects"]["effective_format_changes"]) == len(samples)
    assert all(
        change["requested"] == {"color": "black", "underline": "none"}
        for change in result["effects"]["effective_format_changes"]
    )


def test_structure_order_failure_returns_objective_reselection_feedback(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("第 X 章", "FF0000", "body.heading.level1"),
        ("1 节标题", "0000FF", "body.heading.level2"),
        ("正文样例", "0000FF", "body.paragraph"),
    ]
    _append_styled_paragraphs(source, [(text, color) for text, color, _ in samples])
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _, _ in samples}
    }

    with pytest.raises(ToolFailure) as caught:
        service.edit(
            {
                "operations": [
                    {
                        "action": "materialize_structure",
                        "object_ref": selected[samples[-1][0]].object_ref,
                        "field_id": "body.chapters",
                        "members": [
                            {
                                "object_ref": selected[text].object_ref,
                                "field_id": field_id,
                            }
                            for text, _, field_id in reversed(samples)
                        ],
                    }
                ]
            }
        )

    assert caught.value.code == "body_structure_not_in_document_order"
    assert "body.paragraph@" in caught.value.message
    assert "body.heading.level1@" in caught.value.message
    assert "Do not repair a cross-block selection by only reordering" in caught.value.message
    assert caught.value.suggested_actions == (
        "reselect_members_from_one_forward_document_block",
        "do_not_only_reorder_cross_block_members",
    )


def test_structure_leaves_empty_section_boundary_outside_repeatable_unit(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(
        source,
        [
            ("第 X 章", "FF0000"),
            ("1 节标题", "0000FF"),
            ("1.1 小节标题", "0000FF"),
            ("", "000000"),
            ("正文样例", "0000FF"),
        ],
    )
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    document_root = ET.fromstring(parts["word/document.xml"])
    appended = list(document_root.iter(f"{W}p"))[-5:]
    properties = appended[-2].find(f"{W}pPr")
    assert properties is not None
    ET.SubElement(properties, f"{W}sectPr")
    parts["word/document.xml"] = ET.tostring(
        document_root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(source, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])

    _, document = service._register_source()
    selected = {
        item.text: item
        for item in service._inspection(document).objects
        if item.kind == "paragraph"
        and item.text in {"第 X 章", "1 节标题", "1.1 小节标题", "正文样例"}
    }
    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": selected["第 X 章"].object_ref,
                    "members": [
                        {
                            "object_ref": selected["第 X 章"].object_ref,
                            "field_id": "body.heading.level1",
                        },
                        {
                            "object_ref": selected["1 节标题"].object_ref,
                            "field_id": "body.heading.level2",
                        },
                        {
                            "object_ref": selected["1.1 小节标题"].object_ref,
                            "field_id": "body.heading.level3",
                        },
                        {
                            "object_ref": selected["正文样例"].object_ref,
                            "field_id": "body.paragraph",
                        },
                    ],
                }
            ]
        }
    )

    _, changed_path = service._resolve_document(result["document_ref"])
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
    structure = next(
        sdt
        for sdt in document_root.iter(f"{W}sdt")
        if (alias := sdt.find(f"{W}sdtPr/{W}alias")) is not None
        and alias.get(f"{W}val") == "body.chapters"
    )
    assert structure.find(f".//{W}sectPr") is None
    assert document_root.find(f".//{W}sectPr") is not None


def test_structure_extracts_nonadjacent_members_without_absorbing_instructions(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(
        source,
        [
            ("第 X 章", "FF0000"),
            ("各章标题三号黑体，正文首行缩进两个字符。", "FF0000"),
            ("1 节标题", "0000FF"),
            ("1.1 小节标题", "0000FF"),
            ("正文样例", "0000FF"),
        ],
    )
    _, document = service._register_source()
    selected = {
        item.text: item
        for item in service._inspection(document).objects
        if item.kind == "paragraph"
        and item.text in {"第 X 章", "1 节标题", "1.1 小节标题", "正文样例"}
    }

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": selected["第 X 章"].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": selected["第 X 章"].object_ref,
                            "field_id": "body.heading.level1",
                        },
                        {
                            "object_ref": selected["1 节标题"].object_ref,
                            "field_id": "body.heading.level2",
                        },
                        {
                            "object_ref": selected["1.1 小节标题"].object_ref,
                            "field_id": "body.heading.level3",
                        },
                        {
                            "object_ref": selected["正文样例"].object_ref,
                            "field_id": "body.paragraph",
                        },
                    ],
                }
            ]
        }
    )

    _, changed_path = service._resolve_document(result["document_ref"])
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
    structure = next(
        sdt
        for sdt in document_root.iter(f"{W}sdt")
        if (alias := sdt.find(f"{W}sdtPr/{W}alias")) is not None
        and alias.get(f"{W}val") == "body.chapters"
    )
    structure_text = "".join(node.text or "" for node in structure.iter(f"{W}t"))
    document_text = "".join(node.text or "" for node in document_root.iter(f"{W}t"))
    assert "各章标题三号黑体" not in structure_text
    assert "各章标题三号黑体" in document_text


def test_structure_reports_style_boundary_risk_without_semantic_rejection(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(
        source,
        [
            ("第 X 章 代表标题", "FF0000"),
            ("1 节标题", "0000FF"),
            ("1.1 小节标题", "0000FF"),
            ("第 X 章 结论与展望", "000000"),
            ("结论章正文样例", "0000FF"),
        ],
    )
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    document_root = ET.fromstring(parts["word/document.xml"])
    for paragraph in document_root.iter(f"{W}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{W}t"))
        if text.startswith("第 X 章"):
            properties = paragraph.find(f"{W}pPr")
            assert properties is not None
            properties.insert(0, ET.Element(f"{W}pStyle", {f"{W}val": "chapter"}))
    parts["word/document.xml"] = ET.tostring(
        document_root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(source, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])

    _, document = service._register_source()
    selected = {
        item.text: item
        for item in service._inspection(document).objects
        if item.kind == "paragraph"
        and item.text in {"第 X 章 代表标题", "1 节标题", "1.1 小节标题", "结论章正文样例"}
    }

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": selected["第 X 章 代表标题"].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": selected["第 X 章 代表标题"].object_ref,
                            "field_id": "body.heading.level1",
                        },
                        {
                            "object_ref": selected["1 节标题"].object_ref,
                            "field_id": "body.heading.level2",
                        },
                        {
                            "object_ref": selected["1.1 小节标题"].object_ref,
                            "field_id": "body.heading.level3",
                        },
                        {
                            "object_ref": selected["结论章正文样例"].object_ref,
                            "field_id": "body.paragraph",
                        },
                    ],
                }
            ]
        }
    )

    assert result["committed"] is True
    assert result["structural_risks"][0]["code"] == ("similar_heading_style_inside_member_span")
    assert result["structural_risks"][0]["severity"] == "warning"


def test_body_structure_materializes_agent_selected_member_set_without_fixed_grammar(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(
        source,
        [("第 X 章", "FF0000"), ("1 节标题", "FF0000")],
    )
    _, document = service._register_source()
    selected = {
        item.text: item
        for item in service._inspection(document).objects
        if item.kind == "paragraph" and item.text in {"第 X 章", "1 节标题"}
    }

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": selected["第 X 章"].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": selected["第 X 章"].object_ref,
                            "field_id": "body.heading.level1",
                        },
                        {
                            "object_ref": selected["1 节标题"].object_ref,
                            "field_id": "body.heading.level2",
                        },
                    ],
                }
            ]
        }
    )

    assert result["committed"] is True
    assert result["materialized_members"] == [
        "body.heading.level1",
        "body.heading.level2",
    ]
    assert result["structural_risks"] == []


def test_pending_structure_intent_keeps_the_richer_failed_attempt(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item for item in service._inspection(document).objects if item.kind == "paragraph"
    )
    reference = {"object_id": selected.object_ref["object_id"]}

    def operation(member_types: list[str]) -> JsonObject:
        return {
            "action": "materialize_structure",
            "object_ref": reference,
            "field_id": "body.chapters",
            "members": [
                {"object_ref": reference, "field_id": field_id} for field_id in member_types
            ],
        }

    richer = [
        "body.heading.level1",
        "body.heading.level2",
        "body.heading.level3",
        "body.paragraph",
    ]
    failure = ToolFailure(
        status="needs_input",
        origin="request",
        code="body_structure_not_contiguous",
        message="retry",
    )
    service.record_edit_failure({"operations": [operation(richer)]}, failure)
    service.record_edit_failure(
        {"operations": [operation(["body.heading.level2", "body.heading.level3"])]},
        failure,
    )

    progress = service._read_progress(sha256_file(source))
    assert progress["pending_edit_intents"][0]["member_field_ids"] == richer
    assert [
        item["field_id"]
        for item in progress["pending_edit_intents"][0]["retry_operation"]["members"]
    ] == richer


def test_failed_batch_persists_only_registered_semantic_intents(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "run" and "请在此填写" in item.text
    )
    service.record_edit_failure(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": selected.object_ref,
                    "field_id": "abstract.zh",
                },
                {
                    "action": "materialize_slot",
                    "object_ref": selected.object_ref,
                    "field_id": "invented.field",
                },
            ]
        },
        ToolFailure(
            status="needs_input",
            origin="request",
            code="field_not_registered",
            message="One field was not registered.",
        ),
    )

    progress = service._read_progress(sha256_file(source))
    assert [item["field_id"] for item in progress["pending_edit_intents"]] == ["abstract.zh"]
    assert progress["pending_edit_intents"][0]["last_failure"]["code"] == (
        "batch_rejected_by_invalid_sibling"
    )

    progress["pending_edit_intents"].append(
        {
            "action": "materialize_slot",
            "field_id": "invented.field",
            "member_field_ids": [],
        }
    )
    service._write_progress(progress)
    reopened, _ = service.view({"action": "open"})
    assert [item["field_id"] for item in reopened["pending_edit_intents"]] == ["abstract.zh"]


def test_existing_capability_satisfies_a_narrower_failed_edit_intent() -> None:
    summary: JsonObject = {
        "materialized_fields": {
            "body.heading.level1": 1,
            "body.heading.level2": 1,
            "body.heading.level3": 1,
            "body.paragraph": 3,
            "submission.date": 1,
        },
        "materialized_structures": ["body.chapters"],
        "toc": {"refresh_needed": False},
    }

    assert TemplateWorkspaceService._intent_already_satisfied(
        {
            "action": "materialize_structure",
            "field_id": "body.chapters",
            "member_field_ids": [
                "body.heading.level2",
                "body.heading.level3",
                "body.paragraph",
            ],
        },
        summary,
    )
    assert TemplateWorkspaceService._intent_already_satisfied(
        {"action": "materialize_slot", "field_id": "body.paragraph"},
        summary,
    )
    assert TemplateWorkspaceService._intent_already_satisfied(
        {
            "action": "materialize_structure",
            "field_id": "submission.date",
            "member_field_ids": ["submission.date"],
        },
        summary,
    )
    assert TemplateWorkspaceService._intent_already_satisfied(
        {"action": "refresh_toc", "field_id": "generated.toc"},
        summary,
    )


def test_failed_semantic_edit_intent_survives_fresh_open_until_success(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    document_ref, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "run" and "请在此填写" in item.text
    )
    operation = {
        "action": "materialize_slot",
        "object_ref": selected.object_ref,
        "field_id": "abstract.zh",
    }
    service.record_edit_failure(
        {"operations": [operation]},
        ToolFailure(
            status="needs_input",
            origin="request",
            code="synthetic_edit_failure",
            message="The requested semantic edit did not commit.",
        ),
    )

    reopened, _ = service.view({"action": "open"})
    intent = reopened["pending_edit_intents"][0]
    assert intent["action"] == "materialize_slot"
    assert intent["field_id"] == "abstract.zh"
    assert intent["member_field_ids"] == []
    assert intent["target"] == {"type": "run", "text": "请在此填写"}
    assert intent["last_failure"]["code"] == "synthetic_edit_failure"
    assert intent["recovery"] == "re_locate_and_improve"
    assert "retry_operation" not in intent
    assert reopened["pending_generated_content"] is None
    with pytest.raises(ToolFailure) as pending:
        service.publish({"document_ref": document_ref})
    assert pending.value.code == "agent_edit_intent_unresolved"

    changed, _ = service.edit({"operations": [operation]})
    assert (
        json.loads(service.progress_path.read_text(encoding="utf-8"))["pending_edit_intents"] == []
    )
    assert changed["effects"]["slots_created"] == 1


def test_large_focus_crop_returns_a_bounded_larger_object_neighborhood(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_plain_paragraphs(source, [f"正文对象{index}" for index in range(12)])
    _, document = service._register_source()
    selected = next(
        item
        for item in service._inspection(document).objects
        if item.kind == "paragraph" and item.text == "正文对象5"
    )

    narrow, _ = service.view({"action": "focus", "object_ref": selected.object_ref, "padding": 32})
    wide, _ = service.view({"action": "focus", "object_ref": selected.object_ref, "padding": 256})
    narrow_paragraphs = [
        item for item in narrow["local_context"]["adjacent_objects"] if item["type"] == "paragraph"
    ]
    wide_paragraphs = [
        item for item in wide["local_context"]["adjacent_objects"] if item["type"] == "paragraph"
    ]

    assert len(wide_paragraphs) > len(narrow_paragraphs)
    assert len(wide["local_context"]["adjacent_objects"]) <= 32


def test_run_level_slot_feedback_falls_back_to_its_own_paragraph_crop(
    tmp_path: Path,
) -> None:
    root, _ = _task(tmp_path)
    visual = MissingFirstRegionVisual()
    service = TemplateWorkspaceService(
        task_root=root,
        field_registry=REGISTRY,
        visual=visual,  # type: ignore[arg-type]
    )
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(
        item for item in inspection.objects if item.kind == "run" and "请在此填写" in item.text
    )

    result, images = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": selected.object_ref,
                    "field_id": "abstract.zh",
                }
            ]
        }
    )

    assert images == [Path("/tmp/current-region.png")]
    assert len(visual.reviews) == 2
    fallback_ref = visual.reviews[1]["regions"][0]["object_ref"]
    _, changed_path = service._resolve_document(result["document_ref"])
    changed = service._inspection(changed_path)
    fallback = next(item for item in changed.objects if item.object_ref == fallback_ref)
    slot = next(
        item
        for item in changed.objects
        if item.kind == "sdt" and item.format.get("alias") == "abstract.zh"
    )
    assert fallback.kind == "paragraph"
    assert slot.locator.startswith(f"{fallback.locator}/")


def test_slot_uses_brackets_only_and_normalizes_effective_color_without_losing_style(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_styled_paragraphs(source, [("蓝色摘要样例", "0000FF")])
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "蓝色摘要样例"
    )

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_slot",
                    "object_ref": selected.object_ref,
                    "field_id": "abstract.zh",
                    "effective_format": {"color": "black", "underline": "none"},
                }
            ],
        }
    )

    assert result["knowledge_signals"] == ["effective-style"]
    assert result["effects"]["effective_format_changes"][0]["requested"] == {
        "color": "black",
        "underline": "none",
    }

    _, changed_path = service._resolve_document(result["document_ref"])
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
    control = next(
        sdt
        for sdt in document_root.iter(f"{W}sdt")
        if (alias := sdt.find(f"{W}sdtPr/{W}alias")) is not None
        and alias.get(f"{W}val") == "abstract.zh"
    )
    assert "".join(node.text or "" for node in control.iter(f"{W}t")) == "【中文摘要】"
    assert control.find(f".//{W}showingPlcHdr") is None
    color = control.find(f".//{W}color")
    assert color is not None
    assert color.get(f"{W}val") == "000000"
    underline = control.find(f".//{W}u")
    assert underline is not None
    assert underline.get(f"{W}val") == "none"
    assert control.find(f".//{W}rFonts").get(f"{W}eastAsia") == "宋体"
    assert control.find(f".//{W}sz").get(f"{W}val") == "22"


def test_body_structure_is_one_direct_operation_with_school_styles_preserved(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("第一章 样例", "FF0000", "body.heading.level1"),
        ("一级正文样例", "0000FF", "body.paragraph"),
        ("1.1 样例", "FF0000", "body.heading.level2"),
        ("二级正文样例", "0000FF", "body.paragraph"),
        ("1.1.1 样例", "FF0000", "body.heading.level3"),
        ("三级正文样例", "0000FF", "body.paragraph"),
    ]
    replacement_samples = [
        ("第二章 更完整样例", "FF0000", "body.heading.level1"),
        ("2.1 更完整样例", "FF0000", "body.heading.level2"),
        ("2.1.1 更完整样例", "FF0000", "body.heading.level3"),
        ("替换后的正文样例", "0000FF", "body.paragraph"),
    ]
    _append_styled_paragraphs(
        source,
        [(text, color) for text, color, _ in [*samples, *replacement_samples]],
    )
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _, _ in samples}
    }
    members = [
        {
            "object_ref": selected[text].object_ref,
            "field_id": field_id,
            "effective_format": {"color": "black"},
        }
        for text, _, field_id in samples
    ]

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": selected[samples[0][0]].object_ref,
                    "field_id": "body.chapters",
                    "members": members,
                }
            ],
        }
    )

    assert result["structures"] == [
        {
            "field_id": "body.chapters",
            "slot_id": "body.chapters.1",
            "member_count": 6,
        }
    ]
    _, changed_path = service._resolve_document(result["document_ref"])
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
    group = next(
        sdt
        for sdt in document_root.iter(f"{W}sdt")
        if (alias := sdt.find(f"{W}sdtPr/{W}alias")) is not None
        and alias.get(f"{W}val") == "body.chapters"
    )
    aliases = [alias.get(f"{W}val") for alias in group.findall(f".//{W}sdtPr/{W}alias")]
    assert aliases == ["body.chapters", *[field_id for _, _, field_id in samples]]
    assert group.find(f".//{W}showingPlcHdr") is None
    assert {color.get(f"{W}val") for color in group.findall(f".//{W}color")} == {"000000"}
    assert len(group.findall(f".//{W}rFonts")) == 6
    assert [node.get(f"{W}before") for node in group.findall(f".//{W}pPr/{W}spacing")] == [
        "20",
        "40",
        "60",
        "80",
        "100",
        "120",
    ]

    opened, _ = service.view({"action": "open"})
    assert opened["checkpoint_summary"]["materialized_structures"] == ["body.chapters"]
    assert opened["checkpoint_summary"]["materialized_fields"]["body.chapters"] == 1
    changed_inspection = service._inspection(changed_path)
    replacements = {
        item.text: item
        for item in changed_inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _, _ in replacement_samples}
    }
    replacement_result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": {
                        "object_id": replacements[replacement_samples[0][0]].object_ref["object_id"]
                    },
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": {"object_id": replacements[text].object_ref["object_id"]},
                            "field_id": field_id,
                            "effective_format": {"color": "black"},
                        }
                        for text, _, field_id in replacement_samples
                    ],
                }
            ]
        }
    )
    assert replacement_result["structures"] == [
        {
            "field_id": "body.chapters",
            "slot_id": "body.chapters.1",
            "member_count": 4,
        }
    ]
    _, replacement_path = service._resolve_document(replacement_result["document_ref"])
    replacement_inspection = service._inspection(replacement_path)
    structures = [
        item
        for item in replacement_inspection.objects
        if item.kind == "sdt" and item.format.get("alias") == "body.chapters"
    ]
    assert len(structures) == 1
    assert structures[0].text == "【一级章标题】【二级标题】【三级标题】【正文段落】"
    _finish_local_work(service, source)
    first_review, _ = service.final_review(
        {"document_ref": replacement_result["document_ref"]}
    )
    _record_clean_batch(service, first_review)
    final_review, _ = service.final_review(
        {
            "document_ref": replacement_result["document_ref"],
            "cursor": first_review["next_cursor"],
        }
    )
    receipt = _record_clean_batch(service, final_review)
    assert receipt["coverage_complete"] is True
    assert receipt["status"] == "clean"
    published = service.publish({"document_ref": replacement_result["document_ref"]})
    assert published["counts"]["slot"] == 4
    fill_contract = json.loads(
        (service.root / "publication/fill-contract.json").read_text(encoding="utf-8")
    )
    assert fill_contract["schema_version"] == "docfit-template-fill-contract/v2"
    assert fill_contract["provenance"]["structure_count"] == 1
    assert [item["field_id"] for item in fill_contract["slots"]] == [
        field_id for _, _, field_id in replacement_samples
    ]
    assert len(fill_contract["styles"]) == 4
    assert fill_contract["validation"]["style_capture"]["validation"]["counts"] == {
        "passed": 4,
        "failed": 0,
        "unresolved": 0,
    }
    styles = {item["style_contract_id"]: item for item in fill_contract["styles"]}
    assert all(
        styles[slot["style_contract_ref"]["style_contract_id"]]["contract_digest"]
        == slot["style_contract_ref"]["contract_digest"]
        for slot in fill_contract["slots"]
    )
    observation_artifact = json.loads(
        (service.root / "publication/school-style-observations.json").read_text(
            encoding="utf-8"
        )
    )
    assert fill_contract["profile_registry_digest"] == (
        DEFAULT_STYLE_PROPERTY_PROFILES.registry_digest
    )
    assert fill_contract["school_observation_set_digest"] == observation_artifact[
        "school_observation_set_digest"
    ]
    observed = {
        item["style_role_id"]: item
        for item in observation_artifact["observation_set"]["observations"]
    }
    assert [
        item["property_path"] for item in observed["style.body.heading.1"]["properties"]
    ] == list(DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type("heading").property_paths)
    table_caption_gap = next(
        item
        for item in fill_contract["known_school_style_gaps"]
        if item["field_id"] == "body.table.caption"
    )
    assert table_caption_gap["reason"] == "school_role_representative_missing"
    assert published["school_style"]["known_gap_count"] > 0
    assert published["school_style"]["failed_observation_count"] == 0
    forbidden_publish_payload = json.dumps(
        {
            "published": published,
            "fill_contract": fill_contract,
        },
        ensure_ascii=False,
    )
    assert "selected_style_contract_set_digest" not in forbidden_publish_payload
    assert "fallback_selection" not in forbidden_publish_payload
    assert "preset_digest" not in forbidden_publish_payload


def test_structure_replacement_reuses_existing_members_and_adds_new_level(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    samples = [
        ("第一章 样例", "FF0000", "body.heading.level1"),
        ("正文样例", "0000FF", "body.paragraph"),
        ("1.1 样例", "FF0000", "body.heading.level2"),
        ("1.1.1 后发现样例", "FF0000", "body.heading.level3"),
    ]
    _append_styled_paragraphs(source, [(text, color) for text, color, _ in samples])
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in {text for text, _, _ in samples}
    }

    initial, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": selected[samples[0][0]].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {
                            "object_ref": selected[text].object_ref,
                            "field_id": field_id,
                        }
                        for text, _, field_id in samples[:3]
                    ],
                }
            ]
        }
    )
    _, initial_path = service._resolve_document(initial["document_ref"])
    initial_inspection = service._inspection(initial_path)
    member_controls = {
        str(item.format["alias"]): item
        for item in initial_inspection.objects
        if item.kind == "sdt"
        and item.format.get("alias")
        in {"body.heading.level1", "body.paragraph", "body.heading.level2"}
    }

    def containing_paragraph(control: InspectedObject) -> InspectedObject:
        return max(
            (
                item
                for item in initial_inspection.objects
                if item.kind == "paragraph"
                and control.locator.startswith(f"{item.locator}/")
            ),
            key=lambda item: len(item.locator),
        )

    reused = {
        field_id: containing_paragraph(control)
        for field_id, control in member_controls.items()
    }
    discovered = next(
        item
        for item in initial_inspection.objects
        if item.kind == "paragraph" and item.text == samples[-1][0]
    )
    ordered_members = [
        (reused["body.heading.level1"], "body.heading.level1"),
        (reused["body.paragraph"], "body.paragraph"),
        (reused["body.heading.level2"], "body.heading.level2"),
        (discovered, "body.heading.level3"),
    ]

    replaced, _ = service.edit(
        {
            "operations": [
                {
                    "action": "materialize_structure",
                    "object_ref": reused["body.heading.level1"].object_ref,
                    "field_id": "body.chapters",
                    "members": [
                        {"object_ref": item.object_ref, "field_id": field_id}
                        for item, field_id in ordered_members
                    ],
                }
            ]
        }
    )

    assert replaced["committed"] is True
    assert replaced["effects"]["actions"] == {"materialize_structure": 1}
    assert replaced["materialized_members"] == sorted(
        field_id for _, field_id in ordered_members
    )
    _, replaced_path = service._resolve_document(replaced["document_ref"])
    replaced_inspection = service._inspection(replaced_path)
    structures = [
        item
        for item in replaced_inspection.objects
        if item.kind == "sdt" and item.format.get("alias") == "body.chapters"
    ]
    assert len(structures) == 1
    assert structures[0].text == "【一级章标题】【正文段落】【二级标题】【三级标题】"


def test_clear_content_preserves_selected_container_and_its_metadata(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(item for item in inspection.objects if item.kind == "sdt")

    result, _ = service.edit(
        {
            "operations": [{"action": "clear_content", "object_ref": selected.object_ref}],
        }
    )

    _, changed_path = service._resolve_document(result["document_ref"])
    changed = service._inspection(changed_path)
    preserved = next(item for item in changed.objects if item.kind == "sdt")
    assert preserved.text == ""
    assert preserved.format["alias"] == "author.name.zh"
    assert preserved.format["tag"] == "docfit.cover.student_name"


def test_remove_instruction_preserves_its_next_page_section_boundary(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    _append_section_boundary_instruction(source)
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "应删除的目录页说明"
    )
    sections_before = int(inspection.summary["sections"])

    result, _ = service.edit(
        {
            "operations": [
                {"action": "remove_object", "object_ref": selected.object_ref},
            ]
        }
    )

    _, changed_path = service._resolve_document(result["document_ref"])
    changed = service._inspection(changed_path)
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
    boundary = next(
        paragraph
        for paragraph in document_root.iter(f"{W}p")
        if paragraph.find(f"{W}pPr/{W}sectPr/{W}type") is not None
    )
    assert "".join(node.text or "" for node in boundary.iter(f"{W}t")) == ""
    assert boundary.find(f"{W}pPr/{W}sectPr/{W}type").get(f"{W}val") == "nextPage"
    assert int(changed.summary["sections"]) == sections_before
    assert any(item.text == "摘  要" for item in changed.objects)


def test_toc_refresh_keeps_live_field_and_builds_non_empty_representative_cache(
    tmp_path: Path,
) -> None:
    source = tmp_path / "toc.docx"
    output = tmp_path / "toc-refreshed.docx"
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        '<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>第一章</w:t><w:tab/></w:r></w:p>"
        '<w:p><w:pPr><w:pStyle w:val="TOC2"/></w:pPr>'
        "<w:r><w:t>第二节</w:t><w:tab/></w:r></w:p>"
        '<w:p><w:pPr><w:pStyle w:val="TOC3"/></w:pPr>'
        "<w:r><w:t>第三小节</w:t><w:tab/></w:r>"
        "<w:r><w:drawing/></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        "<w:p><w:r><w:t>【中文摘要】</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>【英文摘要】</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>【一级章标题】</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>【二级标题】</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>【三级标题】</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>【附录标题】</w:t></w:r></w:p>"
        "<w:sectPr/></w:body></w:document>"
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr(
            "word/settings.xml",
            (f'<w:settings xmlns:w="{W[1:-1]}"><w:compat/><w:rsids/></w:settings>').encode(),
        )
    entries = [
        TocEntry(
            selected=InspectedObject(
                locator=f"/body/p[{index + 3}]",
                kind="paragraph",
                text=text,
                style=None,
                format={},
                object_ref={},
            ),
            level=level,
        )
        for index, (text, level) in enumerate(
            [
                ("【中文摘要】", 1),
                ("【英文摘要】", 1),
                ("【一级章标题】", 1),
                ("【二级标题】", 2),
                ("【三级标题】", 3),
                ("【附录标题】", 1),
            ],
            start=1,
        )
    ]
    mutation = ObjectMutation(
        selected=InspectedObject(
            locator="/body/p[2]",
            kind="paragraph",
            text="第二节",
            style="TOC2",
            format={},
            object_ref={},
        ),
        action="refresh_toc",
        field_id="generated.toc",
        toc_entries=tuple(entries),
    )

    mutate_objects(source, output, mutations=[mutation])

    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        settings = ET.fromstring(archive.read("word/settings.xml"))
    paragraphs = root.findall(f"{W}body/{W}p")[:6]
    field_types = [node.get(f"{W}fldCharType") for node in root.iter(f"{W}fldChar")]
    assert field_types == ["begin", "separate", "end"]
    assert "TOC" in "".join(node.text or "" for node in root.iter(f"{W}instrText"))
    assert [
        "".join(node.text or "" for node in paragraph.iter(f"{W}t")) for paragraph in paragraphs
    ] == [
        "【中文摘要】1",
        "【英文摘要】1",
        "【一级章标题】1",
        "【二级标题】1",
        "【三级标题】1",
        "【附录标题】1",
    ]
    assert [paragraph.find(f"{W}pPr/{W}pStyle").get(f"{W}val") for paragraph in paragraphs] == [
        "TOC1",
        "TOC1",
        "TOC1",
        "TOC2",
        "TOC3",
        "TOC1",
    ]
    assert all(paragraph.find(f".//{W}tab") is not None for paragraph in paragraphs)
    assert root.find(f".//{W}drawing") is not None
    following_title = next(
        paragraph
        for paragraph in root.findall(f"{W}body/{W}p")
        if "".join(node.text or "" for node in paragraph.iter(f"{W}t")) == "【中文摘要】"
    )
    assert following_title.find(f"{W}pPr/{W}pageBreakBefore") is None
    assert settings.find(f"{W}updateFields").get(f"{W}val") == "true"
    assert [child.tag for child in settings][:2] == [f"{W}updateFields", f"{W}compat"]
    begin = next(
        node for node in root.iter(f"{W}fldChar") if node.get(f"{W}fldCharType") == "begin"
    )
    assert begin.get(f"{W}dirty") == "true"


def test_toc_refresh_resolves_live_field_after_its_visible_title(tmp_path: Path) -> None:
    source = tmp_path / "toc-title.docx"
    output = tmp_path / "toc-title-refreshed.docx"
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        "<w:p><w:r><w:t>目  录</w:t></w:r></w:p>"
        '<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>旧目录</w:t><w:tab/><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        "<w:p><w:r><w:t>摘  要</w:t></w:r></w:p>"
        "<w:sectPr/></w:body></w:document>"
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr(
            "word/settings.xml",
            (f'<w:settings xmlns:w="{W[1:-1]}"><w:compat/></w:settings>').encode(),
        )

    mutate_objects(
        source,
        output,
        mutations=[
            ObjectMutation(
                selected=InspectedObject(
                    locator="/body/p[1]",
                    kind="paragraph",
                    text="目  录",
                    style=None,
                    format={},
                    object_ref={},
                ),
                action="refresh_toc",
                toc_entries=(
                    TocEntry(
                        selected=InspectedObject(
                            locator="/body/p[3]",
                            kind="paragraph",
                            text="摘  要",
                            style=None,
                            format={},
                            object_ref={},
                        ),
                        level=1,
                    ),
                ),
            )
        ],
    )

    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = root.findall(f"{W}body/{W}p")
    assert "".join(node.text or "" for node in paragraphs[0].iter(f"{W}t")) == "目  录"
    assert "".join(node.text or "" for node in paragraphs[1].iter(f"{W}t")) == "摘  要1"
    assert "TOC" in "".join(node.text or "" for node in root.iter(f"{W}instrText"))


def test_toc_refresh_does_not_duplicate_a_preserved_next_page_section(tmp_path: Path) -> None:
    source = tmp_path / "toc-with-boundary.docx"
    output = tmp_path / "toc-with-boundary-refreshed.docx"
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        '<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>旧目录</w:t><w:tab/><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        '<w:p><w:pPr><w:sectPr><w:type w:val="nextPage"/></w:sectPr></w:pPr>'
        "<w:r><w:t>应删除说明</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>摘  要</w:t></w:r></w:p>"
        "<w:sectPr/></w:body></w:document>"
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr(
            "word/settings.xml",
            (f'<w:settings xmlns:w="{W[1:-1]}"><w:compat/></w:settings>').encode(),
        )
    toc = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="旧目录",
        style="TOC1",
        format={},
        object_ref={},
    )
    instruction = InspectedObject(
        locator="/body/p[2]",
        kind="paragraph",
        text="应删除说明",
        style=None,
        format={},
        object_ref={},
    )
    entry = TocEntry(
        selected=InspectedObject(
            locator="/body/p[3]",
            kind="paragraph",
            text="摘  要",
            style=None,
            format={},
            object_ref={},
        ),
        level=1,
    )

    mutate_objects(
        source,
        output,
        mutations=[
            ObjectMutation(selected=toc, action="refresh_toc", toc_entries=(entry,)),
            ObjectMutation(selected=instruction, action="remove_object"),
        ],
    )

    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = root.findall(f"{W}body/{W}p")
    boundary = paragraphs[1]
    title = paragraphs[2]
    assert "".join(node.text or "" for node in boundary.iter(f"{W}t")) == ""
    assert boundary.find(f"{W}pPr/{W}sectPr/{W}type").get(f"{W}val") == "nextPage"
    assert title.find(f"{W}pPr/{W}pageBreakBefore") is None


def test_template_edit_refreshes_toc_as_one_compound_object(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    # The live cache may not contain every level that the Agent selects for the
    # rebuilt TOC. Styles for newly introduced levels still need durable tabs
    # and effective formatting before Word regenerates the field.
    _append_toc_and_titles(
        source,
        cached_levels=(1, 2),
        unselected_sources=True,
    )
    _, document = service._register_source()
    inspection = service._inspection(document)
    toc = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph"
        and item.style
        and item.style.casefold().replace(" ", "") == "toc1"
    )
    title_levels = {
        "【中文摘要】": 1,
        "【英文摘要】": 1,
        "【一级章标题】": 1,
        "【二级标题】": 2,
        "【三级标题】": 3,
        "【附录标题】": 1,
    }
    titles = {
        item.text: item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text in title_levels
    }

    result, _ = service.edit(
        {
            "operations": [
                {
                    "action": "normalize_effective_format",
                    "object_ref": toc.object_ref,
                    "effective_format": {"color": "black", "underline": "none"},
                },
                {
                    "action": "refresh_toc",
                    "object_ref": toc.object_ref,
                    "effective_format": {"color": "black", "underline": "none"},
                    "entries": list(
                        reversed(
                            [
                                {
                                    "object_ref": titles[text].object_ref,
                                    "level": level,
                                }
                                for text, level in title_levels.items()
                            ]
                        )
                    ),
                },
            ],
        }
    )

    assert result["generated_content"] == [
        {
            "field_id": "generated.toc",
            "entry_count": 6,
            "live_field": True,
            "update_on_open": True,
        }
    ]
    assert result["effects"]["effective_format_changes"][0]["requested"] == {
        "color": "black",
        "underline": "none",
    }
    assert result["effects"]["absorbed_operations"][0]["reason"] == (
        "effective_format_merged_into_compound_action"
    )
    assert result["effects"]["style_scope_changes"] == [
        {
            "style_id": "Hyperlink",
            "scope": "document_character_style",
            "reason": "preserve_toc_effective_format_after_field_update",
        }
    ]
    assert [
        (item["level"], item["outline_level"])
        for item in result["effects"]["toc_source_levels"]
    ] == [(1, 0), (1, 0), (1, 0), (2, 1), (3, 2), (1, 0)]
    suppressed = {
        item["text"]: item for item in result["effects"]["toc_suppressed_sources"]
    }
    assert suppressed["目  录"] == {
        "text": "目  录",
        "previous_outline_level": 0,
        "source": "built_in_heading_style",
        "outline_level": 9,
        "changed": True,
    }
    assert suppressed["【未入选正文】"] == {
        "text": "【未入选正文】",
        "previous_outline_level": 2,
        "source": "paragraph_outline_level",
        "outline_level": 9,
        "changed": True,
    }
    assert result["structural_risks"] == [
        {
            "code": "shared_character_style_override",
            "severity": "warning",
            "style_id": "Hyperlink",
            "scope": "document_character_style",
            "reason": "preserve_toc_effective_format_after_field_update",
        }
    ]
    _, changed_path = service._resolve_document(result["document_ref"])
    changed = service._inspection(changed_path)
    toc_rows = [
        item.text
        for item in changed.objects
        if item.kind == "paragraph" and item.style and item.style.casefold().startswith("toc")
    ]
    assert toc_rows == [f"{text}\t1" for text in title_levels]
    assert [
        item.style.casefold()
        for item in changed.objects
        if item.kind == "paragraph" and item.style and item.style.casefold().startswith("toc")
    ] == ["toc 1", "toc 1", "toc 1", "toc 2", "toc 3", "toc 1"]
    with zipfile.ZipFile(changed_path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
        styles_root = ET.fromstring(archive.read("word/styles.xml"))
    toc_styles = {
        name.get(f"{W}val"): style
        for style in styles_root.findall(f"{W}style")
        if (name := style.find(f"{W}name")) is not None
        and name.get(f"{W}val") in {"toc 1", "toc 2", "toc 3"}
    }
    hyperlink_style = next(
        style
        for style in styles_root.findall(f"{W}style")
        if style.get(f"{W}styleId") == "Hyperlink"
    )
    assert hyperlink_style.find(f"{W}rPr/{W}color").get(f"{W}val") == "000000"
    assert hyperlink_style.find(f"{W}rPr/{W}u").get(f"{W}val") == "none"
    for level in range(1, 4):
        style = toc_styles[f"toc {level}"]
        assert style.find(f"{W}rPr/{W}rFonts") is not None
        assert style.find(f"{W}rPr/{W}b").get(f"{W}val") == "0"
        assert style.find(f"{W}rPr/{W}sz").get(f"{W}val") == "28"
        color = style.find(f"{W}rPr/{W}color")
        assert color is not None
        assert color.get(f"{W}val") == "000000"
        assert style.find(f"{W}rPr/{W}u").get(f"{W}val") == "none"
        assert style.find(f"{W}pPr/{W}jc").get(f"{W}val") == "left"
        assert style.find(f"{W}pPr/{W}tabs/{W}tab").get(f"{W}leader") == "dot"
    assert toc_styles["toc 2"].find(f"{W}pPr/{W}ind").get(f"{W}left") == "420"
    assert toc_styles["toc 3"].find(f"{W}pPr/{W}ind").get(f"{W}left") == "840"
    refreshed_paragraphs = [
        paragraph
        for paragraph in document_root.iter(f"{W}p")
        if (paragraph_style := paragraph.find(f"{W}pPr/{W}pStyle")) is not None
        and paragraph_style.get(f"{W}val") in {"TOC1", "TOC2", "TOC3"}
    ]
    assert all(
        color.get(f"{W}val") == "000000"
        for paragraph in refreshed_paragraphs
        for color in paragraph.findall(f".//{W}color")
    )
    assert all(
        underline.get(f"{W}val") == "none"
        for paragraph in refreshed_paragraphs
        for underline in paragraph.findall(f".//{W}u")
    )
    source_outline_levels = {
        "".join(node.text or "" for node in paragraph.iter(f"{W}t")): outline.get(f"{W}val")
        for paragraph in document_root.iter(f"{W}p")
        if (outline := paragraph.find(f"{W}pPr/{W}outlineLvl")) is not None
    }
    assert source_outline_levels == {
        "目  录": "9",
        "【未入选正文】": "9",
        "【中文摘要】": "0",
        "【英文摘要】": "0",
        "【一级章标题】": "0",
        "【二级标题】": "1",
        "【三级标题】": "2",
        "【附录标题】": "0",
    }
    toc_locators = [
        item.locator
        for item in changed.objects
        if item.kind == "paragraph" and item.style and item.style.casefold().startswith("toc")
    ]
    effective_toc_objects = [
        item
        for item in changed.objects
        if item.kind in {"paragraph", "run"}
        and any(
            item.locator == locator or item.locator.startswith(f"{locator}/")
            for locator in toc_locators
        )
    ]
    assert all(
        str(item.format.get("effective.color", "#000000")).casefold()
        in {"#000000", "000000", "black", "auto"}
        for item in effective_toc_objects
    )


def test_toc_row_effective_normalization_stabilizes_hyperlink_style(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_toc_and_titles(source)
    _, document = service._register_source()
    inspection = service._inspection(document)
    toc = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph"
        and item.style
        and item.style.casefold().replace(" ", "") == "toc1"
    )
    title = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "【一级章标题】"
    )

    refreshed, _ = service.edit(
        {
            "operations": [
                {
                    "action": "refresh_toc",
                    "object_ref": toc.object_ref,
                    "field_id": "generated.toc",
                    "entries": [{"object_ref": title.object_ref, "level": 1}],
                }
            ]
        }
    )

    assert refreshed["effects"]["style_scope_changes"] == []
    _, refreshed_path = service._resolve_document(refreshed["document_ref"])
    refreshed_inspection = service._inspection(refreshed_path)
    refreshed_row = next(
        item
        for item in refreshed_inspection.objects
        if item.kind == "paragraph"
        and item.style
        and item.style.casefold().replace(" ", "") == "toc1"
    )
    normalized, _ = service.edit(
        {
            "operations": [
                {
                    "action": "normalize_effective_format",
                    "object_ref": refreshed_row.object_ref,
                    "effective_format": {"color": "black", "underline": "none"},
                }
            ]
        }
    )

    assert normalized["effects"]["style_scope_changes"] == [
        {
            "style_id": "Hyperlink",
            "scope": "document_character_style",
            "reason": "preserve_toc_effective_format_after_field_update",
        }
    ]
    assert normalized["structural_risks"] == [
        {
            "code": "shared_character_style_override",
            "severity": "warning",
            "style_id": "Hyperlink",
            "scope": "document_character_style",
            "reason": "preserve_toc_effective_format_after_field_update",
        }
    ]
    _, normalized_path = service._resolve_document(normalized["document_ref"])
    with zipfile.ZipFile(normalized_path) as archive:
        styles_root = ET.fromstring(archive.read("word/styles.xml"))
    hyperlink_style = next(
        style
        for style in styles_root.findall(f"{W}style")
        if style.get(f"{W}styleId") == "Hyperlink"
    )
    assert hyperlink_style.find(f"{W}rPr/{W}color").get(f"{W}val") == "000000"
    assert hyperlink_style.find(f"{W}rPr/{W}u").get(f"{W}val") == "none"


def test_template_edit_rejects_duplicate_toc_entry_objects(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    _append_toc_and_titles(source)
    _, document = service._register_source()
    inspection = service._inspection(document)
    toc = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph"
        and item.style
        and item.style.casefold().replace(" ", "") == "toc1"
    )
    title = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "【一级章标题】"
    )

    with pytest.raises(ToolFailure) as duplicate:
        service.edit(
            {
                "operations": [
                    {
                        "action": "refresh_toc",
                        "object_ref": toc.object_ref,
                        "entries": [
                            {"object_ref": title.object_ref, "level": 1},
                            {"object_ref": title.object_ref, "level": 2},
                        ],
                    }
                ]
            }
        )

    assert duplicate.value.code == "toc_entry_duplicate"


def test_batch_remove_checks_every_effect_and_returns_one_fresh_version(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path, "S07-ambiguous-anchor")
    source_hash = sha256_file(source)
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = [item for item in inspection.objects if item.kind == "paragraph"]
    assert len(selected) == 2

    result, _ = service.edit(
        {
            "operations": [
                {"action": "remove_object", "object_ref": item.object_ref} for item in selected
            ],
        }
    )

    _, after_path = service._resolve_document(result["document_ref"])
    after = service._inspection(after_path)
    assert all(item.text != "姓名：" for item in after.objects)
    assert sha256_file(source) == source_hash


def test_parent_removal_absorbs_descendant_cleanup_and_commits_once(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    inspection = service._inspection(document)
    parent = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph"
        and item.text.strip()
        and any(
            child.kind == "run"
            and child.locator.startswith(f"{item.locator}/")
            and child.text.strip()
            for child in inspection.objects
        )
    )
    child = next(
        item
        for item in inspection.objects
        if item.kind == "run"
        and item.locator.startswith(f"{parent.locator}/")
        and item.text.strip()
    )

    result, _ = service.edit(
        {
            "operations": [
                {"action": "remove_object", "object_ref": parent.object_ref},
                {"action": "remove_object", "object_ref": child.object_ref},
            ]
        }
    )

    assert result["committed"] is True
    assert result["effects"]["operations"] == 1
    assert result["effects"]["actions"] == {"remove_object": 1}
    absorbed = result["effects"]["absorbed_operations"]
    assert len(absorbed) == 1
    assert absorbed[0]["target"] == child.public()
    assert absorbed[0]["absorbed_by"]["action"] == "remove_object"
    assert absorbed[0]["reason"] == "ancestor_removal"


def test_parent_removal_rejects_descendant_materialization_as_true_conflict(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    inspection = service._inspection(document)
    parent = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph"
        and any(
            child.kind == "run"
            and child.locator.startswith(f"{item.locator}/")
            and child.text.strip()
            for child in inspection.objects
        )
    )
    child = next(
        item
        for item in inspection.objects
        if item.kind == "run"
        and item.locator.startswith(f"{parent.locator}/")
        and item.text.strip()
    )

    with pytest.raises(ToolFailure) as caught:
        service.edit(
            {
                "operations": [
                    {"action": "remove_object", "object_ref": parent.object_ref},
                    {
                        "action": "materialize_slot",
                        "object_ref": child.object_ref,
                        "field_id": "abstract.zh",
                    },
                ]
            }
        )

    assert caught.value.code == "batch_operations_conflict"


def test_removal_preserves_word_boundaries_ranges_anchors_and_table_wrapper(
    tmp_path: Path,
) -> None:
    source = tmp_path / "boundary-source.docx"
    output = tmp_path / "boundary-output.docx"
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        '<w:p><w:pPr><w:pageBreakBefore/><w:sectPr><w:type w:val="nextPage"/>'
        '</w:sectPr></w:pPr><w:bookmarkStart w:id="1" w:name="mark"/>'
        '<w:commentRangeStart w:id="2"/><w:r><w:fldChar w:fldCharType="begin"/>'
        '<w:instrText> PAGE </w:instrText><w:br w:type="page"/><w:drawing/>'
        '<w:footnoteReference w:id="3"/><w:endnoteReference w:id="4"/>'
        '<w:t>应删除说明</w:t></w:r><w:commentRangeEnd w:id="2"/>'
        '<w:bookmarkEnd w:id="1"/></w:p>'
        "<w:tbl><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl><w:p/>"
        "<w:sectPr/></w:body></w:document>"
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
    boundary = InspectedObject(
        locator="/body/p[1]",
        kind="paragraph",
        text="应删除说明",
        style=None,
        format={},
        object_ref={"object_id": "obj-boundary"},
    )
    wrapper = InspectedObject(
        locator="/body/p[2]",
        kind="paragraph",
        text="",
        style=None,
        format={},
        object_ref={"object_id": "obj-wrapper"},
    )

    receipt = mutate_objects(
        source,
        output,
        mutations=[
            ObjectMutation(selected=boundary, action="remove_object"),
            ObjectMutation(selected=wrapper, action="remove_object"),
        ],
    )

    kinds = {item["kind"] for item in receipt["preserved_boundaries"]}
    assert kinds == {
        "section_boundary",
        "page_break_before",
        "explicit_page_break",
        "bookmark_range",
        "comment_range",
        "footnote_reference",
        "endnote_reference",
        "field_boundary",
        "drawing_anchor",
        "table_wrapper_paragraph",
    }
    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    assert "应删除说明" not in "".join(node.text or "" for node in root.iter(f"{W}t"))
    for tag in (
        "sectPr",
        "pageBreakBefore",
        "br",
        "bookmarkStart",
        "bookmarkEnd",
        "commentRangeStart",
        "commentRangeEnd",
        "fldChar",
        "instrText",
        "drawing",
        "footnoteReference",
        "endnoteReference",
    ):
        assert next(root.iter(f"{W}{tag}"), None) is not None
    assert len(root.findall(f".//{W}body/{W}p")) == 2


def test_ensure_page_start_is_idempotent_and_never_inserts_a_blank_page(
    tmp_path: Path,
) -> None:
    source = tmp_path / "page-start-source.docx"
    first = tmp_path / "page-start-first.docx"
    second = tmp_path / "page-start-second.docx"
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        "<w:p><w:r><w:t>前置内容</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>摘  要</w:t></w:r></w:p><w:sectPr/>"
        "</w:body></w:document>"
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
    abstract = InspectedObject(
        locator="/body/p[2]",
        kind="paragraph",
        text="摘  要",
        style=None,
        format={},
        object_ref={"object_id": "obj-abstract"},
    )

    first_receipt = mutate_objects(
        source,
        first,
        mutations=[ObjectMutation(selected=abstract, action="ensure_page_start")],
    )
    second_receipt = mutate_objects(
        first,
        second,
        mutations=[ObjectMutation(selected=abstract, action="ensure_page_start")],
    )

    assert first_receipt["page_start_results"][0]["changed"] is True
    assert second_receipt["page_start_results"][0]["changed"] is False
    with zipfile.ZipFile(second) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = root.findall(f".//{W}body/{W}p")
    assert len(paragraphs) == 2
    assert len(paragraphs[1].findall(f"{W}pPr/{W}pageBreakBefore")) == 1


def test_remove_only_batch_returns_immediate_fill_interface_recovery_hint(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _append_plain_paragraphs(source, ["样例一", "样例二", "样例三"])
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = [item for item in inspection.objects if item.kind == "paragraph"][:5]
    assert len(selected) == 5

    result, _ = service.edit(
        {
            "operations": [
                {"action": "remove_object", "object_ref": item.object_ref} for item in selected
            ],
        }
    )

    assert "created no fillable slot" in result["guidance"]
    assert "previous_document_ref" in result["guidance"]


def test_vml_textbox_is_one_visible_editable_shape_object(tmp_path: Path) -> None:
    root, source = _task(tmp_path)
    _inject_vml_textbox(source, "本说明阅读后请删除，包括本文本框")
    service = TemplateWorkspaceService(
        task_root=root,
        field_registry=REGISTRY,
        visual=FakeVisual(),  # type: ignore[arg-type]
    )
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(item for item in inspection.objects if item.kind == "shape")

    assert selected.text == "本说明阅读后请删除，包括本文本框"
    changed, _ = service.edit(
        {
            "operations": [{"action": "remove_object", "object_ref": selected.object_ref}],
        }
    )

    _, changed_path = service._resolve_document(changed["document_ref"])
    after = service._inspection(changed_path)
    assert all(item.kind != "shape" for item in after.objects)
    with zipfile.ZipFile(changed_path) as archive:
        xml = ET.fromstring(archive.read("word/document.xml"))
    assert xml.find(f".//{V}shape") is None


def test_object_ref_is_shared_by_focus_visual_and_edit_and_is_version_bound(
    tmp_path: Path,
) -> None:
    service, visual, _ = _service(tmp_path)
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(item for item in inspection.objects if item.kind == "paragraph")

    focused, _ = service.view({"action": "focus", "object_ref": selected.object_ref})
    assert visual.last_review is not None
    assert visual.last_review["regions"][0]["object_ref"] == selected.object_ref
    changed, _ = service.edit(
        {
            "operations": [{"action": "clear_content", "object_ref": selected.object_ref}],
        }
    )
    mixed_ref = dict(selected.object_ref)
    mixed_ref["document_sha256"] = changed["document_sha256"]

    assert focused["local_context"]["target"]["object_ref"] == {
        "object_id": selected.object_ref["object_id"]
    }
    with pytest.raises(ToolFailure) as captured:
        service.view({"action": "focus", "object_ref": mixed_ref})
    assert captured.value.code in {
        "invalid_object_ref",
        "object_fingerprint_mismatch",
        "stale_object_ref",
    }


def test_final_review_requires_explicit_clean_verdict_for_every_page(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(
        item
        for item in inspection.objects
        if item.kind == "paragraph" and item.text == "请在此填写"
    )
    changed, _ = service.edit(
        {
            "operations": [{"action": "remove_object", "object_ref": selected.object_ref}],
        }
    )
    _finish_local_work(service, source)

    first, first_images = service.final_review({"document_ref": changed["document_ref"]})

    assert first["phase"] == "final_visual_qa"
    assert first["batch_pages"] == [1]
    assert first["next_cursor"] == "fake-final-page-2"
    assert first_images == [Path("/tmp/final-page-1.png")]
    assert not service.final_reviews.exists()
    first_receipt = _record_clean_batch(service, first)
    assert first_receipt["reviewed_pages"] == [1]
    assert first_receipt["coverage_complete"] is False
    with pytest.raises(ToolFailure) as incomplete:
        service.publish({"document_ref": changed["document_ref"]})
    assert incomplete.value.code == "final_visual_review_incomplete"

    second, second_images = service.final_review(
        {
            "document_ref": changed["document_ref"],
            "cursor": first["next_cursor"],
        }
    )

    assert second["batch_pages"] == [2]
    assert second["next_cursor"] is None
    assert second_images == [Path("/tmp/final-page-2.png")]
    final_receipt = _record_clean_batch(service, second)
    assert final_receipt["reviewed_pages"] == [1, 2]
    assert final_receipt["coverage_complete"] is True
    assert final_receipt["status"] == "clean"
    published = service.publish({"document_ref": changed["document_ref"]})

    output = service.task_root / "output/final-template.docx"
    assert published["artifact_path"] == "output/final-template.docx"
    assert published["counts"]["remove"] == 1
    assert [item.name for item in (service.task_root / "output").iterdir()] == [
        "final-template.docx"
    ]
    assert sha256_file(output) == published["template_sha256"]
    with pytest.raises(ToolFailure) as duplicate:
        service.publish({"document_ref": changed["document_ref"]})
    assert duplicate.value.code == "final_template_exists"


def test_publish_rejects_an_unreviewed_exact_version(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    document_ref, _ = service._register_source()
    _finish_local_work(service, source)

    with pytest.raises(ToolFailure) as missing:
        service.publish({"document_ref": document_ref})

    assert missing.value.code == "final_visual_review_missing"


def test_publish_rejects_complete_page_coverage_with_a_visual_defect(
    tmp_path: Path,
) -> None:
    service, _, source = _service(tmp_path)
    document_ref, _ = service._register_source()
    _finish_local_work(service, source)
    first, _ = service.final_review({"document_ref": document_ref})
    _record_clean_batch(service, first)
    second, _ = service.final_review(
        {"document_ref": document_ref, "cursor": first["next_cursor"]}
    )
    receipt = service.record_final_review_verdict(
        document_ref=document_ref,
        render_ref=second["render_ref"],
        page_count=second["page_count"],
        verdicts=[
            {
                "page": 2,
                "verdict": "defect",
                "defects": [
                    {
                        "category": "clipping",
                        "description": "The bottom line is visibly clipped.",
                    }
                ],
            }
        ],
    )

    assert receipt["coverage_complete"] is True
    assert receipt["status"] == "defects"
    with pytest.raises(ToolFailure) as rejected:
        service.publish({"document_ref": document_ref})
    assert rejected.value.code == "final_visual_review_incomplete"


def test_final_review_rejects_local_work_and_stale_document_versions(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path)
    original_ref, document = service._register_source()

    with pytest.raises(ToolFailure) as premature:
        service.final_review({"document_ref": original_ref})
    assert premature.value.code == "final_review_not_ready"

    _finish_local_work(service, source)
    first, _ = service.final_review({"document_ref": original_ref})
    _record_clean_batch(service, first)
    second, _ = service.final_review(
        {"document_ref": original_ref, "cursor": first["next_cursor"]}
    )
    receipt = _record_clean_batch(service, second)
    assert receipt["coverage_complete"] is True

    inspection = service._inspection(document)
    selected = next(item for item in inspection.objects if item.kind == "paragraph")
    changed, _ = service.edit(
        {
            "operations": [{"action": "clear_content", "object_ref": selected.object_ref}],
        }
    )

    with pytest.raises(ToolFailure) as stale_review:
        service.final_review({"document_ref": original_ref})
    assert stale_review.value.code == "final_review_document_not_current"
    with pytest.raises(ToolFailure) as stale_publish:
        service.publish({"document_ref": original_ref})
    assert stale_publish.value.code == "publish_document_not_current"
    with pytest.raises(ToolFailure) as changed_not_closed:
        service.final_review({"document_ref": changed["document_ref"]})
    assert changed_not_closed.value.code == "final_review_not_ready"


def test_final_review_propagates_renderer_failure_without_publish_receipt(
    tmp_path: Path,
) -> None:
    root, source = _task(tmp_path)
    service = TemplateWorkspaceService(
        task_root=root,
        field_registry=REGISTRY,
        visual=FailingVisual(),  # type: ignore[arg-type]
    )
    document_ref, _ = service._register_source()
    _finish_local_work(service, source)

    with pytest.raises(ToolFailure) as failed:
        service.final_review({"document_ref": document_ref})

    assert failed.value.code == "visual_renderer_failed"
    assert not service.final_reviews.exists()

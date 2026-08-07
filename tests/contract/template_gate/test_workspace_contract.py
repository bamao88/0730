from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.template.object_mutation import (
    ObjectMutation,
    TocEntry,
    mutate_objects,
)
from docfit.template.workspace import TemplateWorkspaceService
from docfit.tools.inspection import InspectedObject, Inspection
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.template_schemas.workspace import TEMPLATE_REGISTRY_SCHEMA
from docfit.tools.template_tools import (
    TEMPLATE_FULL_TOOL_NAMES,
    TEMPLATE_LOGICAL_TOOL_NAMES,
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
    ET.SubElement(blank, f"{W}t", {f"{XML}space": "preserve"}).text = "            "
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


def _append_toc_and_titles(document: Path) -> None:
    with zipfile.ZipFile(document) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    styles = ET.fromstring(parts["word/styles.xml"])
    for level in range(1, 4):
        style = ET.SubElement(
            styles,
            f"{W}style",
            {f"{W}type": "paragraph", f"{W}styleId": f"TOC{level}"},
        )
        ET.SubElement(style, f"{W}name", {f"{W}val": f"toc {level}"})
        ET.SubElement(style, f"{W}basedOn", {f"{W}val": "Normal"})
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
    for level, text in [(1, "第X章 XXX"), (2, "1 XXX"), (3, "1.1 XXX")]:
        paragraph = ET.Element(f"{W}p")
        properties = ET.SubElement(paragraph, f"{W}pPr")
        ET.SubElement(properties, f"{W}pStyle", {f"{W}val": f"TOC{level}"})
        if level == 1:
            begin = ET.SubElement(paragraph, f"{W}r")
            ET.SubElement(begin, f"{W}fldChar", {f"{W}fldCharType": "begin"})
            instruction = ET.SubElement(paragraph, f"{W}r")
            ET.SubElement(instruction, f"{W}instrText").text = ' TOC \\o "1-3" '
            separate = ET.SubElement(paragraph, f"{W}r")
            ET.SubElement(separate, f"{W}fldChar", {f"{W}fldCharType": "separate"})
        run = ET.SubElement(paragraph, f"{W}r")
        ET.SubElement(run, f"{W}t").text = text
        ET.SubElement(run, f"{W}tab")
        ET.SubElement(run, f"{W}t").text = str(level)
        if level == 3:
            ET.SubElement(run, f"{W}fldChar", {f"{W}fldCharType": "end"})
        body.insert(position, paragraph)
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


def test_agent_surface_is_four_direct_tools_without_plan_protocol() -> None:
    assert TEMPLATE_LOGICAL_TOOL_NAMES == (
        "template_view",
        "template_registry",
        "template_edit",
        "template_publish",
    )
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
        "review_page",
    ):
        assert forbidden not in schemas
    assert "'page'" not in str(TEMPLATE_TOOLS[0].input_schema)


def test_open_next_and_search_expose_only_one_local_visual_region(tmp_path: Path) -> None:
    service, _, source = _service(tmp_path, "S07-ambiguous-anchor")
    _append_plain_paragraphs(source, [f"相邻对象{index}" for index in range(8)])

    opened, images = service.view({"action": "open"})
    next_region, next_images = service.view(
        {
            "action": "next",
            "region_ref": opened["current_region"]["region_ref"],
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
    assert set(opened["current_region"]["target"]["object_ref"]) == {"object_id"}
    assert all(
        set(item["object_ref"]) == {"object_id"}
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
        "evidence",
    }
    assert next_region["current_region"]["region_ref"] != opened["current_region"]["region_ref"]
    assert next_region["navigation"]["completed_regions"] == 1
    assert searched["match_count"] > 1
    assert len(searched["matches"]) <= 5


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
        ),
        summary={},
        risks=(),
        warnings=(),
        provider={},
    )

    summary = TemplateWorkspaceService._checkpoint_summary(inspection)

    assert summary["toc"] == {
        "entry_count": 2,
        "sample_marker_count": 1,
        "sample_marker_examples": ["第X章 XXX\tXX"],
        "missing_body_heading_types": ["body.heading.level1"],
        "refresh_needed": True,
    }


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
    assert 1 <= len(pending["title_candidates"]) <= 16
    assert all(set(item["object_ref"]) == {"object_id"} for item in pending["title_candidates"])
    assert "non-semantic suggestions" in pending["guidance"]


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
    }
    adjacent_label = next(
        item for item in context["adjacent_objects"] if item["text"] == "题目："
    )
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
            "queries": [
                {"object_ref": selected.object_ref, "query": "中文姓名"},
                {"object_ref": second.object_ref, "field_id": "abstract.zh"},
                {
                    "object_ref": second.object_ref,
                    "field_id": "body.heading.level1",
                },
            ]
        }
    )

    assert result["document_ref"] == document_ref
    assert len(result["results"]) == 3
    assert result["results"][0]["matches"][0]["field_id"] == "author.name.zh"
    assert result["results"][1]["matches"][0]["field_id"] == "abstract.zh"
    assert result["results"][2]["matches"][0]["semantic_object_type"] == {
        "type_id": "body.heading.level1",
        "role": "heading",
        "repeatable": True,
        "parent_type": "body.chapters",
        "toc_level": 1,
    }
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
            "queries": [
                {
                    "object_ref": selected.object_ref,
                    "field_id": "thesis.title",
                },
                {
                    "object_ref": selected.object_ref,
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


def test_registry_ignores_an_empty_optional_field_id_when_query_is_present(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = next(
        item for item in service._inspection(document).objects if "请在此填写" in item.text
    )

    result = service.registry_query(
        {
            "queries": [
                {
                    "object_ref": selected.object_ref,
                    "field_id": "",
                    "query": "thesis title on cover",
                }
            ]
        }
    )

    assert result["results"][0]["operation"] == "search"
    assert result["results"][0]["matches"][0]["field_id"] == "thesis.title.zh"


def test_template_object_identity_does_not_depend_on_model_echoed_fingerprint(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    selected = service._inspection(document).objects[0]
    advisory_ref = dict(selected.object_ref)
    advisory_ref["expected_fingerprint"] = "a" * 63

    result = service.registry_query(
        {
            "queries": [
                {
                    "object_ref": advisory_ref,
                    "field_id": "thesis.title.zh",
                }
            ]
        }
    )

    ref_schema = TEMPLATE_REGISTRY_SCHEMA["properties"]["queries"]["items"]["properties"][
        "object_ref"
    ]
    assert ref_schema["required"] == ["object_id"]
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


def test_materialize_slot_rejects_a_paragraph_that_contains_label_and_blank_runs(
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

    with pytest.raises(ToolFailure) as caught:
        service.edit(
            {
                "operations": [
                    {
                        "action": "materialize_slot",
                        "object_ref": paragraph.object_ref,
                        "field_id": "advisor.name.zh",
                    }
                ]
            }
        )

    assert caught.value.code == "slot_boundary_too_broad"


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

    assert caught.value.code == "duplicate_operation_target"


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


def test_slot_uses_brackets_only_and_agent_can_drop_direct_color_without_losing_style(
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
                    "clear_direct_format": ["color"],
                }
            ],
        }
    )

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
    assert control.find(f".//{W}color") is None
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
            "clear_direct_format": ["color"],
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
    assert group.find(f".//{W}color") is None
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
                            "clear_direct_format": ["color"],
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
            "member_count": 3,
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
    assert structures[0].text == "【一级章标题】【二级标题】【正文段落】"
    published = service.publish({"document_ref": replacement_result["document_ref"]})
    assert published["counts"]["slot"] == 3
    fill_contract = json.loads(
        (service.root / "publication/fill-contract.json").read_text(encoding="utf-8")
    )
    assert len(fill_contract["structures"]) == 1
    assert [item["field"]["field_id"] for item in fill_contract["slots"]] == [
        field_id for _, _, field_id in replacement_samples
    ]


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
        "<w:r><w:t>第三小节</w:t><w:tab/>"
        '<w:fldChar w:fldCharType="end"/></w:r></w:p>'
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
            locator="/body/p[1]",
            kind="paragraph",
            text="第一章",
            style="TOC1",
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
    following_title = root.findall(f"{W}body/{W}p")[6]
    assert following_title.find(f"{W}pPr/{W}pageBreakBefore") is not None
    assert settings.find(f"{W}updateFields").get(f"{W}val") == "true"
    assert [child.tag for child in settings][:2] == [f"{W}updateFields", f"{W}compat"]
    begin = next(
        node for node in root.iter(f"{W}fldChar") if node.get(f"{W}fldCharType") == "begin"
    )
    assert begin.get(f"{W}dirty") == "true"


def test_template_edit_refreshes_toc_as_one_compound_object(tmp_path: Path) -> None:
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
                    "action": "refresh_toc",
                    "object_ref": toc.object_ref,
                    "field_id": "generated.toc",
                    "entries": [
                        {
                            "object_ref": titles[text].object_ref,
                            "level": level,
                        }
                        for text, level in title_levels.items()
                    ],
                }
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


def test_publish_requires_local_feedback_not_all_page_coverage_and_outputs_one_word(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
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
    service, _, _ = _service(tmp_path)
    document_ref, _ = service._register_source()

    with pytest.raises(ToolFailure) as missing:
        service.publish({"document_ref": document_ref})

    assert missing.value.code == "final_visual_review_missing"

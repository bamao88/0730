from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.template.object_mutation import ObjectMutation, mutate_objects
from docfit.template.workspace import TemplateWorkspaceService
from docfit.tools.inspection import InspectedObject
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.template_tools import (
    TEMPLATE_FULL_TOOL_NAMES,
    TEMPLATE_LOGICAL_TOOL_NAMES,
    TEMPLATE_TOOLS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "evals/template-extraction/fixtures"
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"


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
                "evidence": [{"pages": pages}],
                "next_cursor": None,
                "mode": args["mode"],
            },
            [Path("/tmp/current-page.png")],
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
    for forbidden in ("yaml", "compiler", "plan_path", "output_docx", "attempt"):
        assert forbidden not in schemas


def test_open_page_and_search_expose_only_current_visual_context(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path, "S07-ambiguous-anchor")

    opened, images = service.view({"action": "open"})
    page, page_images = service.view(
        {
            "action": "page",
            "document_ref": opened["document_ref"],
            "page": 2,
        }
    )
    searched, _ = service.view(
        {
            "action": "search",
            "document_ref": opened["document_ref"],
            "query": "姓名",
        }
    )

    assert images == [Path("/tmp/current-page.png")]
    assert page_images == [Path("/tmp/current-page.png")]
    assert "objects" not in opened
    assert opened["current_page"]["page"] == 1
    assert page["current_page"]["page"] == 2
    assert 1 <= len(opened["current_page"]["objects"]) <= 192
    assert "overview" not in opened["visual"]
    assert "local_context" not in opened
    assert all(
        set(item) <= {"object_ref", "type", "text", "slot"}
        for item in page["current_page"]["objects"]
    )
    assert searched["match_count"] > 1
    assert len(searched["matches"]) <= 5


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
            ]
        }
    )

    assert result["document_ref"] == document_ref
    assert len(result["results"]) == 2
    assert result["results"][0]["matches"][0]["field_id"] == "author.name.zh"
    assert result["results"][1]["matches"][0]["field_id"] == "abstract.zh"
    assert "fields" not in result


def test_batch_edit_is_atomic_returns_same_page_feedback_and_preserves_source(
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
            "review_page": 1,
        }
    )

    assert result["committed"] is True
    assert result["document_sha256"] != source_hash
    assert len(result["applied"]) == 2
    assert result["slots"][0]["field_id"] == "abstract.zh"
    assert result["slots"][0]["placeholder"] == "【中文摘要】"
    assert set(result["applied"][0]) <= {"action", "type", "text", "field_id", "slot_id"}
    assert result["reviewed_page"] == 1
    assert result["current_page"]["page"] == 1
    assert images == [Path("/tmp/current-page.png")]
    assert visual.last_review is not None
    assert visual.last_review["pages"] == [1]
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


def test_clear_content_preserves_selected_container_and_its_metadata(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    _, document = service._register_source()
    inspection = service._inspection(document)
    selected = next(item for item in inspection.objects if item.kind == "sdt")

    result, _ = service.edit(
        {
            "operations": [
                {"action": "clear_content", "object_ref": selected.object_ref}
            ],
            "review_page": 1,
        }
    )

    _, changed_path = service._resolve_document(result["document_ref"])
    changed = service._inspection(changed_path)
    preserved = next(item for item in changed.objects if item.kind == "sdt")
    assert preserved.text == ""
    assert preserved.format["alias"] == "author.name.zh"
    assert preserved.format["tag"] == "docfit.cover.student_name"


def test_clear_content_collapses_toc_cache_but_preserves_field_boundaries(
    tmp_path: Path,
) -> None:
    source = tmp_path / "toc.docx"
    output = tmp_path / "toc-cleared.docx"
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        '<w:p><w:pPr/><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>第一章</w:t><w:tab/></w:r></w:p>'
        '<w:p><w:pPr/><w:r><w:t>第二章</w:t><w:tab/></w:r></w:p>'
        '<w:p><w:pPr/><w:r><w:t>第三章</w:t><w:tab/>'
        '<w:fldChar w:fldCharType="end"/></w:r></w:p>'
        '<w:sectPr/></w:body></w:document>'
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)
    mutations = [
        ObjectMutation(
            selected=InspectedObject(
                locator=f"/body/p[{index}]",
                kind="paragraph",
                text=f"第{index}章",
                style="toc 1",
                format={},
                object_ref={},
            ),
            action="clear_content",
        )
        for index in range(1, 4)
    ]

    mutate_objects(source, output, mutations=mutations)

    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = root.findall(f"{W}body/{W}p")
    field_types = [node.get(f"{W}fldCharType") for node in root.iter(f"{W}fldChar")]
    assert len(paragraphs) == 2
    assert field_types == ["begin", "separate", "end"]
    assert "TOC" in "".join(node.text or "" for node in root.iter(f"{W}instrText"))
    assert all(node.text in {None, ""} for node in root.iter(f"{W}t"))
    assert list(root.iter(f"{W}tab")) == []


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
                {"action": "remove_object", "object_ref": item.object_ref}
                for item in selected
            ],
            "review_page": 1,
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
                {"action": "remove_object", "object_ref": item.object_ref}
                for item in selected
            ],
            "review_page": 1,
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
            "operations": [
                {"action": "remove_object", "object_ref": selected.object_ref}
            ],
            "review_page": 1,
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
            "operations": [
                {"action": "clear_content", "object_ref": selected.object_ref}
            ],
            "review_page": 1,
        }
    )
    mixed_ref = dict(selected.object_ref)
    mixed_ref["document_sha256"] = changed["document_sha256"]

    assert focused["local_context"]["current_object"]["object_ref"] == selected.object_ref
    with pytest.raises(ToolFailure) as captured:
        service.view({"action": "focus", "object_ref": mixed_ref})
    assert captured.value.code in {"object_fingerprint_mismatch", "stale_object_ref"}


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
            "operations": [
                {"action": "remove_object", "object_ref": selected.object_ref}
            ],
            "review_page": 1,
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

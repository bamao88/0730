from __future__ import annotations

import zipfile
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from PIL import Image

from docfit.tools.inspection import inspect_document
from docfit.tools.runtime import JsonObject, ToolFailure
from docfit.visual.locator import locate_text
from docfit.visual.renderer import LibreOfficeRenderer, RendererEnvironment
from docfit.visual.service import VisualEvidenceService


class _Renderer:
    calls = 0

    def environment(self) -> RendererEnvironment:
        return RendererEnvironment(
            name="libreoffice",
            version="LibreOffice 25.2.3.2",
            container_image="fixture",
            container_image_digest="sha256:" + "a" * 64,
            font_environment_digest="b" * 64,
            locale="zh_CN.UTF-8",
            pdf_export_options="fixture-options",
        )

    def render(self, input_docx: Path, output_pdf: Path) -> None:
        self.calls += 1
        output_pdf.write_bytes(b"%PDF-fixture")


class _Pdf:
    @staticmethod
    def build_text_index(pdf: Path) -> JsonObject:
        assert pdf.read_bytes().startswith(b"%PDF")
        return {
            "schema_version": 2,
            "page_count": 2,
            "pages": [
                {
                    "page": 1,
                    "width_pt": 600.0,
                    "height_pt": 800.0,
                    "text": "学生姓名 指导教师 职称 重复",
                    "words": [
                        {"text": "学生姓名", "bbox_pdf": [50.0, 50.0, 120.0, 70.0]},
                        {"text": "指导教师", "bbox_pdf": [50.0, 90.0, 120.0, 110.0]},
                        {"text": "职称", "bbox_pdf": [50.0, 130.0, 90.0, 150.0]},
                        {"text": "重复", "bbox_pdf": [50.0, 170.0, 90.0, 190.0]},
                    ],
                },
                {
                    "page": 2,
                    "width_pt": 600.0,
                    "height_pt": 800.0,
                    "text": "重复 第二页",
                    "words": [
                        {"text": "重复", "bbox_pdf": [50.0, 50.0, 90.0, 70.0]},
                        {"text": "第二页", "bbox_pdf": [50.0, 90.0, 100.0, 110.0]},
                    ],
                },
            ],
        }

    @staticmethod
    def rasterize_page(pdf: Path, page: int, dpi: int, output: Path) -> JsonObject:
        assert pdf.is_file()
        Image.new("RGB", (100, 150), (page * 30, dpi % 255, 80)).save(output)
        return {"page": page, "dpi": dpi, "pixel_size": [100, 150]}

    @staticmethod
    def rasterize_region(
        pdf: Path,
        page: int,
        bbox_pdf: list[float],
        dpi: int,
        output: Path,
    ) -> JsonObject:
        assert pdf.is_file()
        Image.new("RGB", (80, 50), (page * 30, dpi % 255, 120)).save(output)
        return {
            "page": page,
            "dpi": dpi,
            "bbox_pdf": bbox_pdf,
            "pixel_size": [80, 50],
        }


class _Office:
    @staticmethod
    def evidence() -> JsonObject:
        return {"name": "officecli", "version": "fixture"}

    @staticmethod
    def query(document: Path, selector: str) -> tuple[JsonObject, ...]:
        assert document.is_file()
        assert selector == "paragraph, table, picture"
        return (
            {"path": "/body/p[1]", "type": "paragraph", "text": "学生姓名"},
            {"path": "/body/p[2]", "type": "paragraph", "text": "指导教师"},
            {"path": "/body/p[3]", "type": "paragraph", "text": "职称"},
        )


class _ShapeOffice(_Office):
    @staticmethod
    def query(document: Path, selector: str) -> tuple[JsonObject, ...]:
        assert document.is_file()
        assert selector == "paragraph, shape"
        return (
            {"path": "/body/p[1]", "type": "paragraph", "text": "学生姓名"},
            {"path": "/body/p[2]", "type": "paragraph", "text": ""},
            {"path": "/body/p[3]", "type": "paragraph", "text": "第二页"},
            {
                "path": "/body/p[2]/r[1]/pict[1]/shape[1]",
                "type": "shape",
                "text": "隐藏的模板说明，包括本文本框",
            },
        )


def _docx(path: Path) -> None:
    content_types = "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>"
    relationships = "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'/>"
    document = (
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        "<w:body><w:p><w:r><w:t>指导教师</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)


def _service(root: Path, renderer: _Renderer | None = None) -> VisualEvidenceService:
    return VisualEvidenceService(
        root,
        renderer=renderer or _Renderer(),  # type: ignore[arg-type]
        pdf=_Pdf(),  # type: ignore[arg-type]
        office=_Office(),  # type: ignore[arg-type]
    )


def test_render_is_content_addressed_and_pages_are_generated_on_demand(tmp_path: Path) -> None:
    document = tmp_path / "current.docx"
    _docx(document)
    renderer = _Renderer()
    service = _service(tmp_path, renderer)

    first, first_images = service.render({"input_docx": document.name, "overview": False})
    second, second_images = service.render({"input_docx": document.name, "overview": False})

    assert first["render_ref"].startswith("render:v2:")
    assert first["renderer"]["name"] == "libreoffice"
    assert first["fidelity"] == "approximate"
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["render_ref"] == first["render_ref"]
    assert renderer.calls == 1
    assert first_images == second_images == []
    render_dir = next((tmp_path / ".docfit/evidence/renders").iterdir())
    views = render_dir / "views"
    assert not views.exists() or not list(views.glob("*.png"))

    review, images = service.review(
        {"render_ref": first["render_ref"], "mode": "pages", "pages": [2]}
    )
    assert len(images) == 1
    assert review["evidence"][0]["page"] == 2
    assert review["evidence"][0]["evidence_ref"].startswith("visual:v2:")


def test_renderer_resolves_a_listed_tag_to_immutable_id_when_tag_inspect_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_id = "sha256:" + "5" * 64
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs: object) -> CompletedProcess[str]:
        calls.append(arguments)
        if arguments[1] == "inspect" and arguments[-1] == "locked:tag":
            return CompletedProcess(arguments, 1, "", "No such image")
        if arguments[1:3] == ["image", "ls"]:
            return CompletedProcess(arguments, 0, f"{image_id}\n", "")
        if arguments[1] == "inspect" and arguments[-1] == image_id:
            return CompletedProcess(arguments, 0, f"{image_id}\n", "")
        if arguments[1] == "run":
            assert image_id in arguments
            return CompletedProcess(
                arguments,
                0,
                "version=LibreOffice 25.2.3.2 520(Build:2)\n"
                "locale=zh_CN.UTF-8\n"
                f"fonts={'6' * 64}\n",
                "",
            )
        raise AssertionError(arguments)

    monkeypatch.setattr("docfit.visual.renderer.subprocess.run", fake_run)

    environment = LibreOfficeRenderer(image="locked:tag", docker="docker").environment()

    assert environment.container_image == "locked:tag"
    assert environment.container_image_digest == image_id
    assert any(arguments[1:3] == ["image", "ls"] for arguments in calls)


def test_regions_use_text_object_and_image_coordinate_selectors(tmp_path: Path) -> None:
    document = tmp_path / "current.docx"
    _docx(document)
    service = _service(tmp_path)
    rendered, _ = service.render({"input_docx": document.name, "overview": False})
    inspected = service.office.query(document, "paragraph, table, picture")
    assert inspected[1]["text"] == "指导教师"
    anchors = service._read_index(  # noqa: SLF001 - contract fixture reads stored evidence
        next((tmp_path / ".docfit/evidence/renders").iterdir())
        / "indexes/semantic-anchors.json"
    )
    object_ref = anchors["anchors"][1]["object_ref"]

    review, images = service.review(
        {
            "render_ref": rendered["render_ref"],
            "mode": "regions",
            "quality": "detail",
            "regions": [
                {"selector": "object_ref", "object_ref": object_ref, "padding": 12},
                {"selector": "text", "text": "指导教师", "occurrence": 1},
            ],
        }
    )
    assert len(images) == 2
    assert [item["mapping_quality"] for item in review["evidence"]] == [
        "exact_text",
        "exact_text",
    ]
    assert review["evidence"][0]["selector"]["object_ref"] == object_ref
    assert review["evidence"][1]["selector"]["text"] == "指导教师"

    grouped, grouped_images = service.review(
        {
            "render_ref": rendered["render_ref"],
            "mode": "regions",
            "regions": [
                {
                    "selector": "object_refs",
                    "object_refs": [item["object_ref"] for item in anchors["anchors"][:3]],
                    "padding": 0,
                }
            ],
        }
    )
    assert len(grouped_images) == 1
    assert grouped["evidence"][0]["mapping_quality"] == "object_group"
    assert grouped["evidence"][0]["bbox_pdf"] == [50.0, 50.0, 120.0, 150.0]

    page_review, _ = service.review(
        {"render_ref": rendered["render_ref"], "mode": "pages", "pages": [1]}
    )
    page_ref = page_review["evidence"][0]["evidence_ref"]
    cropped, crop_images = service.review(
        {
            "render_ref": rendered["render_ref"],
            "mode": "regions",
            "regions": [
                {
                    "selector": "image_bbox",
                    "evidence_ref": page_ref,
                    "bbox_px": [10, 20, 80, 120],
                }
            ],
        }
    )
    assert len(crop_images) == 1
    assert cropped["evidence"][0]["mapping_quality"] == "image_coordinates"


def test_ambiguous_text_returns_candidate_pages_instead_of_false_crop(tmp_path: Path) -> None:
    document = tmp_path / "current.docx"
    _docx(document)
    service = _service(tmp_path)
    rendered, _ = service.render({"input_docx": document.name, "overview": False})

    review, images = service.review(
        {
            "render_ref": rendered["render_ref"],
            "mode": "regions",
            "regions": [{"selector": "text", "text": "重复"}],
        }
    )

    assert {item["page"] for item in review["evidence"]} == {1, 2}
    assert all(item["mapping_quality"] == "mapping_unavailable" for item in review["evidence"])
    assert review["warnings"][0]["candidate_pages"] == [1, 2]
    assert len(images) == 2


def test_text_location_ignores_layout_only_toc_dot_leaders() -> None:
    index: JsonObject = {
        "pages": [
            {
                "page": 1,
                "words": [
                    {"text": "第一章", "bbox_pdf": [10.0, 20.0, 40.0, 30.0]},
                    {
                        "text": "文献综述................................",
                        "bbox_pdf": [42.0, 20.0, 120.0, 30.0],
                    },
                    {"text": "1", "bbox_pdf": [122.0, 20.0, 128.0, 30.0]},
                ],
            }
        ]
    }

    located = locate_text(index, "第一章 文献综述\t1")

    assert located["page"] == 1
    assert located["mapping_quality"] == "normalized_text"


def test_non_rendered_shape_is_exposed_on_its_anchor_paragraph_candidate_pages(
    tmp_path: Path,
) -> None:
    document = tmp_path / "current.docx"
    _docx(document)
    office = _ShapeOffice()
    service = VisualEvidenceService(
        tmp_path,
        renderer=_Renderer(),  # type: ignore[arg-type]
        pdf=_Pdf(),  # type: ignore[arg-type]
        office=office,  # type: ignore[arg-type]
        semantic_selector="paragraph, shape",
    )
    rendered, _ = service.render({"input_docx": document.name, "overview": False})
    inspection = inspect_document(document, office, selector="paragraph, shape")  # type: ignore[arg-type]

    first, _ = service.objects_on_page(
        str(rendered["render_ref"]), inspection, 1, limit=20
    )
    second, _ = service.objects_on_page(
        str(rendered["render_ref"]), inspection, 2, limit=20
    )

    assert any(item["type"] == "shape" for item in first)
    assert any(item["type"] == "shape" for item in second)


def test_old_render_contract_is_rejected_by_v2_service(tmp_path: Path) -> None:
    document = tmp_path / "current.docx"
    _docx(document)
    service = _service(tmp_path)

    with pytest.raises(ToolFailure) as failure:
        service.render(
            {
                "input_docx": document.name,
                "unsupported_option": True,
                "output_dir": "render",
            }
        )

    assert failure.value.code == "unsupported_visual_argument"

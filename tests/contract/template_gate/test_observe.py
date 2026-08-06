from __future__ import annotations

import asyncio
import base64
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

from docfit.template.observation import TemplateObservationService
from docfit.template.ports import RenderedDocument
from docfit.tools.runtime import sha256_file
from docfit.tools.template_tools import template_observe

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "evals"
    / "template-extraction"
    / "fixtures"
)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _task(tmp_path: Path, fixture: str = "S00-minimal-pass") -> tuple[Path, Path]:
    task_root = tmp_path / "task"
    (task_root / "input").mkdir(parents=True)
    (task_root / "work").mkdir()
    (task_root / "output").mkdir()
    source = task_root / "input" / "school-template.docx"
    shutil.copyfile(FIXTURE_ROOT / fixture / "actual-template.docx", source)
    return task_root, source


def _mixed_run_task(tmp_path: Path) -> tuple[Path, Path]:
    task_root, source = _task(tmp_path, "S08-forbidden-residue")
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    root = ET.fromstring(parts["word/document.xml"])
    paragraph = list(root.iter(f"{W}p"))[1]
    original_run = paragraph.find(f"{W}r")
    assert original_run is not None
    original_text = original_run.find(f"{W}t")
    assert original_text is not None
    original_text.text = "姓名："
    placeholder_run = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(placeholder_run, f"{W}t").text = "请在此填写"
    parts["word/document.xml"] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )
    with zipfile.ZipFile(source, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])
    return task_root, source


def test_observe_create_publishes_hash_bound_snapshot_without_mutating_source(
    tmp_path: Path,
) -> None:
    task_root, source = _task(tmp_path)
    source_hash = sha256_file(source)

    result = asyncio.run(
        template_observe.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "create",
                "input_docx": "input/school-template.docx",
                "visual_level": "none",
                "focus": ["structure", "slot_candidates"],
            }
        )
    )

    structured = result["structuredContent"]
    assert structured["call_status"] == "ok"
    assert structured["result_state"] == "observed"
    assert structured["document_sha256"] == source_hash
    assert structured["snapshot_ref"].startswith("snapshot:v1:")
    assert structured["render_ref"] is None
    assert structured["page_count"] is None
    assert structured["content_controls"] == [
        {
            "alias": "author.name.zh",
            "tag": "docfit.cover.student_name",
            "story": "document",
            "part": "word/document.xml",
            "text": "【姓名】",
        }
    ]
    assert sha256_file(source) == source_hash
    assert len(list((task_root / "work" / ".docfit" / "template-v1").rglob("*"))) > 0


def test_observe_query_returns_zero_or_all_matches_without_silent_selection(
    tmp_path: Path,
) -> None:
    task_root, _ = _task(tmp_path, "S07-ambiguous-anchor")
    created = asyncio.run(
        template_observe.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "create",
                "input_docx": "input/school-template.docx",
                "visual_level": "none",
                "focus": ["visible_objects"],
            }
        )
    )["structuredContent"]

    duplicated = asyncio.run(
        template_observe.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "query",
                "snapshot_ref": created["snapshot_ref"],
                "query": {
                    "text": "^姓名",
                    "match": "regex",
                    "include": ["context"],
                },
            }
        )
    )["structuredContent"]
    missing = asyncio.run(
        template_observe.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "query",
                "snapshot_ref": created["snapshot_ref"],
                "query": {
                    "text": "不存在的字段",
                    "match": "exact",
                    "include": [],
                },
            }
        )
    )["structuredContent"]

    assert duplicated["call_status"] == "ok"
    assert duplicated["match_count"] == 2
    assert len(duplicated["matches"]) == 2
    assert all(
        match["object_ref"]["snapshot_ref"] == created["snapshot_ref"]
        for match in duplicated["matches"]
    )
    assert missing["call_status"] == "ok"
    assert missing["match_count"] == 0
    assert missing["matches"] == []


def test_observe_query_can_select_a_run_without_selecting_its_label_paragraph(
    tmp_path: Path,
) -> None:
    task_root, _ = _mixed_run_task(tmp_path)
    created = TemplateObservationService().create(
        {
            "input_docx": "input/school-template.docx",
            "visual_level": "none",
            "focus": ["slot_candidates"],
        },
        task_root=task_root,
    )

    paragraph = TemplateObservationService().query(
        {
            "snapshot_ref": created["snapshot_ref"],
            "query": {
                "text": "姓名：请在此填写",
                "match": "exact",
                "include": ["context"],
            },
        },
        task_root=task_root,
    )
    run = TemplateObservationService().query(
        {
            "snapshot_ref": created["snapshot_ref"],
            "query": {
                "text": "请在此填写",
                "match": "exact",
                "kinds": ["run"],
                "include": ["context"],
            },
        },
        task_root=task_root,
    )

    assert paragraph["match_count"] == 1
    assert paragraph["matches"][0]["kind"] == "paragraph"
    assert run["match_count"] == 1
    assert run["matches"][0]["kind"] == "run"
    assert run["matches"][0]["context"]["run_index"] == 1


class _ThreePageRenderer:
    def render(
        self,
        document: Path,
        *,
        visual_level: str,
        output: Path,
    ) -> RenderedDocument:
        assert document.is_file()
        assert visual_level == "candidate_verification"
        pages_directory = output / "pages"
        pages_directory.mkdir()
        pages: list[Path] = []
        for page_number in range(1, 4):
            page = pages_directory / f"page-{page_number:04d}.png"
            Image.new("RGB", (40, 60), (page_number * 30, 10, 10)).save(page)
            pages.append(page)
        return RenderedDocument(tuple(pages), {"name": "fake-boundary"})


def test_observe_candidate_images_are_hash_bound_and_cursor_bounded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task_root, source = _task(tmp_path)
    source_hash = sha256_file(source)
    service = TemplateObservationService(_ThreePageRenderer())
    monkeypatch.setattr(
        "docfit.tools.template_tools.TemplateObservationService",
        lambda: service,
    )

    created = asyncio.run(
        template_observe.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "create",
                "input_docx": "input/school-template.docx",
                "visual_level": "candidate_verification",
                "focus": ["structure"],
            }
        )
    )["structuredContent"]
    first = asyncio.run(
        template_observe.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "images",
                "render_ref": created["render_ref"],
                "max_images": 2,
            }
        )
    )
    second = asyncio.run(
        template_observe.handler(
            {
                "schema_version": 1,
                "task_root": str(task_root),
                "action": "images",
                "render_ref": created["render_ref"],
                "cursor": first["structuredContent"]["next_cursor"],
                "max_images": 2,
            }
        )
    )

    assert created["page_count"] == 3
    assert created["render_ref"].startswith("render:v1:")
    assert len(first["structuredContent"]["images"]) == 2
    assert first["structuredContent"]["next_cursor"] is not None
    assert len([item for item in first["content"] if item["type"] == "image"]) == 2
    assert len(second["structuredContent"]["images"]) == 1
    assert second["structuredContent"]["next_cursor"] is None
    assert base64.b64decode(second["content"][1]["data"]).startswith(b"\x89PNG")
    assert sha256_file(source) == source_hash

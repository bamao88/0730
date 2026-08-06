"""Create immutable structural snapshots of authorized DOCX inputs."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from docfit.template.ports import TemplateRenderer
from docfit.template.rendering import TemplateRenderService
from docfit.template.runtime.paths import task_file
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{W_NS}}}"
_STORY_PATTERN = re.compile(
    r"word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml"
)
_FOCUS_VALUES = {"structure", "visible_objects", "styles", "slot_candidates"}


def _attribute(element: ET.Element | None, name: str) -> str | None:
    if element is None:
        return None
    return element.get(f"{_W}{name}")


def _text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{_W}t"))


def _story(name: str) -> str:
    if name == "word/document.xml":
        return "document"
    if name.startswith("word/header"):
        return "header"
    if name.startswith("word/footer"):
        return "footer"
    return Path(name).stem


def snapshot_document(document: Path, document_sha256: str, source_path: str) -> JsonObject:
    objects: list[JsonObject] = []
    controls: list[JsonObject] = []
    sections: list[JsonObject] = []
    unsupported: list[JsonObject] = []
    styles: list[JsonObject] = []
    try:
        with zipfile.ZipFile(document) as archive:
            names = sorted(archive.namelist())
            for part in (name for name in names if _STORY_PATTERN.fullmatch(name)):
                root = ET.fromstring(archive.read(part))
                story = _story(part)
                for index, paragraph in enumerate(root.iter(f"{_W}p")):
                    text = _text(paragraph)
                    identity = {
                        "part": part,
                        "kind": "paragraph",
                        "index": index,
                        "text": text,
                    }
                    objects.append(
                        {
                            "object_id": f"obj-{sha256_json(identity)[:24]}",
                            "kind": "paragraph",
                            "story": story,
                            "part": part,
                            "paragraph_index": index,
                            "text": text,
                            "expected_fingerprint": sha256_json(identity),
                        }
                    )
                for control in root.iter(f"{_W}sdt"):
                    properties = control.find(f"{_W}sdtPr")
                    item: JsonObject = {
                        "alias": _attribute(
                            None if properties is None else properties.find(f"{_W}alias"),
                            "val",
                        ),
                        "tag": _attribute(
                            None if properties is None else properties.find(f"{_W}tag"),
                            "val",
                        ),
                        "story": story,
                        "part": part,
                        "text": _text(control),
                    }
                    controls.append(item)
                for section_index, section in enumerate(root.iter(f"{_W}sectPr")):
                    sections.append(
                        {
                            "story": story,
                            "part": part,
                            "section_index": section_index,
                            "fingerprint": sha256_json(ET.tostring(section).decode("utf-8")),
                        }
                    )
                for element in root.iter():
                    if element.tag in {f"{_W}altChunk", f"{_W}customXml"}:
                        unsupported.append(
                            {"story": story, "part": part, "kind": element.tag.rsplit("}", 1)[-1]}
                        )
            if "word/styles.xml" in names:
                style_root = ET.fromstring(archive.read("word/styles.xml"))
                for style in style_root.findall(f"{_W}style"):
                    styles.append(
                        {
                            "style_id": _attribute(style, "styleId"),
                            "type": _attribute(style, "type"),
                            "fingerprint": sha256_json(ET.tostring(style).decode("utf-8")),
                        }
                    )
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="document",
            code="invalid_docx_package",
            message="The input DOCX package cannot be parsed safely.",
        ) from error
    return {
        "schema_version": 1,
        "kind": "snapshot",
        "implementation_version": "0.1.0",
        "document_sha256": document_sha256,
        "source_path": source_path,
        "objects": objects,
        "content_controls": controls,
        "styles": styles,
        "sections": sections,
        "unsupported_features": unsupported,
    }


class TemplateObservationService:
    """Trusted observation boundary for template extraction."""

    def __init__(self, renderer: TemplateRenderer | None = None) -> None:
        self.rendering = TemplateRenderService(renderer)

    def create(self, args: dict[str, Any], *, task_root: Path) -> JsonObject:
        visual_level = args.get("visual_level", "none")
        if visual_level not in {"none", "quick", "candidate_verification"}:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_visual_level",
                message="The requested visual evidence level is unsupported.",
            )
        focus = args.get("focus", [])
        if not isinstance(focus, list) or any(item not in _FOCUS_VALUES for item in focus):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_focus",
                message="focus contains an unsupported observation category.",
            )
        document = task_file(
            args.get("input_docx"),
            task_root=task_root,
            field="input_docx",
            suffix=".docx",
        )
        validate_docx_package(document)
        before_hash = sha256_file(document)
        relative = document.relative_to(task_root).as_posix()
        payload = snapshot_document(document, before_hash, relative)
        if sha256_file(document) != before_hash:
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="source_changed",
                message="The source document changed while the snapshot was being created.",
            )
        snapshot_ref = EvidenceStore(task_root).publish("snapshot", payload)
        if sha256_file(document) != before_hash:
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="source_changed",
                message="The source document changed before evidence publication completed.",
            )
        render = (
            self.rendering.create(
                task_root=task_root,
                snapshot_ref=snapshot_ref,
                visual_level=visual_level,
            )
            if visual_level != "none"
            else None
        )
        return {
            "schema_version": 1,
            "call_status": "ok",
            "result_state": "observed",
            "document_sha256": before_hash,
            "snapshot_ref": snapshot_ref,
            "render_ref": render["render_ref"] if render else None,
            "page_count": render["page_count"] if render else None,
            "objects": payload["objects"],
            "content_controls": payload["content_controls"],
            "styles": payload["styles"],
            "sections": payload["sections"],
            "unsupported_features": payload["unsupported_features"],
            "checks": [
                {"name": "docx_package", "result": "ok"},
                {"name": "source_hash_unchanged", "result": "ok"},
            ],
            "warnings": [],
            "failure": None,
        }

    def query(self, args: dict[str, Any], *, task_root: Path) -> JsonObject:
        snapshot_ref = args.get("snapshot_ref")
        snapshot = EvidenceStore(task_root).resolve(snapshot_ref, expected_kind="snapshot")
        query = args.get("query")
        if not isinstance(query, dict) or set(query) - {"text", "match", "include"}:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_query",
                message="query must contain only text, match, and include.",
            )
        text = query.get("text")
        match_mode = query.get("match")
        include = query.get("include", [])
        if (
            not isinstance(text, str)
            or not text
            or len(text) > 256
            or match_mode not in {"exact", "casefold", "regex"}
            or not isinstance(include, list)
            or any(
                item not in {"context", "effective_style", "visual_location"}
                for item in include
            )
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_query",
                message="The observation query is invalid or exceeds its budget.",
            )
        expression: re.Pattern[str] | None = None
        if match_mode == "regex":
            if re.search(r"\\[1-9]|\(\?|(?:\*|\+|\{[^}]+\}){2}", text):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="regex_budget_exceeded",
                    message="The regular expression uses constructs outside the safe query subset.",
                )
            try:
                expression = re.compile(text)
            except re.error as error:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_query",
                    message="The regular expression cannot be compiled.",
                ) from error

        def matches(candidate: str) -> bool:
            if match_mode == "exact":
                return candidate == text
            if match_mode == "casefold":
                return candidate.casefold() == text.casefold()
            return expression.search(candidate) is not None if expression is not None else False

        raw_objects = snapshot.get("objects")
        if not isinstance(raw_objects, list):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="The snapshot object inventory is invalid.",
            )
        results: list[JsonObject] = []
        for item in raw_objects:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            if not matches(item["text"]):
                continue
            result: JsonObject = {
                "kind": item.get("kind"),
                "text": item["text"],
                "story": item.get("story"),
                "part": item.get("part"),
                "object_ref": {
                    "snapshot_ref": snapshot_ref,
                    "object_id": item.get("object_id"),
                    "expected_fingerprint": item.get("expected_fingerprint"),
                },
            }
            if "context" in include:
                result["context"] = {"paragraph_index": item.get("paragraph_index")}
            if "effective_style" in include:
                result["effective_style"] = item.get("effective_style")
            if "visual_location" in include:
                result["visual_location"] = None
            results.append(result)
        results.sort(
            key=lambda item: (
                str(item.get("part")),
                int(item.get("context", {}).get("paragraph_index") or 0),
                str(item.get("object_ref", {}).get("object_id")),
            )
        )
        return {
            "schema_version": 1,
            "call_status": "ok",
            "result_state": "observed",
            "snapshot_ref": snapshot_ref,
            "document_sha256": snapshot.get("document_sha256"),
            "match_count": len(results),
            "matches": results,
            "checks": [{"name": "snapshot_integrity", "result": "ok"}],
            "warnings": [],
            "failure": None,
        }

    def images(
        self,
        args: dict[str, Any],
        *,
        task_root: Path,
    ) -> tuple[JsonObject, list[Path]]:
        return self.rendering.images(args, task_root=task_root)

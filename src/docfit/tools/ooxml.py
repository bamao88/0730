"""Minimal OOXML dependency-closure patch for template section imports."""

from __future__ import annotations

import copy
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import cast
from xml.etree import ElementTree as ET

from docfit.tools.runtime import JsonObject, ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"

_IGNORABLE_NAMESPACES = {
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
}

for prefix, uri in (
    ("w", W_NS),
    ("r", R_NS),
    ("wp", WP_NS),
    ("mc", MC_NS),
    *_IGNORABLE_NAMESPACES.items(),
):
    ET.register_namespace(prefix, uri)


def _q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _read_package(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile) as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="template_package_unreadable",
            message="A template import package cannot be read.",
        ) from error


def _xml(parts: dict[str, bytes], name: str) -> ET.Element:
    try:
        return ET.fromstring(parts[name])
    except (KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="template_part_unreadable",
            message="A required OOXML part for template import cannot be read.",
        ) from error


def _serialize(root: ET.Element) -> bytes:
    if root.tag == _q(CT_NS, "Types"):
        ET.register_namespace("", CT_NS)
    elif root.tag == _q(REL_NS, "Relationships"):
        ET.register_namespace("", REL_NS)
    payload = cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    ignorable = root.get(_q(MC_NS, "Ignorable"), "").split()
    missing = [
        (prefix, _IGNORABLE_NAMESPACES[prefix])
        for prefix in ignorable
        if prefix in _IGNORABLE_NAMESPACES and f"xmlns:{prefix}=".encode() not in payload
    ]
    if missing:
        declaration_end = payload.find(b"?>")
        root_start = payload.find(b"<", declaration_end + 2)
        root_end = payload.find(b">", root_start)
        declarations = b"".join(f' xmlns:{prefix}="{uri}"'.encode() for prefix, uri in missing)
        payload = payload[:root_end] + declarations + payload[root_end:]
    return payload


def _relationship_part(owner: str) -> str:
    path = PurePosixPath(owner)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _resolve(owner: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner), target)).lstrip("/")


def _relative(owner: str, target: str) -> str:
    return posixpath.relpath(target, posixpath.dirname(owner))


def _unique_part(name: str, target: dict[str, bytes]) -> str:
    if name not in target:
        return name
    path = PurePosixPath(name)
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 10000):
        candidate = str(path.with_name(f"{stem}-docfit-{index}{suffix}"))
        if candidate not in target:
            return candidate
    raise ToolFailure(
        status="error",
        origin="adapter",
        code="part_name_exhausted",
        message="Template dependency part names could not be remapped safely.",
    )


def _next_relationship_id(root: ET.Element) -> str:
    used = {item.get("Id", "") for item in root.findall(_q(REL_NS, "Relationship"))}
    for index in range(1, 100000):
        candidate = f"rId{index}"
        if candidate not in used:
            return candidate
    raise ToolFailure(
        status="error",
        origin="adapter",
        code="relationship_id_exhausted",
        message="Template relationship IDs could not be remapped safely.",
    )


def _max_numeric_attribute(root: ET.Element, tag: str, attribute: str) -> int:
    values: list[int] = []
    for element in root.iter(tag):
        value = element.get(attribute)
        if value is not None and value.isdigit():
            values.append(int(value))
    return max(values, default=0)


def _find_body_element(root: ET.Element, locator: str) -> ET.Element:
    body = root.find(_q(W_NS, "body"))
    if body is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_body_missing",
            message="The DOCX document body is missing.",
        )
    paragraph_match = re.fullmatch(r"/body/p\[@paraId=([0-9A-Fa-f]+)\]", locator)
    if paragraph_match:
        para_id = paragraph_match.group(1).upper()
        for paragraph in body.findall(_q(W_NS, "p")):
            for key, value in paragraph.attrib.items():
                if key.endswith("}paraId") and value.upper() == para_id:
                    return paragraph
    table_match = re.fullmatch(r"/body/tbl\[(\d+)\]", locator)
    if table_match:
        tables = body.findall(_q(W_NS, "tbl"))
        index = int(table_match.group(1)) - 1
        if 0 <= index < len(tables):
            return tables[index]
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="unsupported_template_object",
        message="Template import currently accepts only top-level paragraph or table refs.",
        suggested_actions=("inspect_template_again", "select_top_level_objects"),
    )


def _find_direct_body_content_control(body: ET.Element, tag: str) -> ET.Element:
    matches: list[ET.Element] = []
    for child in body.findall(_q(W_NS, "sdt")):
        tag_element = child.find(f"{_q(W_NS, 'sdtPr')}/{_q(W_NS, 'tag')}")
        if tag_element is not None and tag_element.get(_q(W_NS, "val")) == tag:
            matches.append(child)
    if len(matches) != 1:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="content_control_tag_not_unique",
            message=(
                "A block replacement tag must identify exactly one body-level content control."
            ),
            suggested_actions=("inspect_template_again", "repair_fill_contract"),
        )
    return matches[0]


@dataclass(slots=True)
class _Closure:
    source: dict[str, bytes]
    target: dict[str, bytes]
    content_types: ET.Element
    part_map: dict[str, str] = field(default_factory=dict)
    copied_parts: list[str] = field(default_factory=list)
    copied_relationships: int = 0

    def _copy_content_type(self, source_part: str, target_part: str) -> None:
        source_types = _xml(self.source, "[Content_Types].xml")
        source_name = f"/{source_part}"
        target_name = f"/{target_part}"
        existing_overrides = {
            item.get("PartName") for item in self.content_types.findall(_q(CT_NS, "Override"))
        }
        for override in source_types.findall(_q(CT_NS, "Override")):
            if override.get("PartName") == source_name and target_name not in existing_overrides:
                clone = copy.deepcopy(override)
                clone.set("PartName", target_name)
                self.content_types.append(clone)
                return
        extension = PurePosixPath(source_part).suffix.lstrip(".")
        existing_defaults = {
            item.get("Extension") for item in self.content_types.findall(_q(CT_NS, "Default"))
        }
        if extension and extension not in existing_defaults:
            for default in source_types.findall(_q(CT_NS, "Default")):
                if default.get("Extension") == extension:
                    self.content_types.append(copy.deepcopy(default))
                    return

    def copy_part(self, source_part: str) -> str:
        if source_part in self.part_map:
            return self.part_map[source_part]
        if source_part not in self.source:
            raise ToolFailure(
                status="error",
                origin="document",
                code="template_dependency_missing",
                message="A template relationship points to a missing package part.",
            )
        if source_part in self.target and self.target[source_part] == self.source[source_part]:
            self.part_map[source_part] = source_part
            return source_part
        target_part = _unique_part(source_part, self.target)
        self.part_map[source_part] = target_part

        content = self.source[source_part]
        source_rels_name = _relationship_part(source_part)
        if source_rels_name in self.source:
            source_rels = _xml(self.source, source_rels_name)
            target_rels = copy.deepcopy(source_rels)
            for relationship in target_rels.findall(_q(REL_NS, "Relationship")):
                if relationship.get("TargetMode") == "External":
                    continue
                target = relationship.get("Target")
                if not target:
                    continue
                source_dependency = _resolve(source_part, target)
                target_dependency = self.copy_part(source_dependency)
                relationship.set("Target", _relative(target_part, target_dependency))
                self.copied_relationships += 1
            target_rels_name = _relationship_part(target_part)
            self.target[target_rels_name] = _serialize(target_rels)
            self._copy_content_type(source_rels_name, target_rels_name)
        self.target[target_part] = content
        self._copy_content_type(source_part, target_part)
        self.copied_parts.append(target_part)
        return target_part


def _copy_referenced_styles(
    copied: list[ET.Element],
    source_parts: dict[str, bytes],
    target_parts: dict[str, bytes],
) -> tuple[dict[str, str], int]:
    source_styles = _xml(source_parts, "word/styles.xml")
    target_styles = _xml(target_parts, "word/styles.xml")
    source_by_id = {
        item.get(_q(W_NS, "styleId"), ""): item for item in source_styles.findall(_q(W_NS, "style"))
    }
    target_by_id = {
        item.get(_q(W_NS, "styleId"), ""): item for item in target_styles.findall(_q(W_NS, "style"))
    }
    mapping: dict[str, str] = {}

    def copy_style(style_id: str) -> str:
        if style_id in mapping:
            return mapping[style_id]
        source_style = source_by_id.get(style_id)
        if source_style is None:
            mapping[style_id] = style_id
            return style_id
        target_style = target_by_id.get(style_id)
        if target_style is not None and _serialize(target_style) == _serialize(source_style):
            mapping[style_id] = style_id
            return style_id
        candidate = style_id
        index = 1
        while candidate in target_by_id:
            candidate = f"{style_id}_docfit_{index}"
            index += 1
        mapping[style_id] = candidate
        clone = copy.deepcopy(source_style)
        clone.set(_q(W_NS, "styleId"), candidate)
        for link_tag in ("basedOn", "next", "link"):
            link = clone.find(_q(W_NS, link_tag))
            if link is not None:
                linked = link.get(_q(W_NS, "val"))
                if linked:
                    link.set(_q(W_NS, "val"), copy_style(linked))
        target_styles.append(clone)
        target_by_id[candidate] = clone
        return candidate

    style_tags = {_q(W_NS, value) for value in ("pStyle", "rStyle", "tblStyle")}
    for element in copied:
        for descendant in element.iter():
            if descendant.tag not in style_tags:
                continue
            value = descendant.get(_q(W_NS, "val"))
            if value:
                descendant.set(_q(W_NS, "val"), copy_style(value))
    target_parts["word/styles.xml"] = _serialize(target_styles)
    copied_count = sum(1 for old, new in mapping.items() if old != new or old not in target_by_id)
    return mapping, copied_count


def _copy_numbering(
    copied: list[ET.Element],
    source_parts: dict[str, bytes],
    target_parts: dict[str, bytes],
) -> tuple[dict[str, str], int]:
    requested = {
        element.get(_q(W_NS, "val"), "")
        for item in copied
        for element in item.iter(_q(W_NS, "numId"))
    }
    requested.discard("")
    if not requested:
        return {}, 0
    source_numbering = _xml(source_parts, "word/numbering.xml")
    target_numbering = _ensure_numbering_part(target_parts)
    source_nums = {
        item.get(_q(W_NS, "numId"), ""): item for item in source_numbering.findall(_q(W_NS, "num"))
    }
    source_abstract = {
        item.get(_q(W_NS, "abstractNumId"), ""): item
        for item in source_numbering.findall(_q(W_NS, "abstractNum"))
    }
    next_num = _max_numeric_attribute(target_numbering, _q(W_NS, "num"), _q(W_NS, "numId")) + 1
    next_abstract = (
        _max_numeric_attribute(
            target_numbering,
            _q(W_NS, "abstractNum"),
            _q(W_NS, "abstractNumId"),
        )
        + 1
    )
    mapping: dict[str, str] = {}
    for old_num_id in sorted(requested, key=lambda value: int(value) if value.isdigit() else 0):
        source_num = source_nums.get(old_num_id)
        if source_num is None:
            raise ToolFailure(
                status="error",
                origin="document",
                code="template_numbering_missing",
                message="A selected template object references missing numbering data.",
            )
        abstract_ref = source_num.find(_q(W_NS, "abstractNumId"))
        old_abstract_id = abstract_ref.get(_q(W_NS, "val")) if abstract_ref is not None else None
        source_abstract_item = source_abstract.get(old_abstract_id or "")
        if source_abstract_item is None:
            raise ToolFailure(
                status="error",
                origin="document",
                code="template_abstract_numbering_missing",
                message="A selected template list references missing abstract numbering.",
            )
        abstract_clone = copy.deepcopy(source_abstract_item)
        abstract_clone.set(_q(W_NS, "abstractNumId"), str(next_abstract))
        target_numbering.append(abstract_clone)
        num_clone = copy.deepcopy(source_num)
        num_clone.set(_q(W_NS, "numId"), str(next_num))
        num_abstract_ref = num_clone.find(_q(W_NS, "abstractNumId"))
        if num_abstract_ref is not None:
            num_abstract_ref.set(_q(W_NS, "val"), str(next_abstract))
        target_numbering.append(num_clone)
        mapping[old_num_id] = str(next_num)
        next_num += 1
        next_abstract += 1
    for item in copied:
        for num_id in item.iter(_q(W_NS, "numId")):
            old = num_id.get(_q(W_NS, "val"))
            if old in mapping:
                num_id.set(_q(W_NS, "val"), mapping[old])
    target_parts["word/numbering.xml"] = _serialize(target_numbering)
    return mapping, len(mapping)


def _ensure_numbering_part(target_parts: dict[str, bytes]) -> ET.Element:
    """Create the standard numbering infrastructure when a target has none."""

    if "word/numbering.xml" in target_parts:
        return _xml(target_parts, "word/numbering.xml")
    numbering = ET.Element(_q(W_NS, "numbering"))
    target_relationships = _xml(target_parts, "word/_rels/document.xml.rels")
    numbering_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering"
    if not any(
        relationship.get("Type") == numbering_type
        for relationship in target_relationships.findall(_q(REL_NS, "Relationship"))
    ):
        relationship = ET.SubElement(
            target_relationships,
            _q(REL_NS, "Relationship"),
        )
        relationship.set("Id", _next_relationship_id(target_relationships))
        relationship.set("Type", numbering_type)
        relationship.set("Target", "numbering.xml")
    target_parts["word/_rels/document.xml.rels"] = _serialize(target_relationships)

    content_types = _xml(target_parts, "[Content_Types].xml")
    part_name = "/word/numbering.xml"
    if not any(
        item.get("PartName") == part_name for item in content_types.findall(_q(CT_NS, "Override"))
    ):
        override = ET.SubElement(content_types, _q(CT_NS, "Override"))
        override.set("PartName", part_name)
        override.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml",
        )
    target_parts["[Content_Types].xml"] = _serialize(content_types)
    return numbering


def _remap_local_ids(copied: list[ET.Element], target_document: ET.Element) -> int:
    changes = 0
    for local_name in ("paraId", "textId"):
        used = {
            value.upper()
            for element in target_document.iter()
            for key, value in element.attrib.items()
            if key.endswith(f"}}{local_name}")
        }
        next_value = (
            max(
                (int(value, 16) for value in used if re.fullmatch(r"[0-9A-F]+", value)),
                default=0x100000,
            )
            + 1
        )
        for item in copied:
            for element in item.iter():
                for key in tuple(element.attrib):
                    if not key.endswith(f"}}{local_name}"):
                        continue
                    while f"{next_value:08X}" in used:
                        next_value += 1
                    replacement = f"{next_value:08X}"
                    next_value += 1
                    used.add(replacement)
                    element.set(key, replacement)
                    changes += 1
    next_bookmark = (
        _max_numeric_attribute(
            target_document,
            _q(W_NS, "bookmarkStart"),
            _q(W_NS, "id"),
        )
        + 1
    )
    next_doc_pr = _max_numeric_attribute(target_document, _q(WP_NS, "docPr"), "id") + 1
    bookmark_map: dict[str, str] = {}
    for item in copied:
        for start in item.iter(_q(W_NS, "bookmarkStart")):
            old = start.get(_q(W_NS, "id"))
            if old is None:
                continue
            new = str(next_bookmark)
            next_bookmark += 1
            bookmark_map[old] = new
            start.set(_q(W_NS, "id"), new)
            changes += 1
        for end in item.iter(_q(W_NS, "bookmarkEnd")):
            old = end.get(_q(W_NS, "id"))
            if old in bookmark_map:
                end.set(_q(W_NS, "id"), bookmark_map[old])
        for doc_pr in item.iter(_q(WP_NS, "docPr")):
            doc_pr.set("id", str(next_doc_pr))
            next_doc_pr += 1
            changes += 1
    return changes


def _write_package(path: Path, parts: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(parts):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, parts[name])


def mutate_content_controls(
    *,
    input_docx: Path,
    text_replacements: dict[str, str],
    remove_body_tags: tuple[str, ...],
    output_docx: Path,
) -> JsonObject:
    """Replace tagged text and remove declared body-level controls in one snapshot."""

    parts = _read_package(input_docx)
    document = _xml(parts, "word/document.xml")
    body = document.find(_q(W_NS, "body"))
    if body is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_body_missing",
            message="The DOCX document body is missing.",
        )
    controls_by_tag: dict[str, list[ET.Element]] = {}
    for control in document.iter(_q(W_NS, "sdt")):
        tag_element = control.find(f"{_q(W_NS, 'sdtPr')}/{_q(W_NS, 'tag')}")
        tag = tag_element.get(_q(W_NS, "val")) if tag_element is not None else None
        if tag:
            controls_by_tag.setdefault(tag, []).append(control)
    for tag, value in text_replacements.items():
        matches = controls_by_tag.get(tag, [])
        if len(matches) != 1:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="content_control_tag_not_unique",
                message="A text replacement tag must identify exactly one content control.",
            )
        content = matches[0].find(_q(W_NS, "sdtContent"))
        if content is None:
            raise ToolFailure(
                status="error",
                origin="document",
                code="content_control_content_missing",
                message="A target content control has no editable content container.",
            )
        text_nodes = list(content.iter(_q(W_NS, "t")))
        if text_nodes:
            text_nodes[0].text = value
            text_nodes[0].set(
                "{http://www.w3.org/XML/1998/namespace}space",
                "preserve",
            )
            for text_node in text_nodes[1:]:
                text_node.text = None
        else:
            run = next(content.iter(_q(W_NS, "r")), None)
            if run is None:
                run = ET.SubElement(content, _q(W_NS, "r"))
            text_node = ET.SubElement(run, _q(W_NS, "t"))
            text_node.set(
                "{http://www.w3.org/XML/1998/namespace}space",
                "preserve",
            )
            text_node.text = value
        properties = matches[0].find(_q(W_NS, "sdtPr"))
        if properties is not None:
            placeholder_flag = properties.find(_q(W_NS, "showingPlcHdr"))
            if placeholder_flag is not None:
                properties.remove(placeholder_flag)
    removed = 0
    for tag in remove_body_tags:
        control = _find_direct_body_content_control(body, tag)
        body.remove(control)
        removed += 1
    parts["word/document.xml"] = _serialize(document)
    _write_package(output_docx, parts)
    return {
        "text_controls_replaced": len(text_replacements),
        "body_controls_removed": removed,
    }


def import_content_objects(
    *,
    target_docx: Path,
    source_docx: Path,
    source_locators: list[str],
    anchor_locator: str | None,
    position: str,
    include_source_final_section_properties: bool,
    output_docx: Path,
    replace_content_control_tag: str | None = None,
) -> JsonObject:
    """Copy selected body objects and their concrete package dependencies."""

    if not source_locators:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="content_sources_empty",
            message="import_content_objects requires at least one source object ref.",
        )
    if position not in {"before", "after", "end"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_insert_position",
            message="Content insertion position must be before, after, or end.",
        )
    if replace_content_control_tag is None and position != "end" and anchor_locator is None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="insert_anchor_required",
            message="Content insertion before or after requires a target anchor ref.",
        )

    source_parts = _read_package(source_docx)
    target_parts = _read_package(target_docx)
    source_document = _xml(source_parts, "word/document.xml")
    target_document = _xml(target_parts, "word/document.xml")
    source_body = source_document.find(_q(W_NS, "body"))
    target_body = target_document.find(_q(W_NS, "body"))
    if source_body is None or target_body is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_body_missing",
            message="Content import requires readable source and target document bodies.",
        )
    copied = [
        copy.deepcopy(_find_body_element(source_document, value)) for value in source_locators
    ]
    if include_source_final_section_properties:
        final_section = source_body.find(_q(W_NS, "sectPr"))
        if final_section is not None:
            paragraph = ET.Element(_q(W_NS, "p"))
            paragraph_properties = ET.SubElement(paragraph, _q(W_NS, "pPr"))
            paragraph_properties.append(copy.deepcopy(final_section))
            copied.append(paragraph)

    style_mapping, copied_styles = _copy_referenced_styles(copied, source_parts, target_parts)
    numbering_mapping, copied_numbering = _copy_numbering(copied, source_parts, target_parts)
    remapped_local_ids = _remap_local_ids(copied, target_document)

    target_content_types = _xml(target_parts, "[Content_Types].xml")
    closure = _Closure(source_parts, target_parts, target_content_types)
    source_document_rels = _xml(source_parts, "word/_rels/document.xml.rels")
    target_document_rels = _xml(target_parts, "word/_rels/document.xml.rels")
    source_rels_by_id = {
        item.get("Id", ""): item
        for item in source_document_rels.findall(_q(REL_NS, "Relationship"))
    }
    relationship_attrs = {_q(R_NS, local) for local in ("id", "embed", "link")}
    for item in copied:
        for element in item.iter():
            for attribute in tuple(element.attrib):
                if attribute not in relationship_attrs:
                    continue
                old_id = element.get(attribute)
                source_relationship = source_rels_by_id.get(old_id or "")
                if source_relationship is None:
                    raise ToolFailure(
                        status="error",
                        origin="document",
                        code="source_relationship_missing",
                        message="A selected source object contains an unresolved relationship.",
                    )
                new_id = _next_relationship_id(target_document_rels)
                clone = copy.deepcopy(source_relationship)
                clone.set("Id", new_id)
                if clone.get("TargetMode") != "External":
                    source_target = clone.get("Target")
                    if not source_target:
                        raise ToolFailure(
                            status="error",
                            origin="document",
                            code="source_relationship_target_missing",
                            message="A source dependency relationship has no target.",
                        )
                    source_part = _resolve("word/document.xml", source_target)
                    target_part = closure.copy_part(source_part)
                    clone.set("Target", _relative("word/document.xml", target_part))
                target_document_rels.append(clone)
                closure.copied_relationships += 1
                element.set(attribute, new_id)

    if replace_content_control_tag is not None:
        replaced = _find_direct_body_content_control(
            target_body,
            replace_content_control_tag,
        )
        insert_index = list(target_body).index(replaced)
        target_body.remove(replaced)
    elif position == "end":
        final_sect_pr = target_body.find(_q(W_NS, "sectPr"))
        insert_index = (
            list(target_body).index(final_sect_pr)
            if final_sect_pr is not None
            else len(target_body)
        )
    else:
        assert anchor_locator is not None
        anchor = _find_body_element(target_document, anchor_locator)
        anchor_index = list(target_body).index(anchor)
        insert_index = anchor_index if position == "before" else anchor_index + 1
    for offset, item in enumerate(copied):
        target_body.insert(insert_index + offset, item)

    target_parts["word/document.xml"] = _serialize(target_document)
    target_parts["word/_rels/document.xml.rels"] = _serialize(target_document_rels)
    target_parts["[Content_Types].xml"] = _serialize(target_content_types)
    _write_package(output_docx, target_parts)
    return {
        "source_objects": len(source_locators),
        "inserted_objects": len(copied),
        "styles_copied": copied_styles,
        "style_id_map": style_mapping,
        "numbering_copied": copied_numbering,
        "numbering_id_map": numbering_mapping,
        "package_parts_copied": len(closure.copied_parts),
        "relationships_copied": closure.copied_relationships,
        "replaced_content_control_tag": replace_content_control_tag,
        "local_ids_remapped": remapped_local_ids,
        "headers_or_footers_copied": sum(
            1
            for value in closure.copied_parts
            if PurePosixPath(value).name.startswith(("header", "footer"))
        ),
        "dependency_closure_complete": True,
        "conflicts_remapped": True,
    }

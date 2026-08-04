"""Internal Tool-only PoC for deterministic logical-unit page boundaries."""

from __future__ import annotations

import copy
import io
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

from docfit.tools.inspection import Inspection, resolve_object_ref
from docfit.tools.layout import measure_html_layout
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"


def _q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


@dataclass(frozen=True, slots=True)
class BodyBlock:
    index: int
    kind: str
    element: ET.Element
    locator: str
    html_path: str | None
    text: str
    object_ref: JsonObject

    @property
    def layout_only(self) -> bool:
        return self.kind == "paragraph" and not self.text.strip()

    @property
    def explicit_page_break(self) -> bool:
        return any(
            item.get(_q(W_NS, "type"), "textWrapping") == "page"
            for item in self.element.findall(f".//{_q(W_NS, 'br')}")
        )

    @property
    def page_break_before(self) -> bool:
        properties = self.element.find(_q(W_NS, "pPr"))
        return properties is not None and properties.find(_q(W_NS, "pageBreakBefore")) is not None

    @property
    def section_break(self) -> ET.Element | None:
        properties = self.element.find(_q(W_NS, "pPr"))
        return properties.find(_q(W_NS, "sectPr")) if properties is not None else None


@dataclass(frozen=True, slots=True)
class ReferenceLayout:
    page_count: int
    records: tuple[JsonObject, ...]

    def for_path(self, path: str | None) -> JsonObject | None:
        if path is None:
            return None
        return next((item for item in self.records if item.get("path") == path), None)


def _paragraph_text(element: ET.Element) -> str:
    values: list[str] = []
    for node in element.iter():
        if node.tag in {_q(W_NS, "t"), _q(W_NS, "delText"), _q(W_NS, "instrText")}:
            values.append(node.text or "")
        elif node.tag == _q(W_NS, "tab"):
            values.append("\t")
        elif node.tag == _q(W_NS, "br"):
            values.append("\n")
    return "".join(values)


def _internal_ref(document_sha256: str, index: int, kind: str, element: ET.Element) -> JsonObject:
    fingerprint = sha256_json(
        {
            "index": index,
            "kind": kind,
            "xml": ET.tostring(element, encoding="unicode"),
        }
    )
    return {
        "schema_version": 1,
        "document_sha256": document_sha256,
        "object_id": f"ub-{fingerprint[:24]}",
        "expected_fingerprint": fingerprint,
    }


def _body_blocks(document: Path, inspection: Inspection) -> tuple[BodyBlock, ...]:
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(_q(W_NS, "body"))
    if body is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_body_missing",
            message="The DOCX package contains no WordprocessingML body.",
        )
    inspected_by_locator = {item.locator: item for item in inspection.objects}
    remaining_paragraphs = [item for item in inspection.objects if item.kind == "paragraph"]
    paragraph_index = 0
    table_index = 0
    sdt_index = 0
    blocks: list[BodyBlock] = []
    for child in body:
        if child.tag == _q(W_NS, "sectPr"):
            continue
        if child.tag == _q(W_NS, "p"):
            paragraph_index += 1
            para_id = child.get(_q(W14_NS, "paraId"))
            locator = (
                f"/body/p[@paraId={para_id}]" if para_id else f"/body/p[{paragraph_index}]"
            )
            kind = "paragraph"
            text = _paragraph_text(child)
            html_path = f"/body/p[{paragraph_index}]"
        elif child.tag == _q(W_NS, "tbl"):
            table_index += 1
            locator = f"/body/tbl[{table_index}]"
            kind = "table"
            text = _paragraph_text(child)
            html_path = f"/body/table[{table_index}]"
        elif child.tag == _q(W_NS, "sdt"):
            sdt_index += 1
            locator = f"/body/sdt[{sdt_index}]"
            kind = "content_control"
            text = _paragraph_text(child)
            html_path = None
        else:
            locator = f"/body/unsupported[{len(blocks) + 1}]"
            kind = "unsupported"
            text = _paragraph_text(child)
            html_path = None
        inspected = inspected_by_locator.get(locator)
        if inspected is None and kind == "paragraph":
            inspected = next(
                (
                    item
                    for item in remaining_paragraphs
                    if item.text == text and item.locator not in {block.locator for block in blocks}
                ),
                None,
            )
        reference = (
            dict(inspected.object_ref)
            if inspected is not None
            else _internal_ref(inspection.document_sha256, len(blocks), kind, child)
        )
        blocks.append(
            BodyBlock(
                index=len(blocks),
                kind=kind,
                element=child,
                locator=locator,
                html_path=html_path,
                text=text,
                object_ref=reference,
            )
        )
    return tuple(blocks)


def _block_for_ref(
    reference: Any,
    inspection: Inspection,
    blocks: tuple[BodyBlock, ...],
) -> BodyBlock:
    if isinstance(reference, dict):
        object_id = reference.get("object_id")
        internal = next(
            (
                block
                for block in blocks
                if block.object_ref.get("object_id") == object_id
            ),
            None,
        )
        if internal is not None:
            return internal
    inspected = resolve_object_ref(reference, inspection)
    by_object_id = {
        str(block.object_ref.get("object_id")): block for block in blocks
    }
    block = by_object_id.get(str(inspected.object_ref["object_id"]))
    if block is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="unsupported_atomic_boundary",
            message="The anchor is not a top-level body block and cannot be split safely.",
        )
    return block


def _section_for_block(root: ET.Element, block_index: int) -> ET.Element:
    body = root.find(_q(W_NS, "body"))
    if body is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_body_missing",
            message="The DOCX package contains no WordprocessingML body.",
        )
    blocks = [child for child in body if child.tag != _q(W_NS, "sectPr")]
    for child in blocks[block_index:]:
        properties = child.find(_q(W_NS, "pPr")) if child.tag == _q(W_NS, "p") else None
        section = properties.find(_q(W_NS, "sectPr")) if properties is not None else None
        if section is not None:
            return copy.deepcopy(section)
    section = body.find(_q(W_NS, "sectPr"))
    if section is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="section_properties_missing",
            message="The DOCX package contains no effective section properties.",
        )
    return copy.deepcopy(section)


def _page_count(html_path: Path) -> int:
    source = html_path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"\bdata-page(?:=|\b)", source)) or 1


def _render_layout(
    document: Path,
    office: OfficeCliAdapter,
    work_dir: Path,
) -> ReferenceLayout:
    work_dir.mkdir(parents=True, exist_ok=True)
    html_path = work_dir / "document.html"
    office.html(document, html_path)
    records = measure_html_layout(html_path, virtual_pages=True)
    measured_page_count = max(
        (int(item["page"]) for item in records if isinstance(item.get("page"), int)),
        default=1,
    )
    return ReferenceLayout(max(_page_count(html_path), measured_page_count), records)


def _visual_anchor(record: JsonObject) -> JsonObject:
    bbox = record.get("bbox")
    page_width = record.get("page_width")
    page_height = record.get("page_height")
    page = record.get("page")
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or not isinstance(page, int)
        or not isinstance(page_width, (int, float))
        or not isinstance(page_height, (int, float))
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="anchor_layout_shape",
            message="OfficeCLI returned incomplete anchor layout evidence.",
        )
    return {
        "page": page,
        "bbox_px": [float(value) for value in bbox],
        "page_width_px": float(page_width),
        "page_height_px": float(page_height),
    }


def _geometry(document: Path, anchor_index: int) -> JsonObject:
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(_q(W_NS, "body"))
    assert body is not None
    body_blocks = [child for child in body if child.tag != _q(W_NS, "sectPr")]
    section: ET.Element | None = None
    for child in body_blocks[anchor_index:]:
        properties = child.find(_q(W_NS, "pPr")) if child.tag == _q(W_NS, "p") else None
        candidate = properties.find(_q(W_NS, "sectPr")) if properties is not None else None
        if candidate is not None:
            section = candidate
            break
    if section is None:
        section = body.find(_q(W_NS, "sectPr"))
    page_size = section.find(_q(W_NS, "pgSz")) if section is not None else None
    margins = section.find(_q(W_NS, "pgMar")) if section is not None else None

    def value(element: ET.Element | None, name: str, default: int) -> int:
        raw = element.get(_q(W_NS, name)) if element is not None else None
        return int(raw) if isinstance(raw, str) and raw.lstrip("-").isdigit() else default

    width = value(page_size, "w", 11906)
    height = value(page_size, "h", 16838)
    orientation = (
        page_size.get(_q(W_NS, "orient"), "portrait")
        if page_size is not None
        else "portrait"
    )
    return {
        "page_width_twips": width,
        "page_height_twips": height,
        "orientation": orientation,
        "margin_top_twips": value(margins, "top", 1440),
        "margin_bottom_twips": value(margins, "bottom", 1440),
        "margin_left_twips": value(margins, "left", 1440),
        "margin_right_twips": value(margins, "right", 1440),
        "header_distance_twips": value(margins, "header", 720),
        "footer_distance_twips": value(margins, "footer", 720),
    }


def _top_twips(visual: JsonObject, geometry: JsonObject) -> int:
    bbox = visual["bbox_px"]
    assert isinstance(bbox, list)
    return round(
        float(bbox[1])
        / float(visual["page_height_px"])
        * int(geometry["page_height_twips"])
    )


def _register_namespaces(xml: bytes) -> dict[str, str]:
    namespaces: dict[str, str] = {}
    for _, value in ET.iterparse(io.BytesIO(xml), events=("start-ns",)):
        prefix, namespace = cast(tuple[str, str], value)
        if prefix == "xml":
            continue
        namespaces[prefix] = namespace
        try:
            ET.register_namespace(prefix, namespace)
        except ValueError:
            continue
    return namespaces


def _write_page_break_candidate(source: Path, destination: Path, block_index: int) -> None:
    with zipfile.ZipFile(source) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    document_xml = next(data for item, data in entries if item.filename == "word/document.xml")
    namespaces = _register_namespaces(document_xml)
    root = ET.fromstring(document_xml)
    body = root.find(_q(W_NS, "body"))
    if body is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_body_missing",
            message="The DOCX package contains no WordprocessingML body.",
        )
    blocks = [child for child in body if child.tag != _q(W_NS, "sectPr")]
    if not 0 <= block_index < len(blocks) or blocks[block_index].tag != _q(W_NS, "p"):
        raise ToolFailure(
            status="error",
            origin="document",
            code="unsupported_atomic_boundary",
            message="A next-page boundary can only be inserted before a top-level paragraph.",
        )
    paragraph = blocks[block_index]
    properties = paragraph.find(_q(W_NS, "pPr"))
    if properties is None:
        properties = ET.Element(_q(W_NS, "pPr"))
        paragraph.insert(0, properties)
    if properties.find(_q(W_NS, "pageBreakBefore")) is None:
        insertion = 0
        allowed_before = {
            _q(W_NS, "pStyle"),
            _q(W_NS, "keepNext"),
            _q(W_NS, "keepLines"),
        }
        for index, child in enumerate(properties):
            if child.tag in allowed_before:
                insertion = index + 1
        properties.insert(insertion, ET.Element(_q(W_NS, "pageBreakBefore")))
    replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    root_start = replacement.find(b"<w:document")
    root_end = replacement.find(b">", root_start)
    if root_start >= 0 and root_end >= 0:
        opening = replacement[root_start:root_end]
        missing = b"".join(
            (
                f' xmlns:{prefix}="{namespace}"'.encode()
                if prefix
                else f' xmlns="{namespace}"'.encode()
            )
            for prefix, namespace in namespaces.items()
            if (f"xmlns:{prefix}=" if prefix else "xmlns=").encode() not in opening
        )
        replacement = replacement[:root_end] + missing + replacement[root_end:]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as output:
        for info, data in entries:
            output.writestr(info, replacement if info.filename == "word/document.xml" else data)


def _strip_document_start_boundary(block: ET.Element) -> None:
    if block.tag != _q(W_NS, "p"):
        return
    properties = block.find(_q(W_NS, "pPr"))
    if properties is not None:
        page_break_before = properties.find(_q(W_NS, "pageBreakBefore"))
        if page_break_before is not None:
            properties.remove(page_break_before)
        if not list(properties) and not properties.attrib and not (properties.text or "").strip():
            block.remove(properties)
    for parent in block.iter():
        for child in list(parent):
            if (
                child.tag == _q(W_NS, "br")
                and child.get(_q(W_NS, "type"), "textWrapping") == "page"
            ):
                parent.remove(child)


def _move_terminal_section_to_body(
    selected: list[ET.Element],
    fallback: ET.Element,
) -> ET.Element:
    if not selected or selected[-1].tag != _q(W_NS, "p"):
        return fallback
    properties = selected[-1].find(_q(W_NS, "pPr"))
    section = properties.find(_q(W_NS, "sectPr")) if properties is not None else None
    if section is None or properties is None:
        return fallback
    properties.remove(section)
    if not list(properties) and not properties.attrib and not (properties.text or "").strip():
        selected[-1].remove(properties)
    return section


def _ref_ids(references: Any) -> tuple[str, ...]:
    if not isinstance(references, list) or not all(
        isinstance(reference, dict) and isinstance(reference.get("object_id"), str)
        for reference in references
    ):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="invalid_resolved_boundary_recipe",
            message="The resolved boundary recipe contains invalid object references.",
        )
    return tuple(cast(dict[str, Any], reference)["object_id"] for reference in references)


def materialize_resolved_unit(
    source: Path,
    destination: Path,
    inspection: Inspection,
    resolved_unit: JsonObject,
    *,
    next_anchor_ref: JsonObject | None,
    next_resolved_unit: JsonObject | None = None,
) -> JsonObject:
    """Write one standalone DOCX from a resolved logical-unit boundary recipe.

    The document start becomes the unit's sole page-boundary owner. Natural-flow
    filler marked ``boundary_consumed`` is omitted, while the resolver-selected
    visible leading and trailing layout blocks are retained exactly once.
    """

    source_hash = sha256_file(source)
    if (
        inspection.document_sha256 != source_hash
        or resolved_unit.get("source_sha256") != source_hash
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="boundary_request_snapshot_mismatch",
            message="The materialization recipe is not bound to the current DOCX snapshot.",
        )
    if resolved_unit.get("status") != "resolved":
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="unresolved_unit_not_publishable",
            message="Only a uniquely resolved unit may be materialized.",
        )
    boundary = resolved_unit.get("resolved_boundary")
    anchor_reference = resolved_unit.get("first_visible_anchor_ref")
    if not isinstance(boundary, dict) or not isinstance(anchor_reference, dict):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="invalid_resolved_boundary_recipe",
            message="The resolved unit is missing its boundary or first-anchor reference.",
        )

    blocks = _body_blocks(source, inspection)
    anchor = _block_for_ref(anchor_reference, inspection, blocks)
    leading_ids = _ref_ids(boundary.get("leading_layout_refs"))
    consumed_ids = _ref_ids(boundary.get("boundary_consumed_refs"))
    trailing_ids = _ref_ids(boundary.get("trailing_layout_refs"))
    leading = tuple(
        _block_for_ref(reference, inspection, blocks)
        for reference in cast(list[JsonObject], boundary["leading_layout_refs"])
    )
    consumed = tuple(
        _block_for_ref(reference, inspection, blocks)
        for reference in cast(list[JsonObject], boundary["boundary_consumed_refs"])
    )
    if any(not block.layout_only for block in (*leading, *consumed)):
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="semantic_block_marked_as_layout",
            message="A semantic source block was marked as boundary-only layout.",
        )
    source_leading = _layout_run_before(blocks, anchor.index)
    source_leading_ids = tuple(
        str(block.object_ref.get("object_id")) for block in source_leading
    )
    expected_leading_ids = consumed_ids + leading_ids
    if resolved_unit.get("source_boundary_mode") == "explicit_section_break":
        owner_reference = boundary.get("boundary_owner_ref")
        owner = _block_for_ref(owner_reference, inspection, blocks)
        if owner.layout_only and owner.index < anchor.index:
            expected_leading_ids = (
                *consumed_ids,
                str(owner.object_ref.get("object_id")),
                *leading_ids,
            )
    if source_leading_ids != expected_leading_ids:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="boundary_recipe_not_contiguous",
            message="The consumed and visible leading blocks do not cover one source run.",
        )

    start_index = leading[0].index if leading else anchor.index
    adjacent_visible_count = 0
    if next_anchor_ref is None:
        end_index = len(blocks)
    else:
        next_anchor = _block_for_ref(next_anchor_ref, inspection, blocks)
        end_index = next_anchor.index
        source_trailing_ids = tuple(
            str(block.object_ref.get("object_id"))
            for block in _layout_run_before(blocks, next_anchor.index)
        )
        if source_trailing_ids != trailing_ids:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="trailing_boundary_recipe_mismatch",
                message="The trailing layout recipe does not match the next source boundary.",
            )
        if next_resolved_unit is not None:
            if (
                next_resolved_unit.get("status") != "resolved"
                or next_resolved_unit.get("source_sha256") != source_hash
            ):
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="unresolved_next_unit_not_publishable",
                    message="The adjacent unit recipe is not resolved for this source.",
                )
            next_boundary = next_resolved_unit.get("resolved_boundary")
            next_unit_anchor = next_resolved_unit.get("first_visible_anchor_ref")
            if not isinstance(next_boundary, dict) or not isinstance(next_unit_anchor, dict):
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="invalid_resolved_boundary_recipe",
                    message="The adjacent unit recipe is missing its boundary references.",
                )
            resolved_next_anchor = _block_for_ref(next_unit_anchor, inspection, blocks)
            if resolved_next_anchor.index != next_anchor.index:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="adjacent_anchor_mismatch",
                    message="The current and adjacent unit recipes identify different anchors.",
                )
            next_leading_value = next_boundary.get("leading_layout_refs")
            _ref_ids(next_leading_value)
            next_leading = cast(list[JsonObject], next_leading_value)
            adjacent_visible_count = len(next_leading)
            if next_leading:
                end_index = _block_for_ref(
                    next_leading[0], inspection, blocks
                ).index
    if not start_index < end_index:
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="invalid_unit_block_range",
            message="The resolved unit has an empty or reversed source block range.",
        )

    with zipfile.ZipFile(source) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    document_xml = next(data for item, data in entries if item.filename == "word/document.xml")
    namespaces = _register_namespaces(document_xml)
    root = ET.fromstring(document_xml)
    body = root.find(_q(W_NS, "body"))
    if body is None:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_body_missing",
            message="The DOCX package contains no WordprocessingML body.",
        )
    source_elements = [child for child in body if child.tag != _q(W_NS, "sectPr")]
    selected = [copy.deepcopy(child) for child in source_elements[start_index:end_index]]
    _strip_document_start_boundary(selected[0])
    final_section = _move_terminal_section_to_body(
        selected,
        _section_for_block(root, end_index - 1),
    )
    for child in list(body):
        body.remove(child)
    for child in selected:
        body.append(child)
    body.append(copy.deepcopy(final_section))

    replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    root_start = replacement.find(b"<w:document")
    root_end = replacement.find(b">", root_start)
    if root_start >= 0 and root_end >= 0:
        opening = replacement[root_start:root_end]
        missing = b"".join(
            (
                f' xmlns:{prefix}="{namespace}"'.encode()
                if prefix
                else f' xmlns="{namespace}"'.encode()
            )
            for prefix, namespace in namespaces.items()
            if (f"xmlns:{prefix}=" if prefix else "xmlns=").encode() not in opening
        )
        replacement = replacement[:root_end] + missing + replacement[root_end:]

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="unit-materialize-", dir=destination.parent
    ) as temporary_name:
        temporary = Path(temporary_name) / destination.name
        with zipfile.ZipFile(temporary, "w") as output:
            for info, data in entries:
                output.writestr(
                    info,
                    replacement if info.filename == "word/document.xml" else data,
                )
        warnings = validate_docx_package(temporary)
        temporary.replace(destination)
    if sha256_file(source) != source_hash:
        destination.unlink(missing_ok=True)
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="source_document_changed",
            message="The source DOCX changed during unit materialization.",
        )
    return {
        "schema_version": 1,
        "status": "materialized",
        "unit_id": resolved_unit.get("unit_id"),
        "source_sha256": source_hash,
        "output_sha256": sha256_file(destination),
        "source_block_range": [start_index, end_index],
        "materialized_block_count": len(selected),
        "document_start_owns_boundary": True,
        "leading_layout_block_count": len(leading_ids),
        "boundary_consumed_block_count": len(consumed_ids),
        "trailing_layout_block_count": len(trailing_ids),
        "adjacent_visible_leading_excluded_count": adjacent_visible_count,
        "package_warnings": list(warnings),
    }


def _visible_sequence(document: Path) -> tuple[str, ...]:
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(_q(W_NS, "body"))
    if body is None:
        return ()
    return tuple(
        text
        for child in body
        if child.tag != _q(W_NS, "sectPr")
        if (text := _paragraph_text(child))
    )


def _xml_signature(element: ET.Element) -> tuple[Any, ...]:
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        element.text,
        element.tail,
        tuple(_xml_signature(child) for child in element),
    )


def _candidate_mutation_is_bounded(
    source: Path,
    candidate: Path,
    block_index: int | None,
) -> bool:
    if block_index is None:
        return sha256_file(source) == sha256_file(candidate)
    with zipfile.ZipFile(source) as source_archive, zipfile.ZipFile(candidate) as candidate_archive:
        if source_archive.namelist() != candidate_archive.namelist():
            return False
        for name in source_archive.namelist():
            if (
                name != "word/document.xml"
                and source_archive.read(name) != candidate_archive.read(name)
            ):
                return False
        source_root = ET.fromstring(source_archive.read("word/document.xml"))
        candidate_root = ET.fromstring(candidate_archive.read("word/document.xml"))
    source_body = source_root.find(_q(W_NS, "body"))
    candidate_body = candidate_root.find(_q(W_NS, "body"))
    if source_body is None or candidate_body is None:
        return False
    source_blocks = [child for child in source_body if child.tag != _q(W_NS, "sectPr")]
    candidate_blocks = [
        child for child in candidate_body if child.tag != _q(W_NS, "sectPr")
    ]
    if not 0 <= block_index < len(source_blocks) or block_index >= len(candidate_blocks):
        return False
    source_properties = source_blocks[block_index].find(_q(W_NS, "pPr"))
    paragraph = candidate_blocks[block_index]
    properties = paragraph.find(_q(W_NS, "pPr"))
    page_break = properties.find(_q(W_NS, "pageBreakBefore")) if properties is not None else None
    if properties is None or page_break is None:
        return False
    properties.remove(page_break)
    if (
        source_properties is None
        and not list(properties)
        and not properties.attrib
        and not (properties.text or "").strip()
    ):
        paragraph.remove(properties)
    return _xml_signature(source_root) == _xml_signature(candidate_root)


def _records_match(
    expected: JsonObject | None,
    actual: JsonObject | None,
    geometry: JsonObject,
    tolerance_twips: int,
) -> bool:
    if expected is None or actual is None:
        return expected is actual
    expected_visual = _visual_anchor(expected)
    actual_visual = _visual_anchor(actual)
    return bool(
        expected_visual["page"] == actual_visual["page"]
        and abs(
            _top_twips(expected_visual, geometry) - _top_twips(actual_visual, geometry)
        )
        <= tolerance_twips
    )


def _office_schema_valid(document: Path, office: OfficeCliAdapter) -> bool:
    try:
        office.validate(document)
    except ToolFailure as error:
        if error.origin == "engine" and error.code == "officecli_failed":
            return False
        raise
    return True


def _layout_run_before(blocks: tuple[BodyBlock, ...], index: int) -> tuple[BodyBlock, ...]:
    run: list[BodyBlock] = []
    cursor = index - 1
    while cursor >= 0 and blocks[cursor].layout_only:
        run.insert(0, blocks[cursor])
        cursor -= 1
    return tuple(run)


def _anchor_from_request(
    unit: JsonObject,
    inspection: Inspection,
    blocks: tuple[BodyBlock, ...],
) -> tuple[BodyBlock | None, JsonObject | None]:
    expected_text = unit.get("first_visible_anchor_text")
    if not isinstance(expected_text, str) or not expected_text:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="first_visible_anchor_required",
            message="A boundary unit requires non-empty first-visible-anchor text.",
        )
    reference = unit.get("first_visible_anchor_ref")
    if isinstance(reference, dict):
        anchor = _block_for_ref(reference, inspection, blocks)
        if not anchor.text.startswith(expected_text):
            return None, {
                "status": "unsupported",
                "unit_id": unit.get("unit_id"),
                "source_boundary_mode": "unsupported",
                "warnings": [
                    {
                        "code": "unsupported_atomic_boundary",
                        "message": (
                            "The first visible anchor is not the start of a top-level body "
                            "block."
                        ),
                    }
                ],
            }
        return anchor, None

    matches = [block for block in blocks if block.text.startswith(expected_text)]
    next_reference = unit.get("next_visible_anchor_ref")
    if isinstance(next_reference, dict):
        next_anchor = _block_for_ref(next_reference, inspection, blocks)
        matches = [block for block in matches if block.index < next_anchor.index]
        if matches:
            nearest = max(block.index for block in matches)
            matches = [block for block in matches if block.index == nearest]
    if len(matches) == 1:
        return matches[0], None
    return None, {
        "status": "ambiguous",
        "unit_id": unit.get("unit_id"),
        "source_boundary_mode": "ambiguous",
        "warnings": [
            {
                "code": "ambiguous_anchor_mapping",
                "message": "The supplied evidence does not identify one top-level anchor.",
            }
        ],
    }


class UnitBoundaryResolver:
    """Resolve internal PoC boundary recipes without changing public Tool contracts."""

    def __init__(self, office: OfficeCliAdapter, *, tolerance_twips: int = 240) -> None:
        self.office = office
        self.tolerance_twips = tolerance_twips

    def measure_reference_anchor(
        self,
        document: Path,
        inspection: Inspection,
        anchor_ref: JsonObject,
        *,
        work_dir: Path,
    ) -> JsonObject:
        blocks = _body_blocks(document, inspection)
        anchor = _block_for_ref(anchor_ref, inspection, blocks)
        layout = _render_layout(document, self.office, work_dir)
        record = layout.for_path(anchor.html_path)
        if record is None:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="anchor_layout_missing",
                message="OfficeCLI returned no layout evidence for the requested anchor.",
            )
        return _visual_anchor(record)

    def resolve(
        self,
        document: Path,
        inspection: Inspection,
        request: JsonObject,
        *,
        work_dir: Path,
    ) -> JsonObject:
        source_hash = sha256_file(document)
        if request.get("schema_version") != 1 or request.get("source_sha256") != source_hash:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="boundary_request_snapshot_mismatch",
                message="The boundary request is not bound to the current DOCX snapshot.",
            )
        units = request.get("units")
        if (
            not isinstance(units, list)
            or not units
            or not all(isinstance(unit, dict) for unit in units)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_boundary_units",
                message="The boundary request requires at least one unit object.",
            )
        blocks = _body_blocks(document, inspection)
        resolved = [
            self._resolve_unit(document, inspection, blocks, unit, work_dir=work_dir)
            for unit in units
        ]
        if sha256_file(document) != source_hash:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="source_document_changed",
                message="The source DOCX changed during boundary resolution.",
            )
        statuses = {str(unit["status"]) for unit in resolved}
        if statuses == {"resolved"}:
            status = "resolved"
        elif "ambiguous" in statuses:
            status = "ambiguous"
        else:
            status = "unsupported"
        return {
            "schema_version": 1,
            "status": status,
            "source_sha256": source_hash,
            "units": resolved,
        }

    def _resolve_unit(
        self,
        document: Path,
        inspection: Inspection,
        blocks: tuple[BodyBlock, ...],
        unit: JsonObject,
        *,
        work_dir: Path,
    ) -> JsonObject:
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_unit_id",
                message="Each boundary unit requires a non-empty unit_id.",
            )
        anchor, anchor_failure = _anchor_from_request(unit, inspection, blocks)
        if anchor_failure is not None:
            return anchor_failure
        assert anchor is not None
        leading = _layout_run_before(blocks, anchor.index)
        previous_index = (leading[0].index if leading else anchor.index) - 1
        region_start = max(0, previous_index)
        boundary_region = blocks[region_start : anchor.index + 1]
        page_break_owners = [block for block in boundary_region if block.explicit_page_break]
        page_break_before_owners = [
            block for block in (*leading, anchor) if block.page_break_before
        ]
        section_owners = []
        for block in boundary_region:
            section = block.section_break
            if section is None:
                continue
            break_type = section.find(_q(W_NS, "type"))
            value = (
                break_type.get(_q(W_NS, "val"), "nextPage")
                if break_type is not None
                else "nextPage"
            )
            if value in {"nextPage", "oddPage", "evenPage"}:
                section_owners.append(block)
        mechanisms = sum(
            bool(owners)
            for owners in (page_break_owners, page_break_before_owners, section_owners)
        )
        if mechanisms > 1 or any(
            len(owners) > 1
            for owners in (page_break_owners, page_break_before_owners, section_owners)
        ):
            return {
                "status": "ambiguous",
                "unit_id": unit_id,
                "source_boundary_mode": "ambiguous",
                "warnings": [
                    {
                        "code": "multiple_boundary_owners",
                        "message": "More than one pagination owner applies to this boundary.",
                    }
                ],
            }

        if page_break_owners:
            owner = page_break_owners[0]
            source_mode = "explicit_page_break"
            resolved_mode = "preserve_explicit_page_break"
        elif page_break_before_owners:
            owner = page_break_before_owners[0]
            source_mode = "explicit_page_break_before"
            resolved_mode = "preserve_explicit_page_break_before"
        elif section_owners:
            owner = section_owners[0]
            source_mode = "explicit_section_break"
            resolved_mode = "preserve_explicit_section_break"
        elif unit.get("starts_on_new_page") is True:
            owner = None
            source_mode = (
                "natural_flow_with_layout_blocks"
                if leading
                else "natural_flow_without_layout_blocks"
            )
            resolved_mode = "next_page"
        else:
            return {
                "status": "unsupported",
                "unit_id": unit_id,
                "source_boundary_mode": "unsupported",
                "warnings": [
                    {
                        "code": "unsupported_boundary_mode",
                        "message": "No supported new-page boundary fact applies to this unit.",
                    }
                ],
            }

        geometry = _geometry(document, anchor.index)
        visual = unit.get("visual_anchor")
        if not isinstance(visual, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="visual_anchor_required",
                message="A boundary unit requires visual anchor evidence.",
            )
        target_top = _top_twips(visual, geometry)

        next_anchor: BodyBlock | None = None
        next_reference = unit.get("next_visible_anchor_ref")
        if isinstance(next_reference, dict):
            next_anchor = _block_for_ref(next_reference, inspection, blocks)
            if next_anchor.index <= anchor.index:
                return {
                    "status": "ambiguous",
                    "unit_id": unit_id,
                    "source_boundary_mode": source_mode,
                    "warnings": [{"code": "next_anchor_order_invalid"}],
                }
        trailing = _layout_run_before(blocks, next_anchor.index) if next_anchor else ()
        previous = blocks[previous_index] if previous_index >= 0 else None

        candidate_specs: list[tuple[str, int | None, tuple[BodyBlock, ...], tuple[BodyBlock, ...]]]
        if owner is not None:
            explicit_leading = (
                tuple(block for block in leading if block != owner)
                if source_mode == "explicit_section_break"
                else leading
            )
            candidate_specs = [
                ("preserve-source-boundary", None, explicit_leading, ())
            ]
        else:
            candidate_specs = []
            for keep_count in range(len(leading) + 1):
                kept = leading[-keep_count:] if keep_count else ()
                consumed = leading[:-keep_count] if keep_count else leading
                target = kept[0] if kept else anchor
                candidate_specs.append(
                    (f"candidate-{keep_count}", target.index, kept, consumed)
                )

        work_dir.mkdir(parents=True, exist_ok=True)
        matches: list[
            tuple[
                str,
                int | None,
                tuple[BodyBlock, ...],
                tuple[BodyBlock, ...],
                JsonObject,
            ]
        ] = []
        evidence: list[JsonObject] = []
        with tempfile.TemporaryDirectory(prefix="unit-boundary-", dir=work_dir) as name:
            temporary = Path(name)
            source_schema_valid = _office_schema_valid(document, self.office)
            source_layout = _render_layout(document, self.office, temporary / "source")
            source_previous = source_layout.for_path(previous.html_path) if previous else None
            source_next = source_layout.for_path(next_anchor.html_path) if next_anchor else None
            source_visible = _visible_sequence(document)
            for candidate_id, target_index, kept, consumed in candidate_specs:
                candidate = temporary / f"{candidate_id}.docx"
                if target_index is None:
                    shutil.copyfile(document, candidate)
                else:
                    _write_page_break_candidate(document, candidate, target_index)
                validate_docx_package(candidate)
                candidate_schema_valid = _office_schema_valid(candidate, self.office)
                mutation_bounded = _candidate_mutation_is_bounded(
                    document,
                    candidate,
                    target_index,
                )
                semantic_content_preserved = _visible_sequence(candidate) == source_visible
                candidate_layout = _render_layout(
                    candidate,
                    self.office,
                    temporary / candidate_id,
                )
                candidate_record = candidate_layout.for_path(anchor.html_path)
                candidate_previous = (
                    candidate_layout.for_path(previous.html_path) if previous else None
                )
                candidate_next = (
                    candidate_layout.for_path(next_anchor.html_path) if next_anchor else None
                )
                if candidate_record is None:
                    matched = False
                    candidate_page: int | None = None
                    candidate_top: int | None = None
                else:
                    candidate_visual = _visual_anchor(candidate_record)
                    candidate_page = int(candidate_visual["page"])
                    candidate_top = _top_twips(candidate_visual, geometry)
                    matched = bool(
                        semantic_content_preserved
                        and mutation_bounded
                        and (candidate_schema_valid or not source_schema_valid)
                        and candidate_page == visual.get("page")
                        and abs(candidate_top - target_top) <= self.tolerance_twips
                        and candidate_layout.page_count == source_layout.page_count
                        and _records_match(
                            source_previous,
                            candidate_previous,
                            geometry,
                            self.tolerance_twips,
                        )
                        and _records_match(
                            source_next,
                            candidate_next,
                            geometry,
                            self.tolerance_twips,
                        )
                    )
                record: JsonObject = {
                    "candidate_id": candidate_id,
                    "matched": matched,
                    "semantic_content_preserved": semantic_content_preserved,
                    "mutation_bounded": mutation_bounded,
                    "office_schema_valid": candidate_schema_valid,
                    "page_count_preserved": candidate_layout.page_count
                    == source_layout.page_count,
                    "anchor_page": candidate_page,
                    "anchor_page_top_twips": candidate_top,
                    "candidate_sha256": sha256_file(candidate),
                }
                evidence.append(record)
                if matched:
                    matches.append((candidate_id, target_index, kept, consumed, record))

        if len(matches) != 1:
            return {
                "status": "ambiguous",
                "unit_id": unit_id,
                "source_boundary_mode": source_mode,
                "candidate_evidence": {
                    "candidate_count": len(candidate_specs),
                    "match_count": len(matches),
                    "unique_match": False,
                    "candidates": evidence,
                },
                "warnings": [
                    {
                        "code": (
                            "no_candidate_match" if not matches else "multiple_candidate_matches"
                        )
                    }
                ],
            }

        selected_id, target_index, kept, consumed, _ = matches[0]
        insert_before = anchor if target_index is None else blocks[target_index]
        boundary_owner = owner if owner is not None else insert_before
        return {
            "status": "resolved",
            "source_sha256": inspection.document_sha256,
            "unit_id": unit_id,
            "first_visible_anchor_ref": anchor.object_ref,
            "source_boundary_mode": source_mode,
            "section_geometry": geometry,
            "visual_metrics": {
                "anchor_page_top_twips": target_top,
                "anchor_content_top_gap_twips": target_top
                - int(geometry["margin_top_twips"]),
            },
            "resolved_boundary": {
                "mode": resolved_mode,
                "boundary_owner_ref": boundary_owner.object_ref,
                "insert_before_ref": insert_before.object_ref,
                "leading_layout_refs": [block.object_ref for block in kept],
                "trailing_layout_refs": [block.object_ref for block in trailing],
                "boundary_consumed_refs": [block.object_ref for block in consumed],
            },
            "candidate_evidence": {
                "selected_candidate_id": selected_id,
                "candidate_count": len(candidate_specs),
                "unique_match": True,
                "candidates": evidence,
            },
            "warnings": (
                []
                if source_schema_valid
                else [
                    {
                        "code": "source_schema_invalid",
                        "message": (
                            "The source has pre-existing Office schema errors; the candidate "
                            "passed package checks but inherits that invalid baseline."
                        ),
                    }
                ]
            ),
        }

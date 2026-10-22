"""Small independent OOXML package checks used as postconditions."""

from __future__ import annotations

import os
import posixpath
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from docfit.tools.runtime import ToolFailure

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CUSTOM_PROPERTIES_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
CUSTOM_PROPERTIES_PART = "docProps/custom.xml"
VT_PROPERTY_TYPES = {
    "array",
    "blob",
    "bool",
    "bstr",
    "cf",
    "clsid",
    "cy",
    "date",
    "decimal",
    "empty",
    "error",
    "filetime",
    "i1",
    "i2",
    "i4",
    "i8",
    "int",
    "lpstr",
    "lpwstr",
    "null",
    "oblob",
    "ostorage",
    "ostream",
    "r4",
    "r8",
    "storage",
    "stream",
    "ui1",
    "ui2",
    "ui4",
    "ui8",
    "uint",
    "vector",
    "vstream",
}

ET.register_namespace("op", CUSTOM_PROPERTIES_NS)
ET.register_namespace("vt", VT_NS)


def _relationship_owner(rels_name: str) -> str:
    path = PurePosixPath(rels_name)
    if path == PurePosixPath("_rels/.rels"):
        return ""
    parts = list(path.parts)
    if len(parts) < 2 or parts[-2] != "_rels" or not parts[-1].endswith(".rels"):
        return ""
    owner_name = parts[-1][:-5]
    return str(PurePosixPath(*parts[:-2], owner_name))


def _resolve_target(owner: str, target: str) -> str:
    base = posixpath.dirname(owner)
    return posixpath.normpath(posixpath.join(base, target)).lstrip("/")


def _normalize_custom_properties_xml(payload: bytes) -> tuple[bytes, bool]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="invalid_custom_properties_xml",
            message="The DOCX custom properties part contains invalid XML.",
        ) from error
    changed = False
    for property_node in root.findall(f"{{{CUSTOM_PROPERTIES_NS}}}property"):
        for child in list(property_node):
            if not isinstance(child.tag, str) or child.tag.startswith("{"):
                continue
            if child.tag in VT_PROPERTY_TYPES:
                child.tag = f"{{{VT_NS}}}{child.tag}"
                changed = True
    if not changed:
        return payload, False
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), True


def normalize_docx_custom_properties(path: Path) -> tuple[str, ...]:
    """Repair namespace-less custom property value nodes produced by Office backends."""

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            parts = {info.filename: archive.read(info.filename) for info in infos}
    except zipfile.BadZipFile as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="invalid_docx_package",
            message="The input is not a readable DOCX package.",
        ) from error
    payload = parts.get(CUSTOM_PROPERTIES_PART)
    if payload is None:
        return ()
    normalized, changed = _normalize_custom_properties_xml(payload)
    if not changed:
        return ()
    parts[CUSTOM_PROPERTIES_PART] = normalized
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-normalize-",
        suffix=".docx",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w") as result:
            for info in infos:
                result.writestr(info, parts[info.filename])
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return ("normalized_custom_property_value_namespaces",)


def validate_docx_package(path: Path) -> tuple[str, ...]:
    """Raise a normalized document failure for corrupt or dangling packages."""

    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            missing = sorted(required - names)
            if missing:
                raise ToolFailure(
                    status="error",
                    origin="document",
                    code="missing_package_parts",
                    message="The DOCX package is missing required OOXML parts.",
                )
            corrupt = archive.testzip()
            if corrupt is not None:
                raise ToolFailure(
                    status="error",
                    origin="document",
                    code="corrupt_zip_member",
                    message="The DOCX package contains a corrupt member.",
                )
            for name in sorted(names):
                if name.endswith(".xml") or name.endswith(".rels"):
                    try:
                        root = ET.fromstring(archive.read(name))
                    except ET.ParseError as error:
                        raise ToolFailure(
                            status="error",
                            origin="document",
                            code="invalid_package_xml",
                            message="The DOCX package contains invalid XML.",
                        ) from error
                    if not name.endswith(".rels"):
                        continue
                    owner = _relationship_owner(name)
                    for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
                        if relationship.get("TargetMode") == "External":
                            continue
                        target = relationship.get("Target")
                        if not target:
                            warnings.append("relationship_without_target")
                            continue
                        resolved = _resolve_target(owner, target)
                        if resolved not in names:
                            raise ToolFailure(
                                status="error",
                                origin="document",
                                code="dangling_relationship",
                                message="The DOCX package contains a dangling relationship.",
                            )
    except zipfile.BadZipFile as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="invalid_docx_package",
            message="The input is not a readable DOCX package.",
        ) from error
    return tuple(warnings)

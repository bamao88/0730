"""Small independent OOXML package checks used as postconditions."""

from __future__ import annotations

import os
import posixpath
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from docfit.tools.runtime import ToolFailure

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
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

_MC_PREFIX_LIST_ATTRIBUTES = {
    f"{{{MC_NS}}}Ignorable",
    f"{{{MC_NS}}}MustUnderstand",
    f"{{{MC_NS}}}PreserveAttributes",
    f"{{{MC_NS}}}PreserveElements",
    f"{{{MC_NS}}}ProcessContent",
}
_WORD_CELL_BLOCK_TAGS = {
    f"{{{W_NS}}}altChunk",
    f"{{{W_NS}}}customXml",
    f"{{{W_NS}}}p",
    f"{{{W_NS}}}sdt",
    f"{{{W_NS}}}tbl",
}


def _invalid_word_xml_contract(message: str) -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="document",
        code="invalid_word_xml_contract",
        message=message,
    )


def _validate_word_xml_contract(payload: bytes, root: ET.Element) -> None:
    if not any(
        isinstance(element.tag, str)
        and element.tag.startswith((f"{{{W_NS}}}", f"{{{MC_NS}}}"))
        for element in root.iter()
    ):
        return
    declared_prefixes = {
        prefix
        for _event, (prefix, _uri) in ET.iterparse(
            BytesIO(payload), events=("start-ns",)
        )
        if prefix
    }
    for element in root.iter():
        for name, value in element.attrib.items():
            is_choice_requires = (
                element.tag == f"{{{MC_NS}}}Choice" and name == "Requires"
            )
            if name not in _MC_PREFIX_LIST_ATTRIBUTES and not is_choice_requires:
                continue
            referenced = {token.split(":", 1)[0] for token in value.split()}
            if referenced - declared_prefixes:
                raise _invalid_word_xml_contract(
                    "The DOCX contains an undeclared Markup Compatibility prefix."
                )
    for cell in root.iter(f"{{{W_NS}}}tc"):
        if not any(child.tag in _WORD_CELL_BLOCK_TAGS for child in cell):
            raise _invalid_word_xml_contract(
                "The DOCX contains a table cell without block content."
            )


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
                    payload = archive.read(name)
                    try:
                        root = ET.fromstring(payload)
                    except ET.ParseError as error:
                        raise ToolFailure(
                            status="error",
                            origin="document",
                            code="invalid_package_xml",
                            message="The DOCX package contains invalid XML.",
                        ) from error
                    if not name.endswith(".rels"):
                        _validate_word_xml_contract(payload, root)
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

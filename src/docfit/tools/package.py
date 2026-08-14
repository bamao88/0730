"""Small independent OOXML package checks used as postconditions."""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from docfit.tools.runtime import ToolFailure

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


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

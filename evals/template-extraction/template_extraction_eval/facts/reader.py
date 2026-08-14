"""Read DOCX ZIP parts and relationships without importing product code."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from ..contracts import sha256_file
from ..models import RelationshipFact

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_PREFIX = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"


class PackageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class StoryPart:
    story: str
    part: str
    root: ElementTree.Element


@dataclass(frozen=True)
class DocxPackage:
    path: Path
    document_sha256: str
    parts: Mapping[str, bytes]
    relationships: tuple[RelationshipFact, ...]

    def bytes(self, part: str) -> bytes:
        try:
            return self.parts[part]
        except KeyError as error:
            raise PackageValidationError(f"missing DOCX part: {part}") from error

    def xml(self, part: str) -> ElementTree.Element:
        try:
            return ElementTree.fromstring(self.bytes(part))
        except ElementTree.ParseError as error:
            raise PackageValidationError(f"invalid XML in {part}: {error}") from error

    def relationships_for(self, source_part: str) -> tuple[RelationshipFact, ...]:
        return tuple(
            relationship
            for relationship in self.relationships
            if relationship.source_part == source_part
        )

    def relationship(self, source_part: str, relationship_id: str) -> RelationshipFact | None:
        return next(
            (
                relationship
                for relationship in self.relationships_for(source_part)
                if relationship.relationship_id == relationship_id
            ),
            None,
        )

    def story_parts(self) -> tuple[StoryPart, ...]:
        result = [StoryPart("document", "word/document.xml", self.xml("word/document.xml"))]
        story_types = {
            f"{OFFICE_REL_PREFIX}header": "header",
            f"{OFFICE_REL_PREFIX}footer": "footer",
            f"{OFFICE_REL_PREFIX}footnotes": "footnote",
            f"{OFFICE_REL_PREFIX}endnotes": "endnote",
        }
        for relationship in self.relationships_for("word/document.xml"):
            story = story_types.get(relationship.relationship_type)
            if story is None or relationship.resolved_target is None:
                continue
            result.append(
                StoryPart(
                    story,
                    relationship.resolved_target,
                    self.xml(relationship.resolved_target),
                )
            )
        return tuple(result)


def _source_part_for_rels(rels_part: str) -> str:
    if rels_part == "_rels/.rels":
        return ""
    path = PurePosixPath(rels_part)
    if path.parent.name != "_rels" or not path.name.endswith(".rels"):
        raise PackageValidationError(f"invalid relationship part path: {rels_part}")
    source_name = path.name.removesuffix(".rels")
    return (path.parent.parent / source_name).as_posix()


def _resolve_target(source_part: str, target: str) -> str:
    if target.startswith("/"):
        candidate = posixpath.normpath(target.lstrip("/"))
    else:
        source_directory = posixpath.dirname(source_part)
        candidate = posixpath.normpath(posixpath.join(source_directory, target))
    if candidate in {"", ".", ".."} or candidate.startswith("../"):
        raise PackageValidationError(
            f"relationship target escapes the DOCX package: {source_part!r} -> {target!r}"
        )
    return candidate


def _read_relationships(parts: Mapping[str, bytes]) -> tuple[RelationshipFact, ...]:
    facts: list[RelationshipFact] = []
    for rels_part in sorted(name for name in parts if name.endswith(".rels")):
        source_part = _source_part_for_rels(rels_part)
        try:
            root = ElementTree.fromstring(parts[rels_part])
        except ElementTree.ParseError as error:
            raise PackageValidationError(f"invalid XML in {rels_part}: {error}") from error
        for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
            relationship_id = relationship.get("Id")
            relationship_type = relationship.get("Type")
            target = relationship.get("Target")
            if not relationship_id or not relationship_type or target is None:
                raise PackageValidationError(f"incomplete relationship in {rels_part}")
            target_mode = relationship.get("TargetMode", "Internal")
            resolved_target = None
            target_exists = None
            if target_mode != "External":
                resolved_target = _resolve_target(source_part, target)
                target_exists = resolved_target in parts
            facts.append(
                RelationshipFact(
                    source_part=source_part,
                    relationship_id=relationship_id,
                    relationship_type=relationship_type,
                    target=target,
                    target_mode=target_mode,
                    resolved_target=resolved_target,
                    target_exists=target_exists,
                )
            )
    return tuple(facts)


def read_docx(path: Path) -> DocxPackage:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise PackageValidationError(f"DOCX file does not exist: {resolved}")
    try:
        with ZipFile(resolved) as archive:
            corrupt = archive.testzip()
            if corrupt is not None:
                raise PackageValidationError(f"corrupt DOCX ZIP entry: {corrupt}")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise PackageValidationError("DOCX contains duplicate ZIP part names")
            parts = {name: archive.read(name) for name in names if not name.endswith("/")}
    except BadZipFile as error:
        raise PackageValidationError(f"not a valid DOCX ZIP package: {error}") from error
    required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
    missing = sorted(required - parts.keys())
    if missing:
        raise PackageValidationError(f"DOCX missing required parts: {missing}")
    for part in required:
        if part.endswith((".xml", ".rels")):
            try:
                ElementTree.fromstring(parts[part])
            except ElementTree.ParseError as error:
                raise PackageValidationError(f"invalid XML in {part}: {error}") from error
    relationships = _read_relationships(parts)
    office_document = next(
        (
            relationship
            for relationship in relationships
            if relationship.source_part == ""
            and relationship.relationship_type == f"{OFFICE_REL_PREFIX}officeDocument"
        ),
        None,
    )
    if office_document is None or office_document.resolved_target != "word/document.xml":
        raise PackageValidationError("root relationships do not target word/document.xml")
    broken = [
        relationship
        for relationship in relationships
        if relationship.target_mode != "External" and relationship.target_exists is False
    ]
    if broken:
        details = ", ".join(
            f"{relationship.source_part}:{relationship.relationship_id}"
            for relationship in broken
        )
        raise PackageValidationError(f"broken internal relationships: {details}")
    return DocxPackage(
        path=resolved,
        document_sha256=sha256_file(resolved),
        parts=MappingProxyType(parts),
        relationships=relationships,
    )

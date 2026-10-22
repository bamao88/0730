"""Readable facts from the bound Word source, without choosing school semantics."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.template.source_entries import CanonicalSourceInventory
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.word_parts import read_word_stories, resolve_story_locator
from docfit.tools.word_xml import W_NS

W = f"{{{W_NS}}}"
WORD_FORMAT_EVIDENCE_VERSION = "docfit-source-word-format/v1"


def require_word_format_evidence(packet: JsonObject) -> None:
    if packet.get("word_format_evidence_version") != WORD_FORMAT_EVIDENCE_VERSION:
        raise ToolFailure(
            status="error",
            origin="harness",
            code="source_word_format_evidence_missing",
            message="The saved semantic context predates required source Word format evidence.",
            suggested_actions=(
                "Preserve this task's history and start fresh post-unit preparation.",
            ),
        )


def _val(parent: ET.Element | None, name: str) -> str | None:
    item = parent.find(W + name) if parent is not None else None
    return item.get(W + "val") if item is not None else None


def _style_chain(styles: dict[str, ET.Element], style_id: str | None) -> list[ET.Element]:
    chain: list[ET.Element] = []
    seen: set[str] = set()
    while style_id and style_id not in seen and style_id in styles:
        seen.add(style_id)
        style = styles[style_id]
        chain.append(style)
        style_id = _val(style, "basedOn")
    return chain


def _numbering_formats(archive: zipfile.ZipFile) -> dict[tuple[str, int], str]:
    if "word/numbering.xml" not in archive.namelist():
        return {}
    root = ET.fromstring(archive.read("word/numbering.xml"))
    abstracts = {item.get(W + "abstractNumId"): item for item in root.findall(W + "abstractNum")}
    formats: dict[tuple[str, int], str] = {}
    for num in root.findall(W + "num"):
        num_id = num.get(W + "numId")
        abstract = abstracts.get(_val(num, "abstractNumId"))
        if num_id is None or abstract is None:
            continue
        for level in abstract.findall(W + "lvl"):
            raw_level = level.get(W + "ilvl")
            fmt = _val(level, "numFmt")
            if raw_level is not None and raw_level.isdigit() and fmt:
                formats[(num_id, int(raw_level))] = fmt
        for override in num.findall(W + "lvlOverride"):
            raw_level = override.get(W + "ilvl")
            override_level = override.find(W + "lvl")
            fmt = _val(override_level, "numFmt")
            if raw_level is not None and raw_level.isdigit() and fmt:
                formats[(num_id, int(raw_level))] = fmt
    return formats


def _paragraph_format(
    paragraph: ET.Element,
    styles: dict[str, ET.Element],
    numbering_formats: dict[tuple[str, int], str],
) -> JsonObject:
    properties = paragraph.find(W + "pPr")
    style_id = _val(properties, "pStyle")
    chain = _style_chain(styles, style_id)
    facts: JsonObject = {}
    if style_id:
        style_name = _val(chain[0], "name") if chain else None
        facts["paragraph_style"] = style_name or style_id

    outline = _val(properties, "outlineLvl")
    if outline is None:
        outline = next(
            (
                _val(style.find(W + "pPr"), "outlineLvl")
                for style in chain
                if _val(style.find(W + "pPr"), "outlineLvl") is not None
            ),
            None,
        )
    if outline is not None and outline.isdigit() and int(outline) < 9:
        facts["outline_level"] = int(outline) + 1  # Word uses zero-based levels.

    num_id: str | None = None
    level: str | None = None
    for num_properties in [properties, *(style.find(W + "pPr") for style in chain)]:
        num = num_properties.find(W + "numPr") if num_properties is not None else None
        if num is None:
            continue
        num_id = num_id or _val(num, "numId")
        level = level or _val(num, "ilvl")
    if num_id and num_id != "0":
        index = int(level) if level is not None and level.isdigit() else 0
        facts["list_level"] = index + 1
        fmt = numbering_formats.get((num_id, index))
        if fmt:
            facts["numbering_format"] = fmt
    return facts


def source_word_format_facts(
    source_docx: Path,
    inventory: CanonicalSourceInventory,
) -> dict[str, JsonObject]:
    """Resolve original story, paragraph style, outline and list facts by provenance."""
    if sha256_file(source_docx) != inventory.source_snapshot_sha256:
        raise ToolFailure(
            status="error",
            origin="harness",
            code="source_word_format_snapshot_mismatch",
            message="Word format evidence does not belong to the bound source document.",
        )
    try:
        with zipfile.ZipFile(source_docx) as archive:
            stories = read_word_stories(archive)
            style_root = (
                ET.fromstring(archive.read("word/styles.xml"))
                if "word/styles.xml" in archive.namelist()
                else None
            )
            styles = (
                {
                    style_id: style
                    for style in style_root.findall(W + "style")
                    if (style_id := style.get(W + "styleId")) is not None
                }
                if style_root is not None
                else {}
            )
            numbering_formats = _numbering_formats(archive)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="error",
            origin="tool",
            code="source_word_format_document_unreadable",
            message="The bound Word package cannot provide format evidence.",
        ) from error
    parents = {
        id(child): parent
        for story in stories.values()
        for parent in story.root.iter()
        for child in parent
    }
    cache: dict[str, JsonObject] = {}
    result: dict[str, JsonObject] = {}
    for entry in inventory.source_entries:
        values: dict[str, list[object]] = {}
        for provenance in entry.provenance:
            locator = provenance.locator
            if locator not in cache:
                resolved = resolve_story_locator(stories, locator)
                if resolved is None:
                    cache[locator] = {"source_format_unavailable": True}
                else:
                    _, node = resolved
                    story_kind = locator.lstrip("/").split("[", 1)[0].split("/", 1)[0]
                    facts: JsonObject = {"story": story_kind}
                    while node.tag != W + "p" and id(node) in parents:
                        node = parents[id(node)]
                    if node.tag == W + "p":
                        facts.update(_paragraph_format(node, styles, numbering_formats))
                    cache[locator] = facts
            for key, value in cache[locator].items():
                values.setdefault(key, [])
                if value not in values[key]:
                    values[key].append(value)
        if values:
            result[entry.source_entry_id] = {
                key: items[0] if len(items) == 1 else items for key, items in values.items()
            }
    return result


def visible_word_format_facts(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    allowed = {
        "story": str,
        "paragraph_style": str,
        "outline_level": int,
        "list_level": int,
        "numbering_format": str,
        "source_format_unavailable": bool,
    }
    result: JsonObject = {}
    for key, kind in allowed.items():
        item = value.get(key)
        if type(item) is kind or (
            isinstance(item, list) and item and all(type(v) is kind for v in item)
        ):
            result[key] = item
    return result or None

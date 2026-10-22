"""Word story package mapping for exact OfficeCLI object locators."""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from docfit.tools.runtime import ToolFailure
from docfit.tools.word_xml import resolve_word_locator


@dataclass(frozen=True)
class WordStory:
    part_name: str
    root: ET.Element
    locator_root: ET.Element | None = None


def read_word_stories(archive: zipfile.ZipFile) -> dict[str, WordStory]:
    """Preserve relationship order: header[N] is not the headerN.xml filename."""
    stories = {
        "body": WordStory("word/document.xml", ET.fromstring(archive.read("word/document.xml")))
    }
    relationships = "word/_rels/document.xml.rels"
    if relationships not in archive.namelist():
        return stories
    counts = {"header": 0, "footer": 0}
    roots: dict[str, ET.Element] = {}
    for relationship in ET.fromstring(archive.read(relationships)):
        kind = relationship.get("Type", "").rsplit("/", 1)[-1]
        if kind not in {*counts, "footnotes", "endnotes", "comments"}:
            continue
        if relationship.get("TargetMode") == "External":
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="word_story_part_invalid",
                message="Word stories must be internal package parts.",
            )
        target = unquote(relationship.get("Target", ""))
        part_name = posixpath.normpath(posixpath.join("word", target)).lstrip("/")
        if part_name not in archive.namelist() or not part_name.startswith("word/"):
            raise ToolFailure(
                status="needs_input",
                origin="document",
                code="word_story_part_missing",
                message="Word story relationship is unresolved.",
            )
        if part_name not in roots:
            roots[part_name] = ET.fromstring(archive.read(part_name))
        if kind in counts:
            counts[kind] += 1
            stories[f"{kind}[{counts[kind]}]"] = WordStory(part_name, roots[part_name])
        else:
            # OfficeCLI inspection uses the element sequence, including separator notes.
            note_kind = kind[:-1]
            notes = [node for node in roots[part_name] if node.tag.rsplit("}", 1)[-1] == note_kind]
            for index, note in enumerate(notes, 1):
                stories[f"{note_kind}[{index}]"] = WordStory(part_name, roots[part_name], note)
    return stories


def resolve_story_locator(
    stories: dict[str, WordStory],
    locator: str,
) -> tuple[WordStory, ET.Element] | None:
    segments = locator.lstrip("/").split("/", 1)
    story = stories.get(segments[0])
    if story is None:
        return None
    local_locator = (
        locator if segments[0] == "body" else (segments[1] if len(segments) == 2 else "")
    )
    scope = story.root if story.locator_root is None else story.locator_root
    target = resolve_word_locator(scope, local_locator) if local_locator else scope
    return (story, target) if target is not None else None

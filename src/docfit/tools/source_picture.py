"""Pixels for a canonical picture entry in the immutable school Word input."""

from __future__ import annotations

import io
import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps, UnidentifiedImageError

from docfit.template.source_entries import CanonicalSourceEntry
from docfit.tools.runtime import ToolFailure
from docfit.tools.word_parts import read_word_stories, resolve_story_locator
from docfit.tools.word_xml import W_NS

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_W = f"{{{W_NS}}}"
_MAX_PIXELS = 30_000_000


def _unavailable() -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="document",
        code="source_picture_evidence_unavailable",
        message="The school Word picture cannot be shown from this source entry.",
        suggested_actions=(
            "Return needs_input for this picture; readable visual evidence is required.",
        ),
    )


def _relationship_part(part_name: str) -> str:
    directory, basename = posixpath.split(part_name)
    return posixpath.join(directory, "_rels", basename + ".rels")


def _embedded_image(archive: zipfile.ZipFile, entry: CanonicalSourceEntry) -> bytes:
    if entry.entry_type != "picture" or len(entry.provenance) != 1:
        raise _unavailable()
    stories = read_word_stories(archive)
    resolved = resolve_story_locator(stories, entry.provenance[0].locator)
    if resolved is None:
        raise _unavailable()
    story, node = resolved
    drawings = [node] if node.tag == _W + "drawing" else node.findall(_W + "drawing")
    if len(drawings) != 1:
        raise _unavailable()
    blips = drawings[0].findall(".//" + _A + "blip")
    if len(blips) != 1:
        raise _unavailable()
    relation_id = blips[0].get(_R + "embed")
    if not relation_id or blips[0].get(_R + "link"):
        raise _unavailable()
    relationships = _relationship_part(story.part_name)
    if relationships not in archive.namelist():
        raise _unavailable()
    matches = [
        relation
        for relation in ET.fromstring(archive.read(relationships)).findall(_REL + "Relationship")
        if relation.get("Id") == relation_id
    ]
    if len(matches) != 1 or matches[0].get("TargetMode") == "External":
        raise _unavailable()
    relation = matches[0]
    if not relation.get("Type", "").endswith("/image"):
        raise _unavailable()
    target = unquote(relation.get("Target", ""))
    relative_target = (
        target.lstrip("/")
        if target.startswith("/")
        else posixpath.join(posixpath.dirname(story.part_name), target)
    )
    image_part = posixpath.normpath(relative_target)
    if not image_part.startswith("word/") or image_part not in archive.namelist():
        raise _unavailable()
    return archive.read(image_part)


def source_picture_png(source: Path, entry: CanonicalSourceEntry) -> bytes:
    """Resolve the entry's one direct embedded drawing without searching by text."""
    try:
        with zipfile.ZipFile(source) as archive:
            raw = _embedded_image(archive, entry)
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width * opened.height > _MAX_PIXELS:
                raise _unavailable()
            picture = ImageOps.exif_transpose(opened)
            picture.load()
            has_alpha = "A" in picture.getbands() or "transparency" in picture.info
            converted = picture.convert("RGBA" if has_alpha else "RGB")
            output = io.BytesIO()
            converted.save(output, format="PNG")
            return output.getvalue()
    except ToolFailure:
        raise
    except (
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        ET.ParseError,
        UnidentifiedImageError,
    ) as error:
        raise _unavailable() from error

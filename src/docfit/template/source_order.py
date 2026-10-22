"""Order inspected facts before canonical identities are created."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.word_parts import read_word_stories, resolve_story_locator

SOURCE_ORDER_VERSION = "docfit-word-story-order/v1"


def order_initial_source_objects(
    source: Path, *, source_sha256: str, objects: list[JsonObject],
) -> list[JsonObject]:
    """Use actual XML positions; preserve every supplied fact and all object identities.

    Body objects follow physical preorder, including containers before children.
    Other Word stories follow package relationship order. No text/label sorting,
    semantic grouping, or rewriting of an already frozen canonical inventory.
    """
    if sha256_file(source) != source_sha256:
        raise ToolFailure(
            status="error", origin="harness", code="source_order_snapshot_mismatch",
            message="Source ordering is not bound to the immutable Word input.",
        )
    try:
        with zipfile.ZipFile(source) as archive:
            stories = read_word_stories(archive)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="error", origin="tool", code="source_order_document_unreadable",
            message="The bound Word package cannot provide source ordering.",
        ) from error
    positions = {
        (key, id(node)): (story_index, node_index)
        for story_index, (key, story) in enumerate(stories.items())
        for node_index, node in enumerate(
            (story.root if story.locator_root is None else story.locator_root).iter()
        )
    }
    cache: dict[str, tuple[int, int]] = {}
    ordered = []
    for index, item in enumerate(objects):
        locator = item.get("locator") if isinstance(item, dict) else None
        if not isinstance(locator, str) or not locator:
            raise ToolFailure(
                status="error", origin="tool", code="source_order_object_unresolved",
                message="An inspected object has no resolvable source position.",
            )
        if locator not in cache:
            resolved = resolve_story_locator(stories, locator)
            key = locator.lstrip("/").split("/", 1)[0]
            position = positions.get((key, id(resolved[1]))) if resolved is not None else None
            if position is None:
                raise ToolFailure(
                    status="error", origin="tool", code="source_order_object_unresolved",
                    message=f"An inspected object cannot be ordered at {locator}.",
                )
            cache[locator] = position
        ordered.append((cache[locator], index, item))
    return [item for _, _, item in sorted(ordered, key=lambda row: (row[0], row[1]))]

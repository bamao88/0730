"""Project physical containment as reading context, never as semantic scope."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.template.source_entries import CanonicalSourceInventory
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.word_parts import read_word_stories, resolve_story_locator

STRUCTURE_EVIDENCE_VERSION = "docfit-source-structure/v1"
_READING_NOTE = (
    "These are physical containment relationships between source entries. "
    "This entry's own text is separate from descendant text; empty own text does not "
    "imply an empty container. Related entries are context only, not additional text "
    "to submit for this entry or permission to revise those entries. "
    "Containment alone does not determine a role or field."
)


def require_structure_evidence(packet: JsonObject) -> None:
    if packet.get("structure_evidence_version") != STRUCTURE_EVIDENCE_VERSION:
        raise ToolFailure(
            status="error",
            origin="harness",
            code="source_structure_evidence_missing",
            message="The saved semantic context predates required containment evidence.",
            suggested_actions=(
                "Preserve this task's history and start fresh post-unit preparation.",
            ),
        )


def source_structure_context(
    source: Path,
    inventory: CanonicalSourceInventory,
) -> dict[str, JsonObject]:
    """Resolve actual XML ancestry; do not infer relations from labels or ID order.

    Every provenance node of a descendant must lie strictly within the ancestor's
    represented XML nodes. Shared carriers and unresolved nodes are not containment.
    Related text stays separate from canonical text and from editable judgment scope.
    """
    if sha256_file(source) != inventory.source_snapshot_sha256:
        raise ToolFailure(
            status="error",
            origin="harness",
            code="source_structure_snapshot_mismatch",
            message="Containment evidence does not belong to the bound source Word input.",
        )
    try:
        with zipfile.ZipFile(source) as archive:
            stories = read_word_stories(archive)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="error",
            origin="tool",
            code="source_structure_document_unreadable",
            message="The bound Word package cannot provide containment evidence.",
        ) from error
    parents = {
        id(child): id(parent)
        for story in stories.values()
        for parent in story.root.iter()
        for child in parent
    }
    ancestry: dict[int, set[int]] = {}
    nodes: dict[str, set[int]] = {}
    unavailable: set[str] = set()
    for entry in inventory.source_entries:
        ids = set()
        for provenance in entry.provenance:
            resolved = resolve_story_locator(stories, provenance.locator)
            if resolved is None:
                unavailable.add(entry.source_entry_id)
                continue
            node_id = id(resolved[1])
            ids.add(node_id)
            if node_id not in ancestry:
                ancestors = set()
                current = node_id
                while current in parents:
                    current = parents[current]
                    ancestors.add(current)
                ancestry[node_id] = ancestors
        nodes[entry.source_entry_id] = ids
    entries = {entry.source_entry_id: entry for entry in inventory.source_entries}
    ancestors_by_entry: dict[str, list[str]] = {key: [] for key in entries}
    descendants_by_entry: dict[str, list[str]] = {key: [] for key in entries}
    for child_id, child_nodes in nodes.items():
        if child_id in unavailable or not child_nodes:
            continue
        for parent_id, parent_nodes in nodes.items():
            if parent_id == child_id or parent_id in unavailable or not parent_nodes:
                continue
            if all(ancestry[node] & parent_nodes for node in child_nodes):
                ancestors_by_entry[child_id].append(parent_id)
                descendants_by_entry[parent_id].append(child_id)

    def rows(keys: list[str]) -> list[JsonObject]:
        return [
            {
                "source_entry_id": key,
                "entry_type": entries[key].entry_type,
                "text": entries[key].text,
            }
            for key in keys
        ]

    result: dict[str, JsonObject] = {}
    for key in entries:
        if key in unavailable:
            result[key] = {
                "reading_note": "Physical containment evidence is unavailable for this entry."
            }
        elif ancestors_by_entry[key] or descendants_by_entry[key]:
            result[key] = {
                "reading_note": _READING_NOTE,
                "ancestor_entries": rows(ancestors_by_entry[key]),
                "descendant_entries": rows(descendants_by_entry[key]),
            }
    return result


def visible_structure_context(value: object) -> JsonObject | None:
    """Keep exact text and source IDs while excluding execution references."""
    if not isinstance(value, dict) or not isinstance(value.get("reading_note"), str):
        return None
    result: JsonObject = {"reading_note": value["reading_note"]}
    for relation in ("ancestor_entries", "descendant_entries"):
        if isinstance(value.get(relation), list):
            result[relation] = [
                {key: item[key] for key in ("source_entry_id", "entry_type", "text")}
                for item in value[relation]
                if isinstance(item, dict)
                and all(
                    isinstance(item.get(key), str)
                    for key in ("source_entry_id", "entry_type", "text")
                )
            ]
    return result

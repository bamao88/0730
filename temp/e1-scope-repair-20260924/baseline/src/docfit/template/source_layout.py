"""Read-only Word layout facts attached to existing source identities."""

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.template.source_entries import CanonicalSourceInventory
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.word_parts import read_word_stories, resolve_story_locator
from docfit.tools.word_xml import MC_NS, W_NS, visible_word_text

W = f"{{{W_NS}}}"
LAYOUT_EVIDENCE_VERSION = "docfit-source-layout/v1"
_UNAVAILABLE = "Layout evidence is unavailable for part of this entry."


def require_layout_evidence(packet: JsonObject) -> None:
    if packet.get("layout_evidence_version") != LAYOUT_EVIDENCE_VERSION:
        raise ToolFailure(
            status="error",
            origin="harness",
            code="source_layout_evidence_missing",
            message="The saved semantic context predates required source layout evidence.",
            suggested_actions=(
                "Preserve this task's history and start fresh post-unit preparation.",
            ),
        )


def _paragraph_facts(paragraph: ET.Element) -> list[str]:
    facts: list[str] = []
    properties = paragraph.find(W + "pPr")
    if properties is not None:
        if properties.find(W + "sectPr") is not None:
            facts.append("The containing paragraph carries section boundary settings.")
        before = properties.find(W + "pageBreakBefore")
        if before is not None and before.get(W + "val", "true") not in {"0", "false", "off"}:
            facts.append("Paragraph formatting explicitly requests a page break before it.")

    def visit(node: ET.Element) -> None:
        if node is not paragraph and node.tag == W + "p":
            return  # A text box's paragraph is not its containing anchor paragraph.
        if node.tag == f"{{{MC_NS}}}AlternateContent":
            if any(n.tag in {W + "br", W + "cr"} for n in node.iter()):
                facts.append("Alternative document representations contain breaks; inspect pages.")
            return  # Do not claim every alternative is simultaneously visible.
        if node.tag in {W + "br", W + "cr"}:
            kind = node.get(W + "type", "textWrapping")
            label = {"page": "page", "column": "column", "textWrapping": "line"}.get(kind)
            facts.append(
                f"The containing paragraph includes an explicit {label} break."
                if label
                else "The containing paragraph includes an unrecognized break type."
            )
        for child in node:
            visit(child)

    visit(paragraph)
    if facts and not visible_word_text(paragraph):
        facts.append("The containing paragraph has no visible text.")
    return list(dict.fromkeys(facts))


def source_layout_facts(
    source_docx: Path,
    inventory: CanonicalSourceInventory,
) -> dict[str, list[str]]:
    """Project physical facts without changing text, identities, or choosing roles.

    The source hash binds this supplemental evidence to the same immutable Word
    input. Canonical identity and accepted partitions are deliberately untouched.
    Resolve existing provenance, never search by wording or create new objects.
    """
    if sha256_file(source_docx) != inventory.source_snapshot_sha256:
        raise ToolFailure(
            status="error",
            origin="harness",
            code="source_layout_snapshot_mismatch",
            message="Layout evidence does not belong to the bound source document.",
        )
    try:
        with zipfile.ZipFile(source_docx) as archive:
            stories = read_word_stories(archive)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="error",
            origin="tool",
            code="source_layout_document_unreadable",
            message="The bound source Word package cannot provide layout evidence.",
        ) from error
    parents = {
        id(child): parent
        for story in stories.values()
        for parent in story.root.iter()
        for child in parent
    }
    paragraph_cache: dict[int, list[str]] = {}
    locator_cache: dict[str, list[str]] = {}
    result: dict[str, list[str]] = {}
    for entry in inventory.source_entries:
        facts = []
        for provenance in entry.provenance:
            locator = provenance.locator
            if locator not in locator_cache:
                resolved = resolve_story_locator(stories, locator)
                if resolved is None:
                    locator_cache[locator] = [_UNAVAILABLE]
                else:
                    _, node = resolved
                    while node.tag != W + "p" and id(node) in parents:
                        node = parents[id(node)]
                    if node.tag == W + "p":
                        if id(node) not in paragraph_cache:
                            paragraph_cache[id(node)] = _paragraph_facts(node)
                        locator_cache[locator] = paragraph_cache[id(node)]
                    else:
                        locator_cache[locator] = []
            facts.extend(locator_cache[locator])
        if facts:
            result[entry.source_entry_id] = list(dict.fromkeys(facts))
    return result

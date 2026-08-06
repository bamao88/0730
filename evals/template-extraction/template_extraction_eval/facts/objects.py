"""Extract images, formulas, fields, bookmarks, table merges, and unsupported objects."""

from __future__ import annotations

import hashlib
from xml.etree import ElementTree

from ..models import AssertionStatus, ObjectFact
from .reader import DocxPackage, StoryPart

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
M = f"{{{M_NS}}}"
A = f"{{{A_NS}}}"
WP = f"{{{WP_NS}}}"


def _paragraph_context(
    node: ElementTree.Element,
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    paragraph_indices: dict[ElementTree.Element, tuple[str, int]],
) -> tuple[str, int | None]:
    current = node
    while current in parent_map:
        current = parent_map[current]
        if current.tag == f"{W}p":
            return paragraph_indices[current]
    return story_part.story, None


def _paragraph_indices(
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
) -> dict[ElementTree.Element, tuple[str, int]]:
    counters: dict[str, int] = {}
    result: dict[ElementTree.Element, tuple[str, int]] = {}
    for paragraph in story_part.root.iter(f"{W}p"):
        current = paragraph
        in_textbox = False
        while current in parent_map:
            current = parent_map[current]
            if current.tag == f"{W}txbxContent":
                in_textbox = True
                break
        story = "textbox" if in_textbox else story_part.story
        index = counters.get(story, 0)
        counters[story] = index + 1
        result[paragraph] = (story, index)
    return result


def _xml(element: ElementTree.Element) -> str:
    return ElementTree.tostring(element, encoding="unicode", short_empty_elements=True)


def _image_facts(
    package: DocxPackage,
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    paragraph_indices: dict[ElementTree.Element, tuple[str, int]],
) -> list[ObjectFact]:
    result: list[ObjectFact] = []
    for blip in story_part.root.iter(f"{A}blip"):
        relationship_id = blip.get(f"{R}embed") or blip.get(f"{R}link")
        story, paragraph_index = _paragraph_context(
            blip, story_part, parent_map, paragraph_indices
        )
        relationship = (
            None
            if relationship_id is None
            else package.relationship(story_part.part, relationship_id)
        )
        target = None if relationship is None else relationship.resolved_target
        content_sha256 = None
        status = AssertionStatus.PASS
        detail = None
        if relationship_id is None:
            status = AssertionStatus.FAIL
            detail = "image has no relationship ID"
        elif relationship is None:
            status = AssertionStatus.FAIL
            detail = "image relationship is missing"
        elif target is None or target not in package.parts:
            status = AssertionStatus.FAIL
            detail = "image target is missing"
        else:
            content_sha256 = hashlib.sha256(package.parts[target]).hexdigest()
        width = None
        height = None
        paragraph = blip
        while paragraph in parent_map and paragraph.tag != f"{W}p":
            paragraph = parent_map[paragraph]
        if paragraph.tag == f"{W}p":
            extent = paragraph.find(f".//{WP}extent")
            if extent is not None:
                cx = extent.get("cx")
                cy = extent.get("cy")
                width = None if cx is None else int(cx)
                height = None if cy is None else int(cy)
        result.append(
            ObjectFact(
                kind="image",
                story=story,
                part=story_part.part,
                paragraph_index=paragraph_index,
                relationship_id=relationship_id,
                target=target,
                content_sha256=content_sha256,
                width_emu=width,
                height_emu=height,
                status=status,
                detail=detail,
            )
        )
    return result


def _formula_facts(
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    paragraph_indices: dict[ElementTree.Element, tuple[str, int]],
) -> list[ObjectFact]:
    result = []
    for formula in story_part.root.iter(f"{M}oMath"):
        story, paragraph_index = _paragraph_context(
            formula, story_part, parent_map, paragraph_indices
        )
        result.append(
            ObjectFact(
                kind="formula",
                story=story,
                part=story_part.part,
                paragraph_index=paragraph_index,
                semantic_xml=_xml(formula),
            )
        )
    return result


def _field_facts(
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    paragraph_indices: dict[ElementTree.Element, tuple[str, int]],
) -> list[ObjectFact]:
    result = []
    for field in story_part.root.iter(f"{W}fldSimple"):
        story, paragraph_index = _paragraph_context(
            field, story_part, parent_map, paragraph_indices
        )
        result.append(
            ObjectFact(
                kind="field",
                story=story,
                part=story_part.part,
                paragraph_index=paragraph_index,
                value=field.get(f"{W}instr"),
                semantic_xml=_xml(field),
            )
        )
    for field_character in story_part.root.iter(f"{W}fldChar"):
        story, paragraph_index = _paragraph_context(
            field_character, story_part, parent_map, paragraph_indices
        )
        result.append(
            ObjectFact(
                kind="field",
                story=story,
                part=story_part.part,
                paragraph_index=paragraph_index,
                value=field_character.get(f"{W}fldCharType"),
                semantic_xml=_xml(field_character),
            )
        )
    return result


def _bookmark_facts(
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    paragraph_indices: dict[ElementTree.Element, tuple[str, int]],
) -> list[ObjectFact]:
    end_ids = {
        bookmark.get(f"{W}id") for bookmark in story_part.root.iter(f"{W}bookmarkEnd")
    }
    result = []
    for bookmark in story_part.root.iter(f"{W}bookmarkStart"):
        story, paragraph_index = _paragraph_context(
            bookmark, story_part, parent_map, paragraph_indices
        )
        bookmark_id = bookmark.get(f"{W}id")
        complete = bookmark_id is not None and bookmark_id in end_ids
        result.append(
            ObjectFact(
                kind="bookmark",
                story=story,
                part=story_part.part,
                paragraph_index=paragraph_index,
                name=bookmark.get(f"{W}name"),
                value=bookmark_id,
                semantic_xml=_xml(bookmark),
                status=AssertionStatus.PASS if complete else AssertionStatus.FAIL,
                detail=None if complete else "bookmark end is missing",
            )
        )
    return result


def _merge_facts(
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    paragraph_indices: dict[ElementTree.Element, tuple[str, int]],
) -> list[ObjectFact]:
    result = []
    for cell in story_part.root.iter(f"{W}tc"):
        properties = cell.find(f"{W}tcPr")
        if properties is None:
            continue
        grid_span = properties.find(f"{W}gridSpan")
        vertical_merge = properties.find(f"{W}vMerge")
        if grid_span is None and vertical_merge is None:
            continue
        story, paragraph_index = _paragraph_context(cell, story_part, parent_map, paragraph_indices)
        value = None
        if grid_span is not None:
            value = f"gridSpan:{grid_span.get(f'{W}val', '1')}"
        if vertical_merge is not None:
            vertical = vertical_merge.get(f"{W}val", "continue")
            value = f"{value + ';' if value else ''}vMerge:{vertical}"
        result.append(
            ObjectFact(
                kind="table_merge",
                story=story,
                part=story_part.part,
                paragraph_index=paragraph_index,
                value=value,
                semantic_xml=_xml(properties),
            )
        )
    return result


def _unsupported_facts(
    story_part: StoryPart,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    paragraph_indices: dict[ElementTree.Element, tuple[str, int]],
) -> list[ObjectFact]:
    result = []
    for alt_chunk in story_part.root.iter(f"{W}altChunk"):
        story, paragraph_index = _paragraph_context(
            alt_chunk, story_part, parent_map, paragraph_indices
        )
        relationship_id = alt_chunk.get(f"{R}id")
        result.append(
            ObjectFact(
                kind="unsupported",
                story=story,
                part=story_part.part,
                paragraph_index=paragraph_index,
                relationship_id=relationship_id,
                status=AssertionStatus.UNKNOWN,
                detail="altChunk is visible but semantic comparison is unsupported in v1",
            )
        )
    return result


def analyze_objects(
    package: DocxPackage,
) -> tuple[tuple[ObjectFact, ...], tuple[ObjectFact, ...]]:
    objects: list[ObjectFact] = []
    unsupported: list[ObjectFact] = []
    for story_part in package.story_parts():
        parent_map = {child: parent for parent in story_part.root.iter() for child in parent}
        paragraph_indices = _paragraph_indices(story_part, parent_map)
        objects.extend(_image_facts(package, story_part, parent_map, paragraph_indices))
        objects.extend(_formula_facts(story_part, parent_map, paragraph_indices))
        objects.extend(_field_facts(story_part, parent_map, paragraph_indices))
        objects.extend(_bookmark_facts(story_part, parent_map, paragraph_indices))
        objects.extend(_merge_facts(story_part, parent_map, paragraph_indices))
        unsupported.extend(_unsupported_facts(story_part, parent_map, paragraph_indices))
    return tuple(objects), tuple(unsupported)


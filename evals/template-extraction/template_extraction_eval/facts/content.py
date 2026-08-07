"""Extract loss-aware text, whitespace, non-text tokens, and content controls."""

from __future__ import annotations

from collections.abc import Iterator
from xml.etree import ElementTree

from ..models import ContentControlFact, ParagraphFact, RunFact
from .effective_style import EffectiveStyleAnalyzer
from .reader import DocxPackage, StoryPart

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = f"{{{W_NS}}}"
M = f"{{{M_NS}}}"


def _attribute(element: ElementTree.Element | None, name: str) -> str | None:
    if element is None:
        return None
    return element.get(f"{W}{name}")


def _node_text(element: ElementTree.Element) -> str:
    if element.tag in {f"{W}t", f"{W}instrText", f"{W}delText", f"{M}t"}:
        return element.text or ""
    if element.tag == f"{W}tab":
        return "\t"
    if element.tag in {f"{W}br", f"{W}cr"}:
        return "\n"
    return ""


def element_text(element: ElementTree.Element) -> str:
    return "".join(_node_text(node) for node in element.iter())


def _tokens(paragraph: ElementTree.Element) -> tuple[str, ...]:
    tokens: list[str] = []
    seen_nodes: set[int] = set()
    for node in paragraph.iter():
        text = _node_text(node)
        if text:
            tokens.append(f"TEXT:{text}")
        if node.tag in {f"{W}drawing", f"{W}pict"} and id(node) not in seen_nodes:
            tokens.append("OBJECT:image")
            seen_nodes.add(id(node))
        elif node.tag == f"{M}oMath" and id(node) not in seen_nodes:
            tokens.append("OBJECT:formula")
            seen_nodes.add(id(node))
        elif node.tag in {f"{W}fldSimple", f"{W}fldChar"} and id(node) not in seen_nodes:
            tokens.append("OBJECT:field")
            seen_nodes.add(id(node))
        elif node.tag in {f"{W}bookmarkStart", f"{W}bookmarkEnd"} and id(node) not in seen_nodes:
            tokens.append("OBJECT:bookmark")
            seen_nodes.add(id(node))
    return tuple(tokens)


def _text_before(root: ElementTree.Element, target: ElementTree.Element) -> str:
    values: list[str] = []
    found = False

    def visit(node: ElementTree.Element) -> None:
        nonlocal found
        if found:
            return
        if node is target:
            found = True
            return
        values.append(_node_text(node))
        for child in node:
            visit(child)

    visit(root)
    return "".join(values)


def _ancestors(
    element: ElementTree.Element,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
) -> Iterator[ElementTree.Element]:
    current = parent_map.get(element)
    while current is not None:
        yield current
        current = parent_map.get(current)


def _container_coordinates(
    paragraph: ElementTree.Element,
    parent_map: dict[ElementTree.Element, ElementTree.Element],
    table_indices: dict[ElementTree.Element, int],
    row_indices: dict[ElementTree.Element, int],
    cell_indices: dict[ElementTree.Element, int],
) -> tuple[int | None, int | None, int | None, ElementTree.Element | None, bool]:
    table = None
    row = None
    cell = None
    in_textbox = False
    for ancestor in _ancestors(paragraph, parent_map):
        if ancestor.tag == f"{W}txbxContent":
            in_textbox = True
        elif cell is None and ancestor.tag == f"{W}tc":
            cell = ancestor
        elif row is None and ancestor.tag == f"{W}tr":
            row = ancestor
        elif table is None and ancestor.tag == f"{W}tbl":
            table = ancestor
    return (
        None if table is None else table_indices[table],
        None if row is None else row_indices[row],
        None if cell is None else cell_indices[cell],
        cell,
        in_textbox,
    )


def _index_tables(
    root: ElementTree.Element,
) -> tuple[
    dict[ElementTree.Element, int],
    dict[ElementTree.Element, int],
    dict[ElementTree.Element, int],
]:
    table_indices: dict[ElementTree.Element, int] = {}
    row_indices: dict[ElementTree.Element, int] = {}
    cell_indices: dict[ElementTree.Element, int] = {}
    for table_index, table in enumerate(root.iter(f"{W}tbl")):
        table_indices[table] = table_index
        for row_index, row in enumerate(table.findall(f"{W}tr")):
            row_indices[row] = row_index
            for cell_index, cell in enumerate(row.findall(f"{W}tc")):
                cell_indices[cell] = cell_index
    return table_indices, row_indices, cell_indices


def analyze_content(
    package: DocxPackage,
    style_analyzer: EffectiveStyleAnalyzer,
) -> tuple[tuple[ParagraphFact, ...], tuple[ContentControlFact, ...]]:
    paragraphs: list[ParagraphFact] = []
    controls: list[ContentControlFact] = []
    story_counters: dict[tuple[str, str], int] = {}
    for story_part in package.story_parts():
        part_paragraphs, part_controls = _analyze_story(story_part, style_analyzer, story_counters)
        paragraphs.extend(part_paragraphs)
        controls.extend(part_controls)
    return tuple(paragraphs), tuple(controls)


def _analyze_story(
    story_part: StoryPart,
    style_analyzer: EffectiveStyleAnalyzer,
    story_counters: dict[tuple[str, str], int],
) -> tuple[list[ParagraphFact], list[ContentControlFact]]:
    root = story_part.root
    parent_map = {child: parent for parent in root.iter() for child in parent}
    table_indices, row_indices, cell_indices = _index_tables(root)
    paragraphs: list[ParagraphFact] = []
    controls: list[ContentControlFact] = []
    paragraph_contexts: dict[
        ElementTree.Element,
        tuple[ParagraphFact, ElementTree.Element | None],
    ] = {}
    section_index = 0
    for paragraph in root.iter(f"{W}p"):
        table_index, row, cell_index, cell, in_textbox = _container_coordinates(
            paragraph,
            parent_map,
            table_indices,
            row_indices,
            cell_indices,
        )
        story = "textbox" if in_textbox else story_part.story
        counter_key = (story, story_part.part)
        paragraph_index = story_counters.get(counter_key, 0)
        story_counters[counter_key] = paragraph_index + 1
        text = element_text(paragraph)
        runs: list[RunFact] = []
        cursor = 0
        for run in paragraph.iter(f"{W}r"):
            run_text = element_text(run)
            start = cursor
            cursor += len(run_text)
            style_id = _attribute(run.find(f"{W}rPr/{W}rStyle"), "val")
            runs.append(
                RunFact(
                    text=run_text,
                    start=start,
                    end=cursor,
                    style_id=style_id,
                    effective_style=style_analyzer.effective_style(paragraph, run, cell=cell),
                )
            )
        if not runs:
            runs.append(
                RunFact(
                    text="",
                    start=0,
                    end=0,
                    style_id=None,
                    effective_style=style_analyzer.effective_style(paragraph, cell=cell),
                )
            )
        path = f"{story_part.part}:{story}:p[{paragraph_index}]"
        if table_index is not None:
            path += f"/tbl[{table_index}]/tr[{row}]/tc[{cell_index}]"
        fact = ParagraphFact(
            story=story,
            part=story_part.part,
            paragraph_index=paragraph_index,
            section_index=section_index,
            path=path,
            text=text,
            tokens=_tokens(paragraph),
            runs=tuple(runs),
            table_index=table_index,
            row=row,
            cell=cell_index,
        )
        paragraphs.append(fact)
        paragraph_contexts[paragraph] = (fact, cell)
        paragraph_properties = paragraph.find(f"{W}pPr")
        if paragraph_properties is not None and paragraph_properties.find(f"{W}sectPr") is not None:
            section_index += 1

    for control in root.iter(f"{W}sdt"):
        ancestor_paragraph = next(
            (node for node in _ancestors(control, parent_map) if node.tag == f"{W}p"),
            None,
        )
        descendant_paragraphs = tuple(control.iter(f"{W}p"))
        control_paragraph = (
            ancestor_paragraph
            if ancestor_paragraph is not None
            else descendant_paragraphs[0]
            if descendant_paragraphs
            else None
        )
        if control_paragraph is None:
            continue
        paragraph_fact, cell = paragraph_contexts[control_paragraph]
        properties = control.find(f"{W}sdtPr")
        alias = _attribute(
            None if properties is None else properties.find(f"{W}alias"),
            "val",
        )
        tag = _attribute(
            None if properties is None else properties.find(f"{W}tag"),
            "val",
        )
        internal_id = _attribute(
            None if properties is None else properties.find(f"{W}id"),
            "val",
        )
        showing_placeholder = (
            properties is not None
            and properties.find(f"{W}showingPlcHdr") is not None
        )
        content = control.find(f"{W}sdtContent")
        control_text = element_text(control if content is None else content)
        covered_paragraphs = (
            (control_paragraph,)
            if ancestor_paragraph is not None
            else descendant_paragraphs
        )
        paragraph_indices = tuple(
            paragraph_contexts[item][0].paragraph_index
            for item in covered_paragraphs
            if item in paragraph_contexts
        )
        start = (
            0
            if ancestor_paragraph is None
            else len(_text_before(control_paragraph, control))
        )
        control_run = control.find(f".//{W}r")
        controls.append(
            ContentControlFact(
                alias=alias,
                tag=tag,
                internal_id=internal_id,
                story=paragraph_fact.story,
                part=paragraph_fact.part,
                paragraph_index=paragraph_fact.paragraph_index,
                start=start,
                end=start + len(control_text),
                text=control_text,
                effective_style=style_analyzer.effective_style(
                    control_paragraph,
                    control_run,
                    cell=cell,
                ),
                paragraph_indices=paragraph_indices,
                block_level=ancestor_paragraph is None,
                showing_placeholder=showing_placeholder,
            )
        )
    return paragraphs, controls

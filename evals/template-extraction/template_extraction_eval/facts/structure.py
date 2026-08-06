"""Extract table/container structure and apply stable structural locators."""

from __future__ import annotations

from xml.etree import ElementTree

from ..models import CellFact, Locator, ParagraphFact, TableFact
from .content import element_text
from .reader import DocxPackage

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _attribute(element: ElementTree.Element | None, name: str) -> str | None:
    if element is None:
        return None
    return element.get(f"{W}{name}")


def analyze_structure(package: DocxPackage) -> tuple[TableFact, ...]:
    tables: list[TableFact] = []
    table_counters: dict[tuple[str, str], int] = {}
    for story_part in package.story_parts():
        for table in story_part.root.iter(f"{W}tbl"):
            in_textbox = any(
                textbox_table is table
                for content in story_part.root.iter(f"{W}txbxContent")
                for textbox_table in content.iter(f"{W}tbl")
            )
            story = "textbox" if in_textbox else story_part.story
            counter_key = (story, story_part.part)
            table_index = table_counters.get(counter_key, 0)
            table_counters[counter_key] = table_index + 1
            cells: list[CellFact] = []
            rows = table.findall(f"{W}tr")
            for row_index, row in enumerate(rows):
                for cell_index, cell in enumerate(row.findall(f"{W}tc")):
                    properties = cell.find(f"{W}tcPr")
                    grid_span = _attribute(
                        None if properties is None else properties.find(f"{W}gridSpan"),
                        "val",
                    )
                    vertical_merge = _attribute(
                        None if properties is None else properties.find(f"{W}vMerge"),
                        "val",
                    )
                    if properties is not None and properties.find(f"{W}vMerge") is not None:
                        vertical_merge = vertical_merge or "continue"
                    cells.append(
                        CellFact(
                            row=row_index,
                            cell=cell_index,
                            text="\n".join(element_text(p) for p in cell.iter(f"{W}p")),
                            grid_span=1 if grid_span is None else int(grid_span),
                            vertical_merge=vertical_merge,
                        )
                    )
            tables.append(
                TableFact(
                    story=story,
                    part=story_part.part,
                    table_index=table_index,
                    row_count=len(rows),
                    cells=tuple(cells),
                )
            )
    return tuple(tables)


def locate_paragraphs(
    paragraphs: tuple[ParagraphFact, ...],
    locator: Locator,
) -> tuple[ParagraphFact, ...]:
    matches = [
        paragraph
        for paragraph in paragraphs
        if paragraph.story == locator.story and paragraph.part == locator.part
    ]
    if locator.section_index is not None:
        matches = [p for p in matches if p.section_index == locator.section_index]
    if locator.paragraph_index is not None:
        matches = [p for p in matches if p.paragraph_index == locator.paragraph_index]
    if locator.table_index is not None:
        matches = [p for p in matches if p.table_index == locator.table_index]
    if locator.row is not None:
        matches = [p for p in matches if p.row == locator.row]
    if locator.cell is not None:
        matches = [p for p in matches if p.cell == locator.cell]
    if locator.left_anchor is not None:
        matches = [p for p in matches if locator.left_anchor in p.text]
    if locator.right_anchor is not None:
        matches = [p for p in matches if locator.right_anchor in p.text]
    if locator.occurrence is not None:
        occurrence_index = locator.occurrence - 1
        if occurrence_index >= len(matches):
            return ()
        return (matches[occurrence_index],)
    return tuple(matches)


def table_signature(table: TableFact) -> tuple[tuple[int, int, int, str | None, str], ...]:
    return tuple(
        (cell.row, cell.cell, cell.grid_span, cell.vertical_merge, cell.text)
        for cell in table.cells
    )


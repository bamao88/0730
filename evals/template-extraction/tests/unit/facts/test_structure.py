from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from template_extraction_eval.contracts import load_fill_contract
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.facts.structure import locate_paragraphs, table_signature

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def _with_header_and_textbox(source: Path, target: Path) -> Path:
    header_relationship = (
        b'<Relationship Id="rIdHeader" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
        b'Target="header1.xml"/>'
    )
    header_override = (
        b'<Override PartName="/word/header1.xml" '
        b'ContentType="application/vnd.openxmlformats-officedocument.'
        b'wordprocessingml.header+xml"/>'
    )
    textbox = '<w:txbxContent><w:p><w:r><w:t>文本框</w:t></w:r></w:p></w:txbxContent>'.encode()
    with ZipFile(source) as original, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == "word/document.xml":
                content = content.replace(b"<w:sectPr>", textbox + b"<w:sectPr>")
            elif info.filename == "word/_rels/document.xml.rels":
                content = content.replace(
                    b"</Relationships>", header_relationship + b"</Relationships>"
                )
            elif info.filename == "[Content_Types].xml":
                content = content.replace(b"</Types>", header_override + b"</Types>")
            output.writestr(info, content)
        output.writestr(
            "word/header1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:p><w:r><w:t>页眉</w:t></w:r></w:p></w:hdr>",
        )
    return target


def test_str_01_paragraph_run_ranges_and_locator_are_stable() -> None:
    root = FIXTURES / "S00-minimal-pass"
    facts = analyze_docx(root / "gold-template.docx")
    contract = load_fill_contract(root / "gold-contract.yaml")
    paragraph = locate_paragraphs(facts.paragraphs, contract.regions[0].locator)[0]
    assert paragraph.text == "姓名：【姓名】"
    assert [(run.start, run.end) for run in paragraph.runs] == [(0, 3), (3, 7)]


def test_str_02_table_rows_cells_and_merge_are_preserved() -> None:
    facts = analyze_docx(
        FIXTURES / "S12-simple-table-structure" / "gold-template.docx"
    )
    table = facts.tables[0]
    assert table.row_count == 2
    assert table.cells[0].grid_span == 2
    assert table_signature(table)[-1][-1] == "B"


def test_str_03_header_and_textbox_stories_do_not_collapse(tmp_path: Path) -> None:
    source = FIXTURES / "S00-minimal-pass" / "gold-template.docx"
    facts = analyze_docx(_with_header_and_textbox(source, tmp_path / "stories.docx"))
    by_story = {paragraph.story: paragraph for paragraph in facts.paragraphs}
    assert by_story["document"].text == "姓名：【姓名】"
    assert by_story["textbox"].text == "文本框"
    assert by_story["header"].text == "页眉"
    assert by_story["header"].part == "word/header1.xml"

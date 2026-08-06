from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from template_extraction_eval.facts import analyze_docx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def _style_inheritance_docx(source: Path, target: Path) -> Path:
    with ZipFile(source) as original, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == "word/document.xml":
                content = content.replace(
                    b"<w:p>",
                    b'<w:p><w:pPr><w:pStyle w:val="Child"/></w:pPr>',
                    1,
                )
            elif info.filename == "word/styles.xml":
                styles = (
                    b'<w:style w:type="paragraph" w:styleId="Base">'
                    b'<w:name w:val="Base"/><w:rPr><w:b/></w:rPr></w:style>'
                    b'<w:style w:type="paragraph" w:styleId="Child">'
                    b'<w:name w:val="Child"/><w:basedOn w:val="Base"/>'
                    b'<w:rPr><w:sz w:val="28"/></w:rPr></w:style>'
                )
                content = content.replace(b"</w:styles>", styles + b"</w:styles>")
            output.writestr(info, content)
    return target


def test_sty_01_direct_font_size_overrides_defaults() -> None:
    gold = analyze_docx(FIXTURES / "S02-protected-style-changed" / "gold-template.docx")
    actual = analyze_docx(FIXTURES / "S02-protected-style-changed" / "actual-template.docx")
    assert gold.paragraphs[0].runs[0].effective_style.font["size_pt"] == 12
    assert actual.paragraphs[0].runs[0].effective_style.font["size_pt"] == 14


def test_sty_02_document_defaults_and_named_style_inheritance_apply(tmp_path: Path) -> None:
    source = FIXTURES / "S00-minimal-pass" / "gold-template.docx"
    facts = analyze_docx(_style_inheritance_docx(source, tmp_path / "styles.docx"))
    style = facts.controls[0].effective_style
    assert style.font["east_asia"] == "宋体"
    assert style.font["latin"] == "Times New Roman"
    assert style.font["bold"] is True
    assert style.font["size_pt"] == 14


def test_sty_03_paragraph_and_page_units_are_points() -> None:
    facts = analyze_docx(FIXTURES / "S00-minimal-pass" / "gold-template.docx")
    style = facts.paragraphs[0].runs[0].effective_style
    assert style.paragraph["line_spacing_pt"] == 12
    assert style.page["margin_top_pt"] == 72
    assert round(style.page["page_width_pt"], 1) == 595.3

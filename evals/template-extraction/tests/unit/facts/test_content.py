from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from template_extraction_eval.facts import analyze_docx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def _patched_docx(source: Path, target: Path, old: bytes, new: bytes) -> Path:
    with ZipFile(source) as original, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == "word/document.xml":
                content = content.replace(old, new)
            output.writestr(info, content)
    return target


def test_cont_01_preserves_chinese_punctuation_spaces_and_breaks(tmp_path: Path) -> None:
    source = FIXTURES / "S00-minimal-pass" / "gold-template.docx"
    target = _patched_docx(
        source,
        tmp_path / "whitespace.docx",
        "<w:t>姓名：</w:t>".encode(),
        '<w:t xml:space="preserve">姓名：  </w:t><w:br/><w:t>下一行</w:t>'.encode(),
    )
    paragraph = analyze_docx(target).paragraphs[0]
    assert paragraph.text.startswith("姓名：  \n下一行")
    assert "TEXT:\n" in paragraph.tokens


def test_cont_02_extracts_marker_identity_and_range() -> None:
    facts = analyze_docx(FIXTURES / "S00-minimal-pass" / "gold-template.docx")
    control = facts.controls[0]
    assert control.alias == "author.name.zh"
    assert control.tag == "docfit.cover.student_name"
    assert control.text == "【姓名】"
    assert facts.paragraphs[0].text[control.start : control.end] == control.text


def test_cont_03_non_text_objects_are_tokens_not_empty_text() -> None:
    image = analyze_docx(FIXTURES / "S09-protected-image-missing" / "gold-template.docx")
    semantic = analyze_docx(
        FIXTURES / "S13-simple-formula-field-bookmark" / "gold-template.docx"
    )
    assert any("OBJECT:image" in paragraph.tokens for paragraph in image.paragraphs)
    tokens = {token for paragraph in semantic.paragraphs for token in paragraph.tokens}
    assert {"OBJECT:formula", "OBJECT:field", "OBJECT:bookmark"} <= tokens


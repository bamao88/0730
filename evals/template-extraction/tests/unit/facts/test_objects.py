from __future__ import annotations

import hashlib
from pathlib import Path

from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.facts.reader import read_docx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def test_obj_01_image_relationship_hash_and_dimensions_are_bound() -> None:
    path = FIXTURES / "S09-protected-image-missing" / "gold-template.docx"
    package = read_docx(path)
    facts = analyze_docx(path)
    image = next(item for item in facts.objects if item.kind == "image")
    assert image.target == "word/media/tiny.png"
    assert image.content_sha256 == hashlib.sha256(package.parts[image.target]).hexdigest()
    assert (image.width_emu, image.height_emu) == (9525, 9525)


def test_obj_02_formula_field_and_bookmark_have_semantic_facts() -> None:
    facts = analyze_docx(
        FIXTURES / "S13-simple-formula-field-bookmark" / "gold-template.docx"
    )
    by_kind = {item.kind: item for item in facts.objects}
    assert "x+1" in (by_kind["formula"].semantic_xml or "")
    assert by_kind["field"].value == " DATE "
    assert by_kind["bookmark"].name == "SyntheticBookmark"


def test_obj_03_table_merge_and_unsupported_object_are_explicit() -> None:
    table = analyze_docx(FIXTURES / "S12-simple-table-structure" / "gold-template.docx")
    unsupported = analyze_docx(
        FIXTURES / "S10-unsupported-object" / "gold-template.docx"
    )
    assert any(item.kind == "table_merge" and item.value == "gridSpan:2" for item in table.objects)
    assert unsupported.unsupported[0].status.value == "UNKNOWN"
    assert "unsupported" in (unsupported.unsupported[0].detail or "")


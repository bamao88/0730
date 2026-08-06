from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from template_extraction_eval.facts.reader import PackageValidationError, read_docx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def test_read_01_reads_main_parts_and_story() -> None:
    package = read_docx(FIXTURES / "S00-minimal-pass" / "gold-template.docx")
    assert "word/document.xml" in package.parts
    assert "word/styles.xml" in package.parts
    assert [(story.story, story.part) for story in package.story_parts()] == [
        ("document", "word/document.xml")
    ]


def _with_external_relationship(source: Path, target: Path) -> Path:
    relationship = (
        b'<Relationship Id="rIdExternal" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        b'Target="https://example.invalid/" TargetMode="External"/>'
    )
    with ZipFile(source) as original, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == "word/_rels/document.xml.rels":
                content = content.replace(b"</Relationships>", relationship + b"</Relationships>")
            output.writestr(info, content)
    return target


def test_read_02_resolves_internal_and_preserves_external_targets(tmp_path: Path) -> None:
    source = FIXTURES / "S09-protected-image-missing" / "gold-template.docx"
    package = read_docx(_with_external_relationship(source, tmp_path / "relationships.docx"))
    relationship = package.relationship("word/document.xml", "rIdImage")
    assert relationship is not None
    assert relationship.resolved_target == "word/media/tiny.png"
    assert relationship.target_exists is True
    external = package.relationship("word/document.xml", "rIdExternal")
    assert external is not None
    assert external.target_mode == "External"
    assert external.resolved_target is None
    assert external.target_exists is None


@pytest.mark.parametrize(
    "path_factory",
    [
        lambda root: FIXTURES / "S11-invalid-input" / "actual-template.docx",
        lambda root: (root / "not-a-docx.docx"),
    ],
    ids=["missing-main-part", "bad-zip"],
)
def test_read_03_invalid_packages_fail_explicitly(
    tmp_path: Path,
    path_factory: object,
) -> None:
    if not callable(path_factory):
        raise AssertionError("test factory must be callable")
    path = path_factory(tmp_path)
    if path.parent == tmp_path:
        path.write_bytes(b"not a ZIP")
    with pytest.raises(PackageValidationError):
        read_docx(path)

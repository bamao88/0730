from __future__ import annotations

import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
import yaml

import docfit.knowledge as knowledge_api
from docfit.knowledge import (
    KnowledgeValidationError,
    load_knowledge,
    select_knowledge_modules,
    validate_knowledge_package,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_UNIVERSAL = _FIXTURES / "valid-universal" / "v1"
_SAFE_CONTENT_MARKER = "A task evidence item is an authorized input"


def _copy_package(source: Path, tmp_path: Path) -> Path:
    root = tmp_path / source.name
    shutil.copytree(source, root)
    return root


def _manifest(root: Path) -> dict[str, Any]:
    loaded = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write_manifest(root: Path, manifest: dict[str, Any], *, sort_keys: bool = False) -> None:
    (root / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=sort_keys),
        encoding="utf-8",
    )


def _assert_error(root: Path, code: str) -> KnowledgeValidationError:
    with pytest.raises(KnowledgeValidationError) as raised:
        validate_knowledge_package(root)
    assert raised.value.code == code
    assert _SAFE_CONTENT_MARKER not in str(raised.value)
    return raised.value


def test_loads_product_bundled_universal_package() -> None:
    package = load_knowledge()

    assert package.manifest.package_id == "docfit-thesis-format"
    assert package.manifest.version == "v1"
    assert package.manifest.scope == "universal_thesis_formatting"
    assert [document.spec.kind for document in package.documents] == [
        "concepts",
        "recognition_method",
        "interpretation_principle",
        "processing_pattern",
    ]
    assert "不包含任何学校" in package.overview_markdown
    assert all(document.markdown.strip() for document in package.documents)


def test_validates_generic_synthetic_package_as_frozen_typed_model() -> None:
    package = validate_knowledge_package(_UNIVERSAL)

    assert package.manifest.package_id == "synthetic-universal"
    assert package.manifest.document_specs[0].path.as_posix() == "references/concepts.md"
    assert package.documents[0].spec is package.manifest.document_specs[0]
    assert package.documents[-1].spec.kind == "example"
    with pytest.raises(FrozenInstanceError):
        package.manifest.title = "changed"  # type: ignore[misc]


def test_selects_only_requested_universal_documents_as_prompt_modules() -> None:
    package = load_knowledge()

    modules = select_knowledge_modules(
        ["recognition-methods", "interpretation-principles"],
        package=package,
    )

    assert [module.id for module in modules] == [
        "recognition-methods",
        "interpretation-principles",
    ]
    assert all(module.version == package.manifest.version for module in modules)
    assert all(module.package_id == package.manifest.package_id for module in modules)
    assert all(
        module.package_content_digest == package.manifest.content_digest
        for module in modules
    )
    assert all(module.content_digest.startswith("sha256:") for module in modules)
    assert "通用论文格式概念" not in "\n".join(module.content for module in modules)


@pytest.mark.parametrize(
    "module_ids",
    [[], ["concepts", "concepts"], ["unknown-module"]],
)
def test_rejects_invalid_knowledge_module_selection(module_ids: list[str]) -> None:
    with pytest.raises(ValueError):
        select_knowledge_modules(module_ids)


@pytest.mark.parametrize(
    "old_name",
    [
        "SchoolKnowledgePackage",
        "KnowledgeSource",
        "KnowledgeSourceKind",
        "KnowledgeAsset",
        "load_school_knowledge",
    ],
)
def test_old_school_package_api_is_not_public(old_name: str) -> None:
    assert not hasattr(knowledge_api, old_name)


def test_manifest_yaml_key_order_does_not_change_digest(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    _write_manifest(root, _manifest(root), sort_keys=True)

    assert validate_knowledge_package(root).manifest.content_digest.startswith("sha256:")


def test_review_date_is_normalized_for_canonical_digest(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    path = root / "manifest.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('reviewed_at: "2026-08-01"', "reviewed_at: 2026-08-01"),
        encoding="utf-8",
    )

    package = validate_knowledge_package(root)

    assert package.manifest.review.reviewed_at.isoformat() == "2026-08-01"


@pytest.mark.parametrize("missing_name", ["manifest.yaml", "knowledge.md"])
def test_rejects_missing_required_root_file(tmp_path: Path, missing_name: str) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / missing_name).unlink()

    _assert_error(root, "missing_file")


def test_rejects_missing_references_directory(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    shutil.rmtree(root / "references")

    _assert_error(root, "missing_file")


def test_rejects_invalid_yaml(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / "manifest.yaml").write_text("documents: [", encoding="utf-8")

    _assert_error(root, "invalid_yaml")


@pytest.mark.parametrize(
    ("original", "duplicate"),
    [
        ("schema_version: 1\n", "schema_version: 1\nschema_version: 1\n"),
        (
            "  reviewed_by: test-maintainers\n",
            "  reviewed_by: test-maintainers\n  reviewed_by: other-maintainers\n",
        ),
        (
            "    kind: concepts\n",
            "    kind: concepts\n    kind: recognition_method\n",
        ),
    ],
)
def test_rejects_duplicate_yaml_mapping_keys(
    tmp_path: Path,
    original: str,
    duplicate: str,
) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    path = root / "manifest.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(original, duplicate), encoding="utf-8")

    _assert_error(root, "invalid_yaml")


def test_rejects_non_utf8_manifest(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / "manifest.yaml").write_bytes(b"\xff\xfe")

    _assert_error(root, "invalid_utf8")


def test_rejects_non_mapping_manifest(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / "manifest.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    _assert_error(root, "invalid_field_value")


def test_rejects_missing_required_manifest_field(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    del manifest["scope"]
    _write_manifest(root, manifest)

    _assert_error(root, "missing_required_field")


def test_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["schema_version"] = 2
    _write_manifest(root, manifest)

    _assert_error(root, "unsupported_schema_version")


@pytest.mark.parametrize(
    "school_field",
    [
        "school_id",
        "academic_year",
        "degree_level",
        "program_scope",
        "language",
        "template_version",
        "sources",
    ],
)
def test_rejects_school_specific_manifest_fields(tmp_path: Path, school_field: str) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest[school_field] = "forbidden-school-value"
    _write_manifest(root, manifest)

    _assert_error(root, "unknown_field")


def test_rejects_unknown_nested_document_field(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["documents"][0]["school_rule"] = True
    _write_manifest(root, manifest)

    _assert_error(root, "unknown_field")


def test_rejects_directory_identity_mismatch(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["version"] = "v2"
    _write_manifest(root, manifest)

    _assert_error(root, "directory_identity_mismatch")


def test_rejects_non_universal_scope(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["scope"] = "school_specific"
    _write_manifest(root, manifest)

    _assert_error(root, "invalid_field_value")


@pytest.mark.parametrize(
    ("field", "code"),
    [("id", "duplicate_document_id"), ("path", "duplicate_document_path")],
)
def test_rejects_duplicate_document_identity(tmp_path: Path, field: str, code: str) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    duplicate = dict(manifest["documents"][0])
    if field == "id":
        duplicate["path"] = "references/second.md"
    else:
        duplicate["id"] = "second"
    manifest["documents"].append(duplicate)
    _write_manifest(root, manifest)

    _assert_error(root, code)


def test_rejects_missing_declared_document(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / "references" / "concepts.md").unlink()

    _assert_error(root, "missing_file")


def test_rejects_document_hash_mismatch_before_package_digest(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / "references" / "concepts.md").write_text("# Tampered\n", encoding="utf-8")

    _assert_error(root, "document_hash_mismatch")


def test_rejects_package_digest_mismatch(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / "knowledge.md").write_text("# Tampered overview\n", encoding="utf-8")

    _assert_error(root, "content_digest_mismatch")


@pytest.mark.parametrize(
    "document_path",
    [
        "/tmp/outside.md",
        "references/../../outside.md",
        "../outside.md",
        "other/file.md",
        "references/nested/file.md",
        "references/bad\\name.md",
        "references/bad\x00name.md",
        "references//concepts.md",
        "references/.hidden.md",
    ],
)
def test_rejects_unsafe_document_paths(tmp_path: Path, document_path: str) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["documents"][0]["path"] = document_path
    _write_manifest(root, manifest)

    _assert_error(root, "unsafe_path")


def test_rejects_non_markdown_document_path(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["documents"][0]["path"] = "references/concepts.txt"
    _write_manifest(root, manifest)

    _assert_error(root, "invalid_field_value")


@pytest.mark.parametrize(
    "forbidden_name",
    [
        "school.md",
        "structure-profile.yaml",
        "format-profile.yaml",
        "template.docx",
        "template.pdf",
        ".hidden-school-data",
    ],
)
def test_rejects_school_template_profile_and_hidden_root_assets(
    tmp_path: Path,
    forbidden_name: str,
) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / forbidden_name).write_text("must not persist", encoding="utf-8")

    _assert_error(root, "undeclared_path")


@pytest.mark.parametrize("directory", ["references", "examples"])
def test_rejects_undeclared_document_in_controlled_directory(
    tmp_path: Path,
    directory: str,
) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / directory / ".hidden.md").write_text("# Undeclared\n", encoding="utf-8")

    _assert_error(root, "undeclared_path")


def test_rejects_nested_directory_even_when_empty(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / "references" / "nested").mkdir()

    _assert_error(root, "undeclared_path")


def test_rejects_symlink_anywhere_in_package(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    link = root / "references" / "linked.md"
    try:
        link.symlink_to(root / "knowledge.md")
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    _assert_error(root, "symlink_not_allowed")


def test_rejects_symlink_package_root(tmp_path: Path) -> None:
    target = _copy_package(_UNIVERSAL, tmp_path)
    link = tmp_path / "linked-v1"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    _assert_error(link, "symlink_not_allowed")


@pytest.mark.parametrize(
    "relative_path",
    ["knowledge.md", "references/concepts.md", "examples/evidence-reading.md"],
)
def test_rejects_empty_markdown(tmp_path: Path, relative_path: str) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / relative_path).write_text("  \n", encoding="utf-8")

    _assert_error(root, "invalid_field_value")


@pytest.mark.parametrize("relative_path", ["knowledge.md", "references/concepts.md"])
def test_rejects_non_utf8_markdown(tmp_path: Path, relative_path: str) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    (root / relative_path).write_bytes(b"\xff\xfe")

    _assert_error(root, "invalid_utf8")


def test_rejects_manifest_without_documents(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["documents"] = []
    _write_manifest(root, manifest)

    _assert_error(root, "invalid_field_value")


@pytest.mark.parametrize(
    "missing_kind",
    [
        "concepts",
        "recognition_method",
        "interpretation_principle",
        "processing_pattern",
    ],
)
def test_rejects_manifest_missing_a_required_core_kind(
    tmp_path: Path,
    missing_kind: str,
) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["documents"] = [
        document for document in manifest["documents"] if document["kind"] != missing_kind
    ]
    _write_manifest(root, manifest)

    error = _assert_error(root, "invalid_field_value")

    assert error.location == "manifest.yaml:documents"
    assert missing_kind in error.message


def test_rejects_manifest_without_reference_document(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    for document in manifest["documents"]:
        path = Path(document["path"])
        if path.parts[0] != "references":
            continue
        target = root / "examples" / path.name
        (root / path).replace(target)
        document["path"] = f"examples/{path.name}"
    _write_manifest(root, manifest)

    _assert_error(root, "invalid_field_value")


def test_rejects_unknown_document_kind(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["documents"][0]["kind"] = "school_rule"
    _write_manifest(root, manifest)

    _assert_error(root, "invalid_field_value")


def test_rejects_non_string_notes(tmp_path: Path) -> None:
    root = _copy_package(_UNIVERSAL, tmp_path)
    manifest = _manifest(root)
    manifest["notes"] = {"school": "forbidden"}
    _write_manifest(root, manifest)

    _assert_error(root, "invalid_field_value")

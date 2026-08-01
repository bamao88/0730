from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

import yaml
from yaml.nodes import MappingNode

from docfit.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentKind,
    KnowledgeDocumentSpec,
    KnowledgeErrorCode,
    KnowledgeManifest,
    KnowledgePackage,
    KnowledgeReview,
    KnowledgeScope,
    KnowledgeValidationError,
)

_BUNDLED_PACKAGE_ROOT = Path(__file__).parent / "package" / "v1"
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "package_id",
        "version",
        "scope",
        "title",
        "content_digest",
        "documents",
        "review",
        "notes",
    }
)
_REQUIRED_MANIFEST_FIELDS = _MANIFEST_FIELDS - {"notes"}
_DOCUMENT_FIELDS = frozenset({"id", "kind", "path", "description", "sha256"})
_REVIEW_FIELDS = frozenset({"reviewed_by", "reviewed_at"})
_CORE_DOCUMENT_KINDS = frozenset(
    {
        "concepts",
        "recognition_method",
        "interpretation_principle",
        "processing_pattern",
    }
)
_DOCUMENT_KINDS = _CORE_DOCUMENT_KINDS | {"example"}
_SCOPE = "universal_thesis_formatting"
_ROOT_FILES = frozenset({"manifest.yaml", "knowledge.md"})
_ROOT_DIRECTORIES = frozenset({"references", "examples"})
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate keys at every mapping level."""

    def construct_mapping(
        self,
        node: MappingNode,
        deep: bool = False,
    ) -> dict[Any, Any]:
        self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as error:
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    "mapping keys must be hashable",
                    key_node.start_mark,
                ) from error
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    "duplicate mapping key",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_knowledge() -> KnowledgePackage:
    """Load DocFit's single product-bundled universal Knowledge Package."""

    return validate_knowledge_package(_BUNDLED_PACKAGE_ROOT)


def validate_knowledge_package(package_root: Path) -> KnowledgePackage:
    """Validate a universal Knowledge Package for build, test, or maintenance use."""

    root = _package_root(package_root)
    _reject_symlinks(root)

    manifest_path = _required_file(root, PurePosixPath("manifest.yaml"))
    manifest_bytes = _read_bytes(manifest_path, "manifest.yaml")
    manifest_data = _load_yaml_mapping(manifest_bytes)
    manifest = _parse_manifest(manifest_data, root)

    _required_directory(root, PurePosixPath("references"))
    overview_path = _required_file(root, PurePosixPath("knowledge.md"))
    overview_bytes = _read_nonempty_markdown(overview_path, "knowledge.md")

    entries: dict[str, bytes] = {
        "manifest.yaml": _canonical_manifest_bytes(manifest_data, manifest),
        "knowledge.md": overview_bytes,
    }
    documents: list[KnowledgeDocument] = []
    for index, spec in enumerate(manifest.document_specs):
        relative = spec.path.as_posix()
        path = _required_file(root, spec.path)
        raw = _read_nonempty_markdown(path, relative)
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), spec.sha256):
            _fail(
                "document_hash_mismatch",
                f"manifest.yaml:documents[{index}].sha256",
                "document bytes do not match the declared SHA-256",
            )
        entries[relative] = raw
        documents.append(KnowledgeDocument(spec=spec, markdown=raw.decode("utf-8")))

    _reject_undeclared_entries(root, manifest)
    if not hmac.compare_digest(_content_digest(entries), manifest.content_digest):
        _fail(
            "content_digest_mismatch",
            "manifest.yaml:content_digest",
            "package contents do not match the declared content digest",
        )

    return KnowledgePackage(
        root=root,
        manifest=manifest,
        overview_markdown=overview_bytes.decode("utf-8"),
        documents=tuple(documents),
    )


def _package_root(package_root: Path) -> Path:
    if package_root.is_symlink():
        _fail("symlink_not_allowed", ".", "package root must not be a symlink")
    try:
        root = package_root.resolve(strict=True)
    except OSError:
        _fail("missing_file", ".", "package root does not exist or cannot be accessed")
    if not root.is_dir():
        _fail("invalid_field_value", ".", "package root must be a directory")
    return root


def _reject_symlinks(root: Path) -> None:
    try:
        for path in root.rglob("*"):
            if path.is_symlink():
                _fail(
                    "symlink_not_allowed",
                    path.relative_to(root).as_posix(),
                    "Knowledge packages must not contain symlinks",
                )
    except OSError:
        _fail("missing_file", ".", "package contents cannot be enumerated")


def _load_yaml_mapping(raw: bytes) -> dict[str, object]:
    text = _decode_utf8(raw, "manifest.yaml")
    try:
        loaded = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError:
        _fail("invalid_yaml", "manifest.yaml", "file is not valid safe YAML")
    return _mapping(loaded, "manifest.yaml")


def _parse_manifest(data: dict[str, object], root: Path) -> KnowledgeManifest:
    _reject_unknown_fields(data, _MANIFEST_FIELDS, "manifest.yaml")
    _require_fields(data, _REQUIRED_MANIFEST_FIELDS, "manifest.yaml")

    schema_version = data["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        _fail(
            "invalid_field_value",
            "manifest.yaml:schema_version",
            "value must be the integer 1",
        )
    if schema_version != 1:
        _fail(
            "unsupported_schema_version",
            "manifest.yaml:schema_version",
            "only schema version 1 is supported",
        )

    version = _slug(data["version"], "manifest.yaml:version")
    if version != root.name:
        _fail(
            "directory_identity_mismatch",
            "manifest.yaml:version",
            "value must match the package directory name",
        )

    scope_text = _nonempty_string(data["scope"], "manifest.yaml:scope")
    if scope_text != _SCOPE:
        _fail(
            "invalid_field_value",
            "manifest.yaml:scope",
            "value must be universal_thesis_formatting",
        )
    scope = cast(KnowledgeScope, scope_text)

    content_digest = _nonempty_string(data["content_digest"], "manifest.yaml:content_digest")
    if _CONTENT_DIGEST_PATTERN.fullmatch(content_digest) is None:
        _fail(
            "invalid_field_value",
            "manifest.yaml:content_digest",
            "value must be sha256 followed by 64 lowercase hexadecimal characters",
        )

    return KnowledgeManifest(
        schema_version=schema_version,
        package_id=_slug(data["package_id"], "manifest.yaml:package_id"),
        version=version,
        scope=scope,
        title=_nonempty_string(data["title"], "manifest.yaml:title"),
        content_digest=content_digest,
        document_specs=_parse_documents(data["documents"]),
        review=_parse_review(data["review"]),
        notes=_optional_notes(data),
    )


def _parse_documents(value: object) -> tuple[KnowledgeDocumentSpec, ...]:
    if not isinstance(value, list) or not value:
        _fail("invalid_field_value", "manifest.yaml:documents", "value must be a non-empty list")

    document_items = cast(list[object], value)
    documents: list[KnowledgeDocumentSpec] = []
    document_ids: set[str] = set()
    document_paths: set[PurePosixPath] = set()
    document_kinds: set[KnowledgeDocumentKind] = set()
    for index, raw_document in enumerate(document_items):
        location = f"manifest.yaml:documents[{index}]"
        document_data = _mapping(raw_document, location)
        _reject_unknown_fields(document_data, _DOCUMENT_FIELDS, location)
        _require_fields(document_data, _DOCUMENT_FIELDS, location)

        document_id = _slug(document_data["id"], f"{location}.id")
        if document_id in document_ids:
            _fail("duplicate_document_id", f"{location}.id", "document ID must be unique")
        document_ids.add(document_id)

        document_path = _document_path(document_data["path"], f"{location}.path")
        if document_path in document_paths:
            _fail(
                "duplicate_document_path",
                f"{location}.path",
                "document path must be unique",
            )
        document_paths.add(document_path)

        kind_text = _nonempty_string(document_data["kind"], f"{location}.kind")
        if kind_text not in _DOCUMENT_KINDS:
            _fail("invalid_field_value", f"{location}.kind", "value is not a v1 document kind")
        kind = cast(KnowledgeDocumentKind, kind_text)
        document_kinds.add(kind)

        document_hash = _nonempty_string(document_data["sha256"], f"{location}.sha256")
        if _SHA256_PATTERN.fullmatch(document_hash) is None:
            _fail(
                "invalid_field_value",
                f"{location}.sha256",
                "value must be 64 lowercase hexadecimal characters",
            )

        documents.append(
            KnowledgeDocumentSpec(
                id=document_id,
                kind=kind,
                path=document_path,
                description=_nonempty_string(
                    document_data["description"], f"{location}.description"
                ),
                sha256=document_hash,
            )
        )
    missing_core_kinds = sorted(_CORE_DOCUMENT_KINDS - document_kinds)
    if missing_core_kinds:
        _fail(
            "invalid_field_value",
            "manifest.yaml:documents",
            f"at least one {missing_core_kinds[0]} document is required",
        )
    return tuple(documents)


def _parse_review(value: object) -> KnowledgeReview:
    location = "manifest.yaml:review"
    review_data = _mapping(value, location)
    _reject_unknown_fields(review_data, _REVIEW_FIELDS, location)
    _require_fields(review_data, _REVIEW_FIELDS, location)
    return KnowledgeReview(
        reviewed_by=_nonempty_string(review_data["reviewed_by"], f"{location}.reviewed_by"),
        reviewed_at=_iso_date(review_data["reviewed_at"], f"{location}.reviewed_at"),
    )


def _canonical_manifest_bytes(
    data: Mapping[str, object],
    manifest: KnowledgeManifest,
) -> bytes:
    canonical_data = dict(data)
    canonical_data.pop("content_digest", None)
    canonical_data["review"] = {
        "reviewed_by": manifest.review.reviewed_by,
        "reviewed_at": manifest.review.reviewed_at.isoformat(),
    }
    try:
        return json.dumps(
            canonical_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("invalid_field_value", "manifest.yaml", "values must be canonical JSON compatible")


def _content_digest(entries: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(entries):
        path_bytes = relative_path.encode("utf-8")
        content = entries[relative_path]
        digest.update(len(path_bytes).to_bytes(8, "big", signed=False))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big", signed=False))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _reject_undeclared_entries(
    root: Path,
    manifest: KnowledgeManifest,
) -> None:
    declared_files = {spec.path.as_posix() for spec in manifest.document_specs}
    declared_files.update(_ROOT_FILES)
    referenced_count = sum(spec.path.parts[0] == "references" for spec in manifest.document_specs)
    if referenced_count == 0:
        _fail(
            "invalid_field_value",
            "manifest.yaml:documents",
            "at least one document must be declared below references/",
        )

    try:
        root_entries = tuple(root.iterdir())
        all_entries = tuple(root.rglob("*"))
    except OSError:
        _fail("missing_file", ".", "package contents cannot be enumerated")

    for entry in root_entries:
        relative = entry.relative_to(root).as_posix()
        if entry.is_file() and relative in _ROOT_FILES:
            continue
        if entry.is_dir() and relative in _ROOT_DIRECTORIES:
            continue
        _fail("undeclared_path", relative, "path is not declared by Knowledge Package v1")

    for entry in all_entries:
        relative = entry.relative_to(root).as_posix()
        if entry.is_dir():
            if relative in _ROOT_DIRECTORIES:
                continue
            _fail("undeclared_path", relative, "nested directories are not declared in schema v1")
        if not entry.is_file():
            _fail("invalid_field_value", relative, "package entries must be regular files")
        if relative not in declared_files:
            _fail("undeclared_path", relative, "file is not declared in manifest.yaml")

def _required_file(root: Path, relative: PurePosixPath) -> Path:
    path = _controlled_path(root, relative)
    if not path.exists():
        _fail("missing_file", relative.as_posix(), "required file does not exist")
    if not path.is_file():
        _fail("invalid_field_value", relative.as_posix(), "path must be a regular file")
    return path


def _required_directory(root: Path, relative: PurePosixPath) -> Path:
    path = _controlled_path(root, relative)
    if not path.exists():
        _fail("missing_file", relative.as_posix(), "required directory does not exist")
    if not path.is_dir():
        _fail("invalid_field_value", relative.as_posix(), "path must be a directory")
    return path


def _controlled_path(root: Path, relative: PurePosixPath) -> Path:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("unsafe_path", relative.as_posix(), "path must stay inside the package root")
    path = root.joinpath(*relative.parts)
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        _fail("unsafe_path", relative.as_posix(), "path cannot be resolved safely")
    if not resolved.is_relative_to(root):
        _fail("unsafe_path", relative.as_posix(), "path must stay inside the package root")
    return path


def _document_path(value: object, location: str) -> PurePosixPath:
    text = _nonempty_string(value, location)
    if "\\" in text or "\x00" in text:
        _fail("unsafe_path", location, "document path must use POSIX separators")
    path = PurePosixPath(text)
    if path.as_posix() != text or path.is_absolute() or ".." in path.parts:
        _fail("unsafe_path", location, "document path must be a normalized relative POSIX path")
    if len(path.parts) != 2 or path.parts[0] not in _ROOT_DIRECTORIES:
        _fail(
            "unsafe_path",
            location,
            "document path must be directly below references/ or examples/",
        )
    if path.name.startswith("."):
        _fail("unsafe_path", location, "hidden document paths are not allowed")
    if path.suffix != ".md":
        _fail("invalid_field_value", location, "document path must have the .md extension")
    return path


def _read_nonempty_markdown(path: Path, location: str) -> bytes:
    raw = _read_bytes(path, location)
    text = _decode_utf8(raw, location)
    if not text.strip():
        _fail("invalid_field_value", location, "Markdown file must contain non-whitespace text")
    return raw


def _read_bytes(path: Path, location: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        _fail("missing_file", location, "file cannot be read")


def _decode_utf8(raw: bytes, location: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("invalid_utf8", location, "file must be valid UTF-8")


def _mapping(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail("invalid_field_value", location, "value must be a mapping with string keys")
    return cast(dict[str, object], value)


def _reject_unknown_fields(
    data: Mapping[str, object], allowed: frozenset[str], location: str
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail("unknown_field", f"{location}:{unknown[0]}", "field is not declared in schema v1")


def _require_fields(data: Mapping[str, object], required: frozenset[str], location: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        _fail(
            "missing_required_field",
            f"{location}:{missing[0]}",
            "required field is missing",
        )


def _nonempty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("invalid_field_value", location, "value must be a non-empty string")
    return value


def _optional_notes(data: Mapping[str, object]) -> str | None:
    if "notes" not in data or data["notes"] is None:
        return None
    value = data["notes"]
    if not isinstance(value, str):
        _fail("invalid_field_value", "manifest.yaml:notes", "value must be a string or null")
    return value


def _iso_date(value: object, location: str) -> date:
    if type(value) is date:
        return value
    text = _nonempty_string(value, location)
    try:
        return date.fromisoformat(text)
    except ValueError:
        _fail("invalid_field_value", location, "value must be an ISO 8601 date")


def _slug(value: object, location: str) -> str:
    text = _nonempty_string(value, location)
    if _SLUG_PATTERN.fullmatch(text) is None:
        _fail("invalid_field_value", location, "value must be a lowercase hyphenated slug")
    return text


def _fail(code: KnowledgeErrorCode, location: str, message: str) -> NoReturn:
    raise KnowledgeValidationError(code, location, message)

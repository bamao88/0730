from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Literal

KnowledgeDocumentKind = Literal[
    "concepts",
    "recognition_method",
    "interpretation_principle",
    "processing_pattern",
    "example",
]

KnowledgeScope = Literal["universal_thesis_formatting"]

KnowledgeErrorCode = Literal[
    "invalid_yaml",
    "unsupported_schema_version",
    "missing_required_field",
    "unknown_field",
    "invalid_field_value",
    "directory_identity_mismatch",
    "unsafe_path",
    "symlink_not_allowed",
    "missing_file",
    "undeclared_path",
    "duplicate_document_id",
    "duplicate_document_path",
    "document_hash_mismatch",
    "content_digest_mismatch",
    "invalid_utf8",
]


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentSpec:
    id: str
    kind: KnowledgeDocumentKind
    path: PurePosixPath
    description: str
    sha256: str


@dataclass(frozen=True, slots=True)
class KnowledgeReview:
    reviewed_by: str
    reviewed_at: date


@dataclass(frozen=True, slots=True)
class KnowledgeManifest:
    schema_version: int
    package_id: str
    version: str
    scope: KnowledgeScope
    title: str
    content_digest: str
    document_specs: tuple[KnowledgeDocumentSpec, ...]
    review: KnowledgeReview
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    spec: KnowledgeDocumentSpec
    markdown: str


@dataclass(frozen=True, slots=True)
class KnowledgePackage:
    root: Path
    manifest: KnowledgeManifest
    overview_markdown: str
    documents: tuple[KnowledgeDocument, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeModule:
    """One explicitly selected, prompt-ready view of a universal document."""

    id: str
    kind: KnowledgeDocumentKind
    description: str
    version: str
    content_digest: str
    content: str
    package_id: str
    package_content_digest: str


class KnowledgeValidationError(ValueError):
    """A stable, content-safe error raised for an invalid Knowledge package."""

    def __init__(self, code: KnowledgeErrorCode, location: str, message: str) -> None:
        self.code = code
        self.location = location
        self.message = message
        super().__init__(f"{code} at {location}: {message}")

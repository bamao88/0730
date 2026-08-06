"""Immutable task-local evidence store with opaque references."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docfit.template.runtime.atomic import publish_json_directory, write_json_file
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

STORE_VERSION = 1
_REF_PATTERN = re.compile(r"^(snapshot|render|mutation|comparison):v1:([0-9a-f]{32})$")


@dataclass(frozen=True, slots=True)
class EvidenceStore:
    task_root: Path

    @property
    def root(self) -> Path:
        return self.task_root / "work" / ".docfit" / "template-v1"

    def publish(self, kind: str, payload: JsonObject) -> str:
        payload_sha256 = sha256_json(payload)
        opaque = sha256_json(
            {
                "store_version": STORE_VERSION,
                "kind": kind,
                "payload_sha256": payload_sha256,
            }
        )[:32]
        reference = f"{kind}:v1:{opaque}"
        target = self.root / f"{kind}s" / opaque
        manifest: JsonObject = {
            "schema_version": 1,
            "store_version": STORE_VERSION,
            "kind": kind,
            "ref": reference,
            "payload_path": "payload.json",
            "payload_sha256": payload_sha256,
        }
        if target.exists():
            existing = self._read_json(target / "manifest.json")
            existing_payload = self._read_json(target / "payload.json")
            if existing != manifest or sha256_json(existing_payload) != payload_sha256:
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="evidence_collision",
                    message="Existing task evidence does not match its opaque reference.",
                )
            return reference
        publish_json_directory(
            target,
            {"payload.json": payload, "manifest.json": manifest},
        )
        return reference

    def publish_bundle(
        self,
        kind: str,
        payload: JsonObject,
        files: dict[str, Path],
    ) -> str:
        file_records = [
            {
                "path": name,
                "sha256": sha256_file(source),
                "size": source.stat().st_size,
            }
            for name, source in sorted(files.items())
        ]
        payload_sha256 = sha256_json(payload)
        opaque = sha256_json(
            {
                "store_version": STORE_VERSION,
                "kind": kind,
                "payload_sha256": payload_sha256,
                "files": file_records,
            }
        )[:32]
        reference = f"{kind}:v1:{opaque}"
        target = self.root / f"{kind}s" / opaque
        manifest: JsonObject = {
            "schema_version": 1,
            "store_version": STORE_VERSION,
            "kind": kind,
            "ref": reference,
            "payload_path": "payload.json",
            "payload_sha256": payload_sha256,
            "files": file_records,
        }
        if target.exists():
            self.resolve(reference, expected_kind=kind)
            return reference
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
        try:
            write_json_file(temporary / "payload.json", payload)
            for name, source in files.items():
                destination = temporary / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(
                    destination,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        with source.open("rb") as source_handle:
                            shutil.copyfileobj(source_handle, handle)
                        handle.flush()
                        os.fsync(handle.fileno())
                except BaseException:
                    destination.unlink(missing_ok=True)
                    raise
            write_json_file(temporary / "manifest.json", manifest)
            try:
                os.rename(temporary, target)
            except FileExistsError:
                self.resolve(reference, expected_kind=kind)
            return reference
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def resolve(self, reference: Any, *, expected_kind: str) -> JsonObject:
        if not isinstance(reference, str):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code=f"{expected_kind}_ref_not_found",
                message=f"A valid {expected_kind} evidence reference is required.",
            )
        match = _REF_PATTERN.fullmatch(reference)
        if match is None or match.group(1) != expected_kind:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code=f"{expected_kind}_ref_not_found",
                message=f"The {expected_kind} evidence reference is invalid or unavailable.",
            )
        opaque = match.group(2)
        target = self.root / f"{expected_kind}s" / opaque
        if not target.is_dir():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code=f"{expected_kind}_ref_not_found",
                message=f"The {expected_kind} evidence reference is invalid or unavailable.",
            )
        manifest = self._read_json(target / "manifest.json")
        payload = self._read_json(target / "payload.json")
        expected_manifest: JsonObject = {
            "schema_version": 1,
            "store_version": STORE_VERSION,
            "kind": expected_kind,
            "ref": reference,
            "payload_path": "payload.json",
            "payload_sha256": sha256_json(payload),
        }
        files = manifest.get("files")
        if files is not None:
            if not isinstance(files, list):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="evidence_invalid",
                    message="Task evidence has an invalid file inventory.",
                )
            expected_files: list[JsonObject] = []
            for item in files:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    raise ToolFailure(
                        status="error",
                        origin="evidence",
                        code="evidence_invalid",
                        message="Task evidence has an invalid file inventory.",
                    )
                path = (target / item["path"]).resolve(strict=True)
                if target not in path.parents:
                    raise ToolFailure(
                        status="error",
                        origin="evidence",
                        code="evidence_invalid",
                        message="Task evidence contains an unsafe file path.",
                    )
                expected_files.append(
                    {"path": item["path"], "sha256": sha256_file(path), "size": path.stat().st_size}
                )
            expected_manifest["files"] = expected_files
        if manifest != expected_manifest:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_hash_mismatch",
                message="Task evidence failed its integrity check.",
            )
        return payload

    def bundle_path(self, reference: Any, *, expected_kind: str) -> Path:
        self.resolve(reference, expected_kind=expected_kind)
        assert isinstance(reference, str)
        opaque = reference.rsplit(":", 1)[-1]
        return (self.root / f"{expected_kind}s" / opaque).resolve(strict=True)

    def discard(self, reference: str, *, expected_kind: str) -> None:
        """Roll back evidence created by the current transaction only."""
        target = self.bundle_path(reference, expected_kind=expected_kind)
        shutil.rmtree(target)

    @staticmethod
    def _read_json(path: Path) -> JsonObject:
        try:
            value: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_unreadable",
                message="Task evidence cannot be read or verified.",
            ) from error
        if not isinstance(value, dict):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="evidence_invalid",
                message="Task evidence has an invalid shape.",
            )
        return value

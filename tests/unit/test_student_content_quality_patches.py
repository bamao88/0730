from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from docfit.content.quality_patches import load_quality_patches
from docfit.tools.runtime import ToolFailure


def _inventory(source_sha256: str) -> dict[str, object]:
    return {
        "source_sha256": source_sha256,
        "objects": [
            {
                "kind": "paragraph",
                "text": "AlphaBetasp. remains",
                "source_object_ref": {"object_id": "obj-body-1"},
            }
        ],
    }


def _write_patches(
    path: Path,
    *,
    source_sha256: str,
    source_object_id: str = "obj-body-1",
    before: str = "AlphaBetasp.",
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "docfit-student-quality-patches/v1",
                "source_sha256": source_sha256,
                "patches": [
                    {
                        "patch_id": "patch-001",
                        "source_object_id": source_object_id,
                        "before": before,
                        "after": "AlphaBeta sp.",
                        "reason": "Remove a source run-boundary spacing artifact.",
                        "expected_count": 1,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_quality_patch_is_bound_to_exact_source_object(tmp_path: Path) -> None:
    source_sha256 = "a" * 64
    patch_path = tmp_path / "quality-patches.yaml"
    _write_patches(patch_path, source_sha256=source_sha256)

    patches = load_quality_patches(
        patch_path,
        source_sha256=source_sha256,
        inventory=_inventory(source_sha256),
    )

    assert len(patches) == 1
    assert patches[0].patch_id == "patch-001"
    assert patches[0].source_object_id == "obj-body-1"
    assert patches[0].old == "AlphaBetasp."
    assert patches[0].new == "AlphaBeta sp."


def test_quality_patch_rejects_another_source_snapshot(tmp_path: Path) -> None:
    patch_path = tmp_path / "quality-patches.yaml"
    _write_patches(patch_path, source_sha256="a" * 64)

    with pytest.raises(ToolFailure) as failure:
        load_quality_patches(
            patch_path,
            source_sha256="b" * 64,
            inventory=_inventory("b" * 64),
        )

    assert failure.value.code == "quality_patches_source_stale"


@pytest.mark.parametrize(
    ("source_object_id", "before"),
    (("obj-missing", "AlphaBetasp."), ("obj-body-1", "absent text")),
)
def test_quality_patch_rejects_untraceable_or_changed_evidence(
    tmp_path: Path,
    source_object_id: str,
    before: str,
) -> None:
    source_sha256 = "a" * 64
    patch_path = tmp_path / "quality-patches.yaml"
    _write_patches(
        patch_path,
        source_sha256=source_sha256,
        source_object_id=source_object_id,
        before=before,
    )

    with pytest.raises(ToolFailure) as failure:
        load_quality_patches(
            patch_path,
            source_sha256=source_sha256,
            inventory=_inventory(source_sha256),
        )

    assert failure.value.code in {"quality_patch_invalid", "quality_patch_evidence_mismatch"}

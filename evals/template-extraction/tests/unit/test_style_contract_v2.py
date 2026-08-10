from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from template_extraction_eval.contracts import (
    InputContractError,
    InputErrorCode,
    compute_style_contract_digest,
    compute_style_contract_set_digest,
    load_fill_contract,
    load_legacy_fill_contract,
)

V2 = "docfit-template-fill-contract/v2"
TEMPLATE_SHA256 = "1" * 64


def _style(
    style_contract_id: str = "style.cover.title",
    *,
    dependencies: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    style: dict[str, Any] = {
        "style_contract_id": style_contract_id,
        "contract_digest": "0" * 64,
        "label": "Cover title",
        "word_style_id": "CoverTitle",
        "word_style_name": "封面标题",
        "owned_properties": [
            "paragraph.alignment",
            "run.font_size_pt",
            "run.bold",
        ],
        "effective_properties": {
            "run.font_size_pt": 16,
            "run.bold": True,
            "paragraph.alignment": "center",
        },
        "application_scope": "text",
        "override_policy": {
            "managed_direct_formatting": "clear_conflicts",
            "unmanaged_properties": "preserve",
        },
        "dependencies": [] if dependencies is None else dependencies,
        "evidence_refs": [{"source": "gold"}],
    }
    style["contract_digest"] = compute_style_contract_digest(style)
    return style


def _contract(styles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    style_values = [_style()] if styles is None else styles
    selected = style_values[-1]
    value: dict[str, Any] = {
        "schema_version": V2,
        "contract_id": "test.style-contract-v2",
        "template_sha256": TEMPLATE_SHA256,
        "field_registry_ref": {
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.1.0",
            "sha256": "2" * 64,
        },
        "marker_protocol": "docfit-content-control-marker/v1",
        "regions": [],
        "slots": [
            {
                "slot_id": "slot.cover.title",
                "owner": "slot",
                "field_id": "thesis.title.zh",
                "content_type": "text",
                "required": True,
                "cardinality": "one",
                "locator": {
                    "type": "content_control_tag",
                    "value": "docfit.cover.title",
                    "story": "document",
                    "part": "word/document.xml",
                    "expected_match_count": 1,
                },
                "style_contract_ref": {
                    "style_contract_id": selected["style_contract_id"],
                    "contract_digest": selected["contract_digest"],
                },
            }
        ],
        "styles": style_values,
    }
    _refresh_set_digest(value)
    return value


def _refresh_set_digest(value: dict[str, Any]) -> None:
    value["style_contract_set_digest"] = compute_style_contract_set_digest(
        schema_version=str(value["schema_version"]),
        template_sha256=str(value["template_sha256"]),
        styles=value["styles"],
    )


def _write(tmp_path: Path, value: dict[str, Any], name: str = "fill-contract.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def test_v2_loads_styles_and_derives_slot_style_from_the_only_source(tmp_path: Path) -> None:
    value = _contract()

    contract = load_fill_contract(_write(tmp_path, value))

    assert contract.schema_version == V2
    assert len(contract.styles) == 1
    style = contract.styles[0]
    slot = contract.slots[0]
    assert contract.styles_by_id[style.style_contract_id] is style
    assert style.effective_properties == {
        "run.font_size_pt": 16,
        "run.bold": True,
        "paragraph.alignment": "center",
    }
    assert slot.style_contract_ref is not None
    assert slot.style_contract_ref.contract_digest == style.contract_digest
    assert slot.expected_value_style.font == {"size_pt": 16, "bold": True}
    assert slot.expected_value_style.paragraph == {"alignment": "center"}
    assert contract.style_contract_set_digest == value["style_contract_set_digest"]


def test_v2_digest_excludes_hints_but_covers_all_semantic_fields() -> None:
    original = _style()
    hint_only = deepcopy(original)
    hint_only["label"] = "Renamed"
    hint_only["word_style_id"] = "DifferentMaterialization"
    hint_only["word_style_name"] = "不同名称"
    hint_only["evidence_refs"] = [{"source": "different"}]
    assert compute_style_contract_digest(hint_only) == original["contract_digest"]

    semantic_change = deepcopy(original)
    semantic_change["effective_properties"]["run.bold"] = False
    assert compute_style_contract_digest(semantic_change) != original["contract_digest"]


def test_v2_rejects_inline_expected_value_style(tmp_path: Path) -> None:
    value = _contract()
    value["slots"][0]["expected_value_style"] = {"font": {"bold": False}}

    with pytest.raises(InputContractError) as captured:
        load_fill_contract(_write(tmp_path, value))

    assert captured.value.code is InputErrorCode.SCHEMA_INVALID


def test_v2_rejects_style_and_set_digest_mismatches(tmp_path: Path) -> None:
    style_mismatch = _contract()
    style_mismatch["styles"][0]["effective_properties"]["run.bold"] = False
    with pytest.raises(InputContractError) as captured:
        load_fill_contract(_write(tmp_path, style_mismatch, "style-mismatch.yaml"))
    assert captured.value.code is InputErrorCode.HASH_MISMATCH
    assert "style style.cover.title digest mismatch" in str(captured.value)

    set_mismatch = _contract()
    set_mismatch["style_contract_set_digest"] = "f" * 64
    with pytest.raises(InputContractError) as captured:
        load_fill_contract(_write(tmp_path, set_mismatch, "set-mismatch.yaml"))
    assert captured.value.code is InputErrorCode.HASH_MISMATCH
    assert "style contract set digest mismatch" in str(captured.value)


def test_v2_validates_slot_and_dependency_reference_closure(tmp_path: Path) -> None:
    base = _style("style.base")
    child = _style(
        "style.child",
        dependencies=[
            {
                "style_contract_id": base["style_contract_id"],
                "contract_digest": base["contract_digest"],
            }
        ],
    )
    closed = _contract([base, child])
    contract = load_fill_contract(_write(tmp_path, closed, "closed.yaml"))
    assert contract.styles_by_id["style.child"].dependencies[0].style_contract_id == "style.base"

    missing = _contract([base, child])
    missing["slots"][0]["style_contract_ref"] = {
        "style_contract_id": "style.missing",
        "contract_digest": "a" * 64,
    }
    with pytest.raises(InputContractError) as captured:
        load_fill_contract(_write(tmp_path, missing, "missing.yaml"))
    assert captured.value.code is InputErrorCode.CONTRACT_MISMATCH
    assert "references missing style" in str(captured.value)

    bad_dependency = _contract([base, child])
    bad_dependency["styles"][1]["dependencies"][0]["contract_digest"] = "b" * 64
    bad_dependency["styles"][1]["contract_digest"] = compute_style_contract_digest(
        bad_dependency["styles"][1]
    )
    bad_dependency["slots"][0]["style_contract_ref"]["contract_digest"] = (
        bad_dependency["styles"][1]["contract_digest"]
    )
    _refresh_set_digest(bad_dependency)
    with pytest.raises(InputContractError) as captured:
        load_fill_contract(_write(tmp_path, bad_dependency, "bad-dependency.yaml"))
    assert captured.value.code is InputErrorCode.CONTRACT_MISMATCH
    assert "style digest does not match style.base" in str(captured.value)


def test_v2_rejects_owned_property_missing_from_effective_properties(tmp_path: Path) -> None:
    value = _contract()
    value["styles"][0]["owned_properties"].append("run.italic")
    value["styles"][0]["contract_digest"] = compute_style_contract_digest(value["styles"][0])
    value["slots"][0]["style_contract_ref"]["contract_digest"] = value["styles"][0][
        "contract_digest"
    ]
    _refresh_set_digest(value)

    with pytest.raises(InputContractError) as captured:
        load_fill_contract(_write(tmp_path, value))

    assert captured.value.code is InputErrorCode.CONTRACT_MISMATCH
    assert "owns missing effective property run.italic" in str(captured.value)


def test_legacy_v1_reader_resolves_style_id_without_forcing_inline_style(
    tmp_path: Path,
) -> None:
    value = _contract()
    value["schema_version"] = "docfit-template-fill-contract/v1"
    value.pop("style_contract_set_digest")
    value["slots"][0].pop("style_contract_ref")
    value["slots"][0]["style_id"] = "style.cover.title"
    value["styles"] = [
        {
            "style_id": "style.cover.title",
            "effective_properties": {
                "font": {"size_pt": 16, "bold": True},
                "paragraph": {"alignment": "center"},
                "container": {},
                "page": {},
            },
        }
    ]
    path = _write(tmp_path, value)

    legacy = load_legacy_fill_contract(path)
    dispatched = load_fill_contract(path)

    assert legacy.slots[0].expected_value_style.font["bold"] is True
    assert legacy.slots[0].style_contract_ref is None
    assert legacy.styles == ()
    assert dispatched == legacy


def test_legacy_reader_rejects_v2_contract(tmp_path: Path) -> None:
    with pytest.raises(InputContractError) as captured:
        load_legacy_fill_contract(_write(tmp_path, _contract()))
    assert captured.value.code is InputErrorCode.CONTRACT_MISMATCH

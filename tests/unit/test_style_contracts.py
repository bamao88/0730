from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from docfit.styles import StyleContractSet, style_contract_digest
from docfit.tools.runtime import ToolFailure, sha256_json

TEMPLATE_SHA256 = "a" * 64


def _style(
    style_contract_id: str,
    *,
    dependencies: list[dict[str, str]] | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "style_contract_id": style_contract_id,
        "application_scope": "paragraph",
        "owned_properties": ["paragraph.alignment", "run.font_size_pt", "run.bold"],
        "effective_properties": {
            "run.bold": True,
            "run.font_size_pt": 12,
            "paragraph.alignment": "center",
        },
        "override_policy": {
            "managed_direct_formatting": "clear_conflicts",
            "unmanaged_properties": "preserve",
        },
        "dependencies": dependencies or [],
        "word_style_id": "DocFitStableTitle",
        "word_style_name": "DocFit Stable Title",
        "evidence_refs": [{"type": "template_object", "value": "obj-1"}],
    }
    if label is not None:
        value["label"] = label
    value["contract_digest"] = style_contract_digest(value)
    return value


def _set(*styles: dict[str, Any]) -> StyleContractSet:
    return StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": TEMPLATE_SHA256,
            "styles": list(styles),
        }
    )


def test_style_contract_set_is_normalized_immutable_and_preserves_hints() -> None:
    raw = _style("style.title", label="Title")
    contracts = _set(raw)

    style = contracts.resolve(
        {
            "style_contract_id": "style.title",
            "contract_digest": raw["contract_digest"],
        }
    )

    assert style.application_scope == "paragraph"
    assert style.owned_properties == (
        "paragraph.alignment",
        "run.bold",
        "run.font_size_pt",
    )
    assert style.effective_properties["run.font_size_pt"] == 12.0
    assert style.word_style_id == "DocFitStableTitle"
    assert style.word_style_name == "DocFit Stable Title"
    assert style.label == "Title"
    assert style.digest == style.contract_digest
    with pytest.raises(TypeError):
        style.effective_properties["run.bold"] = False  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        style.label = "Changed"  # type: ignore[misc]

    serialized = contracts.as_dict()
    assert "style_contract_set_digest" in serialized
    assert "digest" not in serialized
    assert serialized["styles"][0]["contract_digest"] == raw["contract_digest"]
    assert StyleContractSet.from_mapping(serialized) == contracts
    with pytest.raises(ToolFailure):
        contracts.resolve("style.title")  # type: ignore[arg-type]


def test_semantic_digest_excludes_materialization_hints() -> None:
    first = _style("style.title", label="Original")
    second = dict(first)
    second.update(
        {
            "label": "Renamed",
            "word_style_id": "DifferentWordStyle",
            "word_style_name": "Different name",
            "evidence_refs": [{"type": "other"}],
        }
    )

    assert style_contract_digest(first) == style_contract_digest(second)

    changed = dict(first)
    changed["effective_properties"] = {
        **first["effective_properties"],
        "run.bold": False,
    }
    assert style_contract_digest(first) != style_contract_digest(changed)


def test_dependencies_are_digest_bound_and_cycles_are_rejected() -> None:
    base = _style("style.base")
    derived = _style(
        "style.derived",
        dependencies=[
            {
                "style_contract_id": "style.base",
                "contract_digest": base["contract_digest"],
            }
        ],
    )
    contracts = _set(derived, base)
    assert contracts.styles[0].style_contract_id == "style.base"

    stale = dict(derived)
    stale["dependencies"] = [
        {"style_contract_id": "style.base", "contract_digest": "f" * 64}
    ]
    stale["contract_digest"] = style_contract_digest(stale)
    with pytest.raises(ToolFailure) as caught:
        _set(base, stale)
    assert caught.value.code == "style_contract_dependency_stale"

    first = _style(
        "style.first",
        dependencies=[{"style_contract_id": "style.second", "contract_digest": "1" * 64}],
    )
    second = _style(
        "style.second",
        dependencies=[
            {"style_contract_id": "style.first", "contract_digest": first["contract_digest"]}
        ],
    )
    first["dependencies"][0]["contract_digest"] = second["contract_digest"]
    first["contract_digest"] = style_contract_digest(first)
    second["dependencies"][0]["contract_digest"] = first["contract_digest"]
    second["contract_digest"] = style_contract_digest(second)
    # A digest-bound cycle has no finite fixed point. Stale binding is rejected first.
    with pytest.raises(ToolFailure) as cycle:
        _set(first, second)
    assert cycle.value.code in {
        "style_contract_dependency_stale",
        "style_contract_dependency_cycle",
    }


def test_fill_contract_set_digest_uses_only_template_and_style_refs() -> None:
    style = _style("style.title")
    refs = [
        {
            "style_contract_id": style["style_contract_id"],
            "contract_digest": style["contract_digest"],
        }
    ]
    expected = sha256_json(
        {
            "schema_version": "docfit-template-fill-contract/v2",
            "template_sha256": TEMPLATE_SHA256,
            "styles": refs,
        }
    )
    fill_contract = {
        "schema_version": "docfit-template-fill-contract/v2",
        "template_sha256": TEMPLATE_SHA256,
        "styles": [style],
        "style_contract_set_digest": expected,
    }

    contracts = StyleContractSet.from_fill_contract(fill_contract)

    assert contracts.digest == expected
    with pytest.raises(ToolFailure) as stale:
        StyleContractSet.from_fill_contract(
            {**fill_contract, "style_contract_set_digest": "0" * 64}
        )
    assert stale.value.code == "style_contract_set_digest_mismatch"


def test_noncanonical_contract_shapes_fail_closed() -> None:
    style = _style("style.title")
    style["application_scope"] = ["paragraph"]
    style["contract_digest"] = "0" * 64

    with pytest.raises(ToolFailure) as caught:
        _set(style)

    assert caught.value.code == "style_contract_invalid"

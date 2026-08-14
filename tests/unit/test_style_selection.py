from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest

from docfit.styles.actual_roles import ActualStyleRoleSet
from docfit.styles.materialization import materialize_style_contracts
from docfit.styles.presets import GeneralStylePreset
from docfit.styles.profiles import (
    PropertyDefinition,
    StylePropertyProfile,
    StylePropertyProfileRegistry,
)
from docfit.styles.selection import (
    compile_selected_style_contracts,
    select_complete_style_roles,
)
from docfit.styles.validator import StyleContractValidator
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"


def _registry() -> tuple[StylePropertyProfileRegistry, StylePropertyProfile]:
    profile = StylePropertyProfile.build(
        role_type="caption",
        properties=(
            PropertyDefinition.build(
                property_path="run.bold",
                applicable_role_types={"caption"},
                value_type="boolean",
                resolver_sources=("run.bold",),
                canonicalization="identity",
                materializer_targets=("run.bold",),
            ),
            PropertyDefinition.build(
                property_path="run.underline",
                applicable_role_types={"caption"},
                allows_none=True,
                resolver_sources=("run.underline",),
                canonicalization="identity",
                materializer_targets=("run.underline",),
            ),
        ),
    )
    return StylePropertyProfileRegistry.build([profile]), profile


def _preset(registry: StylePropertyProfileRegistry) -> GeneralStylePreset:
    value: dict[str, Any] = {
        "schema_version": "docfit-general-style-preset/v1.0",
        "preset_id": "docfit.selection-test",
        "preset_version": "1.0.0",
        "status": "product_definition_accepted",
        "parameters": {},
        "complete_style_type_profiles": {
            "caption": {"run": {"bold": False, "underline": "none"}}
        },
        "required_effective_properties": {
            "caption": ["run.bold", "run.underline"]
        },
        "style_roles": {
            "style.caption.table": {
                "role_type": "caption",
                "complete": True,
                "evidence_profile": "accepted",
                "value_authority": "accepted_product_value",
            }
        },
        "field_handling": {
            "body.table.caption": {
                "handling": "styled_content",
                "components": {"content": "style.caption.table"},
            }
        },
    }
    return GeneralStylePreset.from_mapping(value, registry=registry)


def _actual(
    preset: GeneralStylePreset,
) -> ActualStyleRoleSet:
    return ActualStyleRoleSet.compile(
        preset=preset,
        student_field_ids=["body.table.caption"],
    )


def _school_candidate(
    profile: StylePropertyProfile,
    observation_digest: str,
) -> dict[str, Any]:
    semantic = {
        "schema_version": "docfit-school-style-role-candidate/v1",
        "style_role_id": "style.caption.table",
        "style_role_type": "caption",
        "property_profile_ref": profile.ref().as_dict(),
        "properties": [
            {
                "property_path": "run.bold",
                "effective_state": "VALUE",
                "value": True,
            },
            {
                "property_path": "run.underline",
                "effective_state": "NONE",
            },
        ],
    }
    return {
        **semantic,
        "candidate_digest": sha256_json(semantic),
        "applies_to": ["body.table.caption"],
        "evidence_refs": [
            {
                "type": "school_field_style_observation",
                "slot_id": "body.table.caption.1",
                "observation_digest": "b" * 64,
                "school_observation_set_digest": observation_digest,
            }
        ],
    }


def test_complete_school_role_is_selected_whole_without_preset_mixing() -> None:
    registry, profile = _registry()
    preset = _preset(registry)
    observation_digest = "a" * 64

    receipt = select_complete_style_roles(
        actual_roles=_actual(preset),
        school_candidates=[_school_candidate(profile, observation_digest)],
        school_observation_set_digest=observation_digest,
        preset=preset,
        registry=registry,
    )

    selected = receipt.selections[0]
    assert selected.source == "school"
    assert [item.effective_state for item in selected.properties] == ["VALUE", "NONE"]
    assert selected.properties[0].value is True
    assert receipt.as_dict()["selection_counts"] == {"school": 1, "preset": 0}


def test_hunau_missing_table_caption_selects_the_complete_preset_role() -> None:
    registry, _ = _registry()
    preset = _preset(registry)

    receipt = select_complete_style_roles(
        actual_roles=_actual(preset),
        school_candidates=[],
        school_observation_set_digest="a" * 64,
        preset=preset,
        registry=registry,
    )

    selected = receipt.selections[0]
    assert selected.style_role_id == "style.caption.table"
    assert selected.source == "preset"
    assert selected.properties[0].value is False
    assert selected.properties[1].effective_state == "NONE"
    assert receipt.as_dict()["selection_counts"] == {"school": 0, "preset": 1}
    assert len(receipt.selected_style_contract_set_digest) == 64


def test_corrupt_school_candidate_fails_closed_instead_of_falling_back() -> None:
    registry, profile = _registry()
    preset = _preset(registry)
    candidate = _school_candidate(profile, "a" * 64)
    candidate["properties"] = candidate["properties"][:1]

    with pytest.raises(ToolFailure, match="fixed property profile"):
        select_complete_style_roles(
            actual_roles=_actual(preset),
            school_candidates=[candidate],
            school_observation_set_digest="a" * 64,
            preset=preset,
            registry=registry,
        )


def test_selection_digests_are_deterministic_and_separate_from_observation() -> None:
    registry, _ = _registry()
    preset = _preset(registry)
    kwargs = {
        "actual_roles": _actual(preset),
        "school_candidates": [],
        "school_observation_set_digest": "a" * 64,
        "preset": preset,
        "registry": registry,
    }

    first = select_complete_style_roles(**kwargs)
    second = select_complete_style_roles(**kwargs)

    assert first.selected_style_contract_set_digest == (
        second.selected_style_contract_set_digest
    )
    assert first.selection_receipt_digest == second.selection_receipt_digest
    assert first.selected_style_contract_set_digest != first.school_observation_set_digest


def test_typed_none_compiles_to_an_explicit_occurrence_contract() -> None:
    registry, _ = _registry()
    preset = _preset(registry)
    receipt = select_complete_style_roles(
        actual_roles=_actual(preset),
        school_candidates=[],
        school_observation_set_digest="a" * 64,
        preset=preset,
        registry=registry,
    )

    contracts = compile_selected_style_contracts(
        receipt=receipt,
        template_sha256="c" * 64,
        registry=registry,
    )

    style = contracts.styles[0]
    assert style.effective_properties == {
        "run.bold": False,
        "run.underline": None,
    }
    assert style.style_contract_id == "selected.style.caption.table"


@pytest.mark.parametrize("count", [1, 10, 100])
def test_missing_school_table_caption_preset_is_stable_for_every_occurrence(
    tmp_path: Path,
    count: int,
) -> None:
    source = tmp_path / "hunau-non-publishable-style-fixture.docx"
    output = tmp_path / "styled.docx"
    paragraphs = "".join(
        f'''<w:p w14:paraId="{index:08X}"><w:r><w:rPr><w:b/>
          <w:u w:val="double"/></w:rPr><w:t>表 {index}</w:t></w:r></w:p>'''
        for index in range(1, count + 1)
    )
    document = f'''<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
      <w:body>{paragraphs}</w:body></w:document>'''
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", document)
    registry, _ = _registry()
    preset = _preset(registry)
    receipt = select_complete_style_roles(
        actual_roles=_actual(preset),
        school_candidates=[],
        school_observation_set_digest="a" * 64,
        preset=preset,
        registry=registry,
    )
    contracts = compile_selected_style_contracts(
        receipt=receipt,
        template_sha256=sha256_file(source),
        registry=registry,
    )
    style = contracts.styles[0]
    manifest = {
        "occurrences": [
            {
                "occurrence_id": f"table-caption-{index}",
                "locator": f"/body/p[@paraId={index:08X}]",
                "style_contract_ref": {
                    "style_contract_id": style.style_contract_id,
                    "contract_digest": style.contract_digest,
                },
            }
            for index in range(1, count + 1)
        ]
    }

    materialize_style_contracts(
        input_docx=source,
        output_docx=output,
        contracts=contracts,
        occurrence_manifest=manifest,
    )
    validation = StyleContractValidator(contracts).validate(output, manifest)

    assert receipt.selections[0].source == "preset"
    assert validation.status == "passed"
    assert validation.as_dict()["counts"] == {
        "passed": count,
        "failed": 0,
        "unresolved": 0,
    }

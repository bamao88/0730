from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from docfit.styles.capture import (
    capture_template_style_observations,
    compile_school_style_contracts,
)
from docfit.styles.observation import (
    EffectiveState,
    PropertyObservation,
    SchoolEvidenceStatus,
)
from docfit.styles.profiles import (
    PropertyDefinition,
    StylePropertyProfile,
    StylePropertyProfileRegistry,
)
from docfit.tools.runtime import ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _registry() -> tuple[StylePropertyProfileRegistry, StylePropertyProfile]:
    definitions = (
        PropertyDefinition.build(
            property_path="run.latin_font",
            applicable_role_types={"paragraph"},
            resolver_sources=("run.font_ascii", "run.font_hansi"),
            canonicalization="equal_word_font_pair",
            materializer_targets=("run.font_ascii", "run.font_hansi"),
        ),
        PropertyDefinition.build(
            property_path="run.bold",
            applicable_role_types={"paragraph"},
            value_type="boolean",
            resolver_sources=("run.bold",),
            canonicalization="identity",
            materializer_targets=("run.bold",),
        ),
        PropertyDefinition.build(
            property_path="run.color",
            applicable_role_types={"paragraph"},
            resolver_sources=("run.color",),
            canonicalization="word_hex_color_v1",
            materializer_targets=("run.color",),
        ),
    )
    profile = StylePropertyProfile.build(
        role_type="paragraph",
        properties=definitions,
    )
    return StylePropertyProfileRegistry.build([profile]), profile


def _write_docx(path: Path) -> None:
    document = f'''<w:document xmlns:w="{W_NS}"><w:body>
      <w:sdt><w:sdtPr><w:tag w:val="body.paragraph.1"/></w:sdtPr><w:sdtContent>
        <w:p><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>
          <w:b w:val="0"/><w:color w:val="112233"/></w:rPr>
          <w:t>正文</w:t></w:r></w:p>
      </w:sdtContent></w:sdt>
    </w:body></w:document>'''
    styles = f'''<w:styles xmlns:w="{W_NS}">
      <w:style w:type="paragraph" w:default="1" w:styleId="Normal"/>
    </w:styles>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)


def _slot(profile: StylePropertyProfile) -> dict[str, object]:
    return {
        "field_id": "body.paragraph",
        "slot_id": "body.paragraph.1",
        "style_role_id": "style.body.paragraph",
        "style_role_type": "paragraph",
        "property_profile_ref": profile.ref().as_dict(),
        "locator": {
            "type": "content_control_tag",
            "value": "body.paragraph.1",
            "part": "word/document.xml",
        },
    }


def test_capture_returns_fixed_dual_axis_observation_and_complete_candidate(
    tmp_path: Path,
) -> None:
    document = tmp_path / "school.docx"
    _write_docx(document)
    registry, profile = _registry()

    capture = capture_template_style_observations(
        document,
        [_slot(profile)],
        registry=registry,
    )

    assert capture.status == "passed"
    assert capture.observation_set.profile_registry_digest == registry.registry_digest
    observation = capture.observation_set.observations[0]
    assert tuple(item.property_path for item in observation.properties) == (
        "run.latin_font",
        "run.bold",
        "run.color",
    )
    assert [item.effective_state for item in observation.properties] == [
        EffectiveState.VALUE,
        EffectiveState.VALUE,
        EffectiveState.VALUE,
    ]
    assert {item.school_evidence_status for item in observation.properties} == {
        SchoolEvidenceStatus.EXPLICIT_OR_VERIFIED
    }
    assert len(capture.school_candidates) == 1
    assert capture.known_gaps == ()
    assert capture.failed_observations == ()
    contracts = compile_school_style_contracts(capture, registry=registry)
    assert contracts is not None
    assert len(contracts.styles) == 1


def test_missing_expected_role_is_a_known_school_gap_not_observation_failure(
    tmp_path: Path,
) -> None:
    document = tmp_path / "school.docx"
    _write_docx(document)
    registry, profile = _registry()
    expected_table_caption = {
        "field_id": "body.table.caption",
        "slot_id": "body.table.caption.expected",
        "style_role_id": "style.body.table.caption",
        "style_role_type": "paragraph",
        "property_profile_ref": profile.ref().as_dict(),
    }

    capture = capture_template_style_observations(
        document,
        [_slot(profile)],
        expected_roles=[expected_table_caption],
        registry=registry,
    )

    assert capture.status == "passed_with_known_gaps"
    assert len(capture.observation_set.observations) == 2
    gap = next(
        item for item in capture.known_gaps if item["field_id"] == "body.table.caption"
    )
    assert gap["reason"] == "school_role_representative_missing"
    assert gap["property_paths"] == list(profile.property_paths)
    assert capture.failed_observations == ()
    assert all("preset" not in str(item).casefold() for item in capture.known_gaps)


def test_dual_axis_contract_rejects_none_without_none_semantics() -> None:
    _, profile = _registry()

    with pytest.raises(ToolFailure, match="no defined NONE semantics"):
        PropertyObservation.build(
            profile=profile,
            property_path="run.bold",
            effective_state=EffectiveState.NONE,
            school_evidence_status=SchoolEvidenceStatus.EXPLICIT_OR_VERIFIED,
        )


def test_resolver_unsupported_is_not_relabelled_as_a_school_gap(tmp_path: Path) -> None:
    document = tmp_path / "school.docx"
    _write_docx(document)
    unsupported = PropertyDefinition.build(
        property_path="paragraph.keep_with_next",
        applicable_role_types={"paragraph"},
    )
    profile = StylePropertyProfile.build(
        role_type="paragraph",
        properties=[unsupported],
    )
    registry = StylePropertyProfileRegistry.build([profile])

    capture = capture_template_style_observations(
        document,
        [_slot(profile)],
        registry=registry,
    )

    assert capture.status == "failed"
    assert capture.known_gaps == ()
    assert capture.failed_observations[0]["failed_properties"] == [
        "paragraph.keep_with_next"
    ]

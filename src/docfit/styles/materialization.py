"""Materialize immutable Style Contracts onto final DOCX occurrences."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

from docfit.styles.contracts import StyleContract, StyleContractSet
from docfit.tools.runtime import JsonObject, ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W = f"{{{W_NS}}}"
W14 = f"{{{W14_NS}}}"

SUPPORTED_MATERIALIZED_PROPERTIES = frozenset(
    {
        "run.font_ascii",
        "run.font_hansi",
        "run.font_east_asia",
        "run.font_complex_script",
        "run.font_ascii_theme",
        "run.font_hansi_theme",
        "run.font_east_asia_theme",
        "run.font_complex_script_theme",
        "run.font_size_pt",
        "run.bold",
        "run.italic",
        "run.color",
        "run.color_theme",
        "paragraph.alignment",
        "paragraph.space_before_pt",
        "paragraph.space_after_pt",
        "paragraph.line_spacing_rule",
        "paragraph.line_spacing_pt",
        "paragraph.line_value",
        "paragraph.page_break_before",
    }
)
_PARAGRAPH_PATH = re.compile(r"/body/p\[@paraId=([0-9A-Fa-f]{8})\]")


def materialize_style_contracts(
    *,
    input_docx: Path,
    output_docx: Path,
    contracts: StyleContractSet,
    occurrence_manifest: Mapping[str, Any],
) -> JsonObject:
    """Apply managed effective properties without mutating shared named styles."""

    if output_docx.exists():
        raise _failure(
            "style_materialization_output_exists",
            "Style materialization never overwrites an existing output snapshot.",
        )
    raw_occurrences = occurrence_manifest.get("occurrences")
    if not isinstance(raw_occurrences, Sequence) or isinstance(raw_occurrences, str | bytes):
        raise _failure(
            "style_occurrence_manifest_invalid",
            "Occurrence manifest requires an occurrences array.",
        )
    parts = _read_package(input_docx)
    roots: dict[str, ET.Element] = {}
    seen_ids: set[str] = set()
    seen_locators: set[str] = set()
    applied: list[JsonObject] = []
    for index, raw_occurrence in enumerate(raw_occurrences, start=1):
        if not isinstance(raw_occurrence, Mapping):
            raise _failure(
                "style_occurrence_manifest_invalid", "Every occurrence must be an object."
            )
        occurrence_id = raw_occurrence.get("occurrence_id")
        locator = raw_occurrence.get("locator")
        style_ref = raw_occurrence.get("style_contract_ref")
        if not isinstance(occurrence_id, str) or not occurrence_id:
            raise _failure(
                "style_occurrence_manifest_invalid",
                f"Occurrence {index} requires a non-empty occurrence_id.",
            )
        if occurrence_id in seen_ids:
            raise _failure(
                "style_occurrence_duplicate", f"Duplicate occurrence_id: {occurrence_id}."
            )
        if not isinstance(locator, str | Mapping) or not isinstance(style_ref, Mapping):
            raise _failure(
                "style_occurrence_manifest_invalid",
                f"{occurrence_id} requires locator and style_contract_ref.",
            )
        contract = contracts.resolve(style_ref)
        unsupported = sorted(set(contract.owned_properties) - SUPPORTED_MATERIALIZED_PROPERTIES)
        if unsupported:
            raise _failure(
                "style_property_unsupported",
                f"{contract.style_contract_id} owns unsupported properties: "
                + ", ".join(unsupported),
            )
        part, selected, locator_key = _resolve_locator(parts, roots, locator)
        if locator_key in seen_locators:
            raise _failure(
                "style_occurrence_duplicate",
                f"More than one Style Contract targets {locator_key}.",
            )
        seen_ids.add(occurrence_id)
        seen_locators.add(locator_key)
        paragraphs = _target_paragraphs(selected)
        if len(paragraphs) != 1:
            raise _failure(
                "style_occurrence_paragraph_not_unique",
                f"{occurrence_id} resolved to {len(paragraphs)} paragraphs; expected one.",
            )
        counts = _apply_contract(paragraphs[0], contract)
        roots[part] = roots[part]
        applied.append(
            {
                "occurrence_id": occurrence_id,
                "locator": dict(locator) if isinstance(locator, Mapping) else locator,
                "style_contract_ref": {
                    "style_contract_id": contract.style_contract_id,
                    "contract_digest": contract.contract_digest,
                },
                "managed_property_count": len(contract.owned_properties),
                **counts,
            }
        )

    for part, root in roots.items():
        parts[part] = _serialize(root)
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    _write_package(output_docx, parts)
    return {
        "schema_version": "docfit-style-materialization/v2",
        "style_contract_set_digest": contracts.digest,
        "occurrence_count": len(applied),
        "occurrences": applied,
    }


def _apply_contract(paragraph: ET.Element, contract: StyleContract) -> JsonObject:
    paragraph_paths = tuple(
        path for path in contract.owned_properties if path.startswith("paragraph.")
    )
    run_paths = tuple(path for path in contract.owned_properties if path.startswith("run."))
    if paragraph_paths:
        paragraph_properties = _properties(paragraph, "pPr")
        _apply_paragraph_properties(
            paragraph_properties,
            paragraph_paths,
            contract.effective_properties,
        )
    runs = list(paragraph.iter(f"{W}r"))
    if run_paths and not runs:
        raise _failure(
            "style_occurrence_run_missing",
            f"{contract.style_contract_id} owns run properties but the occurrence has no Word run.",
        )
    for run in runs:
        _apply_run_properties(
            _properties(run, "rPr"),
            run_paths,
            contract.effective_properties,
        )
    return {
        "paragraph_count": 1,
        "run_count": len(runs),
    }


def _apply_run_properties(
    properties: ET.Element,
    owned: Sequence[str],
    effective: Mapping[str, Any],
) -> None:
    font_attributes = {
        "run.font_ascii": "ascii",
        "run.font_hansi": "hAnsi",
        "run.font_east_asia": "eastAsia",
        "run.font_complex_script": "cs",
        "run.font_ascii_theme": "asciiTheme",
        "run.font_hansi_theme": "hAnsiTheme",
        "run.font_east_asia_theme": "eastAsiaTheme",
        "run.font_complex_script_theme": "cstheme",
    }
    for path, attribute in font_attributes.items():
        if path in owned:
            _set_attribute(properties, "rFonts", attribute, _text(effective[path], path))
    if "run.font_size_pt" in owned:
        size = _positive_number(effective["run.font_size_pt"], "run.font_size_pt")
        half_points = str(round(size * 2))
        _set_value(properties, "sz", half_points)
        _set_value(properties, "szCs", half_points)
    for path, tag, complex_tag in (
        ("run.bold", "b", "bCs"),
        ("run.italic", "i", "iCs"),
    ):
        if path in owned:
            encoded = "1" if _boolean(effective[path], path) else "0"
            _set_value(properties, tag, encoded)
            _set_value(properties, complex_tag, encoded)
    if "run.color" in owned:
        color = _text(effective["run.color"], "run.color")
        if color.casefold() != "auto" and re.fullmatch(r"[0-9A-Fa-f]{6}", color) is None:
            raise _failure("style_property_invalid", "run.color must be auto or six hex digits.")
        _set_attribute(properties, "color", "val", color.upper())
    if "run.color_theme" in owned:
        _set_attribute(
            properties,
            "color",
            "themeColor",
            _text(effective["run.color_theme"], "run.color_theme"),
        )


def _apply_paragraph_properties(
    properties: ET.Element,
    owned: Sequence[str],
    effective: Mapping[str, Any],
) -> None:
    if "paragraph.alignment" in owned:
        _set_value(
            properties,
            "jc",
            _text(effective["paragraph.alignment"], "paragraph.alignment"),
        )
    for path, attribute in (
        ("paragraph.space_before_pt", "before"),
        ("paragraph.space_after_pt", "after"),
    ):
        if path in owned:
            twips = str(round(_nonnegative_number(effective[path], path) * 20))
            _set_attribute(properties, "spacing", attribute, twips)
    line_pt = "paragraph.line_spacing_pt" in owned
    line_value = "paragraph.line_value" in owned
    if line_pt and line_value:
        raise _failure(
            "style_property_conflict",
            "A contract cannot own both paragraph.line_spacing_pt and paragraph.line_value.",
        )
    if line_pt:
        spacing = _positive_number(
            effective["paragraph.line_spacing_pt"], "paragraph.line_spacing_pt"
        )
        line = str(round(spacing * 20))
        _set_attribute(properties, "spacing", "line", line)
    if line_value:
        spacing = _positive_number(
            effective["paragraph.line_value"], "paragraph.line_value"
        )
        line = str(round(spacing * 240))
        _set_attribute(properties, "spacing", "line", line)
    if "paragraph.line_spacing_rule" in owned:
        _set_attribute(
            properties,
            "spacing",
            "lineRule",
            _text(effective["paragraph.line_spacing_rule"], "paragraph.line_spacing_rule"),
        )
    if "paragraph.page_break_before" in owned:
        encoded = "1" if _boolean(
            effective["paragraph.page_break_before"], "paragraph.page_break_before"
        ) else "0"
        _set_value(properties, "pageBreakBefore", encoded)


def _properties(owner: ET.Element, tag: str) -> ET.Element:
    found = owner.find(f"{W}{tag}")
    if found is not None:
        return found
    created = ET.Element(f"{W}{tag}")
    owner.insert(0, created)
    return created


def _set_value(parent: ET.Element, tag: str, value: str) -> None:
    _set_attribute(parent, tag, "val", value)


def _set_attribute(parent: ET.Element, tag: str, attribute: str, value: str) -> None:
    element = parent.find(f"{W}{tag}")
    if element is None:
        element = ET.SubElement(parent, f"{W}{tag}")
    element.set(f"{W}{attribute}", value)


def _resolve_locator(
    parts: Mapping[str, bytes],
    roots: dict[str, ET.Element],
    locator: str | Mapping[str, Any],
) -> tuple[str, ET.Element, str]:
    if isinstance(locator, Mapping):
        if locator.get("type") != "content_control_tag":
            raise _failure(
                "style_locator_unsupported", "Object locators require type=content_control_tag."
            )
        tag = locator.get("value")
        part = locator.get("part", "word/document.xml")
        if not isinstance(tag, str) or not tag or not isinstance(part, str):
            raise _failure(
                "style_locator_invalid", "Content-control locators require value and part."
            )
        root = _root(parts, roots, part)
        matches = []
        for control in root.iter(f"{W}sdt"):
            tag_element = control.find(f"{W}sdtPr/{W}tag")
            if tag_element is not None and tag_element.get(f"{W}val") == tag:
                matches.append(control)
        if len(matches) != 1:
            raise _failure(
                "style_locator_not_unique",
                f"Content-control tag {tag} matched {len(matches)} occurrences; expected one.",
            )
        return part, matches[0], f"{part}#content_control_tag:{tag}"
    match = _PARAGRAPH_PATH.fullmatch(locator)
    if match is None:
        raise _failure(
            "style_locator_unsupported",
            "Style materialization currently requires a paraId paragraph locator.",
        )
    part = "word/document.xml"
    root = _root(parts, roots, part)
    para_id = match.group(1).upper()
    matches = [
        paragraph
        for paragraph in root.iter(f"{W}p")
        if (paragraph.get(f"{W14}paraId") or "").upper() == para_id
    ]
    if len(matches) != 1:
        raise _failure(
            "style_locator_not_unique",
            f"Paragraph paraId {para_id} matched {len(matches)} occurrences; expected one.",
        )
    return part, matches[0], f"{part}#/body/p[@paraId={para_id}]"


def _target_paragraphs(selected: ET.Element) -> list[ET.Element]:
    if selected.tag == f"{W}p":
        return [selected]
    return list(selected.iter(f"{W}p"))


def _root(
    parts: Mapping[str, bytes], roots: dict[str, ET.Element], part: str
) -> ET.Element:
    if part in roots:
        return roots[part]
    try:
        root = ET.fromstring(parts[part])
    except (KeyError, ET.ParseError) as error:
        raise _failure("style_part_unreadable", f"The DOCX part {part} cannot be read.") from error
    roots[part] = root
    return root


def _read_package(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path.expanduser().resolve(strict=True)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile) as error:
        raise _failure("style_package_unreadable", "The DOCX package cannot be read.") from error


def _serialize(root: ET.Element) -> bytes:
    return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _write_package(path: Path, parts: Mapping[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(parts):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, parts[name])


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise _failure("style_property_invalid", f"{path} must be a non-empty string.")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _failure("style_property_invalid", f"{path} must be a boolean.")
    return value


def _positive_number(value: object, path: str) -> float:
    number = _number(value, path)
    if number <= 0:
        raise _failure("style_property_invalid", f"{path} must be positive.")
    return number


def _nonnegative_number(value: object, path: str) -> float:
    number = _number(value, path)
    if number < 0:
        raise _failure("style_property_invalid", f"{path} cannot be negative.")
    return number


def _number(value: object, path: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise _failure("style_property_invalid", f"{path} must be numeric.")
    return float(value)


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_style_contract_set", "inspect_document_again"),
    )

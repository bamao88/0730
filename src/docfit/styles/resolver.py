"""Resolve effective Word formatting with property-level provenance."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from xml.etree import ElementTree as ET

from docfit.tools.runtime import JsonObject, ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W = f"{{{W_NS}}}"
W14 = f"{{{W14_NS}}}"
_LOCATOR_TOKEN = re.compile(
    r"^(?P<tag>[A-Za-z0-9]+)(?:\[(?P<index>\d+)\]|"
    r"\[@paraId=(?:['\"])?(?P<para_id>[0-9A-Fa-f]+)(?:['\"])?\])?$"
)


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("inspect_document_again", "repair_occurrence_manifest"),
    )


def _attribute(element: ET.Element | None, name: str) -> str | None:
    return None if element is None else element.get(f"{W}{name}")


def _on_off(element: ET.Element | None) -> bool | None:
    if element is None:
        return None
    return _attribute(element, "val") not in {"0", "false", "off"}


def _half_points(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return int(value) / 2
    except ValueError:
        return None


def _twips(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return int(value) / 20
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class PropertyProvenance:
    """One contribution to an effective property."""

    source_kind: str
    source_id: str
    action: str
    value: str | float | bool | None

    def as_dict(self) -> JsonObject:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "action": self.action,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class EffectiveStyleResult:
    """Flattened effective properties plus complete contribution trails."""

    locator: str
    properties: Mapping[str, str | float | bool | None]
    provenance: Mapping[str, tuple[PropertyProvenance, ...]]
    coverage: frozenset[str]
    unresolved: tuple[str, ...]

    def value(self, property_path: str) -> str | float | bool | None:
        return self.properties.get(property_path)

    def as_dict(self) -> JsonObject:
        return {
            "locator": self.locator,
            "properties": dict(self.properties),
            "provenance": {
                key: [item.as_dict() for item in trail]
                for key, trail in self.provenance.items()
            },
            "coverage": {key: "resolved" for key in sorted(self.coverage)},
            "unresolved": list(self.unresolved),
        }


@dataclass(frozen=True, slots=True)
class _Instruction:
    path: str
    value: str | float | bool | None
    toggle: bool = False


@dataclass(frozen=True, slots=True)
class _NamedStyle:
    style_id: str
    style_type: str
    based_on: str | None
    is_default: bool
    run: tuple[_Instruction, ...]
    paragraph: tuple[_Instruction, ...]


class _Accumulator:
    def __init__(self) -> None:
        self.values: dict[str, str | float | bool | None] = {}
        self.trails: dict[str, list[PropertyProvenance]] = {}

    def apply(
        self,
        instructions: tuple[_Instruction, ...],
        *,
        source_kind: str,
        source_id: str,
        style_toggle: bool = False,
    ) -> None:
        for instruction in instructions:
            action = "set"
            value = instruction.value
            if instruction.toggle and style_toggle:
                if value is True:
                    value = not bool(self.values.get(instruction.path, False))
                    action = "toggle"
                else:
                    value = self.values.get(instruction.path, False)
                    action = "toggle_noop"
            self.values[instruction.path] = value
            self.trails.setdefault(instruction.path, []).append(
                PropertyProvenance(source_kind, source_id, action, value)
            )

    def derive(self, path: str, source_path: str) -> None:
        if path in self.values or source_path not in self.values:
            return
        value = self.values[source_path]
        self.values[path] = value
        self.trails[path] = [
            *self.trails.get(source_path, []),
            PropertyProvenance("word_font_fallback", source_path, "derive", value),
        ]

    def implicit(self, path: str, value: str | float | bool | None) -> None:
        if path in self.values:
            return
        self.values[path] = value
        self.trails[path] = [
            PropertyProvenance("word_implicit_default", "ECMA-376", "default", value)
        ]


class EffectiveStyleResolver:
    """Read-only effective formatting resolver for one DOCX snapshot."""

    def __init__(self, document: Path) -> None:
        try:
            self.document = document.expanduser().resolve(strict=True)
        except OSError as error:
            raise _failure(
                "effective_style_docx_unreadable", "The DOCX package cannot be read."
            ) from error
        try:
            with zipfile.ZipFile(self.document) as archive:
                self._parts = {
                    name: archive.read(name)
                    for name in archive.namelist()
                    if name.endswith(".xml")
                }
        except (OSError, zipfile.BadZipFile) as error:
            raise _failure(
                "effective_style_docx_unreadable", "The DOCX package cannot be read."
            ) from error
        if "word/document.xml" not in self._parts:
            raise _failure(
                "effective_style_document_missing", "The DOCX package has no word/document.xml."
            )
        self._roots: dict[str, ET.Element] = {}
        self._styles: dict[str, _NamedStyle] = {}
        self._default_paragraph_style: str | None = None
        self._default_character_style: str | None = None
        self._default_run: tuple[_Instruction, ...] = ()
        self._default_paragraph: tuple[_Instruction, ...] = ()
        if "word/styles.xml" in self._parts:
            self._read_styles(self._root("word/styles.xml"))

    def resolve(self, locator: str | Mapping[str, Any]) -> EffectiveStyleResult:
        part, locator_text, selected = self._resolve_locator(locator)
        root = self._root(part)
        parents = {child: parent for parent in root.iter() for child in parent}
        paragraph = self._paragraph_for(selected, parents)
        run = self._run_for(selected, paragraph)
        accumulator = _Accumulator()
        unresolved: list[str] = []
        accumulator.apply(
            self._default_run,
            source_kind="doc_defaults",
            source_id="word/styles.xml#docDefaults/rPrDefault",
        )
        accumulator.apply(
            self._default_paragraph,
            source_kind="doc_defaults",
            source_id="word/styles.xml#docDefaults/pPrDefault",
        )

        paragraph_properties = paragraph.find(f"{W}pPr")
        paragraph_style = _attribute(
            None
            if paragraph_properties is None
            else paragraph_properties.find(f"{W}pStyle"),
            "val",
        )
        if paragraph_style is None:
            paragraph_style = self._default_paragraph_style
        for style in self._style_chain(paragraph_style, "paragraph", unresolved):
            accumulator.apply(
                style.paragraph,
                source_kind="paragraph_style",
                source_id=style.style_id,
            )
            accumulator.apply(
                style.run,
                source_kind="paragraph_style",
                source_id=style.style_id,
                style_toggle=True,
            )

        if paragraph_properties is not None:
            accumulator.apply(
                _paragraph_properties(paragraph_properties),
                source_kind="paragraph_direct",
                source_id=locator_text,
            )
            accumulator.apply(
                _run_properties(paragraph_properties.find(f"{W}rPr")),
                source_kind="paragraph_mark_direct",
                source_id=locator_text,
            )

        run_properties = None if run is None else run.find(f"{W}rPr")
        run_style = _attribute(
            None if run_properties is None else run_properties.find(f"{W}rStyle"), "val"
        )
        if run_style is None:
            run_style = self._default_character_style
        if run_style is not None:
            for style in self._style_chain(run_style, "character", unresolved):
                accumulator.apply(
                    style.run,
                    source_kind="character_style",
                    source_id=style.style_id,
                    style_toggle=True,
                )
        if run_properties is not None:
            accumulator.apply(
                _run_properties(run_properties),
                source_kind="run_direct",
                source_id=locator_text,
            )

        accumulator.derive("run.font_ascii", "run.font_hansi")
        accumulator.derive("run.font_hansi", "run.font_ascii")
        accumulator.implicit("run.bold", False)
        accumulator.implicit("run.italic", False)
        accumulator.implicit("run.color", "auto")
        accumulator.implicit("paragraph.space_before_pt", 0.0)
        accumulator.implicit("paragraph.space_after_pt", 0.0)
        accumulator.implicit("paragraph.page_break_before", False)
        properties = MappingProxyType(dict(sorted(accumulator.values.items())))
        provenance = MappingProxyType(
            {
                key: tuple(accumulator.trails[key])
                for key in sorted(accumulator.trails)
            }
        )
        return EffectiveStyleResult(
            locator=locator_text,
            properties=properties,
            provenance=provenance,
            coverage=frozenset(properties),
            unresolved=tuple(dict.fromkeys(unresolved)),
        )

    def _root(self, part: str) -> ET.Element:
        if part in self._roots:
            return self._roots[part]
        payload = self._parts.get(part)
        if payload is None:
            raise _failure("effective_style_part_missing", f"The DOCX has no {part} part.")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            raise _failure(
                "effective_style_xml_invalid", f"The DOCX part {part} is not valid XML."
            ) from error
        self._roots[part] = root
        return root

    def _read_styles(self, root: ET.Element) -> None:
        defaults = root.find(f"{W}docDefaults")
        if defaults is not None:
            self._default_run = _run_properties(defaults.find(f"{W}rPrDefault/{W}rPr"))
            self._default_paragraph = _paragraph_properties(
                defaults.find(f"{W}pPrDefault/{W}pPr")
            )
        for style_element in root.findall(f"{W}style"):
            style_id = _attribute(style_element, "styleId")
            style_type = _attribute(style_element, "type")
            if style_id is None or style_type not in {"paragraph", "character"}:
                continue
            item = _NamedStyle(
                style_id=style_id,
                style_type=style_type,
                based_on=_attribute(style_element.find(f"{W}basedOn"), "val"),
                is_default=_on_off_attribute(style_element, "default"),
                run=_run_properties(style_element.find(f"{W}rPr")),
                paragraph=_paragraph_properties(style_element.find(f"{W}pPr")),
            )
            self._styles[style_id] = item
            if item.is_default and item.style_type == "paragraph":
                self._default_paragraph_style = item.style_id
            if item.is_default and item.style_type == "character":
                self._default_character_style = item.style_id

    def _style_chain(
        self, style_id: str | None, expected_type: str, unresolved: list[str]
    ) -> tuple[_NamedStyle, ...]:
        if style_id is None:
            return ()
        chain: list[_NamedStyle] = []
        seen: set[str] = set()
        current: str | None = style_id
        while current is not None:
            if current in seen:
                unresolved.append(f"style inheritance cycle at {current}")
                return ()
            seen.add(current)
            style = self._styles.get(current)
            if style is None:
                unresolved.append(f"missing {expected_type} style {current}")
                break
            if style.style_type != expected_type:
                unresolved.append(
                    f"style {current} has type {style.style_type}, expected {expected_type}"
                )
                break
            chain.append(style)
            current = style.based_on
        chain.reverse()
        return tuple(chain)

    def _resolve_locator(
        self, locator: str | Mapping[str, Any]
    ) -> tuple[str, str, ET.Element]:
        if isinstance(locator, Mapping):
            locator_type = locator.get("type")
            if locator_type != "content_control_tag":
                raise _failure(
                    "effective_style_locator_unsupported",
                    "Locator objects must use type=content_control_tag.",
                )
            value = locator.get("value")
            part = locator.get("part", "word/document.xml")
            if not isinstance(value, str) or not isinstance(part, str):
                raise _failure(
                    "effective_style_locator_invalid",
                    "A content-control locator requires string value and part fields.",
                )
            selected = self._content_control(part, value)
            return part, f"content_control_tag:{value}", selected
        if not isinstance(locator, str) or not locator.startswith("/"):
            raise _failure(
                "effective_style_locator_invalid", "A locator must be an absolute OOXML path."
            )
        part = "word/document.xml"
        selected = self._path_element(self._root(part), locator)
        return part, locator, selected

    def _content_control(self, part: str, tag: str) -> ET.Element:
        matches: list[ET.Element] = []
        for control in self._root(part).iter(f"{W}sdt"):
            tag_element = control.find(f"{W}sdtPr/{W}tag")
            if _attribute(tag_element, "val") == tag:
                matches.append(control)
        if len(matches) != 1:
            raise _failure(
                "effective_style_content_control_not_unique",
                f"content-control tag {tag} matched {len(matches)} objects; expected one.",
            )
        return matches[0]

    @staticmethod
    def _path_element(root: ET.Element, locator: str) -> ET.Element:
        tokens = [item for item in locator.split("/") if item]
        current = root
        if tokens and tokens[0] == "document":
            tokens.pop(0)
        for raw in tokens:
            match = _LOCATOR_TOKEN.fullmatch(raw)
            if match is None:
                raise _failure(
                    "effective_style_locator_unsupported", f"Unsupported locator token: {raw}."
                )
            tag = match.group("tag")
            candidates = list(current.findall(f"{W}{tag}"))
            para_id = match.group("para_id")
            if para_id is not None:
                candidates = [
                    item
                    for item in candidates
                    if (item.get(f"{W14}paraId") or "").casefold() == para_id.casefold()
                ]
                index = 1
            else:
                index = int(match.group("index") or "1")
            if index < 1 or index > len(candidates):
                raise _failure(
                    "effective_style_locator_not_found", f"Locator does not exist: {locator}."
                )
            current = candidates[index - 1]
        return current

    @staticmethod
    def _paragraph_for(
        selected: ET.Element, parents: Mapping[ET.Element, ET.Element]
    ) -> ET.Element:
        current: ET.Element | None = selected
        while current is not None:
            if current.tag == f"{W}p":
                return current
            current = parents.get(current)
        paragraphs = list(selected.iter(f"{W}p"))
        if len(paragraphs) != 1:
            raise _failure(
                "effective_style_paragraph_not_unique",
                "The occurrence must resolve to exactly one paragraph.",
            )
        return paragraphs[0]

    @staticmethod
    def _run_for(selected: ET.Element, paragraph: ET.Element) -> ET.Element | None:
        if selected.tag == f"{W}r":
            return selected
        runs = list(selected.iter(f"{W}r")) if selected is not paragraph else list(
            paragraph.iter(f"{W}r")
        )
        return runs[0] if runs else None


def _on_off_attribute(element: ET.Element, name: str) -> bool:
    value = element.get(f"{W}{name}")
    return value not in {None, "0", "false", "off"}


def _run_properties(properties: ET.Element | None) -> tuple[_Instruction, ...]:
    if properties is None:
        return ()
    result: list[_Instruction] = []
    fonts = properties.find(f"{W}rFonts")
    if fonts is not None:
        for xml_name, property_name in (
            ("ascii", "run.font_ascii"),
            ("hAnsi", "run.font_hansi"),
            ("eastAsia", "run.font_east_asia"),
            ("cs", "run.font_complex_script"),
            ("asciiTheme", "run.font_ascii_theme"),
            ("hAnsiTheme", "run.font_hansi_theme"),
            ("eastAsiaTheme", "run.font_east_asia_theme"),
            ("cstheme", "run.font_complex_script_theme"),
        ):
            value = _attribute(fonts, xml_name)
            if value is not None:
                result.append(_Instruction(property_name, value))
    size = _half_points(_attribute(properties.find(f"{W}sz"), "val"))
    if size is not None:
        result.append(_Instruction("run.font_size_pt", size))
    for tag, path in (("b", "run.bold"), ("i", "run.italic")):
        element = properties.find(f"{W}{tag}")
        toggle_value = _on_off(element)
        if toggle_value is not None:
            result.append(_Instruction(path, toggle_value, toggle=True))
    color = properties.find(f"{W}color")
    if color is not None:
        color_value = _attribute(color, "val")
        if color_value is not None:
            result.append(_Instruction("run.color", color_value.upper()))
        theme = _attribute(color, "themeColor")
        if theme is not None:
            result.append(_Instruction("run.color_theme", theme))
    return tuple(result)


def _paragraph_properties(properties: ET.Element | None) -> tuple[_Instruction, ...]:
    if properties is None:
        return ()
    result: list[_Instruction] = []
    alignment = _attribute(properties.find(f"{W}jc"), "val")
    if alignment is not None:
        result.append(_Instruction("paragraph.alignment", alignment))
    spacing = properties.find(f"{W}spacing")
    if spacing is not None:
        before = _twips(_attribute(spacing, "before"))
        after = _twips(_attribute(spacing, "after"))
        if before is not None:
            result.append(_Instruction("paragraph.space_before_pt", before))
        if after is not None:
            result.append(_Instruction("paragraph.space_after_pt", after))
        raw_line = _attribute(spacing, "line")
        line_rule = _attribute(spacing, "lineRule") or ("auto" if raw_line is not None else None)
        if line_rule is not None:
            result.append(_Instruction("paragraph.line_spacing_rule", line_rule))
        if raw_line is not None:
            try:
                numeric_line = int(raw_line)
            except ValueError:
                numeric_line = None
            if numeric_line is not None and line_rule in {"exact", "atLeast"}:
                result.append(_Instruction("paragraph.line_spacing_pt", numeric_line / 20))
            elif numeric_line is not None:
                result.append(_Instruction("paragraph.line_value", numeric_line / 240))
    page_break = _on_off(properties.find(f"{W}pageBreakBefore"))
    if page_break is not None:
        result.append(_Instruction("paragraph.page_break_before", page_break))
    return tuple(result)

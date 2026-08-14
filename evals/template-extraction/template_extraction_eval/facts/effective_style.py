"""Resolve DOCX defaults, named styles, direct formatting, containers, and page facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

from ..models import EffectiveStyle
from .reader import DocxPackage

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


class StyleAnalysisError(ValueError):
    pass


def style_differences(
    expected: EffectiveStyle,
    actual: EffectiveStyle,
    tolerances: dict[str, float],
) -> tuple[tuple[str, Any, Any], ...]:
    """Compare only expected style properties using shared numeric tolerances."""

    differences: list[tuple[str, Any, Any]] = []
    for group_name in ("font", "paragraph", "container", "page"):
        expected_group = getattr(expected, group_name)
        actual_group = getattr(actual, group_name)
        for name, expected_value in expected_group.items():
            actual_value = actual_group.get(name)
            if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
                if not isinstance(actual_value, (int, float)) or isinstance(actual_value, bool):
                    differences.append((f"{group_name}.{name}", expected_value, actual_value))
                    continue
                tolerance_key = "font_size_pt" if name == "size_pt" else "distance_pt"
                tolerance = tolerances.get(tolerance_key, 0.0)
                if abs(float(expected_value) - float(actual_value)) > tolerance:
                    differences.append((f"{group_name}.{name}", expected_value, actual_value))
            elif expected_value != actual_value:
                differences.append((f"{group_name}.{name}", expected_value, actual_value))
    return tuple(differences)


@dataclass(frozen=True)
class _NamedStyle:
    style_id: str
    based_on: str | None
    run: dict[str, Any]
    paragraph: dict[str, Any]


def _attribute(element: ElementTree.Element | None, name: str) -> str | None:
    if element is None:
        return None
    return element.get(f"{W}{name}")


def _on_off(element: ElementTree.Element | None) -> bool | None:
    if element is None:
        return None
    value = _attribute(element, "val")
    return value not in {"0", "false", "off"}


def _half_points(value: str | None) -> float | None:
    return None if value is None else int(value) / 2


def _twips(value: str | None) -> float | None:
    return None if value is None else int(value) / 20


def _run_properties(run_properties: ElementTree.Element | None) -> dict[str, Any]:
    if run_properties is None:
        return {}
    fonts = run_properties.find(f"{W}rFonts")
    result: dict[str, Any] = {}
    if fonts is not None:
        result.update(
            {
                "east_asia": _attribute(fonts, "eastAsia"),
                "latin": _attribute(fonts, "ascii") or _attribute(fonts, "hAnsi"),
            }
        )
    size = _half_points(_attribute(run_properties.find(f"{W}sz"), "val"))
    if size is not None:
        result["size_pt"] = size
    bold = _on_off(run_properties.find(f"{W}b"))
    if bold is not None:
        result["bold"] = bold
    italic = _on_off(run_properties.find(f"{W}i"))
    if italic is not None:
        result["italic"] = italic
    color = _attribute(run_properties.find(f"{W}color"), "val")
    if color is not None and color != "auto":
        result["color"] = color.upper()
    return result


def _paragraph_properties(properties: ElementTree.Element | None) -> dict[str, Any]:
    if properties is None:
        return {}
    result: dict[str, Any] = {}
    alignment = _attribute(properties.find(f"{W}jc"), "val")
    if alignment is not None:
        result["alignment"] = alignment
    indentation = properties.find(f"{W}ind")
    if indentation is not None:
        for xml_name, fact_name in (
            ("firstLine", "first_line_indent_pt"),
            ("left", "left_indent_pt"),
            ("right", "right_indent_pt"),
        ):
            fact = _twips(_attribute(indentation, xml_name))
            if fact is not None:
                result[fact_name] = fact
    spacing = properties.find(f"{W}spacing")
    if spacing is not None:
        for xml_name, fact_name in (
            ("before", "space_before_pt"),
            ("after", "space_after_pt"),
        ):
            fact = _twips(_attribute(spacing, xml_name))
            if fact is not None:
                result[fact_name] = fact
        rule = _attribute(spacing, "lineRule") or "auto"
        result["line_spacing_rule"] = rule
        line = _attribute(spacing, "line")
        if line is not None and rule in {"exact", "atLeast"}:
            result["line_spacing_pt"] = _twips(line)
        elif line is not None:
            result["line_multiple"] = int(line) / 240
    return result


def _merge(*values: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        result.update({key: item for key, item in value.items() if item is not None})
    return result


class EffectiveStyleAnalyzer:
    def __init__(self, package: DocxPackage) -> None:
        self._package = package
        self._default_run: dict[str, Any] = {}
        self._default_paragraph: dict[str, Any] = {}
        self._styles: dict[str, _NamedStyle] = {}
        if "word/styles.xml" in package.parts:
            self._read_styles(package.xml("word/styles.xml"))
        self._page = self._read_page(package.xml("word/document.xml"))

    def _read_styles(self, root: ElementTree.Element) -> None:
        defaults = root.find(f"{W}docDefaults")
        if defaults is not None:
            run_default = defaults.find(f"{W}rPrDefault/{W}rPr")
            paragraph_default = defaults.find(f"{W}pPrDefault/{W}pPr")
            self._default_run = _run_properties(run_default)
            self._default_paragraph = _paragraph_properties(paragraph_default)
        for style in root.findall(f"{W}style"):
            style_id = _attribute(style, "styleId")
            if style_id is None:
                continue
            based_on = _attribute(style.find(f"{W}basedOn"), "val")
            self._styles[style_id] = _NamedStyle(
                style_id=style_id,
                based_on=based_on,
                run=_run_properties(style.find(f"{W}rPr")),
                paragraph=_paragraph_properties(style.find(f"{W}pPr")),
            )

    def _style_chain(self, style_id: str | None) -> tuple[_NamedStyle, ...]:
        if style_id is None:
            return ()
        chain: list[_NamedStyle] = []
        seen: set[str] = set()
        current: str | None = style_id
        while current is not None:
            if current in seen:
                raise StyleAnalysisError(f"named style inheritance cycle at {current}")
            seen.add(current)
            style = self._styles.get(current)
            if style is None:
                break
            chain.append(style)
            current = style.based_on
        chain.reverse()
        return tuple(chain)

    def _read_page(self, document: ElementTree.Element) -> dict[str, Any]:
        section = document.find(f".//{W}sectPr")
        if section is None:
            return {}
        result: dict[str, Any] = {}
        page_size = section.find(f"{W}pgSz")
        if page_size is not None:
            width = _twips(_attribute(page_size, "w"))
            height = _twips(_attribute(page_size, "h"))
            if width is not None:
                result["page_width_pt"] = width
            if height is not None:
                result["page_height_pt"] = height
        margins = section.find(f"{W}pgMar")
        if margins is not None:
            for xml_name, fact_name in (
                ("top", "margin_top_pt"),
                ("bottom", "margin_bottom_pt"),
                ("left", "margin_left_pt"),
                ("right", "margin_right_pt"),
            ):
                fact = _twips(_attribute(margins, xml_name))
                if fact is not None:
                    result[fact_name] = fact
        return result

    def _container_style(self, cell: ElementTree.Element | None) -> dict[str, Any]:
        if cell is None:
            return {}
        properties = cell.find(f"{W}tcPr")
        if properties is None:
            return {}
        result: dict[str, Any] = {}
        vertical = _attribute(properties.find(f"{W}vAlign"), "val")
        if vertical is not None:
            result["vertical_alignment"] = vertical
        margins = properties.find(f"{W}tcMar")
        if margins is not None:
            for xml_name, fact_name in (
                ("left", "cell_margin_left_pt"),
                ("right", "cell_margin_right_pt"),
                ("top", "cell_margin_top_pt"),
                ("bottom", "cell_margin_bottom_pt"),
            ):
                fact = _twips(_attribute(margins.find(f"{W}{xml_name}"), "w"))
                if fact is not None:
                    result[fact_name] = fact
        return result

    def effective_style(
        self,
        paragraph: ElementTree.Element,
        run: ElementTree.Element | None = None,
        *,
        cell: ElementTree.Element | None = None,
    ) -> EffectiveStyle:
        paragraph_properties = paragraph.find(f"{W}pPr")
        paragraph_style_id = _attribute(
            None if paragraph_properties is None else paragraph_properties.find(f"{W}pStyle"),
            "val",
        )
        paragraph_chain = self._style_chain(paragraph_style_id)
        run_properties = None if run is None else run.find(f"{W}rPr")
        run_style_id = _attribute(
            None if run_properties is None else run_properties.find(f"{W}rStyle"),
            "val",
        )
        run_chain = self._style_chain(run_style_id)
        inherited_run = _merge(*(style.run for style in paragraph_chain))
        inherited_paragraph = _merge(*(style.paragraph for style in paragraph_chain))
        explicit_run_style = _merge(*(style.run for style in run_chain))
        paragraph_run = _run_properties(
            None if paragraph_properties is None else paragraph_properties.find(f"{W}rPr")
        )
        font = _merge(
            self._default_run,
            inherited_run,
            paragraph_run,
            explicit_run_style,
            _run_properties(run_properties),
        )
        font.setdefault("east_asia", None)
        font.setdefault("latin", None)
        font.setdefault("size_pt", None)
        font.setdefault("bold", False)
        font.setdefault("italic", False)
        font.setdefault("color", None)
        paragraph_facts = _merge(
            self._default_paragraph,
            inherited_paragraph,
            _paragraph_properties(paragraph_properties),
        )
        if "line_multiple" in paragraph_facts:
            multiple = float(paragraph_facts.pop("line_multiple"))
            size = font.get("size_pt")
            paragraph_facts["line_spacing_pt"] = None if size is None else size * multiple
        paragraph_facts.setdefault("alignment", None)
        paragraph_facts.setdefault("first_line_indent_pt", 0.0)
        paragraph_facts.setdefault("left_indent_pt", 0.0)
        paragraph_facts.setdefault("right_indent_pt", 0.0)
        paragraph_facts.setdefault("space_before_pt", 0.0)
        paragraph_facts.setdefault("space_after_pt", 0.0)
        return EffectiveStyle(
            font=font,
            paragraph=paragraph_facts,
            container=self._container_style(cell),
            page=dict(self._page),
        )

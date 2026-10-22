"""Keep the visible width of a school's underlined blank fill area."""

from __future__ import annotations

import unicodedata


def _display_width_units(value: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        for character in value
    )


def preserve_underlined_fill_width(
    *, source_text: str, placeholder_text: str, underlined: bool
) -> str:
    """Retain blank underline geometry while exposing a visible field marker."""

    if source_text.strip() or not underlined:
        return placeholder_text
    remaining = max(
        0, _display_width_units(source_text) - _display_width_units(placeholder_text)
    )
    return f"{placeholder_text}{' ' * remaining}"

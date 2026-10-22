"""Layout placeholder normalization for template materialization."""

from __future__ import annotations

import re

from docfit.template.materialization.models import MaterializationContextKind


def convert_inter_character_boxes_to_spacing(text: str) -> str:
    if "□" not in text:
        return text
    stripped = text.strip()
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", stripped))
    has_intercharacter_gap = re.search(r"[\u4e00-\u9fff]□+[\u4e00-\u9fff]", stripped)
    if (
        2 <= cjk_count <= 12
        and has_intercharacter_gap is not None
        and re.fullmatch(r"[\u4e00-\u9fff□\s　]+", stripped)
    ):
        return text.replace("□", "　")
    return text


def normalize_square_placeholders(text: str, *, context_kind: str | None) -> str:
    if context_kind == MaterializationContextKind.FIXED_HEADING.value:
        return convert_inter_character_boxes_to_spacing(text)
    return text

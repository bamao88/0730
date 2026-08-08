"""Code-owned semantic object types for reusable thesis body structures.

The catalog is deliberately not a document checklist.  It describes the small
set of object meanings that the Agent may assign to the school objects it is
currently looking at.  The Agent owns the semantic judgment; the Tool only
checks that the requested Word object can physically represent that type.
"""

from __future__ import annotations

from dataclasses import dataclass

from docfit.tools.runtime import JsonObject, ToolFailure


@dataclass(frozen=True, slots=True)
class SemanticObjectType:
    type_id: str
    role: str
    parent_type: str | None
    allowed_word_kinds: frozenset[str]
    repeatable: bool = True
    toc_level: int | None = None

    def public(self) -> JsonObject:
        value: JsonObject = {
            "type_id": self.type_id,
            "role": self.role,
            "repeatable": self.repeatable,
        }
        if self.parent_type is not None:
            value["parent_type"] = self.parent_type
        if self.toc_level is not None:
            value["toc_level"] = self.toc_level
        return value


_TEXT_BLOCK = frozenset({"paragraph"})
BODY_CHAPTER_CORE_MEMBER_TYPES = (
    "body.heading.level1",
    "body.heading.level2",
    "body.heading.level3",
    "body.paragraph",
)
_BODY_TYPES = {
    item.type_id: item
    for item in (
        SemanticObjectType(
            "body.chapters",
            "repeatable_structure",
            None,
            frozenset({"paragraph", "table"}),
        ),
        SemanticObjectType(
            "body.heading.level1", "heading", "body.chapters", _TEXT_BLOCK, toc_level=1
        ),
        SemanticObjectType(
            "body.heading.level2", "heading", "body.chapters", _TEXT_BLOCK, toc_level=2
        ),
        SemanticObjectType(
            "body.heading.level3", "heading", "body.chapters", _TEXT_BLOCK, toc_level=3
        ),
        SemanticObjectType(
            "body.heading.level4", "heading", "body.chapters", _TEXT_BLOCK, toc_level=4
        ),
        SemanticObjectType(
            "body.heading.level5", "heading", "body.chapters", _TEXT_BLOCK, toc_level=5
        ),
        SemanticObjectType("body.paragraph", "text_block", "body.chapters", _TEXT_BLOCK),
        SemanticObjectType("body.numbered_list_item", "list_item", "body.chapters", _TEXT_BLOCK),
        SemanticObjectType("body.block_quote", "text_block", "body.chapters", _TEXT_BLOCK),
        SemanticObjectType(
            "body.figure", "composite_block", "body.chapters", frozenset({"paragraph"})
        ),
        SemanticObjectType("body.figure.caption", "caption", "body.chapters", _TEXT_BLOCK),
        SemanticObjectType(
            "body.equation", "composite_block", "body.chapters", frozenset({"paragraph"})
        ),
        SemanticObjectType("body.table", "composite_block", "body.chapters", frozenset({"table"})),
        SemanticObjectType("body.table.caption", "caption", "body.chapters", _TEXT_BLOCK),
        SemanticObjectType("body.table.note", "text_block", "body.chapters", _TEXT_BLOCK),
        SemanticObjectType(
            "body.landscape_block",
            "section_block",
            "body.chapters",
            frozenset({"paragraph", "table"}),
            repeatable=False,
        ),
    )
}


def semantic_object_type(type_id: str) -> SemanticObjectType | None:
    return _BODY_TYPES.get(type_id)


def require_body_structure_type(type_id: str) -> SemanticObjectType:
    value = semantic_object_type(type_id)
    if value is None or value.parent_type is not None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_type_invalid",
            message="materialize_structure requires the body.chapters structure type.",
        )
    return value


def require_body_member_type(type_id: str, word_kind: str) -> SemanticObjectType:
    value = semantic_object_type(type_id)
    if value is None or value.parent_type != "body.chapters":
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_member_type_invalid",
            message="Each structure member requires one supported body semantic type.",
        )
    if word_kind not in value.allowed_word_kinds:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_member_word_kind_invalid",
            message=(
                f"The selected {word_kind} object cannot represent semantic type "
                f"{type_id}. Select its containing school template object instead."
            ),
        )
    return value


def require_complete_body_structure(member_type_ids: list[str]) -> None:
    """Enforce the minimum reusable chapter grammar after Agent classification.

    The Agent still decides which school objects carry these meanings.  Once it
    requests ``body.chapters``, the Tool must not accept a fragment such as two
    adjacent headings as though it were a complete repeatable chapter.
    """

    missing = [
        type_id for type_id in BODY_CHAPTER_CORE_MEMBER_TYPES if type_id not in member_type_ids
    ]
    if missing:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_core_members_missing",
            message=(
                "A reusable body.chapters block must include at least one H1, H2, H3, "
                "and ordinary body paragraph. Missing semantic member types: "
                f"{', '.join(missing)}. Keep the members in document order and classify "
                "instruction/sample prose by its demonstrated role rather than by an "
                "unreliable Word style name. Members do not need to be adjacent."
            ),
        )

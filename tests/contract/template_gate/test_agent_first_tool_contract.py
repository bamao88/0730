from __future__ import annotations

from docfit.tools import docx_edit, docx_validate


def test_template_mechanics_are_actions_on_the_stable_docx_edit_tool() -> None:
    actions = set(
        docx_edit.input_schema["properties"]["operations"]["items"]["properties"][
            "action"
        ]["enum"]
    )

    assert {
        "clear_content",
        "remove_object",
        "materialize_slot",
        "materialize_structure",
        "normalize_effective_format",
        "refresh_toc",
        "ensure_page_start",
    } <= actions
    assert "field_registry" in docx_edit.input_schema["properties"]
    assert "members" in docx_edit.input_schema["properties"]["operations"]["items"][
        "properties"
    ]
    assert "toc_entries" in docx_edit.input_schema["properties"]["operations"]["items"][
        "properties"
    ]


def test_validate_accepts_agent_owned_structured_visual_evidence() -> None:
    visual_schema = docx_validate.input_schema["properties"]["visual_review"]

    assert set(visual_schema["type"]) == {"string", "object"}
    assert docx_validate.input_schema["properties"]["required_visual_coverage"]["const"] == (
        "all_final_pages"
    )

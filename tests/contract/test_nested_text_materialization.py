"""Accepted character spans must work inside supported inline Word wrappers."""

import zipfile
from xml.etree import ElementTree as ET

import pytest

from docfit.template.materialization import materialize_template_from_semantics
from docfit.tools.word_xml import visible_word_text
from tests.contract.test_exact_object_cleanup import W, case, part


def _control(content: str, identity: int) -> str:
    return (
        f'<w:sdt><w:sdtPr><w:id w:val="{identity}"/></w:sdtPr>'
        f"<w:sdtContent>{content}</w:sdtContent></w:sdt>"
    )


def _candidate(tmp_path, wrapper: str, locator: str, action: str):
    parts = [part("fixed_label", "Keep")]
    if action == "fill":
        parts.append(part("fill_slot", "Value", field_id="thesis.title.zh"))
    else:
        parts.append(part("cleanup", "Value"))
    source, registry, inventory, review = case(
        tmp_path,
        f"<w:p>{wrapper}</w:p>",
        [("text", locator, "KeepValue", parts)],
    )
    candidate = tmp_path / "candidate.docx"
    materialize_template_from_semantics(
        source_docx=source,
        output_docx=candidate,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    with zipfile.ZipFile(candidate) as archive:
        return ET.fromstring(archive.read("word/document.xml"))


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("action", ["fill", "cleanup"])
def test_partial_control_edit_keeps_outer_control_and_fixed_text(tmp_path, nested, action):
    runs = "<w:r><w:t>Keep</w:t></w:r><w:r><w:t>Value</w:t></w:r>"
    inner = _control(runs, 2) if nested else runs
    xml = _control(inner, 1)
    locator = "/body/p[1]/sdt[1]/sdtContent[1]/sdt[1]" if nested else "/body/p[1]/sdt[1]"
    root = _candidate(tmp_path, xml, locator, action)
    outer = root.find(f".//{W}p/{W}sdt")
    assert outer is not None
    assert outer.find(f"{W}sdtPr/{W}id").get(W + "val") == "1"
    assert visible_word_text(outer).startswith("Keep")
    if action == "fill":
        slots = [
            node for node in outer.iter(W + "sdt")
            if node.find(f"{W}sdtPr/{W}tag") is not None
        ]
        assert len(slots) == 1
        assert slots[0] is not outer
        assert visible_word_text(slots[0]) == "【填】"
        assert visible_word_text(outer) == "Keep【填】"
    else:
        assert visible_word_text(outer) == "Keep"
        assert outer.find(f"{W}sdtPr/{W}tag") is None


@pytest.mark.parametrize("action", ["fill", "cleanup"])
def test_hyperlink_edit_stays_inside_link(tmp_path, action):
    xml = (
        '<w:hyperlink w:anchor="target">'
        "<w:r><w:t>Keep</w:t></w:r><w:r><w:t>Value</w:t></w:r>"
        "</w:hyperlink>"
    )
    root = _candidate(tmp_path, xml, "/body/p[1]/hyperlink[1]", action)
    link = root.find(f".//{W}hyperlink")
    assert link is not None and link.get(W + "anchor") == "target"
    paragraph = root.find(f".//{W}p")
    assert paragraph is not None
    assert list(paragraph) == [link]
    if action == "fill":
        slot = link.find(f"{W}sdt")
        assert slot is not None
        assert slot.find(f"{W}sdtPr/{W}alias").get(W + "val") == "thesis.title.zh"
        assert visible_word_text(link) == "Keep【填】"
    else:
        assert visible_word_text(link) == "Keep"


def test_direct_and_wrapped_edits_in_one_paragraph_keep_their_own_containers(tmp_path):
    xml = (
        '<w:p><w:r><w:t>Outside</w:t></w:r>'
        '<w:hyperlink w:anchor="target"><w:r><w:t>Inside</w:t></w:r></w:hyperlink>'
        '<w:r><w:t>End</w:t></w:r></w:p>'
    )
    source, registry, inventory, review = case(
        tmp_path,
        xml,
        [
            ("text", "/body/p[1]/r[1]", "Outside", [part("cleanup", "Outside")]),
            (
                "text", "/body/p[1]/hyperlink[1]", "Inside",
                [part("fill_slot", "Inside", field_id="thesis.title.zh")],
            ),
            ("text", "/body/p[1]/r[3]", "End", [part("fixed_label", "End")]),
        ],
    )
    output = tmp_path / "candidate.docx"
    materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraph = root.find(f".//{W}p")
    assert paragraph is not None
    link = paragraph.find(f"{W}hyperlink")
    assert link is not None and link.get(W + "anchor") == "target"
    assert link.find(f"{W}sdt") is not None
    assert visible_word_text(paragraph) == "【中文题目】End"

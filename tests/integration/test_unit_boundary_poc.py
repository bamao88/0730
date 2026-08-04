from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.tools.inspection import Inspection, inspect_document
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file
from docfit.tools.unit_boundary import (
    UnitBoundaryResolver,
    materialize_resolved_unit,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def _top_level_texts(document: Path) -> list[str]:
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(_q("body"))
    assert body is not None
    return [
        "".join(node.text or "" for node in child.iter(_q("t")))
        for child in body
        if child.tag != _q("sectPr")
    ]


def _final_section_geometry(document: Path) -> dict[str, int]:
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(_q("body"))
    assert body is not None
    section = body.find(_q("sectPr"))
    assert section is not None
    page_size = section.find(_q("pgSz"))
    margins = section.find(_q("pgMar"))
    assert page_size is not None and margins is not None
    return {
        "page_width_twips": int(page_size.get(_q("w"), "0")),
        "page_height_twips": int(page_size.get(_q("h"), "0")),
        "margin_top_twips": int(margins.get(_q("top"), "0")),
        "margin_bottom_twips": int(margins.get(_q("bottom"), "0")),
        "margin_left_twips": int(margins.get(_q("left"), "0")),
        "margin_right_twips": int(margins.get(_q("right"), "0")),
    }


def _officecli(*arguments: str) -> None:
    executable = shutil.which("officecli")
    if executable is None:
        pytest.skip("unit-boundary PoC integration requires locked OfficeCLI")
    environment = dict(os.environ)
    environment["OFFICECLI_SKIP_UPDATE"] = "1"
    environment["OFFICECLI_RESIDENT_FLUSH"] = "each"
    completed = subprocess.run(
        [executable, *arguments, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["success"] is True


def _ref(inspection: Inspection, text: str) -> dict[str, object]:
    return next(dict(item.object_ref) for item in inspection.objects if item.text == text)


def _ref_containing(inspection: Inspection, text: str) -> dict[str, object]:
    return next(dict(item.object_ref) for item in inspection.objects if text in item.text)


def _refs(inspection: Inspection, text: str) -> list[dict[str, object]]:
    return [dict(item.object_ref) for item in inspection.objects if item.text == text]


def _make_c1(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add", str(path), "/body", "--type", "paragraph", "--prop", "text=PREVIOUS_UNIT_END"
    )
    _officecli("add", str(path), "/body/p[1]", "--type", "pagebreak")
    for text in ("UNIT_ANCHOR", "UNIT_BODY", "NEXT_UNIT_ANCHOR"):
        _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", f"text={text}")


def _make_c2(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add", str(path), "/body", "--type", "paragraph", "--prop", "text=PREVIOUS_UNIT_END"
    )
    _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", "pageBreakBefore=true")
    for text in ("UNIT_ANCHOR", "UNIT_BODY", "NEXT_UNIT_ANCHOR"):
        _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", f"text={text}")


def _make_c3(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add", str(path), "/body", "--type", "paragraph", "--prop", "text=PREVIOUS_UNIT_END"
    )
    _officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "section",
        "--prop",
        "type=nextPage",
        "--prop",
        "marginTop=2cm",
    )
    _officecli("set", str(path), "/", "--prop", "marginTop=3cm")
    for text in ("UNIT_ANCHOR", "UNIT_BODY", "NEXT_UNIT_ANCHOR"):
        _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", f"text={text}")


def _make_c4(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    commands: list[dict[str, object]] = [
        {
            "command": "add",
            "path": "/body",
            "type": "paragraph",
            "props": {"text": f"FILLER_{index:02d}"},
        }
        for index in range(49)
    ]
    commands.extend(
        [
            {
                "command": "add",
                "path": "/body",
                "type": "paragraph",
                "props": {"text": "PREVIOUS_UNIT_END"},
            },
            {"command": "add", "path": "/body", "type": "paragraph", "props": {}},
            {"command": "add", "path": "/body", "type": "paragraph", "props": {}},
            *[
                {
                    "command": "add",
                    "path": "/body",
                    "type": "paragraph",
                    "props": {"text": text},
                }
                for text in ("UNIT_ANCHOR", "UNIT_BODY", "NEXT_UNIT_ANCHOR")
            ],
        ]
    )
    OfficeCliAdapter().batch(path, commands)


def _make_c5(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    commands: list[dict[str, object]] = [
        {
            "command": "add",
            "path": "/body",
            "type": "paragraph",
            "props": {"text": f"FILLER_{index:02d}"},
        }
        for index in range(50)
    ]
    commands.append(
        {
            "command": "add",
            "path": "/body",
            "type": "paragraph",
            "props": {"text": "PREVIOUS_UNIT_END"},
        }
    )
    commands.append(
        {
            "command": "add",
            "path": "/body",
            "type": "paragraph",
            "props": {"text": "UNIT_ANCHOR", "spaceBefore": "2pt"},
        }
    )
    commands.extend(
        {
            "command": "add",
            "path": "/body",
            "type": "paragraph",
            "props": {"text": text},
        }
        for text in ("UNIT_BODY", "NEXT_UNIT_ANCHOR")
    )
    OfficeCliAdapter().batch(path, commands)


def _make_c6(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add", str(path), "/body", "--type", "paragraph", "--prop", "text=PREVIOUS_UNIT_END"
    )
    _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", "pageBreakBefore=true")
    for text in ("UNIT_ANCHOR", "UNIT_BODY"):
        _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", f"text={text}")
    for _ in range(3):
        _officecli("add", str(path), "/body", "--type", "paragraph")
    _officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "paragraph",
        "--prop",
        "text=NEXT_UNIT_ANCHOR",
        "--prop",
        "pageBreakBefore=true",
    )


def _make_c7(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add", str(path), "/body", "--type", "paragraph", "--prop", "text=PREVIOUS_UNIT_END"
    )
    _officecli(
        "add", str(path), "/body/p[1]", "--type", "pagebreak", "--prop", "type=line"
    )
    _officecli(
        "add", str(path), "/body/p[1]", "--type", "run", "--prop", "text=UNIT_ANCHOR"
    )
    for text in ("UNIT_BODY", "NEXT_UNIT_ANCHOR"):
        _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", f"text={text}")


def _make_c8(path: Path) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    for text in ("UNIT_ANCHOR", "INTERMEDIATE_CONTENT"):
        _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", f"text={text}")
    _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", "pageBreakBefore=true")
    for text in ("UNIT_ANCHOR", "UNIT_BODY", "NEXT_UNIT_ANCHOR"):
        _officecli("add", str(path), "/body", "--type", "paragraph", "--prop", f"text={text}")


def _resolve_repeatably(
    tmp_path: Path,
    resolver: UnitBoundaryResolver,
    document: Path,
    inspection: Inspection,
    *,
    unit_id: str,
    anchor_ref: JsonObject,
    next_ref: JsonObject,
    visual_anchor: JsonObject,
) -> JsonObject:
    request: JsonObject = {
        "schema_version": 1,
        "source_sha256": sha256_file(document),
        "render_ref": "officecli-reference",
        "units": [
            {
                "unit_id": unit_id,
                "first_visible_anchor_text": "UNIT_ANCHOR",
                "first_visible_anchor_ref": anchor_ref,
                "next_visible_anchor_ref": next_ref,
                "starts_on_new_page": True,
                "visual_anchor": visual_anchor,
            }
        ],
    }
    first = resolver.resolve(
        document,
        inspection,
        request,
        work_dir=tmp_path / "candidates-first",
    )
    second = resolver.resolve(
        document,
        inspection,
        request,
        work_dir=tmp_path / "candidates-second",
    )
    assert second == first
    assert all(
        candidate["mutation_bounded"] is True
        for unit in first["units"]
        for candidate in unit["candidate_evidence"]["candidates"]
    )
    return first


def test_c1_preserves_single_explicit_page_break(tmp_path: Path) -> None:
    document = tmp_path / "c1.docx"
    _make_c1(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    next_ref = _ref(inspection, "NEXT_UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document,
        inspection,
        anchor_ref,
        work_dir=tmp_path / "reference",
    )

    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c1",
        anchor_ref=anchor_ref,
        next_ref=next_ref,
        visual_anchor=visual_anchor,
    )

    assert result["status"] == "resolved"
    unit = result["units"][0]
    assert unit["status"] == "resolved", unit
    assert unit["source_boundary_mode"] == "explicit_page_break"
    assert unit["resolved_boundary"]["mode"] == "preserve_explicit_page_break"
    assert unit["candidate_evidence"]["unique_match"] is True
    assert sha256_file(document) == source_hash


def test_c2_preserves_page_break_before_and_one_leading_block(tmp_path: Path) -> None:
    document = tmp_path / "c2.docx"
    _make_c2(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, anchor_ref, work_dir=tmp_path / "reference"
    )

    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c2",
        anchor_ref=anchor_ref,
        next_ref=_ref(inspection, "NEXT_UNIT_ANCHOR"),
        visual_anchor=visual_anchor,
    )

    unit = result["units"][0]
    assert unit["status"] == "resolved"
    assert unit["source_boundary_mode"] == "explicit_page_break_before"
    assert unit["resolved_boundary"]["mode"] == "preserve_explicit_page_break_before"
    assert len(unit["resolved_boundary"]["leading_layout_refs"]) == 1
    assert unit["candidate_evidence"]["unique_match"] is True
    assert sha256_file(document) == source_hash


def test_c3_preserves_next_page_section_geometry(tmp_path: Path) -> None:
    document = tmp_path / "c3.docx"
    _make_c3(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, anchor_ref, work_dir=tmp_path / "reference"
    )

    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c3",
        anchor_ref=anchor_ref,
        next_ref=_ref(inspection, "NEXT_UNIT_ANCHOR"),
        visual_anchor=visual_anchor,
    )

    unit = result["units"][0]
    assert unit["status"] == "resolved"
    assert unit["source_boundary_mode"] == "explicit_section_break"
    assert unit["resolved_boundary"]["mode"] == "preserve_explicit_section_break"
    assert unit["section_geometry"]["margin_top_twips"] != 0
    assert unit["candidate_evidence"]["unique_match"] is True
    assert sha256_file(document) == source_hash


def test_materializer_rehomes_explicit_section_geometry_without_blank_first_page(
    tmp_path: Path,
) -> None:
    document = tmp_path / "c3-materialize.docx"
    output = tmp_path / "unit.docx"
    _make_c3(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    next_ref = _ref(inspection, "NEXT_UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, anchor_ref, work_dir=tmp_path / "reference"
    )
    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c3-materialize",
        anchor_ref=anchor_ref,
        next_ref=next_ref,
        visual_anchor=visual_anchor,
    )
    unit = result["units"][0]

    materialize_resolved_unit(
        document,
        output,
        inspection,
        unit,
        next_anchor_ref=next_ref,
    )

    assert _top_level_texts(output) == ["UNIT_ANCHOR", "UNIT_BODY"]
    geometry = _final_section_geometry(output)
    for key, value in geometry.items():
        assert value == unit["section_geometry"][key]
    output_inspection = inspect_document(output, office)
    output_visual = resolver.measure_reference_anchor(
        output,
        output_inspection,
        _ref(output_inspection, "UNIT_ANCHOR"),
        work_dir=tmp_path / "output-reference",
    )
    assert output_visual["page"] == 1
    assert output_visual["bbox_px"][1] == pytest.approx(
        visual_anchor["bbox_px"][1], abs=4.0
    )
    assert sha256_file(document) == source_hash


def test_c4_selects_one_of_two_natural_flow_leading_blocks(tmp_path: Path) -> None:
    document = tmp_path / "c4.docx"
    _make_c4(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, anchor_ref, work_dir=tmp_path / "reference"
    )
    assert visual_anchor["page"] == 2

    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c4",
        anchor_ref=anchor_ref,
        next_ref=_ref(inspection, "NEXT_UNIT_ANCHOR"),
        visual_anchor=visual_anchor,
    )

    unit = result["units"][0]
    assert unit["status"] == "resolved", unit
    assert unit["source_boundary_mode"] == "natural_flow_with_layout_blocks"
    assert unit["resolved_boundary"]["mode"] == "next_page"
    assert len(unit["resolved_boundary"]["leading_layout_refs"]) == 1
    assert len(unit["resolved_boundary"]["boundary_consumed_refs"]) == 1
    assert unit["candidate_evidence"]["candidate_count"] == 3
    assert unit["candidate_evidence"]["unique_match"] is True
    assert sha256_file(document) == source_hash


def test_materializer_consumes_natural_flow_filler_and_keeps_visible_leading_block(
    tmp_path: Path,
) -> None:
    document = tmp_path / "c4-materialize.docx"
    previous_output = tmp_path / "previous-unit.docx"
    output = tmp_path / "unit.docx"
    _make_c4(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    next_ref = _ref(inspection, "NEXT_UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, anchor_ref, work_dir=tmp_path / "reference"
    )
    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c4-materialize",
        anchor_ref=anchor_ref,
        next_ref=next_ref,
        visual_anchor=visual_anchor,
    )
    unit = result["units"][0]
    assert len(unit["resolved_boundary"]["leading_layout_refs"]) == 1
    assert len(unit["resolved_boundary"]["boundary_consumed_refs"]) == 1

    blank_refs = _refs(inspection, "")
    assert len(blank_refs) == 2
    previous_result = materialize_resolved_unit(
        document,
        previous_output,
        inspection,
        {
            "status": "resolved",
            "source_sha256": source_hash,
            "unit_id": "previous",
            "first_visible_anchor_ref": _ref(inspection, "FILLER_00"),
            "source_boundary_mode": "document_start",
            "resolved_boundary": {
                "boundary_owner_ref": _ref(inspection, "FILLER_00"),
                "leading_layout_refs": [],
                "boundary_consumed_refs": [],
                "trailing_layout_refs": blank_refs,
            },
        },
        next_anchor_ref=anchor_ref,
        next_resolved_unit=unit,
    )
    previous_texts = _top_level_texts(previous_output)
    assert len(previous_texts) == 51
    assert previous_texts[-2:] == ["PREVIOUS_UNIT_END", ""]
    assert "UNIT_ANCHOR" not in previous_texts
    assert previous_result["adjacent_visible_leading_excluded_count"] == 1

    materialize_resolved_unit(
        document,
        output,
        inspection,
        unit,
        next_anchor_ref=next_ref,
    )

    assert _top_level_texts(output) == ["", "UNIT_ANCHOR", "UNIT_BODY"]
    output_inspection = inspect_document(output, office)
    output_visual = resolver.measure_reference_anchor(
        output,
        output_inspection,
        _ref(output_inspection, "UNIT_ANCHOR"),
        work_dir=tmp_path / "output-reference",
    )
    assert output_visual["page"] == 1
    assert output_visual["page_height_px"] == pytest.approx(
        visual_anchor["page_height_px"], rel=0.01
    )
    assert output_visual["bbox_px"][1] == pytest.approx(
        visual_anchor["bbox_px"][1], abs=4.0
    )
    assert sha256_file(document) == source_hash


def test_c5_resolves_natural_flow_without_layout_blocks(tmp_path: Path) -> None:
    document = tmp_path / "c5.docx"
    _make_c5(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, anchor_ref, work_dir=tmp_path / "reference"
    )
    assert visual_anchor["page"] == 2

    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c5",
        anchor_ref=anchor_ref,
        next_ref=_ref(inspection, "NEXT_UNIT_ANCHOR"),
        visual_anchor=visual_anchor,
    )

    unit = result["units"][0]
    assert unit["status"] == "resolved", f"{visual_anchor}\n{json.dumps(unit, indent=2)}"
    assert unit["source_boundary_mode"] == "natural_flow_without_layout_blocks"
    assert unit["resolved_boundary"]["mode"] == "next_page"
    assert unit["resolved_boundary"]["leading_layout_refs"] == []
    assert unit["resolved_boundary"]["boundary_consumed_refs"] == []
    assert unit["candidate_evidence"]["candidate_count"] == 1
    assert unit["candidate_evidence"]["unique_match"] is True
    assert sha256_file(document) == source_hash


def test_c6_preserves_one_leading_and_three_trailing_blocks(tmp_path: Path) -> None:
    document = tmp_path / "c6.docx"
    _make_c6(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    anchor_ref = _ref(inspection, "UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, anchor_ref, work_dir=tmp_path / "reference"
    )

    result = _resolve_repeatably(
        tmp_path,
        resolver,
        document,
        inspection,
        unit_id="c6",
        anchor_ref=anchor_ref,
        next_ref=_ref(inspection, "NEXT_UNIT_ANCHOR"),
        visual_anchor=visual_anchor,
    )

    unit = result["units"][0]
    assert unit["status"] == "resolved"
    assert len(unit["resolved_boundary"]["leading_layout_refs"]) == 1
    assert len(unit["resolved_boundary"]["trailing_layout_refs"]) == 3
    assert unit["resolved_boundary"]["boundary_consumed_refs"] == []
    assert unit["candidate_evidence"]["unique_match"] is True
    assert sha256_file(document) == source_hash


def test_c7_rejects_a_boundary_inside_a_mixed_paragraph(tmp_path: Path) -> None:
    document = tmp_path / "c7.docx"
    _make_c7(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)

    result = resolver.resolve(
        document,
        inspection,
        {
            "schema_version": 1,
            "source_sha256": source_hash,
            "render_ref": "mock-reference",
            "units": [
                {
                    "unit_id": "c7",
                    "first_visible_anchor_text": "UNIT_ANCHOR",
                    "first_visible_anchor_ref": _ref_containing(inspection, "UNIT_ANCHOR"),
                    "next_visible_anchor_ref": _ref(inspection, "NEXT_UNIT_ANCHOR"),
                    "starts_on_new_page": True,
                    "visual_anchor": {
                        "page": 2,
                        "bbox_px": [0, 0, 1, 1],
                        "page_width_px": 1,
                        "page_height_px": 1,
                    },
                }
            ],
        },
        work_dir=tmp_path / "candidates",
    )

    assert result["status"] == "unsupported"
    unit = result["units"][0]
    assert unit["status"] == "unsupported"
    assert unit["warnings"][0]["code"] == "unsupported_atomic_boundary"
    assert not (tmp_path / "candidates").exists()
    assert sha256_file(document) == source_hash


def test_c8_disambiguates_with_next_anchor_and_fails_without_context(tmp_path: Path) -> None:
    document = tmp_path / "c8.docx"
    _make_c8(document)
    source_hash = sha256_file(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)
    resolver = UnitBoundaryResolver(office)
    duplicate_refs = _refs(inspection, "UNIT_ANCHOR")
    assert len(duplicate_refs) == 2
    second_ref = duplicate_refs[1]
    next_ref = _ref(inspection, "NEXT_UNIT_ANCHOR")
    visual_anchor = resolver.measure_reference_anchor(
        document, inspection, second_ref, work_dir=tmp_path / "reference"
    )

    unique = resolver.resolve(
        document,
        inspection,
        {
            "schema_version": 1,
            "source_sha256": source_hash,
            "render_ref": "officecli-reference",
            "units": [
                {
                    "unit_id": "c8-unique",
                    "first_visible_anchor_text": "UNIT_ANCHOR",
                    "next_visible_anchor_ref": next_ref,
                    "starts_on_new_page": True,
                    "visual_anchor": visual_anchor,
                }
            ],
        },
        work_dir=tmp_path / "unique-candidates",
    )

    unique_unit = unique["units"][0]
    assert unique_unit["status"] == "resolved"
    assert (
        unique_unit["resolved_boundary"]["insert_before_ref"]["object_id"]
        == second_ref["object_id"]
    )

    ambiguous = resolver.resolve(
        document,
        inspection,
        {
            "schema_version": 1,
            "source_sha256": source_hash,
            "render_ref": "officecli-reference",
            "units": [
                {
                    "unit_id": "c8-ambiguous",
                    "first_visible_anchor_text": "UNIT_ANCHOR",
                    "starts_on_new_page": True,
                    "visual_anchor": visual_anchor,
                }
            ],
        },
        work_dir=tmp_path / "ambiguous-candidates",
    )

    assert ambiguous["status"] == "ambiguous"
    ambiguous_unit = ambiguous["units"][0]
    assert ambiguous_unit["status"] == "ambiguous"
    assert ambiguous_unit["warnings"][0]["code"] == "ambiguous_anchor_mapping"
    assert not (tmp_path / "ambiguous-candidates").exists()
    assert sha256_file(document) == source_hash


def test_materializer_refuses_unresolved_unit_without_publishing(tmp_path: Path) -> None:
    document = tmp_path / "unresolved.docx"
    output = tmp_path / "must-not-exist.docx"
    _make_c8(document)
    office = OfficeCliAdapter()
    inspection = inspect_document(document, office)

    with pytest.raises(ToolFailure) as captured:
        materialize_resolved_unit(
            document,
            output,
            inspection,
            {
                "status": "ambiguous",
                "source_sha256": sha256_file(document),
                "unit_id": "ambiguous",
            },
            next_anchor_ref=None,
        )

    assert captured.value.code == "unresolved_unit_not_publishable"
    assert not output.exists()

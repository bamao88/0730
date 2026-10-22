"""Initial source order must follow Word positions, not inspection type buckets."""

from copy import deepcopy

import pytest

from docfit.app.prepare_template import PrepareTemplateRequest, prepare_template_task
from docfit.template.source_order import order_initial_source_objects
from docfit.template.unit_source import load_initial_inventory
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file
from docfit.tools.service import DocFitToolService
from tests.contract.test_template_materialization_runtime import _write_docx_from_paragraph_xml


def test_prepare_places_container_and_picture_with_their_document_neighbors(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    _write_docx_from_paragraph_xml(source, [
        '<w:p><w:r><w:t>Chapter</w:t></w:r></w:p>',
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:tr></w:tbl>',
        '<w:p><w:r><w:drawing/></w:r></w:p>',
        '<w:p><w:r><w:t>Declaration</w:t></w:r></w:p>',
    ])
    specs = [
        ("chapter", "paragraph", "/body/p[1]", "Chapter"),
        ("cell", "paragraph", "/body/tbl[1]/tr[1]/tc[1]/p[1]", "A"),
        ("picture-paragraph", "paragraph", "/body/p[2]", ""),
        ("declaration", "paragraph", "/body/p[3]", "Declaration"),
        ("table", "table", "/body/tbl[1]", "A"),
        ("picture", "picture", "/body/p[2]/r[1]", ""),
    ]
    objects = [{"object_ref": {"object_id": key}, "type": kind, "locator": locator, "text": text}
               for key, kind, locator, text in specs]
    original = deepcopy(objects)
    monkeypatch.setattr(DocFitToolService, "inspect", lambda *_: {"objects": objects})
    prepared = prepare_template_task(PrepareTemplateRequest(
        school_template=source, output_directory=tmp_path / "task",
    ))
    initial = load_initial_inventory(prepared.task_root, prepared.template_sha256)
    entries = initial["canonical_source_inventory"]["source_entries"]
    assert [e["provenance"][0]["object_id"] for e in entries] == [
        "chapter", "table", "cell", "picture-paragraph", "picture", "declaration",
    ]
    assert objects == original
    assert entries[1]["text"] == ""  # Container text is still owned once by its cell entry.
    assert entries[2]["text"] == "A"
    # An old task is never silently reordered and assigned new identities on resume.
    initial.pop("source_order_version")
    path = prepared.task_root / "work/.docfit/initial-source-inventory.json"
    atomic_write_json(path, initial)
    before = path.read_bytes()
    with pytest.raises(ToolFailure) as caught:
        prepare_template_task(PrepareTemplateRequest(
            school_template=source, output_directory=prepared.task_root,
        ))
    assert caught.value.code == "source_order_evidence_missing"
    assert path.read_bytes() == before


@pytest.mark.parametrize("fault", ["unknown_position", "wrong_source"])
def test_source_ordering_does_not_guess_missing_positions_or_use_another_input(tmp_path, fault):
    source = tmp_path / "source.docx"
    _write_docx_from_paragraph_xml(source, ['<w:p/>'])
    objects = [{"locator": "/body/p[2]" if fault == "unknown_position" else "/body/p[1]"}]
    with pytest.raises(ToolFailure) as caught:
        order_initial_source_objects(
            source, source_sha256="0" * 64 if fault == "wrong_source" else sha256_file(source),
            objects=objects,
        )
    assert caught.value.code == (
        "source_order_object_unresolved" if fault == "unknown_position"
        else "source_order_snapshot_mismatch"
    )

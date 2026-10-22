"""Faults in lowering must not redefine the accepted effect (logic/contract)."""

import zipfile
from dataclasses import replace
from xml.etree import ElementTree as ET

import pytest

from docfit.template.materialization import materialize_template_from_semantics
from docfit.template.materialization.text_edits import TextEdits
from docfit.tools.runtime import ToolFailure
from tests.contract.test_exact_object_cleanup import W, case, drawing, part


@pytest.mark.parametrize(
    "fault",
    [
        "promote_picture",
        "drop_span",
        "widen_text",
        "wrong_mapping",
        "replace_cleanup",
        "wrong_field",
    ],
)
def test_lowering_fault_cannot_redefine_verification_scope(tmp_path, monkeypatch, fault):
    import docfit.template.materialization.runtime as runtime

    if fault == "promote_picture":
        xml = "<w:p><w:r>" + drawing(1) + "</w:r></w:p>"
        rows = [("picture", "/body/p[1]/r[1]", "", [part("cleanup")])]
    else:
        xml = "<w:p><w:r><w:t>KeepRemove</w:t></w:r></w:p>"
        role = "fill_slot" if fault == "wrong_field" else "cleanup"
        rows = [
            (
                "text",
                "/body/p[1]/r[1]",
                "KeepRemove",
                [
                    part("fixed_label", "Keep"),
                    part(
                        role,
                        "Remove",
                        **({"field_id": "thesis.title.zh"} if role == "fill_slot" else {}),
                    ),
                ],
            )
        ]
    source, registry, inventory, review = case(tmp_path, xml, rows)
    if fault == "promote_picture":
        monkeypatch.setattr(
            runtime,
            "_cleanup_carrier_for_intent",
            lambda intent, targets: (
                targets[intent.resolved_spans[0].span_ref].paragraph,
                "paragraph",
            ),
        )
    elif fault == "drop_span":
        compile_plan = runtime.build_shadow_materialization_plan

        def drop(**kwargs):
            compiled = compile_plan(**kwargs)
            intent = compiled.plan.intents[0]
            return replace(
                compiled,
                plan=replace(
                    compiled.plan,
                    intents=(
                        replace(
                            intent,
                            resolved_spans=intent.resolved_spans[:1],
                            payload={
                                **intent.payload,
                                "resolved_spans": [intent.resolved_spans[0].to_json()],
                            },
                        ),
                    ),
                ),
            )

        monkeypatch.setattr(runtime, "build_shadow_materialization_plan", drop)
    elif fault == "wrong_mapping":
        original_bind = TextEdits.bind

        def widened_mapping(self, ref):
            bound = original_bind(self, ref)
            if bound.characters:
                atom = bound.characters[0][0]
                bound.characters[:] = [(atom, i) for i in range(len(atom.text))]
            return bound

        monkeypatch.setattr(TextEdits, "bind", widened_mapping)
    else:
        original = TextEdits.replace

        def wrong(self, span, children):
            original(self, span, children)
            ref = span["span_ref"]
            if fault == "widen_text":
                bound = self.bound[ref]
                atom = bound.characters[0][0]
                bound.characters[:] = [(atom, i) for i in range(len(atom.text))]
            elif fault == "replace_cleanup":
                from docfit.template.materialization.handlers.slots import run

                self.requests[ref] = [run("Injected")]
            else:
                children[0].find(f"{W}sdtPr/{W}alias").set(W + "val", "wrong.field")

        monkeypatch.setattr(TextEdits, "replace", wrong)
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert caught.value.code == "materialization_effect_mismatch"
    assert caught.value.origin == "tool"
    assert not output.exists()


def test_partial_existing_control_uses_inner_slot_without_adopting_whole_control(tmp_path):
    source, registry, inventory, review = case(
        tmp_path,
        '<w:p><w:sdt><w:sdtPr><w:id w:val="1"/></w:sdtPr>'
        "<w:sdtContent><w:r><w:t>KeepValue</w:t></w:r></w:sdtContent></w:sdt></w:p>",
        [
            (
                "text",
                "/body/p[1]/sdt[1]",
                "KeepValue",
                [
                    part("fixed_label", "Keep"),
                    part("fill_slot", "Value", field_id="thesis.title.zh"),
                ],
            )
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
    outer = root.find(f".//{W}p/{W}sdt")
    assert outer is not None and outer.find(f"{W}sdtPr/{W}tag") is None
    inner = outer.find(f".//{W}sdtContent/{W}sdt")
    assert inner is not None
    assert inner.find(f"{W}sdtPr/{W}alias").get(W + "val") == "thesis.title.zh"
    assert "".join(node.text or "" for node in outer.iter(W + "t")).startswith("Keep")


@pytest.mark.parametrize("fault", ["extra_paragraph", "wrap_retained_in_field"])
def test_unchanged_text_does_not_authorize_new_content_or_field_scope(tmp_path, monkeypatch, fault):
    source, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:r><w:t>Remove</w:t></w:r></w:p><w:p><w:r><w:t>Keep</w:t></w:r></w:p>",
        [
            ("text", "/body/p[1]/r[1]", "Remove", [part("cleanup", "Remove")]),
            ("text", "/body/p[2]/r[1]", "Keep", [part("fixed_label", "Keep")]),
        ],
    )
    original = TextEdits.apply

    def wrong(self):
        original(self)
        paragraph = next(iter(self.original_paragraphs))
        body = self.parents[paragraph]
        added = ET.SubElement(body, W + "p" if fault == "extra_paragraph" else W + "sdt")
        if fault == "extra_paragraph":
            ET.SubElement(ET.SubElement(added, W + "r"), W + "t").text = "Injected"
        else:
            ET.SubElement(ET.SubElement(added, W + "sdtPr"), W + "tag", {W + "val": "rogue"})
            content = ET.SubElement(added, W + "sdtContent")
            retained = body.findall(W + "p")[1]
            body.remove(retained)
            content.append(retained)

    monkeypatch.setattr(TextEdits, "apply", wrong)
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure, match="outside accepted|structural boundary"):
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert not output.exists()


@pytest.mark.parametrize("widen", [False, True])
def test_table_field_cannot_absorb_an_adjacent_retained_paragraph(tmp_path, monkeypatch, widen):
    import docfit.template.materialization.runtime as runtime

    source, registry, inventory, review = case(
        tmp_path,
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "<w:p><w:r><w:t>Keep</w:t></w:r></w:p>",
        [
            ("table", "/body/tbl[1]", "", [part("body_structure", field_id="body.table")]),
            ("text", "/body/p[1]/r[1]", "Keep", [part("fixed_label", "Keep")]),
        ],
    )
    if widen:
        original = runtime._materialize_body_intents

        def wrong(**kwargs):
            result = original(**kwargs)
            body = kwargs["document"].find(W + "body")
            retained = body.find(W + "p")
            body.remove(retained)
            control = next(
                n for n in body.iter(W + "sdt") if n.find(f"{W}sdtPr/{W}tag") is not None
            )
            control.find(W + "sdtContent").append(retained)
            return result

        monkeypatch.setattr(runtime, "_materialize_body_intents", wrong)
    output = tmp_path / "candidate.docx"
    if widen:
        with pytest.raises(ToolFailure, match="table interface changed"):
            materialize_template_from_semantics(
                source_docx=source,
                output_docx=output,
                registry=registry,
                inventory=inventory,
                review=review,
            )
        assert not output.exists()
    else:
        result = materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
        assert result["effect_verification"]["status"] == "ok"


def test_two_present_slots_cannot_exchange_their_source_bindings(tmp_path, monkeypatch):
    source, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:r><w:t>TitleBody</w:t></w:r></w:p>",
        [
            (
                "text",
                "/body/p[1]/r[1]",
                "TitleBody",
                [
                    part("body_structure", "Title", field_id="body.heading.outline1"),
                    part("body_structure", "Body", field_id="body.paragraph"),
                ],
            )
        ],
    )
    original = TextEdits.apply

    def swap(self):
        original(self)
        first, second = [children[0] for children in self.requests.values()]
        for tag in ("tag", "alias"):
            left, right = (s.find(f"{W}sdtPr/{W}{tag}") for s in (first, second))
            left_value, right_value = left.get(W + "val"), right.get(W + "val")
            left.set(W + "val", right_value)
            right.set(W + "val", left_value)

    monkeypatch.setattr(TextEdits, "apply", swap)
    output = tmp_path / "candidate.docx"
    output.write_bytes(b"previous-candidate")
    with pytest.raises(ToolFailure, match="accepted source binding"):
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert output.read_bytes() == b"previous-candidate"

"""Freeze effect authority from the accepted review, before execution lowering.

The executor may choose implementations, but cannot supply the verifier's scope,
required edits or field destinations. This is an internal view of existing spans,
not another source identity or an Agent-authored operation plan.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.body_interfaces import body_interfaces
from docfit.template.materialization.effect_verification import EffectVerification
from docfit.template.materialization.models import AcceptedResolvedSpan, MaterializationPlan
from docfit.template.materialization.text_edits import TextEdits, effect_failure, text_atoms
from docfit.template.unit_source import source_unit_cut_points, validate_inventory_partition
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json
from docfit.tools.word_parts import WordStory, resolve_story_locator
from docfit.tools.word_xml import W_NS, visible_word_text

W = f"{{{W_NS}}}"
SHAPE = "{urn:schemas-microsoft-com:vml}shape"


def assert_plan_preserves_review(plan: MaterializationPlan, review: JsonObject) -> None:
    accepted = Counter(sha256_json(span) for span in review["resolved_spans"])
    lowered = Counter(
        sha256_json(span.to_json()) for intent in plan.intents for span in intent.resolved_spans
    )
    if accepted != lowered:
        raise effect_failure("Execution lowering changed or omitted an accepted source span.")


def _unsupported(message: str) -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="tool",
        code="materialization_scope_mapping_unsupported",
        message=message,
        retryable=False,
    )


class AcceptedEffects:
    def __init__(
        self,
        *,
        stories: dict[str, WordStory],
        inventory: JsonObject,
        review: JsonObject,
        registry: FieldRegistrySnapshot,
    ) -> None:
        self.spans = deepcopy(review["resolved_spans"])
        self.roots = list({id(s.root): s.root for s in stories.values()}.values())
        self.parents = {
            child: parent for root in self.roots for parent in root.iter() for child in parent
        }
        self.objects: dict[str, list[ET.Element]] = {}
        self.slots: dict[str, str] = {}
        self.adopted: dict[str, ET.Element] = {}
        self.tables: dict[str, ET.Element] = {}
        self.removed: set[ET.Element] = set()
        self.object_cleanup: set[str] = set()
        kinds = {e["source_entry_id"]: e.get("entry_type") for e in inventory["source_entries"]}
        for span in self.spans:
            nodes: list[ET.Element] = []
            for fragment in span["word_fragments"]:
                resolved = resolve_story_locator(stories, fragment["locator"])
                if resolved is None:
                    raise effect_failure("An accepted source fragment cannot be resolved.")
                nodes.append(resolved[1])
            self.objects[span["span_ref"]] = nodes

        # Object authority comes from explicit extents, never from DELETE_BLOCK
        # classification or the executor's chosen paragraph/carrier.
        for judgment in review["semantic_judgments"]:
            spans = judgment["resolved_spans"]
            object_nodes = {n for s in spans for n in self.objects[s["span_ref"]]}
            if (
                all(s["role"] == "cleanup" for s in spans)
                and len(object_nodes) == 1
                and (node := next(iter(object_nodes))).tag == SHAPE
            ):
                whole = all(
                    f.get("extent") == {"kind": "whole_entry"}
                    for s in spans
                    for f in s["word_fragments"]
                )
                if not whole and "".join(s["text"] for s in spans) != visible_word_text(node):
                    raise ToolFailure(
                        status="needs_input",
                        origin="tool",
                        code="cleanup_span_not_whole_shape",
                        message="Shape deletion requires its complete accepted content.",
                    )
                self.removed.add(node)
                self.object_cleanup.update(s["span_ref"] for s in spans)
        for span in self.spans:
            if span["role"] != "cleanup" or span["span_ref"] in self.object_cleanup:
                continue
            fragments = span["word_fragments"]
            if not all(f.get("extent") == {"kind": "whole_entry"} for f in fragments):
                continue
            object_nodes = set(self.objects[span["span_ref"]])
            if len(object_nodes) != 1:
                raise _unsupported("Whole-object cleanup has no unique source object.")
            node = next(iter(object_nodes))
            if node.tag == W + "r" and kinds.get(span["source_entry_id"]) == "picture":
                drawings = node.findall(W + "drawing")
                if len(drawings) != 1:
                    raise ToolFailure(
                        status="error",
                        origin="tool",
                        code="materialization_cleanup_target_unsupported",
                        message="Picture source has no unique direct drawing.",
                    )
                node = drawings[0]
            elif node.tag not in {W + "p", W + "tbl", W + "drawing", SHAPE}:
                raise ToolFailure(
                    status="error",
                    origin="tool",
                    code="materialization_cleanup_target_unsupported",
                    message="Whole-object cleanup has no exact supported object.",
                )
            self.removed.add(node)
            self.object_cleanup.add(span["span_ref"])
        deleted = {n for node in self.removed for n in node.iter()}
        self.covered_cleanup = {
            s["span_ref"]
            for s in self.spans
            if s["role"] == "cleanup" and all(n in deleted for n in self.objects[s["span_ref"]])
        }

        cut_points = source_unit_cut_points(validate_inventory_partition(inventory))
        for judgment in review["semantic_judgments"]:
            for group in body_interfaces(
                tuple(AcceptedResolvedSpan.from_json(s) for s in judgment["resolved_spans"]),
                cut_points=cut_points,
            ):
                self.slots[group.anchor.span_ref] = group.slot_ref
        required = []
        for span in self.spans:
            ref, role = span["span_ref"], span["role"]
            if role == "fill_slot":
                self.slots[ref] = span["slot_ref"]
            if role in {"fill_slot", "body_structure"}:
                nodes = self.objects[ref]
                if (
                    role == "body_structure"
                    and len(set(nodes)) == 1
                    and nodes[0].tag == W + "tbl"
                    and all(
                        f.get("extent") == {"kind": "whole_entry"} for f in span["word_fragments"]
                    )
                ):
                    self.tables[ref] = nodes[0]
                    continue
                controls = {c for n in nodes if (c := self._ancestor(n, W + "sdt")) is not None}
                if role == "fill_slot" and controls:
                    if len(controls) != 1:
                        raise _unsupported("A field span crosses existing controls.")
                    control = next(iter(controls))
                    if self._can_adopt(span, control):
                        self.adopted[ref] = control
                        continue
                required.append(ref)
            elif (
                role in {"cleanup", "style_only"}
                and span["text"]
                and ref not in self.object_cleanup | self.covered_cleanup
            ):
                required.append(ref)
        # Separate bindings on the same immutable source nodes: executor changes
        # to its BoundText/requests cannot alter this expectation.
        self.reference = TextEdits.from_stories(stories, self.spans)
        self.reference.prepare(required)
        for span in self.spans:
            if span["span_ref"] in self.reference.bound:
                bound = self.reference.bound[span["span_ref"]]
                if bound.characters != self._characters(span):
                    raise effect_failure("Text mapping changed accepted fragment offsets.")
        self.reference.exclude_deleted_objects(self.removed)
        mutable = {n for bound in self.reference.bound.values() for n, _ in bound.characters}
        mutable.update(b.paragraph for b in self.reference.bound.values() if not b.characters)
        for control in self.adopted.values():
            mutable.add(control)
            props = control.find(W + "sdtPr")
            if props is not None:
                # Adoption may edit binding metadata, never unrelated properties.
                mutable.add(props)
                for child in props:
                    if child.tag in {W + "alias", W + "tag", W + "id"}:
                        mutable.add(child)
        for span in self.spans:
            if span["role"] != "fill_slot" or span["span_ref"] in self.adopted:
                continue
            field = registry.lookup(span["field_id"])
            layout = field.get("materialization")
            if not isinstance(layout, dict) or layout.get("slot_layout") != "centered_title":
                continue
            paragraph = self.reference.bound[span["span_ref"]].paragraph
            mutable.add(paragraph)
            props = paragraph.find(W + "pPr")
            if props is not None:
                mutable.add(props)
                for child in props:
                    if child.tag in {W + "ind", W + "jc"}:
                        mutable.update(child.iter())
        self.verification = EffectVerification(
            self.roots,
            mutable=mutable,
            removed=self.removed,
            required_edits=set(required),
            wrapped=set(self.tables.values()),
        )

    def _ancestor(self, node: ET.Element, tag: str) -> ET.Element | None:
        while node.tag != tag and node in self.parents:
            node = self.parents[node]
        return node if node.tag == tag else None

    def _characters(self, span: JsonObject) -> list[tuple[ET.Element, int]]:
        selected = []
        for fragment, node in zip(
            span["word_fragments"], self.objects[span["span_ref"]], strict=True
        ):
            chars = [(n, i) for n, text in text_atoms(node) for i in range(len(text))]
            selected.extend(
                chars[
                    fragment.get("object_text_start", 0) : fragment.get(
                        "object_text_end", len(chars)
                    )
                ]
            )
        return list(dict.fromkeys(selected))

    def _can_adopt(self, span: JsonObject, control: ET.Element) -> bool:
        selected = self._characters(span)
        whole = any(
            node is control and f.get("extent") == {"kind": "whole_entry"}
            for f, node in zip(span["word_fragments"], self.objects[span["span_ref"]], strict=True)
        )
        all_chars = [(n, i) for n, text in text_atoms(control) for i in range(len(text))]
        return whole or (
            selected == all_chars
            and not any(
                n.tag
                in {
                    W + "drawing", W + "pict", W + "object", W + "fldChar", W + "fldSimple"
                }
                for n in control.iter()
            )
        )

    def make_editor(self, stories: dict[str, WordStory]) -> TextEdits:
        editor = TextEdits.from_stories(stories, deepcopy(self.spans))
        editor.prepare(self.reference.bound)
        editor.exclude_deleted_objects(self.removed)
        return editor

    def verify(self, editor: TextEdits) -> None:
        if set(editor.bound) != set(self.reference.bound) or set(editor.requests) != set(
            self.reference.bound
        ):
            raise effect_failure("Execution omitted or added an accepted text obligation.")
        by_ref = {s["span_ref"]: s for s in self.spans}
        for ref, bound in self.reference.bound.items():
            actual = editor.bound[ref]
            if (
                actual.paragraph is not bound.paragraph
                or actual.container is not bound.container
                or actual.characters != bound.characters
            ):
                raise effect_failure("Execution changed an accepted source text boundary.")
            children = editor.requests[ref]
            if ref in self.slots:
                if len(children) != 1:
                    raise effect_failure(
                        "A field span did not produce exactly one field interface."
                    )
                self._check_slot(children[0], self.slots[ref], by_ref[ref]["field_id"])
            elif children:
                raise effect_failure("Accepted cleanup inserted unauthorized replacement content.")
        self.reference.requests = dict(editor.requests)
        self.verification.verify(self.reference, set(self.slots.values()))
        controls = {
            tag.get(W + "val"): n
            for root in self.roots
            for n in root.iter(W + "sdt")
            if (tag := n.find(f"{W}sdtPr/{W}tag")) is not None
        }
        for ref, original in {**self.adopted, **self.tables}.items():
            control = controls.get(self.slots[ref])
            if control is None:
                raise effect_failure("An accepted object interface disappeared.")
            self._check_slot(control, self.slots[ref], by_ref[ref]["field_id"])
            if ref in self.adopted:
                if control is not original:
                    raise effect_failure("Existing field interface moved to another object.")
            else:
                content = control.find(W + "sdtContent")
                if content is None or list(content) != [original]:
                    raise effect_failure("A table interface changed its accepted object boundary.")
        self._verify_structure(editor, controls)

    def _verify_structure(self, editor: TextEdits, controls: dict[str | None, ET.Element]) -> None:
        """Protect ancestry and reject new content outside accepted interfaces.

        Untagged body grouping wrappers and split runs are representation changes;
        they cannot become new semantic field boundaries or contain extra content.
        """
        current = {
            child: parent for root in self.roots for parent in root.iter() for child in parent
        }
        original_nodes = set(self.parents) | set(self.roots)
        deleted = {n for obj in self.removed for n in obj.iter()}
        edited_atoms = {n for b in self.reference.bound.values() for n, _ in b.characters}
        table_wrappers = {controls[self.slots[ref]] for ref in self.tables}
        for node, original_parent in self.parents.items():
            if node in deleted or node in edited_atoms or node not in current:
                continue
            parent = current[node]
            if parent is original_parent:
                continue
            # Text editing may split a run around an inline slot. An independent
            # drawing/field may move to the split run, but stays in its paragraph.
            if (
                original_parent.tag == W + "r"
                and parent.tag == W + "r"
                and parent not in original_nodes
                and current.get(parent) is self.parents.get(original_parent)
            ):
                continue
            while parent not in original_nodes:
                if parent.tag == W + "sdtContent":
                    next_parent = current.get(parent)
                    if next_parent is None or next_parent.tag != W + "sdt":
                        break
                    parent = next_parent
                if parent.tag != W + "sdt" or (
                    parent.find(f"{W}sdtPr/{W}tag") is not None and parent not in table_wrappers
                ):
                    break
                next_parent = current.get(parent)
                if next_parent is None:
                    break
                parent = next_parent
            if parent is not original_parent:
                raise effect_failure("A source object left its accepted structural boundary.")

        inserted = {
            n for children in editor.requests.values() for child in children for n in child.iter()
        }
        inserted.update(
            n for control in table_wrappers for n in control.iter() if n not in original_nodes
        )
        adopted_properties = {
            n
            for control in self.adopted.values()
            for props in control.findall(W + "sdtPr")
            for n in props.iter()
        }
        edited_paragraphs = {b.paragraph for b in self.reference.bound.values()}
        for node, parent in current.items():
            if node in original_nodes or node in inserted or node in adopted_properties:
                continue
            # Remaining generated nodes are run pieces, permitted paragraph
            # formatting, transparent body wrappers, or mandatory empty shells.
            ancestor = parent
            if node.tag in {W + "r", W + "t", W + "tab", W + "sym", W + "rPr"}:
                while ancestor not in edited_paragraphs and ancestor in current:
                    ancestor = current[ancestor]
                if ancestor in edited_paragraphs:
                    continue
            ancestor = parent
            while ancestor.tag not in {W + "rPr", W + "pPr"} and ancestor in current:
                ancestor = current[ancestor]
            if (
                ancestor.tag == W + "rPr"
                and (run := current.get(ancestor)) is not None
                and current.get(run) in edited_paragraphs
            ):
                continue
            if (node.tag == W + "pPr" and parent in edited_paragraphs) or (
                node.tag == W + "jc"
                and parent.tag == W + "pPr"
                and current.get(parent) in edited_paragraphs
            ):
                continue
            if (
                node.tag == W + "p"
                and not list(node)
                and not node.attrib
                and parent.tag
                in {
                    W + "tc",
                    W + "hdr",
                    W + "ftr",
                    W + "footnote",
                    W + "endnote",
                }
                and any(self.parents.get(obj) is parent for obj in self.removed)
            ):
                continue
            if node.tag == W + "sdt" and node.find(f"{W}sdtPr/{W}tag") is None:
                continue
            if node.tag in {W + "sdtPr", W + "sdtContent"} and parent.tag == W + "sdt":
                continue
            if node.tag == W + "id" and parent.tag == W + "sdtPr":
                continue
            raise effect_failure("Execution inserted content outside accepted source effects.")

    @staticmethod
    def _check_slot(control: ET.Element, slot_ref: str, field_id: str) -> None:
        tag = control.find(f"{W}sdtPr/{W}tag")
        alias = control.find(f"{W}sdtPr/{W}alias")
        if (
            control.tag != W + "sdt"
            or tag is None
            or tag.get(W + "val") != slot_ref
            or alias is None
            or alias.get(W + "val") != field_id
        ):
            raise effect_failure("The field interface differs from its accepted source binding.")

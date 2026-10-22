"""Source-bound text edits. Bind once, then edit without replacing a paragraph."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from docfit.tools.runtime import JsonObject, ToolFailure
from docfit.tools.word_parts import WordStory, resolve_story_locator
from docfit.tools.word_xml import W_NS, visible_word_text

W = f"{{{W_NS}}}"


def effect_failure(message: str) -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="tool",
        code="materialization_effect_mismatch",
        message=message,
        retryable=False,
    )


def _unsupported() -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="tool",
        code="materialization_text_mapping_unsupported",
        message="Accepted text has no exact editable Word text mapping.",
        retryable=False,
    )


def _break_failure() -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="tool",
        code="materialization_layout_break_mapping_unsupported",
        message="Text replacement has no unambiguous output position for a layout break.",
    )


def text_atoms(element: ET.Element) -> list[tuple[ET.Element, str]]:
    atoms = []
    parents = {child: parent for parent in element.iter() for child in parent}
    for node in element.iter():
        if node.tag in {W + "t", W + "tab", W + "sym"}:
            if (
                node.tag == W + "tab"
                and parents.get(node) is not None
                and parents[node].tag != W + "r"
            ):
                continue
            text = "\t" if node.tag == W + "tab" else visible_word_text(node)
            atoms.append((node, text))
    if "".join(text for _, text in atoms) != visible_word_text(element):
        raise _unsupported()
    return atoms


@dataclass
class BoundText:
    paragraph: ET.Element
    container: ET.Element
    characters: list[tuple[ET.Element, int]]


@dataclass(frozen=True)
class WrapperBoundary:
    node: ET.Element
    edge: str


type InlineToken = ET.Element | tuple[ET.Element, int] | WrapperBoundary


def paragraph_tokens(paragraph: ET.Element, original_nodes: set[ET.Element]) -> list[InlineToken]:
    """Preserve inline positions independently of run splitting and text serialization."""
    tokens: list[InlineToken] = []

    def visit(parent: ET.Element) -> None:
        for child in parent:
            if child.tag in {W + "pPr", W + "rPr"}:
                continue
            if child.tag == W + "r":
                for node in child:
                    if node.tag in {W + "t", W + "tab", W + "sym"}:
                        text = "\t" if node.tag == W + "tab" else visible_word_text(node)
                        tokens.extend((node, index) for index in range(len(text)))
                    elif node.tag != W + "rPr":
                        tokens.append(node)
                continue
            if child in original_nodes and child.tag in {
                W + "sdt", W + "sdtContent", W + "hyperlink"
            }:
                tokens.append(WrapperBoundary(child, "open"))
                visit(child)
                tokens.append(WrapperBoundary(child, "close"))
            else:
                tokens.append(child)

    visit(paragraph)
    return tokens


def _token_node(token: InlineToken) -> ET.Element:
    if isinstance(token, WrapperBoundary):
        return token.node
    return token[0] if isinstance(token, tuple) else token


class TextEdits:
    """Schedule disjoint changes against original nodes; never re-resolve shifted runs."""

    def __init__(
        self,
        roots: Iterable[ET.Element],
        spans: Iterable[JsonObject],
        resolve: Callable[[str], ET.Element | None],
    ) -> None:
        self.parents = {
            child: parent for root in roots for parent in root.iter() for child in parent
        }
        self.bound: dict[str, BoundText] = {}
        self.requests: dict[str, list[ET.Element]] = {}
        self.changed_atoms: set[ET.Element] = set()
        self.expected_text: dict[ET.Element, str] = {}
        self.original_paragraphs: dict[ET.Element, list[tuple[ET.Element, str]]] = {}
        self.original_tokens: dict[ET.Element, list[InlineToken]] = {}
        self.spans = {str(span["span_ref"]): span for span in spans}
        self.resolve = resolve

    @classmethod
    def from_stories(cls, stories: dict[str, WordStory], spans: list[JsonObject]) -> TextEdits:
        def resolve(locator: str) -> ET.Element | None:
            resolved = resolve_story_locator(stories, locator)
            return resolved[1] if resolved is not None else None

        return cls((story.root for story in stories.values()), spans, resolve)

    def bind(self, ref: str) -> BoundText:
        if ref in self.bound:
            return self.bound[ref]
        span = self.spans[ref]
        characters: list[tuple[ET.Element, int]] = []
        paragraphs: set[ET.Element] = set()
        for fragment in span["word_fragments"]:
            node = self.resolve(fragment["locator"])
            if node is None:
                raise _unsupported()
            paragraph = node
            while paragraph.tag != W + "p" and paragraph in self.parents:
                paragraph = self.parents[paragraph]
            if paragraph.tag != W + "p":
                raise _unsupported()
            paragraphs.add(paragraph)
            atoms = text_atoms(node)
            all_chars = [(atom, index) for atom, text in atoms for index in range(len(text))]
            start = fragment.get("object_text_start", 0)
            end = fragment.get("object_text_end", len(all_chars))
            characters.extend(all_chars[start:end])
        characters = list(dict.fromkeys(characters))
        if len(paragraphs) != 1:
            raise _unsupported()
        paragraph = next(iter(paragraphs))
        if "".join(dict(text_atoms(paragraph))[node][i] for node, i in characters) != span["text"]:
            raise _unsupported()
        containers: set[ET.Element] = set()
        for node, _ in characters:
            run = self.parents.get(node)
            if run is None or run.tag != W + "r":
                raise _unsupported()
            container = self.parents.get(run)
            if container is None or container.tag not in {
                W + "p", W + "sdtContent", W + "hyperlink"
            }:
                raise _unsupported()
            containers.add(container)
            ancestor: ET.Element | None = run
            while ancestor is not paragraph:
                assert ancestor is not None
                ancestor = self.parents.get(ancestor)
                if ancestor is None or ancestor.tag == W + "fldSimple":
                    raise _unsupported()
        if len(containers) > 1:
            raise _unsupported()
        container = next(iter(containers)) if containers else paragraph
        selected_nodes = {node for node, _ in characters}
        field_depth = 0
        for run in paragraph.iter(W + "r"):
            for node in run:
                if node.tag == W + "fldChar":
                    kind = node.get(W + "fldCharType")
                    if kind == "begin":
                        field_depth += 1
                    elif kind == "end":
                        field_depth = max(0, field_depth - 1)
                elif field_depth and node in selected_nodes:
                    raise _unsupported()
        self.original_paragraphs.setdefault(paragraph, text_atoms(paragraph))
        self.original_tokens.setdefault(
            paragraph, paragraph_tokens(paragraph, set(self.parents))
        )
        result = BoundText(paragraph, container, characters)
        self.bound[ref] = result
        return result

    def prepare(self, refs: Iterable[str]) -> None:
        for ref in refs:
            self.bind(ref)

    def exclude_deleted_objects(self, removed: set[ET.Element]) -> None:
        """Object deletions have their own verifier; exclude them from inline expectations."""
        deleted = {node for root in removed for node in root.iter()}
        for paragraph, atoms in self.original_paragraphs.items():
            self.original_paragraphs[paragraph] = [(node, text) for node, text in atoms
                                                   if node not in deleted]
            self.original_tokens[paragraph] = [
                token for token in self.original_tokens[paragraph]
                if _token_node(token) not in deleted
            ]

    def properties(self, ref: str) -> ET.Element | None:
        bound = self.bind(ref)
        if bound.characters:
            return self.parents[bound.characters[0][0]].find(W + "rPr")
        return bound.paragraph.find(f"{W}r/{W}rPr")

    def replace(self, span: JsonObject, children: list[ET.Element]) -> None:
        ref = str(span["span_ref"])
        self.bind(ref)
        if ref in self.requests:
            raise effect_failure("A source span received duplicate text edits.")
        self.requests[ref] = children

    def expected_results(self) -> dict[ET.Element, str]:
        """Derive expected text from original anchors, independently of apply()."""
        result = {}
        for paragraph, atoms in self.original_paragraphs.items():
            original = [(node, i) for node, text in atoms for i in range(len(text))]
            texts = dict(atoms)
            removed = set()
            inserted = {}
            empty = ""
            for ref, children in self.requests.items():
                bound = self.bound[ref]
                if bound.paragraph is not paragraph:
                    continue
                text = "".join(visible_word_text(child) for child in children)
                if bound.characters:
                    removed.update(bound.characters)
                    inserted[bound.characters[0]] = text
                else:
                    empty += text
            result[paragraph] = (
                "".join(
                    inserted.get(key, "") + ("" if key in removed else texts[key[0]][key[1]])
                    for key in original
                )
                + empty
            )
        return result

    def verify_inline_positions(self) -> None:
        for paragraph, tokens in self.original_tokens.items():
            original_text = dict(self.original_paragraphs[paragraph])
            removed = set()
            inserted = {}
            empty: list[ET.Element] = []
            for ref, children in self.requests.items():
                bound = self.bound[ref]
                if bound.paragraph is not paragraph:
                    continue
                if bound.characters:
                    removed.update(bound.characters)
                    inserted[bound.characters[0]] = children
                else:
                    empty.extend(children)
            expected: list[ET.Element | WrapperBoundary | str] = []
            for token in tokens:
                if isinstance(token, tuple):
                    expected.extend(inserted.get(token, []))
                    if token not in removed:
                        expected.append(original_text[token[0]][token[1]])
                else:
                    expected.append(token)
            expected.extend(empty)
            actual_text = dict(text_atoms(paragraph))
            actual = [
                actual_text[t[0]][t[1]] if isinstance(t, tuple) else t
                for t in paragraph_tokens(paragraph, set(self.parents))
            ]
            if actual != expected:
                raise effect_failure("An edit changed its accepted inline position or boundary.")

    def apply(self) -> None:
        expected_text = self.expected_results()
        self.expected_text.update(expected_text)
        containers = list(dict.fromkeys(
            bound.container for ref, bound in self.bound.items() if ref in self.requests
        ))
        for container in containers:
            atoms = text_atoms(container)
            requests = [
                (ref, children)
                for ref, children in self.requests.items()
                if self.bound[ref].container is container
            ]
            original = [(node, i) for node, text in atoms for i in range(len(text))]
            positions = {key: i for i, key in enumerate(original)}
            deleted: set[tuple[ET.Element, int]] = set()
            replaced: set[tuple[ET.Element, int]] = set()
            insertions: dict[tuple[ET.Element, int], list[ET.Element]] = {}
            empty_insertions: list[ET.Element] = []
            for ref, children in requests:
                chars = self.bound[ref].characters
                if not chars:
                    if children and (original or next(container.iter(W + "br"), None) is not None):
                        raise _break_failure()
                    empty_insertions.extend(children)
                    continue
                indexes = [positions[key] for key in chars]
                if indexes != list(range(indexes[0], indexes[-1] + 1)) or deleted.intersection(
                    chars
                ) and (children or replaced.intersection(chars)):
                    raise _unsupported()
                deleted.update(chars)
                if children:
                    replaced.update(chars)
                insertions[chars[0]] = children
                self.changed_atoms.update(node for node, _ in chars)
            # An explicit break inside replaced source text has no output anchor.
            offset = 0
            texts = dict(atoms)
            for node in container.iter():
                if (
                    node.tag == W + "br"
                    and 0 < offset < len(original)
                    and original[offset - 1] in deleted
                    and original[offset] in deleted
                ):
                    raise _break_failure()
                if node in texts:
                    offset += len(texts[node])
            children_out: list[ET.Element] = []
            for child in list(container):
                if child.tag != W + "r" or not any(node in self.changed_atoms for node in child):
                    children_out.append(child)
                    continue
                properties = child.find(W + "rPr")
                chunk: list[ET.Element] = []
                pieces: list[ET.Element] = []
                used_original = False

                def flush(
                    child: ET.Element = child,
                    properties: ET.Element | None = properties,
                    pieces: list[ET.Element] = pieces,
                ) -> None:
                    nonlocal chunk, used_original
                    if not chunk:
                        return
                    shell = ET.Element(W + "r", child.attrib)
                    if properties is not None:
                        shell.append(deepcopy(properties) if used_original else properties)
                    shell.extend(chunk)
                    if not used_original:
                        child[:] = list(shell)
                        shell = child
                        used_original = True
                    pieces.append(shell)
                    chunk = []

                for node in list(child):
                    if node.tag == W + "rPr":
                        continue
                    if node not in self.changed_atoms:
                        chunk.append(node)
                        continue
                    text = texts[node]
                    kept = ""

                    def flush_text(node: ET.Element = node) -> None:
                        nonlocal kept
                        if kept:
                            leaf = deepcopy(node)
                            if node.tag == W + "t":
                                leaf.text = kept
                                leaf.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                            chunk.append(leaf)  # noqa: B023 - invoked synchronously before flush
                            kept = ""

                    for i, character in enumerate(text):
                        key = (node, i)
                        if insertions.get(key):
                            flush_text()
                            flush()
                            pieces.extend(insertions[key])
                        if key not in deleted:
                            kept += character
                    flush_text()
                flush()
                if not used_original:
                    child[:] = [properties] if properties is not None else []
                    pieces.append(child)
                children_out.extend(pieces)
            container[:] = children_out + empty_insertions
        for paragraph, expected in expected_text.items():
            if visible_word_text(paragraph) != expected:
                raise effect_failure("The actual paragraph text differs from accepted edits.")

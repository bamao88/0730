"""Exact OfficeCLI 1.0.143 story-part mapping; no text search or alternative targets."""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from docfit.tools.runtime import ToolFailure
from docfit.tools.word_xml import resolve_word_locator, serialize_word_xml

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'

@dataclass
class SourceWordPackage:
    document: ET.Element
    locator_roots: dict[str, ET.Element]
    part_roots: dict[str, ET.Element]
    original_trees: dict[str, bytes]

    @classmethod
    def load(cls, path: Path) -> 'SourceWordPackage':
        with ZipFile(path) as archive:
            document = ET.fromstring(archive.read('word/document.xml'))
            roots = {'word/document.xml': document}
            locators = {'body': document.find(W+'body')}
            relationships = ET.fromstring(archive.read('word/_rels/document.xml.rels'))
            counts: dict[str,int] = {}
            for relationship in relationships:
                kind = relationship.get('Type','').removeprefix(REL)
                if kind not in {'header','footer','footnotes','endnotes','comments'}:
                    continue
                if relationship.get('TargetMode') == 'External':
                    raise ValueError('A source story must be an internal package part.')
                target = relationship.get('Target','')
                name = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'word/'+target)
                if not name.startswith('word/') or name in roots:
                    raise ValueError('A source story part is invalid or ambiguously related.')
                root = ET.fromstring(archive.read(name));roots[name]=root
                if kind in {'header','footer'}:
                    counts[kind]=counts.get(kind,0)+1
                    locators[f'{kind}[{counts[kind]}]']=root
                else:
                    item_kind={'footnotes':'footnote','endnotes':'endnote','comments':'comment'}[kind]
                    for index,item in enumerate(root.findall(W+item_kind),1):
                        locators[f'{item_kind}[{index}]']=item
            if locators['body'] is None:
                raise ValueError('Source document body is absent.')
            originals={name:ET.tostring(root) for name,root in roots.items()}
            return cls(document,locators,roots,originals)

    def resolve(self, locator: str) -> ET.Element | None:
        pieces=locator.strip('/').split('/',1)
        root=self.locator_roots.get(pieces[0])
        if root is None:return None
        return root if len(pieces)==1 else resolve_word_locator(root,pieces[1])

    def attach_stories(self) -> None:
        # One in-memory forest gives mutators an exact parent map. No new IDs/locators.
        for name,root in self.part_roots.items():
            if name != 'word/document.xml':self.document.append(root)

    def xml_updates(self) -> dict[str,bytes]:
        for name,root in self.part_roots.items():
            if name != 'word/document.xml':self.document.remove(root)
        return {name:serialize_word_xml(root) for name,root in self.part_roots.items()
                if ET.tostring(root)!=self.original_trees[name]}

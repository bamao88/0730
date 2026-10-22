"""Offline review of this named cover case; never passed to the product Agent."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

root = Path(__file__).resolve().parent
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
runs = {}
for name in ('before', 'after', 'after-final', 'example', 'example-repeat'):
    events = [json.loads(line) for line in (root / name / 'events.jsonl').read_text().splitlines()]
    rounds = []
    for event in events:
        if event['kind'] != 'structured_result':
            continue
        output = event.get('output') or {}
        judgments = output.get('semantic_judgments', [])
        bindings = [part for judgment in judgments for part in judgment['parts'] if part.get('field_id')]
        name_parts = next((j['parts'] for j in judgments if any(p.get('field_id') == 'author.name.zh' for p in j['parts'])), [])
        fields = {p['field_id']: p['text'] for p in bindings}
        checks = {
            'chinese_title_on_original_title_text': fields.get('thesis.title.zh') == '毕业论文（设计）中文题目',
            'english_title_on_original_title_text': fields.get('thesis.title.en') == 'TITLE OF GRADUATION PAPER',
            'advisor_title_on_example_value_only': fields.get('advisor.title') == '教授',
            'name_label_style_note_separated': any(p['text'].strip() == '（三号黑体加粗）' and p['role'] == 'style_only' for p in name_parts),
            'student_id_excludes_label': fields.get('author.student_id') == '20××××××××××',
            'cohort_class_excludes_label': fields.get('author.cohort_class') == '20××级×××（×）班',
        }
        rounds.append({'query_index': event['query_index'], 'status': output.get('status'), 'fields': fields, 'name_parts': name_parts, 'case_review': checks})
    doc = root / name / 'task/output/final-template.docx'
    with ZipFile(doc) as package:
        xml = ET.fromstring(package.read('word/document.xml'))
    paragraphs = [''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in xml.findall('.//w:body/w:p', ns)]
    render_file = root / name / 'render.json'
    render = json.loads(render_file.read_text()) if render_file.exists() and render_file.stat().st_size else None
    runs[name] = {
        'events': str(root / name / 'events.jsonl'),
        'rounds': rounds,
        'host_feedback_types': [e['feedback'].get('feedback', {}).get('type') for e in events if e['kind'] == 'host_review' and e['feedback']],
        'reference_reads': [e['input'] for e in events if e['kind'] == 'tool_call' and e['name'] == 'Read'],
        'sdt_count': len(xml.findall('.//w:sdt', ns)),
        'paragraphs': paragraphs,
        'artifact': str(doc),
        'render': render,
    }
result = {
    'verification_level': 'Real post-unit E2E agent loops resumed from the same validated unit-boundary proof, with final DOCX and fill-contract; before/example/example-repeat also rendered and visually inspected. Product acceptance failed.',
    'scope': 'Five diagnostic runs of one real cover case; final identical version tested twice. Offline case checks are review criteria, never supplied to runtime or used as semantic gates.',
    'runs': runs,
    'conclusions': [
        'Errors originate before revision feedback; coverage checking does not forbid adjacent semantic splits.',
        'All five observed post-unit runs loaded the main Skill but made no Reference Read call.',
        'Final two runs both recognize Chinese/English title, professor title value and embedded name-label style note.',
        'Second final run replaces whole student-ID and cohort-class lines, removing their fixed labels; overall semantic reliability remains unproven.',
        'Slot materialization preserves style_only text and long Registry-label placeholders; both final renders still occupy two pages.',
    ],
}
(root / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
for name, run in runs.items():
    print(name, len(run['host_feedback_types']), run['sdt_count'], run['rounds'][-1]['case_review'])

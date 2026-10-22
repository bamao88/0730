"""Offline evidence summary; never supplied to the runtime Agent."""
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
OLD = ROOT / 'temp/id-closure-20260911/cover-e2e'
NEW = RUN / 'cover-e2e'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def summarize(task):
    trace_path = task / 'work/.docfit/template-agent-execution.json'
    trace = json.loads(trace_path.read_text())
    completion = trace.get('agent_completion') or {}
    judgments = completion.get('semantic_judgments', [])
    result = {
        'task': str(task),
        'status': trace.get('status'),
        'completion_status': completion.get('status'),
        'failure': trace.get('failure'),
        'backend': trace.get('backend'),
        'session_id': trace.get('session_id'),
        'skills_loaded': trace.get('skills_loaded'),
        'sdk_query_count': trace.get('sdk_query_count'),
        'harness_feedback_attempts': trace.get('harness_feedback_attempts'),
        'semantic_feedback_attempts': trace.get('semantic_feedback_attempts'),
        'wall_duration_ms': trace.get('wall_duration_ms'),
        'judgment_count': len(judgments),
        'part_count': sum(len(j.get('parts', [])) for j in judgments),
        'field_parts': [
            {'judgment_index': i, 'source_entry_id': j.get('source_entry_id'), **part}
            for i,j in enumerate(judgments)
            for part in j.get('parts', []) if part.get('field_id')
        ],
        'judgments': judgments,
    }
    doc = task / 'output/final-template.docx'
    if doc.exists():
        with ZipFile(doc) as z:
            body = ET.fromstring(z.read('word/document.xml'))
        result['docx_sha256'] = hashlib.sha256(doc.read_bytes()).hexdigest()
        result['paragraphs'] = [
            ''.join(t.text or '' for t in p.findall('.//w:t', NS))
            for p in body.findall('.//w:body/w:p', NS)
        ]
        result['content_controls'] = []
        for sdt in body.findall('.//w:sdt', NS):
            alias = sdt.find('w:sdtPr/w:alias', NS)
            tag = sdt.find('w:sdtPr/w:tag', NS)
            result['content_controls'].append({
                'alias': alias.get('{'+NS['w']+'}val') if alias is not None else None,
                'tag': tag.get('{'+NS['w']+'}val') if tag is not None else None,
                'text': ''.join(t.text or '' for t in sdt.findall('.//w:t', NS)),
            })
    return result

comparison = {'baseline': summarize(OLD), 'current': summarize(NEW)}
(RUN / 'comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2)+'\n')
for name, result in comparison.items():
    print(name, {k:v for k,v in result.items() if k not in ['judgments','paragraphs','field_parts','content_controls']})
    print('field parts:', json.dumps(result['field_parts'],ensure_ascii=False))
    print('paragraphs:',json.dumps(result.get('paragraphs'),ensure_ascii=False))

"""Offline observations only; never imported or supplied to the product Agent.

Single-span reference matching is descriptive, not semantic acceptance: a name
example may validly separate its alternative-form note from the fill value.
Native review status below is mechanical span/coverage acceptance only.
"""
from pathlib import Path
import json
import re
base=Path(__file__).parent
recorded=[json.loads(l) for l in (base.parent/'title-field-meaning-20260911/run-2/events.jsonl').read_text().splitlines()]
packet=next(e['result'] for e in recorded if e['kind']=='unit_evidence_packet')
entries=packet['evidence'];byid={e['source_entry_id']:e for e in entries}
expected={6:('thesis.title.zh','毕业论文（设计）中文题目'),7:('thesis.title.en','TITLE OF GRADUATION PAPER'),10:('author.student_id','20××××××××××'),11:('author.cohort_class','20××级×××（×）班')}
expected_bindings={'thesis.title.zh':'毕业论文（设计）中文题目','thesis.title.en':'TITLE OF GRADUATION PAPER','author.name.zh':'×××（或×□×）','author.student_id':'20××××××××××','author.cohort_class':'20××级×××（×）班','advisor.name.zh':'×××','advisor.title':'教授','author.department':'××××学院','submission.date':'20××年××月'}
def score(output):
 if not isinstance(output,dict): return {'valid_result':False}
 js=output.get('semantic_judgments',[]);bindings=[];literal_errors=[];nonspace_errors=[];title_reasons=[];byorder={}
 for j in js:
  parts=j.get('parts',[]);entry=byid.get(j.get('source_entry_id',''))
  if entry is None and 'scope' in j:
   block=j['scope'].get('reading_block_id','')
   if block.startswith('cover:block-'):entry=entries[int(block.rsplit('-',1)[1])-1]
  if entry:
   n=entry['source_order']['block'];byorder[n]=parts
   if ''.join(p.get('text','') for p in parts)!=entry['text']:
    literal_errors.append(n)
    if re.sub(r'\s+', '', ''.join(p.get('text','') for p in parts))!=re.sub(r'\s+', '', entry['text']):nonspace_errors.append(n)
   if n in (6,7):title_reasons.append({'block':n,'parts':parts,'reason':j.get('reason')})
  bindings.extend({'field_id':p['field_id'],'text':p.get('text'),'role':p.get('role')} for p in parts if p.get('field_id'))
 good={str(n):any(p.get('field_id')==f and p.get('role')=='fill_slot' and p.get('text','').strip()==t for p in byorder.get(n,[])) for n,(f,t) in expected.items()}
 preserved={str(n):all(p.get('role') not in ('fill_slot','cleanup') for p in byorder.get(n,[]) if not p.get('text','').strip().startswith('（')) for n in (3,4,15)}
 return {'valid_result':True,'status':output.get('status'),'field_count':len(bindings),'matches_single_span_reference':len(bindings)==len(expected_bindings) and all(any(p['field_id']==f and p['role']=='fill_slot' and p['text'].strip()==t for p in bindings) for f,t in expected_bindings.items()),'title_fields_present':{fid:any(p['field_id']==fid and p['role']=='fill_slot' for p in bindings) for fid in ('thesis.title.zh','thesis.title.en')},'checked_value_spans':good,'fixed_landmarks_preserved':preserved,'literal_partition_differences':literal_errors,'nonspace_partition_errors':nonspace_errors,'bindings':bindings,'titles':title_reasons}
reports={}
for folder in sorted(base.glob('sdk-*')):
 if not folder.is_dir() or not (folder/'events.jsonl').exists():continue
 ev=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()]
 attempts=[e['input'] for e in ev if e['kind']=='tool_call' and e.get('name')=='StructuredOutput']
 results=[e['output'] for e in ev if e['kind']=='result']
 reviews=[e for e in ev if e['kind']=='native_review']
 reports[folder.name]={'native_mechanical_accepted': bool(reviews) and reviews[-1]['feedback'] is None, 'stopped_incomplete': (folder/'termination.json').exists(), 'attempt_count':len(attempts),'complete':bool(results),'first':score(attempts[0]) if attempts else None,'final':score(results[-1]) if results else None,'reads':[e['input'] for e in ev if e['kind']=='tool_call' and e.get('name')=='Read']}
(base/'audit.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
for name,r in reports.items():
 f=r['final'] or r['first'] or {}
 print(name,'complete',r['complete'],'attempts',r['attempt_count'],'slots',f.get('field_count'),'spans',f.get('checked_value_spans'),'literal',f.get('nonspace_partition_errors'))

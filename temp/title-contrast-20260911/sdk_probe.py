"""Real-input SDK ablation. Frozen evidence is replayed, no host materialization.

Only public tool calls/results, final structured decisions and init context paths
are saved. No private reasoning or full SDK transcript is persisted here.
"""
import argparse
import asyncio
import importlib
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace

from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, ResultMessage, SystemMessage, ToolUseBlock, ThinkingBlock
from docfit.app.settings import iter_agent_backends
pt=importlib.import_module('docfit.app.prepare_template')
os.umask(0o077)
parser=argparse.ArgumentParser();parser.add_argument('--arm-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--captured',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
source=[json.loads(line) for line in args.captured.read_text().splitlines()]
packet=next(e['result'] for e in source if e['kind']=='unit_evidence_packet')
original_prompt=next(e['prompt'] for e in source if e['kind']=='initial_prompt')
root=args.arm_root.resolve();task=root/args.output.name;task.mkdir()
input_dir=task/'input';input_dir.mkdir()
old_task=Path('/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/title-field-meaning-20260911/run-2/task')
import shutil
for name in ['school-template.docx','school-requirements.pdf','field-registry.yaml']:
 shutil.copy2(old_task/'input'/name,input_dir/name)
prompt=original_prompt.replace(str(old_task),str(task))
if (root/'probe-brief.txt').exists():
 prompt=(root/'probe-brief.txt').read_text()
started=time.monotonic()
def log(kind,**kw):
 with (args.output/'events.jsonl').open('a') as f:f.write(json.dumps({'kind':kind,'elapsed_ms':round((time.monotonic()-started)*1000),**kw},ensure_ascii=False)+'\n')
def evidence(self,request):
 if request.get('focus')=='unit_evidence_packet' and request.get('unit_id')=='cover':
  log('evidence',request=request,result=packet)
  return packet
 return {'schema_version':'docfit_evidence_card_v1','status':'needs_input','focus':request.get('focus'),'summary':{'message':'This bounded replay provides the complete saved unit_evidence_packet for cover. Other evidence was not captured.'}}
pt.DocFitToolService.evidence=evidence
backend=next(b for b in iter_agent_backends() if b.name=='minimax')
async def main():
 with tempfile.TemporaryDirectory(prefix='docfit-probe-config-') as conf:
  opts=pt.build_prepare_template_options(SimpleNamespace(task_root=task),backend,Path(conf))
  if (root/'probe-reasoning.json').exists():
   reasoning=json.loads((root/'probe-reasoning.json').read_text());opts.thinking=reasoning['thinking'];opts.effort=reasoning['effort']
  (args.output/'options.json').write_text(json.dumps({'model':opts.model,'thinking':opts.thinking,'effort':opts.effort,'cwd':str(opts.cwd),'setting_sources':opts.setting_sources,'skills':opts.skills,'system_prompt':opts.system_prompt,'output_format':opts.output_format},ensure_ascii=False,indent=2)+'\n')
  (args.output/'prompt.txt').write_text(prompt)
  calls={}
  async with ClaudeSDKClient(options=opts) as client:
   await client.query(prompt)
   async for message in client.receive_response():
    if isinstance(message,SystemMessage) and message.subtype=='init':
     log('init',**{k:message.data.get(k) for k in ['memory_paths','skills','model','cwd','claude_code_version','tools']})
    if isinstance(message,AssistantMessage):
     for block in message.content:
      if isinstance(block,ThinkingBlock):
       log('thinking_block_present')  # Presence only; never content.
      if isinstance(block,ToolUseBlock):
       calls[block.id]=block.name
       log('tool_call',name=block.name,input=block.input)
    for block in getattr(message,'content',[]) if isinstance(getattr(message,'content',None),list) else []:
     if getattr(block,'tool_use_id',None) in calls:
      log('tool_result',name=calls[block.tool_use_id],is_error=getattr(block,'is_error',None),content=getattr(block,'content',None))
    if isinstance(message,ResultMessage):
     output=message.structured_output
     log('result',is_error=message.is_error,subtype=message.subtype,output=output)
     (args.output/'result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
     fields=[p.get('field_id') for j in (output or {}).get('semantic_judgments',[]) for p in j.get('parts',[]) if p.get('field_id')]
     print(json.dumps({'arm':args.arm_root.name,'run':args.output.name,'is_error':message.is_error,'fields':fields},ensure_ascii=False),flush=True)
asyncio.run(main())

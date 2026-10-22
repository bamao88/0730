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
 from native_feedback import verify_inventory, feedback_for_output, INVENTORY_SHA256
 verify_inventory(packet)
 log('native_inventory',sha256=INVENTORY_SHA256)
 with tempfile.TemporaryDirectory(prefix='docfit-probe-config-') as conf:
  opts=pt.build_prepare_template_options(SimpleNamespace(task_root=task),backend,Path(conf))
  opts.thinking={'type':'adaptive'}
  opts.include_partial_messages=True
  (args.output/'options.json').write_text(json.dumps({'model':opts.model,'thinking':opts.thinking,'effort':opts.effort,'include_partial_messages':True,'cwd':str(opts.cwd),'setting_sources':opts.setting_sources,'skills':opts.skills,'system_prompt':opts.system_prompt,'output_format':opts.output_format},ensure_ascii=False,indent=2)+'\n')
  (args.output/'prompt.txt').write_text(prompt)
  calls={}
  async with ClaudeSDKClient(options=opts) as client:
   await client.query(prompt)
   for round_index in range(1,5):
    output=None;progress_count=0;last_progress=time.monotonic();max_gap=0.0
    responses=client.receive_response().__aiter__()
    while True:
     try:
      remaining=180-(time.monotonic()-last_progress)
      if remaining<=0:raise TimeoutError('No generation or tool progress for 180 seconds')
      message=await asyncio.wait_for(anext(responses),timeout=remaining)
     except StopAsyncIteration:
      break
     if pt._sdk_has_generation_progress(message):
      now=time.monotonic();max_gap=max(max_gap,now-last_progress);last_progress=now;progress_count+=1
     if isinstance(message,SystemMessage) and message.subtype=='init':
      log('init',**{k:message.data.get(k) for k in ['skills','model','cwd','claude_code_version']})
     if isinstance(message,AssistantMessage):
      for block in message.content:
       if isinstance(block,ThinkingBlock):log('thinking_block_present')
       if isinstance(block,ToolUseBlock):
        calls[block.id]=block.name;last_progress=time.monotonic()
        log('tool_call',name=block.name,input=block.input,round_index=round_index)
     for block in getattr(message,'content',[]) if isinstance(getattr(message,'content',None),list) else []:
      if getattr(block,'tool_use_id',None) in calls:
       log('tool_result',name=calls[block.tool_use_id],is_error=getattr(block,'is_error',None),content=getattr(block,'content',None))
     if isinstance(message,ResultMessage):
      output=message.structured_output;last_progress=time.monotonic()
      log('result',is_error=message.is_error,subtype=message.subtype,output=output,round_index=round_index,generation_events=progress_count,max_generation_gap_seconds=round(max_gap,3))
      (args.output/f'result-{round_index}.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    if output is None:raise RuntimeError('No structured result')
    feedback=feedback_for_output(output)
    log('native_review',feedback=feedback,round_index=round_index)
    if feedback is None:
     (args.output/'result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
     fields=[p.get('field_id') for j in output.get('semantic_judgments',[]) for p in j.get('parts',[]) if p.get('field_id')]
     print(json.dumps({'run':args.output.name,'rounds':round_index,'fields':fields,'native_review':'accepted'},ensure_ascii=False),flush=True)
     return
    revised_prompt=pt._semantic_feedback_prompt(feedback)
    log('feedback_prompt',prompt=revised_prompt,round_index=round_index)
    await client.query(revised_prompt)
   raise RuntimeError('Native feedback did not close within four rounds')
asyncio.run(main())

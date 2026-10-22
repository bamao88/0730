"""Diagnostic taps around the normal product CLI; preserve all original returns.

Only explicit tool calls, structured results, evidence packets and host feedback
are recorded, not model reasoning or raw SDK transcripts. Logs stay outside the
runtime task input. No alternate Agent loop or semantic answers are injected.
"""
import importlib
import json
import os
from pathlib import Path
import sys
import time
from claude_agent_sdk import SystemMessage

os.umask(0o077)
pt = importlib.import_module('docfit.app.prepare_template')
log_dir = Path(os.environ['DOCFIT_DIAGNOSTIC_LOG_DIR']).resolve()
log_dir.mkdir(parents=True, exist_ok=True)
log = log_dir / 'events.jsonl'
started = time.monotonic()
structured_calls = set()


def record(kind, **payload):
    with log.open('a') as f:
        f.write(json.dumps({'kind':kind,'elapsed_ms':round((time.monotonic()-started)*1000),**payload},ensure_ascii=False)+'\n')


original_event = pt._sdk_receive_event

def receive_event(message, **kwargs):
    event = original_event(message, **kwargs)
    if isinstance(message, SystemMessage) and message.subtype == 'init':
        record('sdk_init_context', memory_paths=message.data.get('memory_paths'), skills=message.data.get('skills'), agents=message.data.get('agents'), tools=message.data.get('tools'), cwd=message.data.get('cwd'), model=message.data.get('model'), version=message.data.get('claude_code_version'))
    stage = kwargs.get('stage')
    if isinstance(message, pt.AssistantMessage):
        for block in message.content:
            if not isinstance(block, pt.ToolUseBlock):
                continue
            if block.name in ('Read','Skill','StructuredOutput'):
                record('tool_call',stage=stage,query_index=kwargs.get('query_index'),name=block.name,input=block.input)
            if block.name == 'StructuredOutput':
                structured_calls.add(block.id)
    if isinstance(message, pt.ResultMessage):
        record('structured_result',stage=stage,query_index=kwargs.get('query_index'),output=message.structured_output,is_error=message.is_error)
    for block in getattr(message,'content',[]) if isinstance(getattr(message,'content',None),list) else []:
        if getattr(block,'tool_use_id',None) in structured_calls:
            record('structured_tool_result',stage=stage,result=getattr(block,'content',None),is_error=getattr(block,'is_error',None))
    return event
pt._sdk_receive_event = receive_event

original_review = pt._runtime_feedback_for_complete_output

def review(prepared, structured_output, **kwargs):
    record('before_host_review',output=structured_output)
    feedback, semantic = original_review(prepared, structured_output, **kwargs)
    record('host_review',feedback=feedback,is_semantic_feedback=semantic)
    return feedback, semantic
pt._runtime_feedback_for_complete_output = review

original_feedback = pt._semantic_feedback_prompt

def feedback_prompt(feedback):
    prompt = original_feedback(feedback)
    record('feedback_prompt',prompt=prompt)
    return prompt
pt._semantic_feedback_prompt = feedback_prompt

original_prompt = pt.build_prepare_template_prompt

def initial_prompt(*args, **kwargs):
    prompt = original_prompt(*args, **kwargs)
    record('initial_prompt',prompt=prompt)
    return prompt
pt.build_prepare_template_prompt = initial_prompt

original_evidence = pt.DocFitToolService.evidence

def evidence(self, args):
    result = original_evidence(self, args)
    if args.get('focus') == 'unit_evidence_packet':
        record('unit_evidence_packet',input=args,result=result)
    return result
pt.DocFitToolService.evidence = evidence

from docfit.app.cli import main
raise SystemExit(main(sys.argv[1:]))

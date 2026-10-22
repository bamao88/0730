import asyncio
import hashlib
import json
import tempfile
import time
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from jsonschema import Draft7Validator

from docfit.app.prepare_template import POST_UNIT_OUTPUT_SCHEMA, _SEMANTIC_TEXT_TRANSPORT_INSTRUCTIONS
from docfit.app.settings import iter_agent_backends
from docfit.observability.transcript import isolated_sdk_environment
from docfit.template.harness import _decode_whitespace_parts

async def main():
    backend = next(iter_agent_backends())
    parts = [{"text": "Label", "role": "fixed_label"},
             {"text": " Example value", "role": "fill_slot", "field_id": "author.name.en"}]
    prompt = (_SEMANTIC_TEXT_TRANSPORT_INSTRUCTIONS + "\nSynthetic transport test. Re-encode these already assigned parts without changing their text after decoding, number, roles, or fields. Return complete for source-entry-probe. Do not add field_id to the label. Original parts: " + json.dumps(parts))
    result = {"verification_level": "synthetic live SDK compatibility probe, not school E2E", "backend": backend.name, "model": backend.model, "schema": POST_UNIT_OUTPUT_SCHEMA, "prompt": prompt, "original_parts": parts}
    started = time.monotonic()
    warnings = []
    with tempfile.TemporaryDirectory(prefix="docfit-boundary-probe-") as config:
        options = ClaudeAgentOptions(tools=[], setting_sources=[], max_turns=6,
            thinking={"type": "disabled"}, model=backend.model,
            env=isolated_sdk_environment(backend.sdk_environment(), Path(config)),
            output_format={"type": "json_schema", "schema": POST_UNIT_OUTPUT_SCHEMA},
            stderr=lambda line: warnings.append("strictTypes") if "strictTypes" in line else None)
        try:
            async with asyncio.timeout(180):
                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt)
                    async for message in client.receive_response():
                        if isinstance(message, ResultMessage):
                            result.update(subtype=message.subtype, is_error=message.is_error)
                            if not message.is_error and isinstance(message.structured_output, dict):
                                data = message.structured_output
                                Draft7Validator(POST_UNIT_OUTPUT_SCHEMA).validate(data)
                                decoded, failure = _decode_whitespace_parts(data["semantic_judgments"])
                                result.update(structured_output=data, exact_parts_preserved=failure is None and len(decoded) == 1 and decoded[0]["parts"] == parts)
        except Exception as error:
            result["exception_type"] = type(error).__name__
    result.update(duration_seconds=round(time.monotonic()-started, 2), schema_warnings=warnings)
    result["runtime_files"] = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ["src/docfit/app/prepare_template.py", "src/docfit/template/harness.py"]}
    Path(__file__).with_name("part-boundary-final-codec-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k in {"subtype", "is_error", "exact_parts_preserved", "exception_type", "duration_seconds", "schema_warnings"}}))

asyncio.run(main())

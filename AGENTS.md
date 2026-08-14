# DocFit Agent Architecture Guidance

## Architectural mindset

General-purpose coding agents may default to conventional software-engineering
patterns that move uncertainty into application-owned states, protocols, and
fixed workflows.

DocFit follows an Agent-native architecture. Traditional software techniques
remain appropriate for deterministic concerns, but they must not take semantic
judgment or adaptive control away from the Agent.

Before adding application control flow, first ask whether better context, Skill
guidance, References, or Tool feedback would let the Agent solve the problem
itself.

## Claude Agent SDK-native first

Before designing, fixing, or optimizing an Agent capability, read the relevant
official Claude Agent SDK documentation.

Use the SDK's native Agent loop, sessions, context management, Tool calls,
permissions, Skills, Subagents, resumption, and lifecycle mechanisms by default.
DocFit owns thesis-domain capabilities, product contracts, and the thin adapters
needed to connect them to the SDK; it does not build a second Agent runtime.

Introduce custom Agent infrastructure only after a bounded experiment shows
that the SDK-native mechanism cannot satisfy an approved product requirement.
Make the added complexity, maintenance ownership, and removal path explicit.

## Skill-first capability development

DocFit uses Skills as the primary development surface for adaptive domain
capabilities.

A Skill workflow teaches the Agent how to observe, reason, load References,
choose Tools, recover, delegate, and judge completion. The Agent retains control
and may adapt, reorder, repeat, or skip steps. Do not translate this workflow
into application-owned semantic states, work-item queues, routing protocols, or
fixed Tool sequences.

- Semantic judgment and adaptive execution -> Agent guided by a Skill.
- Domain knowledge, examples, and edge cases -> Skill References.
- Deterministic, testable operations -> Tools or scripts.
- Permissions, persistence, irreversible actions, and objective invariants ->
  application code.

The main Agent must retain the complete task objective and discoverable access
to relevant inputs, Skills, References, Tools, evidence, and outputs.

When Agent behavior fails, first improve Skill discovery, instructions,
References, context, Tool feedback, and Evals. Do not turn an observed model
error directly into permanent application control flow.

## Official references

- Claude Agent SDK overview:
  <https://code.claude.com/docs/en/agent-sdk/overview>
- Use Claude Code features in the SDK:
  <https://code.claude.com/docs/en/agent-sdk/claude-code-features>
- Agent Skills in the SDK:
  <https://code.claude.com/docs/en/agent-sdk/skills>
- Skill authoring best practices:
  <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>
- OpenAI Build skills:
  <https://developers.openai.com/codex/skills>

---
name: convert-thesis
description: M0 discovery marker for the future DocFit thesis conversion workflow.
---

# Convert Thesis — M0 Boundary

This Skill exists in M0 to prove native Claude Agent SDK Skill discovery.

During M0:

- never claim that a real DOCX operation is implemented;
- use only `AskUserQuestion` and the five registered DocFit MCP Tools;
- for the image smoke, call `mcp__docfit__docx_visual_review` with
  `{"mode": "m0_image_smoke"}` and inspect the returned image;
- interpret Tool results in the Agent session;
- when a Tool eventually returns `needs_input`, either inspect again or call
  `AskUserQuestion`; do not ask the application shell to invent another protocol.

The real conversion workflow remains outside M0.

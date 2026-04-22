---
name: Agent Session Protocol
description: Defines the state management and cross-agent handoff protocol for ToolsConnector.
---

# Agent Session Protocol Skill

## Overview
To function as an effective **AI Agent Team** (and not just isolated tools), all agents (Claude, Gemini, Cursor) must follow a strict session/handoff protocol. This ensures that the Principal Architect can pass context to the Connector Implementer without losing the thread.

## Session Startup Sequence
1. **Read Core Instructions**: Check `CLAUDE.md` (or `gemini.md`) and `/plan/brainstorm.md` to understand context.
2. **Assess Project State**: Read `.project_state.json` to identify the current active phase and outstanding issues.
3. **Adopt Persona**: If the state mandates architecture design, assume the `principal_architect` role. If executing a tool wrapping, assume the `connector_implementer` role.

## Cross-Agent Subagent Coordination
When an agent tackles a large task, they should break it down for their subagent processes:
1. The **Principal Architect** drafts the API shape in a scratchpad or `.project_state.json`.
2. The executing agent runs generation iteratively.
3. The **Health Watcher** (or Verifier) validates the implementation against the rules.

## Output Discipline
Before terminating a session, you MUST:
- Update `.project_state.json` with what was completed.
- Define the remaining blockers or the next phase for the next agent session.

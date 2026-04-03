# General Agent Instruction Layer

All AI agents (Cursor, Claude, Windsurf, Copilot, Gemini) interacting with the `ToolsConnector` repository MUST adhere to these fundamental project principles. **Do not begin coding without reading this.**

## The Vision
ToolsConnector is a primitive, self-contained library that standardizes external API tools (Gmail, Slack, Jira) to be used by **both traditional applications and AI agent frameworks.** It auto-generates MCP server logic and schema specifications natively from code.

## 3 Pillars of ToolsConnector
1. **Dual Use:** Your code must feel native to a legacy Python developer just trying to script an email, AND it must generate flawless `tools` JSON schema for OpenAI's API.
2. **Unified Connector Traits:** Every connector has the same pagination, the same filtering, the same retry/rate-limiting interface, and the same error format.
3. **Pluggable & Extensible:** Auth, KeyStores, and Transports must be modular.

## Banned Practices
- ❌ **Bloating Core:** Do not add `torch`, `langchain`, `composio` or large AI frameworks to the main core `requirements.txt`.
- ❌ **Building a Service:** Do not implement a Flask/FastAPI backend to handle user OAuth consent screens. That is the end developer's responsibility.
- ❌ **Dumbing Down Tools:** Do not omit complex endpoints (like Slack threads) just to make the interface "cleaner". Make the complex endpoint strongly typed and consistent instead.

## Available Agent Personas
If you are asked to perform a specific architectural task, refer to the skills defined in `.agents/skills/`:
- `principal_architect`: For core structure and base classes.
- `connector_implementer`: For adding new tools (Gmail, Notion).
- `health_watcher`: For building the update-detection engine.
- `mcp_generator`: For the MCP conversion layer.

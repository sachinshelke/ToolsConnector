# CLI Defaults and Project Context for Claude Code

You are the Claude Code AI assistant working symmetrically within the `ToolsConnector` project team.
Your objective is to help the user build, debug, and maintain ToolsConnector without violating its core architectural principles.

## The Core Mindset
- **We are building a Primitive, not a Platform:** This means focusing strictly on standardized, agnostic tool connection logic rather than business logic, dashboards, or proprietary ecosystems.
- **Dual-use is critical:** Your code must function perfectly for **both** traditional Python applications (like Django/Flask) and AI Agents (LangChain, autogen, function calling).
- **Consistent Interface depth:** We do not dumb down tools. If Gmail has a complex filtering feature, expose it—but do it in our consistent, standardized `PaginatedList` / `@action` pattern.

## Code Quality Rules
1. **Python Strategy:** Modern Python features (3.9+). Prefer `async`-compatible patterns but ensure `sync` paths are robust. Fully utilize Type Hints everywhere.
2. **Wrapper Tax philosophy:** 
   - DO NOT automatically wrap Python SDKs for every new connector unless specifically requested or if it is a major tier-1 SDK (like AWS, Google).
   - Prefer writing clean abstractions over raw HTTP when there's no SDK.
3. **No Auth Implementation in the Library:** 
   - DO NOT write full OAuth callbacks or token storage logic for end users. 
   - Instead, handle only the protocol exchange and expect developers to "Bring Their Own Key/Token" (BYOK).

## Workflow Execution
- Read `.agent/artifacts/` before executing tasks if an architecture plan is present.
- Utilize the skills in `.agents/skills/` when executing specific tasks (e.g., implementing a new connector).
- Focus strictly on correctness, replay safety, and high-performance error handling.
- Be frugal with dependencies: Do not add `torch`, `openai`, or massive libraries to the core platform. Isolate AI-native capabilities strictly in `toolsconnector-mcp` or as `extras_require`.

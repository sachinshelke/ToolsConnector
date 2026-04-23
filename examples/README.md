# ToolsConnector Examples

Copy-pasteable scripts that demonstrate every major integration pattern.
Each script is self-contained and runnable -- set the right environment
variables and go.

## Quick Start

```bash
pip install "toolsconnector[gmail]"
export TC_GMAIL_CREDENTIALS='your-oauth-token'
python examples/01_basic_usage.py
```

## Examples

| # | File | What it shows | Dependencies |
|---|------|---------------|-------------|
| 01 | `01_basic_usage.py` | Create a ToolKit, list tools, execute an action | `toolsconnector[gmail]` |
| 02 | `02_mcp_server.py` | One-line MCP server for Claude Desktop / Cursor | `toolsconnector[mcp,gmail,slack]` |
| 03 | `03_openai_function_calling.py` | Full tool-use loop with OpenAI GPT-4 | `toolsconnector[github]`, `openai` |
| 04 | `04_anthropic_tool_use.py` | Full tool-use loop with Anthropic Claude | `toolsconnector[slack]`, `anthropic` |
| 05 | `05_multi_connector.py` | Five connectors + safety filtering + multi-framework schemas | `toolsconnector[gmail,slack,github,notion,jira]` |
| 06 | `06_cli_usage.sh` | `tc` CLI: list connectors, run actions, start servers | `toolsconnector[gmail]` |
| 07 | `07_multi_tenant.py` | Per-user isolated ToolKits via ToolKitFactory | `toolsconnector[gmail,slack]` |
| 08 | `08_rest_api.py` | Expose connectors as a REST API (Starlette + uvicorn) | `toolsconnector[rest,gmail,slack]` |
| 09 | `09_health_check.py` | CI/CD health checks, spec extraction, OpenAPI generation | `toolsconnector[gmail,slack,github]` |
| 10 | `10_linkedin_publish.py` | Publish a post to LinkedIn end-to-end (auth → compose → post) | `toolsconnector[linkedin]` |

## Environment Variables

Every connector reads its credentials from `TC_{CONNECTOR}_CREDENTIALS`:

```bash
export TC_GMAIL_CREDENTIALS='your-oauth-token'
export TC_SLACK_CREDENTIALS='xoxb-your-bot-token'
export TC_GITHUB_CREDENTIALS='ghp_your-personal-access-token'
export TC_NOTION_CREDENTIALS='ntn_your-integration-token'
export TC_JIRA_CREDENTIALS='your-api-token'
```

For OpenAI/Anthropic examples, you also need:

```bash
export OPENAI_API_KEY='sk-your-key'
export ANTHROPIC_API_KEY='sk-ant-your-key'
```

## Safety

Several examples use `exclude_dangerous=True` and `include_actions` to
restrict the ToolKit to read-only operations. This is the recommended
default when giving tools to AI agents -- start safe, then widen access
as needed.

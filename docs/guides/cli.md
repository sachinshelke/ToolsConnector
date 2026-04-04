# CLI Reference

ToolsConnector ships with the `tc` command-line tool. It is installed automatically as a console script when you install the package.

## Commands

### `tc list`

List all available connectors with their category and action count.

```bash
tc list
```

Example output:

```
Connector       Category          Actions
──────────────────────────────────────────
gmail           communication     8
slack           communication     8
github          code-platforms    10
jira            project-mgmt     8
stripe          finance           8
...
```

### `tc <connector> actions`

List all actions available on a specific connector.

```bash
tc gmail actions
```

Example output:

```
Action            Description                      Dangerous
─────────────────────────────────────────────────────────────
list_emails       List emails matching a query      No
get_email         Get a single email by ID          No
send_email        Send an email                     Yes
search_emails     Search emails with a query        No
list_labels       List Gmail labels                 No
create_draft      Create an email draft             No
delete_email      Delete an email by ID             Yes
modify_labels     Add or remove labels on an email  No
```

### `tc <connector> <action> --param value`

Execute a single action from the command line. Parameters are passed as `--key value` flags. Credentials are read from environment variables (`TC_{CONNECTOR}_CREDENTIALS`).

```bash
export TC_GITHUB_CREDENTIALS="ghp_your_token_here"

tc github list_repos --per_page 5
tc github get_repo --owner anthropics --repo toolsconnector
tc slack send_message --channel "#general" --text "Hello from tc"
```

Output is printed as formatted JSON.

For actions that take nested or complex parameters, pass JSON strings:

```bash
tc jira create_issue --project "PROJ" --summary "Bug report" --issue_type "Bug"
```

### `tc <connector> spec`

Export the full action schema for a connector. Useful for inspecting available parameters, types, and descriptions.

```bash
tc github spec
tc github spec --format json
tc github spec --format yaml
```

The default format is JSON. The schema includes every action with its parameter definitions, types, required flags, and descriptions.

### `tc serve mcp <connectors...>`

Start an MCP (Model Context Protocol) server that exposes the specified connectors as tools. Credentials are read from environment variables.

```bash
tc serve mcp gmail slack --transport stdio
tc serve mcp github jira --transport sse --port 3000
tc serve mcp gmail slack github --transport streamable-http --port 3000
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--transport` | `stdio` | Transport protocol: `stdio`, `sse`, or `streamable-http` |
| `--port` | `3000` | Port for HTTP-based transports |
| `--name` | `toolsconnector` | Server name reported to MCP clients |

Use `stdio` for Claude Desktop and Cursor integration. Use `sse` or `streamable-http` for network-accessible deployments.

### `tc serve rest <connectors...>`

Start a REST API server that exposes the specified connectors over HTTP.

```bash
tc serve rest gmail slack --port 8000
tc serve rest github jira --port 9000 --prefix /api/v1
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--port` | `8000` | Port to listen on |
| `--prefix` | `/api/v1` | URL path prefix for all endpoints |

The REST server exposes endpoints in the pattern `{prefix}/{connector}/{action}` accepting POST requests with JSON bodies.

## Environment Variables

The CLI reads credentials from environment variables following the pattern `TC_{CONNECTOR}_CREDENTIALS`:

```bash
export TC_GMAIL_CREDENTIALS="ya29.your-google-token"
export TC_SLACK_CREDENTIALS="xoxb-your-slack-bot-token"
export TC_GITHUB_CREDENTIALS="ghp_your_github_pat"
```

For connectors that require multiple credential fields (e.g., Datadog requires both API key and app key), pass a JSON string:

```bash
export TC_DATADOG_CREDENTIALS='{"api_key": "...", "app_key": "..."}'
```

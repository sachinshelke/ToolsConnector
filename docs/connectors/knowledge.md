# Knowledge

Connectors for workspace knowledge bases, wikis, and documentation. 2 connectors, 49 actions.

---

### Notion

**Category:** Knowledge | **Auth:** Bearer Token (Internal Integration) | **Actions:** 24

Connect to Notion to manage pages, databases, blocks, comments, and users. Search across shared content, run filtered database queries, append rich content blocks, and thread comments via `discussion_id`. Pinned to `Notion-Version: 2022-06-28` for stability.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| search | Search pages and databases in the workspace | No |
| get_page | Get a single page by ID | No |
| create_page | Create a new page | Yes |
| update_page | Update page properties | No |
| archive_page | Archive (soft-delete) a page | Yes |
| restore_page | Restore an archived page | No |
| get_page_property | Get a page property value by ID | No |
| get_database | Get a database schema and metadata | No |
| create_database | Create a new database | Yes |
| update_database | Update a database's title, description, or properties | No |
| query_database | Query a database with optional filters and sorts | No |
| get_block | Get a single block by ID | No |
| get_block_children | Get child blocks of a page or block | No |
| append_block_children | Append child blocks to a page or block | Yes |
| update_block | Update a block's content | No |
| delete_block | Delete a block | Yes |
| list_users | List all users in the workspace | No |
| get_user | Get a single user by ID | No |
| get_me | Get the bot user associated with the integration token | No |
| list_comments | List comments on a block or page | No |
| add_comment | Add a comment to a page or discussion thread | Yes |
| get_comment | Get a single comment by ID | No |
| update_comment | Update a comment's text | No |
| delete_comment | Delete a comment | Yes |

**Quick start:**

```python
kit = ToolKit(["notion"], credentials={"notion": "secret_or_ntn_your-token"})
# Verify the integration is authed and learn its bot identity
me = kit.execute("notion_get_me", {})
```

**Extras required:** `pip install "toolsconnector[notion]"`

**Credentials.** Pass the integration token via `credentials={"notion": "..."}` to `ToolKit`, or set `TC_NOTION_CREDENTIALS` in the environment. To run multiple Notion workspaces in the same process, instantiate a separate `ToolKit` per credential. See the [Credentials Guide](../guides/credentials.md) for the universal pattern.

### Common workflows

**Database row CRUD** — `create_page` under a database parent inserts a row; `query_database` with `filter`/`sorts` retrieves matching rows; `update_page` modifies properties.

**Append blocks to a page** — `append_block_children(block_id=page_id, children=[...])` adds new blocks. Nested children are supported in a single request.

**Thread comments via `discussion_id`** — first call `add_comment(page_id=..., text=...)` to start a thread; the returned comment carries a `discussion_id`. Pass that into subsequent `add_comment(page_id=..., text=..., discussion_id=...)` calls to reply within the same thread.

**Paginated search** — `search(query="...", filter_type="page", limit=20)` returns at most 100 items per call. Follow `result.page_state.cursor` for the next page; `has_more=False` when done.

### Troubleshooting

**404 on a page that should exist** — Notion returns 404 for both "doesn't exist" AND "not shared with this integration" (ambiguous by design). The connector's `NotFoundError.suggestion` field directs you to the fix: open the page in Notion → `...` menu → **Connections** → add your integration.

**403 on a write action** — Your integration's capability profile is missing the required permission. The connector's `PermissionDeniedError.suggestion` and `e.details["notion_code"] == "restricted_resource"` make this explicit. Edit the integration at https://www.notion.so/my-integrations and enable the missing capability (Update content, Insert content, etc.).

**`add_comment` returns 403** — Either the integration lacks **Insert comments** capability OR the target page isn't shared with the integration. Both fixes documented in the connector's [README](../../src/toolsconnector/connectors/notion/README.md).

**`update_block` succeeds in Notion's UI but fails via API** — Some block types (`column_list`, `synced_block` source-side, `child_page`) are read-only via the API regardless of capabilities. Notion returns 400 with `validation_error`; the connector surfaces the field-level reason via `e.details["notion_message"]`.

**MCP tool exposure debug** — `tc serve mcp notion --transport stdio` starts the server on stdin; pipe a `tools/list` request to confirm what's exposed. With `--exclude-dangerous`, only the 17 read-only actions appear; without it, all 24.

**Version-pin trap** — Do NOT bump `Notion-Version` past `2022-06-28` without a connector major-version release. The 2025-09-03 split of databases into `databases` + `data_sources` and the 2026-03-11 `archived` → `in_trash` rename are both breaking. See the connector's [Versioned API](../../src/toolsconnector/connectors/notion/README.md#versioned-api) section.

---

### Confluence

**Category:** Knowledge | **Auth:** API Token (Atlassian) | **Actions:** 25

Connect to Confluence to manage spaces, pages, blog posts, attachments, and comments. Atlassian REST v2 API with email + API token authentication.

**Actions:** see the [connector README](../../src/toolsconnector/connectors/confluence/README.md) for the full action table.

**Quick start:**

```python
kit = ToolKit(
    ["confluence"],
    credentials={"confluence": "email@example.com:your-api-token"},
)
kit.execute("confluence_list_spaces", {})
```

**Extras required:** `pip install "toolsconnector[confluence]"`

---

## When to pick which

- **Notion** — best for fast-moving, internal team wikis, project trackers, and CRM-style databases. Block-based content model makes rich structured documents easy to query programmatically. Integration tokens are simpler to provision than OAuth.
- **Confluence** — best for enterprise documentation with formal page hierarchies, version history, and Atlassian SSO integration. Pairs naturally with Jira for engineering teams.

Both are **BYOK** — you bring your own integration token / API token. ToolsConnector does not store credentials.

## See also

- [Notion connector README](../../src/toolsconnector/connectors/notion/README.md) — full action reference, capability table, verification status
- [Confluence connector README](../../src/toolsconnector/connectors/confluence/README.md)
- [MCP server guide](../guides/mcp-server.md) — exposing Notion/Confluence to Claude Desktop, Cursor, and other MCP clients
- [Credentials guide](../guides/credentials.md) — general BYOK patterns across connectors

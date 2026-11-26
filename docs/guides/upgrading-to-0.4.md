# Upgrading to 0.4

0.4.0 is a safety and reliability release. It has no new connectors, and the changes below can affect existing code.

**Upgrade soon if you use Outlook, Teams, GitHub or Docker Hub.** Earlier releases sent your access token to any next-page URL a caller supplied.

| Change | What to do |
|---|---|
| Python 3.10 or later | Upgrade Python. On 3.9, pip keeps installing 0.3.25 |
| `mcp` is pinned to `>=1.10,<2` | Reinstall: `pip install -U "toolsconnector[mcp]"` |
| Missing credentials raise `MissingConfigError` on the first call | Catch it where you caught a 401, or set the credential it names |
| `dry_run=True` runs only actions declared as reads | Expect a preview from every other action, and `ValidationError` for invalid arguments |
| Incomplete pages raise `PaginationNotWiredError` | In your own connectors, set `_fetch_next` on every page that has more |
| Okta and Confluence `page_state.cursor` is the bare cursor | Stop parsing it as a URL |
| `LocalFileKeyStore` needs an extra | `pip install "toolsconnector[local-keystore]"` |
| Unencrypted key files raise `LegacyKeyFileError` | Open once with `migrate_legacy=True`, then rotate those credentials |

## New

MCP clients now receive `readOnlyHint` and `destructiveHint` for every action whose access is declared. Actions with no declared access get no hint, so clients assume the worst case.

Full list: [changelog](https://github.com/sachinshelke/ToolsConnector/blob/main/CHANGELOG.md).

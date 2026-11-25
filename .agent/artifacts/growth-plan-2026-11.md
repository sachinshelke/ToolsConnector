# Growth plan (2026-11-25)

Owner go-ahead: build tool search, harden, and record the rest to pick up soon.

## Built on `feat/tool-search`
- Tool search: `--mode direct|search|auto`, `--tools`, `--read-only`, `ToolKit.search_tools`, `arun_tool`,
  `to_anthropic_search_tools`, `to_openai_search_tools` (OpenAI shape from docs, not run against the API).
- No resend of writes with an unknown outcome. Webhook private-address and redirect guards.
- 7 always-crashing actions fixed (Cloudflare 4, Mixpanel 3); conformance test for missing `self.*`.

## Next, in order
1. Per-connector `base_url` + refuse placeholder hosts (Jira, Confluence, Salesforce, Supabase, MongoDB, Redis).
2. Merge `docs/0.4.0-upgrade` (no conflicts with this branch at the time of writing).
3. Classify the 871 actions with no `access`. Until then they all fall under `tc_run_destructive`.
4. Prebuilt index + lazy connector load (all 79: 2.8 s server startup in search mode).
5. Result size cap with "get more".
6. Publish allowed values (`enum`): 0 of 3,823 parameters have one.
7. OAuth: merge the Google branch; `tc auth login/status/logout` writing to the OS keychain, never printing a
   token and never via MCP. Narrows D00000J and the CLAUDE.md no-token-storage rule; D00000H still holds.
8. Connect vendor MCP servers through `tc`, labelled vendor-maintained, in the same search.
9. Cross-check overlapping connectors against OpenConnector v1.9.4 (plain Apache-2.0; never later versions).
10. Golden search set to 100+ queries. Known misses: "list my google tasks", "subscribe someone to mailchimp list".

## TypeScript
- Today: any TS app can spawn `tc serve mcp`. Native SDK: Stripe, GitHub, Notion, Slack only, zero dependencies,
  13.7 KB gzipped in total; not on npm.
- Next: subpath exports (`@toolsconnector/sdk/stripe`), tool schemas + search in TS generated from the same bindings,
  then bind connectors one at a time by demand. Do not hand-write TS connectors.
- Owner: npm scope + login.

## Do not build
Hosted service, token custody, dashboard, single run-anything tool, bulk port of 1,700 connectors.

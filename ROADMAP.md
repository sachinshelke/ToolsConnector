# ToolsConnector Roadmap

A living document. Reflects current priorities, not commitments.

## Philosophy

ToolsConnector is a **primitive, not a platform**. Every roadmap item is evaluated against these principles:

1. **BYOK first** — users bring their own credentials. We never run a shared OAuth app or token vault.
2. **Dual-use** — everything that works for async Python agents must also work for sync Python apps (Django, Flask, scripts). No async-only features.
3. **Consistent interface depth** — we expose the full power of each tool through the same `@action` pattern. No lowest-common-denominator.
4. **Honest quality claims** — "verified" means something specific (see the `Verification tiers` section below).
5. **Small dependency surface** — core stays on `pydantic` + `httpx` + `docstring-parser`. New capabilities land as optional extras or companion packages.

---

## Verification tiers

Every connector in the registry falls into one of these tiers:

| Tier | Criteria | Example |
|---|---|---|
| **Tier 1 — Live verified** | Doc-verified AND tested against the real vendor API with a real token. | `linkedin` (3 of 8 actions live-verified as of 2026-04); `notion` (**all 24 of 24 actions + full error matrix live-verified as of 2026-05-14**) |
| **Tier 2 — Doc verified** | Every endpoint, header, scope, and body shape cross-checked against the vendor's canonical docs and verified with respx mocks. | `x` (Twitter) |
| **Tier 3 — Pattern correct** | Code reads sensibly, matches documented API patterns from public knowledge, but no active doc or live verification has happened. This is where most of the 68 connectors currently sit. | `medium`, the 14 AWS connectors, the 51 pre-existing ones |

The goal is to progressively promote connectors from Tier 3 → Tier 2 → Tier 1. The CHANGELOG tracks which connectors moved tiers in each release.

---

## In progress (next release)

### Documentation: `Getting credentials` per connector
Each connector's README gets a `Getting credentials` section explaining exactly how to obtain a token for that service (which developer portal, which scopes, how to regenerate). Zero new library code — pure docs. Unblocks onboarding for every BYOK user without introducing OAuth flow complexity.

### Doc-verification sweep for the top 10 connectors
Apply the same `WebFetch → compare → respx-verify` treatment used for LinkedIn and X to the 10 highest-value connectors. Target: move all 10 from Tier 3 → Tier 2.

- ✅ `gmail`, `slack`, `github` — respx-verified against canonical vendor docs (Tier 2)
- ✅ `notion` — **Fully Tier 1 — all 24 of 24 actions + complete error matrix live-verified (2026-05-14)**. End-to-end live runs against a real workspace covered every action including the database CRUD chain (`get_database`, `create_database`, `update_database`, `query_database` with filter+sort), the comment lifecycle (top-level and threaded via `discussion_id`), all block CRUD, all page CRUD + archive/restore, page-property fetches, and identity (`get_me`, `list_users`, `get_user`). The typed-error mapping was also verified against real Notion responses: real 404 → `NotFoundError`, real 400 → `ValidationError`, real 401 → `InvalidCredentialsError`. Live testing uncovered + fixed **3 bugs respx alone would not have caught**: (1) `search` crashing on mixed page/database results; (2) `parse_page` defensiveness against unknown property shapes; (3) `add_comment(discussion_id=...)` sending the wrong body envelope (top-level `discussion_id` is required, not `parent.discussion_id`). 24 actions, 89 respx tests + 1 MCP-subprocess integration test, 97.6% coverage. Pinned to `Notion-Version: 2022-06-28`. See [docs/connectors/knowledge.md](docs/connectors/knowledge.md) and [examples/11_notion_workflow.py](examples/11_notion_workflow.py).
- ✅ `linear` — **Fully Tier 1 — 16 of 19 actions live-verified against `api.linear.app` (2026-05-23)**. Live run covered the full issue CRUD chain, comment add/list with unicode round-trip, label create, search via the new `searchIssues(term:)` op, all team/user/project/workflow-state/cycle/label discovery, and pagination through `pageInfo.endCursor`. 3 actions remain Doc verified intentionally: `update_project` / `delete_project` would mutate real user projects; `get_cycle` requires an active sprint in the test workspace (the introspect probe confirmed the query is structurally and schematically correct). Live testing uncovered + fixed **5 bugs respx alone would not have caught**: (1) `list_cycles` HTTP-400ing on phantom `scopeCount` / `completedScopeCount` fields; (2) `search_issues` failing with `INPUT_ERROR: deprecated` because `issueSearch(query:)` is gone — migrated to `searchIssues(term:)`; (3) `Team.private` field deprecation — migrated to `visibility` with backwards-compatible parsing; (4) `Project.state` field deprecation — migrated to `status { type }` with backwards-compatible parsing; (5) initial respx mocks accepted these stale shapes, masking all four. Closing the gap pinned a new pattern: a live **schema introspection sweep** that confirms every selected field + every called operation is non-deprecated against the live API. 19 actions, 75 respx tests + 1 schema-sweep verification script. The connector uses `ProtocolType.GRAPHQL` with raw httpx (GraphQL adapter abstraction still on backlog). See [src/toolsconnector/connectors/linear/README.md](src/toolsconnector/connectors/linear/README.md).
- ⏳ `jira`, `stripe`, `hubspot`, `asana`, `mongodb` — remaining

---

## Planned (committed, 3–6 months out)

### `[auth]` optional extra — OAuth 2.0 flow helper

**Goal**: let developers who've already created their own OAuth app (LinkedIn / X / Gmail / Slack / etc.) execute the authorization-code dance from Python without writing OAuth code themselves. Returns the access token + refresh token to the caller. Does not store them.

```python
# pip install "toolsconnector[auth]"
from toolsconnector.auth import OAuth2Flow

flow = OAuth2Flow.for_connector(
    "linkedin",
    client_id=os.environ["LINKEDIN_CLIENT_ID"],
    client_secret=os.environ["LINKEDIN_CLIENT_SECRET"],
    scopes=["openid", "profile", "email", "w_member_social"],
)
token = flow.run()  # opens browser, returns AccessToken(access_token=..., refresh_token=..., expires_at=...)

kit = ToolKit(["linkedin"], credentials={"linkedin": token.access_token})
```

**Scope discipline** (keeps this a primitive, not a platform):

- ✅ BYOK philosophy preserved — users supply their own app credentials
- ✅ Core library unchanged; `toolsconnector.auth` module only loads when `[auth]` extra is installed
- ✅ Supports interactive mode (browser + local callback) AND manual mode (paste-the-code, for CI/SSH)
- ✅ Reuses the existing underused `AuthSpec` / `OAuthSpec` types in `spec/auth.py`
- ❌ No token storage / vault. We return the token; caller decides where it lives.
- ❌ No auto-refresh. Caller must explicitly call `flow.refresh(refresh_token)`.
- ❌ No shared OAuth apps. Ever.
- ❌ No multi-user/tenant features. Those belong in the caller's application.

**Concrete work**:
1. Build `toolsconnector.auth.OAuth2Flow` with Authorization Code + PKCE support (~400 lines + ~200 lines of respx-mocked tests)
2. Add `auth_spec = OAuth2Spec(...)` declarations to each OAuth-based connector (~5 lines × ~35 connectors)
3. Add `tc auth <connector>` CLI command for ergonomics (~80 lines)
4. Document in `docs/guides/authentication.md` with a worked example per major flow variant

### Live-verification sweep for top 10 connectors
Once `[auth]` exists, getting a token for Gmail / Slack / GitHub / etc. takes 10 seconds, making live verification (the LinkedIn treatment) cheap. Target: all 10 Tier-2 connectors promoted to Tier 1.

---

## Considered, not committed

### `toolsconnector-cloud` — hosted MCP gateway (separate package)
If enough users ask for "a single URL to give my LLM client that has all my configured connectors", we ship a companion package similar to `toolsconnector-mcp`. Would NOT live in the core repo. Only if strong user demand; risk is scope creep away from the primitive.

### Integration test harness with VCR fixtures
A per-connector live-test pattern (like `examples/10_linkedin_publish.py` but formalized). Would unlock automated regression testing against recorded fixtures. Only after the top 10 live-verifications prove the pattern.

### GraphQL-native connectors (beyond REST/JSON)
`ProtocolType.GRAPHQL` is now used by the Linear connector (raw httpx POST to `/graphql`, see `connectors/linear/connector.py`). The next natural step is extracting the request/response/error-mapping pattern into a `GraphQLAdapter` so a GitHub v4 (and any future GraphQL connector) doesn't reinvent the wheel. Deferred until a second GraphQL connector creates the actual need.

---

## Explicitly not planned

These have been evaluated and rejected, to keep the project a primitive:

- ❌ **Shared OAuth apps** — we will never run a "ToolsConnector LinkedIn app" that users authorize. Always BYOK.
- ❌ **Token storage service** — no cloud key vault, no "ToolsConnector.cloud" credential manager.
- ❌ **Dashboard / admin UI for connector management** — that's a platform. The static site at toolsconnector.github.io is a catalogue, not an admin UI.
- ❌ **Built-in rate-limiting / proxying service** — users bring their own (nginx, Cloudflare, infrastructure). We return OpenTelemetry signals if asked.
- ❌ **Proprietary runtime / execution environment** — the library runs in the user's Python process. Period.

---

## How to influence this roadmap

Open an issue on [the GitHub repository](https://github.com/sachinshelke/ToolsConnector/issues) with:
1. What you want
2. Your actual use case (not a generic ask)
3. Whether it fits any of the `Explicitly not planned` items above — if so, why it's worth reconsidering

Maintainers read every issue and update this document as direction changes.

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

- ✅ `gmail`, `slack` — respx-verified against canonical vendor docs (Tier 2)
- ✅ `github` — **Fully Tier 1 — 33 of 37 actions live-verified against `api.github.com` (2026-05-27)**. Live run covered the full lifecycle on a throwaway repo (create → read → update → delete) including file CRUD with unicode + base64 round-trip, full issue lifecycle (create / get / update / comment / label / unlabel / close), branches + commits + releases, gists, search across all three global endpoints (code/repos/issues), star/unstar, and authenticated-user identity. 4 actions remain Probe verified intentionally because they require multi-repo or multi-branch setup the connector doesn't expose primitives for: `fork_repo` (would leave a fork behind), `create_pull_request` / `merge_pull_request` (need a non-default branch — connector doesn't expose git/refs), `trigger_workflow` (needs a committed workflow file). All 4 probe requests returned the expected `NotFoundError`/`ValidationError`, confirming the REST envelopes are accepted by GitHub's server. Live testing uncovered + fixed **2 real bugs respx alone would not have caught**: (1) **URL path-traversal vulnerability** — f-string interpolation of `owner`/`repo`/etc. allowed `owner="../admin"` to collapse `/repos/../admin/repo` to `/admin/repo` via httpx normalization, escaping out of the intended URL prefix; fixed by adding a `_p()` percent-encoding helper applied at every interpolation site. Not exploitable on GitHub today (no sensitive `/admin/...` endpoint) but a real defense-in-depth gap. (2) **Secondary rate-limit silent classification** — GitHub returns HTTP 403 (not 429) for BOTH primary (`X-RateLimit-Remaining: 0`) and secondary (`Retry-After` / `"abuse detection"` body) rate limits; the shared `raise_typed_for_status` mapped 403 → `PermissionDeniedError`, hiding the rate-limit semantics. Added GitHub-specific override in `_request` that detects both signals BEFORE the generic mapping and raises typed `RateLimitError` with computed `retry_after_seconds`. Also added **6 GitHub token prefixes** (`ghp_`, `github_pat_`, `gho_`, `ghs_`, `ghu_`, `ghr_`) to the shared credential-redaction regex used by `http_errors.py` + CI secret-scan + pre-commit hook. 37 actions, 80 respx tests + 1 MCP-subprocess integration verification, transport-error mapping (ConnectError/Timeout/TransportError → typed), explicit `extra="ignore"` on all 17 response models, `add_labels` return type upgraded from `list[dict]` to `list[GitHubLabel]`. See [src/toolsconnector/connectors/github/README.md](src/toolsconnector/connectors/github/README.md).
- ✅ `notion` — **Fully Tier 1 — all 24 of 24 actions + complete error matrix live-verified (2026-05-14)**. End-to-end live runs against a real workspace covered every action including the database CRUD chain (`get_database`, `create_database`, `update_database`, `query_database` with filter+sort), the comment lifecycle (top-level and threaded via `discussion_id`), all block CRUD, all page CRUD + archive/restore, page-property fetches, and identity (`get_me`, `list_users`, `get_user`). The typed-error mapping was also verified against real Notion responses: real 404 → `NotFoundError`, real 400 → `ValidationError`, real 401 → `InvalidCredentialsError`. Live testing uncovered + fixed **3 bugs respx alone would not have caught**: (1) `search` crashing on mixed page/database results; (2) `parse_page` defensiveness against unknown property shapes; (3) `add_comment(discussion_id=...)` sending the wrong body envelope (top-level `discussion_id` is required, not `parent.discussion_id`). 24 actions, 89 respx tests + 1 MCP-subprocess integration test, 97.6% coverage. Pinned to `Notion-Version: 2022-06-28`. See [docs/connectors/knowledge.md](docs/connectors/knowledge.md) and [examples/11_notion_workflow.py](examples/11_notion_workflow.py).
- ✅ `linear` — **Fully Tier 1 — 16 of 19 actions live-verified against `api.linear.app` (2026-05-23)**. Live run covered the full issue CRUD chain, comment add/list with unicode round-trip, label create, search via the new `searchIssues(term:)` op, all team/user/project/workflow-state/cycle/label discovery, and pagination through `pageInfo.endCursor`. 3 actions remain Doc verified intentionally: `update_project` / `delete_project` would mutate real user projects; `get_cycle` requires an active sprint in the test workspace (the introspect probe confirmed the query is structurally and schematically correct). Live testing uncovered + fixed **5 bugs respx alone would not have caught**: (1) `list_cycles` HTTP-400ing on phantom `scopeCount` / `completedScopeCount` fields; (2) `search_issues` failing with `INPUT_ERROR: deprecated` because `issueSearch(query:)` is gone — migrated to `searchIssues(term:)`; (3) `Team.private` field deprecation — migrated to `visibility` with backwards-compatible parsing; (4) `Project.state` field deprecation — migrated to `status { type }` with backwards-compatible parsing; (5) initial respx mocks accepted these stale shapes, masking all four. Closing the gap pinned a new pattern: a live **schema introspection sweep** that confirms every selected field + every called operation is non-deprecated against the live API. 19 actions, 75 respx tests + 1 schema-sweep verification script. The connector uses `ProtocolType.GRAPHQL` with raw httpx (GraphQL adapter abstraction still on backlog). See [src/toolsconnector/connectors/linear/README.md](src/toolsconnector/connectors/linear/README.md).
- ✅ **`gdocs`** — **Fully Tier 1 — all 5 of 5 actions live-verified against `docs.googleapis.com` (2026-05-28)**. End-to-end live run covered the full lifecycle on a throwaway document: `create_document` → `get_document` (metadata round-trip) → `get_document_text` (empty body returns `"\n"`) → `insert_text` (with unicode `你好 🚀` round-trip) → `get_document_text` (verifies content persisted) → `batch_update` (multi-request envelope) → real 404 → typed `NotFoundError`. Cleanup deleted the throwaway via Drive API (HTTP 204), zero artifacts left. Live testing also uncovered + fixed **1 real production bug respx alone would not have caught**: `insert_text` was calling `self.batch_update` (the auto-installed sync wrapper bound after `__init__`) instead of `self.abatch_update`; any async caller would get `TypeError: object BatchUpdateResponse can't be used in 'await' expression`. 5 actions, 26 respx tests + 1 MCP-subprocess integration verification. URL-path `_p()` percent-encoding helper protects against the same path-traversal class GitHub had. Transport-error mapping (ConnectError/Timeout/TransportError → typed). Explicit `extra="ignore"` on both response models. See [src/toolsconnector/connectors/gdocs/README.md](src/toolsconnector/connectors/gdocs/README.md).
- ✅ **`gsheets`** — **Fully Tier 1 — all 16 of 16 actions live-verified against `sheets.googleapis.com` (2026-05-28; re-verified end-to-end through MCP stdio transport 2026-05-29)**. End-to-end live run on a throwaway spreadsheet covered the full action surface: `create_spreadsheet` (multi-tab), `get_spreadsheet` + `get_sheet_metadata` (round-trip), values CRUD (`update_values`, `get_values` with unicode `你好 🚀` round-trip, `batch_get_values`, `append_values`, `batch_update_values`, `clear_values`), tab management (`add_sheet`, `rename_sheet`, `merge_cells`, `auto_resize_columns`, `copy_sheet`, `delete_sheet`), generic structural mutation (`batch_update_spreadsheet`). Cleanup deleted the throwaway via Drive API (HTTP 204), zero artifacts. 16 actions, 36 respx tests + 1 MCP-subprocess integration verification. **MCP smoke surfaced + fixed an additional production bug**: `tc serve mcp` printed a startup banner ("Starting MCP server with N tools...") to **STDOUT** — corrupting the JSON-RPC channel for the default stdio transport. Every Claude Desktop / Cursor / VS Code MCP user connecting via stdio would see a JSONDecodeError on the first message and have the session dropped. Fixed by routing the banner to stderr (banner is informational; stdout is the wire protocol). 2 new tests in `tests/unit/test_serve_cli.py` pin the contract. Same hardening as gdocs: transport-error mapping, `_p()` percent-encoding helper, explicit `extra="ignore"` on all 7 response models. Cross-cutting Google-token redaction (`ya29.*` + `AIza*`) applies. See [src/toolsconnector/connectors/gsheets/README.md](src/toolsconnector/connectors/gsheets/README.md).
- ✅ **`gcalendar`** — **Fully Tier 1 — 17 of 20 actions live-verified + 3 envelope-verified via bogus-ID probe (2026-05-29)**. End-to-end live run on a throwaway secondary calendar covered: event lifecycle (create/get/update/delete with unicode `你好 🚀` round-trip), quick-add via natural language, recurring event with real RRULE `FREQ=WEEKLY;COUNT=3` returning 3 expanded instances, move_event between calendars, full ACL CRUD (add/list/remove), free/busy lookup, color enumeration. The 3 previously probe-skipped (`subscribe_calendar`, `unsubscribe_calendar`, `clear_calendar`) are envelope-verified — bogus calendar IDs return typed `NotFoundError` from Google, proving the connector's request envelope is correctly built; full happy-path live verification skipped intentionally because those actions would alter the user's persistent calendarList or erase real primary-calendar events. Cleanup deleted throwaway calendar via Calendar API DELETE (HTTP 204), zero artifacts. 20 actions, 42 respx tests + 1 live-verify script + 1 envelope-probe script. Same hardening as gdocs/gsheets (transport wrap, `_p()` helper, `extra="ignore"` on all 10 response models). See [src/toolsconnector/connectors/gcalendar/README.md](src/toolsconnector/connectors/gcalendar/README.md).
- ✅ **`gdrive`** — **Fully Tier 1 — 20 of 22 actions live-verified + 2 envelope-verified via probe (2026-05-29)**. End-to-end live run on a throwaway folder covered: full file CRUD (upload with unicode metadata, get, download with unicode `你好 🚀` content round-trip, update, copy, move, delete), folder management, search via Drive query DSL, sharing CRUD (public-link `type="anyone"` + permission get + delete), comment CRUD (unicode), revision history (Drive auto-creates revisions; verified read-back), storage quota lookup. The 2 previously probe-skipped are envelope-verified: `export_file` with a bogus file ID returns typed `NotFoundError`; `empty_trash` returns the spec-compliant HTTP 204 No Content (Drive returns 204 whether trash had content or was already empty, so this verifies envelope acceptance — there is no way to non-destructively distinguish the two states server-side). Cleanup deleted the throwaway folder (Drive cascades to all contents), zero artifacts. **Live verification surfaced + fixed 2 real production bugs respx alone had silently accepted**: (1) **`upload_file` always failed with HTTP 400** — multipart body declared `Content-Transfer-Encoding: base64` but actually sent raw decoded bytes. Fixed by removing the spurious header. (2) **`share_file` failed for `type="anyone"` and `type="domain"`** — unconditionally included `emailAddress` in the permission body. Fixed with type-aware field mapping. New `convert_to_google_docs` kwarg on `upload_file` lets callers ask Drive to auto-convert Word/Excel/PowerPoint uploads to Google native formats during the multipart write. 22 actions, 41 respx tests + 1 live-verify script + envelope probes. Same Phase A hardening as gdocs/gsheets/gcalendar. See [src/toolsconnector/connectors/gdrive/README.md](src/toolsconnector/connectors/gdrive/README.md).
- ✅ **`gtasks`** — **Fully Tier 1 — all 13 of 13 actions live-verified against `tasks.googleapis.com` (2026-05-29)**. End-to-end live run on a throwaway task list covered the full lifecycle: `list_task_lists` (baseline), `create_task_list` (throwaway), `get_task_list` (round-trip), `update_task_list` (rename via PATCH), `list_tasks` (empty new list), `create_task` × 2 (with due date + notes), `get_task` (round-trip), `update_task` (extend due date), `move_task` (reparent — sub-task under parent), `complete_task` (status → completed), `clear_completed` (wipe done), `delete_task` (kill leftover), `delete_task_list` (cleanup). Throwaway list cleanly deleted, zero artifacts on user's account. MCP stdio dispatch also verified: tools/list (13 tools), tools/call `list_task_lists` (real API response through MCP JSON-RPC). **Live verification surfaced + fixed 1 real production bug respx alone had silently accepted**: `update_task_list` used HTTP PUT with a title-only body, but Google's `tasklists.update` endpoint requires a complete TaskList resource and returns 400. Fix: switched to HTTP PATCH (`tasklists.patch`) which accepts partial bodies — matching the connector's rename-only intent. New regression test pins PATCH. 13 actions, 30 respx tests + 1 live-verify script + 1 MCP smoke. Same Phase A hardening (transport wrap, `_p()` percent-encoding, `extra="ignore"`) as the rest of the GW batch. See [src/toolsconnector/connectors/gtasks/README.md](src/toolsconnector/connectors/gtasks/README.md).
- ✅ **`huggingface`** — **Fully Tier 1 — 24 of 30 actions live-verified against `router.huggingface.co` + the Hub API (2026-06-05)**. Live run covered the Hub surface (whoami, list/get models·datasets·spaces), OpenAI-compatible chat (incl. tool-calling + JSON mode), and the `hf-inference` task set: summarize, translate, fill-mask, text/token/zero-shot classification, QA, table-QA, embeddings (single **and batch**), sentence-similarity, and image classify/detect/segment. The remaining 6 (`text_generation`, `text_to_image`, `text_to_speech`, `image_to_text`, `automatic_speech_recognition`, `audio_classification`) are **partner-provider-dependent** by HF's multi-provider architecture — they route correctly and return a clean provider error; pass `provider=` (e.g. `fal-ai`) to a host that serves the model. Live testing + an adversarial re-test sweep uncovered + fixed **4 gaps respx alone would not have caught**: (1) `zero_shot_classification` parsed to empty because the router returns a score-sorted `[{label,score}]` list, not the classic `{sequence,labels,scores}` object; (2) `get_model`/`get_dataset` failed to parse because the Hub `307`-redirects legacy aliases (`bert-base-uncased` → `google-bert/bert-base-uncased`) and the client wasn't following redirects; (3) **cross-cutting** — the schema generator collapsed multi-type `Union`s to `"string"`, so the serve/MCP validator rejected batch lists ("expects string"); now rendered as `anyOf` (also unblocked Mistral batch embeddings + Gemini structured `contents`); (4) **cross-cutting** — the MCP handler annotated `anyOf` params as `"string"`, so FastMCP's Pydantic model would reject a batch list over stdio; now mapped to a `Union[...]` annotation. Resilience contract pinned: cold-start `503` → retry-eligible `ServerError`, `429` → `RateLimitError` + `retry_after`. Added `list_models` `pipeline_tag`/`library` filters and a **model/provider/cost discovery** surface: `list_inference_catalog` (the router `/v1/models` catalog with per-provider pricing + context + capability flags), `get_model_providers` (which providers serve a model + status, from `inferenceProviderMapping`), `list_repo_files` (repo file tree), and `get_model(expand=...)` (param counts, config, card metadata) — all live-verified. 30 actions, 46 respx tests + runtime/MCP union unit tests + 1 MCP-subprocess integration test + an adversarial fuzz/concurrency/Unicode live sweep. See [src/toolsconnector/connectors/huggingface/README.md](src/toolsconnector/connectors/huggingface/README.md).
- ⏳ `jira`, `stripe`, `hubspot`, `asana`, `mongodb` — remaining after Google batch

**AI/ML batch (2026-06-05):** added 5 AI provider connectors — `huggingface` (Tier 1, above), and `gemini` (19), `cohere` (22), `mistral` (30), `groq` (15) at **Tier 3 (pattern)** pending their own live-verification cycle. Catalog: 68 → 73 connectors, 1,402 → 1,518 actions; AI/ML category 3 → 8 connectors.

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

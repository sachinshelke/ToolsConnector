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
| **Tier 1 — Live verified** | Doc-verified AND tested against the real vendor API with a real token. | `linkedin` (3 of 8 actions live-verified as of 2026-04) |
| **Tier 2 — Doc verified** | Every endpoint, header, scope, and body shape cross-checked against the vendor's canonical docs and verified with respx mocks. | `x` (Twitter) |
| **Tier 3 — Pattern correct** | Code reads sensibly, matches documented API patterns from public knowledge, but no active doc or live verification has happened. This is where most of the 68 connectors currently sit. | `medium`, the 14 AWS connectors, the 51 pre-existing ones |

The goal is to progressively promote connectors from Tier 3 → Tier 2 → Tier 1. The CHANGELOG tracks which connectors moved tiers in each release.

---

## In progress (next release)

### Documentation: `Getting credentials` per connector
Each connector's README gets a `Getting credentials` section explaining exactly how to obtain a token for that service (which developer portal, which scopes, how to regenerate). Zero new library code — pure docs. Unblocks onboarding for every BYOK user without introducing OAuth flow complexity.

### Doc-verification sweep for the top 10 connectors
Apply the same `WebFetch → compare → respx-verify` treatment used for LinkedIn and X to the 10 highest-value connectors: `gmail`, `slack`, `github`, `notion`, `jira`, `stripe`, `hubspot`, `linear`, `asana`, `mongodb`. Target: move all 10 from Tier 3 → Tier 2.

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
The `ProtocolType.GRAPHQL` enum value exists but no connector uses it. Linear and GitHub v4 would benefit. Depends on someone encountering a compelling use case.

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

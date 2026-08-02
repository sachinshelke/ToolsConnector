# OAuth Acquisition Flow — Tier A (Google) Plan

Status: PLAN (not built) · Created 2026-08-03 · Scope: Tier A only

## 1. Objective

Add a **token-acquisition** helper so developers stop hand-rolling the Google
OAuth 2.0 authorization-code dance. TC already handles everything *after* the
token exists (refresh + storage + per-request injection); the only missing
piece is *getting the first token*.

Principle (unchanged): **run the flow, return the tokens, never host a callback,
never store tokens centrally.** TC stays a client-side primitive with no cloud.

## 2. Scope

- **In scope:** the 6 Tier-A connectors — all Google — which already declare
  `AuthType.OAUTH2`: `gmail`, `gcalendar`, `gdrive`, `gdocs`, `gsheets`, `gtasks`.
- **Key insight:** these are **one flow (Google) + six scope sets**, not six
  integrations. Same `auth_url`, `token_url`, same quirks; only scopes differ.
- **Out of scope:** Tier B/C/D connectors; any hosted/callback service; any
  central token vault; the `google-*` dependency cleanup (fast-follow, §9).

## 3. Current state (verified from code)

- All 6 declare auth via `service_account_auth(...)` → `AuthType.OAUTH2`, but the
  helper only expects a **single pasted `access_token`** (BYOK). No `auth_url` /
  `token_url` in the connector spec.
- `OAuth2Provider.refresh()` **already** implements `grant_type=refresh_token`
  (+ rotating-token handling + expiry buffer + keystore persistence).
- `KeyStore` protocol + 3 backends (InMemory / Env / encrypted LocalFile) already
  ship. Pluggable, no cloud.
- The 6 connectors use **pure httpx** for API calls — no Google SDK imported.
- `gdocs` README currently tells users to DIY the flow. That is the friction we
  are removing.

## 4. Tier A spec matrix

### Shared Google preset (all 6)

| Field | Value |
|---|---|
| Provider | Google |
| `auth_url` | `https://accounts.google.com/o/oauth2/v2/auth` |
| `token_url` | `https://oauth2.googleapis.com/token` |
| PKCE | S256 (supported) |
| Refresh | already implemented in `OAuth2Provider` |
| **Required extra params** | **`access_type=offline` + `prompt=consent`** — without these Google returns no refresh token |
| Client types | Desktop (loopback + PKCE) *or* Web (client_secret + web redirect) |

### Per-connector scopes (verified in each connector.py)

| Connector | Scopes |
|---|---|
| gmail | gmail.readonly, gmail.send, gmail.modify, gmail.labels |
| gcalendar | calendar, calendar.readonly |
| gdrive | drive, drive.file |
| gdocs | documents, documents.readonly |
| gsheets | spreadsheets, spreadsheets.readonly |
| gtasks | tasks, tasks.readonly |

## 5. Design (layered)

**Core (pure, no socket, respx-testable, works everywhere) — "the protocol exchange":**
- `begin(...) -> PendingAuth{ authorization_url, state, code_verifier }`
- `complete(pending, code, state) -> CredentialSet` (validates `state`; PKCE)

**Convenience (opt-in, touches OS) — Desktop only:**
- `login(...) -> CredentialSet` = open browser + one-shot loopback listener on
  127.0.0.1 + catch code + `complete()`.

Both feed the **existing** pipeline unchanged:
`CredentialSet → OAuth2Provider (auto-refresh) → KeyStore`.

Web apps use the core directly: their own `/oauth/callback` route calls
`complete()`. TC never runs a callback server on the public internet.

**Decision: cover BOTH (option C).** Desktop/loopback and Web both ship. They
reuse the same core, so this is sequenced, not doubled work:
- Slice 1: core `begin`/`complete` (serves Web immediately).
- Slice 2: `login()` loopback wrapper (Desktop).
Both land before Tier A is called done.

## 6. Google-specific decisions / gotchas (lock before build)

1. **`access_type=offline` + `prompt=consent` are mandatory** — the #1 correctness
   item; miss it and there is no refresh token, starving the whole refresh pipeline.
2. **Client-secret nuance:** Google "Desktop app" clients get a `client_secret`
   that is *not* truly confidential **and** use PKCE. So `OAuthConfig.client_secret`
   must be **Optional** and the flow must allow *secret present WITH PKCE*. (This is
   the earlier "public/confidential" fix; Google is the proof case.)
3. **Testing-mode refresh expiry:** if the developer's OAuth consent screen is in
   "Testing" status, refresh tokens **expire in 7 days**. Document (console setting).
4. **Sensitive-scope verification:** gmail.modify, drive, etc. need Google app
   verification for public distribution. Fine for BYOK/own-project/internal.
   Document-only, developer-side.

## 7. Backward compatibility

- Purely **additive**. New `tc.oauth` surface; nothing existing calls it.
- The one existing-type touch — `OAuthConfig.client_secret` required → Optional —
  is a **widening**; current callers (who always pass a secret) are unaffected.
- `OAuthConfig` is **not** in the SDK binding IR (`sdks/`, `codegen/`) → **no TS/Go
  regen**. Constructed only in 1 test + 1 docstring today.
- Existing "paste an access_token" BYOK path stays. Ships as a **minor** release.
  No user migration.

## 8. Dependency & weight analysis (incl. "user uses ALL connectors")

- OAuth engine = **httpx (core) + stdlib** (secrets, hashlib, base64, urllib,
  http.server, webbrowser). **Zero new runtime deps.**
- Weight is **independent of connector count** — the engine imports no connector.
- Base install stays **4 deps** regardless.
- "All connectors" weight comes only from **opt-in** extras (boto3, grpcio/protobuf,
  zeep, aiohttp/gql, google-cloud-storage) — the user's explicit choice, per extra.
- **No per-vendor OAuth library** — one protocol engine serves every OAuth tool.
- Net effect: OAuth can make TC **lighter** by justifying removal of the unused
  `google-*` trio (see §10).

## 9. Staying current — the OAuth config must never go stale

Endpoints, scopes and consent params drift over time (Google deprecates scopes,
tweaks consent behavior). The design keeps TC current without a release per change:

1. **Endpoints via OIDC discovery, not just hardcoded.** Google (and any OIDC
   provider) publishes `https://accounts.google.com/.well-known/openid-configuration`
   listing `authorization_endpoint` + `token_endpoint`. Fetch + cache at connect
   time; fall back to pinned constants when offline. Endpoints can never silently rot.
2. **Presets are data, not code.** Per-provider config (params, PKCE method, offline
   flags) lives in a declarative table. Updating = edit data, not rewrite logic.
3. **Scopes = single source of truth in the connector.** The flow reads each
   connector's declared scopes; never duplicated. Connector scope change → flow follows.
4. **Developer override / escape hatch.** Every field (auth_url, token_url, scopes,
   extra params) is overridable at call time. If a provider changes something before
   we ship a release, the developer sets it and is never blocked. (TC escape-hatch philosophy.)
5. **Release-sync.** Add "verify OAuth presets + scope lists vs provider docs" to the
   existing on-release verification directive.
6. **Optional CI drift check.** A test fetches the discovery doc and asserts the pinned
   fallback endpoints still match — fails loudly on drift. Strongest guarantee.

## 10. Fast-follow (separate task, NOT this build)

**Remove unused Google SDK deps.** Verified: the 6 Google connectors import only
httpx; `google-api-python-client` / `google-auth` / `google-auth-oauthlib` are
declared in extras but unused. Before removing: grep tests/examples for lazy
imports, then drop from `[gmail]`, `[gdrive]`, `[gcalendar]` and re-test.
Slims `[google]` and `[all]` substantially.

## 11. Build scope + "done when"

**Decision: cover BOTH (option C), sequenced.**

**Status: Slice 1 core DONE 2026-08-03** — `src/toolsconnector/runtime/auth/flows.py`
(`begin`/`complete`, PKCE S256 + `state`, `GOOGLE` preset with offline+consent),
4 tests green in `tests/unit/test_oauth_flow.py`. Web path usable now.
Note: `OAuthConfig.client_secret` did NOT need widening — the flow's `complete()`
takes `client_secret` as an optional arg and omits it on the wire for public
(PKCE-only) clients, so the existing type is untouched (even more compatible).

Slice 1 — core (serves Web):
1. `begin()` / `complete()` core with PKCE + `state`. ✅ done
2. Google provider preset (endpoints + offline/consent/PKCE defaults). ✅ done
   Remaining: OIDC-discovery endpoints + pinned fallback (§9); per-connector scope sets.
3. Public/confidential client handling. ✅ done (in-flow, OAuthConfig untouched).

**Status: Slice 2 DONE 2026-08-03** — `src/toolsconnector/runtime/auth/loopback.py`
(`login()`: browser + one-shot 127.0.0.1 listener + `complete()`), 3 integration
tests green in `tests/unit/test_oauth_loopback.py` (real socket + stdlib redirect +
respx token). Core `flows.py` stays socket-free.

Slice 2 — Desktop:
4. `login()` loopback convenience (127.0.0.1, one-shot, timeout, state-check,
   `error=access_denied` handling, configurable port). ✅ done

**Done when (tests that fail today):**
- Unit: `begin(google, scopes=gmail)` → URL contains `access_type=offline`,
  `prompt=consent`, `code_challenge` (S256), and the 4 gmail scopes.
- respx: `complete(code)` → `CredentialSet` with `access_token` **+ refresh_token**
  + `token_expiry`, consumable by `OAuth2Provider`; mismatched `state` raises.
- Live smoke: real Google Cloud project via the throwaway-loopback pattern — the
  only proof that counts.

## 12. Decisions (resolved)

- Redirect model: **(C) cover both** — Web via core, Desktop via loopback wrapper,
  sequenced (§11). RESOLVED 2026-08-03.
- Stay-current requirement: **added** — OIDC discovery + data-driven presets +
  single-source scopes + override + release-sync (§9). RESOLVED 2026-08-03.

### Still open
- Scope source when wiring connectors: keep scopes hardcoded per connector (today)
  vs. a shared Google scope registry the flow reads. Does not block Slice 1.
- Meaning of "always updated" — confirm it covers provider-config currency (§9) and
  whether it also means keeping docs/ROADMAP in sync each release.

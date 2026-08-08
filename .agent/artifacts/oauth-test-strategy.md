# OAuth Tier A — Test Strategy

Scope: the Google OAuth 2.0 token-**acquisition** flow (`runtime/auth/{flows,loopback,connectors,credentials}.py`)
and its seam into the 6 Google connectors.

State at time of writing: branch `claude/mcp-server-toolsconnector-access-3e0375`, HEAD `0d90f0d`.
`PYTHONPATH=src pytest tests/unit/test_oauth_flow.py tests/unit/test_oauth_loopback.py
tests/unit/test_google_oauth_wiring.py tests/unit/test_credential_resolution.py -q` → **30 passed**.

> **Env note (cost me a run):** the venv at `/Users/sachin/Documents/Projects/Agentic/ToolsConnector/.venv`
> resolves `toolsconnector` to an installed copy, *not* this worktree. Without `PYTHONPATH=src`
> all four modules fail collection with `ModuleNotFoundError: toolsconnector.runtime.auth.flows`.
> Any CI job added for this work must pin the worktree src or the tests silently test the wrong tree.

---

## 0. Correction to the inherited defect list

Two entries on the inbound list ("CredentialSet handed to a connector leaks client_secret in a header",
"CredentialSet passed to a connector leaks refresh_token + client_secret to Google") were **fixed by HEAD
commit `0d90f0d`** and are no longer real. Verified by execution, not by reading:

```
Gmail(credentials=CredentialSet(auth_type=OAUTH2, access_token="ya29.AAA",
      refresh_token="1//SECRET", client_secret="GOCSPX-topsecret"))._get_headers()
->  {'Authorization': 'Bearer ya29.AAA'}
```

The mechanism: `runtime/base.py:117` now stores `self._raw_credentials`, and `_credentials` is a
**property** (`base.py:132-150`) that calls `resolve_credential()` (`types/credentials.py:82-105`) on
every access, narrowing a `CredentialSet` via `as_credential_string()` (`types/credentials.py:50-79`).
Regression coverage exists at `tests/unit/test_credential_resolution.py:97-120`.

Treat that pair as **closed**. Everything below is verified against HEAD.

---

## 1. What is pending

### (a) Defects that must be fixed — ranked by what blocks production use

**P0-1 — The documented happy path still dies at 60 minutes, because the fix is undocumented.**
`grep -rln RefreshingCredentials --include "*.md" .` → **zero hits.** `RefreshingCredentials`
(`runtime/auth/credentials.py:43`) is exported (`runtime/auth/__init__.py:23,54`) and tested
(`test_credential_resolution.py:102-215`), but all 6 Google READMEs stop at
`src/toolsconnector/connectors/gmail/README.md:96` — `# creds.access_token / creds.refresh_token` —
and never mention that the token is dead in an hour or that a wrapper exists. Every user who follows
the README gets a connector that works in dev and fails overnight. This is now the single largest
production risk in the feature and it is a docs change, not a code change.

**P0-2 — Google's 401 never maps to `TokenExpiredError`; the reactive recovery path is dead.**
`_TOKEN_EXPIRED_MARKERS` (`connectors/_helpers/http_errors.py:99-104`) is a substring match over the
body only. Executed against both real Google 401 shapes:

```
{"error":{"code":401,"message":"Request had invalid authentication credentials...","status":"UNAUTHENTICATED"}}
  -> InvalidCredentialsError  retry_eligible=False
{"error":{"errors":[{"reason":"authError","message":"Invalid Credentials"}],"code":401,...}}
  -> InvalidCredentialsError  retry_eligible=False
```

Google puts the distinguishing signal in `WWW-Authenticate: Bearer ... error="invalid_token"`, and
`grep -rni "www-authenticate\|invalid_token" src/toolsconnector/` returns **zero hits** — the header is
parsed nowhere. Consequences: `retry_eligible=False` (`errors/auth.py:79`) short-circuits
`middleware/retry.py:83` and `serve/toolkit.py:556-558`; the `except TokenExpiredError` re-auth branch at
`serve/toolkit.py:542-554` is unreachable for all 6 Google connectors; and an agent written as
`except TokenExpiredError: relogin()` silently never re-logins. The operator-facing suggestion string
(`errors/auth.py:81-82`, "Verify that the API key or credentials are correct") points at client
credentials for a token that was merely an hour old.

Why P0 and not P1: `RefreshingCredentials` only refreshes **proactively off the local clock**. Every
early-invalidation path — user revokes access, password change, Workspace admin session reset, clock
skew, `token_expiry=None` (see P0-3) — produces a 401 that nothing can recover from.

**P0-3 — `RefreshingCredentials` with no expiry never refreshes, silently.**
`credentials.py:98-100`: `if expiry is None: return False`. Executed: a `CredentialSet` without
`token_expiry` reports `needs_refresh() == False` forever. `flows.complete()` sets `token_expiry` only
when the response carries `expires_in` (`flows.py:200-203`), and any credential rehydrated from a user's
vault that drops the timestamp degrades to a static token with no warning. Combined with P0-2 this is an
unrecoverable production failure with a misleading error message. Minimum fix: treat `None` expiry as
"unknown → refresh on first use" or log a loud warning at construction.

**P1-4 — Loopback bind is unguarded; port clash escapes the documented exception contract.**
`loopback.py:82` constructs `_LoopbackServer((host, port), _CallbackHandler)` with no `try/except`.
Reproduced against the real function with a squatter on 127.0.0.1:8765:

```
_wait_for_callback("127.0.0.1", 8765, 2.0)
  -> OSError(48, 'Address already in use')   isinstance OAuthFlowError? False
```

`loopback.py:132-133` promises only `OAuthFlowError`, so caller `except OAuthFlowError` handlers miss it.
The fixed default `8765` lives in two places: `loopback.py:103` and `connectors.py:107` (`login_for`, the
API the READMEs actually steer users to). Secondary: `webbrowser.open()` at `loopback.py:145` fires
*before* the bind at `:150`, so the user gets an orphaned consent tab. For Google **installed-app**
clients the port is ignored during redirect_uri validation, so `port=0` + read-back is a legitimate fix.

**P1-5 — One idle TCP connection defeats the timeout entirely.**
`_wait_for_callback` (`loopback.py:82-93`) sets `server.timeout = 1.0`, which bounds only
`selector.select()` on the *listening* socket. Confirmed at runtime: `socketserver.StreamRequestHandler.timeout`
is `None` and `BaseHTTPRequestHandler.timeout` is `None`, so an accepted connection blocks forever in
`rfile.readline()`. `HTTPServer` is single-threaded, so a blocked handler also starves the accept backlog.
Reproduced: a peer that connects and writes nothing, held 8s, against `timeout=2.0`:

```
B timeout=2.0 -> returned after 8.3s : OAuthFlowError
```

Return was gated by the *peer closing*, not by the deadline. Hold forever → hang forever; `login()` wraps
this in `run_in_executor` (`loopback.py:150`) with no `asyncio.wait_for`, so the documented
`timeout: float = 180.0` (`loopback.py:107`, `connectors.py:110`) never fires either, and a default-executor
thread is burned permanently. Worse: the deadline is checked *before* `handle_request()` (`loopback.py:86`),
so a genuine redirect that arrived in time is discarded and `server_close()` resets the browser connection —
a single-use auth code destroyed after the user successfully consented.

**P1-6 — `complete()` has no error-redirect path and no empty-code guard.**
`flows.py:141-176` accepts `code: str` and posts it unvalidated. Verified:
`httpx.Request("POST", ..., data={"grant_type":"authorization_code","code":None}).content`
→ `b'grant_type=authorization_code&code='` — no `TypeError`, an empty code goes to Google. On Deny, RFC 6749
§4.1.2.1 requires the provider to echo `state`, so `compare_digest` at `flows.py:167` passes and execution
falls straight through to a wasted round-trip and `OAuthFlowError("Token endpoint returned HTTP 400: ...")`
(`flows.py:190-193`). The reason the user declined is discarded. `loopback.py:152-154` already has this
handling — the **web** path (documented at `gmail/README.md:115-116` and 5 siblings) does not.
Sub-defect: `state=request.args.get("state")` returning `None` produces a raw `TypeError` out of
`secrets.compare_digest` at `flows.py:167`, escaping any `except OAuthFlowError`.
Severity is diagnostic, not security — it always fails loudly.

**P2-7 — Granted scope is discarded; `AuthState.scopes` reports the wrong thing.**
`flows.py:195-212` reads only `access_token` / `refresh_token` / `expires_in`. `payload.get("scope")` appears
nowhere in `src/toolsconnector/runtime/auth/` — the same omission repeats on refresh at
`credentials.py:186-202` and `oauth2.py:192-212`. Google's granular consent lets a user untick individual
boxes; Gmail requests 4 scopes (`gmail/connector.py:135-140`), a partial grant returns 200 with a narrowed
`scope`, and `login_for()` reports unqualified success. Sharper: `oauth2.py:106` populates
`AuthState.scopes` from `oauth_config.scopes` — the **requested** set — while `runtime/auth/base.py:81,98-101`
documents that field as *"Scopes granted by the authorization server."* A caller who does the diligent thing
gets an affirmatively wrong answer. `CredentialSet.extra` (`types/credentials.py:48`) already exists as a
home for it — this is a one-line carry-through, not a model migration. Note the `incremental=True` path
(`connectors.py:63-66`) makes the response `scope` the *only* authority on what the token covers.

**P2-8 — Docs omit `client_secret` and the loopback redirect registration.**
All 6 READMEs lead with `login_for(Gmail, client_id="...")` and no secret
(`gmail/README.md:95`, `gcalendar:99`, `gdrive:100`, `gtasks:87`, `gsheets:109`, `gdocs:104`).
Google's Desktop-app and Web client types both issue a secret; iOS/Android are unusable from Python. The
kwarg works (`connectors.py:103→123` → `loopback.py:101→160` → `flows.py:177-178`) but is undocumented in
`login_for`'s Args block (`connectors.py:112-118`), and `flows.py:15-16` actively misleads
("public clients (desktop/CLI) pass none"). Only `loopback.py:119-120` gets it right. The repo's own plan
already knew (`.agent/artifacts/oauth-flow-tier-a-plan.md:88-89`). Same section also never tells the user to
register `http://127.0.0.1:8765/` — the exact `redirect_uri_mismatch` that already bit the one live attempt.
**This is a docs defect, zero code change.** Do not "fix" it until L4 records the real response (see §4).

### (b) Features not yet built

| # | Missing | Where it would live | Blocks |
|---|---|---|---|
| F1 | **Any live verification at all.** Nothing has reached `oauth2.googleapis.com/token`. Every assertion about Google's behavior in this repo is inference. | §4 runbook | Everything below L3 |
| F2 | Reactive 401 → refresh → retry-once, at the credential layer | `credentials.py` + `http_errors.py` | P0-2, P0-3 |
| F3 | Error-redirect parsing for the web path (`parse_redirect(url)` or `complete(..., error=...)`) | `flows.py` | P1-6 |
| F4 | `port=0` / dynamic-port loopback with read-back into `redirect_uri` | `loopback.py:135` | P1-4 |
| F5 | `OAuth2Provider`/`AuthManager` wired into a connector request path. Still unwired. Note `toolkit.py:643` rebuilds the instance with `resolve_credentials(...)` — the same static string — so even fixing P0-2 does **not** make ToolKit self-heal. | `runtime/base.py` | ToolKit auto-recovery |
| F6 | Non-Google presets. `GOOGLE` (`flows.py:59-64`) is the only `ProviderPreset`. | `flows.py` | Tier A→B generalization |
| F7 | A `live` pytest marker + live-verify script convention. `pyproject.toml` has **no** `[tool.pytest.ini_options] markers` section. | `pyproject.toml`, `scripts/` | L4/L5 as repeatable jobs |
| F8 | Captured Google response fixtures. `tests/fixtures/google_oauth/` does not exist. | tests/ | All of L2 |

---

## 2. The test ladder

### L1 — Unit (pure, offline, no socket, no clock)

Catches: input validation, PKCE correctness, URL construction, branch logic that never touches a network.

Add:
- `test_complete_rejects_empty_code_before_any_http` — `complete(pending, code="", state=pending.state)`;
  assert `OAuthFlowError` **and** `route.call_count == 0`. Fails today (`flows.py:170-176`).
- `test_complete_rejects_none_state_as_oauthflowerror` — currently a raw `TypeError` from `flows.py:167`.
- `test_pkce_verifier_is_rfc7636_conformant` — 43–128 chars, unreserved charset only, `_pkce_pair()`
  (`flows.py:83-88`) produces a verifier whose S256 digest matches the challenge. Never asserted today.
- `test_begin_extra_params_override_preset_defaults` — `flows.py:126-127` ordering (a caller passing
  `prompt=select_account` must win over the preset's `prompt=consent`, which silently kills refresh tokens).
- `test_refreshing_credentials_without_expiry_does_not_silently_never_refresh` — P0-3. Fails today.
- `test_credentialset_stringification_never_contains_refresh_token` — regression guard for the `0d90f0d` fix.
- `test_resolve_credential_propagates_provider_exception` — a callable that raises must surface a typed
  error from `base.py:150`, not an opaque failure mid-request.

**Cannot catch:** anything about what Google actually sends or requires; socket behavior; real expiry.

### L2 — Contract (real captured response fixtures, error shapes)

Precondition: **F8 + F1.** Fixtures land in `tests/fixtures/google_oauth/` with a provenance header
(date, client type, the exact command that produced them). Captured during the §4 run:
`token_success.json`, `token_partial_grant.json`, `token_invalid_grant.json`, `token_invalid_client.json`,
`token_no_refresh_on_reconsent.json`, `api_401_unauthenticated.json` + `.headers.json`,
`api_403_insufficient_permissions.json`, `redirect_access_denied.txt`.

Catches: misclassification of real vendor error shapes — the class of bug that a hand-written mock
structurally cannot produce.

Add (in `tests/unit/test_http_errors_helper.py` and a new `tests/unit/test_oauth_contract.py`):
- `test_google_401_unauthenticated_maps_to_token_expired` — verbatim body from `api_401_unauthenticated.json`.
  **Fails today** (P0-2).
- `test_www_authenticate_invalid_token_maps_to_token_expired` — requires `raise_typed_for_status` to read
  response headers, which it does not (`http_errors.py:358-371` is body-only). Fails today.
- `test_partial_grant_is_recorded_on_the_credentialset` — `token_partial_grant.json` returns 3 of Gmail's
  4 scopes; assert `complete()` records the granted set (or raises on downgrade). Fails today (P2-7).
- `test_incremental_grant_superset_scope_is_recorded` — `include_granted_scopes=true` can return *more*
  than requested; the response `scope` is the only authority.
- `test_reconsent_without_refresh_token_is_flagged` — Google omits `refresh_token` on re-consent;
  `flows.py:208` stores `None` silently, and `RefreshingCredentials` then dies at the 1-hour mark with
  "re-run the OAuth flow" (`credentials.py:147-150`). Assert the flow warns at acquisition time.
- `test_invalid_client_body_reaches_the_exception_message` — the P2-8 failure must be self-diagnosing.
- `test_403_insufficient_permissions_is_distinguishable_from_401` — the downstream symptom of a partial grant.

**Cannot catch:** drift (a fixture is a photograph, see L5); anything request-side — respx returns 200
regardless of whether the POST satisfied Google's parameter rules.

### L3 — Integration (flow → connector → API call, token actually used)

Catches: seam failures between components that are individually green. This is the level that
`0d90f0d` added and that would have caught the CredentialSet leak years earlier.

Keep as regression (already exist, do not weaken):
- `test_credential_resolution.py:97` `test_credentialset_reaches_gmail_authorization_header`
- `test_credential_resolution.py:189` `test_connector_keeps_working_past_expiry`

Add:
- `test_refresh_post_body_carries_client_secret_and_grant_type` — extend the existing refresh tests to
  assert `route.calls.last.request.content`, not just the returned token (`credentials.py:151-158`).
- `test_401_midflight_triggers_reactive_refresh_and_one_retry` — respx: API 401 (real fixture) → token
  200 → API 200; assert exactly 2 API calls and a fresh header on call 2. **Cannot pass until F2 lands.**
- `test_toolkit_execute_recovers_from_token_expiry` — drives `serve/toolkit.py:542-554`. Will fail; it
  documents F5 (`toolkit.py:643` rebuilds with the same static credential).
- `test_loopback_port_in_use_raises_oauthflowerror` — bind first, monkeypatch `webbrowser.open`, assert
  `OAuthFlowError` **and** `webbrowser.open.call_count == 0`. Fails today (P1-4).
- `test_loopback_idle_peer_does_not_consume_the_deadline` — `socket.create_connection`, write nothing,
  then fire the genuine redirect; assert the code is returned within `timeout`. Fails today (P1-5,
  measured 8.3s against `timeout=2.0`).
- `test_loopback_respects_wall_clock_timeout` — assert `elapsed < timeout + 1.0`.
- `test_concurrent_refresh_issues_one_token_request` — two threads through `RefreshingCredentials.__call__`;
  assert `token_route.call_count == 1`. Exercises the double-check lock at `credentials.py:112-116`,
  currently untested.
- `test_login_for_defaults_are_exercised` — no explicit `port=`, no `open_browser=False`. Every existing
  loopback test passes `_free_port()` and `open_browser=False` (`test_oauth_loopback.py:27-32,50,57,82`;
  `test_google_oauth_wiring.py:41-46,104`), so the **shipped defaults are untested**.

**Cannot catch:** Google's real parameter validation; consent-screen behavior; the real 1-hour cliff.

### L4 — Live-verify (real Google, human consent)

Catches: everything respx cannot — that a Desktop client actually needs `client_secret`, that the
loopback URI is accepted, that `access_type=offline&prompt=consent` really yields a refresh token, and
the true wire shape of every error. **This level produces the L2 fixtures.** Runbook in §4.

**Cannot catch:** drift after the run; per-tenant Workspace admin policies; rare error shapes not
deliberately provoked.

### L5 — Production canary / ongoing

Extend the existing weekly job (`.github/workflows/api-drift.yml`, Mondays 06:00 UTC) rather than adding
a new one.

- **`oauth-endpoints` job (no secrets):** assert `GOOGLE.auth_url` and `GOOGLE.token_url`
  (`flows.py:61-62`) still resolve, and that a deliberately-malformed grant still returns a JSON
  `{"error": ...}` body of the shape the fixtures encode. Catches endpoint moves and error-format changes.
- **`oauth-refresh-canary` job (one repo secret: a long-lived refresh token + client id/secret):** run
  `RefreshingCredentials` → force `arefresh()` → `GET /users/me/profile` → assert 200 **and** that
  `on_refresh` fired with a token distinct from the input. This is the only mechanism that proves
  auto-refresh in the wild and that detects Google's refresh-token expiry policies (tokens issued by an
  app in "Testing" publishing status expire in 7 days — a canary catches that on day 8; L1–L4 never will).
- **Fixture staleness:** quarterly, re-provoke each captured error and diff against
  `tests/fixtures/google_oauth/`. A fixture with no re-capture date is a liability.
- **Scope drift:** the existing drift checker already diffs Discovery Doc scopes — wire its scope-change
  output to fail if a connector's `_auth_providers_config` scopes (`gmail/connector.py:135-140`) no longer
  match what Google publishes.

**Cannot catch:** user-specific consent configurations; Workspace admin policy changes in *their* tenant.

---

## 3. Anti-false-green rules

Concrete rules for this repo. Each one names the line that motivated it.

**R1 — Fixtures are captured, never composed.** Every mocked Google response body must load from
`tests/fixtures/google_oauth/` with a provenance header. Inline literals like
`json={"access_token": "ya29.x", "expires_in": 3600}` (`test_oauth_flow.py:59-68`,
`test_oauth_loopback.py:65-69`, `test_google_oauth_wiring.py:105-109`) are banned for new flow tests —
*that exact literal is why P2-7 is invisible*: a field the mock never sends cannot be asserted missing.

**R2 — Assert the bytes that leave the process AND the object that comes back.**
`test_credential_resolution.py:110` (`assert sent == "Bearer ya29.live"`) is the model. A test that only
inspects the outbound request (`test_oauth_flow.py:51`, `q["scope"]`) proves what was *asked for*, never
what was *granted* — pair it with a parsed-output assertion in the same test.

**R3 — Every happy path ships with a named error twin.** Currently missing twins, by name:
`test_complete_exchanges_code_for_credentials` → no `_denied` / `_empty_code` twin;
`test_login_for_end_to_end` → no `_port_in_use` / `_idle_peer` twin;
`test_expired_token_is_refreshed_and_new_one_is_returned` → no `_no_expiry_known` twin.
Review rule: a PR adding a happy-path OAuth test without its twin does not merge.

**R4 — Negative assertions require a positive twin in the same module.**
`assert "client_secret" not in body` (`test_oauth_flow.py:82`) is only meaningful because
`test_complete_sends_secret_for_confidential_client` (`:87-97`) proves it *is* sent when supplied.
That pairing is correct — keep it as the template. An unpaired `not in` assertion proves nothing.
(Open question for L4: whether `:82` should stay the *Google* expectation at all — see P2-8.)

**R5 — respx matches URL, not headers.** A connector test that only mocks the URL returns 200 for a
completely wrong `Authorization`. Every connector-level auth test must read
`route.calls.last.request.headers["Authorization"]`. This is precisely the gap that let the CredentialSet
leak live: `test_google_oauth_wiring.py:123` asserted `creds.access_token == "ya29.x"` and stopped, while
connector tests passed hand-written strings — two disjoint suites that never met.

**R6 — Time is injected, never assumed.** `token_expiry = now - 5min` (`test_credential_resolution.py:110`)
proves the branch, not the cliff. Required companions: `token_expiry=None` (P0-3), expiry inside the
60s buffer (`credentials.py:40`), and ±10min clock skew.

**R7 — At least one test per public entry point uses the shipped defaults.** No test exercises
`port=8765` or `open_browser=True`. If the default is worth shipping it is worth one test.

**R8 — Any test that binds a socket must include a hostile peer case.** Connect-and-say-nothing,
partial request line, and connection-reset. `test_oauth_loopback.py:35-45` only ever drives the listener
with a well-behaved `urllib.request.urlopen`.

**R9 — A test asserting third-party behavior must cite a fixture or a vendor doc URL in its docstring.**
`tests/connectors/test_gmail.py:322-333` pins the P0-2 misclassification as *intended* with a docstring
that is factually wrong ("Tokens that ARE expired return Google's `invalid_grant` body in OAuth flows,
not 401 on the API" — `invalid_grant` is the **token endpoint's** response to a bad **refresh** token; an
expired **access** token against `gmail.googleapis.com` returns exactly the 401 that test mocks). A green
suite that encodes a wrong model of the vendor is worse than no test. That docstring must be corrected
and the assertion retargeted as part of P0-2.

**R10 — Docs are test surface.** Every Python block in the 6 Google READMEs should at minimum be
`compile()`-checked in CI, and ideally executed against fixtures. P0-1 and P2-8 both exist purely because
code and docs diverged with nothing checking.

---

## 4. The one-page live-verify runbook

**Goal:** prove the flow against real Google, and produce the L2 fixtures. Nothing below is library code —
it is a throwaway operator script, same pattern as the LinkedIn live-verify.

### Step 0 — Google Cloud Console setup (10 min, human)

1. Create/select a project → **APIs & Services → Enabled APIs** → enable **Gmail API**.
2. **OAuth consent screen** → External → add your own account under **Test users**.
   Record the **publishing status** (Testing vs In production) — it determines refresh-token lifetime and
   is the thing the L5 canary watches.
3. **Credentials → Create Credentials → OAuth client ID → Desktop app.**
4. Record whether Google issued a **client secret**. **This single observation settles P2-8.**
5. If the client type offers a redirect-URI field, register `http://127.0.0.1:8765/` exactly
   (trailing slash — `loopback.py:135` builds `f"http://{host}:{port}/"`).

### Step 1 — Acquire (`scripts/live_oauth_verify.py`, not shipped)

```python
import asyncio, json, os, pathlib
from toolsconnector.connectors.gmail import Gmail
from toolsconnector.runtime.auth import login_for

CID, SEC = os.environ["G_CLIENT_ID"], os.environ.get("G_CLIENT_SECRET") or None
OUT = pathlib.Path("tests/fixtures/google_oauth"); OUT.mkdir(parents=True, exist_ok=True)

creds = asyncio.run(login_for(Gmail, client_id=CID, client_secret=SEC))
print("access_token prefix:", (creds.access_token or "")[:6])
print("refresh_token?     ", bool(creds.refresh_token))
print("token_expiry       ", creds.token_expiry)
```

**Assert, in order — each is a distinct claim currently unverified:**
- `creds.access_token.startswith("ya29.")` → the exchange worked end-to-end.
- `creds.refresh_token is not None` → `access_type=offline` + `prompt=consent` (`flows.py:63`) really work.
  **If this is `None`, P0-1/P0-3 are worse than documented and the preset is wrong.**
- `creds.token_expiry` is ~60 min out → `expires_in` parsing (`flows.py:200-203`) is right.
- **Run it once with `G_CLIENT_SECRET` unset.** If it fails → P2-8 confirmed, capture the body as
  `token_invalid_client.json`, and `test_oauth_flow.py:82` must be retargeted off the Google path.
  If it succeeds → P2-8 is downgraded to a docs-clarity item. **Do not guess this — record it.**

### Step 2 — Prove the token actually works through a connector

```python
gmail = Gmail(credentials=creds)          # the CredentialSet directly — the 0d90f0d contract
print(asyncio.run(gmail.get_profile()))   # or gmail._request("GET", "/users/me/profile")
```

Assert: 200 with a real `emailAddress`. This proves `resolve_credential` (`types/credentials.py:82-105`)
narrows correctly against a live server, not just respx.

### Step 3 — Capture the expiry 401 (the P0-2 fixture)

Do **not** wait an hour. Force it:

```python
import httpx
bad = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": "Bearer " + creds.access_token[:-8] + "AAAAAAAA"})
(OUT / "api_401_unauthenticated.json").write_text(bad.text)
(OUT / "api_401_unauthenticated.headers.json").write_text(json.dumps(dict(bad.headers), indent=2))
print(bad.status_code, bad.headers.get("www-authenticate"))
```

Assert: status 401, and `www-authenticate` contains `error="invalid_token"`. **That header string is the
fix for P0-2** — it is what `http_errors.py:212` must learn to read.
For the genuinely-expired variant, re-run this after the hour with the *original* token and diff the two
bodies; if they differ, capture both.

### Step 4 — Prove auto-refresh (not "a fresh token works")

This is the step that distinguishes a real proof from a false green. **Force expiry rather than waiting**,
so the refresh path is exercised deterministically:

```python
from datetime import datetime, timedelta, timezone
from toolsconnector.runtime.auth import RefreshingCredentials

rotated = []
auth = RefreshingCredentials(
    creds.model_copy(update={"token_expiry": datetime.now(timezone.utc) - timedelta(minutes=1)}),
    client_id=CID, client_secret=SEC, on_refresh=rotated.append,
)
old = creds.access_token
gmail2 = Gmail(credentials=auth)                  # callable credential
print(asyncio.run(gmail2.get_profile()))
new = auth.credentials.access_token
assert new != old,        "no refresh happened — the whole feature is unproven"
assert rotated,           "on_refresh never fired — rotated tokens would be lost"
assert auth.needs_refresh() is False
```

Assert all four. `new != old` is the load-bearing one: a passing `get_profile()` alone proves nothing,
because the original token is still valid — that is exactly the false green to avoid.

**Then the real-clock confirmation, which nothing else substitutes for:** leave the process alive
(or re-run from the persisted `refresh_token`) and call `get_profile()` again **after 65 minutes**.
Assert 200 and a third distinct access token. This is the only proof that the 1-hour cliff is survived
under the real clock rather than a `model_copy`-forced one.

### Step 5 — Capture the error shapes

- **Denial:** re-run Step 1 and click **Cancel**. Record the full redirect URL to
  `redirect_access_denied.txt`, and record the exception `login()` raised (should be `OAuthFlowError`
  from `loopback.py:152-154`). Then hand the same query params through the **web** path
  (`begin_for` → `complete`) and record what a web integrator gets — that is the P1-6 evidence.
- **Revoked refresh token:** revoke the app at <https://myaccount.google.com/permissions>, then call
  `auth.arefresh()`. Capture the body → `token_invalid_grant.json`. Assert `RefreshFailedError`
  (`credentials.py:175-178`).
- **Partial grant:** re-run Step 1 and untick one Gmail box on the consent screen. Capture the token
  response → `token_partial_grant.json` and note whether `scope` is present. Then call
  `messages.send` and capture the 403 → `api_403_insufficient_permissions.json`. This is the P2-7 pair.
- **Port clash:** run `python -m http.server 8765` in another shell, then run Step 1. Record the raw
  traceback — that is the P1-4 evidence.

### Step 6 — Record and land

1. Commit the fixtures under `tests/fixtures/google_oauth/` with a provenance header
   (date, client type, publishing status, whether a secret was issued).
2. Write the observed answers into this file under a **"Live-verify results (YYYY-MM-DD)"** heading —
   particularly the P2-8 secret question and the exact `WWW-Authenticate` string.
3. Only then write the L2 tests. Fixtures first, assertions second: an assertion written before the
   capture is an assumption wearing a test's clothes.
4. Redact before committing: `ya29\.[A-Za-z0-9_-]{40,}` and `1//...` are already in the CI secret-leak
   grep patterns (`connectors/_helpers/http_errors.py:139`) — replace live values with
   `ya29.REDACTED` / `1//REDACTED` in every fixture.

**Blocking note:** until Step 1 runs, F1 stands and *every* claim in this document about Google's
behavior is inference from the code plus vendor documentation, not observation. The code-side claims
(P0-2 classification, P0-3 no-expiry, P1-4 OSError, P1-5 8.3s stall, P1-6 empty-code encoding) were each
verified by execution against this repo and are not contingent on the live run.

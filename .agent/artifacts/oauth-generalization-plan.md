# OAuth Generalization Plan — provider = data, not code

Status: PLAN (not built) · Created 2026-08-03
Builds on: `oauth-flow-tier-a-plan.md` (Google flow, already built)

## 1. Objective

Make adding any OAuth 2.0 platform (GitHub, Notion, LinkedIn, Slack, Microsoft…)
a **declarative** act — write a small preset, point a connector at it, done. Same
`login_for(Connector, …)` call works for every provider. Third parties can add
their own provider with **zero TC changes** (bring-your-own preset).

## 2. Design — all variance lives in one struct

One flow engine (`begin`/`complete`/`login`, already built). A provider is a
`ProviderPreset`. `begin()`/`complete()` read its fields; they never branch per
provider.

```python
@dataclass(frozen=True)
class ProviderPreset:
    name: str
    auth_url: str
    token_url: str
    extra_auth_params: dict[str, str] = {}   # e.g. Google offline+consent, Notion owner=user
    pkce: bool = True                          # False for OAuth Apps that reject S256
    token_auth: str = "body"                   # "body" (creds in form) | "basic" (HTTP Basic header)
    scope_separator: str = " "                 # " " | ","
    discovery_url: str | None = None           # optional: OIDC .well-known -> auto-fills endpoints
```

Flow honors: `pkce` (emit/skip code_challenge+verifier), `token_auth` (creds in
body vs `Authorization: Basic`), `scope_separator` (join), `extra_auth_params`.
That set covers Google/GitHub/Notion/LinkedIn/Slack/Microsoft.

## 3. Two levels of adoption

1. **Built-in presets** for common providers, in a registry:
   `PRESETS = {"google": GOOGLE, "github": GITHUB, "notion": NOTION, ...}`.
2. **Bring-your-own preset** (the scalability guarantee): any OAuth2 provider TC
   never shipped works today via
   `login(ProviderPreset(name="acme", auth_url=..., token_url=..., token_auth="basic"),
   client_id=..., scopes=[...])`. No fork, no TC change.

## 4. Connector declaration (so login_for stays uniform)

- Add an `oauth2_auth(provider="github", scopes=[...], obtain_url=...)` declaration
  helper to `spec/auth.py` (today there is a helper for every auth type *except*
  oauth2). It records the provider/preset + scopes in the connector spec.
- `login_for(connector)` resolves the preset **from the connector** (preset name
  in its spec) — so no `preset=` arg is needed. `login_for(GitHub, client_id=…)`
  just works, same shape as Gmail. `preset=` stays as an override.
- Connectors that support OAuth **and** a static token (GitHub PAT, Notion
  integration token, LinkedIn) declare **both** providers (`AuthSpec.supported`
  is a list) — additive, backward-compatible, no BYOK path removed.

## 5. Preset values to ship (verify each at build)

| Provider | auth_url | token_url | pkce | token_auth | notes |
|---|---|---|---|---|---|
| google | accounts.google.com/o/oauth2/v2/auth | oauth2.googleapis.com/token | yes | body | offline+consent (built) |
| github | github.com/login/oauth/authorize | github.com/login/oauth/access_token | no | body | Accept: application/json |
| notion | api.notion.com/v1/oauth/authorize | api.notion.com/v1/oauth/token | no | **basic** | owner=user |
| linkedin | linkedin.com/oauth/v2/authorization | linkedin.com/oauth/v2/accessToken | opt | body | |
| slack | slack.com/oauth/v2/authorize | slack.com/api/oauth.v2.access | no | body | bot `scope` vs `user_scope` — handle via extra params |
| microsoft | login.microsoftonline.com/common/oauth2/v2.0/authorize | …/token | yes | body | tenant in URL |

## 6. Backward compatibility

Purely additive. `ProviderPreset` gains fields with Google-matching defaults
(`pkce=True`, `token_auth="body"`, `scope_separator=" "`), so the existing GOOGLE
preset + all Tier A behavior is unchanged. No signature breaks.

## 7. Work breakdown (slices)

- **Slice 1 — engine:** add `pkce`/`token_auth`/`scope_separator`/`discovery_url`
  to `ProviderPreset`; make `begin`/`complete` honor them. Tests: PKCE on/off,
  body-vs-basic token exchange, comma separator. (No provider added yet.)
- **Slice 2 — proof providers:** ship `GITHUB` + `NOTION` presets + registry.
  Notion proves `token_auth="basic"`; GitHub proves `pkce=False`. respx tests each.
- **Slice 3 — connector wiring:** add `oauth2_auth()` helper; declare OAuth2 on
  `github` + `notion` (alongside their bearer); `login_for` auto-resolves preset.
- **Slice 4 — docs + scale-out:** "Add an OAuth provider in 2 steps" guide; then
  add remaining presets (linkedin, slack, microsoft…) as pure data + tests.

## 8. The payoff — "add a new platform" recipe

1. Add a `ProviderPreset` (≈5 lines of data) — or skip if the caller BYO-presets.
2. On the connector, `oauth2_auth(provider="…", scopes=[…])` alongside its bearer.

That's it. No flow code. Effort per platform ≈ 1 preset + 1 connector line + 1
respx test.

## 9. Testing

Per provider: a respx test asserting (a) `begin()` builds the expected auth URL
(scopes joined correctly, PKCE present/absent, extra params) and (b) `complete()`
exchanges via the right client-auth method. Live-verify (BYOK) one non-Google
provider end-to-end before calling the framework proven.

## 10. Open questions

- Preset reference on the connector: a **name** into a registry (simple) vs inline
  endpoints in the connector's `OAuthSpec` (fully self-contained). Rec: name +
  registry, with inline override.
- Slack's bot-vs-user scope split — model via `extra_auth_params` or a dedicated
  field? Decide when Slack is added.

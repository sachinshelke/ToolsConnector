# WhatsApp Connector Plan (max-depth, 2026-07-22)

Status: **APPROVED with naming decision (2026-07-22, founder)** — final names: **`whatsapp_business`** = the full Cloud API connector (messaging + templates + media + webhooks + management, one BYOK credential); **`whatsapp`** = the offline personal-side primitives (wa.me/`whatsapp://` links, QR, E.164 — the connector formerly drafted as `whatsapp_link`). Any `whatsapp_link` mention below is the historical draft name for what is now `whatsapp`. Tool names therefore read `whatsapp_business_send_text`, `whatsapp_build_chat_link`, etc.

Researched against official Meta docs (Graph API v25.0, post-July-2025 per-message pricing) + full repo recon. Sources and per-claim verification flags live in the session research reports; everything marked UNVERIFIED below must be re-checked during live-verify.

---

## 1. The one decision that shapes everything: there is no "WhatsApp user" API

- **Cloud API is the ONLY official API.** On-Premises was deprecated 2025-10-23. Personal WhatsApp (and the free WhatsApp Business *App*) have **no API at all**.
- Every "personal WhatsApp API" (Baileys, whatsmeow, whatsapp-web.js, WPPConnect + commercial resellers like Whapi/Unipile) is a reverse-engineered linked-device client. It violates ≥5 explicit ToS clauses — including one aimed directly at libraries: *"create software or APIs that function substantially the same as our Services and offer them for use by third parties"*. Meta enforcement is active (warning banners since May 2025, bans at low volume even for reply-only bots) and Meta litigates **vendors**, not just senders (2019 legal-action policy; 2022 *Meta v. Rockey Tech* / HeyMods suit). The most-starred "WhatsApp MCP" is whatsmeow-based and ban-class.
- Zero mainstream peers ship personal WhatsApp (Composio, Zapier, Make, n8n, Pipedream, Twilio: Business Cloud API only).
- This is the same boundary as our LinkedIn people-search decline (ARCHITECTURE_FAQ #19 / locked decision): consent to one's own account ≠ Meta authorization of an unofficial client, and chat counterparties never consented to entering an agent pipeline.

**Therefore: no `whatsapp_user` connector — the name would promise an account connection that cannot exist.** The honest primitive for the personal/solopreneur persona is offline link generation (§3).

## 2. Naming (scored: honesty, agent discoverability, our conventions, persona fit)

| Option | Score | Verdict |
|---|---|---|
| **A. single `whatsapp`** (Cloud API messaging + management + webhook primitives) | 18/20 | **SHIP** |
| B. `whatsapp` + `whatsapp_business` (management split) | 8/20 | Reject — one API, one credential; every workflow crosses the split (create template → status webhook → send). FAQ #19: connector boundary = credential, not brand |
| C. `whatsapp_business` + `whatsapp_user` | 11/20 | Reject — `whatsapp_user` is structurally dishonest (nothing to connect to); attracts exactly the users we must refuse |

**FINAL (founder decision 2026-07-22): ship two connectors — `whatsapp_business` + `whatsapp`:**
1. **`whatsapp_business`** — the WhatsApp Business Platform (Cloud API) primitive: everything in the MSG + MGMT columns plus webhook primitives. Meta's own product name ("WhatsApp Business Platform"), so the name is exact.
2. **`whatsapp`** — the personal-side primitive: offline, auth-free wa.me / `whatsapp://send` URL builder, prefilled-text encoding, E.164 normalization/validation, QR rendering, group-invite link validation. Zero network calls, zero ban risk, officially documented scheme. Honest because links are literally everything a personal WhatsApp account offers programmatically. Serves the retail end-user + solopreneur (agent composes → human taps send); mirrors the `linkedin_leads` precedent. Connector descriptions must cross-reference each other so agents wanting to SEND find `whatsapp_business` immediately.

## 3. Personas → what serves them (full analysis in session research)

- **(a) Solopreneur/micro-business** (lives in the WA Business App): auto-replies, appointment reminders (UTILITY templates), broadcast offers (MARKETING templates, 250/day start → 2,000 after verification), QR/wa.me on packaging, business-profile updates. Reaches `whatsapp` once a Meta app + System User token exists (free path documented in §5); reaches `whatsapp_link` with zero setup. **Coexistence** (Business App + API on the same number) is GA but onboarding is partner-gated (Embedded Signup) — we *serve* already-coexistent numbers (20 mps cap, `smb_message_echoes` incl. edit/revoke, history sync) but cannot onboard them.
- **(b) Retail end-user** (personal WhatsApp): every automation ask is officially impossible → `whatsapp_link` + a "Why no personal-WhatsApp connector" FAQ entry.
- **(c) SMB w/ developer or agency**: support inbox (webhook receive + send + mark-read/typing + statuses), order notifications from Django/Flask workers (`biz_opaque_callback_data` correlation), CTWA lead capture (`referral.ctwa_clid`, FEP 72-h free window), template lifecycle ops, multi-number/per-number webhook overrides, `block_users`.
- **(d) Mid/large business**: scale (80→1,000 mps, tier ladder, pair limit ~1msg/6s), marketing (carousel/LTO/coupon templates, pacing, `user_preferences` opt-outs, template analytics), OTP (one-tap/zero-tap auth templates), commerce (SPM/MPM/catalog sends, `order` webhook, payments IN+BR, address messages IN), Flows (CSAT/booking/KYC forms), **Calling API** (voice, ≥2K tier), **Groups API** (official 2026: OBA required, 8 participants — VIP concierge, not broadcast), cost governance (`pricing_analytics`).
- **(e) AI-agent builder** (our sharpest differentiation — *the compliant WhatsApp primitive for agents*): webhook verify/parse helpers → typed events; interactive buttons/lists as a hallucination-free UI round-trip (`button_reply`/`list_reply` ids); mark-read + typing for humanity; CSW-expiry detection → template fallback; media → 5-min URL → download for vision/ASR; `wamid` dedupe (retries WILL duplicate); inbound text treated as untrusted content (prompt-injection warning in MCP docs).

Often-forgotten use cases folded in: OTP autofill templates (iOS 26+ native since Jun 2026), abandoned-cart, CSAT via Flows, CTWA attribution, template-pausing recovery, utility-free-inside-CSW cost arbitrage, `played` status for voice notes, identity-change ack (blocked sends until acked — endpoint UNVERIFIED), BSUID/username shift (`user_id` in webhooks since Mar 2026 — schema-proof models), data-localization at registration, **webhook downtime = permanent inbound loss** (docs must scream this).

## 4. Receiving realtime messages (the design question)

Facts: push-only — **no polling endpoint exists**; retries up to 7 days then unrecoverable; payloads batched (≤3 MB, multiple `entry`); no ordering guarantee; signed with `X-Hub-Signature-256` = HMAC-SHA256(app_secret, raw body); GET handshake echoes `hub.challenge`.

Repo precedent: everything webhook-shaped today is OUTBOUND (`webhook.send_with_hmac` emits the exact `sha256=<hex>` scheme WhatsApp uses inbound); zero inbound verify/parse code; no `hmac.compare_digest` anywhere; `serve/rest.py` already ships an optional self-hosted Starlette app (`[rest]` extra) — so a stateless receiver does NOT violate FAQ #8 ("primitive, not platform" bans *us hosting*, not shipping self-hosted surfaces).

**Design — Shape A (core) + Shape B (optional convenience):**
- **Shape A — pure primitives in the connector package** (like Stripe SDK's `construct_event`; not `@action`s — exported functions/statics):
  - `verify_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool` (constant-time; note escaped-unicode caveat — UNVERIFIED in current docs, test live)
  - `handle_verification(params: Mapping, verify_token: str) -> str` (hub.challenge responder)
  - `parse_event(raw_body: bytes | dict) -> list[WhatsAppEvent]` — typed Pydantic dispatch over the full taxonomy: inbound messages (all types incl. `order`, `referral`, `system`, `unsupported`, `interactive.*_reply`, `nfm_reply` [schema UNVERIFIED]), `statuses` (sent/delivered/read/played/failed + pricing + errors), template status/quality/category, phone quality, `account_update`, `calls`, `smb_message_echoes`/`history`/`smb_app_state_sync`, `user_preferences`. `extra="ignore"`, every field defaulted — schema-proof against Meta drift.
  - Framework-agnostic: user mounts in FastAPI/Flask/Django/Lambda in ~10 lines (docs show all four).
- **Shape B — later, optional:** ~100-line stateless Starlette receiver (`verify → parse → user callback`, nothing stored) behind the existing `[rest]` extra or `toolsconnector-mcp` satellite. Never grows retries/queues/routing (that's platform).
- **Shape C (polling) is not viable for WhatsApp** — keep the telegram `get_updates` pattern for vendors that offer pull.
- Record as a new ARCHITECTURE_FAQ entry: *"inbound events: verify/parse are library primitives; the listener is the developer's — or an optional stateless extra."* The verify helper also seeds the backlogged `toolsconnector.auth` HMAC leg.

## 5. BYOK credential shape & the solopreneur path

Structured credential (Odoo-style dict/JSON parsing, alias-tolerant):
```python
{"access_token": "...",            # System User token (permanent option), scopes:
                                   # whatsapp_business_messaging + whatsapp_business_management
 "phone_number_id": "...",         # messaging endpoints
 "waba_id": "...",                 # template/analytics/management endpoints (optional for send-only)
 "app_secret": "..."}              # optional — only for webhook signature verify
```
Env fallback `TC_WHATSAPP_CREDENTIALS` (JSON). **No partnership needed** (verified): own Meta app → free auto-created **test WABA + test number** (template sends to ~5 pre-verified recipients, no payment method) → add real number (`request_code`/`verify_code`/`register`) → System User → permanent token. Service messages are free; only templates bill per delivered message. This free test path is also our live-verify path.

## 6. Action surface (`whatsapp_business` connector, grouped; ~46 actions P1+P2)

**P1 — Messaging core (~24 actions, live-verifiable free on a test WABA):**
`send_text`, `send_image`, `send_audio`, `send_video`, `send_document`, `send_sticker`, `send_location`, `send_contacts`, `send_reaction`, `send_interactive_buttons`, `send_interactive_list`, `send_cta_url`, `send_location_request`, `send_template` (positional + named params, all button types incl. carousel/LTO/coupon/auth via components passthrough), `mark_as_read`, `send_typing_indicator`, `upload_media`, `get_media_url`, `download_media` (handles the 5-minute-URL dance internally), `delete_media`, `get_business_profile`, `update_business_profile`, `get_phone_number` (quality_rating/throughput/name_status/limit), `list_phone_numbers`.
Plus webhook primitives (§4, non-action) and `context.message_id` reply support + `biz_opaque_callback_data` on all sends.

**P2 — Management & ops (~22 actions):**
`create_template`, `list_templates` (PaginatedList), `get_template`, `edit_template`, `delete_template`, `list_qr_codes`/`create_qr_code`/`update_qr_code`/`delete_qr_code`, `block_users`/`unblock_users`/`list_blocked_users` (PaginatedList), `request_verification_code`/`verify_code`/`register_phone`/`deregister_phone`, `set_two_step_pin`, `get_waba`, `get_messaging_analytics`, `get_pricing_analytics`, `get_template_analytics` (+ insights opt-in), `subscribe_app`/`list_subscribed_apps` (+ per-WABA callback override param).

**P3 — Gated surfaces (doc-tier until live-verifiable; several paths UNVERIFIED):**
Flows (send exists in P1 via interactive passthrough; CRUD `/{WABA}/flows`), commerce sends (`send_product`/`send_product_list`/`send_catalog`), payments IN/BR (`order_details`/`order_status`), Calling API (`initiate_call`/`accept`/`reject`/`terminate` + SDP), Groups API (CRUD + group sends + pin — OBA-gated, endpoint paths UNVERIFIED), MM Lite `/marketing_messages`, address messages (IN→IN).

**`whatsapp` connector (~6 actions, all offline; formerly drafted as `whatsapp_link`):** `build_chat_link`, `build_send_link` (scheme variants), `normalize_phone` (E.164), `encode_prefilled_text`, `render_qr` (optional `segno` dep in the extra), `validate_group_invite_link`.

**Not supported table (document honestly):** edit/delete sent messages (no endpoint), Channels/Status/newsletters (no API), broadcast lists/labels/quick replies (app-only), personal accounts (FAQ), coexistence onboarding (partner-gated).

## 7. Implementation pattern (per repo recon — follow exactly)

- Handwritten httpx (default per `docs/guides/adding-connector.md`; binding IR only for the 4 IR connectors). 4 files: `connector.py` / `types.py` / `__init__.py` / `README.md` under `src/toolsconnector/connectors/whatsapp/`.
- Class: `name="whatsapp_business"`, `category=ConnectorCategory.COMMUNICATION`, `protocol=ProtocolType.REST`, `base_url="https://graph.facebook.com/v25.0"` (version override via `base_url`), `verification_status="pattern"` until verified, `RateLimitSpec` per 80 mps / pair-limit notes.
- All actions `async def` + `@action`; internal calls use `a`-prefixed siblings; single `_request` boundary with `raise_typed_for_status` + `scrub_secret`; Graph error-body mapping (code 130429 → RateLimitError, 131056 pair limit, 133016 register limit, 190 token → InvalidCredentialsError).
- `types.py`: frozen Pydantic, `extra="ignore"`, camelCase aliases, result envelopes carrying `messages[].id` (wamid) and `messaging_product` echo; webhook event models here too.
- Registration touchpoints (13-item checklist from recon): `serve/_discovery.py` `_KNOWN_CONNECTORS`, `pyproject.toml` extras (`whatsapp_business = []`, `whatsapp = ["segno"]`? — decide; frugality rule), `tests/connectors/test_whatsapp_business.py` (+ chaos suite patterned on `test_people_data_chaos.py`), `webapp/tool_metadata.py`, `docs/connectors/communication.md` + index, `README.md`/`ROADMAP.md` counts, `examples/NN_whatsapp_business.py` (mask PII in output — CodeQL), `python scripts/build_site.py`, release-time AgentStore `connectors.ts` re-sync.
- Tests: respx with **real envelopes from official docs**, auth-header pin (`Authorization: Bearer`), request-body pins, pagination collect() walk (templates/blocked lists use cursor pagination), error matrix, spec governance pin (action count + tier), webhook-primitive tests are pure-function (signature vectors, handshake, full payload-taxonomy parse table). Live-verify sweep on the free test WABA before any tier promotion (respx happy-path = false greens — ContactOut/Lusha lesson).

## 8. Build phases ("one thing at a time", each with done-when)

**Status 2026-07-23: W1 ✅ (built + 26-agent adversarial review, 11 confirmed findings fixed) · W3 ✅ (`whatsapp` link connector, Tier 2 doc) · W4 ✅ (live sweep on real test WABA: 18/25 round-tripped, all 11 message types device-confirmed; Tier 1 live; docs/counts/site synced — webhook end-to-end deferred, needs tunnel + dashboard callback). Remaining: W2 (management actions + chaos suite) and W5 (gated surfaces + ES helpers).**

| Phase | Scope | Done when |
|---|---|---|
| **W1** | `whatsapp_business` P1 messaging core + webhook primitives + tests | respx suite green incl. webhook-parse taxonomy table; a FastAPI 10-liner in docs round-trips verify→parse→reply against recorded payloads |
| **W2** | P2 management + pagination + analytics + chaos suite | chaos suite green; template CRUD respx-pinned vs official envelopes |
| **W3** | `whatsapp` link sidecar | pure-function tests incl. E.164 edge cases + QR snapshot |
| **W4** | Live-verify on free test WABA (send/receive/media/templates/profile) → honest tier promotion + docs (README, FAQ entries: inbound-events decision, why-no-personal-WhatsApp) + counts sync | live sweep annotated in README/ROADMAP; `verification_status` reflects only what was actually round-tripped |
| **W5** (later) | P3 gated surfaces + optional Shape-B receiver | each surface individually doc-verified; UNVERIFIED register cleared item-by-item |

## 9a. Platform-embedder addendum (2026-07-22) — PRIMARY PERSONA CORRECTION

ToolsConnector's customer is **the platform embedding tools for THEIR users** (B2B2C — AgentStore-style), not the end developer with one key. Gap check done 2026-07-22 (analysis only, nothing implemented). What this changes:

**WhatsApp connector scope changes:**
1. **The platform IS a Meta "Tech Provider."** §5's "no partnership needed" holds only for a direct developer on their own WABA. A platform connecting *other businesses'* WABAs needs: verified business portfolio + App Review (Advanced Access to `whatsapp_business_messaging`/`whatsapp_business_management`) + Embedded Signup integration + Access Verification to lift the 10-customers/7-day onboarding cap. Document both paths side by side (direct BYOK vs Tech Provider).
2. **Embedded Signup server-side helpers move IN scope** (BYOK-safe: return tokens, never store — matches auth-layer decision D00000F Layer 2): `exchange_code` (ES `code` → customer-scoped Business Integration System User token via `GET /oauth/access_token`), `debug_token` (discover granted WABA ids / phone-number ids / scopes from the token). The browser half of ES (JS SDK, `featureType`) stays the platform's frontend job — library ships the token exchange + the existing onboarding sequence (`subscribe_app` → `register_phone` w/ PIN).
3. **Coexistence onboarding re-scoped**: previously "partner-gated, out of scope" — but the platform persona *is* the partner. Via ES `featureType: "whatsapp_business_app_onboarding"` (ES v2 dies 2026-10-15 → build against v4), a platform CAN onboard solopreneurs' Business-App numbers; our connector then serves them (`history` sync within 24 h, `smb_message_echoes`, `smb_app_state_sync`, 20 mps cap). Add `request_smb_app_sync` action to P2.
4. **Multi-tenant webhook routing is first-class**: ONE Meta app receives events for ALL customer WABAs. `parse_event` must surface `entry[].id` (WABA id) + `value.metadata.phone_number_id` as explicit routing keys on every event; docs must show dispatch-to-tenant. Signature verify uses the **platform's app secret** (app-level, one per Meta app) while actions use the **tenant's token** — the credential model must separate these two scopes explicitly. Per-WABA `override_callback_uri` on `subscribe_app` stays (per-tenant callback fan-out).
5. Business-Integration token lifetime/refresh story: UNVERIFIED — resolve during build; platforms need explicit reconnect-on-`ACCOUNT_OFFBOARDED`/`PARTNER_REMOVED` guidance (`account_update` webhook).

**Library-wide gaps found (blockers for "smooth tools connection", all pre-existing, none WhatsApp-specific):**
| # | Gap | Evidence |
|---|---|---|
| G1 | Auth machinery exists but is UNWIRED: `runtime/auth/` providers (APIKey/Basic/Bearer/OAuth2-with-refresh) + `AuthMiddleware` are used by zero connectors — every connector hand-builds headers from a raw credential string; gmail expects a pre-obtained access token, no auto-refresh on 401 | `runtime/auth/*`, `gmail/connector.py:136` |
| G2 | No connection-initiation helpers (D00000F Layer 2): nothing builds authorize URLs / exchanges auth codes / PKCE / device-code — platforms hand-roll the "connect your tool" flow per provider | `toolsconnector.auth` does not exist |
| G3 | ~~`OAuth2Provider._persist_tokens` hardcodes tenant `"default"`~~ **FIXED 2026-07-22** (commit 9b54b9e on main): `tenant_id` param, keys follow `{connector}:{tenant}:{field}`; failing-first tests in `tests/unit/test_runtime_auth_oauth2.py`; FAQ #20 | `runtime/auth/oauth2.py` |
| G4 | ~~`ToolKitFactory.for_tenant` ignores rotated `credentials` + unbounded cache~~ **FIXED 2026-07-22** (commit 9b54b9e on main): credentials are part of cache identity (stale kit retired + rebuilt), opt-in `max_tenants` LRU; factory↔KeyStore sourcing deliberately deferred to the G1/G2 `toolsconnector.auth` wiring (D00000F); FAQ #20 | `serve/toolkit.py` |
| G5 | `ConnectorSpec.auth: AuthSpec` exists (incl. OAuthSpec URLs + named ScopeSets) but no connector declares it → platforms can't machine-read "what credentials does this connector need / where to get them" (that data lives only in `webapp/tool_metadata.py`, website-only) | `spec/connector.py:113`, grep: zero setters |
| G6 | No credential-validation / connection-health primitive ("is this user's connection alive?") — needed for platform connection dashboards | `health/` is spec-drift monitoring, not per-tenant probes |
| G7 | No disconnect/revoke lifecycle helpers (token revocation, webhook unsubscribe) | — |

WhatsApp does NOT block on G1–G7 (its BYOK token needs no OAuth dance; ES exchange is a self-contained helper). But G3/G4/G5 should be fixed alongside W1–W4, and G1/G2 are the `toolsconnector.auth` backlog (D00000F) now with a concrete driver.

## 9. UNVERIFIED register — RESOLVED 2026-07-22

Full wire-level resolution (41 claims: 39 CONFIRMED, 2 CORRECTED, 0 unresolved whole-claims; per-claim endpoints/fields/sources) lives in **`.agent/artifacts/whatsapp-wire-register.md`** — build W1/W2 models directly from it. The 7 corrections that change this plan:

1. **Identity-change "ack endpoint" does not exist on Cloud API** (On-Premises only). Cloud mechanism: identity-change-check setting + per-send `recipient_identity_key_hash` + error **137000** on mismatch; resend without the hash to unblock. Drop the planned ack action.
2. **Group invite links ARE API-creatable** (Groups API GA Oct 2025, OBA-gated): `GET/POST/DELETE /<GROUP_ID>/invite_link` — invite link is NOT a get-group-info field. `whatsapp` (link connector) still only validates the `chat.whatsapp.com/` prefix offline (no charset/length spec published — don't hard-validate).
3. **Coexistence ES `featureType` must be `whatsapp_business_app_onboarding`** — `"coexistence"` is no longer valid (§9a already reflects this).
4. **Messaging-limit ladder second tier is 2,000** (250 → 2,000 → 10K → 100K → unlimited; the 1,000 tier no longer exists). Read via `GET /{PHONE_NUMBER_ID}?fields=whatsapp_business_manager_messaging_limit` (only `TIER_250` directly observed as an enum value).
5. **Three distinct QR families**: plain wa.me-encoding QR (offline-generatable — our `whatsapp` connector), managed `message_qrdls` short-links (`wa.me/message/<CODE>`, ≤140-char prefill, API-managed — `whatsapp_business`), consumer in-app contact QR (proprietary — must document as NOT generatable). Docs must not conflate them.
6. **`flow_token` is optional** (not required) in the send-flow `parameters` object.
7. **Group create is effectively async**: sync response body is undocumented (treat as opaque); real result (`group_id`, `invite_link`, `request_id`) arrives via `group_lifecycle_update` webhook. Group list nests unusually: `data.groups[]`, not `data[]`. Auth-templates-inside-CSW: **charged** (only service messages and utility-inside-CSW are free).

Also confirmed en route: ES v4 token exchange is `GET /oauth/access_token` with exactly `{client_id, client_secret, code}` (no redirect_uri/grant_type); MM Lite is now "Marketing Messages API" (`POST /<PHONE_NUMBER_ID>/marketing_messages`, marketing templates only, `pricing.category="marketing_lite"`, eligibility via `marketing_messages_onboarding_status`); `user_preferences` payload pinned (`value: "stop"|"resume"`, `category: "marketing_messages"`); pair rate limit + error 131056 + `4^X` backoff guidance pinned; escaped-unicode signature caveat is current official text only on the Messenger webhooks page (test both forms in verify helper); group sends reject non-text/media/template types with error **130501**.

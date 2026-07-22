# WhatsApp UNVERIFIED-register resolution (2026-07-22)

## Summary

| Metric | Count |
|---|---|
| Total claims | 41 |
| CONFIRMED | 39 (35 clean + 4 carrying an embedded correction) |
| CORRECTED | 2 (whole-claim verdict) |
| UNRESOLVED | 0 whole claims; unresolved **sub-details** preserved verbatim inside items and marked UNRESOLVED |

Verdict basis: all items anchored on live-fetched official Meta pages (both the legacy `/docs/whatsapp/...` tree and the new `/documentation/business-messaging/whatsapp/...` tree) except where a lower evidence class is explicitly labeled ([official via search-snippet], [BSP-mirror], [official, archived]).

## CORRECTED items that change the plan

1. **Identity change ack (Number surface)** — full CORRECTED. There is **no acknowledgment endpoint in Cloud API**; `POST /v1/contacts/<wa_id>/identity` + `show_security_notifications` is On-Premises only. Cloud mechanism is "identity change check": settings toggle + per-send `recipient_identity_key_hash` + error 137000 on mismatch + resend-without-hash to unblock.
2. **Group invite links (Link schemes)** — full CORRECTED. "Creation is app-only (no API)" is now false: the Groups API (GA since Oct 2025) creates groups and mints/resets `chat.whatsapp.com/<LINK_ID>` links for OBA businesses.
3. **Coexistence featureType (Tokens/Onboarding)** — `"coexistence"` is **no longer a valid** `extras.featureType` value; must use `whatsapp_business_app_onboarding`.
4. **Invite-link location (Groups)** — invite link is NOT a field of get-group-info; it has its own endpoint `GET /<GROUP_ID>/invite_link`.
5. **Messaging-limit tier ladder (Pricing/Scale)** — second tier is **2,000**, not 1,000; the 1,000 tier no longer exists.
6. **QR taxonomy (Link schemes)** — WhatsApp has THREE distinct QR families (plain wa.me-encoding, managed `message_qrdls`, consumer in-app contact QR); only the first is reproducible by an offline generator.
7. **flow_token (Flows, minor)** — it is **optional**, not required, in the send-flow `parameters` object.

---

## Groups

### G1. Group management endpoint paths + create/get fields
- VERDICT: CONFIRMED (one sub-item UNRESOLVED; one embedded CORRECTION)
- WIRE: All group management lives in the NEW doc tree only; standard Graph host, ~v25.0.
  - **Create**: `POST /<BUSINESS_PHONE_NUMBER_ID>/groups` — body `messaging_product:"whatsapp"`, `subject` (required, max 128 chars), `description` (optional, max 2048), `join_approval_mode` (optional: `"approval_required"` | `"auto_approve"`). **Synchronous response body: UNRESOLVED** — official reference shows NO sample response (Meta community thread explicitly confirms the gap). Creation is effectively async: result (`group_id`, `invite_link`, `join_approval_mode`, `request_id`) arrives via `group_lifecycle_update` webhook. Model the sync response as opaque/unvalidated.
  - **Get group info**: `GET /<GROUP_ID>?fields=<comma-separated>` — fields: `id`, `messaging_product`, `subject`, `description`, `suspended`, `creation_timestamp`, `participants` (array of `{"wa_id"}`), `total_participant_count`, `join_approval_mode`. **CORRECTION: invite link is NOT a get-group-info field** — own endpoint `GET /<GROUP_ID>/invite_link` → `{"messaging_product", "invite_link"}` (format `https://chat.whatsapp.com/<LINK_ID>`).
  - **List**: `GET /<BUSINESS_PHONE_NUMBER_ID>/groups` — `limit` (default 25, max 1024), `after`/`before` cursors. Response nesting unusual: `{"data": {"groups": [{"id","subject","created_at"}]}, "paging": {"cursors": {"after","before"}, "previous", "next"}}` — `data` is an OBJECT containing `groups[]`, not the usual `data[]` array.
  - **Update settings**: `POST /<GROUP_ID>` — `messaging_product`, `subject` (opt), `description` (opt), `profile_picture_file` (opt); result via `group_settings_update` webhook.
  - **Delete**: `DELETE /<GROUP_ID>` — no body; result via `group_lifecycle_update` webhook.
  - **Reset invite link**: `POST /<GROUP_ID>/invite_link` — body `messaging_product` → `{"messaging_product", "invite_link"}`.
  - **Remove participants**: `DELETE /<GROUP_ID>/participants` — `messaging_product` + `participants[]` of `{"user": "<phone-or-wa_id>"}`, max 8 per call. No add-participants endpoint (invite-link/join-request only).
  - **Join requests**: list `GET /<GROUP_ID>/join_requests` → `data[]` of `{join_request_id, wa_id, creation_timestamp}` + `paging`; approve `POST /<GROUP_ID>/join_requests` — `messaging_product` + `join_requests[]` (string-vs-object shape not 100% pinned — treat as list of ID strings, verify live) → `{messaging_product, approved_join_requests[], failed_join_requests[]?, errors[]?}`; reject `DELETE` same path → same shape with `rejected_join_requests[]`.
- SOURCE: developers.facebook.com/documentation/business-messaging/whatsapp/groups/reference [official]; create-response gap via community thread 1401092725368430 [official-secondary (forum)].

### G2. Group messaging envelope
- VERDICT: CONFIRMED
- WIRE: `POST /<BUSINESS_PHONE_NUMBER_ID>/messages` with `{"messaging_product":"whatsapp","recipient_type":"group","to":"<GROUP_ID>","type":"text","text":{"preview_url":true,"body":"..."}}` — `to` = opaque group ID (base64-ish, e.g. `Y2FwaV9ncm91cDoxNzA1NTU1MDEzOToxMjAzNjM0MDQ2OTQyMzM4MjAZD`). Allowed types: text, media, text-based templates, media-based templates ONLY. Unsupported (calling, disappearing, view-once, auth templates, commerce, interactive, editing, deletion) → error **130501** "Message type is not currently supported". Template quality/performance metrics don't apply to group sends; Meta recommends dedicated group templates.
- SOURCE: .../groups/groups-messaging/ + .../groups [official].

### G3. Pin/unpin payload
- VERDICT: CONFIRMED
- WIRE: same `/messages` endpoint, `"type": "pin"`, object `"pin": {"type": "pin"|"unpin", "message_id": "<WAMID>", "expiration_days": 1–30}` (`expiration_days` required for pin, not unpin). Max 3 concurrent pins; 4th auto-unpins oldest. One message per request; only the group admin (business) can pin/unpin.
- SOURCE: .../groups/groups-messaging/ [official].

### G4. Gating and limits
- VERDICT: CONFIRMED
- WIRE: Official Business Account (OBA) required. Max **8** participants/group; **10,000** groups/business number; **1** Cloud API business/group. Cloud API numbers only (not WhatsApp Business app numbers, not Multi-solution Conversations); app needs `whatsapp_business_messaging` permission + webhook subscription. Per-message pricing. Groups invite-only (link or join request).
- SOURCE: .../groups + /groups/get-started [official]; corroborated sanuker.com, woztell.com [BSP-mirror].

### G5. Group webhooks
- VERDICT: CONFIRMED
- WIRE: Four fields: `group_lifecycle_update`, `group_participants_update`, `group_settings_update`, `group_status_update` — all wrapped in `entry[].changes[].value` with `messaging_product`, `metadata{display_phone_number, phone_number_id}`.
  - `group_lifecycle_update`: `groups[]` — `type`: `"group_create"`|`"group_delete"`, `group_id`, `timestamp`, `subject`, `invite_link`, `join_approval_mode`, `request_id` (correlates async create/delete); failures add `errors[]` of `{code, message, title, error_data}`.
  - `group_participants_update`: `type`: `"group_participants_add"` | `"group_participants_remove"` | `"group_join_request_created"` | `"group_join_request_revoked"`; `reason` (e.g. `"invite_link"`), `added_participants[]` / `removed_participants[]` (`{wa_id, input?}`), `failed_participants[]`, `initiated_by`: `"business"`|`"participant"`, `join_request_id`.
  - `group_settings_update`: `type:"group_settings_update"` with `profile_picture` (`mime_type`, `sha256`), `group_subject` / `group_description` (`text`), each carrying `update_successful` (bool) + optional `errors[]`.
  - `group_status_update`: `type`: `"group_suspend"`|`"group_suspend_cleared"`, `group_id`, `timestamp`.
  - **messages** webhook: inbound group messages carry `value.messages[].group_id` alongside `from`, `id`, `timestamp`, `type`, payload object; sender profile via top-level `contacts[]` (`wa_id`, `profile.name`).
  - **statuses** webhook: group sends carry `recipient_type: "group"`, `recipient_id` = GROUP id, `recipient_participant_id` = individual participant number; statuses may be aggregated across participants/messages in one webhook.
- SOURCE: .../groups/webhooks/ + .../webhooks/reference/messages/group/ + .../messages/status [official].

Implementer note: legacy `/docs/whatsapp/cloud-api/reference` does NOT document Groups. Two live-verify spots before freezing Pydantic models: create-group's sync response body; `join_requests[]` shape in approve/reject.

---

## Flows

### F1. Flow CRUD (Management API)
- VERDICT: CONFIRMED (additions: create takes 2 extra optional fields; preview URL needs explicit `fields` param)
- WIRE (graph.facebook.com/v<VER>/, Bearer):
  - **Create**: `POST /<WABA_ID>/flows` — `name` (str, required), `categories` (array, required; enum `SIGN_UP, SIGN_IN, APPOINTMENT_BOOKING, LEAD_GENERATION, CONTACT_US, CUSTOMER_SUPPORT, SURVEY, OTHER`), `clone_flow_id` (opt), `endpoint_uri` (opt), `flow_json` (opt), `publish` (bool, opt). Response: `id`, `success`, `validation_errors[]` (`error, error_type, message, line_start, line_end, column_start, column_end, pointers`).
  - **List**: `GET /<WABA_ID>/flows` → `data[]`, `paging.cursors`.
  - **Get one**: `GET /<FLOW_ID>` — fields: `id, name, status, categories, validation_errors, json_version, data_api_version, endpoint_uri, preview, whatsapp_business_account, application`. Status enum: `DRAFT, PUBLISHED, DEPRECATED, BLOCKED, THROTTLED`. Preview NOT default — `GET /<FLOW_ID>?fields=preview.invalidate(false)` → `preview: {preview_url, expires_at}`.
  - **Update metadata**: `POST /<FLOW_ID>` — `name`/`categories`/`endpoint_uri` (all opt) → `{success}`.
  - **Upload JSON**: `POST /<FLOW_ID>/assets` multipart: `name` = literal `"flow.json"` (req), `asset_type` = literal `"FLOW_JSON"` (req), `file` (req, max 10 MB) → `success`, `validation_errors[]`. `GET /<FLOW_ID>/assets` → `data[] {name, asset_type, download_url}`.
  - **Publish**: `POST /<FLOW_ID>/publish` → `{success}`; **Deprecate**: `POST /<FLOW_ID>/deprecate` → `{success}`; **Delete**: `DELETE /<FLOW_ID>` → `{success}`.
- SOURCE: developers.facebook.com/docs/whatsapp/flows/reference/flowsapi [official].

### F2. Sending a flow (interactive `flow` message)
- VERDICT: CONFIRMED — all parameter names exact as claimed (flow_token optionality corrected: optional, not required)
- WIRE: `POST /<PHONE_NUMBER_ID>/messages`, `type:"interactive"`, `interactive: {type:"flow", header?, body?, footer?, action: {name:"flow", parameters:{...}}}`. Parameters: `flow_message_version` (str, required, must be `"3"`); `flow_id` XOR `flow_name` (exactly one required, "cannot use both together"); `flow_cta` (str, required; official "advised to be 30 characters or less"; 360dialog says max 20 — official wording wins); `flow_token` (str, **optional**, business-generated); `flow_action` (opt: `"navigate"` default | `"data_exchange"`); `flow_action_payload` (opt: `{screen: <entry screen id>, data?: <object>}`, used with navigate); `mode` (opt: `"draft"` | `"published"` default).
- SOURCE: .../flows/gettingstarted/sendingaflow [official].

### F3. Inbound completion webhook (`nfm_reply`)
- VERDICT: CONFIRMED
- WIRE: standard `messages` webhook, message `type:"interactive"` with `interactive: {type:"nfm_reply", nfm_reply: {name:"flow" (constant), body:"Sent" (constant), response_json:"{\"flow_token\": \"<FLOW_TOKEN>\", ...}"}}`. `response_json` is a **JSON-encoded string** (must be parsed); inner shape is flow-defined — set by Flow JSON `Complete` action payload (navigate) or endpoint's final response (data_exchange); `flow_token` echoed inside. Pydantic: `nfm_reply: {name: str, body: str, response_json: str}`.
- SOURCE: .../flows/guides/receiveflowresponse/ [official]; cross-checked docs.360dialog.com [BSP-mirror].

### F4. Gating + data-channel (endpoint) setup
- VERDICT: CONFIRMED
- WIRE: Publish gate (official changelog verbatim): "All businesses can now start creating and building Flows, but to send and publish a Flow, business verification and high message quality are still required" — build/draft = anyone; publish + send = verified business + high quality. data_exchange setup: (a) `endpoint_uri` on the flow (create or update) + `data_api_version` in Flow JSON; (b) per-number key upload `POST /<PHONE_NUMBER_ID>/whatsapp_business_encryption`, form field `business_public_key` (RSA PEM; 2048-bit per BSP docs only — official says just "valid RSA public key in PEM format" meeting "Meta's security standards"). `GET /<PHONE_NUMBER_ID>/whatsapp_business_encryption` → `{business_public_key, business_public_key_signature_status}` enum `VALID | MISMATCH`. Endpoint flows must also meet reliability/performance thresholds (F5 alerts).
- SOURCE: flowsapi + implementingyourflowendpoint [official]; business-encryption-api [official-secondary-tree]; publish-gate [official via search-snippet — page 500'd direct]; 2048-bit [BSP-mirror].

### F5. Flows status/error webhook field
- VERDICT: CONFIRMED (field name is `flows`; NO field named `flow_status` — status changes arrive as event `FLOW_STATUS_CHANGE` inside `flows`)
- WIRE: subscribe WABA field **`flows`**. Envelope `{object:"whatsapp_business_account", entry:[{id:<WABA_ID>, time, changes:[{field:"flows", value:{...}}]}]}`. `value`: common — `event` (`FLOW_STATUS_CHANGE, CLIENT_ERROR_RATE, ENDPOINT_ERROR_RATE, ENDPOINT_LATENCY, ENDPOINT_AVAILABILITY`), `message`, `flow_id`, `alert_state` (`ACTIVATED | DEACTIVATED`). `FLOW_STATUS_CHANGE`: `old_status`, `new_status` (`DRAFT, PUBLISHED, DEPRECATED, BLOCKED, THROTTLED`). Error-rate events: `error_rate`, `threshold`, `requests_count`, `errors[] {error_type, error_rate, error_count}`. `ENDPOINT_LATENCY`: `p50_latency`, `p90_latency`, `threshold`, `requests_count`. `ENDPOINT_AVAILABILITY`: `availability` (0–100), `threshold` (90). Do NOT model ycloud's "whatsapp.flow.status_change / flowChanges" — that is the BSP's transformed format.
- SOURCE: .../flows/reference/flowswebhooks/ [official].

Evidence residue (verbatim from report): (a) publish-gate sentence verified only via search snippet of the official changelog (page HTTP 500 direct); (b) 2048-bit RSA length is BSP-sourced.

---

## Webhook infra

### W1. X-Hub-Signature-256 validation
- VERDICT: CONFIRMED (core); escaped-unicode sub-claim CONFIRMED as current official text, but only on the Messenger webhooks page — absent from WhatsApp + Graph getting-started trees
- WIRE: Every webhook POST carries `X-Hub-Signature-256: sha256=<hex digest>`. Validation = HMAC-SHA256(payload, app_secret), hex-encode, timing-safe compare against everything after `sha256=`. WhatsApp page: "Generate an HMAC-SHA256 hash using the JSON payload as the message input and your app secret as the secret key" — no unicode note. Messenger page (fetched live 2026-07-22) verbatim: signature generated using an "escaped unicode" version of the payload with lowercase hex digits; `äöå` → `\u00e4\u00f6\u00e5`. Search-snippet-grade extended escape list (`/`→`\/`, `<`→`\u003C`, `%`→`\u0025`, `@`→`\u0040`) — do NOT hard-code from this evidence. Library guidance: HMAC over the RAW received bytes before any JSON parse/re-serialize — Meta transmits the body already escaped; only re-encoding breaks it.
- SOURCE: .../webhooks/create-webhook-endpoint/ [official]; docs/messenger-platform/webhooks [official-secondary-tree]; escape-list [search-snippet].

### W2. Delivery/retry policy (7 days vs 36 hours) + ordering
- VERDICT: CONFIRMED — 7 days applies to WhatsApp Cloud API; ordering statement: explicit absence
- WIRE: WhatsApp-specific (both trees): non-200 → retries with decreasing frequency "for up to 7 days" ("retried immediately, then a few more times with decreasing frequency over the next 7 days"). The 36-hour figure is generic Graph getting-started text — superseded for WhatsApp. Retries go to all subscribed apps and "can result in duplicate webhook notifications" — "Your server should handle deduplication." Batching: aggregated, "maximum of 1000 updates. However, batching cannot be guaranteed." Ordering: NO delivery-ordering guarantee or statement exists on any current WhatsApp webhook page (overview, create-webhook-endpoint, legacy set-up-webhooks checked); closest official text (send-messages): outbound delivery order isn't guaranteed to match API-request order; confirm `delivered` status before next send. Model webhooks as at-least-once, unordered.
- SOURCE: .../webhooks/overview + .../create-webhook-endpoint/ [official]; docs/graph-api/webhooks/getting-started [official].

### W3. POST/GET/DELETE /<WABA_ID>/subscribed_apps
- VERDICT: CONFIRMED (one docs-inconsistency caveat)
- WIRE: **POST** `graph.facebook.com/v25.0/<WABA_ID>/subscribed_apps` — subscribes app (identified by token); plain subscribe = NO body → `{"success": true}`. Optional override body is TOP-LEVEL JSON (not nested): `{"override_callback_uri": "<url>", "verify_token": "<token>"}` — hub.challenge verification GET fired at the override URL with that verify_token. POSTing again with no body REMOVES the WABA-level override. **GET** → `{"data": [{"whatsapp_business_api_data": {"link", "name", "id"}, "override_callback_uri": "<url-if-set>"}]}` (`override_callback_uri` present only when set). **DELETE** exists officially ("unsubscribe your app from webhooks for a WhatsApp Business account") → `{"success": true}`. Caveat: the auto-generated Graph reference page for this edge renders POST/DELETE as "You can't perform this operation on this endpoint" — reference skew; WhatsApp doc trees + Meta's Postman collection document all three verbs.
- SOURCE: docs/whatsapp/embedded-signup/webhooks + .../webhooks/override/ [official]; Meta Postman collection [BSP-mirror]; conflicting Graph reference render noted [official].

### W4. Per-phone-number webhook override
- VERDICT: CONFIRMED — exists, and it is NOT on subscribed_apps
- WIRE: **Set**: `POST /<BUSINESS_PHONE_NUMBER_ID>` with NESTED `{"webhook_configuration": {"override_callback_uri": "<url>", "verify_token": "<token>"}}`. **Read**: `GET /<BUSINESS_PHONE_NUMBER_ID>?fields=webhook_configuration` → `{"webhook_configuration": {"phone_number": "<phone-level-url>", "whatsapp_business_account": "<waba-level-url>", "application": "<app-dashboard-url>"}, "id": "..."}` (keys absent if unset). **Remove**: POST with `{"webhook_configuration": {"override_callback_uri": ""}}` (empty string, nested). Routing precedence: phone-number alternate → else WABA alternate → else app callback URL. Model asymmetry: WABA override fields top-level on subscribed_apps; phone override nested under `webhook_configuration` on the phone-number node.
- SOURCE: .../webhooks/override/ [official]; Postman [BSP-mirror].

### W5. GET verification handshake (hub.*)
- VERDICT: CONFIRMED
- WIRE: `GET <endpoint>?hub.mode=subscribe&hub.challenge=<value>&hub.verify_token=<your-token>` (live doc example: `?hub.mode=subscribe&hub.challenge=1158201444&hub.verify_token=vibecoding`). `hub.mode` always `subscribe`; `hub.verify_token` must equal configured token; `hub.challenge` — "An `int` you must pass back to us" (treat as numeric string). Respond HTTP 200 with the raw unquoted `hub.challenge` as body; non-match → 403/error. Endpoint must be HTTPS with valid (non-self-signed) cert.
- SOURCE: .../create-webhook-endpoint/ [official]; docs/graph-api/webhooks/getting-started [official].

### W6. Media webhook `url` field (direct CDN link)
- VERDICT: CONFIRMED (field + rollout); expiry semantics UNRESOLVED (no official TTL stated)
- WIRE: Field exactly `url`, inside the media object of inbound message webhooks. Live-verified on new-tree references: **image** (`caption, mime_type, sha256, id, url`), **document** (`caption, filename, mime_type, sha256, id, url` — example `"url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=133..."`), **audio** (`id, mime_type, sha256, voice, url`); video/sticker pages not individually fetched — same pattern presumed, verify before modeling. "Media URL. You can query this URL directly with your access token to download the media asset" (Bearer required). Every page still carries (as of 2026-07-22): "This JSON property is being released to developers gradually over several weeks, starting November 12, 2025, and may not be available to you immediately" — mid-2026 status = still gradual/not guaranteed; Pydantic `url` MUST be Optional, keep `GET /<MEDIA_ID>` fallback. Expiry: no official TTL stated anywhere for the webhook-delivered `url` (image/document/audio refs, media docs both trees, changelog checked — changelog 500s, JS-only). Related official facts: `GET /<MEDIA_ID>` URLs "expire after 5 minutes"; media downloadable ~7 days post-webhook (search-snippet grade). Treat webhook `url` as short-lived; download immediately.
- SOURCE: .../webhooks/reference/messages/image/ , /document/ , /audio/ [official]; docs/whatsapp/cloud-api/reference/media [official]; retention windows [search-snippet].

---

## Number surface

### N1. Business profile (whatsapp_business_profile)
- VERDICT: CONFIRMED
- WIRE: GET `/<PHONE_NUMBER_ID>/whatsapp_business_profile?fields=about,address,description,email,profile_picture_url,websites,vertical` → `{"data": [{about, address, description, email, messaging_product: "whatsapp", profile_picture_url, websites: [str], vertical}]}` (GET returns `profile_picture_url`; sample value handle-like, e.g. `"2:c2FtcGxl..."`). POST same path, JSON body; `messaging_product: "whatsapp"` REQUIRED; optional: `about` (1–139 chars, non-empty, no markdown, hyperlinks non-clickable, emoji Java/JS-escape encoded), `address` (max 256), `description` (max 512), `email` (valid, max 128), `websites` (array, max 2, max 256 chars each, must include http:// or https://), `profile_picture_handle` (handle from **Resumable Upload API**), `vertical` (empty string or exactly one of 21: `ALCOHOL, APPAREL, AUTO, BEAUTY, EDU, ENTERTAIN, EVENT_PLAN, FINANCE, GOVT, GROCERY, HEALTH, HOTEL, NONPROFIT, ONLINE_GAMBLING, OTC_DRUGS, OTHER, PHYSICAL_GAMBLING, PROF_SERVICES, RESTAURANT, RETAIL, TRAVEL`). Response `{"success": true}`. No DELETE — "To delete your business profile, you must delete your phone number."
- SOURCE: docs/whatsapp/cloud-api/reference/business-profiles/ (updated Jun 16, 2026, browser-rendered) [official].

### N2. Identity change ack
- VERDICT: CORRECTED
- WIRE: **No acknowledgment endpoint in Cloud API** — `POST /v1/contacts/<wa_id>/identity` with `show_security_notifications` is On-Premises API only. Cloud mechanism = "identity change check": enable/disable via `POST /<PHONE_NUMBER_ID>/settings` body `{"user_identity_change": {"enable_identity_key_check": true|false}}` → `{"success": true}`. Once enabled: inbound `messages` webhooks carry customer hash as `identity_key_hash` in `contacts`; outbound status webhooks carry `recipient_identity_key_hash` in `statuses`. Enforcement is opt-in **per send**: top-level `recipient_identity_key_hash: "<hash>"` in the `POST /<PHONE_NUMBER_ID>/messages` body; on mismatch the message is NOT delivered → status webhook with **error code 137000**. "Unblock"/ack = verify customer out-of-band, **resend the failed message WITHOUT the hash field** (hashless sends always go through), then store the new hash from the next delivery status webhook. No settings field or POST "acknowledges" a hash change. BSP claims of a hard block until acknowledgment describe their own platform layer, not Meta's wire.
- SOURCE: .../business-phone-numbers/phone-numbers ("Identity change check") [official]; On-Prem contrast docs/whatsapp/on-premises/reference/contacts/users-whatsapp-id/identity/ [official, legacy product].

### N3. block_users
- VERDICT: CONFIRMED
- WIRE: Block: `POST /<PHONE_NUMBER_ID>/block_users` body `{"messaging_product": "whatsapp", "block_users": [{"user": "<phone, e.g. +16505551234>"}]}` → `{"messaging_product": "whatsapp", "block_users": {"added_users": [{"input", "wa_id"}], "failed_users": [{"input", "wa_id" (absent if number invalid), "errors": [{"message", "code" (int), "error_data": {"details"}}]}]}}`; partial failure adds top-level `"error"` with code **139100**. Unblock: DELETE same path/body → `removed_users` + `failed_users`. List: `GET /<PHONE_NUMBER_ID>/block_users?limit=<int>&after=<cursor>&before=<cursor>` → `{"data": [{"messaging_product": "whatsapp", "wa_id"}], "paging": {"cursors": {"after", "before"}}}`. Constraints: only users who messaged you in last **24 hours** (violation → **131047** "Re-engagement required"); max **1,000 users/request**; blocklist cap **64,000** (**139101**); cannot block own number (**131021**) or another business; synchronous, per-number errors. Also: 139102 concurrent update, 139103 internal, 130429 rate limit.
- SOURCE: docs/whatsapp/cloud-api/block-users/ (updated Jun 26, 2026, browser-rendered) [official].

### N4. QR codes (message_qrdls)
- VERDICT: CONFIRMED
- WIRE: Create: `POST /<PHONE_NUMBER_ID>/message_qrdls` body `{"prefilled_message": "<text, max 140 chars>", "generate_qr_image": "SVG"|"PNG"}` → `{"code", "prefilled_message", "deep_link_url" (https://wa.me/message/<CODE>), "qr_image_url"}`. List: GET collection → `{"data": [{"code", "prefilled_message", "deep_link_url"}]}` (no qr_image_url in list/get examples). Get one: `GET /message_qrdls/<CODE>` → `{"data": [{...}]}`. Update: POST **collection path** (NOT /<CODE>) body `{"code": "<CODE>", "prefilled_message": "<new text>"}` → `{"code", "prefilled_message", "deep_link_url"}`. Delete: `DELETE /message_qrdls/<CODE>` → `{"success": true}`. Codes never expire on their own. Cap: max **2,000** QR codes + short links per WABA phone number. UNVERIFIED sub-detail: whether `generate_qr_image` works as a query param on GET (older legacy docs allowed it).
- SOURCE: .../documentation/business-messaging/whatsapp/qr-codes/ (updated May 21, 2026, browser-rendered) [official].

### N5. phone_number_quality_update webhook
- VERDICT: CONFIRMED (fields NOT yet removed from doc; deprecation notice still active)
- WIRE: `changes[].value`: `display_phone_number` (string), `event` (documented values now ONLY `ONBOARDING` and `THROUGHPUT_UPGRADE` — old FLAGGED/UNFLAGGED/UPGRADE/DOWNGRADE no longer appear), `old_limit` (string, "only included for messaging limit changes"), `current_limit` (string), `max_daily_conversations_per_business` (string). `current_limit` and `old_limit` still carry "This field/parameter will be removed in February, 2026. Use max_daily_conversations_per_business instead" — **docs still list them post-deadline** → model Optional/deprecated. Tier enum for all three limit fields: `TIER_50, TIER_250, TIER_2K, TIER_10K, TIER_100K, TIER_NOT_SET, TIER_UNLIMITED` (`old_limit`'s list omits TIER_UNLIMITED but its example value IS TIER_UNLIMITED — doc inconsistency). Current example payload: only `display_phone_number`, `event`, `current_limit`. Whether Meta still emits current_limit/old_limit on the wire today is unverifiable from docs — mark Optional in Pydantic. Related: `business_capability_update` webhook carries `max_daily_conversations_per_business` (webhooks v24.0+) vs `max_daily_conversation_per_phone` (v23.0 and older, "until February 2026"), plus `max_phone_numbers_per_waba` / `max_phone_numbers_per_business`.
- SOURCE: .../webhooks/reference/phone_number_quality_update/ [official, browser-rendered]; .../messaging-limits [official]; business_capability_update via `.md` endpoint [official — appending `.md` to new-tree URLs returns fetchable markdown].

### N6. Typing indicator / mark-as-read
- VERDICT: CONFIRMED
- WIRE: Both `POST /<PHONE_NUMBER_ID>/messages`. Typing (implies read): `{"messaging_product": "whatsapp", "status": "read", "message_id": "<wamid from inbound messages webhook>", "typing_indicator": {"type": "text"}}` → `{"success": true}`; dismisses on reply or after 25 seconds; `"text"` is the only documented `typing_indicator.type`. Mark-as-read alone: same shape minus `typing_indicator` → `{"success": true}`; within 30 days of receipt; also marks earlier messages in conversation read; invalid wamid → error **131009** ("Parameter value is not valid").
- SOURCE: .../typing-indicators (Jun 17, 2026) + .../messages/mark-message-as-read (Jul 2, 2026) [official, browser-rendered].

---

## Tokens/Onboarding

### T1. Embedded Signup v4 server-side token exchange
- VERDICT: CONFIRMED
- WIRE: `GET https://graph.facebook.com/v25.0/oauth/access_token?client_id=<APP_ID>&client_secret=<APP_SECRET>&code=<CODE>` — GET (not POST); NO `redirect_uri`, NO `grant_type`. Documented response exactly `{"access_token": "<NEW_ACCESS_TOKEN>"}` — `token_type`/`expires_in` NOT shown → model Optional, do not depend on them. Exchangeable code TTL = 30 seconds ("The exchangeable token code has a time-to-live of 30 seconds") → exchange immediately server-side.
- SOURCE: docs/facebook-login/facebook-login-for-business + docs/whatsapp/embedded-signup/implementation [official].

### T2. Business Integration System User token lifetime
- VERDICT: CONFIRMED (never-expiring by default)
- WIRE: "Defaults to never expire for the common offline server-to-server communication." Optional expiring mode: `set_token_expires_in_60_days=true` (expires in 60 days) — documented on `POST /<CLIENT_BUSINESS_ID>/system_user_access_tokens` (params include `asset`, `scope`), NOT on `/oauth/access_token`. No refresh-token flow documented; re-obtain via new granular token or re-run ES exchange. Whether the 60-day default can be toggled in the app-dashboard login-config UI: not pinned — unverified nuance.
- SOURCE: docs/facebook-login/facebook-login-for-business [official].

### T3. System User token "never expire" option still exists (mid-2026)
- VERDICT: CONFIRMED
- WIRE: Two token classes still documented: "Non-expiring Access Tokens" (Lifetime "Never expires", no refresh) and expiring ("Valid for 60 days", `set_token_expires_in_60_days`). Meta positions expiring as best practice ("All integrations should adopt expiring tokens...") but never-expire remains available at generation; third-party 2026 guides confirm "Never" still present in Business Settings > System Users > Generate Token.
- SOURCE: docs/business-management-apis/system-users/install-apps-and-generate-tokens/ [official]; anjoktechnologies.in, notiqoo.com [BSP-mirror/search-snippet, corroboration only].

### T4. debug_token response fields
- VERDICT: CONFIRMED (one field caveat)
- WIRE: `GET /v25.0/debug_token?input_token=<TOKEN_TO_INSPECT>` with `Authorization: Bearer <APP_ACCESS_TOKEN or app developer's user token>`. Envelope `{"data": {...}}` with: `app_id` (string), `application` (string), `is_valid` (bool), `expires_at` (unixtime), `data_access_expires_at` (unixtime), `issued_at` (unixtime), `user_id` (string), `scopes` (string[]), `granular_scopes` (object[] `{scope: string, target_ids: ?int[]}`), `metadata`, `error`, `profile_id`. ES: WABA IDs in `granular_scopes[].target_ids` under `scope: "whatsapp_business_management"` and `"whatsapp_business_messaging"`, most-recently-onboarded first. Official manage-accounts example shows target_ids as STRINGS (e.g. `["102289599326934", ...]`) while reference types them `int[]` → Pydantic `list[str | int] | None`. Caveat: `type` (e.g. `"SYSTEM_USER"`) appears in real responses/community examples but NOT in the fetched reference table → `Optional[str]`. `target_ids` can be absent; field drift between `business_management` vs `whatsapp_business_management` reported in the wild (chatwoot#14690) — don't hard-fail on missing scope entries.
- SOURCE: docs/graph-api/reference/debug_token/ [official]; docs/whatsapp/embedded-signup/manage-accounts/ [official, via search snippet]; github.com/chatwoot/chatwoot/issues/14690 [mirror, drift evidence].

### T5. Tech Provider post-ES onboarding sequence
- VERDICT: CONFIRMED (order nuance noted)
- WIRE: Official order: (1) exchange code → customer-scoped business token; (2) register phone; (3) subscribe app to WABA; Solution Partners add (4) share credit line; Tech Providers instead require the customer to add their own payment method. No strict register-before-subscribe dependency documented — only that token exchange comes first ("After fetching the client's WABA ID, subscribe your app"). Subscribe: `POST /<WABA_ID>/subscribed_apps`, `Authorization: Bearer <CUSTOMER_BUSINESS_TOKEN>`, no required body → `{"success": true}`; `GET` → `{"data": [{"id", "name", "link"}]}`. `override_callback_uri`/`verify_token` override options exist but exact param docs were not pinned in this report — UNRESOLVED sub-detail (cross-reference: resolved by Webhook-infra W3 — top-level body params on subscribed_apps). Auto-generated Graph reference claims POST unsupported on this edge — WhatsApp doc tree contradicts and is correct; trust the WhatsApp tree. Register: `POST /<PHONE_NUMBER_ID>/register`, body `{"messaging_product": "whatsapp", "pin": "<6-digit>"}` (+ optional `data_localization_region`, 2-letter ISO) → `{"success": true}`. NO separate set-two-step-PIN call needed first: if 2FA already enabled, pass the existing 6-digit PIN; otherwise register establishes it. Rate limit: 10 register requests per number per 72 hours.
- SOURCE: .../embedded-signup/overview + get-started-for-tech-providers [official-secondary-tree]; docs/whatsapp/embedded-signup/webhooks + docs/whatsapp/cloud-api/reference/registration [official].

### T6. Coexistence onboarding (featureType + smb_app_data + 24h)
- VERDICT: CONFIRMED for `whatsapp_business_app_onboarding` / smb_app_data / 24h; CORRECTED insofar as `"coexistence"` must NOT be used
- WIRE: Changelog: "coexistence is no longer a valid extras.featureType value; you must use whatsapp_business_app_onboarding to launch the WhatsApp Business App onboarding flow" (also: Marketing Messages Lite moved from `extras.featureType` to `extras.features`). Launch config (mirror-corroborated): `FB.login(cb, { config_id, response_type: 'code', override_default_response_type: true, extras: { setup: {}, featureType: 'whatsapp_business_app_onboarding', sessionInfoVersion: '3' } })`. Completion session event: `event: "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"`. SKIP phone-registration step ("the number is already registered"). Sync API: `POST /<BUSINESS_PHONE_NUMBER_ID>/smb_app_data` body `{"messaging_product": "whatsapp", "sync_type": "smb_app_state_sync" | "history"}` → `{"messaging_product": "whatsapp", "request_id": "<REQUEST_ID>"}` (`smb_app_state_sync` = contacts, `history` = messaging history; results async via `smb_app_state_sync`, `history`, `smb_message_echoes` webhooks). Deadline verbatim: "you have 24 hours to synchronize their messaging history, otherwise they must be offboarded and they must complete the flow again." Eligibility: WhatsApp Business app >= 2.24.17.
- SOURCE: onboarding-business-app-users pages, both trees [official]; changelog [official via search-snippet — page 500s on direct fetch]; FB.login snippet [BSP-mirror: github.com/iragazzisrl/whatsapp-api-cloud-coexistence, ycloud helpdocs].

### T7. Test numbers: recipient cap + payment method
- VERDICT: CONFIRMED (5 recipients; no payment method needed) — but only via official-domain search snippets, not a rendered official page
- WIRE: Test business phone number can message "up to 5 recipient phone numbers"; each recipient verified via WhatsApp confirmation code before selectable; once added, a recipient reportedly cannot be removed (snippet/mirror-level detail). Payment: "Test WhatsApp Business accounts and test phone numbers ... have relaxed messaging limits and don't require a payment method on file in order to send template messages" — NO payment method for template sends from a test number (payment method required for real business numbers / Tech Provider customers). Current rewritten Get Started pages no longer server-render these sentences — facts come from search-index snippets of developers.facebook.com pages, corroborated by multiple BSP mirrors.
- SOURCE: docs/whatsapp/cloud-api/get-started/ + messaging-limits [official, via search-snippet]; respond.io, clickatell, landbot [BSP-mirror].

---

## Pricing/Scale

### P1. Authentication templates inside CSW — charged; utility inside CSW — free
- VERDICT: CONFIRMED (auth-inside-CSW = CHARGED; utility-inside-CSW = free)
- WIRE: Per-message pricing (since 2025-07-01), charged per **delivered** template message. Only free cases (official): (a) "All non-template messages are free" (only sendable inside an open CSW); (b) "Utility templates delivered within an open customer service window are free" (verbatim, incl. charge-example table row: utility at hour 4 inside CSW → rate "None"); (c) all messages free for 72h inside a free-entry-point window. Authentication templates appear in NO free list, no CSW exemption anywhere in the official tree → charged even with open CSW. Twilio explicit: "During a customer service window, Meta does not charge for utility template messages or free-form messages. You will still be charged for Marketing and authentication templates." Pricing-model code: charge attaches on `statuses[].pricing` at delivery; category follows template category.
- SOURCE: .../pricing + docs/whatsapp/pricing/ + docs/whatsapp/pricing/updates-to-pricing/ [official — free-list + example table; auth exemption absent by omission, no affirmative sentence exists]; twilio.com/en-us/whatsapp/pricing [BSP-mirror — explicit].

### P2. Per-number throughput 80 mps → 1,000 mps
- VERDICT: CONFIRMED (upgrade is AUTOMATIC, no request path)
- WIRE: "Cloud API supports up to 80 messages per second (mps) by default, and up to 1,000 mps by automatic upgrade" (per registered business phone number; combined sent+received). Automatic + free when ALL three hold: (1) portfolio has **unlimited messaging limit**; (2) number messages **100K+ unique WhatsApp user phone numbers outside a CSW within a moving 24-hour period**; (3) `quality_score` YELLOW or higher. No documented "by request" path. During upgrade (≤1 min) number unusable → error **131057** ("Business Account is in maintenance mode"); exceeding current throughput → **130429** ("Cloud API message throughput has been reached"). Coexistence numbers (also on WA Business app) fixed at 20 mps.
- SOURCE: .../throughput + .../support/error-codes [official]; chatarchitect mirror [BSP-mirror, matching text incl. 20 mps].

### P3. Pair rate limit (per business-number↔user pair)
- VERDICT: CONFIRMED
- WIRE: **1 message per 6 seconds to the same WhatsApp user** (~0.17 mps ≈ 600/hr). Bursting up to **45 messages** to the same user permitted, borrowing against quota: after a burst, wait proportionally (burst of 20 → ~2 min) before messaging that user again. Exceed → error **131056** — "Too many messages sent from the sender phone number to the same recipient phone number in a short period of time." Other recipients unaffected. Recommended retry: exponential backoff `4^X` seconds, X starting at 0, +1 per failure.
- SOURCE: docs/whatsapp/cloud-api/overview/ (pair rate limit section) [official]; error-codes [official].

### P4. MM Lite / Marketing Messages API: POST /<PHONE_NUMBER_ID>/marketing_messages
- VERDICT: CONFIRMED (now branded "Marketing Messages API (MM API) for WhatsApp"; "MM Lite" is the legacy name)
- WIRE: Send: `POST /<WHATSAPP_BUSINESS_PHONE_NUMBER_ID>/marketing_messages`. Envelope mirrors `/messages`: `messaging_product:"whatsapp"`, `recipient_type` (optional), `to` (required), `type:"template"` (required), `template:{name, language:{code}, components[]}` (required) — **marketing-category templates only**; other categories error/route to Cloud API. MM-specific optional fields (BSP API ref): `message_activity_sharing: bool` (true → additional **click** webhook events on CTA URL taps), `product_policy` (360dialog schema); `message_send_ttl_seconds` appears in 360dialog guides but is absent from their API-ref schema — TTL-field presence UNRESOLVED. Response: `{messaging_product, contacts:[{input, wa_id}], messages:[{id, message_status}]}` — same shape as `/messages`. Onboarding: business accepts "Marketing Messages API for WhatsApp" ToS (WhatsApp Manager > Overview alert, App Dashboard Quickstart, Embedded Signup, or Intent API); completion fires **`account_update` webhook with event `MM_LITE_TERMS_SIGNED`**; legacy event `AD_ACCOUNT_LINKED` (linked read-only ad account for Insights). Eligibility: `GET /<WABA_ID>?fields=marketing_messages_onboarding_status` (also on `GET /<BUSINESS_ID>`); partner listing `GET /<BUSINESS_PORTFOLIO_ID>/client_whatsapp_business_accounts?filtering=[{'field':'marketing_messages_onboarding_status','operator':'IN','value':['ELIGIBLE']}]`. Statuses: same pipeline (sent → delivered → read, unchanged webhook setup) + click events (only with `message_activity_sharing:true`); status/billing webhooks carry **`pricing.category = "marketing_lite"`** instead of `"marketing"`. Send-only API — inbound messages still via Cloud API webhooks.
- SOURCE: docs/whatsapp/marketing-messages-lite-api/ + /onboarding [official — endpoint, onboarding, MM_LITE_TERMS_SIGNED, marketing_messages_onboarding_status]; docs.360dialog.com marketing-messages pages + API ref [BSP-mirror — envelope, message_activity_sharing, marketing_lite]; infobip.com MM-Lite enable [BSP-mirror].

### P5. user_preferences webhook payload
- VERDICT: CONFIRMED
- WIRE: WABA-level, subscription field **`user_preferences`** (`object:"whatsapp_business_account"`, `changes[].field:"user_preferences"`). `changes[].value` = `{messaging_product:"whatsapp", metadata:{display_phone_number, phone_number_id}, contacts:[{wa_id}], user_preferences:[{wa_id: str, detail: str (human-readable, e.g. "User requested to resume marketing messages"), category: "marketing_messages" (only documented value), value: "stop" | "resume", timestamp: int unix-seconds (shown unquoted, e.g. 1731705721)}]}`. Fired on user opt-out ("stop") / opt-in ("resume") of marketing messages.
- SOURCE: docs/whatsapp/cloud-api/webhooks/reference/user_preferences/ [official — full example verbatim]; mirrored on new tree [official-secondary-tree, not separately fetched].

### P6. Messaging limits: portfolio-level + read field
- VERDICT: CONFIRMED (one correction: second tier is 2,000, not 1,000)
- WIRE: Verbatim: "Messaging limits are calculated and set at the business portfolio level and are shared by all business phone numbers within a portfolio" (effective Oct 7, 2025; existing portfolios set to the highest limit of any number in the portfolio). Tier ladder (current official page): **250** (default, new portfolios) → **2,000** → **10,000** → **100,000** → **unlimited** — old 1,000 tier no longer appears (CORRECTED vs pre-Oct-2025 ladder). Read current limit on the phone-number node: `GET /v25.0/{PHONE_NUMber_ID}?fields=whatsapp_business_manager_messaging_limit` → `{"whatsapp_business_manager_messaging_limit": "TIER_250", "id": "<PHONE_NUMBER_ID>"}` (field name confirmed; only enum value directly observed is `TIER_250` — exact enum strings for higher tiers, e.g. `TIER_2K`, are UNVERIFIED). Increases: 250→2,000 via business verification OR 2,000 delivered template messages; above that, automatic within ~6 hours when message quality is high and ≥50% of current limit used within 7 days. Limit-change webhooks: `business_capability_update` with `max_daily_conversations_per_business` (v24.0+) / `max_daily_conversation_per_phone` (≤v23.0); denials via `account_alerts` (`alert_type`, `alert_description`).
- SOURCE: docs/whatsapp/messaging-limits (fetched twice, consistent) [official]; 8x8 blog [BSP-mirror — portfolio computation for existing portfolios].

---

## Link schemes

### L1. wa.me links (`https://wa.me/<number>`, `https://wa.me/?text=`)
- VERDICT: CONFIRMED (caveat: the official help-center article is being redirected into developer docs as of this check)
- WIRE: `GET https://wa.me/<number>` — full international-format number, digits only ("Omit any zeroes, brackets, or dashes"; iOS variant stricter: "Omit any brackets, dashes, plus signs, and leading zeros"). Use `https://wa.me/1XXXXXXXXXX`; don't use `https://wa.me/+001-(XXX)XXXXXXX`. Number "must have an active account on WhatsApp". Prefill: `?text=<urlencodedtext>`. Text-only: `https://wa.me/?text=` → contact picker ("you'll be shown a list of contacts you can send your message to"). Text length: NO documented limit for `?text=`; the only official 140-char limit applies to managed QR/short links (`wa.me/message/<CODE>`). Live probe 2026-07-22: `https://wa.me/14155552671?text=hello%20world` → 302 → `https://api.whatsapp.com/send/?phone=14155552671&text=hello+world&type=phone_number&app_absent=0`; text-only form 302s with `type=custom_url`; wa.me forwards a `+` as `phone=%2B...` (docs say don't send it). CAVEAT: faq.whatsapp.com/5913398998672934 now JS-redirects to developers.facebook.com/docs/whatsapp/cloud-api/reference/qr-codes/ (legacy tree, itself 404 → superseded by new-tree QR page) — treat the dev-docs QR/short-links page as the maintained successor; wa.me format rules stable across every archived revision 2018→2025.
- SOURCE: faq.whatsapp.com/5913398998672934 [official; via Wayback 2020-06-20 server-rendered snapshot + current search snippet, which adds `https://wa.me/447XXXXXXXXX` as a second valid example]; live HTTP redirect check.

### L2. api.whatsapp.com/send?phone=&text=
- VERDICT: CONFIRMED as official-but-legacy; wa.me canonicalizes onto it
- WIRE: `GET https://api.whatsapp.com/send?phone=<number>&text=<urlencodedtext>`; text-only `...send?text=`. Same number rules (no `+`, zeros, brackets, dashes). Was THE documented click-to-chat format until ~2018 (2018-03-22 archive verbatim: "To create your own link, use https://api.whatsapp.com/send?phone= followed by the person's full phone number in international format"); 2019 FAQ revision switched to wa.me. Live-verified: wa.me is a redirector — every `wa.me/<number>` 302s to `api.whatsapp.com/send/?phone=...&type=phone_number&app_absent=0`; `api.whatsapp.com/send` returns 200 with an interstitial deep-linking into app/desktop. Emit wa.me in generated links; accept api.whatsapp.com/send only for parsing/normalizing inbound links.
- SOURCE: Wayback 2018-03-22 of faq.whatsapp.com/en/android/26000030 [official, archived]; live 302 chain check.

### L3. whatsapp:// scheme
- VERDICT: CONFIRMED officially documented (iOS help-center article) — but `phone=` parameter NOT in the official table; Android UNRESOLVED
- WIRE (verbatim from official iOS article): "Opening whatsapp:// URL with one of the following parameters, will open our app and perform a custom action" — path `app` (no params) → opens WhatsApp Messenger; path `send` → "New chat composer", parameter `text` → "pre-filled into message text input field on a conversation screen". Example: `whatsapp://send?text=Hello%2C%20World!`. iOS notes: add `whatsapp` to `LSApplicationQueriesSchemes` in Info.plist for `canOpenURL:`; article also documents Universal Links (wa.me, "preferred method"), Share Extension (accepted UTIs: plain-text, image, movie, audio, PDF, vCard, URL), Document Interaction. `whatsapp://send?phone=<number>` is NOT in the official parameter table in any archived revision — works de-facto, asserted by third-party/BSP mirrors only; if emitted, flag as de-facto, not official. Android: no official statement at all for `whatsapp://` — UNRESOLVED for Android (official Android guidance = wa.me universal links). Article now JS-redirects into developers.facebook.com (being retired); content from archived 2020-04-13 revision (last server-rendered).
- SOURCE: faq.whatsapp.com/425247423114725 [official; via Wayback 2020-04-13]; `phone=` support [BSP-mirror only: pureoxygenlabs.com, fvdm.com — do not treat as official].

### L4. web.whatsapp.com/send
- VERDICT: CONFIRMED still working; never officially documented; no deprecation notice found
- WIRE: `GET https://web.whatsapp.com/send?phone=<number>&text=<urlencodedtext>` → 200, WhatsApp Web client handles the `/send` route (requires linked-device login session; headless check stopped at the client's browser-version gate, not a 404/redirect — route accepted). No official documentation in any current or archived FAQ/developer page (both doc trees, FAQ archives 2018–2026, web search). Official desktop path: wa.me → api.whatsapp.com/send interstitial → user chooses WhatsApp Web/desktop; QR/short-links doc: "Desktop client launches with message populated in chat thread". Connector: don't emit `web.whatsapp.com/send`; parse as legacy inbound variant.
- SOURCE: live HTTP + browser check (2026-07-22); absence-of-doc across faq.whatsapp.com (live + Wayback) and both developers.facebook.com trees [official + search-snippet].

### L5. Group invite links chat.whatsapp.com/<code>
- VERDICT: CORRECTED — link format confirmed, but "creation is app-only (no API)" is now false: the WhatsApp Business Platform Groups API (GA since Oct 2025) creates groups and mints/resets invite links
- WIRE: Format (official): "`invite_link` always begins with the prefix `https://chat.whatsapp.com/`. The only variable portion is `<LINK_ID>`." No charset/length spec published for `<LINK_ID>` — UNRESOLVED beyond "opaque code" (empirically ~22 alphanumerics; do not hard-validate length). Consumer/app groups: creation and "Invite to group via link" remain app-only (Group info → Invite to group via link; resettable by admins); FAQ 3242937609289432 renders JS-only. Groups API (Cloud API, graph.facebook.com; OBA required; max 8 participants, 10,000 groups/business number; not for WhatsApp Business app numbers): invite link auto-generated at group creation. Endpoints (Bearer auth, body `{"messaging_product": "whatsapp"}`): `GET /<VERSION>/<GROUP_ID>/invite_link` → `{"messaging_product": "whatsapp", "invite_link": "https://chat.whatsapp.com/<LINK_ID>"}`; `POST /<VERSION>/<GROUP_ID>/invite_link` → resets (reference labels POST "Create a new group invite link"; guide labels it "Reset" — same call, previous links become invalid) → same response shape; `DELETE /<VERSION>/<GROUP_ID>/invite_link` → `{"messaging_product": ..., "success": ...}`. `GROUP_ID` sample: `Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD`. Offline link-builder: can only represent/validate `chat.whatsapp.com/<code>` links (prefix check), not create them — creation is app-only for consumers, API-only-for-OBA-businesses.
- SOURCE: groups/reference + reference/groups/groups-invite-link-api + groups overview + changelog entry 6 Oct 2025 "Introducing WhatsApp Groups API" [all official, fetched as raw markdown via new-tree `.md` endpoints]; consumer flow [search-snippet].

### L6. Official QR-code guidance for click-to-chat
- VERDICT: CONFIRMED, with an important taxonomy correction: WhatsApp has THREE distinct QR families, and only one is reproducible by an offline generator
- WIRE:
  - (a) **Plain click-to-chat QR** = QR encoding a wa.me URL. No official article prescribes rules for third-party encoding of wa.me links — only constraints are the wa.me URL rules (L1). UNRESOLVED as a distinct official spec: there is none; state as such in docs.
  - (b) **Managed business QR codes / short links** (`https://wa.me/message/<CODE>`): created only via WhatsApp Manager UI or `POST /<VERSION>/<PHONE_NUMBER_ID>/message_qrdls` with `{"prefilled_message": "<text ≤140 chars>", "generate_qr_image": "SVG"|"PNG"}` → `{"code", "prefilled_message", "deep_link_url": "https://wa.me/message/<CODE>", "qr_image_url"}`; GET (list / by-code); POST with `{"code", "prefilled_message"}` (update); DELETE `/message_qrdls/<CODE>`. Limits: ≤2,000 codes per WABA phone number; prefilled message ≤140 chars; no expiry until deleted; deleted code scans show "This QR code has expired"; no analytics. Official best practice for any generator: output SVG for print; "do not customize the color or look and feel of the code itself in order to preserve readability". Live redirect: `wa.me/message/<CODE>` → 302 → `api.whatsapp.com/message/<CODE>?autoload=1&app_absent=0`. An offline generator cannot mint `<CODE>`s.
  - (c) **Consumer/in-app contact QR** ("About WhatsApp QR codes"): proprietary payload generated in-app, adds the person as a contact, never expires unless reset/account deleted, resettable, "only share with trusted individuals". Not a wa.me URL; not reproducible offline — connector must explicitly not claim to generate these.
- SOURCE: .../qr-codes (+ `.md`) + reference/whatsapp-business-phone-number/whatsapp-business-qr-code-management-api [official]; facebook.com/business/help/890732351439459 (rendered live: 2,000-code limit, no-expiry, optional prefilled message → "open-ended conversation when scanned") [official]; faq.whatsapp.com/2416198805185327 [official, via Wayback 2023 snapshot].

---

## Cross-cutting notes for the implementer

- **Doc trees**: the NEW `/documentation/business-messaging/whatsapp/...` tree is canonical for Groups, QR codes, webhooks, typing indicators, mark-as-read, messaging limits, phone-number settings; business profile and block_users still live on legacy `/docs/whatsapp/cloud-api/...`. Where both were checked, content is equivalent. Appending `.md` to any new-tree path returns raw fetchable markdown (useful for re-verification). Raw WebFetch on developers.facebook.com returns 500/empty (JS-only) — browser rendering or `.md` endpoints required. The changelog page 500s on every direct fetch (facts taken from indexed snippets).
- **Current Graph API version observed in official examples**: v25.0.
- **Live-verify before freezing Pydantic models**: create-group synchronous response body (undocumented); `join_requests[]` approve/reject shape (ID strings vs objects); media webhook `url` on video/sticker types.
- **Drift-prone facts** (live official pages 2026-07-22, no version gates): pair-rate-limit numbers (P3) and messaging-limit tier ladder (P6).
- **Evidence-grade caveats** (facts held only at snippet/BSP grade): Flows publish-gate sentence; RSA 2048-bit key length; test-number recipient cap + payment exemption; X-Hub extended escape list; media retention windows.
- **Downloaded source copies** (scratchpad): `/private/tmp/claude-502/-Users-sachin-Documents-Projects-Agentic-ToolsConnector/8fcbd9c2-e484-4710-8033-51c6f362af0c/scratchpad/` — `qr.md`, `groups_reference.md`, `groups.md`, `reference_groups_groups-invite-link-api.md` (official md); `ctc2018.html`, `ctc2019.html`, `ctc2020.html` (archived click-to-chat FAQ); `linkapp2020.html` (archived whatsapp:// scheme FAQ).

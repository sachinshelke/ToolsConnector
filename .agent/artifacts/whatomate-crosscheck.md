# Whatomate production cross-check (2026-07-22)

Source: shallow clone of github.com/shridarpatil/whatomate @ 62be5a8 (2026-07-14), an
actively-maintained AGPL-3.0 Go/Vue self-hosted WhatsApp platform on the official Cloud
API. **AGPL: wire-protocol FACTS only — no code was or may be copied.** Compared against
`whatsapp-wire-register.md` and our `whatsapp_business` connector. Items marked APPLIED
were folded into W1 on 2026-07-22; the rest feed W2/P3.

## APPLIED to W1 (webhooks.py)
- `messages[].from_user_id` is what production payloads carry for BSUIDs (Meta docs say
  `user_id`) — model now accepts BOTH; resolve which is real at live-verify.
- `messages[].to` present on coexistence echo-shaped messages — added.
- `interactive.type == "call_permission_reply"` with
  `{response, is_permanent, expiration_timestamp (number-OR-string!), response_source}` — added as dict field.
- `contacts[].profile.username` exists; messages can arrive with EMPTY `from`
  (username-only users) — models tolerate.
- Error envelope also carries `error_user_msg` — now captured in error details.
- Corroborated: dedupe-by-wamid (Meta re-sends), monotonic status ladder
  (pending→sent→delivered→read; failed overrides; regressions ignored), HMAC over raw
  body w/ constant-time compare, always-ACK-200 + async processing, media `url` webhook
  field NOT yet reliable (keep the GET /MEDIA_ID fallback — we do).

## For W2 (management actions) — build against these
- Template list: MUST follow `paging` cursors (whatomate reads only first 100 → silent
  truncation bug in their product; don't repeat). Read BOTH `quality_rating` (string) and
  `quality_score{score}` — both shapes seen in the wild. `message_template_id` is
  **numeric** on the status webhook; `flow_id` numeric in template lists.
- `message_template_status_update` value is FLAT: `{event, message_template_id (int),
  message_template_name, message_template_language, reason}`.
- `smb_message_echoes` value uses `message_echoes[]` (NOT `messages[]`), same message
  shape; edit/revoke types. `smb_app_state_sync` value is FLAT: `{action: add|remove,
  contact_name, contact_first_name, contact_phone_number}`.
- Template send quirks: positional params must be sorted NUMERICALLY ("10" after "9");
  named params add `parameter_name`; buttons `sub_type: url|copy_code` + `index` as
  string; COPY_CODE param `{type:"coupon_code", coupon_code}`; auth/OTP buttons use
  `sub_type:"url"` + text param even for COPY_CODE otp_type; FLOW button auto-param
  `{type:"action", action:{flow_token}}`; DOCUMENT header without `filename` → error
  132012 "Header Format Mismatch".
- Template create: AUTH templates — BODY has no text (only
  `add_security_recommendation`), FOOTER only `code_expiration_minutes` (1-90), single
  OTP button `{type:"OTP", otp_type, supported_apps[]}`. **VOICE_CALL** is a real button
  type (absent from our register). Media header examples use `example.header_handle`.
- Resumable Upload (template media + profile pictures): data leg uses
  `Authorization: OAuth <token>` (NOT Bearer) + `file_offset: 0` header; response `{"h": handle}`.
- Analytics: granularity naming inconsistent per endpoint (DAY/MONTH vs DAILY/MONTHLY —
  normalize); `template_analytics` takes numeric UNQUOTED id array, daily-only, paginate
  `paging.next` (up to ~50 pages); responses can be nested `data[].data_points[]` OR flat.
  Also `call_analytics` field exists (dimensions(direction), metric_types COUNT/COST/AVERAGE_DURATION).
- Phone node coexistence detection: `is_on_biz_app` (bool), `platform_type`
  (SMB / SMB_CLOUD_API), `account_mode` (SANDBOX = test number); SMB numbers skip /register.
- ES: WABA discovery fallback `GET /me/accounts?fields=id,name,phone_numbers{...}` when
  granular_scopes is thin; post-ES order exchange → register (random PIN ok) →
  `POST /{WABA}/subscribed_apps` with NO body → `{success:true}`.
- BSUID send addressing: payloads accept `recipient: <BSUID>` alongside/instead of
  `to: <phone>` — our register has no BSUID send story yet.
- Commerce endpoints (absent from register): `GET|POST /{BUSINESS_ID}/owned_product_catalogs`,
  `GET|POST /{CATALOG_ID}/products` (price = integer-cents string), product node POST/DELETE.

## For P3 Calling API (the JS-walled surface — production-verified wire)
- Single endpoint `POST /{PHONE_NUMBER_ID}/calls`, `action` discriminator:
  `pre_accept`/`accept` = `{call_id, action, session:{sdp_type:"answer", sdp}}`;
  `reject`/`terminate` = `{call_id, action}` (NO session); outbound `connect` =
  `{action:"connect", to, session:{sdp_type:"offer", sdp}}` → `{"calls":[{"id":"wacid.xxx"}]}`.
- `GET /{PHONE_NUMBER_ID}/call_permissions?user_wa_id=` → `{permission:{status:
  no_permission|temporary|permanent}}`; permission lasts 72 h.
- `voice_call` interactive: `action:{name:"voice_call", parameters:{display_text ≤20,
  ttl_minutes (default 15), payload}}` — but Meta does NOT echo `payload` back on call
  webhooks (as of 2026-05); correlate yourself.
- `calls` webhook events: inbound ringing/connect(offer SDP)/in_call/ended/terminate/
  missed/unanswered; outbound also accepted/rejected; `connect` can be the FIRST event
  (ringing skipped); `terminate` can arrive after teardown; process call events
  SEQUENTIALLY (ordering matters). Business-initiated call status ALSO arrives in
  `value.statuses[]` under field:"calls" with UPPERCASE status (RINGING/ACCEPTED/REJECTED)
  — a parallel status channel our register lacks. `status` field wire-type unstable.
- SDP flow (user-initiated): webhook offer → answer via pre_accept → same answer via
  accept → media; DTMF is RTP-only (never webhooks).

## Error handling (negative result)
Whatomate special-cases ZERO numeric Graph codes (message-text only; send failures
terminal; retry = manual). Proves shipped products survive without code branching — our
typed mapping is a differentiator, not table stakes. Only literal they pin: 132012.

## Not exercised by Whatomate (no corroboration either way)
Groups API, message_qrdls, MM Lite, block_users, per-phone webhook overrides,
identity-change hashes, Flows encryption endpoint.

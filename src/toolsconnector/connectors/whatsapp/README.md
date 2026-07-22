# WhatsApp

> Offline click-to-chat primitives for personal WhatsApp: build/parse wa.me links, normalize numbers, render QR codes. Zero network calls, zero auth, zero ban risk.

| | |
|---|---|
| **Company** | Meta (WhatsApp) |
| **Category** | Communication |
| **Protocol** | Custom (offline — no HTTP at all) |
| **Base URL** | `https://wa.me` (link target, never called) |
| **Website** | https://www.whatsapp.com |
| **API Docs** | https://faq.whatsapp.com/5913398998672934 (click-to-chat) |
| **Auth** | None |
| **Rate Limit** | n/a (pure computation) |
| **Pricing** | Free |
| **Verification** | 🟡 **Tier 2 — Doc verified** (2026-07-22) — every scheme rule cross-checked against official WhatsApp documentation and pinned in tests; there is no vendor API for a live tier to exist against. |

## Why this connector exists (read this first)

**Personal WhatsApp has no official API.** Every "personal WhatsApp API" you'll find (Baileys, whatsmeow, whatsapp-web.js, and the hosted services reselling them) is a reverse-engineered client that violates WhatsApp's Terms of Service — Meta actively detects them (warning banners since May 2025, bans even at low volume) and litigates vendors. This library refuses to ship one.

What personal WhatsApp *does* officially offer is the **click-to-chat URL scheme** — and that's this connector: an agent (or your app) composes a perfect link or QR code, and **a human taps send**. For programmatic send/receive, use the [`whatsapp_business`](../whatsapp_business/README.md) connector (Meta's official Cloud API).

## Usage

```python
from toolsconnector.connectors.whatsapp import WhatsApp

wa = WhatsApp()  # no credentials — everything is offline
link = wa.build_chat_link("+1 (415) 555-2671", text="Hi! Saw your listing…")
# -> https://wa.me/14155552671?text=Hi%21%20Saw%20your%20listing%E2%80%A6
qr = wa.render_qr_svg(phone="+14155552671", text="Chat with us")  # needs toolsconnector[whatsapp]
```

Link rules enforced (per official docs): full international format, digits only — no `+`, brackets, dashes, or leading trunk zeros; prefilled text URL-encoded; E.164 length bounds (7–15 digits).

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Not supported

| Capability | Why |
|---|---|
| Sending/reading messages on a personal account | No official API; unofficial clients are ToS-violating and ban-prone — deliberately declined (see [`whatsapp_business`](../whatsapp_business/README.md) for the official API) |
| `wa.me/message/<CODE>` short links | Minted only by the Business API (`message_qrdls`) — parseable here, not creatable offline |
| Consumer contact QR codes | Proprietary in-app payload — not reproducible offline |
| Group invite link creation | App-only (or Groups API for Official Business Accounts) — this connector validates/parses them only |

# ContactOut

> B2B contact enrichment via ContactOut's official API. Search people by filters and enrich a LinkedIn URL / email / name+company into **work + personal emails and phone numbers**, find decision-makers, and verify emails. BYOK (your own ContactOut API key).

| | |
|---|---|
| **Company** | ContactOut |
| **Category** | Marketing |
| **Protocol** | REST (v1) |
| **Base URL** | `https://api.contactout.com` |
| **Website** | [contactout.com](https://contactout.com) |
| **API Docs** | [api.contactout.com](https://api.contactout.com) |
| **Auth** | API key in the `token` header (BYOK) |
| **Rate Limit** | People Search 60/min; free checkers 150/min; other 1000/min |
| **Pricing** | Team/API plan (paid). Credits across 4 pools (email / phone / search / verifier); free: `count_people`, `check_*_status`, `get_usage`. |
| **Verification** | 🟡 Tier 2 — Doc verified (built against ContactOut's documented v1 API + respx-pinned; live-verification pending a real Team/API-plan key) |

---

## What this is

A **BYOK wrapper over ContactOut's own API** — you bring your ContactOut key; ToolsConnector performs the protocol exchange only. **It does not scrape.** ContactOut sources the data and is the data controller under its own terms.

Contact data is returned under one **canonical, normalized shape** (`work_emails` / `personal_emails` / `phones`) regardless of ContactOut's per-endpoint field naming (which varies between `work_email`, `work_emails`, and `workEmail`).

**Manage spend:** reveal is gated by `reveal_info` on search (default `false` → browse profiles for free), and the free **`count_people`** + **`check_*_status`** endpoints let you pre-flight before spending email/phone credits.

## Getting credentials (BYOK)

1. A ContactOut **Team/API plan** (the API is not on the self-serve Email plans — it requires a sales/enterprise account).
2. Get your API key from the ContactOut dashboard — it's passed as the `token` header (note: **not** `Authorization: Bearer`).

## Compliance ⚠️

This connector returns **third-party personal data** (work + personal emails, phone numbers). ContactOut asserts (on its marketing/privacy pages, not in the API docs) GDPR **legitimate-interest** + CCPA compliance; its underlying data-sourcing methodology is not fully disclosed.

**You (and your customers) are responsible** for lawful basis, opt-out handling, and data-subject rights when processing returned personal/work emails and phone numbers (especially EU/UK GDPR and CA CCPA). Personal emails and phone numbers are personal data — handle accordingly. Use is bound by ContactOut's API terms.

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Coverage

Full v1 surface **plus** the v2 async bulk flow: sync bulk reveal (`get_linkedin_contact_info_bulk`, ≤100) and async bulk reveal (`enrich_linkedin_bulk_async`, ≤1000 + `get_bulk_reveal_job` to poll), single + bulk email verification (`verify_email`, `verify_emails_bulk`), and the free pre-flight `count_people` / `check_*_status` / `get_usage`.

## Not supported

| Capability | Why |
|---|---|
| Hosting the webhook callback for async jobs | `enrich_linkedin_bulk_async` / `verify_emails_bulk` accept your `callback_url`, but you host and secure that endpoint (BYOK — no callback server in the library). Poll `get_bulk_reveal_job` instead if you prefer. |
| Arbitrary people-search without a paid key | BYOK — you bring your own ContactOut Team/API entitlement. |

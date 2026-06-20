# Lusha

> B2B contact + company data via Lusha's official **V3 API**. Resolve people by name+company / email / LinkedIn URL and reveal their work/personal emails + phone numbers. BYOK (your own paid Lusha API key).

| | |
|---|---|
| **Company** | Lusha Systems Inc. |
| **Category** | Marketing |
| **Protocol** | REST (V3) |
| **Base URL** | `https://api.lusha.com` |
| **Website** | [lusha.com](https://www.lusha.com) |
| **API Docs** | [docs.lusha.com](https://docs.lusha.com) (V3) |
| **Auth** | API key in the `api_key` header (BYOK) |
| **Rate Limit** | 25 req/s general; plan-based daily/hourly quotas (response carries `x-*-requests-left`) |
| **Pricing** | Paid plan; credit-based (email = 1, phone = 5). Every call reports `billing.creditsCharged`. |
| **Verification** | 🟡 Tier 2 — Doc verified (built against Lusha's canonical V3 OpenAPI spec + respx-pinned; live-verification pending a real paid key) |

---

## What this is

A **BYOK wrapper over Lusha's own API** — you bring your Lusha API key; ToolsConnector performs the protocol exchange only. **It does not scrape.** Lusha sources the data (its Community Program, public sources, third parties) and is the data controller under its own terms.

The V3 **reveal flow is two-step**, which keeps you in control of spend:
1. **`search_contacts`** → a non-PII preview (profile + `id` + `canReveal`).
2. **`enrich_contacts`** (or one-shot **`search_and_enrich_contacts`**) → reveals `emails` + `phones`.

`emails[]` carry `type` (`work` / `private`) + confidence; `phones[]` carry `type` and a **`do_not_call`** flag. Read `credits_charged` on every result.

Beyond enrich/search/prospecting, the full V3 surface is covered: **lookalikes** (`find_contact_lookalikes` / `find_company_lookalikes`), **signals** (job-change/promotion + company hiring/headcount/intent/news, with `get_*_signal_types` and company signal-filter discovery), and **prospecting filter discovery** (`get_*_prospecting_filters`) to enumerate valid filter values.

## Getting credentials (BYOK)

1. A **paid Lusha plan** with API access.
2. Generate an API key in the [Lusha dashboard](https://dashboard.lusha.com) (API settings) — it's passed as the `api_key` header.
3. The key works server-side; V3 must be enabled on the account (else `403 "V3 API access is not enabled"`).

## Compliance ⚠️

This connector returns **third-party personal data** (emails, phone numbers). Lusha states a GDPR **legitimate-interest** legal basis and CCPA compliance, processes on your behalf under its DPA, and exposes opt-out / suppression. The connector surfaces Lusha's compliance signals so you can honor them: phones carry **`do_not_call`**, contacts carry `location.isEuContact`, and an HTTP **451** marks a GDPR-blocked record.

**You (and your customers) are responsible** for lawful basis, honoring DNC / opt-out / data-subject rights, and your own outreach compliance (GDPR/ePrivacy, TCPA, CAN-SPAM). Use is bound by [Lusha's API terms](https://www.lusha.com/legal/). Build against **V3** — V2 sunsets 2026-11-18.

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Not supported

| Capability | Why |
|---|---|
| Arbitrary people-search without a paid key | BYOK — you bring your own Lusha entitlement; this is not a free lookup. |
| Webhooks / subscriptions / account-secret endpoints | Out of scope for a contact/company connector (they live under a different `/api/...` prefix). |
| V2 (legacy) endpoints | Deprecated 2026-11-18; this connector targets V3 only. |

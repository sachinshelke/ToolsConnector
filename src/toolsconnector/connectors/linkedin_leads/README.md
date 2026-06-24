# LinkedIn Lead Sync

> Retrieve consented leads — name, email, phone, company — that members submitted to **your** LinkedIn Lead Gen Forms, via the Marketing Lead Sync API. BYOK OAuth 2.0.

| | |
|---|---|
| **Company** | LinkedIn (Microsoft) |
| **Category** | Marketing |
| **Protocol** | REST (versioned `/rest/*`) |
| **Base URL** | `https://api.linkedin.com` |
| **Website** | [linkedin.com](https://www.linkedin.com) |
| **API Docs** | [Lead Sync API](https://learn.microsoft.com/en-us/linkedin/marketing/lead-sync/leadsync) |
| **Auth** | OAuth 2.0 Bearer (BYOK) — scope `r_marketing_leadgen_automation` |
| **Rate Limit** | App + member quotas, enforced server-side |
| **Verification** | 🟡 Tier 2 — Doc verified (2026-06-20; every endpoint/scope/shape cross-checked against canonical docs + respx-pinned; live-verification pending an approved product with real leads) |

---

## Overview

LinkedIn **Lead Gen Forms** let members submit their details (pre-filled from their profile) directly inside an ad or an organic post. The **Lead Sync API** is how you pull those submissions into your own system — CRM, marketing automation, or an agent workflow.

This connector returns the leads you've collected, and — uniquely — resolves each lead's raw answers into **labeled contact fields** (`EMAIL`, `PHONE_NUMBER`, `FIRST_NAME`, …) so you don't have to hand-join answers against form definitions.

## What this is — and what it is **not**

✅ **Is:** a way to retrieve **first-party, opted-in** leads. Every person returned here *chose* to share their details with you by submitting one of your forms.

❌ **Is not:** an "search any LinkedIn member and get their email/phone" tool. **LinkedIn exposes no such API** — that capability is deliberately withheld for privacy and Terms-of-Service reasons, and faking it via scraping would violate LinkedIn's User Agreement (and likely data-protection law). This connector only ever returns leads from forms *you own*.

## Getting credentials (BYOK)

This connector performs only the protocol exchange — you bring your own OAuth 2.0 access token.

1. **Get the Lead Sync API product** for your [developer app](https://www.linkedin.com/developers/apps) → **Products** tab → request **Lead Sync API**. This requires LinkedIn review (verified company page, business email, approved use case) — it is **not** instant self-serve. See [Getting Access to Lead Sync](https://learn.microsoft.com/en-us/linkedin/marketing/lead-sync/getting-access-leadsync).
2. **Scope:** request `r_marketing_leadgen_automation` (forms + responses). Add `r_ads` if you also need to discover ad accounts.
3. **Roles:** the authenticating member must hold a qualifying role on the owner — e.g. `ACCOUNT_MANAGER`/`CAMPAIGN_MANAGER`/`VIEWER` on the Ad Account **and** `ADMINISTRATOR`/`LEAD_GEN_FORMS_MANAGER`/`CONTENT_ADMINISTRATOR` on the associated Company Page. Otherwise reads return `403 PermissionDeniedError`.
4. **Owner URN:** you'll pass your `urn:li:organization:{id}` (organic forms) or `urn:li:sponsoredAccount:{id}` (ad-account forms) — find these in [Campaign Manager](https://www.linkedin.com/campaignmanager).

## Getting labeled contact details

A lead's answers are keyed by integer `questionId`; the *meaning* (which one is the email) lives on the form. **`list_leads` does the join for you** — it fetches the owning form (once, cached) and fills `LeadResponse.fields`:

```python
from toolsconnector.serve import ToolKit
import json

kit = ToolKit(connectors=["linkedin_leads"], credentials={"linkedin_leads": TOKEN})

page = json.loads(kit.execute("linkedin_leads_list_leads", {
    "owner": "urn:li:sponsoredAccount:522529623",
    "lead_type": "SPONSORED",
    "count": 25,
}))

for lead in page["items"]:
    f = lead["fields"]
    print(f.get("FIRST_NAME"), f.get("LAST_NAME"), "|", f.get("EMAIL"), f.get("PHONE_NUMBER"))
```

Prefer `list_lead_responses` if you want the raw, unresolved answers (no extra form fetch).

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Not supported

| Capability | Why |
|---|---|
| Searching arbitrary people / scraping profiles for PII | No LinkedIn API offers it; against LinkedIn's Terms. Only opted-in leads from your own forms are available. |
| Creating / editing Lead Gen Forms | Out of scope for this read-focused connector — needs the `rw_ads` write surface of the Advertising API. |
| Lead webhooks / real-time notifications | The Lead Notifications subscription surface is not implemented here (polling via `list_leads` instead). |

## Notes

- Pinned to `Linkedin-Version: 202606`. LinkedIn Marketing versions are monthly `YYYYMM` strings valid ~12 months — see the [migrations guide](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/migrations) before bumping.
- Read-only. No action mutates anything; nothing is flagged `dangerous`.
- Generate **test leads** from Campaign Manager and fetch them with `test_only=true` to validate an integration without real PII.

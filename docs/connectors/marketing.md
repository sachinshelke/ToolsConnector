# Marketing

Connectors for B2B contact/company enrichment, consented lead capture, and email/audience marketing. 5 connectors, 87 actions.

All of these are **BYOK** (bring your own key) neutral wrappers over the vendors' own official APIs — ToolsConnector performs the protocol exchange only and never scrapes. The contact-data connectors return third-party PII; the caller owns lawful basis (GDPR legitimate-interest / CCPA), DNC/opt-out handling, and data-subject rights.

**Verification status** (see [Verification tiers](../../ROADMAP.md#verification-tiers) for what each tier means): ContactOut and Lusha are **Tier 1 (Live verified)**; LinkedIn Lead Sync is **Tier 2 (Doc verified)**; Mailchimp and SendGrid are **Tier 3 (Pattern)**.

---

### ContactOut

**Category:** Marketing | **Auth:** API key in the `token` header | **Actions:** 19 | **Verification:** ✅ Tier 1 (Live verified — all 19 actions round-tripped against the production API `api.contactout.com` 2026-06-24; **contract-scoped**, since the verifying key is entitled only to ContactOut's sample data in the *real* envelope shape, so shapes + paths are live-verified and real-data values await a fully-provisioned key)

B2B contact enrichment over ContactOut's official API: search people by filters, enrich a LinkedIn URL / email / name+company into **work + personal emails and phone numbers**, find decision-makers, reverse-lookup a LinkedIn profile from an email, sync + async bulk reveal (up to 1000, poll by job id), single + bulk email verification, plus **free** pre-flight existence checks (`count_people`, `check_*_status`) and usage. Reveal spends credits across four pools (email / phone / search / verifier).

**Live verification** caught 3 real wire bugs the respx suite had hidden: `get_usage` `/v1/usage`→`/v1/stats` (404), `verify_email` reading top-level `status` vs the API's `{data:{status}}` nesting, and `/email/enrich` dropping camelCase fields.

**Sample actions:** `search_people`, `enrich_linkedin_profile`, `enrich_people`, `get_decision_makers`, `verify_email`, `count_people` (free), `check_work_email_status` (free), `get_usage` (free) — +11 more in the [connector README](../../src/toolsconnector/connectors/contactout/README.md).

```python
kit = ToolKit(["contactout"], credentials={"contactout": "your-contactout-api-key"})
n = kit.execute("contactout_count_people", {"filters": {"job_title": ["VP Engineering"]}})  # free
```

---

### Lusha

**Category:** Marketing | **Auth:** API key in the `api_key` header | **Actions:** 20 | **Verification:** ✅ Tier 1 (Live verified — 18/20 actions round-tripped against the production API `api.lusha.com` with **real data** 2026-06-24; the other 2 are envelope-verified, both plan-gated on the free plan)

B2B contact + company data over Lusha's official **V3 API**. The reveal flow is two-step: `search_contacts` returns a non-PII preview + Lusha `id` + `canReveal`, then `enrich_contacts` (or one-shot `search_and_enrich_contacts`) reveals **work/personal emails + phone numbers**. Also: company search/enrich, filter-based prospecting, AI lookalikes, job-change/company signals, and filter discovery. Credit-based (email = 1, phone = 5); every call reports `billing.creditsCharged`.

**Live verification** caught 4 real bugs: `get_account_usage` returned the thin `/account/usage` instead of the rich `/v3/account/usage`; prospecting clamped `size` below Lusha's floor of 10 (→400); `get_*_signals` omitted the required `signalTypes` (→400); `LushaCompany` dropped `has`/`canReveal`. The 2 envelope-verified actions (company-signals → HTTP 402, decision-makers → empty on free) are plan-gated.

**Sample actions:** `search_contacts`, `enrich_contacts`, `search_and_enrich_contacts`, `enrich_companies`, `prospecting_search_contacts`, `find_contact_lookalikes`, `get_contact_signals`, `get_account_usage` — +12 more in the [connector README](../../src/toolsconnector/connectors/lusha/README.md).

```python
kit = ToolKit(["lusha"], credentials={"lusha": "your-lusha-api-key"})
preview = kit.execute("lusha_search_contacts", {"contacts": [{"linkedinUrl": "https://www.linkedin.com/in/…"}]})
```

---

### LinkedIn Lead Sync

**Category:** Marketing | **Auth:** OAuth 2.0 (`r_marketing_leadgen_automation`) | **Actions:** 5 | **Verification:** 🟡 Tier 2 (Doc verified — built against LinkedIn's canonical Lead Sync docs + respx-pinned; live-verification pending an approved Lead Sync product with real leads)

Retrieve **consented** leads (name, email, phone, company, …) that members voluntarily submitted to your LinkedIn **Lead Gen Forms**, via the Marketing Lead Sync API. `list_leads` resolves each lead's answers into labeled contact fields by joining them against the owning form. This is the legitimate "get people's contact details" surface — there is **no** people-search / arbitrary-PII-lookup capability; LinkedIn exposes no such API and this connector deliberately offers none.

**Actions:** `list_lead_forms`, `get_lead_form`, `list_lead_responses`, `get_lead_response`, `list_leads`. See the [connector README](../../src/toolsconnector/connectors/linkedin_leads/README.md).

---

### Mailchimp

**Category:** Marketing | **Auth:** API key (datacenter-suffixed, e.g. `key-us21`) | **Actions:** 23 | **Verification:** ⚪ Tier 3 (Pattern — matches Mailchimp's documented Marketing API; not yet doc- or live-verified)

Manage Mailchimp audiences, subscribers, and email campaigns: list/member CRUD, tags + segments, campaign create/content/schedule/send, and reporting. The datacenter prefix (the `usNN` in your key) routes the base URL automatically.

**Sample actions:** `add_member`, `delete_member`, `create_segment`, `create_campaign`, `get_campaign`, `get_campaign_content` — +17 more in the [connector README](../../src/toolsconnector/connectors/mailchimp/README.md).

---

### SendGrid

**Category:** Marketing | **Auth:** Bearer API key | **Actions:** 20 | **Verification:** ⚪ Tier 3 (Pattern — matches SendGrid's documented v3 API; not yet doc- or live-verified)

Send transactional email, manage marketing contacts + lists, view email statistics, manage templates, and handle suppressions (bounces / unsubscribes / spam reports).

**Sample actions:** `add_contacts`, `delete_contact`, `create_list`, `add_to_suppression`, `get_bounces`, `get_email_activity` — +14 more in the [connector README](../../src/toolsconnector/connectors/sendgrid/README.md).

---

> Compliance ⚠️ — ContactOut and Lusha return third-party personal data (work/personal emails, phone numbers). You and your customers are responsible for lawful basis (GDPR legitimate-interest / CCPA), honoring DNC / `isEuContact` flags, and opt-out / data-subject rights. See each connector's README for details.

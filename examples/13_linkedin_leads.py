"""LinkedIn Lead Sync — pull consented leads with resolved contact fields.

Lists the leads people *voluntarily submitted* to your LinkedIn Lead Gen Forms,
with each lead's answers already resolved to labeled contact fields
(``EMAIL`` / ``PHONE_NUMBER`` / ``FIRST_NAME`` / …) via ``list_leads``.

This is first-party, opt-in data ONLY — the people who filled out *your* forms.
LinkedIn exposes no "search arbitrary members → get their email/phone" API, and
this connector deliberately offers none.

Prerequisites:
    pip install "toolsconnector[linkedin_leads]"
    export TC_LINKEDIN_LEADS_CREDENTIALS='token with r_marketing_leadgen_automation'
    export TC_LINKEDIN_OWNER='urn:li:sponsoredAccount:123'   # or urn:li:organization:456

Note: needs the LinkedIn-**approved** "Lead Sync API" product (LinkedIn reviews
it — it is not self-serve). Without approval the calls return a clean 403.
"""

import json
import os

from toolsconnector.serve import ToolKit

TOKEN = os.environ.get("TC_LINKEDIN_LEADS_CREDENTIALS", "")
OWNER = os.environ.get("TC_LINKEDIN_OWNER", "")
if not TOKEN or not OWNER:
    raise SystemExit("set TC_LINKEDIN_LEADS_CREDENTIALS and TC_LINKEDIN_OWNER first")

kit = ToolKit(connectors=["linkedin_leads"], credentials={"linkedin_leads": TOKEN})

# SPONSORED leads come from a sponsoredAccount; organic (COMPANY/EVENT/...) from
# an organization. Pick the lead_type that matches your owner.
lead_type = "SPONSORED" if ":sponsoredAccount:" in OWNER else "COMPANY"

page = json.loads(
    kit.execute(
        "linkedin_leads_list_leads",
        {
            "owner": OWNER,
            "lead_type": lead_type,
            "count": 25,
        },
    )
)


def _present(value: object) -> str:
    """Leads are CONSENTED PII — a demo must show presence, never dump the raw
    email/phone to stdout. Mask in your own logs too (GDPR/CCPA)."""
    return "✓" if value else "—"


print(f"{len(page['items'])} lead(s):")
for lead in page["items"]:
    f = lead["fields"]  # resolved {FIELD_NAME: value}
    name = " ".join(filter(None, [f.get("FIRST_NAME"), f.get("LAST_NAME")]))
    has_email = bool(f.get("EMAIL") or f.get("WORK_EMAIL"))
    print(
        f"  {name or '(no name)'} | email {_present(has_email)} "
        f"phone {_present(f.get('PHONE_NUMBER'))} "
        f"| {f.get('COMPANY_NAME') or ''} {f.get('JOB_TITLE') or ''}"
    )

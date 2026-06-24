"""ContactOut — enrich a LinkedIn profile into emails + phones (BYOK, credit-aware).

Demonstrates the credit-conscious flow: a FREE match count to size an ICP, a
FREE pre-flight existence check, then the paid reveal, then your remaining
balance. The free steps (count_people, check_*_status, get_usage) spend nothing.

ContactOut wraps its OWN official API with your key — no scraping. What it
returns is third-party PII (work/personal email, phone); you are responsible for
lawful basis (GDPR legitimate-interest / CCPA) and opt-out handling.

Prerequisites:
    pip install "toolsconnector[contactout]"
    export TC_CONTACTOUT_CREDENTIALS='your-contactout-api-key'   # Team/API plan
    export TC_CONTACTOUT_PROFILE='https://www.linkedin.com/in/some-person'
"""

import json
import os

from toolsconnector.serve import ToolKit

TOKEN = os.environ.get("TC_CONTACTOUT_CREDENTIALS", "")
PROFILE = os.environ.get("TC_CONTACTOUT_PROFILE", "")
if not TOKEN or not PROFILE:
    raise SystemExit("set TC_CONTACTOUT_CREDENTIALS and TC_CONTACTOUT_PROFILE first")

kit = ToolKit(connectors=["contactout"], credentials={"contactout": TOKEN})

# 1) FREE — size an ICP before spending a single credit.
total = json.loads(
    kit.execute(
        "contactout_count_people",
        {"filters": {"job_title": ["VP Engineering"], "company_size": ["1000_5000"]}},
    )
)
print(f"ICP match count (free): {total}")

# 2) FREE — does this profile even have a work email? (no reveal, no credits)
status = json.loads(kit.execute("contactout_check_work_email_status", {"profile": PROFILE}))
print(f"work email available (free check): {status}")

# 3) PAID — reveal the contact data (spends email/phone credits).
prof = json.loads(kit.execute("contactout_enrich_linkedin_profile", {"profile": PROFILE}))
print(f"\n{prof.get('full_name') or '(unknown)'} — {prof.get('title') or ''}")
print(f"  work emails:     {prof.get('work_emails')}")
print(f"  personal emails: {prof.get('personal_emails')}")
print(f"  phones:          {prof.get('phones')}")

# 4) FREE — what's left? check remaining balances per credit pool.
usage = json.loads(kit.execute("contactout_get_usage", {}))
print(f"\nremaining credits (free): {usage}")

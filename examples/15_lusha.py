"""Lusha — two-step search → enrich (preview, then reveal), credit-aware (BYOK).

V3's reveal flow keeps you in control of spend:
  1. search_contacts → a non-PII preview + a Lusha id + what each reveal costs
  2. enrich_contacts(ids) → reveal emails + phones (billing reports creditsCharged)

Lusha wraps its OWN paid API with your key — no scraping. What it returns is
third-party PII; honor the per-phone ``do_not_call`` flag and your own lawful
basis (GDPR legitimate-interest / CCPA).

Prerequisites:
    pip install "toolsconnector[lusha]"
    export TC_LUSHA_CREDENTIALS='your-lusha-api-key'   # paid plan, V3 enabled
"""

import json
import os

from toolsconnector.serve import ToolKit

TOKEN = os.environ.get("TC_LUSHA_CREDENTIALS", "")
if not TOKEN:
    raise SystemExit("set TC_LUSHA_CREDENTIALS first")

kit = ToolKit(connectors=["lusha"], credentials={"lusha": TOKEN})

# 1) Resolve a person to a Lusha id (preview — no emails/phones yet, cheap).
preview = json.loads(
    kit.execute(
        "lusha_search_contacts",
        {"contacts": [{"firstName": "Ada", "lastName": "Lovelace", "companyName": "Lusha"}]},
    )
)
if not preview["contacts"]:
    raise SystemExit("no match for that person")
contact = preview["contacts"][0]
print(f"matched id={contact['id']} | can_reveal={contact.get('can_reveal')}")

# 2) Reveal emails + phones for that id (this is the step that spends credits).
revealed = json.loads(
    kit.execute(
        "lusha_enrich_contacts",
        {"ids": [contact["id"]], "reveal": ["emails", "phones"]},
    )
)
person = revealed["contacts"][0]
print(f"\n{person.get('full_name') or '(unknown)'}")
for email in person.get("emails", []):
    print(f"  email: {email['email']} ({email.get('type')})")
for phone in person.get("phones", []):
    dnc = " [DO NOT CALL]" if phone.get("do_not_call") else ""
    print(f"  phone: {phone['number']}{dnc}")
print(f"credits charged: {revealed['credits_charged']}")

# 3) Check remaining account balance (free).
usage = json.loads(kit.execute("lusha_get_account_usage", {}))
print(f"\naccount usage: {usage}")

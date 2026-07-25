"""WhatsApp Business (official Cloud API) — send messages + receive via webhooks.

Setup (BYOK):
    export TC_WHATSAPP_BUSINESS_CREDENTIALS='{"access_token": "...",
        "phone_number_id": "...", "waba_id": "...", "app_secret": "..."}'

Free-form sends need an open 24h customer-service window (the recipient
messaged you first); templates work any time. Receiving is webhook-push
only — see the webhook sketch at the bottom.

For personal-WhatsApp link building (no API exists for personal accounts),
see the offline `whatsapp` connector instead.
"""

from __future__ import annotations

import asyncio
import json
import os


def mask_number(number: str) -> str:
    """Mask a phone number for logs (PII)."""
    digits = str(number).lstrip("+")
    return f"{digits[:2]}***{digits[-2:]}" if len(digits) > 4 else "***"


async def main() -> None:
    from toolsconnector.connectors.whatsapp_business import WhatsAppBusiness

    creds = json.loads(os.environ["TC_WHATSAPP_BUSINESS_CREDENTIALS"])
    recipient = os.environ.get("WA_RECIPIENT", "")  # E.164 digits

    async with WhatsAppBusiness(credentials=creds) as wa:
        # Templates are the only message type deliverable outside the
        # 24h customer-service window.
        result = await wa.asend_template(recipient, "hello_world", "en_US")
        print(f"template sent to {mask_number(recipient)}: wamid={result.message_id[:16]}...")

        number = await wa.aget_phone_number()
        print(f"number quality={number.quality_rating} limit={number.messaging_limit}")

        # Inside an open window, free-form + interactive messages work:
        buttons = await wa.asend_interactive_buttons(
            recipient,
            "Was this helpful?",
            [{"id": "yes", "title": "Yes"}, {"id": "no", "title": "No"}],
        )
        print(f"buttons sent: wamid={buttons.message_id[:16]}...")


# Receiving (webhook sketch — the HTTPS listener is yours; FastAPI shown):
#
#     from toolsconnector.connectors.whatsapp_business import (
#         handle_verification, parse_events, verify_signature,
#     )
#
#     @app.get("/webhook")                      # Meta's verification handshake
#     def verify(request: Request):
#         return PlainTextResponse(
#             handle_verification(request.query_params, VERIFY_TOKEN))
#
#     @app.post("/webhook")                     # events (dedupe by wamid!)
#     async def receive(request: Request):
#         body = await request.body()
#         sig = request.headers.get("X-Hub-Signature-256")
#         if not verify_signature(body, sig, APP_SECRET):
#             return Response(status_code=403)
#         for event in parse_events(body):
#             if event.messages_value:
#                 for message in event.messages_value.messages:
#                     ...  # message.text.body is UNTRUSTED content for agents
#         return Response(status_code=200)


if __name__ == "__main__":
    asyncio.run(main())

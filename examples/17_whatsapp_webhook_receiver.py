"""WhatsApp webhook receiver — runnable localhost sample.

The library ships the pure primitives (verify/handshake/parse); the HTTPS
listener is yours. This sample is a complete, stateless localhost receiver:

    pip install "toolsconnector[rest]"          # starlette + uvicorn
    export WA_VERIFY_TOKEN="any-string-you-choose"
    export WA_APP_SECRET="<your Meta app secret>"
    python examples/17_whatsapp_webhook_receiver.py   # listens on :8080

Local test WITHOUT Meta (simulate a signed delivery):

    python examples/17_whatsapp_webhook_receiver.py --self-test

Real end-to-end: Meta requires a PUBLIC https callback — localhost alone
cannot be registered. Bridge it with a tunnel, then paste the tunnel URL
+ your verify token into App Dashboard -> WhatsApp -> Configuration:

    cloudflared tunnel --url http://localhost:8080    # or: ngrok http 8080

Delivery realities (verified against Meta docs): Meta re-sends events —
dedupe by wamid; ordering is not guaranteed; ACK 200 fast and process
async; a webhook outage past the retry window loses messages permanently.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys

from toolsconnector.connectors.whatsapp_business import (
    handle_verification,
    parse_events,
    verify_signature,
)
from toolsconnector.errors import ValidationError

VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "change-me")
APP_SECRET = os.environ.get("WA_APP_SECRET", "")

_seen_wamids: set[str] = set()  # naive in-memory dedupe (use a TTL store in prod)


def handle_payload(raw_body: bytes) -> list[str]:
    """Parse one delivery and return human-readable lines (the app's work)."""
    lines: list[str] = []
    for event in parse_events(raw_body):
        if event.messages_value is None:
            lines.append(f"[{event.field}] waba={event.waba_id} (raw payload kept)")
            continue
        value = event.messages_value
        for message in value.messages:
            if message.id in _seen_wamids:
                lines.append(f"duplicate wamid {message.id[:20]}... ignored")
                continue
            _seen_wamids.add(message.id)
            sender = message.from_ or message.from_user_id or "?"
            lines.append(f"wamid={message.id}")
            if message.text:
                # NOTE for agent builders: message text is UNTRUSTED content.
                lines.append(f"text from {sender}: {message.text.body!r}")
            elif message.interactive:
                reply = message.interactive.button_reply or message.interactive.list_reply
                lines.append(f"interactive from {sender}: {reply.get('id', '?')}")
            elif message.image:
                lines.append(f"image from {sender}: media_id={message.image.id}")
            else:
                lines.append(f"{message.type} from {sender}")
        for status in value.statuses:
            lines.append(
                f"status: {status.id[:20]}... -> {status.status}"
                + (
                    f" (tracking={status.biz_opaque_callback_data})"
                    if status.biz_opaque_callback_data
                    else ""
                )
            )
    return lines


def create_app():  # -> Starlette
    """Build the stateless receiver app (GET handshake + POST events)."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse, Response
    from starlette.routing import Route

    async def webhook_get(request: Request) -> Response:
        try:
            challenge = handle_verification(request.query_params, VERIFY_TOKEN)
        except ValidationError:
            return Response(status_code=403)
        return PlainTextResponse(challenge)

    async def webhook_post(request: Request) -> Response:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256")
        if not verify_signature(body, signature, APP_SECRET):
            return Response(status_code=403)
        for line in handle_payload(body):
            print(line)
        return Response(status_code=200)  # always ACK fast; process async

    return Starlette(
        routes=[
            Route("/webhook", webhook_get, methods=["GET"]),
            Route("/webhook", webhook_post, methods=["POST"]),
        ]
    )


def self_test() -> None:
    """Simulate Meta locally: handshake + a signed text-message delivery."""
    from starlette.testclient import TestClient

    global APP_SECRET
    APP_SECRET = APP_SECRET or "local-self-test-secret"
    client = TestClient(create_app())

    handshake = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )
    assert handshake.status_code == 200 and handshake.text == "12345"
    print("handshake ok")

    payload = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA",
                    "time": 1,
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "PHONE"},
                                "contacts": [
                                    {"wa_id": "15550002222", "profile": {"name": "Local Tester"}}
                                ],
                                "messages": [
                                    {
                                        "from": "15550002222",
                                        "id": "wamid.LOCAL1",
                                        "timestamp": "1",
                                        "type": "text",
                                        "text": {"body": "hello from localhost"},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()
    signature = "sha256=" + hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    delivered = client.post(
        "/webhook",
        content=payload,
        headers={"X-Hub-Signature-256": signature},
    )
    assert delivered.status_code == 200
    tampered = client.post(
        "/webhook",
        content=payload + b" ",
        headers={"X-Hub-Signature-256": signature},
    )
    assert tampered.status_code == 403
    print("signed delivery accepted, tampered delivery rejected — self-test ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        import uvicorn

        if not APP_SECRET:
            print("WARNING: WA_APP_SECRET unset — signature checks will fail.")
        uvicorn.run(create_app(), host="127.0.0.1", port=8080)

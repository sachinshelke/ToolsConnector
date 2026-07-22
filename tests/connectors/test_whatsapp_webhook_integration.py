"""End-to-end webhook-receiver integration test (localhost, no Meta needed).

Proves the full receive loop the way a platform would run it: an ASGI app
built from the pure primitives — GET verification handshake, signed POST
delivery, signature rejection, batched entries, wamid dedupe. Mirrors
examples/17_whatsapp_webhook_receiver.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

starlette = pytest.importorskip("starlette")

from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import PlainTextResponse, Response  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from toolsconnector.connectors.whatsapp_business import (  # noqa: E402
    handle_verification,
    parse_events,
    verify_signature,
)
from toolsconnector.errors import ValidationError  # noqa: E402

VERIFY_TOKEN = "integration-verify-token"
APP_SECRET = "integration-app-secret"


def build_receiver(received: list) -> Starlette:
    seen: set[str] = set()

    async def webhook_get(request: Request) -> Response:
        try:
            return PlainTextResponse(handle_verification(request.query_params, VERIFY_TOKEN))
        except ValidationError:
            return Response(status_code=403)

    async def webhook_post(request: Request) -> Response:
        body = await request.body()
        if not verify_signature(body, request.headers.get("X-Hub-Signature-256"), APP_SECRET):
            return Response(status_code=403)
        for event in parse_events(body):
            if event.messages_value:
                for message in event.messages_value.messages:
                    if message.id in seen:
                        continue
                    seen.add(message.id)
                    received.append(message)
        return Response(status_code=200)

    return Starlette(
        routes=[
            Route("/webhook", webhook_get, methods=["GET"]),
            Route("/webhook", webhook_post, methods=["POST"]),
        ]
    )


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def envelope(*messages: dict) -> bytes:
    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA1",
                    "time": 1,
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "PHONE1"},
                                "messages": list(messages),
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()


def message(wamid: str, sender: str, text: str) -> dict:
    return {"from": sender, "id": wamid, "timestamp": "1", "type": "text", "text": {"body": text}}


def test_full_receive_loop() -> None:
    received: list = []
    client = TestClient(build_receiver(received))

    # 1. Meta's verification handshake
    handshake = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )
    assert handshake.status_code == 200
    assert handshake.text == "1158201444"
    bad_handshake = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "1",
        },
    )
    assert bad_handshake.status_code == 403

    # 2. Signed delivery from MULTIPLE senders on the same number
    body = envelope(
        message("wamid.A1", "15550002222", "hi from alice"),
        message("wamid.B1", "15550003333", "hi from bob"),
    )
    assert (
        client.post(
            "/webhook",
            content=body,
            headers={"X-Hub-Signature-256": sign(body)},
        ).status_code
        == 200
    )
    assert [m.from_ for m in received] == ["15550002222", "15550003333"]

    # 3. Meta retry (same wamids) -> deduped, still ACKed 200
    assert (
        client.post(
            "/webhook",
            content=body,
            headers={"X-Hub-Signature-256": sign(body)},
        ).status_code
        == 200
    )
    assert len(received) == 2

    # 4. Tampered body -> rejected before parsing
    assert (
        client.post(
            "/webhook",
            content=body + b" ",
            headers={"X-Hub-Signature-256": sign(body)},
        ).status_code
        == 403
    )
    # 5. Missing signature -> rejected
    assert client.post("/webhook", content=body).status_code == 403
    assert len(received) == 2


def test_example_self_test_runs() -> None:
    """The runnable localhost sample's --self-test path stays green."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "examples" / "17_whatsapp_webhook_receiver.py"
    spec = importlib.util.spec_from_file_location("wa_receiver_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    module.self_test()

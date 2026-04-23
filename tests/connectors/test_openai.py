"""End-to-end tests for the OpenAI connector using respx.

Same pattern as test_slack.py / test_github.py. Exercises OpenAI's
specifics:

  - **Per-request httpx.AsyncClient** — connector creates a fresh
    client inside `_request()` rather than reusing a long-lived one.
    respx still intercepts because it patches the transport globally.
  - **Two-level response parsing** — top-level `id`/`object`/`created`/
    `model` plus a `choices: list` plus a nested `usage` dict.
  - **Bearer + JSON content-type** auth (no API-key-as-query-param).
  - **Optional `tools` parameter** — must NOT appear in the request
    body when `tools=None` (vendor APIs are picky about None vs absent).

Note: the connector module is named `openai_connector` (with the suffix)
to avoid shadowing the official `openai` PyPI package — the connector
class itself is just `OpenAI`.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.openai_connector import OpenAI

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def openai() -> OpenAI:
    """OpenAI connector with a fake API key.

    Key never hits api.openai.com because respx patches httpx.
    """
    connector = OpenAI(credentials="sk-fake-test-key")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — chat completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_happy_path(openai: OpenAI) -> None:
    """chat_completion: POST /chat/completions → ChatCompletion model.

    Verifies request shape (model + messages in body), auth header,
    and response parsing (choices + usage).
    """
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=True) as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-abc123",
                    "object": "chat.completion",
                    "created": 1700000000,
                    "model": "gpt-4o-2024-08-06",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hi there!"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 4,
                        "total_tokens": 11,
                    },
                },
            )
        )

        result = await openai.achat_completion(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Say hi"}],
        )

        # Top-level fields parsed correctly
        assert result.id == "chatcmpl-abc123"
        assert result.model == "gpt-4o-2024-08-06"

        # Choices structure parsed
        assert len(result.choices) == 1
        assert result.choices[0].message.content == "Hi there!"
        assert result.choices[0].finish_reason == "stop"

        # Usage parsed
        assert result.usage is not None
        assert result.usage.total_tokens == 11

        # Auth header
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer sk-fake-test-key"
        assert request.headers["content-type"] == "application/json"

        # Body has model + messages, no None fields
        body = request.read()
        assert b'"model":"gpt-4o"' in body
        assert b'"messages"' in body


@pytest.mark.asyncio
async def test_chat_completion_optional_params_omitted_when_none(openai: OpenAI) -> None:
    """When `tools=None` and `temperature=None`, those keys must NOT
    appear in the request body. OpenAI's API treats `null` values
    differently from missing keys for some parameters.
    """
    with respx.mock(base_url="https://api.openai.com/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o",
                    "choices": [],
                    "usage": None,
                },
            )
        )

        await openai.achat_completion(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        body = route.calls.last.request.read()
        # Required fields present
        assert b'"model"' in body
        assert b'"messages"' in body
        # Optional fields with default None must be omitted, not sent as null
        assert b'"tools"' not in body
        assert b'"temperature"' not in body
        assert b'"max_tokens"' not in body


# ---------------------------------------------------------------------------
# 2. Tools / function-calling parameter passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_with_tools_passthrough(openai: OpenAI) -> None:
    """When `tools=[{...}]` is passed, it appears in the request body
    AND tool_calls in the response are surfaced on the parsed message.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }
    ]

    with respx.mock(base_url="https://api.openai.com/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "gpt-4o",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_abc",
                                        "type": "function",
                                        "function": {
                                            "name": "get_weather",
                                            "arguments": '{"city": "Paris"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
                },
            )
        )

        result = await openai.achat_completion(
            model="gpt-4o", messages=[{"role": "user", "content": "weather in Paris?"}], tools=tools
        )

        # tools landed in the body
        body = route.calls.last.request.read()
        assert b'"tools"' in body
        assert b'"get_weather"' in body

        # tool_calls came through to the message
        msg = result.choices[0].message
        assert msg.content is None
        assert msg.tool_calls is not None
        assert msg.tool_calls[0]["function"]["name"] == "get_weather"
        assert result.choices[0].finish_reason == "tool_calls"


# ---------------------------------------------------------------------------
# 3. Error mapping — HTTP errors surface as HTTPStatusError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_api_key_raises_http_status_error(openai: OpenAI) -> None:
    """OpenAI returns 401 with body when the key is invalid."""
    with respx.mock(base_url="https://api.openai.com/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                401,
                json={
                    "error": {
                        "message": "Incorrect API key provided",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
            )
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await openai.achat_completion(
                model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
            )

        assert exc_info.value.response.status_code == 401


@pytest.mark.asyncio
async def test_rate_limit_raises_http_status_error(openai: OpenAI) -> None:
    """429 → HTTPStatusError. (Future improvement: map to RateLimitError.)"""
    with respx.mock(base_url="https://api.openai.com/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "20"},
                json={"error": {"message": "Rate limit exceeded"}},
            )
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await openai.achat_completion(
                model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
            )

        assert exc_info.value.response.status_code == 429


# ---------------------------------------------------------------------------
# 4. Spec metadata — dangerous flag
# ---------------------------------------------------------------------------


def test_dangerous_actions_are_flagged() -> None:
    """delete_model is destructive → must be dangerous=True.
    Read/generate actions are NOT dangerous (they spend money but
    don't destroy state).
    """
    spec = OpenAI.get_spec()
    assert spec.actions["delete_model"].dangerous is True
    assert spec.actions["chat_completion"].dangerous is False
    assert spec.actions["create_embedding"].dangerous is False
    assert spec.actions["list_models"].dangerous is False

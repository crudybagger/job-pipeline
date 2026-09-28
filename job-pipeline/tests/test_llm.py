"""Tests for the shared LLM foundation (docs/design/stage2-lld.md).

All provider calls run against httpx.MockTransport or a scripted client —
no live network in the test suite.
"""

import json

import httpx
import pytest

from src.llm import provider
from src.llm.provider import LLMClient, LLMError, complete, set_client


def _chat_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_complete_sends_messages_and_returns_content():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_chat_response("hello"))

    client = LLMClient(
        api_key="test-key", model="test-model", transport=_transport(handler)
    )
    result = client.complete("sys prompt", "user prompt")
    assert result == "hello"
    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer test-key"
    payload = seen["payload"]
    assert payload["model"] == "test-model"
    assert payload["messages"][0] == {"role": "system", "content": "sys prompt"}
    assert payload["messages"][1] == {"role": "user", "content": "user prompt"}
    assert "response_format" not in payload


def test_schema_enables_json_mode_and_instruction():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_chat_response("{}"))

    client = LLMClient(api_key="k", transport=_transport(handler))
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    client.complete("sys", "user", schema=schema)
    payload = seen["payload"]
    assert payload["response_format"] == {"type": "json_object"}
    assert "JSON object matching this schema" in payload["messages"][1]["content"]
    assert json.dumps(schema) in payload["messages"][1]["content"]


def test_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=_chat_response("ok"))

    client = LLMClient(
        api_key="k", max_retries=2, backoff=0, transport=_transport(handler)
    )
    assert client.complete("sys", "user") == "ok"
    assert calls["n"] == 2


def test_exhausted_retries_raise_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = LLMClient(
        api_key="k", max_retries=1, backoff=0, transport=_transport(handler)
    )
    with pytest.raises(LLMError):
        client.complete("sys", "user")


def test_missing_api_key_raises_llm_error():
    client = LLMClient(api_key="")
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        client.complete("sys", "user")


def test_module_seam_uses_set_client():
    class StubClient:
        def complete(self, system, user, schema=None):
            return "from-stub"

    stub = StubClient()
    set_client(stub)  # type: ignore[arg-type]
    try:
        assert complete("sys", "user") == "from-stub"
    finally:
        set_client(None)


def test_get_client_constructs_default_when_unset(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    set_client(None)
    client = provider.get_client()
    assert isinstance(client, LLMClient)
    assert client.api_key == "env-key"
    set_client(None)

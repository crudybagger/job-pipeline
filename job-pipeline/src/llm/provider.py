"""Shared LLM foundation: OpenAI-compatible provider abstraction.

One abstraction used by Stage 1's pluggable `llm` scorer slot and the
Stage 2-3 generation substages (docs/design/pipeline-integration.md):
`complete(system, user, schema=None)` with JSON-mode support. Provider,
endpoint, key and model come from .env (LLM_BASE_URL, LLM_API_KEY,
LLM_MODEL); retry/timeout handling is built in. The module-level
`complete()` resolves the settable default client so tests (and any
caller) can monkey-patch the seam — no live external calls in CI.
"""

import json
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF = 1.0

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Raised when the LLM provider call fails or is not configured."""


class LLMClient:
    """OpenAI-compatible chat-completions client over httpx."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        backoff: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (
            base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = (
            api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
        )
        self.model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        self.timeout = DEFAULT_TIMEOUT if timeout is None else timeout
        self.max_retries = DEFAULT_MAX_RETRIES if max_retries is None else max_retries
        self.backoff = DEFAULT_BACKOFF if backoff is None else backoff
        self.transport = transport

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        """Complete a chat prompt; returns the assistant message content.

        When `schema` is given the user message gains a JSON-schema
        instruction and the request enables OpenAI JSON mode. Retries on
        429/5xx and network errors with linear backoff; raises LLMError
        when the API key is missing or all retries are exhausted.
        """
        if not self.api_key:
            raise LLMError(
                "LLM_API_KEY is not configured (set it in job-pipeline/.env)"
            )
        messages = [{"role": "system", "content": system}]
        if schema is not None:
            user = (
                f"{user}\n\nRespond ONLY with a JSON object matching this "
                f"schema: {json.dumps(schema)}"
            )
        messages.append({"role": "user", "content": user})
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}

        last_error: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                client_kwargs: dict[str, Any] = {"timeout": self.timeout}
                if self.transport is not None:
                    client_kwargs["transport"] = self.transport
                with httpx.Client(**client_kwargs) as http:
                    response = http.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                if response.status_code in RETRYABLE_STATUS:
                    last_error = LLMError(
                        f"LLM HTTP {response.status_code}: {response.text[:200]}"
                    )
                else:
                    response.raise_for_status()
                    return response.json()["choices"][0]["message"]["content"]
            except LLMError:
                pass
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_error = LLMError(f"LLM call failed: {exc}")
            if attempt < self.max_retries and self.backoff:
                time.sleep(self.backoff * (attempt + 1))
        raise last_error or LLMError("LLM call failed")


# Settable default client so tests and callers can monkey-patch the seam.
_default_client: LLMClient | None = None


def set_client(client: LLMClient | None) -> None:
    """Set (or clear with None) the module default client."""
    global _default_client
    _default_client = client


def get_client() -> LLMClient:
    """Return the module default client, constructing one when unset."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def complete(system: str, user: str, schema: dict | None = None) -> str:
    """Complete a chat prompt via the module default client (mockable seam)."""
    return get_client().complete(system, user, schema=schema)

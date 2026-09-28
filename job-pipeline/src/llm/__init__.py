"""Shared LLM foundation (docs/design/pipeline-integration.md).

OpenAI-compatible provider abstraction with a mockable module-level
`complete()` seam; serves Stage 1's pluggable `llm` scorer slot and the
Stage 2-3 generation substages.
"""

from src.llm.provider import LLMClient, LLMError, complete, get_client, set_client

__all__ = ["LLMClient", "LLMError", "complete", "get_client", "set_client"]

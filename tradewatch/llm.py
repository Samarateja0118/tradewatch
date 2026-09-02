"""LLM access, behind the one-method interface the pipeline depends on.

The pipeline only ever calls `complete(system, user) -> str`, so the whole
thing is testable with `FakeLLM` and the provider can be swapped without
touching pipeline code.
"""

from __future__ import annotations

import logging
import os

from anthropic import AsyncAnthropic

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"

# Both prompts ask for a small JSON object. Low effort is the right setting:
# this is structured extraction, not open-ended reasoning, and the prefilter
# has already done the coarse work.
EFFORT = "low"

# Thinking is on by default on this model and shares the budget with the
# response, so leave headroom. Disabling it would be cheaper but can leak
# `<thinking>` tags into the text we then try to parse as JSON.
MAX_TOKENS = 8000


class AnthropicClient:
    """Real client. One call per document per stage."""

    def __init__(self, api_key: str | None = None, model: str = MODEL) -> None:
        # AsyncAnthropic resolves ANTHROPIC_API_KEY itself; the explicit check
        # just turns a confusing 401 mid-run into a clear failure at startup.
        if api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it, or pass api_key=..."
            )
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            output_config={"effort": EFFORT},
            messages=[{"role": "user", "content": user}],
        )

        if response.stop_reason == "refusal":
            # Surfaces as a parse failure downstream, which keeps the document
            # for human review rather than silently dropping it.
            log.warning("Model declined to assess this document")
            return ""

        return "".join(block.text for block in response.content if block.type == "text")

    async def aclose(self) -> None:
        await self._client.close()


class FakeLLM:
    """Deterministic stand-in for tests and dry runs.

    Returns the same canned response to every call and records what it was
    asked, so tests can assert on prompt construction if they need to.
    """

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response

    async def aclose(self) -> None:
        return None

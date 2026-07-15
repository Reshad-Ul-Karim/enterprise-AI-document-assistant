"""The Mistral adapter. The ONLY module that imports `mistralai`.

core/ takes an injected Generator Protocol and cannot import this -- .importlinter fails
the build if it ever does. That is what makes "swap the hosted API for self-hosted Apache
2.0 weights in your VPC" a one-file change rather than a slogan.

TWO SDK FACTS YOU ONLY LEARN BY READING THE SOURCE, NOT THE QUICKSTART:

  1. `retry_config` defaults to None. The SDK does NOT retry unless you pass one. A demo
     that assumes the SDK retries dies on the reviewer's second click. We let the SDK own
     backoff rather than wrapping tenacity around it -- that would double-retry.

  2. `NoResponseError` does NOT subclass `MistralError`. `except MistralError` silently
     misses it and it escapes as an unhandled 500. It gets its own handler here, mapped to
     503.
"""

from __future__ import annotations

from typing import Iterator

from src.api.errors import GenerationUnconfigured, UpstreamRateLimited, UpstreamUnavailable


def _retry_after(exc: object, default: float = 2.0) -> float:
    headers = getattr(exc, "headers", None) or {}
    try:
        return float(headers.get("Retry-After") or headers.get("retry-after") or default)
    except (TypeError, ValueError):
        return default


class MistralGenerator:
    """Streaming generator over the Mistral API.

    temperature=0 is accepted by Mistral and removes sampling as a variable. It does NOT
    buy determinism -- do not claim that it does.
    """

    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise GenerationUnconfigured(
                "MISTRAL_API_KEY is not set. Retrieval, citations and the health endpoint "
                "work without it; answer generation does not."
            )
        from mistralai import Mistral
        from mistralai.utils import BackoffStrategy, RetryConfig

        self.model = model
        self._client = Mistral(
            api_key=api_key,
            # RETRIES OFF, and this is the opposite of what it looks like.
            #
            # Production logs showed a storm -- fourteen consecutive
            #   POST /v1/chat/completions "HTTP/1.1 429 Too Many Requests"
            # -- with asks taking 19-24 seconds. The retry config was the CAUSE, not the cure.
            #
            # The SDK HARDCODES which codes it retries (mistralai/chat.py:220):
            #     retry_config = (retries, ["429", "500", "502", "503", "504"])
            # There is no way to exclude 429 through RetryConfig. And retrying a 429 is
            # feeding the rate limit you are trying to survive: every retry is another
            # request, which earns another 429.
            #
            # It is worse than that, and this is the real bug. The rate gate in front of this
            # (semaphore + token bucket, 1 req/s) admits ONE request -- and then the SDK
            # fires up to five UNGATED retries inside that single admission. The gate counts
            # 1; Mistral sees 6. **The gate built to prevent 429s was being bypassed by the
            # retry logic reacting to them.** Turning retries off is what makes the gate
            # honest: one admission, one request.
            #
            # `strategy="none"` (anything != "backoff") makes the SDK call once and return --
            # verified by reading utils/retries.py, not by hoping.
            #
            # A 429 is not a transport failure. It is the server saying stop, and the correct
            # response to "stop" is to stop. We surface it as a typed 429 carrying the
            # upstream's Retry-After: honest and instant, rather than a silent 20-second
            # stall that ends in the same 429 anyway.
            retry_config=RetryConfig("none", BackoffStrategy(200, 2000, 1.5, 4_000), False),
        )

    def _messages(self, system: str, user: str) -> list[dict[str, str]]:
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def generate(self, system: str, user: str) -> str:
        try:
            response = self._client.chat.complete(
                model=self.model,
                messages=self._messages(system, user),
                temperature=0,
                max_tokens=2000,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise self._translate(exc) from exc

    def stream(self, system: str, user: str) -> Iterator[str]:
        try:
            for event in self._client.chat.stream(
                model=self.model,
                messages=self._messages(system, user),
                temperature=0,
                max_tokens=2000,
            ):
                delta = event.data.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            raise self._translate(exc) from exc

    @staticmethod
    def _translate(exc: Exception) -> Exception:
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)
        if status == 429 or name == "RateLimitError":
            return UpstreamRateLimited("Upstream rate limit reached.", retry_after_s=_retry_after(exc))
        # NoResponseError does not subclass MistralError -- catch it by name, not by class,
        # or it escapes the handler entirely and surfaces as a 500.
        if name in {"NoResponseError", "SDKError", "APIConnectionError"} or (
            isinstance(status, int) and status >= 500
        ):
            return UpstreamUnavailable(f"Upstream unavailable ({name}).")
        return exc

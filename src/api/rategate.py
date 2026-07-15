"""The rate gate: a semaphore plus a TOKEN-aware bucket in front of the provider.

WHY TOKENS AND NOT REQUESTS -- this was measured, twice, the hard way.

v1 metered requests/second. It did not work, and the logs said so:

    HTTP Request: POST https://api.mistral.ai/v1/chat/completions "HTTP/1.1 429 Too Many Requests"   x14
    {"event": "ask", "route": "COMPARE", "citations": 4, "latency_ms": 24182}

At 1.0 req/s -> 429 storm. Lowered to 0.4 req/s, waited 3s between asks -> STILL 429. That
falsifies the whole model: if a request every 2.5 seconds still trips the limit, the limit is
not counting requests. **Mistral's free tier meters TOKENS PER MINUTE.** Each ask here is
~5,000 tokens (the pinned handbook plus eight retrieved sections), so six asks is ~30k tokens
in half a minute -- trivial by request count, enormous by token count.

Metering requests against a token limit is measuring the wrong unit. It is the same shape of
error as the two that preceded it in this project: the retry storm (retrying a 429 feeds the
limit it is trying to survive) and local embeddings (free compute is not free when memory is
what you are short of). Each was a model of the world that stopped matching the world.

WHAT THIS DOES
  * Estimates a request's token cost BEFORE sending it, and spends that many tokens from a
    per-minute bucket. A big request costs more than a small one, which is the entire point.
  * Keeps the concurrency semaphore: tokens govern throughput, the semaphore governs
    simultaneity, and they are different questions.
  * Refills continuously rather than in a fixed window, so a burst after a quiet minute is
    allowed -- which is exactly the reviewer clicking three chips after reading the README.

THE LIMIT IS OBSERVED, NOT PUBLISHED. Mistral's docs tell you to read your own admin console.
So TOKENS_PER_MINUTE is an env var with a conservative default, dated, and honest about being
empirical. If it is wrong, it is wrong in the direction of being slow rather than 429-ing --
and a 429 the user sees is worse than a wait they do not.
"""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """Continuous-refill bucket over an arbitrary unit (here: model tokens per minute).

    The v1 bug is worth remembering: acquire() held its lock across the sleep, so with
    max_concurrent=1 the wait was serialised anyway. Here the lock is only held for the
    arithmetic, never across the await -- waiters wake, recheck, and proceed in turn.
    """

    def __init__(self, capacity: float, refill_per_second: float):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._tokens = capacity  # start full: a cold instance should answer immediately
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    def _replenish(self) -> None:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.refill_per_second)
        self._updated = now

    async def acquire(self, cost: float) -> float:
        """Spend `cost` tokens, waiting if necessary. Returns seconds waited.

        A request larger than the whole bucket would wait forever, so it is clamped to the
        capacity: better to let one oversized request through and eat a 429 than to hang a
        user until their browser gives up.
        """
        cost = min(cost, self.capacity)
        waited = 0.0
        while True:
            async with self._lock:
                self._replenish()
                if self._tokens >= cost:
                    self._tokens -= cost
                    return waited
                shortfall = cost - self._tokens
                delay = shortfall / self.refill_per_second
            # Sleep OUTSIDE the lock so other coroutines can make progress.
            delay = min(delay, 5.0)  # recheck periodically rather than sleeping blind
            await asyncio.sleep(delay)
            waited += delay


def estimate_tokens(text: str) -> int:
    """Deliberately crude, deliberately PESSIMISTIC.

    Yes, this is chars/4 -- the very heuristic this project banned for measuring the corpus,
    and the ban stands there: a REPORTED number must come from the real tokenizer, because a
    wrong number in a README is a checkable falsehood.

    This is a different job. It is a budget estimate for a rate limiter, made before the
    request exists, where being roughly right instantly beats being exactly right slowly --
    running the tekken tokenizer on every prompt would add latency to buy precision nothing
    here needs. Over-estimating costs a little throughput; under-estimating costs a 429.
    So it rounds up, and it never leaves the process.
    """
    return int(len(text) / 3.5) + 200  # /3.5 not /4, plus overhead for the response


class RateGate:
    """Concurrency AND token throughput. They are different questions.

    The semaphore stops two requests being in flight at once (the reviewer opening a second
    tab). The token bucket stops N requests per minute exceeding the provider's token
    allowance. v1 had only the first, dressed up as the second.
    """

    def __init__(self, max_concurrent: int, tokens_per_minute: float):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._bucket = TokenBucket(capacity=tokens_per_minute, refill_per_second=tokens_per_minute / 60.0)
        self.last_wait_s = 0.0

    def reserve(self, prompt_tokens: int) -> "_Reservation":
        return _Reservation(self, prompt_tokens)


class _Reservation:
    def __init__(self, gate: RateGate, cost: int):
        self._gate = gate
        self._cost = cost

    async def __aenter__(self) -> "_Reservation":
        await self._gate._semaphore.acquire()
        try:
            self._gate.last_wait_s = await self._gate._bucket.acquire(self._cost)
        except BaseException:
            self._gate._semaphore.release()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self._gate._semaphore.release()

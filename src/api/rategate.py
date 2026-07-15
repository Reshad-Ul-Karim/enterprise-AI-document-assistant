"""Rate gate: a semaphore plus a token bucket in front of the provider.

This is not theoretical. The reviewer clicks three demo chips in two seconds, against a
free tier that serves roughly one request per second. Without this, the flagship maternity
demo returns a 429 -- or worse, a 500 -- on the one question that decides the submission.

Defence in depth, because the UI fix and the server fix protect different things:
  - The UI disables chips while a request is in flight (the actual fix -- the reviewer
    physically cannot fire concurrently; ~10 lines).
  - The semaphore bounds concurrency if they open two tabs.
  - The token bucket paces sustained throughput.
  - A typed 429 with Retry-After is the honest floor when all of that is exhausted.

The RPS is an env var, observed from the admin console and dated -- never a number quoted
from a blog post. The design honours whatever Retry-After the server actually sends.
"""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    def __init__(self, rate_per_second: float, capacity: float | None = None):
        self.rate = rate_per_second
        self.capacity = capacity if capacity is not None else max(1.0, rate_per_second)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await asyncio.sleep((1.0 - self._tokens) / self.rate)


class RateGate:
    def __init__(self, max_concurrent: int, requests_per_second: float):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._bucket = TokenBucket(requests_per_second)

    async def __aenter__(self) -> "RateGate":
        await self._semaphore.acquire()
        try:
            await self._bucket.acquire()
        except BaseException:
            self._semaphore.release()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self._semaphore.release()

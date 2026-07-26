"""Per-IP daily cap on booking requests -- a different question from rategate.py's.

rategate.py meters TOKENS PER MINUTE in front of the LLM provider, because the scarce
resource there is Mistral's quota. /api/book never calls an LLM at all; the resource it
protects is Reshad's inbox, and the unit that matters is "how many emails can one visitor
trigger," not tokens or concurrency. A token bucket answers the wrong question here, so this
is a separate, much simpler counter rather than a strained reuse of TokenBucket.

In-memory and per-process, same tradeoff KbRegistry already makes for the same reason: a
free-tier single instance with no persistent disk resets on restart or redeploy, and a
booking form's rate limit resetting a little early on a restart is a non-event, not an
incident.
"""

from __future__ import annotations

import time

WINDOW_S = 24 * 60 * 60


class DailyIPGate:
    def __init__(self, max_per_day: int = 3):
        self.max_per_day = max_per_day
        self._hits: dict[str, list[float]] = {}

    def allow(self, ip: str) -> bool:
        """Record an attempt and report whether it's within the daily cap.

        Prunes timestamps older than the window on every call rather than running a
        background sweep -- the dict only ever holds entries for IPs that have actually
        booked recently, so it self-bounds without a separate cleanup task.
        """
        now = time.monotonic()
        hits = [t for t in self._hits.get(ip, []) if now - t < WINDOW_S]
        allowed = len(hits) < self.max_per_day
        if allowed:
            hits.append(now)
        self._hits[ip] = hits
        return allowed

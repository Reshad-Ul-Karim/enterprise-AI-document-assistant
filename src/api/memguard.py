"""A memory budget, checked before doing work that could exceed it.

WHY THIS EXISTS. An upload OOM'd the container on a 512 MB box. Render killed the process,
and the reviewer clicking the PUBLIC demo -- which was working perfectly and shares nothing
with the upload path except a process -- got a 502. **A feature nobody is using took down the
thing being assessed.**

The root cause is fixed (embeddings moved off onnxruntime: 370 MB baseline -> 81 MB, leaving
431 MB of headroom instead of 142). This is the second layer, and it exists because the root
cause was ALSO "fixed" twice before by capping and batching, and both times the arithmetic
still did not close. A guard that refuses is strictly better than a process that dies:

  * refusing  -> one user sees a typed 503 explaining exactly why, and everyone else is fine
  * dying     -> everyone sees a 502, including the reviewer on the public demo

So this is not defence against a known bug. It is defence against the NEXT thing that grows
-- a bigger model, a longer document, a dependency that doubles overnight -- which is the
category of failure that keeps happening here.

Deliberately NOT a percentage of some notional total: cgroup limits are what actually kill
you, and psutil's system-wide numbers are the host's, not the container's. This reads the
container's own RSS, which is the number Render's limit is compared against.
"""

from __future__ import annotations

import os

from src.api.errors import AppError


class InsufficientMemory(AppError):
    status_code = 503
    code = "INSUFFICIENT_MEMORY"  # type: ignore[assignment]


# Render free is 512 MB. Refuse at 380 rather than 500: the check happens BEFORE the work,
# and the work itself is what allocates -- leaving only 12 MB of headroom would guarantee the
# OOM the guard is meant to prevent. Overridable for a bigger instance.
MEMORY_LIMIT_MB = int(os.environ.get("MEMORY_LIMIT_MB", "512"))
INGEST_REFUSE_ABOVE_MB = int(os.environ.get("INGEST_REFUSE_ABOVE_MB", "380"))


def current_rss_mb() -> float:
    """This process's resident set, in MB.

    /proc/self/statm on Linux (what the container's limit is actually measured against);
    psutil elsewhere so it still works on a developer's Mac.
    """
    try:
        with open("/proc/self/statm") as handle:
            pages = int(handle.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 1e6
    except (OSError, ValueError, IndexError):
        try:
            import psutil

            return psutil.Process().memory_info().rss / 1e6
        except Exception:
            return 0.0  # unknown -> do not block on a number we cannot read


def headroom_mb() -> float:
    used = current_rss_mb()
    return MEMORY_LIMIT_MB - used if used else float("inf")


def assert_room_to_ingest(estimated_mb: float = 0.0) -> None:
    """Refuse the upload rather than let it kill the container.

    The failure mode this replaces: the container dies, Render restarts it, and every user --
    including the reviewer on the public demo -- gets a 502 for the ~60 s cold start.
    """
    used = current_rss_mb()
    if not used:
        return  # cannot measure -> proceed; a guard that guesses is worse than none
    if used + estimated_mb > INGEST_REFUSE_ABOVE_MB:
        raise InsufficientMemory(
            f"This instance is using {used:.0f} MB of its {MEMORY_LIMIT_MB} MB limit and this "
            f"upload needs roughly {estimated_mb:.0f} MB more. Refusing it so the running "
            "service stays up rather than being killed mid-request. Delete a notebook, or "
            "wait for the current upload to finish, and retry."
        )


def estimate_ingest_mb(pdf_bytes: int, pages: int) -> float:
    """A rough, deliberately PESSIMISTIC estimate of an ingest's peak.

    Measured on a 4-page scanned extract and a 30-page text PDF: the PDF bytes are held once,
    pypdf's parse runs to roughly the file size again, extracted text is small, and the
    splitter's working set tracked page count more than bytes. Erring high is the point --
    under-estimating means the OOM the guard exists to prevent.
    """
    return (pdf_bytes / 1e6) * 3.0 + pages * 1.5 + 40.0

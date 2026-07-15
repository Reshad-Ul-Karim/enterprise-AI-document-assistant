"""The provider boundary, as a Protocol.

core/ must not import `mistralai` -- enforced by .importlinter, not by good intentions.
That buys three concrete things:

  1. The whole test suite runs with NO API key and NO network, via FakeGenerator.
  2. Swapping the hosted Mistral API for self-hosted open weights is a one-file change.
     mistral-large-2512 is Apache 2.0, so the enterprise answer to "where does our data
     go?" is "run the weights in your VPC" rather than "trust my vendor".
  3. Exposing this over MCP would be an adapter, not a refactor.
"""

from __future__ import annotations

from typing import Iterator, Protocol


class Generator(Protocol):
    def generate(self, system: str, user: str) -> str: ...
    def stream(self, system: str, user: str) -> Iterator[str]: ...


class FakeGenerator:
    """Deterministic generator for tests. No network, no key, no flake.

    The suite must be runnable by a reviewer who has not signed up for anything.
    """

    def __init__(self, reply: str = "Not found in the provided documents."):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply

    def stream(self, system: str, user: str) -> Iterator[str]:
        self.calls.append((system, user))
        yield self.reply

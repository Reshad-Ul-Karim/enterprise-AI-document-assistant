"""Architectural claims, enforced by the build rather than asserted in a README.

"I didn't write that claim in the README and ask you to believe it. I made the build fail
if it stops being true."
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_core_is_protocol_free_and_provider_free():
    """core/ may not import fastapi, mistralai, pinecone, mcp, or a splitter.

    This is what lets the suite run with no API key and no network, makes swapping to
    self-hosted Apache-2.0 weights a one-file change, and would make an MCP server a ~21-line
    adapter instead of a refactor.
    """
    result = subprocess.run(
        ["lint-imports", "--config", str(REPO / ".importlinter")],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"import contract broken:\n{result.stdout}\n{result.stderr}"


def test_runtime_requirements_do_not_pull_torch():
    """~254 MB vs ~2.5 GB.

    The reason is COLD START, not memory: a free Space sleeps, so the reviewer's first click
    IS a cold start and image pull dominates it. (HF Spaces free has 16 GB -- claiming torch
    "can't boot" there would be a credibility grenade.)

    We assert on the manifest rather than the interpreter: a dev machine legitimately has
    torch installed for other work, and that must not fail this test for the wrong reason.
    CI additionally installs requirements.txt into a clean venv and checks the real closure.
    """
    # Parse requirement LINES, not prose: the file's comments discuss torch at length, and
    # a naive substring match would flag the explanation for why it is absent.
    requirements = [
        line.split("#")[0].strip().lower()
        for line in (REPO / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    names = {re.split(r"[=<>\[]", line)[0].strip() for line in requirements if line}

    for banned in ("torch", "sentence-transformers", "transformers", "langchain", "langgraph"):
        assert banned not in names, f"{banned!r} must not be a runtime dependency"


def test_langchain_metapackage_is_not_installed():
    """Not installing it makes the rejection STRUCTURAL rather than aspirational.

    The meta-package is where RecursiveCharacterTextSplitter lives -- measured to merge
    ss.115/116/117 (three distinct legal entitlements sharing a printed page) into one chunk
    with one wrong page number. It is not importable here, so it cannot be reached for.
    """
    import importlib.util

    assert importlib.util.find_spec("langchain") is None

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

    # `transformers` and `pyarrow` are not merely bloat here -- they are a CRASH.
    # langchain_text_splitters' __init__ reaches for transformers when it is importable,
    # which on a machine that also has tensorflow/pyarrow aborts at the C++ level:
    #   libc++abi: terminating due to uncaught exception ... mutex lock failed
    # A C++ abort is NOT catchable by try/except, so it kills the whole uvicorn process --
    # observed locally: one upload took the server down, and with it the public demo.
    # The image is safe only because neither package is in the closure. That is a
    # guarantee worth asserting rather than a coincidence worth relying on.
    for crash_risk in ("transformers", "pyarrow", "tensorflow", "streamlit"):
        assert crash_risk not in names, (
            f"{crash_risk!r} in the runtime closure would make langchain_text_splitters' "
            "import abort at the C++ level and kill the process on the first upload."
        )


def test_langchain_metapackage_is_not_installed():
    """Not installing it makes the rejection STRUCTURAL rather than aspirational.

    The meta-package is where RecursiveCharacterTextSplitter lives -- measured to merge
    ss.115/116/117 (three distinct legal entitlements sharing a printed page) into one chunk
    with one wrong page number. It is not importable here, so it cannot be reached for.
    """
    import importlib.util

    assert importlib.util.find_spec("langchain") is None


def test_upload_stack_is_lazy_so_the_public_demo_never_pays_for_it():
    """The demo path must not import langchain/langsmith/pinecone/pypdf.

    Those exist for the authenticated upload surface. The box has 512 MB and the baseline
    already uses ~435 MB, so importing the upload stack at boot would spend the public
    demo's headroom on a feature most visitors never touch. Booting the app must stay lean.
    """
    import subprocess
    import sys

    code = (
        "import sys; import src.api.main; "
        "heavy=[m for m in ('langchain_core','langsmith','pinecone','pypdf') if m in sys.modules]; "
        "print(','.join(heavy))"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    loaded = result.stdout.strip()
    assert loaded == "", f"upload stack imported at boot: {loaded}"


def test_langsmith_telemetry_is_disabled_where_the_splitter_is_used():
    """langchain-core pulls in langsmith, a telemetry client. In a product about document
    confidentiality, 'it's off by default' is not good enough -- an env var set elsewhere on
    the host would silently opt us into shipping user documents to a third party."""
    source = (REPO / "src" / "api" / "uploads.py").read_text()
    assert 'LANGSMITH_TRACING' in source
    assert 'LANGCHAIN_TRACING_V2' in source


def test_every_app_error_code_is_declared_in_the_literal():
    """Every AppError subclass's `code` must exist in ErrorCode.

    This test exists because it failed in production first. `AuthRequired` shipped with
    code 'AUTH_REQUIRED', which was not in the Literal, so building the envelope raised a
    ValidationError *inside the exception handler* and FastAPI returned 500 -- from the very
    machinery whose whole job is 'never a 500 with a stack trace'. A 401 became a 500.

    Enumerating subclasses is what makes this un-forgettable: adding an error class with an
    undeclared code now fails the suite instead of the deployment.
    """
    from typing import get_args

    from src.api import auth, errors, uploads  # noqa: F401  (import to register subclasses)

    declared = set(get_args(errors.ErrorCode))

    def subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from subclasses(sub)

    for cls in subclasses(errors.AppError):
        assert cls.code in declared, (
            f"{cls.__name__}.code = {cls.code!r} is not in ErrorCode. "
            "The handler would fail validation and return 500 instead of "
            f"{cls.status_code}."
        )


def test_onnxruntime_is_not_a_runtime_dependency():
    """THE regression guard for a real production outage.

    fastembed/onnxruntime was ~280 MB resident. On Render's 512 MB that left 142 MB for an
    upload path needing ~190, so uploads OOM-killed the container and the reviewer got a 502
    -- on the PUBLIC demo, which had nothing to do with uploads and was working fine.

    Measured: 370 MB baseline with it, 81 MB without. No batching or capping fixes a baseline
    that is 72% of the ceiling; that is arithmetic, not tuning.

    The local-embeddings decision was CORRECT when the target was Hugging Face's 16 GB. HF
    made Docker Spaces PRO-only, we moved to a box with 32x less RAM, and the premise died
    without the decision being revisited. This test is what notices if it comes back.
    """
    names = {
        re.split(r"[=<>\[]", line.split("#")[0].strip().lower())[0].strip()
        for line in (REPO / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for banned in ("fastembed", "onnxruntime", "sentence-transformers"):
        assert banned not in names, (
            f"{banned!r} is back in the runtime. It costs ~280 MB resident and reintroduces "
            "the upload OOM that took the public demo down with a 502."
        )


def test_the_memory_guard_refuses_instead_of_dying():
    """A guard that refuses beats a process that dies.

    Refusing -> one user gets a typed 503 that explains itself; everyone else is unaffected.
    Dying   -> Render kills the container and EVERY user, including the reviewer on the public
               demo, gets a 502 through the ~60 s cold start.
    """
    import pytest

    from src.api.memguard import InsufficientMemory, assert_room_to_ingest, estimate_ingest_mb

    assert_room_to_ingest(0)  # a healthy process must not be blocked

    with pytest.raises(InsufficientMemory) as excinfo:
        assert_room_to_ingest(10_000)  # a request that obviously cannot fit
    assert excinfo.value.status_code == 503

    # Pessimistic on purpose: under-estimating causes the OOM the guard exists to prevent.
    assert estimate_ingest_mb(20_000_000, 60) > 100


def test_index_and_runtime_agree_on_the_embedding_model():
    """Query and passage vectors MUST come from the same model or results are silently
    incomparable -- wrong in the way that never throws. The index was rebuilt from 384-dim
    bge-small to 1024-dim llama-text-embed-v2; a stale index must fail loudly at boot."""
    import json

    from src.core.embeddings import EMBED_DIM, EMBED_MODEL_ID

    meta = json.loads((REPO / "index" / "index_meta.json").read_text())
    assert meta["embed_model_id"] == EMBED_MODEL_ID
    assert meta["embed_dim"] == EMBED_DIM


def test_the_dockerfile_only_uses_packages_that_are_installed():
    """The Dockerfile is code that the test suite never executes, so a stale line in it fails
    in the BUILD -- minutes later, in a log, after a push.

    This exact thing happened: fastembed was removed from requirements.txt and the Dockerfile
    kept `RUN python -c "from fastembed import TextEmbedding..."` to pre-bake the model. The
    image tried to import a package that was no longer installed and the build exited 1.
    Deleting a dependency means grepping for it, not just editing the manifest.
    """
    dockerfile = (REPO / "Dockerfile").read_text()
    installed = {
        re.split(r"[=<>\[]", line.split("#")[0].strip().lower())[0].strip()
        for line in (REPO / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    # RUN python -c "..." lines are the risk: they import things at build time.
    for line in dockerfile.splitlines():
        stripped = line.strip()
        if not stripped.startswith("RUN python -c"):
            continue
        for module in re.findall(r"from (\w+) import|import (\w+)", stripped):
            name = (module[0] or module[1]).lower()
            if name in ("os", "sys", "urllib", "json", "importlib"):
                continue  # stdlib
            assert name in installed, (
                f"Dockerfile runs `import {name}` at build time but {name!r} is not in "
                "requirements.txt. The build will exit 1."
            )

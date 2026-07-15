"""Build the committed index. Build-time only.

Emits index/index.npz + index/chunks.jsonl + index/index_meta.json (~2 MB total, plain
git, no LFS, no boot-time fetch).

index_meta.json is verified at boot and answers "how do you reindex when a document
changes?" in sixty seconds -- a question that will be asked.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from src.core.chunking import chunk_handbook, chunk_statute
from src.core.embeddings import EMBED_DIM, EMBED_MODEL_ID, INPUT_TYPE_QUERY
from src.core.sections import assert_build_gate, detect_sections
from src.core.manifest import MANIFEST
from src.ingest.extract import (
    ACT_PDF,
    HANDBOOK_PDF,
    extract_handbook,
    load_act_ocr,
    statute_layer_text,
)

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "index"
CHUNKER_VERSION = "1.0.0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    # The ingest CLI is an entrypoint in its own right and cannot import api.settings (that
    # is the layering contract). It loads .env itself so PINECONE_API_KEY reaches
    # core.embeddings via the process environment.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass  # CI and production set real env vars

    pages = load_act_ocr()
    statute_text, page_offsets = statute_layer_text(pages)

    sections = detect_sections(statute_text)
    assert_build_gate(sections)  # fail the build, not the demo
    print(f"sections detected: {len(sections)}")

    statute_chunks = chunk_statute(
        sections,
        page_offsets,
        doc_id=MANIFEST["statute"]["doc_id"],
        doc_title=MANIFEST["statute"]["doc_title"],
    )
    handbook_chunks = chunk_handbook(
        extract_handbook(),
        doc_id=MANIFEST["handbook"]["doc_id"],
        doc_title=MANIFEST["handbook"]["doc_title"],
    )

    # The handbook is PINNED in full at query time, not retrieved -- but it is indexed
    # anyway (11 rows, 30 seconds) so recall@k is measurable across BOTH documents.
    # Without this, Retrieval Accuracy would be measured over 97% of the corpus while the
    # document the business scenario is about stays invisible to the metric.
    chunks = statute_chunks + handbook_chunks
    print(f"chunks: {len(chunks)} ({len(statute_chunks)} statute + {len(handbook_chunks)} handbook)")

    from src.providers.pinecone_embed import PineconeEmbedder

    vectors = PineconeEmbedder().embed_passages([c.text for c in chunks])
    if vectors.shape != (len(chunks), EMBED_DIM):
        raise SystemExit(f"embedding shape {vectors.shape} != ({len(chunks)}, {EMBED_DIM})")

    INDEX.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(INDEX / "index.npz", vectors=vectors)
    with (INDEX / "chunks.jsonl").open("w") as handle:
        for chunk in chunks:
            handle.write(chunk.model_dump_json() + "\n")

    meta = {
        "index_version": CHUNKER_VERSION,
        "embed_model_id": EMBED_MODEL_ID,
        "embed_dim": EMBED_DIM,
        "query_input_type": INPUT_TYPE_QUERY,  # llama-text-embed-v2 is asymmetric
        "chunker_version": CHUNKER_VERSION,
        "chunk_count": len(chunks),
        "section_count": len(sections),
        "source_sha256": {
            "statute": _sha256(ACT_PDF) if ACT_PDF.exists() else None,
            "handbook": _sha256(HANDBOOK_PDF) if HANDBOOK_PDF.exists() else None,
        },
        "index_bytes": int(vectors.nbytes),
    }
    (INDEX / "index_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"index: {vectors.nbytes / 1e6:.3f} MB -> {INDEX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

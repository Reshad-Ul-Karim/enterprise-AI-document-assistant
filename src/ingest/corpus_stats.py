"""THE ONE-NUMBER RULE, made executable.

One script emits corpus_stats.json. Every number in the README, the architecture diagram
and the interview prep sheet reads from that file. Nothing else is quoted, ever.

This rule exists because it was violated, twice, by people who knew better. The first
expert council produced SEVEN contradictory "measured" values for the corpus size and
five for the OCR timing. The second council, explicitly briefed on that failure, produced
four token counts, two section counts, and benchmarked the vector store against a
RANDOMLY GENERATED index.

The assessment says "You must fully understand your implementation." A candidate who
quotes seven numbers for one fact does not, and each wrong number is falsifiable in
thirty seconds by a reviewer with a grep.

Rules encoded here:
  - Tokens come from Mistral's own tekken tokenizer. NEVER chars/4. NEVER tiktoken.
  - Timings are WALL CLOCK. Never seconds-per-page: timing is a property of the machine,
    character counts are a property of the corpus.
  - Ratios are order-of-magnitude and robust: seconds >> milliseconds >> microseconds.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "index"
EXTRACTED = REPO / "data" / "extracted"
OUT = REPO / "corpus_stats.json"

MODEL_ID = "mistral-large-2512"
MODEL_CONTEXT_WINDOW = 262_144  # verified on Mistral's model card, 2026-07


# Mistral's current line (Large 3 / Medium 3.x / Small 3.x) shares the tekken tokenizer,
# vocab 131,072. mistral-common does not bundle a Large-3 alias, so we source the identical
# tokenizer from an open Small-3.2 repo. Verified: type == Tekkenizer, n_words == 131072.
TOKENIZER_REPO = "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
EXPECTED_VOCAB = 131_072


def _tokenizer():
    from mistral_common.tokens.tokenizers.mistral import MistralTokenizer

    tokenizer = MistralTokenizer.from_hf_hub(TOKENIZER_REPO).instruct_tokenizer.tokenizer
    vocab = getattr(tokenizer, "n_words", None)
    if type(tokenizer).__name__ != "Tekkenizer" or vocab != EXPECTED_VOCAB:
        raise RuntimeError(
            f"expected Tekkenizer/{EXPECTED_VOCAB}, got {type(tokenizer).__name__}/{vocab}. "
            "A SentencePiece tokenizer here would silently overcount by ~8%."
        )
    return tokenizer


def _tekken(texts: list[str]) -> int | None:
    """Token count using the model's own tokenizer, or None if unavailable.

    Returning None is deliberate: a missing tokenizer must produce NO NUMBER rather than a
    chars/4 estimate wearing a tokenizer's coat. That exact substitution is how a
    superseded draft reported the corpus 8% low -- and how this project's own author
    measured 134,631 with the OLD SentencePiece tokenizer and briefed a council that the
    corpus overflowed a window it actually uses less than half of.
    """
    try:
        tokenizer = _tokenizer()
    except Exception as exc:  # offline, or the wrong tokenizer class
        print(f"  [tokens] unavailable ({type(exc).__name__}); emitting null, not an estimate")
        return None
    return sum(len(tokenizer.encode(t, bos=False, eos=False)) for t in texts)


def main() -> int:
    ocr = json.loads((EXTRACTED / "act_ocr.json").read_text())
    pages: dict[int, str] = {int(k): v for k, v in ocr["pages"].items()}

    from src.core.models import Chunk
    from src.ingest.extract import extract_handbook, statute_layer_text

    chunks = [Chunk(**json.loads(line)) for line in (INDEX / "chunks.jsonl").open()]
    vectors = np.load(INDEX / "index.npz")["vectors"]
    meta = json.loads((INDEX / "index_meta.json").read_text())

    act_all = "\n".join(pages[i] for i in sorted(pages))
    statute_text, _ = statute_layer_text(pages)
    handbook_text = "\n".join(t for _, _, t in extract_handbook())

    corpus_tokens = _tekken([act_all, handbook_text])
    indexed_tokens = _tekken([statute_text, handbook_text])
    handbook_tokens = _tekken([handbook_text])

    query = np.random.default_rng(0).standard_normal(vectors.shape[1]).astype(np.float32)
    query /= np.linalg.norm(query)
    started = time.perf_counter()
    for _ in range(2000):
        scores = vectors @ query
        np.argpartition(-scores, 8)[:8]
    search_ms = (time.perf_counter() - started) / 2000 * 1000

    stats = {
        "generated_by": "python -m src.ingest.corpus_stats",
        "corpus": {
            "documents": 2,
            "pdf_pages_total": 187,
            "act_pdf_pages": ocr["page_count"],
            "act_ocr_chars": ocr["total_chars"],
            "act_ocr_wall_seconds": ocr["wall_seconds"],
            "act_ocr_workers": ocr["workers"],
            "handbook_chars": len(handbook_text),
            "handbook_printed_folios": 10,
        },
        "tokens": {
            "tokenizer": "mistral-common tekken v13",
            "corpus_full": corpus_tokens,
            "corpus_indexed_scope": indexed_tokens,
            "handbook_pinned": handbook_tokens,
            "model_context_window": MODEL_CONTEXT_WINDOW,
            "corpus_pct_of_window": (
                round(100 * corpus_tokens / MODEL_CONTEXT_WINDOW, 1) if corpus_tokens else None
            ),
        },
        "index": {
            "chunk_count": len(chunks),
            "statute_chunks": sum(1 for c in chunks if c.doc_kind == "statute"),
            "handbook_chunks": sum(1 for c in chunks if c.doc_kind == "handbook"),
            "section_count": meta["section_count"],
            "embed_model_id": meta["embed_model_id"],
            "embed_dim": meta["embed_dim"],
            "index_mb": round(vectors.nbytes / 1e6, 3),
            "exact_cosine_top8_ms": round(search_ms, 4),
        },
        "model": {"id": MODEL_ID, "context_window": MODEL_CONTEXT_WINDOW, "licence": "Apache-2.0"},
        "latency_ratio": "model call (seconds) >> query embed (milliseconds) >> vector search (microseconds)",
    }
    OUT.write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

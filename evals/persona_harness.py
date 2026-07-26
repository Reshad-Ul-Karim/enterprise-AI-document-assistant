"""Eval harness for the persona corpus (reshadulkarim.me). Mirrors evals/harness.py's shape
-- same three ideas (grep audit, recall, abstention 2x2), adapted because the persona corpus
genuinely differs from the HR one in ways that make reusing harness.py directly wrong, not
just inconvenient:

  * Two indexes, not one: `Corpus(REPO / "index_persona")`, not "index".
  * A different prompt: load_prompt("persona"), not "synthesis".
  * No section_no on portfolio chunks (they're markdown-chunked, see chunking.py) -- recall
    is checked against gold_doc_id (which project/publication) instead of gold_section.
  * A persona-specific grep audit: Tier D here asserts "Rust"/"Kubernetes"/"IELTS" are absent
    from the RESUME specifically, not the labour-act topics the original audit checks.
  * Tier F (page-aware) needs a PageContext threaded through answer(), which the HR corpus
    has no equivalent of at all.

Run:  python -m evals.persona_harness
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "evals" / "persona_golden.yaml"
OUT = REPO / "evals" / "persona_results.json"


def load_golden() -> list[dict]:
    return yaml.safe_load(GOLDEN.read_text())["questions"]


# --------------------------------------------------------------------- grep audit

def grep_audit(resume_chunks) -> dict[str, int]:
    """Every Tier-D absence claim, proved against our OWN pinned resume text -- same
    discipline as harness.py's grep_audit, same reason: an unanswerable question you did not
    grep is a guess, and the first council's Tier D shipped four topics that were WRONG."""
    corpus = " ".join(c.text.lower() for c in resume_chunks)
    return {
        term: corpus.count(term)
        for term in ("rust", "kubernetes", "ielts", "toefl", "golang")
    }


# --------------------------------------------------------------------- retrieval

def eval_retrieval(corpus, questions: list[dict]) -> dict:
    """recall@5 over Tier-B questions with a gold_doc_id, checked against the PORTFOLIO
    retriever specifically (the persona analogue of harness.py's full_retriever check) --
    portfolio chunks have no section_no to anchor on, so doc_id is the anchor instead."""
    scored = [q for q in questions if q.get("gold_doc_id")]
    hits = 0
    misses = []
    for q in scored:
        got = corpus.portfolio_retriever.search(q["q"], k=5)
        doc_ids = {c.doc_id for c, _ in got}
        if q["gold_doc_id"] in doc_ids:
            hits += 1
        else:
            misses.append({"q": q["q"], "gold": q["gold_doc_id"], "got": sorted(doc_ids)})
    return {"n": len(scored), "recall_at_5": round(hits / max(len(scored), 1), 3), "misses": misses}


# --------------------------------------------------------------------- judge (optional)

JUDGE_PROMPT = """You are grading an AI assistant's answer about a person's resume/portfolio.

Answer STRICTLY as JSON: {{"entailed": bool, "reasoning": "one sentence"}}

`entailed`: is the answer's factual content actually supported by the source passages below?

ANSWER:
{answer}

SOURCE PASSAGES CITED:
{source}
"""


def judge(answer: str, source: str) -> dict | None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    import httpx

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={key}"
    )
    body = {
        "contents": [{"parts": [{"text": JUDGE_PROMPT.format(answer=answer, source=source[:12000])}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    try:
        r = httpx.post(url, json=body, timeout=60)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as exc:
        return {"entailed": None, "error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from src.api.service import Corpus, answer
    from src.api.settings import settings
    from src.core.models import PageContext

    corpus = Corpus(REPO / "index_persona")
    questions = load_golden()
    if args.limit:
        questions = questions[: args.limit]

    print(f"=== persona golden set: {len(questions)} questions ===")

    print("\n=== grep audit (every Tier-D absence, proved against the pinned resume) ===")
    for term, n in grep_audit(corpus.resume).items():
        verdict = "ABSENT ✓" if n == 0 else f"PRESENT x{n} -- Tier D claim is WRONG"
        print(f"  {term:12s} {verdict}")

    print("\n=== retrieval (Tier B, portfolio_retriever) ===")
    r = eval_retrieval(corpus, questions)
    print(f"  recall@5 = {r['recall_at_5']} over n={r['n']}")
    for m in r["misses"]:
        print(f"    MISS: {m['q'][:55]:57s} gold={m['gold']!r} got={m['got'][:5]}")

    out = {"retrieval": r, "grep_audit": grep_audit(corpus.resume)}

    if not settings.generation_available:
        print("\n  MISTRAL_API_KEY absent -> generation/abstention skipped.")
        OUT.write_text(json.dumps(out, indent=2))
        return 0

    from src.api.providers.mistral import MistralGenerator
    from src.api.rategate import RateGate, estimate_tokens

    generator = MistralGenerator(settings.mistral_api_key, settings.mistral_model)
    gate = RateGate(settings.max_concurrent_requests, settings.tokens_per_minute)

    print("\n=== generation + abstention 2x2 (through the app's own rate gate) ===")

    async def run_all() -> list[dict]:
        out: list[dict] = []
        for q in questions:
            page = PageContext(**q["page"]) if q.get("page") else None
            cost = estimate_tokens(q["q"]) + corpus.prompt_floor_tokens
            try:
                async with gate.reserve(cost):
                    resp = await asyncio.to_thread(answer, q["q"], corpus, generator, page=page)
            except Exception as exc:
                print(f"  [{q['tier']}] {q['q'][:46]:48s} ERROR {type(exc).__name__}: {str(exc)[:40]}")
                out.append({"q": q["q"], "tier": q["tier"], "error": type(exc).__name__})
                continue
            should = q["expected_behavior"] == "refuse"
            did = resp.insufficient_information
            mark = "ok " if should == did else "MISS"
            print(f"  {mark} [{q['tier']}] {q['q'][:44]:46s} {'REFUSE' if did else 'answer':6s} "
                  f"cites={len(resp.citations)} route={resp.route}")
            out.append({
                "q": q["q"], "tier": q["tier"], "expected": q["expected_behavior"],
                "refused": did, "citations": len(resp.citations), "route": resp.route,
                "answer": resp.answer[:400],
            })
        return out

    rows = asyncio.run(run_all())

    tp = fp = tn = fn = 0
    for row in rows:
        if "error" in row:
            continue
        should, did = row["expected"] == "refuse", row["refused"]
        if should and did:
            tp += 1
        elif should and not did:
            fn += 1  # answered something it cannot know -- the dangerous direction
        elif not should and did:
            fp += 1  # FALSE REFUSAL -- a correct answer thrown away
        else:
            tn += 1

    scored = tp + fp + tn + fn
    errors = sum(1 for row in rows if "error" in row)
    refuse_precision = tp / max(tp + fp, 1)
    false_refusal_rate = fp / max(fp + tn, 1)
    print(f"\n  abstention 2x2: TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"    refusal precision  = {refuse_precision:.2f}")
    print(f"    FALSE-REFUSAL rate = {false_refusal_rate:.2f}")
    print(f"  scored {scored}/{len(questions)} questions ({errors} errored).")

    # Ship gate: a Tier-D question ANSWERED when gold says refuse is exactly FN above --
    # not a separate "tier=='D' and not refused" check, which double-counted the
    # "does he know Rust?" case even after golden.yaml correctly relabeled it expected=answer
    # (a grounded, cited "no" is correct persona behavior, not a fabrication -- see that
    # entry's comment). FN already means "should refuse, didn't" for whichever rows are
    # actually gold-labeled refuse, tier D or not.
    tier_d_fn = sum(
        1 for row in rows
        if row.get("tier") == "D" and row.get("expected") == "refuse" and not row.get("refused", True)
    )
    print(f"\n  Tier D questions answered when gold says refuse (must be 0): {tier_d_fn}")

    out["abstention"] = {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn, "errors": errors, "scored": scored,
        "of": len(questions), "refusal_precision": round(refuse_precision, 3),
        "false_refusal_rate": round(false_refusal_rate, 3),
        "tier_d_wrongly_answered": tier_d_fn,
    }
    out["rows"] = rows

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

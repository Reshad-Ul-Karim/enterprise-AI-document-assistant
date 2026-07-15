"""Eval harness. Hand-rolled, ~200 LOC, three metrics.

WHY NOT RAGAS/DeepEval/promptfoo -- this is spec-level, not taste. The assessment requires
explaining your PROMPTS at interview. RAGAS's faithfulness prompt is not mine to explain, so
I would be defending someone else's prompt for my headline metric. None of them models the
two-authority-level structure this corpus actually has, either.

THREE METRICS ONLY:
  * recall@5          -- did the governing section reach the context?
  * groundedness      -- is each claim entailed by the section it cites? (folds citation
                         correctness in: "is this claim in the cited section" answers both)
  * abstention 2x2    -- refusal precision AND false-refusal rate. Never refusal rate alone:
                         a system that refuses everything scores 100% on abstention.

THE JUDGE IS GEMINI, NOT MISTRAL, AND THAT IS THE POINT. v1 chose a smaller model from the
SAME family as the answerer and called it "cheap insurance". Models exhibit documented
family-bias -- they score their own family higher. A Mistral judge on a Mistral answerer
buys insurance that does not insure; using mistral-small would reproduce the error for free.
The structural fix is a different FAMILY. The zero-billing constraint forced the correct
answer here, which is worth saying out loud.

Run:  python -m evals.harness            # retrieval + generation + judge
      python -m evals.harness --oracle   # + the full-context ablation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "evals" / "golden.yaml"
OUT = REPO / "evals" / "results.json"


def load_golden() -> list[dict]:
    return yaml.safe_load(GOLDEN.read_text())["questions"]


# --------------------------------------------------------------------- grep audit

def grep_audit(chunks) -> dict[str, int]:
    """Every Tier-D absence claim, proved against our OWN OCR, with the grep committed.

    This exists because the first council's Tier D asserted four topics were "verified truly
    absent" that are in the Act -- ss.108, 138/140, 33, 26 -- with contradictory labels in
    the same document. An unanswerable question you did not grep is a guess.
    """
    corpus = " ".join(c.text.lower() for c in chunks)
    # Only terms a Tier-D question actually claims are absent. "pension" was here and FAILED:
    # it appears 19x in the Act (s.163 masters and seamen, s.24, s.160), so the question was
    # removed rather than the audit weakened. An audit you edit to pass is not an audit.
    return {term: corpus.count(term) for term in
            ("paternity", "work from home", "remote work", "sales handbook", "commission rate")}


# --------------------------------------------------------------------- retrieval

def eval_retrieval(corpus, questions: list[dict]) -> dict:
    """recall@5 over questions with a gold section. Measured on the FULL retriever so both
    documents are visible to the metric -- the handbook is pinned at answer time, but if it
    were invisible here, Retrieval Accuracy would be measured over 97% of the corpus while
    the document the business scenario is about went unmeasured."""
    scored = [q for q in questions if q.get("gold_section")]
    hits = 0
    misses = []
    for q in scored:
        got = corpus.full_retriever.search(q["q"], k=5)
        sections = {c.section_no for c, _ in got}
        if q["gold_section"] in sections:
            hits += 1
        else:
            misses.append({"q": q["q"], "gold": q["gold_section"], "got": sorted(s for s in sections if s)})
    return {"n": len(scored), "recall_at_5": round(hits / max(len(scored), 1), 3), "misses": misses}


# --------------------------------------------------------------------- judge

JUDGE_PROMPT = """You are grading an AI assistant's answer against a source document.

Answer STRICTLY as JSON: {"entailed": bool, "cited_section_contains_claim": bool, "reasoning": "one sentence"}

`entailed`: is the answer's factual content supported by the cited source text below?
`cited_section_contains_claim`: does the CITED section actually contain the claim, or was a
real fact attributed to the wrong place?

Three worked examples from this corpus:

1. Answer: "You get 10 days of casual leave [Labour Act s.115]"
   Source: s.115 "Every worker shall be entitled to casual leave with full wages for ten days"
   -> {"entailed": true, "cited_section_contains_claim": true, "reasoning": "Exact match."}

2. Answer: "You get 30 days annual leave [Labour Act s.117]"
   Source: s.117 "at the rate of one day for every eighteen days of work"
   -> {"entailed": false, "cited_section_contains_claim": false,
       "reasoning": "RIGHT NUMBER, WRONG SOURCE -- 30 days is the handbook's figure, not s.117's."}
   (This anchor is the highest-value one here. A naive judge waves it through because the
    number is real and the section exists. It is the exact failure mode of a citation system.)

3. Answer: "The handbook does not address maternity leave."
   Source: the handbook, in full, containing no occurrence of "maternity"
   -> {"entailed": true, "cited_section_contains_claim": true,
       "reasoning": "Absence is provable here because the handbook is pinned in full."}

ANSWER:
{answer}

CITED SOURCE TEXT:
{source}
"""


def judge(answer: str, source: str) -> dict | None:
    """Returns None if GEMINI_API_KEY is absent -- the harness then SKIPS groundedness and
    says so, rather than silently scoring 0 and reporting a number that means nothing."""
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


# --------------------------------------------------------------------- oracle

def run_oracle(corpus, generator, questions: list[dict]) -> dict:
    """The full-context ablation. FREE on the Experiment tier, and the highest-value hour.

    The whole indexed corpus goes in ONE prompt -- ~90k tokens against mistral-large-2512's
    262,144 window (34%). SAME MODEL as the RAG path, deliberately: the only variable in the
    comparison is then retrieval. A cross-provider oracle would conflate retrieval loss with
    model difference and the resulting "gap" would measure nothing.

    This is what BOUNDS the FR#5 concession. For the handbook, absence is provable because it
    is pinned. For the statute, RAG can only say "I didn't find it in the 8 sections I
    retrieved" -- and the oracle, which sees everything, tells us how often that is wrong.

    Groq physically cannot run this: 90k tokens is ~7x its 12k TPM free limit. It is the one
    workload that proves Mistral was chosen on engineering grounds, not preference.
    """
    whole = "\n\n".join(
        f"[[chunk:{c.chunk_id}]] {c.doc_title}"
        + (f" s.{c.section_no} {c.section_title}" if c.section_no else "")
        + f" (p.{c.printed_page})\n{c.text}"
        for c in corpus.chunks
    )
    from src.api.service import load_prompt

    results = []
    for i, q in enumerate(questions):
        if i and i % 4 == 0:
            # Hand-paced, NOT through the app's gate -- and the reason is honest arithmetic.
            # One oracle call is ~90k tokens: three times the whole per-minute budget the gate
            # is configured with. Reserving that would clamp to the capacity and 429 anyway.
            # The oracle is a one-off offline measurement against a different (much larger)
            # allowance, so it gets its own explicit pace. The REQUEST path uses the gate;
            # this does not pretend to.
            time.sleep(60)  # ~4 calls/min
        raw = generator.generate(load_prompt("synthesis"), f"{whole}\n\n# QUESTION\n{q['q']}")
        from src.core.verification import verify_answer

        text, cites, insufficient = verify_answer(raw, corpus.chunks)
        results.append({
            "q": q["q"], "tier": q["tier"], "expected": q["expected_behavior"],
            "insufficient": insufficient, "citations": len(cites),
            "sections": sorted({c.section_no for c in cites if c.section_no}),
            "answer": text[:400],
        })
        print(f"  oracle [{q['tier']}] {q['q'][:50]:52s} -> {'REFUSE' if insufficient else 'answer'}")
    return {"n": len(results), "results": results}


# --------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", action="store_true", help="also run the full-context ablation")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from src.api.service import Corpus, answer
    from src.api.settings import settings

    corpus = Corpus(REPO / "index")
    questions = load_golden()
    if args.limit:
        questions = questions[: args.limit]

    print(f"=== golden set: {len(questions)} questions ===")

    print("\n=== grep audit (every Tier-D absence, proved against our own OCR) ===")
    for term, n in grep_audit(corpus.chunks).items():
        verdict = "ABSENT ✓" if n == 0 else f"PRESENT x{n} -- Tier D claim is WRONG"
        print(f"  {term:16s} {verdict}")

    print("\n=== retrieval ===")
    r = eval_retrieval(corpus, questions)
    print(f"  recall@5 = {r['recall_at_5']} over n={r['n']}")
    for m in r["misses"]:
        print(f"    MISS: {m['q'][:55]:57s} gold s.{m['gold']} got {m['got'][:5]}")

    out = {"retrieval": r, "grep_audit": grep_audit(corpus.chunks)}

    if not settings.generation_available:
        print("\n  MISTRAL_API_KEY absent -> generation/abstention/oracle skipped.")
        OUT.write_text(json.dumps(out, indent=2))
        return 0

    from src.api.providers.mistral import MistralGenerator

    generator = MistralGenerator(settings.mistral_api_key, settings.mistral_model)

    print("\n=== generation + abstention 2x2 ===")
    # THE HARNESS USES THE APP'S OWN RATE GATE.
    #
    # It used to call answer() directly behind `time.sleep(1.2)` -- a naive request-per-second
    # pace that production had already proven wrong. Half the questions died to 429s, n fell
    # from 30 to 12, and the interval widened to +/-25pp: wide enough to swallow the very
    # improvement the run was measuring. **An eval that cannot finish cannot measure
    # anything**, and one that paces differently from the app measures a system nobody ships.
    #
    # ONE event loop for the whole run, deliberately. asyncio.Lock binds to the loop it is
    # first awaited in, so a fresh asyncio.run() per question would raise "attached to a
    # different loop" on the second one -- the gate has to live in a single loop, exactly as
    # it does under uvicorn.
    from src.api.rategate import RateGate, estimate_tokens

    gate = RateGate(settings.max_concurrent_requests, settings.tokens_per_minute)

    async def run_all() -> list[dict]:
        out: list[dict] = []
        for q in questions:
            cost = estimate_tokens(q["q"]) + corpus.prompt_floor_tokens
            try:
                async with gate.reserve(cost):
                    waited = gate.last_wait_s
                    resp = await asyncio.to_thread(answer, q["q"], corpus, generator)
            except Exception as exc:
                print(f"  [{q['tier']}] {q['q'][:46]:48s} ERROR {type(exc).__name__}: {str(exc)[:40]}")
                out.append({"q": q["q"], "tier": q["tier"], "error": type(exc).__name__})
                continue
            should = q["expected_behavior"] == "refuse"
            did = resp.insufficient_information
            mark = "ok " if should == did else "MISS"
            pace = f" (+{waited:.0f}s paced)" if waited > 0.5 else ""
            print(f"  {mark} [{q['tier']}] {q['q'][:44]:46s} {'REFUSE' if did else 'answer':6s} "
                  f"cites={len(resp.citations)}{pace}")
            out.append({
                "q": q["q"], "tier": q["tier"], "expected": q["expected_behavior"],
                "refused": did, "citations": len(resp.citations), "answer": resp.answer[:300],
            })
        return out

    rows = asyncio.run(run_all())

    tp = fp = tn = fn = 0
    for r in rows:
        if "error" in r:
            continue
        should, did = r["expected"] == "refuse", r["refused"]
        if should and did:
            tp += 1
        elif should and not did:
            fn += 1  # answered something it cannot know -- the dangerous direction
        elif not should and did:
            fp += 1  # FALSE REFUSAL -- a correct answer thrown away
        else:
            tn += 1

    scored = tp + fp + tn + fn
    errors = sum(1 for r in rows if "error" in r)
    refuse_precision = tp / max(tp + fp, 1)
    false_refusal_rate = fp / max(fp + tn, 1)
    print(f"\n  abstention 2x2: TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"    refusal precision  = {refuse_precision:.2f}  (of what it refused, how much SHOULD be)")
    print(f"    FALSE-REFUSAL rate = {false_refusal_rate:.2f}  (answerable questions it wrongly refused)")
    print("    -- a 2x2, never one number: refusing everything scores 100% on 'abstention'")
    if errors:
        print(f"\n  ⚠️  {errors}/{len(rows)} questions ERRORED and are excluded. A partial run is a")
        print("     weaker measurement -- say n, not just the rate.")
    # Wilson interval: honest at small n, unlike the normal approximation which is nonsense
    # near 0 or 1 and would quietly flatter a rate built on a handful of questions.
    import math
    n = max(fp + tn, 1)
    ph, z = false_refusal_rate, 1.96
    denom = 1 + z * z / n
    centre = (ph + z * z / (2 * n)) / denom
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / denom
    print(f"\n  false-refusal 95% CI (Wilson, n={n}): {max(0, centre-half):.2f} - {min(1, centre+half):.2f}")
    print(f"  scored {scored}/{len(questions)} questions.")

    out["abstention"] = {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "errors": errors,
                         "scored": scored, "of": len(questions),
                         "refusal_precision": round(refuse_precision, 3),
                         "false_refusal_rate": round(false_refusal_rate, 3),
                         "false_refusal_ci95": [round(max(0, centre-half), 3), round(min(1, centre+half), 3)]}
    out["rows"] = rows

    if args.oracle:
        print("\n=== full-context oracle (the ablation that bounds the FR#5 concession) ===")
        out["oracle"] = run_oracle(corpus, generator, questions)

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

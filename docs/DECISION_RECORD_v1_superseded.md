# DECISION RECORD — Enterprise AI Document Assistant (AgamiSoft)

**Chief Architect ruling. Council of nine + three adversaries. This is the build.**
Status: 4 days past stated deadline (July 11 → July 15). **Action zero is an email, not an OCR script.** See §7.

---

## 0. Action Zero — before any code

Not one of nine experts treated the lateness as an action item; three converted it into a licence to spend 20-30h. That is backwards. Send this today:

> *"I'm past your July 11 deadline. Is a submission still accepted, and if so by when? If not, I'd still value the technical conversation."*

Three outcomes, three plans:
- **Rejected** → stop. Portfolio project. Build whatever you like.
- **Accepted, no new deadline** → ship Phase 0 + Phase 1 within 48h. Every extra day compounds the "poor scoping" read that a good README cannot undo.
- **New deadline** → plan to it.

Lateness gets **one honest line in the submission email**, not buried in README limitations. The grader will check the timestamp.

**Lateness buys exactly one thing:** ~4 extra hours for the eval harness and README, because those are the artifacts that justify the delay. It does not buy 30 hours of stack.

---

## 1. Requirements — as written vs as they actually are

| Spec claims | Reality (measured, reproduced by 3 independent adversaries) |
|---|---|
| 6 documents | **2 documents** |
| 20–30 pages | **187 pages** |
| Text-native PDFs | **97% scanned images** — the Labour Act has **zero** extractable text (0 chars/page native) |
| Employee Handbook.pdf, HR Policy.pdf, Leave Policy.pdf, Sales Handbook.pdf, Company Profile.pdf, FAQ.pdf | **`Partex-Star-Group.pdf`** (6 PDF pages, landscape 2-up spread, PDF metadata title = `Employee Handbook-Final`) and **`A Handbook on the Bangladesh Labour Act 2006.pdf`** (181 pages, 100% image, English) |
| — | **5 of the 6 named documents do not exist.** |

### What the mismatch forces

1. **OCR is mandatory and must be a committed build artifact.** 181 pages × ~2s = ~6 min serial, ~100–150s at 6–8 workers, 498,240 chars, deterministic. Free-tier health checks are 30–60s. OCR at cold start = no live URL = a mandatory submission item fails regardless of code quality.
2. **Neither document's PDF page index is its printed page number**, and they break the mapping in two *different* ways. FR#4 names page numbers explicitly. This is a 10-second check for the grader.
3. **The corpus is bimodal in size by 37:1** (13,378 chars vs 498,240). Any global top-k buries the Employee Handbook — the one document the business scenario is actually about.
4. **The two documents are not an unrelated pair.** Handbook folio 1 states verbatim: *"The human resource (HR) policies and procedures contained in this handbook are in compliance with the applicable labor laws of Bangladesh."* The other 181 pages are the exact statute that claim refers to. **The corpus is a falsifiable claim plus its evidence base.** That is the product.
5. **The whole corpus fits in one context window** (~128k tokens). RAG is a *defended choice*, not a necessity. The interviewer will do this math.
6. **Fine-tuning is unimplementable**, not merely unwise. Verified against the Claude API surface: the endpoints are `/v1/messages`, `/v1/messages/batches`, `/v1/files`, `/v1/messages/count_tokens`, `/v1/models`, plus Managed Agents. **There is no fine-tuning endpoint.**

### Corpus ground truth — ONE number, quoted everywhere

The council produced **six mutually contradictory corpus sizes** (70,634 / 103,189 / 127,903 / 134,683 / 136,106 / 142,000) and **seven OCR timings** (1.0 / 1.83 / 2.0 / 2.48 / 3.1 / 4.1 / 5.58 s/page), each presented as "measured". This is disqualifying under §9 ("you MUST fully understand your implementation"). One candidate cannot quote seven numbers for one fact.

**RULING:** one committed script emits `corpus_stats.json`. Every number in the README, the diagram caption, and the interview prep sheet reads from it. Nothing else is quoted.

```
Ground truth (reproduced independently ≥2×):
  Labour Act:  181 pages, 100% image-only, 498,240 OCR chars, ~2,750 chars/page (body)
  Partex:      6 PDF pages (2-up), 13,378 chars, text-native
  Total:       511,618 chars
  Tokens:      run client.messages.count_tokens(model="claude-opus-4-8", ...) ONCE
               on the concatenated corpus. Do NOT use chars/4. Do NOT use tiktoken.
               (~128k expected; quote the measured value.)
  OCR:         ~100-150s wall at 8 workers, deterministic, byte-identical reruns.
               Quote the WALL CLOCK, never s/page — timing is a property of the machine,
               498,240 chars is a property of the corpus.
```

---

## 2. The 12 requirements that actually matter

| # | Requirement | Source | Rubric marks touched |
|---|---|---|---|
| 1 | Every page of the statute must be OCR'd **at build time** and committed; the runtime image contains no tesseract. | derived — 100% scanned + mandatory live URL | Architecture 20, UX 5, Docs 10 (all zero if URL is dead) |
| 2 | Citations must carry the **printed** page number, one declared index convention, asserted in tests. | explicit FR#4 | AI Response Quality 20, Retrieval 15, UX 5 |
| 3 | Partex must be extracted by **geometric clip at the x-midline**, per half-page; naive extraction interleaves two unrelated policies with no error. | derived — 2-up landscape spread, z-ordered blocks | Retrieval 15, Response Quality 20 |
| 4 | The Employee Handbook must be reachable independently of the statute (2.6% vs 97.4% of chars). | derived + implicit (business scenario names HR policy) | Retrieval 15, Business Insight 5 |
| 5 | The statute must be chunked on **section boundaries**, with `section_no` as a first-class retrieval key and citation anchor. | derived — statutes are pre-chunked; 333/354 sections recoverable | Retrieval 15, Response Quality 20 |
| 6 | TOC (0-based idx 1–15) and the tabular ILO annex (idx 157–180) must be **excluded from the answer index** and the exclusion documented. | derived — dot-leader lines lexically shadow real sections; annex OCRs to word salad | Retrieval 15, Architecture 20, Docs 10 |
| 7 | Abstention must be **enforced and measured**, not asserted. | explicit FR#5 | Response Quality 20 |
| 8 | Answers must reason at **two authority levels**: company policy vs statutory floor, with floor semantics (compliant if handbook ≥ statute). | derived — the corpus IS a compliance claim + its evidence | Business Insight 5, Response Quality 20 |
| 9 | RAG must be defended against a full-context baseline that is **built, not hypothesised**. | derived — 128k fits in one 1M window | Architecture 20 |
| 10 | The corpus is **legally stale** (2006 Act as published by BEF 2009; amended 2013, 2018) and the employer is Bangladeshi. Must be surfaced **in the answer**, not the footer. | derived — PDF creationDate 2011, OCR p1 "Bangladesh Employers' Federation, August 2009" | Business Insight 5, Response Quality 20 |
| 11 | **Software Engineering (15) and API Design (10) must be staffed.** 25 of 100 marks had no owner across 9 experts. | explicit §6 | SWE 15, API 10 |
| 12 | Every component must be explainable in **under 3 minutes** and modifiable **live on camera**. | explicit §9, §10 | caps total complexity — the binding constraint on everything above |

**Rubric coverage check:** Architecture 20 (§1,6,9,11) · Response Quality 20 (§2,3,7,8,10) · Retrieval 15 (§3,4,5,6) · SWE 15 (§11) · API 10 (§11) · Docs 10 (§1,6,9,10) · Business Insight 5 (§8,10) · UX 5 (§2). **100/100 owned.**

---

## 3. Architecture ruling — component by component

### 3.1 Ingestion / OCR

**SHIP:** PyMuPDF `get_textpage_ocr(dpi=200, full=True)` + tesseract 5.5.2 `eng`, `--psm 3`, **zero preprocessing**, `ProcessPoolExecutor(max_workers=8)` with page ranges batched per worker (reopen the PDF once per worker — per-page opens were the measured bottleneck). Output → `data/extracted/labour_act.json`, **committed**.

| Rejected | Why it lost |
|---|---|
| Deskew / denoise / binarise / dpi=300 | Measured A/B: raw wins or ties every variant; deskew **loses ~4% of words** (524→505) because OSD reports 0° on already-straight scans; the embedded scans are natively 204 DPI, so dpi=300 is upsampling — equal-or-worse yield at 2× cost. This is the single best "I measured instead of reciting the tutorial" artifact in the submission. |
| docling / marker / surya | Drags torch + model weights into the deploy image to fix 15% of one document. Character accuracy is already 91–96% mean confidence. |
| Full-corpus Claude vision OCR | ~$2.84–7.60, minutes of latency, per-page nondeterminism, and a hallucination surface on statutory text where a wrong section number is a wrong answer. Use vision as a scalpel or not at all. |
| OCR at deploy / cold start | 100–150s vs a 30–60s health-check budget. Binary ship/no-ship. |

**CRITICAL BUG — two lenses hit this independently.** `tp = doc[i].get_textpage_ocr(...)` lets the transient Page get GC'd, so `doc[i].get_text(textpage=tp)` raises `ReferenceError('weakly-referenced object no longer exists')`. With a `try/except` that swallows it, **you silently index 181 blank pages and the pipeline reports success** ("DONE 181 pages in 167.8s, total_chars 0"). Hold the page reference:

```python
pg = doc[i]
tp = pg.get_textpage_ocr(dpi=200, full=True, language="eng")
text = pg.get_text(textpage=tp)
```

**Build gate (fail the build, never the query):** `assert mean_chars_per_body_page > 1500` and `assert no body page < 300 chars`. Only idx 0 / 32 / 156 are legitimately near-empty (cover, Act title page, "Addendum").

**Partex — clip, never block-x0. ADVERSARY WIN, CONCEDED.** Two lenses prescribed `page.get_text("blocks")` filtered on `b[0] < mid`. **This is wrong and it fails on the exact page you'd check.** Measured: on idx 2 the footer returns as a *single block* with `x0 = 68.7` and text `'4\
employee handbook\
3\
employee handbook\
'` — it spans the gutter, so block-x0 assigns the right page's folio "4" into the left half and you conclude left = 4. Span geometry says folio '3' sits at x=291.5 (left of midline), folio '4' at x=370.4. Left = 3.

```python
W = page.rect.width          # drifts: 686.07 / 687.64 / 686.39 across pages
mid = W / 2                  # compute per page — NEVER hardcode 343.8 or 346
left  = page.get_text(sort=True, clip=fitz.Rect(0, 0, mid, H))
right = page.get_text(sort=True, clip=fitz.Rect(mid, 0, W, H))
text = unicodedata.normalize("NFKC", text)              # 24 ligatures: "conﬁdential" ≠ "confidential"
text = re.sub(r"(\\w)-\
\\s*(\\w)", r"\\1\\2", text)         # 23 hyphenations; joins '-\
' only, spares 'pro-rata'
# drop footer band y > H*0.86
```

**Regression test (silent corruption never throws):** assert the chunk containing `"Leave During Probation"` does **not** contain `"Confidentiality"`.

**Exclusions (0-based PyMuPDF index, hardcoded constants with a comment citing the evidence — NOT a heuristic classifier):**
- `TOC_RANGE = range(1, 16)` — 16 pages, 19,094 chars of `'Procedure for leave : 27'` dot-leaders. Lexically near-identical to every real section heading, zero answer content. Maximally adversarial to both BM25 and cosine. **Keep idx 16** (`PREFACE`) — one council range would have deleted it.
- `ANNEX_RANGE = range(157, 181)` — 24-page ILO ratification table annex. Short-line share 0.73–0.78 vs 0.26 corpus median; OCRs to `'This / aw / is / not / in / force / in'`. Excluded, tagged `kind="table_unreliable"`, documented as a **deliberate, measured exclusion** — which scores better on Architecture and Docs than a half-working table parser, and demonstrates FR#5 in the ingestion layer.
- Layers: idx 17–32 = **commentary about the Act** (idx 32 is the title page `THE BANGLADESH LABOUR ACT, 2006 (XLII of 2006)`); idx 33–156 = **the Act verbatim**. Tag `layer ∈ {commentary, statute}`. `get_section` indexes idx 33+ only — otherwise the regex false-positives sections 1–6 onto the repealed-laws schedule.

**Bengali OCR: non-issue, and knowing why is the point.** Zero Bengali codepoints in 498,240 OCR chars; s.354 of the Act is titled *"Original Text and Authentic English Text"* — this document **is** the authentic English text. One README line to pre-empt the obvious question, not a limitation.

### 3.2 Page fidelity — ONE constant, ONE declared base

**ADVERSARY WIN, CONCEDED.** Four lenses gave the offset and split 2–2 between 16 and 17. **They were not disagreeing** — they used undeclared, inconsistent index bases, which is strictly worse than disagreeing because it reads as corroboration. A candidate synthesising this document picks a constant and a base independently and has a coin-flip chance of being off by one on **every statutory citation**. A one-off is worse than a seventeen-off: seventeen looks like a bug, one looks like sloppiness the grader cannot bound.

**Verified from OCR'd footers.** 0-based index 75 → footer `59`. idx 76 → `60`. idx 55 → `39`. idx 40 → `24`. idx 19 → `3`. idx 90 → `74`.

```python
# ONE convention: 0-based PyMuPDF index. Name the variable accordingly.
PRINTED_OFFSET = 16                        # printed = zero_based_pdf_index - 16
BODY_RANGE     = range(17, 157)            # printed 1..140
FRONT_MATTER   = range(0, 17)              # roman: idx 16 == PREFACE == 'xvi'
# Partex: idx 0 = cover (unnumbered); for idx in 1..5:
#   left folio = 2*idx - 1, right folio = 2*idx     → {1,3,5,7,9} / {2,4,6,8,10}
```

Variables are named `zero_based_pdf_index` and `printed_page`. **Never `page`. Never `idx` bare.**

```python
def test_printed_page_from_zero_based_index():
    assert printed(75) == 59 and printed(76) == 60
    assert printed(55) == 39 and printed(40) == 24
    assert printed(19) == 3  and printed(90) == 74
def test_partex_folios():
    assert partex_folios(2) == (3, 4)   # the page block-x0 gets backwards
```

### 3.3 Citation format — RULING on a direct 5-to-1 contradiction

The Eval lead demanded the **physical PDF index** ("verifiable, deterministic"). Five other lenses demanded the **printed page**. The council shipped both opinions and let the implementer pick — and the Eval lead's own golden-set anchors are written in "physical p76" while the answer template five experts want says "printed p.59". **The eval harness would have marked every correct citation wrong.**

**RULING: print BOTH; the canonical anchor is the section number.**

```
Bangladesh Labour Act 2006, s.117 Annual leave with wages — printed p.59 (PDF page 76 of 181)
Employee Handbook (Partex Star Group), printed p.6 (PDF page 5, right half)
```

One f-string ends the argument and is strictly better than either camp: the printed page matches what the document says about itself, the PDF page matches the grader's scrollbar, and the section number is the statute's actual primary key — **stable regardless of pagination, and it OCRs cleanly where footers do not** (`'ll'` for 11, `'564'` for 56, `'Az'` for 47). The eval harness asserts on the **section number**, not the page. The golden set is written in the **same format the renderer emits**.

`doc_title` comes from a curated manifest, never the filename — `Partex-Star-Group.pdf` is misleadingly named and the metadata title is `Employee Handbook-Final`.

### 3.4 Chunking

**SHIP:** dual-grammar section regex + longest-increasing-subsequence over section numbers, scoped to `layer == "statute"` (idx 33–156).

The Act uses **two** header grammars: `N. Title : (1)…` and `N. Title.— (1)…` (e.g. s.24 `Procedure for punishment.—`). A greedy monotonic scan gives 82% recall because one stray high number poisons everything after it. LIS over the detected numbers kept 333 of 335 raw hits — reproduced independently twice, exactly.

**FATAL HIT, CONCEDED — the recommended regex drops s.46, which is the flagship demo.** `[^:;\
]{3,95}` forbids newlines, and s.46's title wraps: `46. Worker's Right to get and employer's responsibility to pay for, payment of maternity\
benefit\
:`. It cannot match. s.46 silently merges into s.45's chunk **with s.45's metadata**. Three lenses stake their single highest-value demo on it. You'd get 333 sections, a clean "94.1%" for the README, and a confidently wrong citation on the one question the grader remembers.

```python
SECTION_RE = re.compile(
    r"^\\s{0,6}(\\d{1,3})\\s*[.,]\\s+"
    r"([A-Z][^:;\
]{3,95}(?:\
[^:;\
]{1,60})?)"      # ← allows ONE wrapped title line
    r"\\s*[|!,.\\s]{0,3}(?:[:;]|[—–-]{1,2}\\s*\\()",
    re.M,
)
# then LIS over section numbers (it already rejects the false positives it admits)
```

**Build gate:** `assert {45, 46, 100, 108, 115, 116, 117, 118} <= set(detected_sections)` — **fail the build, not the demo.** Re-report the recall number *after* the fix. Do not ship "94.1%" while the flagship section is in the missing 5.9%. Cross-validate detected section→page against the TOC's independent page numbers (the exclusion becomes an engineering asset).

Do **not** anchor on roman chapter numerals — OCR mangles them ('XIL', 'Vv', 'V1', 'Vill'); arabic digits survive.

| Rejected | Why it lost |
|---|---|
| `RecursiveCharacterTextSplitter(1000, 200)` / LangChain default | Measured: merges s.115 (casual, 10d), s.116 (sick, 14d), s.117 (annual) — three distinct entitlements, all on one page — into one blob, answers them as one blurred paragraph with one page number, and destroys the citation anchor. Ask its advocate what page it prints for s.117. It says 76. The document says 59. |
| The 169-section regex | Off by half. Single-grammar; misses `N. Title.— (1)` entirely. Presented as "the structure survives OCR essentially intact" and used to derive chunk counts and the imbalance ratio. "I measured 169 sections" in a 354-section statute is falsifiable with grep in 30 seconds. |

**Chunk shape:** sub-split only sections > ~2000 chars (1200-char windows, 1000 stride) carrying parent metadata. Do **not** merge short sections — a short section is a complete legal unit. s.2 (Definitions, 66 defined terms, ~19.5k chars) sub-splits **per definition** — it's the highest-value retrieval target for "what is a worker?". Partex chunks per printed half-page (each is 2–3k chars — one folio *is* one natural chunk).

Metadata on every chunk: `{doc_id, doc_title, doc_kind, layer, section_no, section_title, chapter, zero_based_pdf_index, printed_page, half, char_span, is_definition, source_modality, ocr_mean_conf}`.

### 3.5 Embeddings

**SHIP:** `fastembed==0.8.*` → `TextEmbedding("BAAI/bge-small-en-v1.5")`, quantized ONNX, 384-dim.

| Rejected | Why it lost |
|---|---|
| `sentence-transformers` + torch 2.9.0 (installed on this machine) | ~2.5 GB. `pip freeze > requirements.txt` from this box produces an image that **cannot boot on any free tier** (Render 512 MB, Fly 256 MB). fastembed + onnxruntime ≈ 200 MB. |
| voyage-3 / Cohere embed-v3 | Third vendor, third API key, billing, network hop in the retrieval path. |
| bge-base (768d) | It's a one-line swap at ~400 chunks — **measure it on the golden set and report the delta** rather than guessing either way. |

**The detail that proves you read the model, not the blog post:** bge requires the asymmetric prefix `"Represent this sentence for searching relevant passages: "` on **queries only, never passages**. Omitting it silently costs recall and is invisible in testing. Applied in the retriever, not the store. Recorded in `index_meta`.

**CI gate:** assert `torch` is not in the dependency tree. Hand-write `requirements.txt`; never `pip freeze`.

### 3.6 Vector store

**SHIP:** a numpy `float32` array + `rank_bm25.BM25Okapi`, persisted to a committed `index.npz` + `chunks.jsonl`. **Flat exact cosine. No ANN index. No vector database service.**

Measured: 481 × 384 = **0.7 MB**; exact brute-force cosine = **0.023 ms/query**; at 50,000 vectors (100× this corpus) it is ~7 ms. A Claude call is 1,000–3,000 ms. **Vector search is ~0.001% of end-to-end latency.**

| Rejected | Why it lost |
|---|---|
| Pinecone / Weaviate / Milvus | Milvus needs etcd + MinIO to serve **0.7 MB**. This is the clearest possible signal you cannot size a system, and it is a one-question interview kill. |
| pgvector on Neon/Supabase | Genuinely the better *enterprise narrative* — and the narrative is free in the README's alternatives table. The code buys 0 marks and adds a network hop, a pool, migrations, and a cold start. **Its own advocate cut it from their own 6-hour plan.** |
| `sqlite-vec` second adapter + `VectorStore` Protocol | Its own advocate called it YAGNI in writing. "Which one is deployed?" → "so why is the other one in the repo?" → "insurance" = code the grader must read that runs nowhere. |
| HNSW (`m=16, ef_construction=200`) | **Strictly worse than not building it** at this scale: approximate (recall < 100%) in exchange for a speedup smaller than network jitter, and an m=16 graph over 481 nodes degenerates into near-fully-connected anyway. |

**The paragraph is worth more than any of the stacks — this is the single best sentence in the whole council, keep it verbatim in the README:**

> *"No ANN index. At 481 vectors, exact cosine search costs 0.023 ms — vector search is 0.001% of end-to-end latency against a ~2s model call. I would add pgvector with HNSW (m=16, ef_construction=200, ef_search=64) at roughly 50k vectors, where the exact scan crosses ~10 ms. Reaching for a distributed vector database to serve a 0.7 MB index is infrastructure cosplay."*

That sentence proves you know the HNSW parameters **and** know when not to use them, which is exactly what the question is probing. It gets 100% of the Architecture credit for 0% of the code and pre-empts the `ef_search` kill-shot.

### 3.7 Retrieval — **ASYMMETRIC, not stratified**

Three lenses independently proposed stratified per-doc top-k quotas to fix the 37:1 imbalance. **They are proposing a workaround for a problem that vanishes if you don't create it.**

**RULING: pin the entire handbook; retrieve only over the statute.**

The handbook is 13,378 chars ≈ 3.3k tokens. **Retrieval over a document that already fits can only lose information.** Pinning:
- eliminates the base-rate problem *by construction* rather than by tuning a quota you'd have to defend ("why 4 and 4?");
- makes "the handbook is silent on maternity" a **sound claim** rather than an inference from a failed top-k — verified: the handbook contains **0** occurrences of `maternity`, **0** of `overtime`, **0** of `paternity`, **0** of `WFH`;
- is *less* code than stratification, not more;
- collapses the router to at most one search call for most queries.

The better idea sat in the lens everyone was primed to distrust as agent-happy, and lost by repetition. It wins on every axis.

**Interview line:** *"The handbook is 3,300 tokens. Retrieving over it can only lose information. So I only retrieve over the document that doesn't fit."*

**MEASURED GOTCHA — verified against current API docs.** Opus 4.8's minimum cacheable prefix is **4,096 tokens**. The handbook alone is ~3.3–3.5k and **will silently fail to cache — no error, `cache_creation_input_tokens: 0`.** System prompt + citation spec + corpus manifest + handbook must clear 4,096 *together*.

```python
# Startup smoke test — a BUILD GATE, not a nice-to-have.
assert resp.usage.cache_read_input_tokens > 0, "cached prefix under the 4096 minimum"
```
Keep the cached prefix byte-stable: no timestamps, no session IDs, no `datetime.now()`, deterministic tool ordering, `json.dumps(..., sort_keys=True)`.

**ADVERSARY FIX, ACCEPTED:** asymmetric retrieval makes the handbook invisible to retrieval metrics, so Retrieval Accuracy (15 marks) would be measured over 97% of the corpus while the document the scenario is about is unmeasurable. **Index the ~10 handbook chunks anyway** (costs 10 rows and 30 seconds) so recall@k is measurable across both documents. That also gives the ablation that makes the design defensible: *"I measured recall@5 on handbook-targeted questions with retrieval, then shipped full-context instead because retrieval was lossy — here are both numbers."*

**Statute retrieval:** hybrid BM25 + dense, fused with **RRF (k=60)** — no alpha weight to justify. Top-k=8, small-to-big expansion to the full parent section (median section = 707 chars / 177 tokens; returning 8 whole sections ≈ 5k tokens against a 1M window — the precision/completeness tension that makes small-to-big a hard call elsewhere simply does not exist here). Assemble in **section-number order**, not relevance order — statutes read sequentially.

**Why hybrid, specifically here** — not the generic reason. Two measured arguments:
1. **IDF.** `gratuity` appears 10× in 61k body word-tokens, `retrenchment` 14×, `lay-off` 7× — rare high-IDF terms of art where BM25 is near-perfectly precise and dense embeddings blur them into `compensation` (120×). Conversely *"can my boss make me work overtime?"* has zero lexical overlap with the governing sections — dense wins.
2. **OCR noise is asymmetric.** Only 2 corrupted tokens in 61,098 body word-tokens (the OCR is clean at word level — the "OCR is noisy so BM25 breaks" argument is **false** and measured false). But real observed prose noise (`'taw'` for law, `'CUOAPTER'`, `'framed m conformity'`) breaks lexical matching on *prose*, while section numbers and statutory terms OCR cleanly and demand exact match. You need both scorers — for *this* reason.

### 3.8 Section lookup — `get_section(n)`

**SHIP:** a dict lookup on `section_no`. 20 minutes. **Extract it from the MCP lens and promote it — it is not an MCP feature and must not die with MCP.**

**FATAL HIT, CONCEDED — the "96% of sections are unreachable" statistic is FALSE and must never be spoken.** The claim: *"s.132 is defined on p80; the pages containing 'section 132' are [9, 81, 82, 161]. BM25 misses it."* Verified: the token `132` **is present** on that page (the header reads `132. Claims arising out of deductions from wages`), count = 1. BM25 tokenizes `132.` → `132` and the query → `{section, 132}`. `132` is a rare, extremely high-IDF numeric token — BM25 ranks that page at or near the top. The measurement searched for the literal **bigram** `"section 132"`, which no BM25 implementation on earth does. A strawman was measured, got 96%, and became a headline.

Worse: the same lens shipped a "passing" verification returning `'Bangladesh Labour Act 2006, s.115 (p.115)'` — s.115 is on printed page **59**. Their working prototype **emits a fabricated citation** and it was presented to the council as evidence the thing works. That is the "your citation says page 47 — prove it" kill, pre-loaded.

**Delete the 96% entirely.** `get_section` survives on an honest one-liner that needs no statistic:

> *"The Act has a natural primary key — the section number. I index it and look it up exactly, because approximating an exact key is silly. It's a `WHERE section_no = 132`, not agentic retrieval."*

Also true and worth saying: *"Statutes cite by number and never self-name in the third person, so a section header and a cross-reference to it are different strings — that's why the section number is a metadata field, not a similarity target."*

### 3.9 Reranking — **CUT**

Four lenses proposed it. The council contains its own refutation, unread.

- Over-retrieving top-20 of ~400 chunks is **4% of the entire corpus**. If retrieving 4% saturates recall, there is nothing left to recover — you are re-sorting a list that already contains the answer, for a generator that reads all of it anyway.
- Worse: the handbook's leave clause is **statutory boilerplate lifted from s.117** (Jaccard 0.53; `"shall be allowed during the subsequent period of twelve months leave"` appears verbatim in both). A reranker **promotes both near-duplicates higher** — it actively amplifies the corpus's hardest case.
- Its strongest advocate wrote *"hybrid+RRF may already saturate recall@10 — reranking could add nothing but latency"* and then budgeted 1.5h for it anyway, gated on an eval harness they placed at risk of being cut.

**RULING:** cut from Phase 0 and Phase 1. The council's own stated principle — *nothing ships that the harness hasn't scored* — applies to the reranker too. If the Phase 1 eval shows recall@5 materially below recall@20, add it then, as a measured decision. The README sentence writes itself.

### 3.10 Generation

**SHIP:** `claude-opus-4-8`, `thinking={"type":"adaptive"}`, `output_config={"effort":"high"}`, streaming, `max_tokens=8000`.

Verified against current API docs — **these will 400 on Opus 4.8, do not write them:**
- `temperature`, `top_p`, `top_k` — **removed, rejected with 400.** A README claiming *"temperature=0 for reproducibility"* is **wrong on current models**. Determinism comes from `output_config.format` json_schema (shape) + `effort: "low"` on the judge (tightness) + threshold-with-slack CI gates.
- `thinking: {"type":"enabled", "budget_tokens": N}` — removed, 400. Adaptive only.
- Last-assistant-turn prefill — 400. Use `output_config.format`.

Router: **`claude-haiku-4-5`** ($1/$5), `output_config.format` json_schema → `{route: HANDBOOK_ONLY|STATUTE_ONLY|COMPARE, confidence, reasoning}`. ~$0.002, ~400ms. Not an agent — one structured classification call. `HANDBOOK_ONLY` → zero retrieval, answers in <2s from the cached prefix (a real UX win). Low confidence → default to `COMPARE` (the strictly safer superset). **Log the label on every request** — it is the single best debugging signal and it makes §10's live-enhancement trivial ("add a fourth route" is a 3-minute change on camera).

### 3.11 Citation + verification

**Phase 0 — metadata citations, deterministic, free, correct.** Every chunk already carries `(doc_title, section_no, section_title, printed_page, zero_based_pdf_index)`. Render:

```
Bangladesh Labour Act 2006, s.117 Annual leave with wages — printed p.59 (PDF page 76 of 181)
  "Every adult worker, who has completed one year of continuous service…"
```

**The verbatim snippet is sliced from the chunk by code, not generated by the model.** That is the anti-hallucination guarantee, and it costs zero API constraint.

**Phase 2 — Anthropic Citations API** (`citations: {enabled: true}` on custom-content `document` blocks) upgrades the snippet to API-extracted `cited_text` with `content_block_location`, which the model **structurally cannot fabricate**. Verified constraint: **Citations is incompatible with `output_config.format` and returns 400.** So the `insufficient_information` signal must be derived from an *empty citations array* rather than a structured field. Knowing and being able to explain that trade is a strong interview beat — but it's a Phase 2 upgrade over a Phase 0 path that is already correct.

**CUT: click-to-verify bbox-highlighted page images (3h).** This hurts — it is genuinely the best trust-builder available, and uniquely powerful because one document is 100% scanned. But it is 3 hours aimed principally at a 5-mark line. `doc + printed page + section + verbatim snippet` lets the grader Ctrl-F the PDF in five seconds: **90% of the trust for 10% of the build.** Phase 2 if everything is green.

### 3.12 Abstention / refusal (FR#5)

**Similarity thresholding is measurably wrong on this corpus, and this is the best original finding in the council.** Measured: the *answerable* question "Who is the Chairperson?" (Sultana Hashem, folio 1) scores TF-IDF top-1 = **0.067**, while the *unanswerable* "How many days of paternity leave do I get?" scores **0.155** — because it collides with the casual-leave chunk. **The distributions overlap and invert.** Any threshold that refuses paternity also refuses the Chairperson. This is not accidental: a good adversarial question is *plausible*, and plausible means semantically adjacent. **Retrieval score is an anti-signal for adversarial abstention.**

**SHIP:**
1. **Structural soundness (free):** the handbook is fully in context, so absence is *provable*, not inferred from a failed retrieval. This is the cheapest correct implementation of FR#5 and it falls out of the asymmetric design.
2. **Claim-level entailment gate (Phase 1, 0.5h):** post-generation, for each `(claim, cited_doc, cited_section)`, call `claude-haiku-4-5` with **only that section's text** and `output_config.format → {entailed: bool}`. Unverified claims are stripped; if all fail, degrade to the insufficient-information response. ~$0.001/query, +300–600ms, parallelised with `asyncio.gather`. Entailment works where similarity fails because *"this text is about leave"* and *"this text states the paternity entitlement"* are different questions.
3. **Measure the false-refusal rate.** A gate you haven't measured for over-triggering is a gate you can't defend.

**Refusal is a designed product state, not a gray error box.** Neutral styling. Headline: *"Not found in the provided documents."* Body: what was searched (Employee Handbook, 10 printed pages + Bangladesh Labour Act 2006, 140 printed pages), the closest related material **with real citations**, and why the gap exists. The corpus gives a genuinely good example: *"The handbook covers Code of Conduct, Leave, Travel, Training, Appraisal, Confidentiality, Separation, Work Culture, Facilities, Lunch/Prayer, Visitors, and Standards of Conduct — parental leave is not among them. The Act addresses maternity benefit at ss.45–46 but does not address parental leave generally."* A search box cannot do that.

Prompt uses **positive** phrasing (*"state that the documents do not address X"*), never negative (*"do not hallucinate"*).

### 3.13 Agent layer — **CUT**

**FATAL HIT, CONCEDED. The single named justification for both cross-reference expansion and the bounded agent loop is factually false.**

The claim, cited by four lenses (RAG, Vector DB, Agent, MCP): *"s.100 says a worker shall not work more than eight hours: 'Provided that, subject to the provisions of section 108…'. Single-shot RAG returns s.100 and states 8 hours — **the exception lives in a DIFFERENT section**."*

It does not. s.100 verbatim (idx 73 / printed 56):

> *"**100. Daily working hours :** No adult worker shall ordinarily be required or allowed to work in an establishment for more than eight hours in any day: Provided that, subject to the provisions of section 108, any such worker may work in an establishment **not exceeding ten hours in any day**."*

**The 10-hour cap is in s.100 — same sentence, same page, same chunk.** And s.108 is `Extra-ailowance for overtime` — the 2× **pay rate**, a different question. §102 has the identical shape. **Section-aware chunking — which the whole council already agreed on — fully answers "what are the maximum working hours?" with "8 hours, extendable to 10."**

With that example dead, **no lens produced a single query that stratified hybrid + whole-section retrieval answers wrongly and a hop fixes.** The cross-reference *count* (121 `section N` + 172 `sub-section (N)`) is real; a count is not a failure mode.

**CUT:** the bounded agent loop, the ReAct loop, CRAG/Self-RAG/reflection, multi-agent (planner/researcher/critic), LangGraph/CrewAI/AutoGen. Two documents, one permanently in context. No coordination problem, no plan space, no long horizon. Multi-agent buys 4× latency, 4× cost, nondeterminism, and zero rubric marks — and it is the fastest available way to fail §10.

The RAG Architect recommended the deterministic 1-hop expansion *and* the agent loop for the same problem, plus a threshold-based router to arbitrate between them (and the threshold is exactly what gets asked about). Their own words defeat their own recommendation: *"90% of the value at 10% of the complexity and none of the nondeterminism."*

**Deterministic 1-hop cross-ref expansion is demoted from "ship" to "an eval hypothesis" (Phase 2).** It's ~20 lines of precomputed adjacency dict and it may well earn its place on genuine chains like *"compensation under section 19, 20 or 23 or wages under section 22, 23, 26 or 27"* — but **find the failing query first.** By the council's own standard, nothing ships that the harness hasn't scored.

**The interview answer this buys is better than any agent:** *"I don't have an agent. I counted 121 cross-references, then looked for a query that single-shot retrieval actually fails. The trap everyone quotes — s.100's working-hours exception — is inside s.100's own sentence; section-aware chunking already handles it. I couldn't find one on my eval set, so I didn't build the hop. Here's the number."*

### 3.14 MCP — **CUT from the build, KEPT in the README**

Zero rubric lines. Its own advocate scores it **+2–3 Architecture and 0 everywhere else**, and honestly concedes *"AI Response Quality (20): 0 directly from MCP. Do not claim otherwise."* Its headline statistic just failed. Its working prototype emits a fabricated citation. It wants 4.5h (server + prompts + resources + bearer auth + FastAPI mount) for a line item worth nothing, whose sole surviving justification is "Claude Desktop could call it too" — and §10's live-enhancement segment means a failed handshake on a shared screen is unrecoverable and costs more than the marks it was worth.

**Ship the paragraph instead** — it earns most of the +2–3 at zero risk:

> *"The retrieval layer is a standalone module with zero web or protocol imports. Exposing it over MCP so Claude Desktop, Cursor, or an internal agent can query the corpus is a ~21-line stdio adapter over the same four functions — `search_documents(query, doc_filter, k)`, `get_section(number)`, `get_document_page(doc_id, page)`, `list_documents()`. Deliberately deferred: the rubric has no protocol line, and MCP's value is crossing a trust boundary to foreign clients — there isn't one between my own FastAPI and my own retriever. Paying protocol overhead to talk to myself would be architecture theater."*

**Adopt the MCP lens's own decision rule** — the most disciplined sentence any lens wrote — as the **Phase 2 gate**: at hour 15, **if** `core/retrieval.py` imports nothing from `fastapi` or `mcp`, add the stdio server (45 min, screenshot in the README, `docs/claude_desktop_config.json` with an **absolute** interpreter path — Claude Desktop does not inherit your shell PATH, the #1 cause of silent startup failure). **Never on the live URL's critical path.** If retrieval logic is smeared across route handlers, do not bolt it on.

**Hard rejections regardless:** MCP as internal transport between your own agent and your own retriever (`anthropic.lib.tools.mcp.mcp_tool` making it easy is the trap, not the justification); OAuth 2.1 (6+ hours, zero marks — a bearer token via `token_verifier` documented as a demo credential is the senior move, and *naming* what you consciously declined outscores half-building it); SSE transport (Streamable HTTP is current; SSE is a stale-mental-model tell).

### 3.15 API — **STAFFED. This was 25 orphaned marks.**

Nine experts. **Software Engineering & Code Quality (15) and API Design (10) had no owner.** The Eval lead explicitly disclaimed them — *"the council should staff them separately"* — and nobody did. Six lenses knife-fought over the same 15 Retrieval marks and five separately budgeted 1–1.5h each to capture the same 5 Business Insight marks (~6 expert-hours chasing 5 marks) while **a quarter of the rubric went unread**. The council optimised the marks it enjoyed. Two hours fixes it.

```
src/
  core/          # retrieval, chunking, sections — ZERO fastapi/mcp imports (enforced by test)
  ingest/        # OCR, page maps, index build — a real CLI
  api/           # FastAPI routes, Pydantic models, error envelope
  prompts/       # versioned .md, loaded at runtime — NEVER inline f-strings (§9 requires you explain them)
tests/
data/extracted/  # committed OCR JSON
index/           # committed index.npz + chunks.jsonl + index_meta.json
```

```
POST /api/ask
  → {question: str, doc_filter?: "handbook"|"statute", section_no?: int}
  ← {answer, citations: [{doc_title, section_no, section_title, printed_page,
                          pdf_page, snippet, source_modality, ocr_confidence}],
     insufficient_information: bool, route: str, latency_ms: int, request_id: str}
GET /health       → {status, index_loaded: bool, chunk_count: int, index_version: str}
GET /api/documents→ corpus manifest with REAL page counts and modality
```

Typed error envelope with real status codes: **400** malformed, **422** no answer found in corpus, **429** upstream rate limit (surfaced with `retry-after`), **503** index not loaded. Never a 200 with a stack trace in the body. Structured JSON logging with `request_id` on every line. A settings module that validates env and **fails loudly at boot**. Explicit timeouts. `anthropic.RateLimitError` / `APIConnectionError` handled by class, never by string-matching the message.

`index_meta.json` = `hash(pdf_bytes) + ocr_params + chunker_version + embed_model_id + query_prefix_scheme`, verified at boot, logged loudly on mismatch. Twenty lines that answer *"how do you reindex when a document changes?"* in 60 seconds — a question that **will** be asked.

### 3.16 Frontend

**SHIP:** FastAPI-served static HTML + fetch + SSE streaming. **6 seeded question chips.** ~1.5h.

| Rejected | Why it lost |
|---|---|
| React SPA (Vite) — 6h | 0.83 marks/hour against a 5-mark line, from the same lens that left deploy uncosted, and it adds a build step, a static-serving path, and a CORS surface to a deploy nobody budgeted — three new ways for the live URL to die. **Its own author conceded it:** *"at a true 6-8h budget… Streamlit + a separately-exposed FastAPI is the CORRECT cut — a broken React app scores far worse than a working Streamlit one, and 20+20+15 dwarfs the 5 for UX."* They argued themselves into the right answer and recommended the wrong one. |
| Streamlit | Fine, but you must build FastAPI anyway for the separate 10 API marks — so the frontend is the only free variable, and a static page is *less* work than Streamlit's rerun model. |

**The 6 chips are the highest-ROI 30 minutes in the entire build** and are non-negotiable. The grader cannot invent good questions about a Bangladeshi labour statute. An empty text box means they type *"what is the leave policy?"*, get something competent and forgettable, and close the tab. Order builds an arc — warm-up → flagship → nuance → honest unknown:

1. *"How many days of casual leave am I entitled to?"* — easy; handbook says 10 **and** s.115 says 10. Both agree. Shows the citation UI working.
2. **FLAGSHIP:** *"Does our Employee Handbook comply with the Bangladesh Labour Act on maternity leave?"* — reasoning about an **absence**. ss.45/46 mandate 8 weeks before + 8 weeks after = 16 weeks; the handbook is silent (0 occurrences of "maternity") while claiming compliance on its own folio 1.
3. *"We work Sun–Thu 9–5 and Sat 9:00–1:30. Is that legal?"* — 44.5h ≤ 48h (s.102) ✓; weekly holiday Friday + Saturday half = 1.5 days = **exactly** s.103(a)'s minimum for a commercial establishment. A nuanced *"compliant, and only just"* answer proves reasoning, not pattern-matching.
4. *"How much overtime pay is required?"* — handbook silent; s.108 = 2× ordinary rate.
5. *"What is the parental leave policy?"* — the honest, designed **"I don't know."** Verified absent from both.
6. *"Who is the Chairperson and where is the head office?"* — Sultana Hashem; Shanta Western Tower L-13, Tejgaon, Dhaka-1208. Grounds the demo.

### 3.17 Eval

**SHIP:** hand-rolled harness, ~150–200 LOC, 30 hand-verified questions, **three metrics only**.

| Rejected | Why it lost |
|---|---|
| RAGAS / DeepEval / promptfoo | **Spec-level, not taste:** §9/§10 require you to explain your PROMPTS at interview. RAGAS's faithfulness prompt is not yours to explain — you'd spend an hour on OpenAI-adapter config to inherit a prompt you cannot defend for your headline metric. None of them models the two-authority-level structure anyway. |
| nDCG | Needs graded relevance; you have binary labels. Computing it from binary labels is theatre. |
| 50–60 questions | Hand-verification is what makes the number real, and hand-verification is the budget. 30 with an honest CI beats 60 you didn't check. |

**Metrics: recall@5 · groundedness · the abstention 2×2.** Fold citation-correctness *into* groundedness — *"is this claim entailed by the cited section?"* answers both at once. This is the highest-value collapse available. **Report the 2×2 confusion matrix, never refusal rate alone** — a system that refuses everything scores 100% on abstention, and one that never refuses scores 100% on coverage.

**Tiers — REBUILT. Two fatal hits conceded.**

**Tier D was contaminated by its own author.** The "verified TRULY ABSENT from both" list included **overtime, minimum wage, grievance, and notice period** — all four are in the Act: s.108 `Extra-ailowance for overtime` (idx 73), s.138 `Establishment of Minimum Wages Board` (idx 82), s.140 `Power to declare minimum rates of Wages`, s.33 `Grievance procedure` (idx 51), s.26 `Termination of employment by employers` (idx 49). The *same output*, four lines earlier, lists **overtime and minimum wage under Tier B ("Act only — MUST ANSWER")**. The same two questions carry contradictory gold labels in one deliverable. And it proposed a **zero-tolerance CI gate**: *"any Tier-D question that gets answered fails the build."* So the harness would **fail the build when the system correctly cites s.108**, and the candidate would "fix" it by teaching the system to refuse questions the corpus answers — **destroying the 20 marks the lens claims to own.** The lens warned *"hand-verify EVERY row against the PDF"* and did not hand-verify its own tier list.

> **Rebuild Tier D from the ONE construction that is provably safe** — the construction the Fine-Tuning lead found and everyone ignored: **questions about the five documents that do not exist.** *"What commission rate does the Sales Handbook specify?"* *"What does the FAQ say about expense claims?"* Provably unanswerable because the documents are provably absent, corpus-grounded, and a perfect FR#5 test that **no other candidate will think to build — because no other candidate will notice the assets don't match the spec.** Survivors of the grep audit: WFH/remote, paternity, pension. **That's three, not ten.** For anything claimed absent from the Act, **prove it with a grep over your own OCR and commit the grep as the test.**

**Tier C contained zero conflicts.** The headline — *"the two documents give DIFFERENT answers to the SAME question"* — is a category error. s.117 verbatim: *"Every adult worker… **shall be allowed** during the subsequent period of twelve months leave with wages… **at the rate of** one day for every eighteen days of work."* That is a statutory **floor** (`shall be allowed… at the rate of`), not a value. Partex granting 30 days flat **exceeds** it → compliant. And the tier listed *"casual leave (both say 10)"* and *"sick leave (both say 14)"* as **conflicts** — s.115 = ten days, s.116(1) = fourteen days, handbook = 10 and 14. **Those are exact matches.** Three items, zero conflicts. Two other lenses explicitly predicted this failure mode (*"a naive diff agent reports '30 vs 18 = MISMATCH' and is wrong"*); the lens that owns 20 marks for response quality **became** the predicted failure. Had a system been graded against this set, **correct answers would have been penalised.**

> **The ONE real conflict in this corpus** was found only by the Fine-Tuning lead and buried as a bullet: handbook folio 7 — *"New joiners will get leave after completion of their probation period on a pro-rata basis"* — vs s.115 *"**Every** worker shall be entitled to casual leave"* and s.116(1) *"**Every** worker… shall be entitled to sick leave"*, neither carrying a probation qualifier. (s.117 *does* require "one year of continuous service", so annual leave during probation is fine — that nuance is the proof you read it.) **That is a genuine, citable, defensible conflict and it is worth more than eight fabricated ones.**

**Final tiers (n=30):**

| Tier | n | Content |
|---|---|---|
| **A — Handbook only** | 8 | working hours (Sun–Thu 9–5, Sat 9–1:30), dress code, transport, canteen, 1hr lunch/prayer, Chairperson Sultana Hashem, founded 1962 by M.A. Hashem, appraisal |
| **B — Statute only** | 8 | s.46 maternity 16 weeks (printed p.39), s.118 eleven festival holidays (printed p.60), s.108 overtime 2× (p.57), s.24 due process (p.32), s.138/140 minimum wage, s.33 grievance, s.26 notice, trade unions |
| **C — Floor comparison** | 8 | *renamed from "conflict".* casual 10 = s.115 floor (match) · sick 14 = s.116(1) floor (match) · annual 30 > s.117 floor (**exceeds → compliant**) · hours 44.5 ≤ 48 (s.102) · weekly holiday exactly at the s.103(a) minimum · **the probation carve-out vs "every worker" — the one real conflict** |
| **D — Unanswerable** | 6 | 3 × the nonexistent documents (Sales Handbook commission, FAQ, Company Profile) + WFH/remote, paternity, pension — each grep-verified, grep committed as the test |

Store as `evals/golden.yaml` with `{q, tier, expected_behavior, gold_answer, gold_doc, gold_section, gold_printed_page}`. Draft with `claude-opus-4-8` against the extracted text, then **hand-verify every row against the rendered page image** — the LLM-generated golds will be wrong precisely on the floor-comparison cases, which is the point.

**Write the golden set BEFORE the retrieval pipeline** — the questions come from the PDFs, not from what the system happens to do well.

**Judge:** `claude-haiku-4-5` (different tier from the answerer — cheap insurance), `output_config.format` json_schema → `{verdict, cited_section_contains_claim, reasoning}`, `effort: "low"`. Measured cost: ~$0.24/run, ~$0.12 via the Batch API (50% off). **Cost is a non-argument here; your time is the constraint.**

**Few-shot anchor the judge with 3 examples from THIS corpus.** Anchor #2 is the highest-value few-shot in the whole build: *"You get 30 days annual leave [Labour Act s.117]"* — **right number, wrong source**; the Act says one day per eighteen. A naive judge waves it through.

Honest reporting: **n=30 → 95% CI ≈ ±10.7pp at a 90% score. Say so.** An honest wide interval beats a fake tight one. Report the harness commit SHA and date so the numbers are reproducible, not aspirational. Do **not** invent a Cohen's κ you didn't compute — hand-check the ~5 judge verdicts that disagree with your expectation and report that as *"spot-checked"*.

**The full-context oracle (1h) — buy it back first.** Because the corpus is ~128k tokens, put **all** of it in one cached `claude-opus-4-8` call and answer every eval question. Cost: 128k × 1.25 × $5/M = **$0.80** one-time cache write + 128k × 0.1 × $5/M = **$0.064/query** → **~$2.72 for 30 questions.** It is the highest marks-per-hour item on the board: it answers the deadliest question on this corpus, it is the *ceiling* you measure RAG against, and **it debugs your golden set for free** — anything both the oracle and RAG miss is a bug in your gold labels, not your retriever.

### 3.18 Deploy

**SHIP:** single Docker container, **Hugging Face Spaces** (free, 16 GB RAM, no card, no 15-min spindown death). Render free = 512 MB + spindown + 30–60s cold start; that's an ML-demo deploy target that fights you.

**BUDGET IT AS A FIRST-CLASS LINE ITEM.** Across 133.75 proposed council-hours, hours allocated to wiring, Dockerfile, deploy config, and a cold-start dry-run: **zero** — while **seven of nine lenses independently rate "dead live URL" as CRITICAL.** The council was unanimous that this is the worst outcome and unanimously declined to budget for preventing it. That is the most revealing pathology in the entire output.

**Deploy a hello-world FastAPI + committed-index skeleton at hour 3, not hour 9.** A deploy that works at hour 3 and gets richer ships. A deploy attempted at hour 12 is a coin flip at 11pm when onnxruntime needs a wheel the base image doesn't have.

Hard rules: **no tesseract in the runtime image.** `data/extracted/*.json` and `index/*` committed. `GET /health` asserts the index loaded and returns the chunk count. **Test an actual cold start from a browser before submitting.** Hand-written `requirements.txt`. CI check: `torch` not in the tree; re-running ingest is byte-identical (proves determinism).

---

## 4. Verdicts on the candidate's four stated desires

### RAG — **KEEP, but REFRAME as a defended choice**

Ship it. But you must be able to say why, because the interviewer will do the token math.

**Do NOT defend RAG on cost.** With prompt caching, full-context is ~$0.064/query vs RAG's ~$0.025 — that's **2–3×, not 40×**. Anyone claiming "RAG saves money" here has not done the caching math and gets broken open in one follow-up. Two lenses saved you from this self-inflicted wound; take the save.

> **THE SENTENCE:** *"I measured the corpus at [N] tokens with `count_tokens` — it fits in one window, so RAG here is a choice, not a necessity. I built the full-context baseline anyway and it's in my eval as the oracle: it's the ceiling I measure retrieval against, and here's the gap. I still ship RAG for three reasons — the rubric grades Retrieval Accuracy as its own line and you can't score it without a retriever; citation provenance is by construction when a chunk carries its own page, whereas a context-stuff invents page numbers; and it doesn't survive the six-document corpus your spec actually described. I don't defend it on cost — with caching, full-context is about two to three times RAG's per-query cost, not forty."*

### MCP — **CUT from the build, KEEP as a costed README paragraph**

Zero rubric lines. Its advocate scored it +2–3 Architecture and 0 elsewhere, then ranked it a ship. Its headline statistic is a strawman. Its prototype emits a fabricated citation. §10's live-enhancement segment makes a failed handshake catastrophic and unrecoverable. Phase 2 gate at hour 15 (see §3.14) if and only if `core/` is protocol-clean.

> **THE SENTENCE:** *"MCP is a distribution protocol, not a retrieval technology — it earns its cost by crossing a trust boundary to foreign clients, and there isn't one between my own FastAPI and my own retriever. My retrieval layer is a clean module with zero web imports, so exposing it over MCP for Claude Desktop is a 21-line adapter — here are the four tool signatures. I deferred it deliberately: the rubric has no protocol line, and I'd rather spend the hours where you're actually scoring me. Paying protocol overhead to talk to myself would be architecture theater."*

### Vector DB + Agents — **CUT both. REFRAME as measurements.**

**Vector DB:** 481 × 384 = 0.7 MB; exact cosine = 0.023 ms. numpy + rank_bm25. The README's alternatives table gets you the "I know vector DBs" signal for free.

> **THE SENTENCE (vector DB):** *"No vector database and no ANN index. At 481 vectors, exact cosine is 0.023 milliseconds — vector search is 0.001% of my end-to-end latency against a two-second model call. I'd add pgvector with HNSW at m=16, ef_construction=200, ef_search=64 at roughly 50k vectors, where the exact scan crosses 10 milliseconds. Milvus needs etcd and MinIO to serve 0.7 megabytes; that's not an architecture, it's a costume."*

**Agents:** the one named justification was false (§3.13). No lens produced a query that needs a hop.

> **THE SENTENCE (agents):** *"I don't have an agent, and I want to tell you why, because I started out planning one. I counted 121 'section N' cross-references in the Act and that looked like a multi-hop retrieval problem. Then I went looking for a query that single-shot retrieval actually gets wrong. The example everyone reaches for is section 100's working-hours cap deferring to section 108 — but I read section 100 and the ten-hour exception is in section 100's own sentence, and 108 is the overtime pay rate, a different question entirely. Section-aware chunking already handles it. I couldn't find a failing query on my eval set, so I wrote no loop. Two documents, one of them permanently in context — there's no coordination problem to solve, and an agent would have added latency, nondeterminism, and something I'd have to defend to you right now."*

### Fine-tuning — **CUT. Zero gradient steps. This is the strongest section of your submission.**

Unanimous across nine experts and three adversaries, and correct. Four independent reasons, in order of force:

1. **It is unimplementable with the stated provider.** Verified against the current Claude API surface: `/v1/messages`, `/v1/messages/batches`, `/v1/files`, `/v1/messages/count_tokens`, `/v1/models`, Managed Agents. **No fine-tuning endpoint exists.** "Fine-tune Claude" is not unwise — it is impossible, and it would force a provider switch *away from the model doing the reasoning*, trading 20 marks of Response Quality for a résumé line.
2. **There is no signal.** ~128k tokens. Zero labelled relevance data. It fits in one context window — the standard justification ("the model must internalise knowledge that won't fit") is *factually false here*, and the interviewer finds that in 30 seconds.
3. **It attacks the requirement you must satisfy.** FR#4 demands page citations, which weights cannot ground — a fine-tuned model emits a citation-*shaped token sequence*, not an attribution. FR#5 demands abstention, and fine-tuning on synthetic Q/A teaches the model that **every question has an answer**. It makes the product measurably worse in exactly the two places the rubric grades hardest.
4. **You could not validate it.** You'd synthesise training pairs from the same 481 chunks your eval questions come from — guaranteed leakage, no held-out set. *"What was your train/test split and what lift did you measure?"* has no answer. And with a measured minimum-detectable-delta of ~9.9pp at n=50 against a realistic +2–8pp gain, **the experiment is unpowered — any result would be noise.** Unmeasurable means unclaimable.

**Also CUT: the "measured negative ablation" (2.5h).** This is ego wearing humility's clothing and it is the most seductive bad idea on the table. Its own advocate pre-declares the outcome (*"I expect this to come out neutral"*) and ranks it **fourth** on their own stretch list, shipped **disabled**. You do not spend 2.5 hours proving a conclusion you've already stated with confidence, and **the README paragraph is byte-identical either way.** No interviewer asks to see the training curve for a thing you correctly declined to build.

> **THE SENTENCE:** *"I considered fine-tuning and rejected it for four reasons. First, Anthropic exposes no fine-tuning endpoint for Claude at all — it would have forced a provider switch away from the model doing the reasoning. Second, my corpus is [N] tokens with zero labelled relevance data; it fits in one context window, so there's no knowledge to inject and no training signal. Third, it can't fix either thing that was actually broken here — page provenance and table layout — and it actively degrades abstention, because training on synthetic Q&A teaches the model that every question has an answer, which is the opposite of requirement 4.5. Fourth, at n=30 my minimum detectable delta is about eleven points and a realistic embedding fine-tune gains two to eight — the experiment is unpowered, so any number I reported would be noise. I'd fine-tune an embedder on mined hard negatives if this grew past ~50k chunks and a 200-question gold set showed a persistent 10-point vocabulary-mismatch gap that normalisation couldn't close. Not before."*

That answer scores more than any fine-tune could, and it turns the candidate's weakest section into their strongest.

---

## 5. The killer differentiator — RULING

**YES. The compliance-gap framing is the move. Ship it. Time-box it to 1.5 hours total.**

It is not scope creep. It is a system prompt plus 3 example questions over the *identical* RAG core, and it is the only decision that converts the corpus mismatch from an embarrassing liability (*"the spec promised 6 HR docs; I got a scanned statute"*) into the differentiator (*"the assets contain a compliance claim and the law it cites — so I built the product that reveals the gap"*). It targets AgamiSoft's actual market: Bangladeshi employers who must comply with this exact statute.

**The corpus forces a decision.** 181 of 187 pages are national statute. Pure handbook Q&A ignores 97% of the corpus. Pure statute Q&A ignores the employer's own document. The only architecture that honestly serves both is one that knows which is which and can relate them.

**Verified ground truth (reproduced independently ≥2×):**

| Topic | Partex Handbook | Bangladesh Labour Act 2006 | Verdict |
|---|---|---|---|
| Casual leave | 10 days (folio 6) | s.115 "ten days" (printed p.59) | **Exactly at the floor** |
| Sick leave | 14 days (folio 6) | s.116(1) "fourteen days" (printed p.59) | **Exactly at the floor** |
| Annual leave | 30 days after 12 months (folio 6) | s.117(1)(a) 1 day per 18 days worked ≈ 14–17 (p.59) | **Exceeds → compliant** |
| Working hours | Sun–Thu 9–5, Sat 9–1:30 = 44.5h | s.100 8h/day (→10h), s.102 48h/week (p.56–57) | **Compliant** |
| Weekly holiday | Friday + Sat half = 1.5 days | s.103(a) commercial establishment minimum | **Compliant, and only just** |
| **Maternity** | **0 occurrences** | ss.45/46: 8 weeks before + 8 weeks after = **16 weeks** (printed p.39) | **GAP** |
| **Festival holidays** | 0 — only *"Festival Bonus"*, a **payment** | s.118(1): **eleven days paid** (printed p.60) | **GAP** |
| **Overtime** | **0 occurrences** | s.108: **2× ordinary rate** (printed p.57) | **GAP** |
| **Due process** | §L: action *"as deemed appropriate by the management"* | s.24 (p.32): written charge + ≥7 days to explain + hearing + enquiry + approval | **CONFLICT** |
| **Probation carve-out** | *"New joiners will get leave after completion of their probation period"* (folio 7) | s.115/s.116: "**Every** worker shall be entitled" — no probation qualifier | **CONFLICT** |

And the handbook, on folio 1, states verbatim: *"The human resource (HR) policies and procedures contained in this handbook are in compliance with the applicable labor laws of Bangladesh."* **The corpus is a claim plus the evidence that falsifies it.** That is not narrative — it's a real, citable finding, and it is the only route to the full 5 Business Insight marks.

### Three hard rules

**1. Floor semantics are encoded in the prompt, not hoped for.**

> *"The Act sets statutory MINIMA. If the handbook grants at or above the statutory minimum, it is COMPLIANT — report it as such. Report a gap ONLY where the handbook grants LESS than the floor, or is SILENT on a mandatory entitlement. Cite both sources verbatim with printed page numbers. Never assert a gap without both citations."*

Without this, *"30 vs 18 = MISMATCH"* is a confidently wrong answer that torches the 5 marks it was chasing. Two lenses predicted it; one committed it in their golden set.

**2. Scope goes IN THE ANSWER, not the footer.** The flagship demo tells a Bangladeshi grader that a Bangladeshi employer's handbook is non-compliant with Bangladeshi labour law, sourced from the 2006 Act as published by the Bangladesh Employers' Federation in **2009** (verified: OCR p1; PDF creationDate 2011) — materially amended in **2013 and 2018**, including in this exact area. Only two of nine lenses flagged staleness, and both filed it as a README bullet. **It is not a footnote — it is the demo detonating in the room, in front of the one audience most likely to know.**

Every compliance answer **opens** with the frame:

> *"Against the Bangladesh Labour Act 2006 as published in the provided 2009 BEF handbook — amendments after 2006 are not in this corpus — the Employee Handbook does not appear to address maternity benefit, which s.46 (printed p.39) requires at eight weeks preceding and eight weeks following delivery. [Employee Handbook §B lists only Annual, Sick, Casual, and Probation leave — folio 6.]"*

**3. Phrasing discipline.** *"does not appear to address X, which s.Y requires"* — **never** *"violates"*, never *"you are breaking the law"*. Persistent UI disclaimer: *"Documented gap analysis to support HR review against the provided 2006 text. Not legal advice."* Always render the verbatim statutory snippet so a human verifies the machine. **Getting this framing right is itself a Business Insight mark; getting it wrong is a red flag about judgement.**

**Sequencing (the legitimate half of the objection, conceded):** build it **fourth**, additively, behind a route label, on top of a working system. If it isn't solid at the 80% mark, ship the single maternity path and document the general case as future work — that captures most of the marks at a fraction of the risk.

---

## 6. Phased build plan

**Council arithmetic:** 133.75 proposed hours against a 6–8 hour budget — a **19× overshoot**. Every lens's own "6-HOUR CUT" exceeded 6 hours ("~8h, the honest floor" · "~7h" · "8h" · "≈6.5h" · "6h exactly" · "~7h"). Summed, the *cuts* are ~51h. OCR was proposed 8 times, the page mapping 8 times, section-aware chunking 7 times, the full-context oracle 6 times, the eval harness 6 times. **Nobody deduped. Nobody integrated. There is no merged build order anywhere in 20,000 words.**

This is it. **One clock. One owner per artifact. Cut globally, not per-lens.**

### Phase 0 — MUST SHIP (~10h). Critical path.

| # | Item | h | Gate |
|---|---|---|---|
| 1 | OCR script (8 workers) → committed JSON. **Hold the page ref.** Partex clip extraction + NFKC + hyphen repair. Drop TOC idx 1–15, annex idx 157–180. Layer tags. | 1.5 | `mean_chars > 1500`; no body page < 300 |
| 2 | `PRINTED_OFFSET = 16`, 0-based, ONE convention. Partex folio `2i−1`/`2i`. 6 pytest asserts. | 0.5 | tests green |
| **3** | **Deploy hello-world FastAPI + skeleton index to HF Spaces. DO THIS AT HOUR 3.** | 1.0 | `/health` returns 200 from a browser |
| 4 | Section index: dual-grammar + **wrapped-title fix** + LIS, scoped idx 33–156. | 1.5 | `{45,46,100,108,115,116,117,118} ⊆ detected` |
| 5 | Chunk + fastembed bge-small (**query prefix**) + numpy + rank_bm25 + RRF. Asymmetric retrieval: pin handbook, retrieve statute. Index handbook chunks anyway for eval. | 1.5 | `cache_read_input_tokens > 0` |
| 6 | Haiku router (3-way json_schema) + synthesis: cite-or-abstain, **floor semantics**, **in-answer staleness frame**, code-sliced verbatim snippet. | 1.5 | 6 chips answer correctly |
| 7 | **SWE + API (the orphaned 25 marks):** `src/` layout, `core/` with zero web imports, Pydantic models, typed error envelope (400/422/429/503), JSON logging + `request_id`, settings validated at boot, hand-written `requirements.txt`, pytest on page maps + de-interleave + one e2e `/ask`. | 1.5 | `pytest` green; no torch in tree |
| 8 | Static HTML + SSE + **6 chips** + designed refusal card. | 1.0 | — |
| 9 | Final deploy + **cold-start dry-run from a browser**. | 0.5 | live URL answers chip #2 |
| 10 | README + Mermaid + verbatim prompts + rejections + corpus-reality opener. | 1.5 | — |

**Critical path:** 1 → 2 → 4 → 5 → 6 → 9. Items 3, 7, 8, 10 parallelise against it. **Item 3 is not optional and not last** — everything else is invisible if the URL is dead.

### Phase 1 — DIFFERENTIATORS (~4h). Only after Phase 0 is live and green.

| Item | h | Why |
|---|---|---|
| 30-question 4-tier golden set, **hand-verified against rendered page images**; hand-rolled harness; recall@5 + groundedness + abstention 2×2. | 2.0 | Only artifact that touches 4 rubric lines at once. Written **before** you tune retrieval. |
| **Full-context oracle + RAG-vs-oracle ablation table.** ~$2.72. | 1.0 | Highest marks-per-hour on the board. Answers the deadliest question. **Debugs the golden set for free.** |
| `get_section(n)` + `section_no` API filter. | 0.5 | Deterministic lookup on a natural primary key. 20 min. |
| Claim-level entailment gate + false-refusal measurement. | 0.5 | Turns FR#5 from a prompt line into an enforced, measured invariant. |

### Phase 2 — STRETCH (~3h). Only if Phase 1 is green.

| Item | h | Gate |
|---|---|---|
| Citations API `cited_text` (custom-content blocks). | 1.0 | Document the `output_config.format` 400 incompatibility as a considered trade. |
| Deterministic 1-hop cross-ref expansion. | 0.5 | **ONLY** if the eval produces a query that single-shot demonstrably fails. |
| MCP stdio adapter + Claude Desktop screenshot. | 1.0 | **ONLY** if `core/retrieval.py` imports nothing from `fastapi`/`mcp`. Never on the live path. |
| Click-to-verify pre-rendered page images (110 dpi, jpg75, ~90 KB/page, ~20 MB, built offline). | 0.5 | — |

**Total: ~17h.** Honest. **Cut ~117 hours from the council's proposal.**

### Cut without mercy

Fine-tuning (all forms, including the "measured negative ablation") · the agent loop · multi-agent · CRAG/Self-RAG/reflection · DSPy (§9 requires you explain your prompts; DSPy writes prompts you didn't) · the cross-encoder / Haiku reranker · pgvector · sqlite-vec · the `VectorStore` Protocol · HNSW · Pinecone/Weaviate/Milvus · the React SPA · Streamlit · docling/marker/surya · all OCR preprocessing · dpi sweeps · spell-ratio QA (it **flagged correct pages as broken** — the OOV tokens were "workers", "rates", "Sramik" — and missed the real defect) · Bengali traineddata · table-annex vision repair · RAGAS/DeepEval/promptfoo · nDCG · MRR · OAuth 2.1 · auth (the spec says *"test credentials **if** auth enabled"* — so don't enable it; it only creates an obligation) · conversation persistence · CI/GitHub Actions (leave the pytest wrapper so you can truthfully say *"this runs in CI with one workflow file"*).

---

## 7. Top risks and specific mitigations

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| 1 | **The submission isn't read.** 4 days late. Zero of nine experts treated it as an action; three converted it into licence to spend 20–30h on a submission that may be in the bin. | **fatal** | Email today (§0). Ship Phase 0+1 in 48h. One honest line in the email, not buried in the README. Optimising the contents of a box before confirming it gets opened is denial, not defensibility. |
| 2 | **Dead live URL.** 100–150s OCR vs a 30–60s health check. `pip freeze` ships 2.5 GB of torch and OOMs every free tier. Seven lenses called this CRITICAL; **zero hours were budgeted to prevent it.** | **fatal** | Commit OCR JSON + index. No tesseract in the image. fastembed/ONNX, hand-written reqs, CI asserts no torch. **Deploy at hour 3.** HF Spaces. Cold-start dry-run from a browser before submitting. |
| 3 | **Silent blank index.** The PyMuPDF weakref bug + a swallowing `try/except` returns "" for all 181 pages and **reports success** ("DONE 181 pages in 167.8s, total_chars 0"). | **critical** | `pg = doc[i]` before `get_textpage_ocr`. Build-gate assertions on mean chars/page. Fail the build, never the query. |
| 4 | **Off-by-one on every statutory citation.** The council's own -16/-17 base confusion, shipped as an apparent consensus. | **critical** | ONE constant, ONE declared base, in the variable name. Six pytest asserts against OCR'd footers. Render both printed and PDF page. |
| 5 | **Silent Partex corruption.** Naive extraction interleaves the Leave Policy with the Confidentiality Policy line-by-line into every chunk of the one document the scenario is about — **and never throws**. Two lenses' prescribed block-x0 fix gets folios exactly backwards on the page you'd check. | **critical** | Clip at `page.rect.width/2`, computed per page. Regression test: the "Leave During Probation" chunk must not contain "Confidentiality". |
| 6 | **s.46 silently dropped by the recommended regex**, taking the flagship maternity demo with it — merged into s.45's chunk with s.45's metadata. | **critical** | Wrapped-title regex + `assert {45,46,100,108,115,116,117,118} ⊆ detected`. Re-report recall **after** the fix. |
| 7 | **Eval set contaminated.** Tier D contained 4 questions the Act answers, with contradictory Tier-B labels in the same output, behind a zero-tolerance CI gate that would train the system to refuse answerable questions. Tier C contained zero conflicts. | **critical** | Rebuild both (§3.17). Tier D from the nonexistent documents + 3 grep-verified absences, grep committed as the test. Tier C → floor-comparison + the one real probation conflict. Hand-verify every row against the rendered page. |
| 8 | **Confidently wrong compliance answer to a Bangladeshi grader** using a 2009-published 2006 text, amended 2013/2018. | **high** | Scope goes **in the answer's opening clause**, not the footer. *"does not appear to address"*, never *"violates"*. Both citations verbatim or no gap assertion. Persistent disclaimer. |
| 9 | **Résumé-driven scope torches the timeline** (FT + MCP + agents + vector DB on a 2-document corpus) and reads as an engineer who can't distinguish a real requirement from a shiny one — a **hiring** signal, not a marks signal. | **high** | Every component carries a one-line justification traceable to a measured corpus property. If it can't, it's cut. The council's own rule, applied to the council. |
| 10 | **Seven numbers for one fact.** 2× spread on corpus size, 5.6× on OCR timing, 8× on chunk count, 48–94% on section recall — all "measured". §9 makes this disqualifying; the wrong ones are falsifiable in 30 seconds. | **high** | One committed `corpus_stats.json`. `count_tokens`, never chars/4, never tiktoken. Quote wall-clock, never s/page. Delete every other figure. |
| 11 | **Prompt cache silently fails.** Handbook 3.3k < Opus 4.8's 4,096-token minimum → `cache_creation_input_tokens: 0`, no error. You pay full input price every query and the latency story is wrong. | **medium** | System + citation spec + manifest + handbook must clear 4,096 together. `assert cache_read_input_tokens > 0` as a **startup build gate**. Byte-stable prefix: no timestamps, no UUIDs, sorted JSON. |
| 12 | **README claims `temperature=0` for reproducibility** — **wrong on current models** (400 on Opus 4.8 / Sonnet 5). | **medium** | Don't. Determinism via `output_config.format` json_schema + `effort: "low"` on the judge + threshold-with-slack. Report the CI (±10.7pp at n=30). |
| 13 | **Empty search box.** Grader types "what is the leave policy?", gets something competent and forgettable, closes the tab. Never sees the compliance capability. | **high** | 6 chips, 30 minutes, ordered warm-up → flagship → nuance → honest-unknown. Plus a 60-second demo script at the top of the README naming the three questions to click. |
| 14 | **25 marks unread.** SWE (15) + API (10) had no owner across nine experts; a beautiful retriever in a repo with no structure and a 200-with-a-stack-trace scores 8/15 and 5/10. | **fatal** | §3.15, 2h, staffed. |
| 15 | **OCR noise reaches the user as a fabricated legal quote** (`'shal!'`, `'Tribunaj'`, `'imjury'`, `'Jeave'`, `'for cight weeks'`). | **medium** | Substantially de-risked by a corpus property nobody expected: **the legally-operative quantities are in WORD form** — "eight weeks" (9×), "fourteen days" (7×), "ten days" (5×), "eight hours" (4×), "sixteen weeks" (2×). Word-form numbers are far more OCR-robust than digits ('14' silently flips to 'l4'; 'fourteen' is a dictionary word tesseract's LM corrects). The handbook is text-native and belt-and-braces ("thirty (30) days"). Mitigations: render the verbatim OCR snippet next to every citation; surface `source_modality: "ocr"` + confidence per chunk; cite by section number (which OCRs cleanly) alongside the page; **bidirectional numeral normalisation on the BM25 index only** ("fourteen" → "fourteen 14") — measured: statute p.76 has `fourteen` ×2 and `14` ×0, so *"14 sick days?"* lexically **misses s.116**, the exact governing section. ~40 lines. |

---

## 8. The interview defence pack

**Eight questions. One line each. Rehearse them cold.**

---

**Q1. "Your corpus is 187 pages and fits in one context window. Why did you build RAG at all?"**

> *"I measured it — [N] tokens with `count_tokens`, so you're right, it fits, and I built the full-context version. It's in my eval as the oracle: it's the ceiling I measure retrieval against, and the gap is [X]. I ship RAG for three reasons — your rubric grades Retrieval Accuracy as its own fifteen marks and you can't score that without a retriever; citation provenance is by construction when a chunk carries its own page, whereas a context-stuff invents page numbers; and it doesn't survive the six-document corpus your spec described. I don't defend it on cost — with caching, full-context is two to three times RAG, not forty."*

---

**Q2. "Your citation says section 117 is on page 59. Prove it."** *(the ten-second kill)*

> *"Open the PDF to page 76 and read the footer — it says 59. The Act has seventeen pages of front matter, so printed equals the zero-based PyMuPDF index minus sixteen; I validated that against six OCR'd footers and it's a pytest assertion in the repo. I render both — 'printed p.59 (PDF page 76 of 181)' — so you can verify either way. Partex is worse: it's a two-up landscape spread, so one PDF page holds two printed folios, and PyMuPDF returns the right-hand page's blocks first on one of them. I split geometrically at the midline rather than by block x-coordinate, because the footer is a single block that spans the gutter — filtering on block x0 puts the right page's folio in the left half and gets it exactly backwards."*

---

**Q3. "Why didn't you fine-tune? You said you wanted to."**

> *"Four reasons, and the first one ends it: Anthropic exposes no fine-tuning endpoint for Claude, so it would have forced a provider switch away from the model doing the reasoning. Second, [N] tokens with zero labelled relevance data — it fits in one window, so there's no knowledge to inject. Third, it can't fix what was actually broken here — page provenance and table layout — and it degrades abstention, because training on synthetic Q&A teaches the model that every question has an answer, which is the opposite of your requirement 4.5. Fourth, at n=30 my minimum detectable delta is eleven points and a realistic embedding fine-tune gains two to eight — unpowered, so any number I reported would be noise. I'd fine-tune an embedder on mined hard negatives past ~50k chunks with a 200-question gold set showing a persistent 10-point vocabulary gap. Not before."*

---

**Q4. "How do you know it's accurate?"**

> *"Here's the table. Thirty questions across four tiers, hand-verified against the rendered pages: recall@5, groundedness, and the abstention two-by-two — refusal precision and false-refusal rate, because either one alone is meaningless; a system that refuses everything scores a hundred percent on abstention. n=30, so the 95% interval is about eleven points and I say so. The unanswerable tier is the interesting one: your spec promised a Sales Handbook, an FAQ, and a Company Profile that don't exist in the assets, so questions about them are provably unanswerable and corpus-grounded. Everything I claim is absent from the Act, I proved with a grep over my own OCR and committed the grep as the test."*

---

**Q5. "Why an agent? Why not an agent?"**

> *"I don't have one, and I want to tell you why, because I planned to. I counted 121 'section N' cross-references and that looked like multi-hop retrieval. Then I went hunting for a query single-shot actually gets wrong. The classic example is section 100's eight-hour cap deferring to section 108 — except I read section 100, and the ten-hour exception is in section 100's own sentence; 108 is the overtime pay rate, a different question. Section-aware chunking already handles it. I couldn't find a failing query on my eval set, so I wrote no loop. Two documents, one permanently in context — there's no coordination problem, and an agent would be latency, nondeterminism, and something I'd be defending to you right now instead of showing you a number."*

---

**Q6. "Why is there no vector database? Isn't that the whole point?"**

> *"481 vectors at 384 dimensions is 0.7 megabytes, and exact cosine over it is 0.023 milliseconds against a two-second model call — vector search is 0.001% of my latency. I'd add pgvector with HNSW at m=16, ef_construction=200, ef_search=64 at roughly 50k vectors, where the exact scan crosses ten milliseconds, and I'd put it in the Postgres you already run rather than adding a second stateful service. Milvus needs etcd and MinIO to serve 0.7 megabytes. I'd rather show you I can size a system than that I can install one."*

---

**Q7. "Walk me through your prompts."**

> *"They're versioned markdown in `prompts/`, loaded at runtime — never inline f-strings — so the git history is the tuning curve and each revision has an eval delta next to it. Three prompts. The router is a three-way structured classification on Haiku with a confidence field; on low confidence it defaults to COMPARE because that's the strictly safer superset. The synthesis prompt encodes floor semantics explicitly — the Act sets minima, so the handbook granting thirty days against a statutory floor of roughly fifteen is compliant, not a mismatch; a naive diff reports a gap there and is confidently wrong. And it uses positive phrasing — 'state that the documents do not address X' — rather than 'do not hallucinate'. The judge prompt is hand-written and few-shot anchored on three examples from this corpus; the most valuable one is a subtly unfaithful answer with the right number and the wrong source. That's also why I didn't use RAGAS — your section 9 says I must explain my prompts, and RAGAS's faithfulness prompt isn't mine to explain."*

---

**Q8. "Add a feature. Right now."** *(the §10 live enhancement)*

> *"Sure — which layer? The tool surface is plain typed functions, so a new capability is a function plus a schema entry. The router is three labels behind a JSON schema, so a fourth route is one enum value and one prompt line. The eval is a YAML file, so a new question is three lines and CI catches the regression. Let me add a fourth route and show you the label in the logs."*
>
> *(Rehearsed enhancement, ~3 min: add `STATUTE_SECTION_LOOKUP` — router detects a bare section reference → `get_section(n)` → answer, zero search. Log the label, run the eval, show the routing accuracy hasn't moved.)*

---

### Two more you'll get, one line each

**"The spec promised six documents. What happened?"**
> *"I got two — a six-page corporate handbook misnamed `Partex-Star-Group.pdf`, whose PDF metadata title is literally 'Employee Handbook-Final', and a 181-page scanned national statute with zero extractable text. That's the first paragraph of my README, because I think how you handle that gap is part of what you're assessing. It also turned out to be the best thing about the assets: the handbook claims on its own first page that it complies with Bangladeshi labour law, and the other 181 pages are the law it's claiming to comply with. So I built the product the corpus was actually asking for."*

**"You're four days late."**
> *"I am, and I said so in my email rather than letting you find it in a timestamp. The six-to-eight hour estimate was written for the twenty-to-thirty page corpus in your spec; I received 187 pages, 97% of them scanned images with no text layer. That's not an excuse for the delay — it's the reason my README opens with measurements instead of a setup guide. What I did with the extra time is the eval harness and the full-context ablation, because those are the only things that turn my claims into numbers you can check."*

---

## Appendix — the one-paragraph README opener

> **What I actually found.** The spec describes six documents totalling 20–30 pages. The assets are two documents totalling 187 pages. `Partex-Star-Group.pdf` is not a company profile — its PDF metadata title is `Employee Handbook-Final`, and it is a landscape two-up spread whose six PDF pages carry a cover plus ten printed folios. `A Handbook on the Bangladesh Labour Act 2006.pdf` is 181 pages with **zero** extractable text — 100% scanned images, OCR'd here at build time to 498,240 characters in ~120 seconds and committed to this repo. The named HR Policy, Leave Policy, Sales Handbook, Company Profile, and FAQ do not exist. Then the useful part: the handbook states on its first printed page that its policies *"are in compliance with the applicable labor laws of Bangladesh"* — and the other 181 pages are the exact statute that claim refers to. **The corpus is a falsifiable claim plus its evidence base.** So this is not a document search box. It is an HR policy compliance assistant, and it finds real gaps: the handbook's casual leave (10 days) and sick leave (14 days) sit exactly at the statutory floors of ss.115 and 116; its annual leave (30 days) exceeds s.117 and is compliant; and it is entirely silent on the sixteen weeks of maternity benefit s.46 mandates, the eleven paid festival holidays s.118 mandates, and the 2× overtime rate s.108 mandates. Every number below comes from `corpus_stats.json`, which is generated by one committed script.",
  
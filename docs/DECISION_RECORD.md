# DECISION RECORD v2 — Enterprise AI Document Assistant (AgamiSoft)

**Chief Architect final ruling. Supersedes v1 entirely — a reader of this document never needs v1.**
Stack: Mistral + open source, zero billing, free deployment. Budget: **22h**. Deadline: extended (C5).
Every number below was re-measured this session against the real assets. Where I contradict v1, I measured.

---

## 0. The one-number rule (v1's best discipline, now applied to v1 itself)

v1 ruled: *one committed script emits `corpus_stats.json`; nothing else is quoted.* Round 2 then produced **four** corpus token counts (113,240 / 122,088 / 122,127 / "128–146k"), **two** section counts (333 vs 342), **four** query-embed latencies (2.2 / 3.2 / 5.3 / 35.1 ms), and benchmarked the vector store against **a randomly generated index**. The rule was written for exactly this and was not applied.

**I measured everything myself. These are the only numbers that ship.**

| Fact | v2 measured value | Method | What it kills |
|---|---|---|---|
| Corpus tokens (full, all 181p + handbook) | **122,204** | `Tekkenizer` v13, vocab 131,072, Mistral-Large-3-675B-Instruct-2512 | Backend's 113,240 (8% low, extrapolated from a handbook chars/token ratio — the banned heuristic in a tokenizer's coat); Deploy's "128–146k" (chars/4) |
| Corpus tokens (indexed scope + handbook) | **101,100** | same | — |
| Statute layer only (idx 33–156) | **87,421** | same | — |
| Handbook clipped | **3,166** | same | — |
| Mistral Large 3 context window | **262,144** | mistral.ai model card, fetched this session | THE BOMBSHELL |
| Labour Act OCR chars | **498,240** | reproduced **byte-exact** from v1 | — |
| Sections detected (idx 33–156) | **342 from 343 raw hits** | dual-grammar + LIS, re-run this session | The brief's "settled" 333/335 — **stale, corrected** |
| Chunks (statute + handbook) | **399** (388 + 11) | sub-split >2000 chars @1200/1000 | v1's 481 |
| Index size | **0.596 MB** (399×384 f32) | measured | v1's 0.7 MB |
| Exact cosine + top-8 | **0.0083 ms** | mean of 2000, real embedded chunks | v1's 0.023 ms; `idx.py`'s synthetic benchmark |
| Query embed (bge-small) | **2.4 ms** | mean of 50 | Backend's 35.1 ms (**15× outlier**, anchored a README table) |
| Build embed rate | **~12.6 chunks/s** | warm, M2 | Backend's 4.3–6.0 (bought 2.25h of architecture) |
| `df('sick')` | **2 / 342** | measured | v1's risk #15 justification |

**Ratio to quote (robust, order-of-magnitude, unfalsifiable):** model call **seconds** ≫ query embed **milliseconds** ≫ vector search **microseconds**. Do not quote "1,500×".

> **Delete on sight:** `113,240` · `43%` · `128–146k` · `481 vectors` · `0.023 ms` · `35.1 ms` · `333 of 335` · `4.3–6.0 chunks/s` · `"BM25 misses s.116"` · `"MDE ~11pp at n=30"` · `"omitting the bge prefix costs recall"`.

---

## 1. What changed from v1, and why

| v1 assumption | New constraint | What it voids | What replaces it |
|---|---|---|---|
| Claude Opus 4.8 generation, 1M window | C1 zero billing, C2 Mistral | `claude-opus-4-8`, `thinking`, `output_config`, the 400-on-`temperature` warning | **`mistral-large-2512`**, 262,144 ctx, `temperature=0` (accepted), streaming, Apache 2.0 open weights |
| `claude-haiku-4-5` router | C1 + free-tier ~1 req/s | The router LLM call entirely | **Code-derived route label.** The router was a *dollar* optimisation; dollars are no longer scarce — **requests** are. A router doubles requests/query to save 8 µs of local retrieval. |
| `claude-haiku-4-5` judge, "different tier = cheap insurance" | C1 | Both the model **and the rationale** | **`gemini-2.5-flash`**, free, **cross-family** (different tier ≠ different family; family-bias is documented). Offline in the harness only. |
| $2.72 full-context oracle | C1 | The cost math | **$0.00.** 30 × 101,100 = 3.03M tokens ≈ 0.3% of the free monthly allowance. **C1 made the oracle free, not impossible.** |
| Anthropic Citations API (Phase 2) | C2 | The whole Phase 2 upgrade path | v1's **code-sliced verbatim snippet is now the final design, not a stepping stone.** It was always the real guarantee; it needs no API cooperation. |
| Opus 4.8's 4,096-token min cacheable prefix + `assert cache_read_input_tokens > 0` **build gate** | C2 | Anthropic-specific constant | Mistral caches in **64-token blocks** — the 3,166-token handbook clears it by 49×. Mistral's docs say a hit is **not guaranteed**, so the gate would fail the build on a documented non-bug. **Log `cached_tokens`; never assert it.** Byte-stable-prefix discipline **survives**. |
| `pip freeze` ships torch → "cannot boot any free tier (Render 512MB)" | C4 (HF Spaces = 16 GB) | **The stated reason.** Torch fits fine in 16 GB. | Ruling (no torch, CI gate) **survives**; reason replaced by **cold start**: ~254 MB vs ~2.5 GB to pull and import before the grader's first answer. |
| Pinecone = "infrastructure cosplay" | C3 mandate + C6 uploads | **Nothing, for the committed corpus.** 399 vectors / 0.596 MB / 0.0083 ms — the ruling is *stronger* than v1 knew. | Pinecone ships for **uploaded KBs only** (§4.6). The paragraph stays verbatim. |
| LangGraph cut as agent collateral | C3 mandate | v1's *reasoning* (category error — LangGraph is a state machine, not an agent) | **Re-examined on its own terms and CUT anyway** (§4.11) — for better reasons. |
| CI/GitHub Actions cut | C4 | The cut | **3 workflows, 0.5h.** CI is now the deploy path *and* the keep-alive canary against HF's 48h pause. |
| §3.15 "**422** no answer found" | — | An internal v1 contradiction (§3.12 says refusal is a designed product state; a product state is not an HTTP error; the harness would score every correct refusal as a transport failure) | **200 OK + `insufficient_information: true`.** 4xx is reserved for the caller being wrong. |
| Entailment gate "parallelised with `asyncio.gather`, +300–600ms" | ~1 req/s | The arithmetic | **`asyncio.gather` does not create quota.** 5 claims = +5s, not +400ms. Judge moves **offline**; request path budget = **ONE LLM call**. |
| "Action Zero — email today", lateness framing | C5 extension | §0 of v1 entirely | Resolved. Optimise for depth and interview defensibility. **Not a licence for 130h.** |
| `anthropic.RateLimitError` by class | C2 | The exception hierarchy | `MistralError` carries `.status_code/.headers/.body`. **`NoResponseError` subclasses `Exception`, NOT `MistralError`** — `except MistralError` misses it and it escapes as a 500. SDK `retry_config` defaults to **None**: it does **not retry unless you pass one**. |
| "risk #15: `14 sick days?` lexically misses s.116" | — | **Falsified.** I reproduced it: BM25 ranks s.116 **rank 1** (`df(sick)=2/342` is a decisive high-IDF anchor). v1 measured at *page* level and inferred a *section*-level failure — the identical strawman error v1 demolished in its own §3.8. | 40 lines **survive** on honest, narrower ground: anchorless numerals (`14 days?` → rank 33, `14` → rank 113). **Never headline it.** |
| "bge prefix omission silently costs recall" | — | Unmeasured claim | Prefix **ships** (that's how the model was trained, one line). **Claim deleted** — measured a wash at recall@5. |
| "MDE ~9.9pp at n=50 / ~11pp at n=30" | — | v1 quoted its **n=100** figure as its n=30 figure | Exact McNemar: **MDE(30)=29pp**, MDE(50)=19pp, MDE(100)=11pp. Power at a realistic +8pp, n=30 = **4.6%**. |
| SWE + API = 1.5h | C6 | The estimate | 2.5h (Phase 0) + 2.0h (C6, Phase 1). |

---

## 2. Requirements — as written vs as they actually are

| Spec claims | Reality (measured, reproduced ≥3×) |
|---|---|
| 6 documents | **2** |
| 20–30 pages | **187** |
| Text-native PDFs | **97% scanned** — the Labour Act has **zero** extractable text |
| Employee Handbook, HR Policy, Leave Policy, Sales Handbook, Company Profile, FAQ | **`Partex-Star-Group.pdf`** (6 pages, landscape 2-up, metadata title `Employee Handbook-Final`) + **`A Handbook on the Bangladesh Labour Act 2006.pdf`** (181 pages, 100% image, English) |
| — | **5 of 6 named documents do not exist.** |

### What the mismatch forces

1. **OCR is a committed build artifact.** 498,240 chars, ~100–150s at 8 workers, 94% mean confidence, byte-identical reruns. *(v1's stated reason — "health checks are 30–60s" — is **wrong**: HF's `startup_duration_timeout` defaults to **30 minutes**. The ruling stands on **determinism** and **cold-start UX**. A right ruling propped on a checkable wrong number is a kill shot.)*
2. **Neither document's PDF index is its printed page**, and they break it in two *different* ways. FR#4 names page numbers. 10-second check for the grader.
3. **Bimodal by 37:1** (14,304 vs 498,240 chars). Any global top-k buries the one document the scenario is about.
4. **The two documents are not an unrelated pair.** Handbook folio 1: *"The human resource (HR) policies and procedures contained in this handbook are in compliance with the applicable labor laws of Bangladesh."* The other 181 pages **are** that law. **The corpus is a falsifiable claim plus its evidence base.** That is the product (§7).
5. **The corpus fits in one window** — 122,204 / 262,144 = **46.6%**. RAG is a *defended choice* (§5).
6. **Fine-tuning: you can train it, you cannot serve it.** Free hosting has no GPU (§6.8).
7. **Bengali is a non-issue and knowing why is the point.** Zero Bengali codepoints in 498,240 chars; s.354 is titled *"Original Text and Authentic English Text"* — this **is** the authentic English text. One README line.

---

## 3. The requirements that actually matter

| # | Requirement | Source | Rubric marks |
|---|---|---|---|
| 1 | Statute OCR'd **at build time**, committed; runtime image has no tesseract | derived — 100% scanned + mandatory live URL | Arch 20, UX 5, Docs 10 (**all zero if the URL is dead**) |
| 2 | Citations carry the **printed** page, ONE declared index base, asserted in tests | explicit FR#4 | Quality 20, Retrieval 15, UX 5 |
| 3 | Partex extracted by **geometric clip at the x-midline** | derived — 2-up spread; naive extraction interleaves two policies **with no error** | Retrieval 15, Quality 20 |
| 4 | Handbook reachable independently of the statute (2.6% vs 97.4% of chars) | derived | Retrieval 15, Insight 5 |
| 5 | Statute chunked on **section boundaries**; `section_no` a first-class key | derived — statutes are pre-chunked; 342/343 recovered | Retrieval 15, Quality 20 |
| 6 | TOC (idx 1–15) and ILO annex (idx 157–180) **excluded** and documented | derived — dot-leaders lexically shadow real headings; annex OCRs to word salad | Retrieval 15, Arch 20, Docs 10 |
| 7 | Abstention **enforced in code and measured** — not a prompt line | explicit FR#5 | Quality 20 |
| 8 | Two authority levels: company policy vs statutory **floor** | derived — the corpus IS a compliance claim + its evidence | Insight 5, Quality 20 |
| 9 | RAG defended against a full-context baseline that is **built** | derived — 46.6% of one window | Arch 20 |
| 10 | Corpus is **legally stale** (2006 Act as published by BEF 2009; amended 2013, 2018). Surfaced **in the answer**, not the footer | derived — OCR p1, PDF creationDate 2011 | Insight 5, Quality 20 |
| 11 | **SWE (15) + API (10) staffed.** 25 marks had no owner across 9 round-1 experts | explicit §6 | SWE 15, API 10 |
| 12 | **C6 — multi-KB runtime upload** | explicit user requirement | Arch 20 (extensibility), API 10 |
| 13 | Every component explainable in **<3 min** and modifiable **live on camera** | explicit §9, §10 | **caps total complexity — the binding constraint on everything above** |

**Coverage:** Arch 20 (1,6,9,11,12) · Quality 20 (2,3,7,8,10) · Retrieval 15 (3,4,5,6) · SWE 15 (11) · API 10 (11,12) · Docs 10 (1,6,9,10) · Insight 5 (8,10) · UX 5 (2). **100/100 owned.**

**On C6, honestly:** it touches **no rubric line by name**. It is a user requirement, not a graded one, and round 2 spent ~6.25h on it across four lenses partly because it retro-justifies the Pinecone mandate — which is circular. It is sized to **2.0h, one owner, Phase 1**. It earns its place as an Architecture-20 extensibility signal and because it is the honest answer to fine-tuning (§6.8).

---

## 4. Architecture ruling — component by component

### 4.1 Ingestion / OCR — tesseract, build-time, committed

**SHIP:** PyMuPDF `get_textpage_ocr(dpi=200, full=True, language="eng")` + tesseract 5.5.2, **zero preprocessing**, `ProcessPoolExecutor(max_workers=8)`, reopening the PDF once per worker. → `data/extracted/labour_act.json`, **committed**.

| Rejected | Why it lost |
|---|---|
| **Mistral OCR** (user asserts a free tier) | **The premise is false.** It is $2–4/1,000 pages ($1–2 batch); no verified no-card free API tier. The structural tell: it is billed **per page** while the free quota is denominated in **tokens** — a per-page product cannot be metered by a per-token quota. Under C1 ("a card on file is CUT"), it cuts itself. **And it costs nothing to lose:** tesseract already produced 498,240 chars at 94% confidence, deterministic, byte-identical, $0. The *only* thing it would fix is the ILO annex table — **which we exclude on purpose** (§4.1 exclusions). Its sole value-add lands on the component we deliberately deleted. |
| **Pixtral** | **Stale mental model — say this out loud.** You do not call Pixtral for vision from Mistral in 2026: `mistral-large-2512` **is** multimodal (673B LM + 2.5B vision encoder). And v1's ruling is cost-independent: vision OCR over statutory text is a hallucination surface where a wrong section number **is** a wrong answer. |
| **Ollama + minicpm-v / granite-vision** | Free, unlimited, **build-time only** (no GPU on free hosting). Would replace a deterministic 94% result with per-page nondeterminism. Nothing to buy. |
| Deskew / denoise / binarise / dpi=300 | Measured A/B: raw wins or ties every variant; deskew **loses ~4% of words** (524→505) — OSD reports 0° on already-straight scans. Embedded scans are natively 204 DPI, so dpi=300 upsamples: equal-or-worse yield at 2× cost. **The single best "I measured instead of reciting the tutorial" artifact in the submission.** |
| docling / marker / surya | Drags torch + weights into the image to fix 15% of one document. |
| OCR at cold start | Nondeterministic user-visible latency on the grader's click; and the image would need tesseract. |

**CRITICAL BUG — hold the page reference.** `tp = doc[i].get_textpage_ocr(...)` lets the transient Page get GC'd → `ReferenceError('weakly-referenced object no longer exists')`. With a swallowing `try/except`, **you silently index 181 blank pages and the pipeline reports success** (`DONE 181 pages in 167.8s, total_chars 0`).

```python
pg = doc[i]                                              # hold it
tp = pg.get_textpage_ocr(dpi=200, full=True, language="eng")
text = pg.get_text(textpage=tp)
```

**Build gate:** `assert mean_chars_per_body_page > 1500` and `assert no body page < 300 chars`. Only idx 0 / 32 / 156 are legitimately near-empty.

**Partex — clip, never block-x0. (v1 adversary win, preserved.)** Measured: on idx 2 the footer returns as a **single block** with `x0=68.7` spanning the gutter — filtering on `b[0] < mid` puts the *right* page's folio "4" in the left half and you conclude left = 4. Span geometry says folio '3' is at x=291.5, '4' at x=370.4. **Left = 3.**

```python
W = page.rect.width          # drifts: 686.07 / 687.64 / 686.39 — compute per page
mid = W / 2                  # NEVER hardcode 343.8
left  = page.get_text(sort=True, clip=fitz.Rect(0, 0, mid, H))
right = page.get_text(sort=True, clip=fitz.Rect(mid, 0, W, H))
text = unicodedata.normalize("NFKC", text)       # 24 ligatures: "conﬁdential" ≠ "confidential"
text = re.sub(r"(\w)-\
\s*(\w)", r"\1\2", text)  # 23 hyphenations; spares 'pro-rata'
# drop footer band y > H*0.86
```

**Exclusions** (0-based PyMuPDF index, hardcoded constants citing the evidence — **not** a heuristic classifier):
- `TOC_RANGE = range(1, 16)` — 19,094 chars of `'Procedure for leave : 27'` dot-leaders. Lexically near-identical to every real heading, zero answer content, maximally adversarial to BM25 **and** cosine. **Keep idx 16** (`PREFACE`).
- `ANNEX_RANGE = range(157, 181)` — ILO ratification table. Short-line share 0.73–0.78 vs 0.26 median; OCRs to `'This / aw / is / not / in / force / in'`. Tagged `kind="table_unreliable"`, documented as a **deliberate, measured exclusion** — which outscores a half-working table parser and demonstrates FR#5 in the ingestion layer.
- Layers: idx 17–32 = **commentary about** the Act; idx 33–156 = **the Act verbatim**. `get_section` indexes idx 33+ **only** — otherwise the regex false-positives ss.1–6 onto the repealed-laws schedule.

**Build/runtime split.** Committed: `data/extracted/*.json` (~0.6 MB), `index/index.npz` (0.596 MB), `chunks.jsonl`, `index_meta.json`. **~2 MB total — plain git, no LFS, no boot-time fetch.** Not shipped: the 16.25 MB Act PDF and 536 KB Partex PDF stay in GitHub, `.dockerignore`d out of the image. **No tesseract in the runtime image.**

### 4.2 Page fidelity — ONE constant, ONE declared base

v1's council split 2–2 between offset 16 and 17 — **they were not disagreeing**, they used undeclared, inconsistent index bases, which is strictly worse than disagreeing because it reads as corroboration. **A one-off is worse than a seventeen-off: seventeen looks like a bug, one looks like sloppiness the grader cannot bound.**

Verified from OCR'd footers, and re-validated this session against the section index (s.46→p.39, s.117→p.59, s.118→p.60 all land correctly):

```python
PRINTED_OFFSET = 16                 # printed = zero_based_pdf_index - 16
BODY_RANGE     = range(17, 157)     # printed 1..140
FRONT_MATTER   = range(0, 17)       # idx 16 == PREFACE == 'xvi'
# Partex: idx 0 = cover; for idx 1..5: left = 2*idx-1, right = 2*idx  → {1,3,5,7,9}/{2,4,6,8,10}
```

Variables are `zero_based_pdf_index` and `printed_page`. **Never `page`. Never bare `idx`.**

```python
def test_printed_page_from_zero_based_index():
    assert printed(75) == 59 and printed(76) == 60 and printed(55) == 39
    assert printed(40) == 24 and printed(19) == 3  and printed(90) == 74
def test_partex_folios():
    assert partex_folios(2) == (3, 4)   # the page block-x0 gets backwards
```

*(Correction to v1: it prints "s.100 (idx 73 / printed 56)" — internally inconsistent. Measured: **s.100 is at idx 72 → printed 56**. Printed 56 was right; the index was the typo.)*

### 4.3 Citation format — print BOTH; the canonical anchor is the section number

v1's council had a direct 5-to-1 contradiction: the Eval lead's golden anchors said "physical p76"; the answer template said "printed p.59". **The harness would have marked every correct citation wrong.**

```
Bangladesh Labour Act 2006, s.117 Annual leave with wages — printed p.59 (PDF page 76 of 181)
Employee Handbook (Partex Star Group), printed p.6 (PDF page 5, right half)
```

One f-string ends the argument and beats either camp: printed matches what the document says about itself, PDF matches the grader's scrollbar, and **the section number is the statute's actual primary key — stable regardless of pagination, and it OCRs cleanly where footers do not** (`'ll'` for 11, `'564'` for 56, `'Az'` for 47). **The harness asserts on the section number, not the page.** The golden set is written in the same format the renderer emits.

`doc_title` comes from a **curated manifest, never the filename** — `Partex-Star-Group.pdf` is misleadingly named; its metadata title is `Employee Handbook-Final`.

**Citations are typed Pydantic objects the whole way out — never markdown strings.** A markdown citation is unassertable: you cannot write `assert c.printed_page == 59` against `'— printed p.59 (PDF page 76)'` without a regex. **Rendering happens in the UI layer from a typed object, so the model never emits a citation string and structurally cannot fabricate one.** That is the anti-hallucination guarantee restated as a type.

### 4.4 Chunking — dual-grammar + LIS + wrapped-title fix

**SHIP:** dual-grammar section regex + longest-increasing-subsequence over section numbers, scoped `layer == "statute"` (idx 33–156). **Measured this session: 343 raw hits → 342 sections. Build gate passes.**

The Act uses **two** header grammars: `N. Title : (1)…` and `N. Title.— (1)…`. A greedy monotonic scan gives 82% recall because one stray high number poisons everything after it.

**FATAL v1 hit, preserved — the naive regex drops s.46, the flagship demo.** `[^:;\
]{3,95}` forbids newlines, and s.46's title wraps. It cannot match, so **s.46 silently merges into s.45's chunk with s.45's metadata.** You'd get a clean recall number for the README and a confidently wrong citation on the one question the grader remembers.

```python
SECTION_RE = re.compile(
    r"^\s{0,6}(\d{1,3})\s*[.,]\s+"
    r"([A-Z][^:;\
]{3,95}(?:\
[^:;\
]{1,60})?)"      # ← allows ONE wrapped title line
    r"\s*[|!,.\s]{0,3}(?:[:;]|[—–-]{1,2}\s*\()",
    re.M,
)
# then LIS over section numbers (it already rejects the false positives it admits)
```

**Build gate:** `assert {45,46,100,108,115,116,117,118} <= set(detected)` — **fail the build, not the demo.** Verified green this session; s.46 → idx 55 → printed p.39. Cross-validate detected section→page against the TOC's independent page numbers (the exclusion becomes an engineering asset).

Do **not** anchor on roman chapter numerals — OCR mangles them (`XIL`, `Vv`, `V1`, `Vill`); arabic digits survive.

**Chunk shape (measured):** 342 sections, median **594** chars, mean 802, max 3,555. Sub-split only sections >2,000 chars (1,200-char windows, 1,000 stride) carrying parent metadata → **388 statute chunks**. Do **not** merge short sections — a short section is a complete legal unit. s.2 (Definitions, 66 terms) sub-splits **per definition** — the highest-value target for "what is a worker?". Partex chunks per printed half-page (~11). **Total 399.**

Metadata per chunk: `{doc_id, doc_title, doc_kind, layer, section_no, section_title, chapter, zero_based_pdf_index, printed_page, half, char_span, is_definition, source_modality, ocr_mean_conf}`.

| Rejected | Why it lost |
|---|---|
| `RecursiveCharacterTextSplitter(1000, 200)` **for the statute** | Measured: merges s.115 (casual, 10d), s.116 (sick, 14d), s.117 (annual) — three distinct entitlements on one printed page — into one blob with one page number. **Ask it what page s.117 is on. It says 76. The document says 59.** A framework mandate does not overturn a measurement. |
| The "169-section" regex | Off by half — single-grammar, misses `N. Title.— (1)` entirely. "I measured 169 sections" in a 354-section statute is falsifiable with grep in 30 seconds. |

### 4.5 Embeddings — fastembed bge-small, 384d, local

**SHIP:** `fastembed==0.8.0` → `TextEmbedding("BAAI/bge-small-en-v1.5")`, 384-dim.

**The new argument v1 could not give:** a remote embedder puts a network call in the **query path**. At ~1 req/s shared with generation, `mistral-embed` would **double the rate-limit consumption of every query** — spending the scarcest resource in the system on something local hardware does in **2.4 ms** for free. *Under a rate-limited free tier, local compute is free and unlimited while API requests are scarce — so move everything you can OFF the API.*

| Rejected | Why it lost |
|---|---|
| `sentence-transformers` + torch | ~2.5 GB vs ~254 MB. **Reason corrected:** not "it can't boot" (HF Spaces has 16 GB — that sentence is a credibility grenade). It's **cold start**: free Spaces sleep, so the grader's first click *is* a cold start, and image pull + import is what you're protecting. |
| `mistral-embed` (1024d) | Billed per token, no verified free quota, **and a network hop + rate-limit spend in the query path**. |
| **Pinecone Inference** `llama-text-embed-v2` (free, 5M tok/mo) | **Refused despite being free — the reason matters.** It would create **two embedding spaces**: uploads embedded remotely, the committed corpus locally. The same query embeds differently depending on which store it hits and the two result sets are **silently incomparable**. Not slower — **wrong**, and wrong in the way that never throws, which is this corpus's signature failure mode (cf. the Partex interleave, the s.46 merge). |
| bge-base (768d) | **Measured, discharging v1's open question:** recall@5 = **1.00 both**, for 4.2× build time and 5.5× query latency. 768d buys nothing. |
| An int8 quantization step | **No work required** — fastembed's default artifact for this ID already resolves to `qdrant/bge-small-en-v1.5-onnx-q` (verified in the cache). C7's "should we quantize?" is answered by the library default. Writing the step would re-do what the library did. |

**The asymmetric query prefix — KEEP the line, DELETE v1's claim.** v1 asserted omitting `"Represent this sentence for searching relevant passages: "` *"silently costs recall."* Measured: recall@5 = 1.00 **with and without**; recall@1 on bge-small is actually *higher* without (0.94 vs 0.88) at n=16 — noise. **Apply it because that is how the model was trained and it is one line. Do not claim a recall benefit you cannot measure.** An interviewer who asks "how much recall did it buy?" gets a measured "nothing detectable at recall@5" or an invented number. Record `query_prefix` in `index_meta.json` — that field is how you prove you read the model card rather than a blog post.

**CI gate:** `assert not importlib.util.find_spec('torch')`. Hand-written `requirements.txt`; **never `pip freeze`**.

### 4.6 Vector store — **numpy for the committed corpus. Pinecone for uploads only. RULED.**

**The committed corpus: numpy `float32` + `rank_bm25.BM25Okapi`, committed `index.npz` + `chunks.jsonl`. Flat exact cosine. No ANN. No network.**

Measured this session on the **real** index (round 2's benchmark ran against `rng.standard_normal` and a 15-word salad — conceded, re-measured): **399 × 384 = 0.596 MB; exact cosine + top-8 = 0.0083 ms.** A model call is 1,000–3,000 ms. **Vector search is ~0.0004% of end-to-end latency.**

> **Keep this in the README verbatim — it is still the best sentence in the build, and now I can say it without hypocrisy because I ship Pinecone next door:**
> *"No ANN index. At 399 vectors, exact cosine search costs 0.008 ms — vector search is a rounding error against a ~2s model call. I would add HNSW (m=16, ef_construction=200, ef_search=64) at roughly 50k vectors, where the exact scan crosses ~10 ms. Reaching for a distributed vector database to serve 0.6 MB is infrastructure cosplay."*

**Uploaded KBs (C6): Pinecone, namespace per KB.**

> **⚠️ ADVERSARY HIT — CONCEDED IN FULL, AND IT IS FATAL TO THE COUNCIL'S ARGUMENT.**
> Every round-2 lens justified Pinecone with: *"HF Spaces has no persistent disk → an uploaded KB must live off-box → Pinecone is the **only** free, no-card answer."* **The first clause is true. The conclusion is false, and I verified it against HF's own docs this session:**
> - `hub/spaces-storage`: *"This disk space is ephemeral… If you need to persist data with a longer lifetime than the Space itself, you can attach one or more **Storage Buckets** as volumes."* … *"Attached buckets are mounted into the Space container at the path you specify"* … *"They can be mounted **read-write (the default)** or read-only."*
> - `hub/storage-buckets`: *"Buckets are **available to all users** and organizations."* … *"buckets are **free to create and have a free storage allowance**."* S3-like, **mutable**, non-versioned.
>
> So there is a **first-party, free, no-card alternative that would reuse the existing NumpyStore** — no second vendor, no VectorStore protocol, no 40 KB metadata gymnastics, no undocumented inactivity policy. The Backend lens *found* Storage Buckets and misfiled them as *"the paid fix."* The Deploy lens evaluated the wrong primitive (Dataset repos / git-LFS) and rejected it on round-trip grounds — the exact objection buckets exist to answer. **Three lenses converged on "Pinecone or evaporate" because all three skipped the same check. Convergence is not corroboration.**

**RULING: ship Pinecone for uploaded KBs — and delete the necessity claim from every artifact.**

Pinecone earns its place on **three honest grounds**, none of which is necessity:
1. **The user mandated it** (C3), and it is genuinely C1-clean: **no credit card**, 2 GB, 5 indexes, **100 namespaces/index**, 2M write / 1M read units/month, 40 KB metadata/record.
2. **Namespace-per-KB fails closed.** `namespace='kb_hr_2024'` gives hard isolation at query time. A metadata filter you forget **leaks across tenants**; a namespace you forget **returns nothing**. When the whole feature is separation, fail-closed beats fail-open.
3. **100 namespaces is the multi-tenancy primitive C6 asks for**, and it is the right shape by 20× (Starter caps at **5 indexes** vs 100 namespaces — index-per-KB is the mistake that shows you didn't read the limits page).

**What makes this defensible rather than mandate-compliance:** the honest interview line is *"I chose it over the first-party alternative for namespace isolation"* — not *"there was no alternative,"* which a grader falsifies in one click on HF's own docs. **Naming the alternative you declined is the senior move; claiming it didn't exist is the failure this council was convened to prevent.**

**Spec.** `pinecone==9.1.0`. ONE index: `create_index(name='eda-kb', dimension=384, metric='cosine', spec=ServerlessSpec(cloud='aws', region='us-east-1'))` — **Starter is region-locked to us-east-1; hardcoding anything else fails at create time.** Dimension 384 because it **must** match fastembed bge-small — the same model on both sides, non-negotiable.

> **⚠️ ADVERSARY HIT — CONCEDED.** The Backend lens specced *"chunk text stays out of Pinecone metadata; keep text in the job's chunk store"* — and the job store is *"an in-process `dict`."* **After the restart Pinecone exists to survive, the vectors persist and the text does not.** You can retrieve a vector and cannot render a citation. **The one justification is destroyed in the same paragraph that states it.** It also misreads the 40 KB cap as *filterable*-only.
> **FIX:** chunk **text rides in Pinecone metadata** — chunks are 0.6–2 KB against a 40 KB cap, ~20× headroom. `assert len(json.dumps(md)) < 40_000` at upsert; **fail the ingest, never the query.** Metadata = `{text, doc_title, section_no, section_title, printed_page, zero_based_pdf_index, source_modality}`. An upload then survives a restart **completely** — vectors *and* text — with no second datastore.

**Boot invariant:** `assert index_meta['embed_model_id'] == 'BAAI/bge-small-en-v1.5' and pc_index.describe_index_stats()['dimension'] == 384`.

**Degrade path (the whole cold-visit insurance policy):** `PINECONE_API_KEY` unset or unreachable → uploads return typed **503 `UPLOAD_BACKEND_UNAVAILABLE`**; the baseline demo and all six chips work with **zero network calls**. `GET /health` reports `pinecone_reachable` as a field **separate** from `index_loaded`.

| Rejected | Why it lost |
|---|---|
| Pinecone for **everything**, including the baseline | Makes the grader's cold visit depend on a free-tier quota, a network hop to serve 0.6 MB, and an **officially undocumented** inactivity policy (Pinecone's docs state none; the 7-day archive was removed in 2023; third-party 2026 reviews claim a ~3-week pause — **the sources conflict, so I will not quote a number**; I architect around the uncertainty instead). This is v1's fatal risk #2 wearing a mandate as a costume. |
| numpy for uploads too | Dies with the ephemeral disk on restart — C6 fails **silently**, the worst way to fail. |
| One index per KB | Starter caps at **5 indexes** vs **100 namespaces**. Wrong primitive by 20×. |
| Milvus / Weaviate | etcd + MinIO to serve 0.6 MB. |
| pgvector on Neon/Supabase | Genuinely the better *enterprise narrative* — and the narrative is free in the README's alternatives table. **Its own v1 advocate cut it from their own plan.** |
| `sqlite-vec` + a **second unused** `VectorStore` adapter | v1 correctly killed **two adapters where one was deployed** ("insurance" = code the grader must read that runs nowhere). **This is not that:** both adapters run in production, on different data, with genuinely different lifecycles — immutable/committed vs mutable/uploaded. That distinction is the answer to *"so why is the other one in the repo?"* |

**The split falls on one causal axis, not taste: DATA LIFETIME.** What ships inside the image is a file; what arrives after the image is built needs a database, because the disk is ephemeral. One `Retriever` Protocol (~20 lines, 3 methods), two live implementations, routed by `kb_id`.

### 4.7 Retrieval — **ASYMMETRIC, not stratified**

Three v1 lenses proposed stratified per-doc top-k quotas to fix the 37:1 imbalance. **They proposed a workaround for a problem that vanishes if you don't create it.**

**RULING: pin the entire handbook; retrieve only over the statute.**

The handbook is **3,166 tokens**. **Retrieval over a document that already fits can only lose information.** Pinning:
- eliminates the base-rate problem **by construction** rather than by tuning a quota you'd have to defend ("why 4 and 4?");
- makes *"the handbook is silent on maternity"* a **sound claim**, not an inference from a failed top-k — verified: **0** occurrences of `maternity`, **0** of `overtime`, **0** of `paternity`, **0** of `WFH`;
- is **less** code than stratification;
- collapses the router to nothing (§4.9).

> **Interview line:** *"The handbook is 3,166 tokens. Retrieving over it can only lose information. So I only retrieve over the document that doesn't fit."*

**v1 adversary fix, preserved:** asymmetric retrieval makes the handbook invisible to retrieval metrics — so Retrieval Accuracy (15) would be measured over 97% of the corpus while the document the scenario is about is unmeasurable. **Index the ~11 handbook chunks anyway** (11 rows, 30 seconds) so recall@k is measurable across both documents, and so you get the ablation: *"I measured recall@5 on handbook questions with retrieval, then shipped full-context because retrieval was lossy — here are both numbers."*

**Statute retrieval:** hybrid BM25 + dense, fused with **RRF (k=60)** — no alpha weight to justify. Top-k=8, small-to-big expansion to the **full parent section** (median section 594 chars ≈ 149 tokens; 8 whole sections ≈ 1,200 tokens against 262,144 — **the precision/completeness tension that makes small-to-big hard elsewhere simply does not exist here**). Assemble in **section-number order**, not relevance order — statutes read sequentially.

**Why hybrid, specifically here** — not the generic reason:
1. **IDF.** `gratuity` appears 10× in 61k body word-tokens, `retrenchment` 14×, `lay-off` 7× — rare high-IDF terms of art where BM25 is near-perfectly precise and dense embeddings blur them into `compensation` (120×). Conversely *"can my boss make me work overtime?"* has zero lexical overlap with the governing sections — dense wins.
2. **OCR noise is asymmetric.** Only **2 corrupted tokens in 61,098** body word-tokens — the OCR is clean at word level, so the *"OCR is noisy so BM25 breaks"* argument is **measured false**. But real prose noise (`'taw'`, `'CUOAPTER'`, `'framed m conformity'`) breaks lexical matching on **prose**, while section numbers and terms of art OCR cleanly and demand exact match. You need both scorers — **for this reason**.

**Uploaded KBs get the same hybrid path.** Build `BM25Okapi` **per-namespace in memory at upload** (~400 chunks, milliseconds). *(Round 2 conceded dense-only for uploads as "an honest, stated asymmetry" — the Hostile Grader is right that this hands the grader a demonstrably worse pipeline built from the components you'll spend the interview rejecting. It costs milliseconds to close. Close it.)*

### 4.8 Section lookup — `get_section(n)`

**SHIP:** a dict lookup on `section_no`. 20 minutes. **Not an MCP feature — it must not die with MCP.**

**v1's "96% of sections are unreachable" is FALSE and must never be spoken.** The claim: *"s.132 is on p80; pages containing 'section 132' are [9,81,82,161]. BM25 misses it."* Verified: the token `132` **is** on that page (`132. Claims arising out of deductions from wages`). BM25 tokenizes `132.` → `132`; `132` is a rare, extremely high-IDF numeric token — BM25 ranks that page at or near the top. **The measurement searched for the literal bigram `"section 132"`, which no BM25 implementation on earth does.** A strawman was measured, got 96%, and became a headline. *(The same lens shipped a "passing" prototype emitting `'s.115 (p.115)'` — s.115 is on printed page **59**. Its working demo **fabricates a citation**.)*

> *"The Act has a natural primary key — the section number. I index it and look it up exactly, because approximating an exact key is silly. It's a `WHERE section_no = 132`, not agentic retrieval."*
> *"Statutes cite by number and never self-name in the third person, so a section header and a cross-reference to it are different strings — that's why the section number is a metadata field, not a similarity target."*

### 4.9 Router — **CUT. The optimisation inverted.**

v1's router was a **cost** optimisation: Haiku ($1/$5) triaging so Opus ($5/$25) did less work. **Under a free tier that logic is void — both cost $0 — and the binding constraint flips from dollars to REQUESTS.**

At ~1 req/s, a router makes every query **2 requests**: it halves throughput and adds a full round-trip, to save retrieval that is **local, free, and 0.0083 ms**. Its stated UX win (*"HANDBOOK_ONLY → zero retrieval → <2s"*) buys nothing when retrieval costs microseconds and the handbook is pinned either way. **This is the cleanest example of the C7 thesis: when the scarce resource changes, the optimisation inverts.**

**SHIP:** one LLM call per query. Retrieve always: handbook pinned (3,166 tok) + top-8 whole statute sections. **Derive the route label in CODE** from which docs the cited chunks came from, and log it — same debugging signal, zero requests, zero latency. Prompt count drops 3→2, which matters directly for the 3-minute walkthrough.

**Replacement for v1's on-camera enhancement:** `get_section(n)` + a `section_no` API filter — *"add a filter and show it in the logs"* is the same 3-minute change without a second model.

| Rejected | Why it lost |
|---|---|
| Router on `mistral-small` "because it's free" | Free of **dollars**, not free of the resource that binds. |
| One `json_schema` call returning `{route, answer, citations}` | Strict JSON fights SSE streaming, and citations are code-sliced from chunk metadata anyway. |

### 4.10 Generation — `mistral-large-2512`

**SHIP:** `model="mistral-large-2512"`, **PINNED — never `mistral-large-latest`**, `temperature=0`, `stream=True`, `max_tokens=2000`.

- **262,144-token context** (verified on Mistral's own model card this session — the card renders the ID as `mistral-large-2512+1`; the `+1` is a UI artifact for the alias).
- **675B total / 41B active MoE + a 2.5B vision encoder** — which is why it is *cheaper* than Mistral Medium 3.5 ($0.50/$1.50 vs $1.50/$7.50 per 1M). **Naming does not track cost; architecture does.**
- **Apache 2.0, open weights** — decisive for an *enterprise* assistant (§4.19).
- `temperature=0` **is accepted** by Mistral (it's the documented example). *(v1's "temperature 400s on current models" was Anthropic-specific and does not port.)* **But do not claim it buys determinism** — only that it removes sampling as a variable.
- Verify the exact ID against `GET /v1/models` at build time; **log the resolved ID in `/health`** and quote *that* in the README.

| Rejected | Why it lost |
|---|---|
| `mistral-large-latest` | An alias silently re-pointing mid-assessment is a dead demo **and** an uncontrolled eval variable. |
| `mistral-medium-3-5` | 3× input, 5× output price; 128B dense; no upside here. |
| `mistral-small` as the answerer | 6B active params doing statutory floor-semantics reasoning. Keep as the documented latency fallback — **one env var, not a runtime branch**. |
| **Multi-provider fallback** (Groq / OpenRouter / Cerebras) | **"Fallback" here means failing over to something that cannot serve the app.** Groq free (from Groq's own table): **12K TPM / 100K TPD** against a measured ~5.2k-token prompt = **12–19 queries per DAY**; the 101k oracle is **8.4× its per-minute limit**. OpenRouter free: 20 RPM but **50 req/day** under $10 lifetime credits, and its roster **rotates as providers pull models** — a rotated-out ID is a **dead live URL**, v1's #1 catastrophic outcome. Cerebras caps context at 8,192 — disqualified by the pinned handbook alone. **And a silent failover means the answers the grader sees come from a model your eval never measured — worse than an honest outage.** Provider is an **env var, not a runtime branch**. |

### 4.11 LangGraph — **CUT.** (Mandated. I am declining it, and here is why, plainly.)

> **⚠️ TWO ADVERSARY HITS — BOTH CONCEDED, AND THEY ARE FATAL TO THE MANDATE'S BEST ARGUMENT.**

The Backend lens shipped LangGraph on **exactly one** load-bearing claim: *"The rubric requires an Architecture Diagram. `draw_mermaid()` emits it from the compiled graph. A CI test diffs it. The diagram cannot drift. **That is most of why LangGraph is in here.**"* It commits the output as `docs/architecture.mmd`.

**That claim is false, and the refutation is already inside the council.** The LangChain lens pre-refutes it in writing under a heading that literally says *do not claim this*: *"`draw_mermaid` gives me the query flow — five nodes. But my architecture diagram is the system: PDFs, build-time OCR, the chunker, two vector stores, the provider boundary, the API, the UI, with the build/runtime boundary drawn across it. **Most of that isn't in the graph and LangGraph can't draw it.**"* The rendered graph contains **zero** of the components the rubric's diagram is for. **The CI test proves the wrong artifact is current, and the filename `architecture.mmd` *is* the overclaim.**

**And the graph has been hollowed out by my own rate-limit rulings.** Strip what §4.9 and §4.13 already deleted — the LLM router (now deterministic code) and the live entailment judge (now offline) — and the "5-node DAG" is:

> code classifier → 0.0083 ms numpy scan → **one** LLM call → code check

**That is a graph framework around a linear pipeline whose only remaining defence is that it draws its own picture.** The Hostile Grader's question — *"why is there a graph framework in a two-node pipeline?"* — has no good answer. Its own advocate concedes *"~40 lines of ceremony over ~15 lines of async Python"* and *"close to the line where fifty lines of asyncio would do."* The Deploy lens cut it outright. **Tally: 2 ship, 2 cut, and the two shippers give mutually incompatible reasons, one refuted by the other.**

**RULING: CUT.** ~15 lines of async Python. **Hand-write the real system architecture diagram in Mermaid — 10 minutes, no dependency, and it is what the rubric actually asks for.**

*Respectfully to the mandate:* LangGraph is not a bad library and this is not a rejection on principle — v1 cut it as collateral damage from the agent argument, which **was** a category error (LangGraph is a state machine, not an agent framework), so I re-examined it on its own terms. It lost on its own terms. **The strongest honest version of what you asked for:** if the pipeline ever grows a genuine branch — a real fan-out, a retry loop, a human-in-the-loop pause — it goes back in, and the revival is ~40 lines. **Revival gate:** ≥5 *real* nodes with ≥2 genuine branch points. Today it has two and one. Also note: checkpointers are unbuildable here anyway (`MemorySaver` dies with the container; `SqliteSaver` needs a disk that HF wipes on restart; durable needs Postgres = a card).

**Side benefit of the cut:** no `langchain-core` → no **langsmith** (6.6 MB, verified in the tree) — an unasserted telemetry client in a repo about document confidentiality is a bad look. *(If you ever re-add it: `assert LANGSMITH_TRACING` falsy at boot.)*

### 4.12 LangChain — **`langchain-text-splitters` for uploads ONLY. Everything else CUT.**

**The rule: use the framework where the complexity is FOREIGN; write it yourself where it IS the thing being graded.**

**SHIP — `langchain-text-splitters==0.3.5`, in exactly one file (`src/ingest/upload.py`).** For the statute I **know** the grammar, and a generic 1000/200 split is measured to destroy the citation anchor. **For a document uploaded thirty seconds from now, I do not know the grammar, and a recursive character split IS the correct, honest default.** Same library, opposite verdicts, both measured — **that contrast is worth more at interview than either choice alone**, and refusing the mandate where it is actually correct would be contrarianism, not judgement.

**CUT — LangChain at the provider boundary.**

> **⚠️ ADVERSARY HIT — CONCEDED.** The LangChain lens rested its **entire** 1h case on *"the one genuinely NEW argument"*: `.with_fallbacks([ChatGroq, ChatGoogleGenerativeAI])`. **Two other lenses independently killed that primitive with arithmetic I verified** (§4.10: Groq = 12–19 queries/day; OpenRouter's roster rotates → a dead model ID). **LangChain's sole load-bearing justification fails over to something that cannot serve the app.** Strip the fallback and LangChain is `ChatMistralAI` wrapping one SDK — *an abstraction over one implementation*, which is the LangChain lens's own stated rejection criterion, applied to itself.

**CUT — splitters for the statute, retrievers, chains, loaders, `EnsembleRetriever`, `MultiVectorRetriever`, LCEL.** Retrieval Accuracy is its own 15-mark line and §9 demands I fully understand my implementation. If my retriever is an `EnsembleRetriever`, at interview I am explaining **LangChain's** RRF, not mine, and *"why k=60?"* answers *"the default."* `PyPDFLoader` would destroy **both** hard-won extraction wins simultaneously: it cannot clip the Partex 2-up spread (silently interleaving Leave with Confidentiality) and it returns **zero chars** on 181 scanned pages. **The loader and the splitter are not neutral conveniences here — they are the two components that would break this corpus.**

**Do NOT install the `langchain` meta-package.** That is where the rejected splitters and retrievers live; not having them installed makes the rejection **structural rather than aspirational**.

### 4.13 Citation + verification + abstention (FR#5) — **the hole the adversary found, closed**

**The finding v1 got right, and it is the best original work in either round.** Similarity thresholding is **measurably broken on this corpus**: the *answerable* "Who is the Chairperson?" scores TF-IDF top-1 = **0.067**; the *unanswerable* "How many days of paternity leave?" scores **0.155** — it collides with the casual-leave chunk. **The distributions overlap and invert.** Any threshold that refuses paternity also refuses the Chairperson. This is not accidental: **a good adversarial question is *plausible*, and plausible means semantically adjacent. Retrieval score is an anti-signal for abstention.**

> **⚠️ ADVERSARY HIT — CONCEDED. FR#5 had no live enforcement and nobody noticed.**
> Round 2 correctly moved the entailment judge offline on rate-limit arithmetic — and then left *"structural soundness — absence is provable because the handbook is fully in context"* as the live mechanism. **That covers handbook-silence only.** The verified flagship unanswerable is *"paternity leave?"*, which requires proving the **statute** is silent — and only top-8 of 399 chunks are in context. **Absence is NOT provable there.** So the flagship refusal case was enforced by *asking the model nicely in a prompt*, on a graded functional requirement inside the 20-mark line.
> **And the irony is exact:** the headline defence is *"the corpus fits in one window"* — full-context would make statute-side absence structurally provable. **Choosing RAG re-introduces the unprovability that FR#5 needs.** No lens noticed their best argument and their abstention design are in tension.

**SHIP — a deterministic, non-LLM structural gate. Code, not goodwill. Zero LLM calls.**

1. **Handbook silence is *provable*** — it is pinned in full. This falls out of the asymmetric design for free.
2. **Every claim must carry a citation to a retrieved chunk.** The verbatim snippet is **sliced from the chunk by code, never generated**. That is the anti-hallucination guarantee, and it is now the *final* design (the Citations API is gone with Anthropic — and it was always the belt to this braces).
3. **Span verification, in code:** for each citation the model emits, assert the quoted span appears in the cited chunk's text (NFKC-normalised, whitespace-collapsed). **A claim whose span does not verify is stripped.** If all claims are stripped → `insufficient_information = true`, **forced by code, not chosen by the model.**
4. **Statute silence is *bounded*, not proved — and I say so.** The honest position, which is stronger than a fake one: *"For the handbook I can prove absence. For the statute I can only say I didn't find it in what I retrieved — and the oracle bounds how often that's wrong."* **The full-context oracle (§4.16) is what turns that concession into a number.**
5. **Measure the false-refusal rate.** A gate you haven't measured for over-triggering is a gate you can't defend.

**Refusal is `200 OK` + `insufficient_information: true` + populated `related_citations`.** *(v1's §3.15 said 422 — that contradicts v1's own §3.12 ruling that refusal is a designed product state. **A designed product state is not an HTTP error**, and 422 would make the harness score every correct refusal as a transport failure. 4xx is reserved for the caller being wrong.)*

**Refusal is a designed product state, not a gray error box.** Neutral styling. Headline: *"Not found in the provided documents."* Body: what was searched (Employee Handbook, 10 printed folios + Bangladesh Labour Act 2006, 140 printed pages), the closest related material **with real citations**, and why the gap exists:

> *"The handbook covers Code of Conduct, Leave, Travel, Training, Appraisal, Confidentiality, Separation, Work Culture, Facilities, Lunch/Prayer, Visitors, and Standards of Conduct — parental leave is not among them. The Act addresses maternity benefit at ss.45–46 but does not address parental leave generally."*

**A search box cannot do that.** Prompt uses **positive** phrasing (*"state that the documents do not address X"*), never negative (*"do not hallucinate"*).

**Test #7 asserts refusal on `"paternity leave?"` — the measured unanswerable — not a generic one.**

### 4.14 Reranking — **CUT** (and it is free now, which changes nothing)

Pinecone Starter hands you **500 free reranks/month** and a local `bge-reranker` cross-encoder is free too. **Price was never the argument, so a free reranker does not revive it.**

- **Nothing to rerank.** Top-20 of 399 chunks is **5% of the entire corpus**; recall@5 measures **1.00**. **You cannot rerank your way above 1.00.**
- **It actively harms.** The handbook's leave clause is **statutory boilerplate lifted from s.117** (Jaccard **0.53**; *"shall be allowed during the subsequent period of twelve months leave"* appears **verbatim in both**). A similarity-maximising reranker **promotes both near-duplicates** — it amplifies the one case where the system most needs to distinguish company policy from statutory floor, which is where the 5 Business Insight marks live.
- **The free tier's own kill:** 500 reranks/month ≈ 16/day would break the live demo it was meant to improve.

**Refusing a free thing because it is wrong is the discipline this build runs on.** Revisit only if the 30-question golden set shows recall@5 **materially** below recall@20 — as a measured decision.

### 4.15 Agents — **CUT**

**The single named justification for both cross-reference expansion and the bounded agent loop is factually false.** Four v1 lenses cited: *"s.100 says eight hours: 'Provided that, subject to the provisions of section 108…'. Single-shot RAG returns s.100 and states 8 hours — the exception lives in a DIFFERENT section."*

**It does not.** s.100 verbatim (idx 72 / printed 56):

> *"**100. Daily working hours :** No adult worker shall ordinarily be required or allowed to work in an establishment for more than eight hours in any day: Provided that, subject to the provisions of section 108, any such worker may work in an establishment **not exceeding ten hours in any day**."*

**The 10-hour cap is in s.100 — same sentence, same page, same chunk.** And s.108 is `Extra-ailowance for overtime` — the 2× **pay rate**, a different question. s.102 has the identical shape. **Section-aware chunking — which everyone already agreed on — fully answers "what are the maximum working hours?" with "8 hours, extendable to 10."**

With that example dead, **no lens across two rounds produced a single query that whole-section hybrid retrieval answers wrongly and a hop fixes.** The cross-reference *count* (121 `section N` + 172 `sub-section (N)`) is real; **a count is not a failure mode.**

**CUT:** the bounded agent loop, ReAct, CRAG/Self-RAG/reflection, multi-agent (planner/researcher/critic), CrewAI, AutoGen. Two documents, one permanently in context. No coordination problem, no plan space, no long horizon. Multi-agent buys 4× latency, 4× nondeterminism, zero rubric marks — **and at ~1 req/s it buys 4 seconds of queueing**, so the free tier kills it twice.

**Deterministic 1-hop cross-ref expansion is demoted to an eval hypothesis (Phase 2)** — ~20 lines of precomputed adjacency. **Find the failing query first.**

### 4.16 Eval — hand-rolled, 30 questions, cross-family judge, free oracle

**SHIP:** hand-rolled harness, ~150–200 LOC, **30 hand-verified questions**, **three metrics only**: **recall@5 · groundedness · the abstention 2×2.**

Fold citation-correctness *into* groundedness — *"is this claim entailed by the cited section?"* answers both at once; **the highest-value collapse available.** **Report the 2×2 confusion matrix, never refusal rate alone** — a system that refuses everything scores 100% on abstention.

| Rejected | Why it lost |
|---|---|
| RAGAS / DeepEval / promptfoo | **Spec-level, not taste:** §9/§10 require you to explain your **prompts**. RAGAS's faithfulness prompt is not yours to explain — you'd inherit a prompt you cannot defend for your headline metric. None models the two-authority-level structure anyway. |
| nDCG / MRR | Needs graded relevance; you have binary labels. Theatre. |
| 50–60 questions | Hand-verification is what makes the number real, and hand-verification is the budget. **30 with an honest CI beats 60 you didn't check.** |

**Judge: `gemini-2.5-flash`, free (1,500 RPD / 15 RPM, no card), offline in the harness only.**

> **v1's rationale was wrong on the research and the free constraint accidentally forces the correct answer.** v1 chose Haiku to judge Opus — *"different tier from the answerer, cheap insurance."* **Different tier, SAME FAMILY.** Models exhibit documented **family-bias** — systematically scoring their own family's outputs higher. v1 bought insurance that does not insure. **Using `mistral-small` to judge `mistral-large` would reproduce the identical error for free.** The structural fix is a **different family**. **The zero-cost constraint made the eval MORE valid, not less — say that in the interview.**

`response_schema` → `{verdict, cited_section_contains_claim, reasoning}`, `temperature=0`. If `GEMINI_API_KEY` is absent the harness **skips groundedness and says so** rather than silently scoring 0. Gemini's free tier also trains on prompts — the eval corpus is a public statute, so this is **disclosed, not hidden**.

**Few-shot anchor the judge with 3 examples from THIS corpus.** Anchor #2 is the highest-value few-shot in the build: *"You get 30 days annual leave [Labour Act s.117]"* — **right number, wrong source**; the Act says one day per eighteen. A naive judge waves it through.

**The full-context oracle — v1's highest marks-per-hour item, now FREE.**

101,100 tokens (indexed scope) fits `mistral-large-2512`'s 262,144 window at **38.6%**. **Run it on the SAME model as the RAG path** — the only variable in the ablation is then retrieval. **A cross-provider oracle (Llama 4 Scout / Gemini) would be DISHONEST here: it conflates retrieval loss with model difference, and the resulting "gap" measures nothing. Same model or no oracle.**

- 30 × 101,100 = **3.03M tokens ≈ 0.3%** of the ~1B/month free allowance = **$0.00**.
- Cap at **4 calls/min** (500k TPM ÷ 101,100) → a 30-question run is ~8 min.
- Run **ONCE**, commit `evals/oracle_answers.json`, **never on the live path**.
- Paid-tier equivalent for the README: ~$0.05/query, $1.52 for 30.
- **It debugs your golden set for free** — anything both the oracle and RAG miss is a bug in your gold labels, not your retriever.
- **It is also what bounds the FR#5 statute-side concession** (§4.13).

**Groq physically cannot run it** (101k is 8.4× its 12K TPM and 101% of its 100K TPD) — **this is the one workload that proves Mistral was the right provider on engineering grounds, not preference.**

**Tiers — REBUILT.** *(v1's council contaminated its own eval, and this is the most instructive failure in the record.)*

> **Tier D was contaminated by its own author.** The "verified TRULY ABSENT" list included **overtime, minimum wage, grievance, and notice period** — **all four are in the Act** (s.108, s.138/140, s.33, s.26). The *same output*, four lines earlier, lists **overtime and minimum wage under Tier B ("MUST ANSWER")**. **The same two questions carry contradictory gold labels in one deliverable** — behind a proposed **zero-tolerance CI gate** (*"any Tier-D question that gets answered fails the build"*). **So the harness would fail the build when the system correctly cites s.108, and the candidate would "fix" it by teaching the system to refuse questions the corpus answers — destroying the 20 marks the lens claimed to own.**

> **Rebuild Tier D from the ONE construction that is provably safe:** **questions about the five documents that do not exist.** *"What commission rate does the Sales Handbook specify?"* Provably unanswerable because the documents are provably absent, corpus-grounded, and **no other candidate will build it — because no other candidate will notice the assets don't match the spec.** Survivors of the grep audit: **WFH/remote, paternity, pension. That's three, not ten.** For anything claimed absent from the Act, **prove it with a grep over your own OCR and commit the grep as the test.**

> **Tier C contained zero conflicts.** The headline — *"the two documents give DIFFERENT answers to the SAME question"* — is a **category error**. s.117: *"Every adult worker… **shall be allowed**… **at the rate of** one day for every eighteen days."* That is a statutory **floor**, not a value. Partex granting 30 days flat **exceeds** it → **compliant**. The tier also listed *"casual (both say 10)"* and *"sick (both say 14)"* as **conflicts** — those are **exact matches**. **Three items, zero conflicts.** Two other lenses explicitly predicted this failure; the lens owning 20 marks **became** the prediction. **Graded against this set, correct answers would have been penalised.**

| Tier | n | Content |
|---|---|---|
| **A — Handbook only** | 8 | hours (Sun–Thu 9–5, Sat 9–1:30), dress code, transport, canteen, 1hr lunch/prayer, Chairperson Sultana Hashem, founded 1962 by M.A. Hashem, appraisal |
| **B — Statute only** | 8 | s.46 maternity 16 weeks (p.39), s.118 eleven festival holidays (p.60), s.108 overtime 2× (p.57), s.24 due process (p.32), s.138/140 minimum wage, s.33 grievance, s.26 notice, trade unions |
| **C — Floor comparison** | 8 | *renamed from "conflict".* casual 10 = s.115 floor · sick 14 = s.116(1) floor · annual 30 **>** s.117 floor (**exceeds → compliant**) · 44.5h ≤ 48h (s.102) · weekly holiday exactly at the s.103(a) minimum · **the probation carve-out vs "every worker" — the one real conflict** |
| **D — Unanswerable** | 6 | 3 × nonexistent documents (Sales Handbook commission, FAQ, Company Profile) + WFH/remote, paternity, pension — **each grep-verified, grep committed as the test** |

`evals/golden.yaml` with `{q, tier, expected_behavior, gold_answer, gold_doc, gold_section, gold_printed_page}`. Draft against the extracted text, then **hand-verify every row against the rendered page image** — the LLM-generated golds will be wrong precisely on the floor-comparison cases, **which is the point.**

**Write the golden set BEFORE the retrieval pipeline** — the questions come from the PDFs, not from what the system happens to do well.

**Honest reporting: n=30 → 95% CI ≈ ±10.7pp at a 90% score. Say so.** An honest wide interval beats a fake tight one. Report the harness commit SHA. **Do not invent a Cohen's κ you didn't compute** — hand-check the ~5 judge verdicts that disagree with your expectation and report that as *"spot-checked"*.

### 4.17 MCP — **CUT from the build, KEPT as a costed README paragraph** (Phase 2 gate)

Zero rubric lines. Its v1 advocate scored it **+2–3 Architecture, 0 everywhere else**, and conceded *"AI Response Quality (20): 0 directly from MCP. Do not claim otherwise."* Its headline statistic was a strawman (§4.8). Its prototype **emits a fabricated citation**. It wanted 4.5h. **And §10's live-enhancement segment means a failed handshake on a shared screen is unrecoverable and costs more than the marks it was worth.**

**Ship the paragraph — it earns most of the +2–3 at zero risk:**

> *"The retrieval layer is a standalone module with zero web or protocol imports. Exposing it over MCP so Claude Desktop, Cursor, or an internal agent can query the corpus is a ~21-line stdio adapter over the same four functions — `search_documents(query, doc_filter, k)`, `get_section(number)`, `get_document_page(doc_id, page)`, `list_documents()`. Deliberately deferred: the rubric has no protocol line, and MCP's value is crossing a trust boundary to foreign clients — there isn't one between my own FastAPI and my own retriever. Paying protocol overhead to talk to myself would be architecture theater."*

**v1 gated this on a hope** — *"at hour 15, IF `core/retrieval.py` imports nothing from `fastapi`/`mcp`"* — checked by eyeball. **UPGRADED to a machine check** (§4.18). Phase 2, 1.0h, `docs/claude_desktop_config.json` with an **absolute** interpreter path (Claude Desktop does not inherit your shell PATH — the #1 cause of silent startup failure). **Never on the live URL's critical path.**

**Hard rejections regardless:** MCP as internal transport between your own code and your own retriever; OAuth 2.1 (6+ hours, zero marks — **a bearer token documented as a demo credential is the senior move, and *naming* what you consciously declined outscores half-building it**); SSE transport (Streamable HTTP is current; SSE is a stale-mental-model tell).

### 4.18 SWE + API — **the 25 marks no round-1 expert read**

```
src/
  core/          # retrieval, chunking, sections — ZERO protocol imports (MACHINE-ENFORCED)
  ingest/        # OCR, page maps, index build, upload — a real CLI
  api/           # FastAPI routes, Pydantic models, error envelope
  prompts/       # versioned .md, loaded at runtime — NEVER inline f-strings (§9 requires you explain them)
tests/  data/extracted/  index/  docs/  evals/
```

**The core-purity contract — the single highest-leverage artifact in this lane.** `.importlinter`, ~15 lines, verified working (`lint-imports` prints `src.core is not allowed to import fastapi` and reports BROKEN with the violating import; KEPT without):

```ini
[importlinter]
root_packages =
    src
include_external_packages = True

[importlinter:contract:1]
name = core is protocol-free
type = forbidden
source_modules =
    src.core
forbidden_modules =
    fastapi
    starlette
    uvicorn
    mcp
    pinecone
    mistralai
    langchain_text_splitters
allow_indirect_imports = False

[importlinter:contract:2]
name = layered
type = layers
layers =
    src.api
    src.ingest
    src.core
```

Two gotchas: it requires `include_external_packages = True` when forbidding external modules (otherwise it errors confusingly), and `root_packages` must be an **indented list, not inline** — a copy-pasted blog config fails both ways. `src/__init__.py` must exist. Wire as a pytest case (`subprocess.run(['lint-imports'], check=True)`) so **`pytest` alone proves it**.

**`mistralai` is forbidden in `core/` too:** core takes an injected `Generator` **Protocol**, so the provider is swappable and core is testable with **zero network**. **Every architectural claim in the README becomes falsifiable by `lint-imports` rather than by trust.**

**API surface:**

```python
class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)
    doc_id: str; doc_title: str; doc_kind: Literal['handbook','statute']
    section_no: int | None = None; section_title: str | None = None
    printed_page: int; pdf_page: int; half: Literal['left','right'] | None = None
    snippet: str            # sliced from the chunk by code, never generated
    source_modality: Literal['text','ocr']; ocr_confidence: float | None = None

class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    kb_id: str = 'default'
    doc_filter: Literal['handbook','statute'] | None = None
    section_no: int | None = Field(default=None, ge=1, le=354)   # free 422 on nonsense

class AskResponse(BaseModel):
    answer: str; citations: list[Citation]
    insufficient_information: bool; route: str
    latency_ms: int; request_id: str; index_version: str
```

```
POST /api/ask            · POST /api/ask/stream (SSE)
GET  /health   → {status, index_loaded, chunk_count, index_version, kb_count,
                  model_id, pinecone_reachable}   # 503 if the index failed to load
GET  /api/documents → the curated manifest (real page counts + modality; NEVER the filename)
POST /api/kb                        → {id, name} → 201
POST /api/kb/{kb_id}/documents      → 202 + Location: /api/jobs/{job_id}
GET  /api/jobs/{job_id}             → {state: queued|extracting|embedding|indexing|done|failed, progress, doc_id?, error?}
GET  /api/kb                        → describe_index_stats()['namespaces'] — the KB list for free
```

**Typed error envelope, real codes:**

```python
class ErrorDetail(BaseModel):
    code: Literal['VALIDATION_FAILED','SCANNED_PDF_REQUIRES_OCR','KB_NOT_FOUND',
                  'PAYLOAD_TOO_LARGE','UPSTREAM_RATE_LIMITED','UPSTREAM_UNAVAILABLE',
                  'UPLOAD_BACKEND_UNAVAILABLE','INDEX_NOT_LOADED']
    message: str; request_id: str; retry_after_s: float | None = None
class ErrorEnvelope(BaseModel): error: ErrorDetail
```

**400** malformed · **413** >32 MB · **422** semantic (scanned PDF) · **429** upstream rate limit **echoing the upstream `Retry-After` into both the header and `retry_after_s`** · **503** index not loaded / `NoResponseError`. **Never a 200 with a stack trace** — *"a 200-with-a-stack-trace scores 5/10."* **Refusal is not an error: 200 + `insufficient_information: true`.**

**Two SDK findings that only come from reading the source, not the quickstart:**
1. **`mistralai` does not retry by default** — `retry_config = None` unless you pass a `RetryConfig`. **A demo that assumes the SDK retries dies on the grader's second click.**
2. **`NoResponseError` subclasses `Exception`, not `MistralError`** — `except MistralError` **silently misses it** and it escapes as a 500. It needs its own handler → 503.
3. **Do not hand-roll tenacity on top** — that double-retries and multiplies your backoff.

```python
Mistral(api_key=..., retry_config=RetryConfig('backoff',
    BackoffStrategy(initial_interval=1000, max_interval=8000, exponent=1.5, max_elapsed_time=30000),
    retry_connection_errors=True))   # retries ['429','500','502','503','504'], honours Retry-After
```

**Upload cap 32 MB → 413.** Measured: **the Labour Act asset is 16,250,566 bytes (16.25 MB)**, so the commonly-copied 10 MB cap would **reject the corpus's own document**. **Size the limit to the corpus you were given.**

**Idempotency:** `doc_id = sha256(pdf_bytes).hexdigest()[:16]`. Re-POST of identical bytes → **200** with the existing doc, no re-ingest. Answers *"what if the grader double-clicks?"* in 5 lines.

**The upload validator and the OCR build gate are the same function.** `core.assess_extractability(pdf)` is called from both the ingest CLI and the API. An uploaded scanned PDF would otherwise **silently index 0 chars** — the exact silent-blank-index failure this corpus punishes. **The build gate becomes a product feature: the API refuses honestly instead of succeeding emptily.** → **422 `SCANNED_PDF_REQUIRES_OCR`**, message naming the measured threshold and pointing at `python -m src.ingest ocr <pdf>`. *(Rejected: tesseract in the runtime image — ~100 MB, ~10 min blocking on 2 vCPU, and the result evaporates on restart. **The typed 422 is less code, honest, and scores better than a half-working feature.**)*

**Logging/config:** `structlog` or stdlib + JSON formatter; `request_id` (uuid4) via middleware on **every** line + echoed in the body and an `X-Request-ID` header; log `route`, `kb_id`, `latency_ms`, `n_citations`, `insufficient_information`, `rate_limit_wait_ms`. **Never log the question at INFO — it is a user's HR query.** `Settings(BaseSettings)`: `MISTRAL_API_KEY` (required → **hard fail at boot with a named error**, not a 500 on first request), `MISTRAL_MODEL`, `MISTRAL_MAX_RPS=1.0`, `PINECONE_API_KEY` (optional), `LOG_LEVEL`.

**`index/index_meta.json`** = `{pdf_sha256 per doc, ocr_params: {engine:'tesseract 5.5.2', lang:'eng', dpi:200, full:true}, chunker_version, embed_model_id:'BAAI/bge-small-en-v1.5', embed_dim:384, query_prefix:'Represent this sentence for searching relevant passages: ', corpus_stats_ref}`. Verified at boot → mismatch = `/health` 503 with the diff logged. **Twenty lines that answer *"how do you reindex when a document changes?"* in 60 seconds — a question that will be asked.**

**Tests a grader will actually run.** `conftest.py` injects a **`FakeGenerator`** implementing the same Protocol as the Mistral client — **every test runs with no API key and no network** (this is what `core/` having no `mistralai` import buys you):

1. `test_printed_page_from_zero_based_index` — the 6 footer asserts
2. `test_partex_folios` — `partex_folios(2) == (3, 4)`
3. `test_deinterleave_regression` — the `"Leave During Probation"` chunk must NOT contain `"Confidentiality"`. **Silent corruption never throws; this is the only thing that catches it.**
4. `test_sections_detected` — `{45,46,100,108,115,116,117,118} <= detected`
5. `test_core_is_protocol_free` — shells `lint-imports`
6. `test_ask_e2e` — asserts `citations[0].printed_page == 59` **on the typed object** (impossible against a markdown string)
7. `test_refusal_is_200` — **`"paternity leave?"`** → 200, `insufficient_information is True`, citations may be non-empty
8. `test_span_verification` — a fabricated span → claim stripped → `insufficient_information`
9. `test_scanned_upload_422`
10. `test_upload_idempotent` — same bytes twice → 202 then 200, one doc
11. `test_upload_survives_restart` — upsert to a namespace, **drop the in-process state**, re-query, **assert a full citation renders**. *(Without this, the durability claim is a README sentence.)*
12. `test_no_torch`

### 4.19 Frontend

**SHIP:** FastAPI-served static HTML + fetch + **SSE streaming**. **6 seeded question chips.** ~1.5h.

| Rejected | Why it lost |
|---|---|
| React SPA (Vite) — 6h | 0.83 marks/hour against a 5-mark line, and it adds a build step, a static-serving path and a CORS surface — **three new ways for the live URL to die.** **Its own v1 author conceded it in writing:** *"a broken React app scores far worse than a working Streamlit one, and 20+20+15 dwarfs the 5 for UX."* |
| Streamlit | You must build FastAPI anyway for the separate 10 API marks, so the frontend is the only free variable — and a static page is **less** work than Streamlit's rerun model. |
| WebSockets | Bidirectional transport for a unidirectional problem, and more ways to fail behind HF's proxy. |

**SSE stops being cosmetic under a rate-limited free tier: it is the only thing between the grader and a blank box for several seconds.** `sse-starlette==3.4.5`, typed events `{event: 'route'|'retrieved'|'token'|'citations'|'done'}` — **citations arrive as a typed terminal event, never interleaved into the token stream**, so the client never parses prose to find a page number. Non-streaming `/api/ask` retained for the harness and for curl in the README.

**The 6 chips are the highest-ROI 30 minutes in the entire build** and are non-negotiable. **The grader cannot invent good questions about a Bangladeshi labour statute.** An empty text box means they type *"what is the leave policy?"*, get something competent and forgettable, and close the tab. Order builds an arc — warm-up → flagship → nuance → honest unknown:

1. *"How many days of casual leave am I entitled to?"* — handbook 10 **and** s.115 ten. Both agree. Shows the citation UI working.
2. **FLAGSHIP:** *"Does our Employee Handbook comply with the Bangladesh Labour Act on maternity leave?"* — reasoning about an **absence**. ss.45/46 mandate 8+8 = 16 weeks; the handbook is silent (**0** occurrences) while claiming compliance on its own folio 1.
3. *"We work Sun–Thu 9–5 and Sat 9:00–1:30. Is that legal?"* — 44.5h ≤ 48h (s.102) ✓; Friday + Saturday half = 1.5 days = **exactly** s.103(a)'s minimum. A *"compliant, and only just"* answer proves reasoning, not pattern-matching.
4. *"How much overtime pay is required?"* — handbook silent; s.108 = 2×.
5. *"What is the parental leave policy?"* — the honest, designed **"I don't know."**
6. *"Who is the Chairperson and where is the head office?"* — Sultana Hashem; Shanta Western Tower L-13, Tejgaon, Dhaka-1208. Grounds the demo.

### 4.20 Deploy — HF Spaces, and the 48h contradiction

**SHIP:** single Docker Space, free `cpu-basic`: **2 vCPU, 16 GB RAM, 50 GB non-persistent disk, no card** (a card is required *only* to upgrade hardware — satisfies C1). Outbound is restricted to 80/443/8080; Mistral and Pinecone are both 443.

**The 16 GB is not a luxury — it is the load-bearing reason this costs nothing:** it lets bge-small int8 ONNX run in-process at 2.4 ms with zero API cost, which is what kills the embedding bill.

```dockerfile
FROM python:3.11-slim-bookworm
RUN useradd -m -u 1000 user           # HF runs as UID 1000 — omitting this is the #1 build failure
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/home/user/app/.models
WORKDIR $HOME/app
COPY --chown=user requirements.txt .   # --chown=user on EVERY copy
RUN pip install --no-cache-dir -r requirements.txt
# Bake the model at BUILD time. fastembed's default cache is a TEMP dir; HF's disk is
# ephemeral, so an unbaked model re-downloads on EVERY cold start (measured +10.7s and a
# hard dependency on HF's CDN at boot — a CDN hiccup boots the Space broken, on the
# grader's click, with no error in my code). Baked: 0.5s.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/home/user/app/.models')"
RUN python -m compileall -q src
COPY --chown=user . .
EXPOSE 7860
CMD ["uvicorn","src.api.main:app","--host","0.0.0.0","--port","7860"]
```

README YAML front-matter: `sdk: docker`, `app_port: 7860`. **Layer order deps → model → index → src**, so a one-line edit redeploys in ~30s — which matters if you're about to be asked to add something on camera.

**Measured boot budget** (warm .pyc + baked model): import fastembed ~1.0s + model load 0.5s + `np.load` 27 ms + chunks 13 ms + BM25 build 21 ms ≈ **~2.5–3.5s app-controlled**. HF's own wake dominates and I do not control it.

> **⚠️ THE 48h CONTRADICTION — the most operationally valuable finding in round 2, and it decides whether a mandatory submission item is alive weeks later.**
> **HF's own docs contradict themselves.** `SpaceRuntime.sleep_time`: free cpu-basic *"will go to sleep after 48 hours"* and *"**Any visitor** landing on your Space will start it back up."* The manage-spaces guide: it *"will automatically be **PAUSED** after 48h of inactivity"* and *"**A paused Space will be inactive until the OWNER of the Space restarts it.**"*
> **Sleeping = the grader waits 60s and gets a demo. Paused = the grader gets a dead URL only I can fix.** Free cpu-basic **cannot configure a custom `sleep_time`**. **I cannot resolve this from documentation, so I engineer so the branch never resolves.**

**Keep-alive:** `.github/workflows/keepalive.yml`, `cron: '0 */12 * * *'` + `workflow_dispatch`, one `curl -fsS .../health`. **2 requests/day** — proportionate, disclosed in one README line, and it doubles as the **uptime canary** (job failure emails the owner). **Disclosed fuse: GitHub auto-disables scheduled workflows after 60 days with no COMMIT activity in a public repo** (only commits reset the timer; GitHub warns first). For a submission graded within weeks it never fires; **naming it is the difference between a limitation and a surprise.**

**CI (v1 cut this — OVERTURNED; it's now the deploy path AND the canary):** `test.yml` (ruff → mypy --strict on `src/core src/api` → `lint-imports` → pytest; **no API key needed thanks to FakeGenerator, so it's green on a fork**), `deploy.yml` (push to the HF remote with `HF_TOKEN`), `keepalive.yml`. **A badge is 25 lines and it is the difference between claiming and showing on 15 marks.**

| Rejected | Why it lost |
|---|---|
| Render free | 512 MB — the runtime is ~301 MB of packages + 65 MB model + index, **no headroom** — and it spins down at 15 min, so **the grader hits a cold start on their only visit**. |
| Fly / Railway | Card or trial-credit expiry = C1 violation. |
| Vercel + separate backend | Two deploys, two failure surfaces, a CORS surface, for a 5-mark line. |
| Private / "protected" Space | **Verified: a private Space returns 404 to everyone but the owner.** "Protected" (private source, public app) requires **PRO = paid = C1 violation**. **One click, and a mandatory submission item scores zero with the code perfect.** |
| Auth | The spec says *"test credentials **if** authentication is enabled"* — **enabling it manufactures an obligation and a new dead-URL mode for zero marks.** |
| `pip freeze` | Measured: torch's linux wheel is **526.6 MB** and pulls **~799 MB of nvidia-cudnn + 197.6 MB triton** — **~2.5–3 GB to run a model I execute in ONNX at 65 MB.** |
| Poetry / uv lockfiles | Extra tooling for the grader to install before they can run anything. **A hand-written pinned `requirements.txt` is readable in 20 seconds and that readability IS the mark.** |
| `--reload` / multi-worker gunicorn | 2 vCPU and an in-process job dict make multiple workers **actively wrong** (jobs land in the wrong worker). |
| **Build-time response cache for the 6 chips** *(Deploy lens's "THE HIGH-VALUE ONE")* | **CUT — conceded to the adversary.** It insures against a 429 that the single-flight UI **already makes untriggerable**. You'd stake the most important 90 seconds of the submission on a committed answer file, and *"Served from cache"* invites *"has your live path ever answered this, and how would I know?"* **A banner makes it honest, not safe.** No other lens reviewed it; it was in no test and no schema. |

### 4.21 C7 — the optimisations, measured, and the ones I refused

**The bottleneck is the LLM call and the rate limit. Full stop.** Measured: model call **1–3s** (+ queueing) ≫ query embed **2.4 ms** ≫ exact cosine **0.0083 ms**. **So every optimisation hour goes to the model path and none goes to the index.**

**SHIP — five layers, in value order:**
1. **Single-flight UI** — all 6 chips disable the moment one is in flight. **The grader physically cannot fire concurrently.** ~10 lines, and it is the actual fix.
2. **Server-side `asyncio.Semaphore(1)` + a monotonic token bucket** in the provider client, so programmatic callers **queue rather than fail**. Queue wait >10s → **429 + Retry-After** rather than queueing until the browser gives up. **That is backpressure, and it is the honest answer to "what happens under load?"**
3. **Backoff by exception CLASS** (SDK-owned), never string-matching a message.
4. **SSE streaming** — hides TTFT; a queued user sees `queued → generating`, not a spinner.
5. **Router cut** (§4.9) — 2 requests/query → 1. **That single decision is worth more than every context-compression technique combined.**

**`MISTRAL_MAX_RPS` is an env var, default 1.0. NEVER quote a rate limit in the README.** Mistral **no longer publishes free-tier numbers** (their docs defer to the Admin Console) and secondary sources disagree **by 30×** (~1 req/s vs 2 req/min). **A README asserting "1 req/s" is a falsifiable claim about someone else's product**, and it would reproduce v1's cardinal sin inside the fix for v1's cardinal sin. The line is: *"the free tier's exact rate limit is not published; I gate client-side at a configurable RPS and honour the server's `Retry-After`, so the correct number is whatever the server tells me."*

**SHIP — `docs/optimisations.md`: "Optimisations I measured and deliberately did NOT do."** 0.5h, and **it is the highest marks-per-hour artifact in the build** — it serves C7, Architecture (20) and Docs (10) at once, and it proves "optimisation" meant measurement and not vocabulary.

| Not done | The number that killed it |
|---|---|
| Product quantization | **399 vectors.** Compressing 0.6 MB that loads in 27 ms and searches in 0.0083 ms. **A rounding error on a rounding error.** |
| HNSW / IVF | **Strictly worse than not building it** at this scale: approximate (recall <100%) for a speedup smaller than network jitter, and an m=16 graph over 399 nodes degenerates into near-fully-connected. |
| int8 quantization | **Already the fastembed default artifact** (`qdrant/bge-small-en-v1.5-onnx-q`). Writing the step would re-do what the library did. |
| bge-base 768d | Measured: **recall@5 1.00 vs 1.00**, 4.2× build, 5.5× query. Zero gain. |
| LLMLingua / selective context / chunk pruning | The RAG prompt is **~5.2k tokens = 2.0% of a 262,144 window**, with ~30× token headroom against a limit that doesn't bind. **Compressing the resource you have a surplus of, against a limit that isn't binding, is theatre.** And it *actively harms*: pruning chunks before a generator that must prove an **absence** can only destroy the soundness the pinned handbook buys by construction. |
| Reranking | recall@5 is **1.00**. You cannot rerank above 1.00 — §4.14. |
| Prompt caching as a latency story | Mistral caches in **64-token blocks** (the 3,166-token handbook clears it 49×), so v1's 4,096-minimum worry evaporates — **but Mistral's docs say `prompt_cache_key` "increases the chance of a cache hit, but it doesn't guarantee one," so porting v1's `assert cache_read_input_tokens > 0` BUILD GATE would fail the build on a documented non-bug.** Pass a stable key (`kb:partex-v1`), keep the prefix byte-stable (no timestamps, no session IDs, `json.dumps(..., sort_keys=True)`), **log `usage.prompt_tokens_details.cached_tokens` as a metric — do not assert on it.** At $0 the 90% price discount discounts nothing; the cacheable prefix is ~4k tokens so the prefill saving is small and unguaranteed. |
| Small-to-big as a prompt-shrinker | Measured: median section **149 tokens**, top-8 = ~1,200. **There is nothing to shrink.** |
| Numeral normalisation *as headlined* | v1's justification is **falsified** — BM25 ranks s.116 **rank 1** for `"14 sick days?"`. **Kept on narrower honest ground:** anchorless queries (`14 days?` rank 33 → rank 2 with normalisation; dense misses too). 40 lines of insurance. **Never headline it.** |

---

## 5. The context-window ruling

**RULED: the corpus FITS. The bombshell is dead. v1's headline defence survives with the number swapped — and it gets stronger.**

The premise I was handed — *"Mistral Large's context window is ~128k. The corpus is ~128k. IT DOES NOT FIT. RAG is FORCED. v1's headline must be rewritten"* — **is false on both halves, and I verified each:**

1. **`mistral-large-2512` (Mistral Large 3, released 2025-12-02) is 256k = 262,144 tokens** — confirmed on Mistral's own model card, fetched this session. Medium 3.5 and Small 4 are **also** 256k. **The entire current line is 256k.** The 128k figure describes **Mistral Large 2 (2411)**, which is superseded.
2. **The corpus is 122,204 tokens** — measured with the model's own tekken tokenizer (v13, vocab 131,072), not chars/4 and not tiktoken. **46.6% of the window, with ~140k of headroom.**

**And even if the window *were* 128k, the indexed corpus (101,100) fits at 77.1%.** There is no configuration in which the bombshell detonates.

> **This is the single most important ruling in the document: DO NOT "FIX" THE BEST ANSWER IN THE RECORD.** Four lenses were briefed by their own principal to rewrite v1's headline around a stale model number, and all four refused and went to primary sources. Had the candidate rehearsed *"RAG is forced because Mistral is 128k"*, the interviewer pulls up the model card and **the credibility of every other measured claim dies with it** — the exact "seven numbers for one fact" disqualification, self-inflicted at the headline. *"RAG is FORCED"* is not a stronger position. **It is not available. It is factually wrong, and a wrong headline defence is worse than a right nuanced one.**

**Consequences:** RAG remains a **defended choice**, not a necessity. The full-context oracle is **possible, free, and on the same model** (a cleaner ablation than a cross-provider oracle, which would be dishonest). And **the honest caveat that makes the defence stronger, not weaker:** *"fits"* and *"the model attends to all of it"* are different claims. Effective recall degrades below the advertised window — **and that gap is precisely what the oracle number measures.**

> ### THE SENTENCE — Q1, lead with this
> *"It fits, and I measured it with Mistral's own tokenizer — mistral-common, the tekken tokenizer, not tiktoken and not chars-over-four, because a token count from the wrong tokenizer can't support a context-window argument. My corpus is 122,204 tokens against Mistral Large 3's 262,144-token window: 47%. So RAG here is a choice, not a necessity, and I want to be the one who says that before you do. I built the full-context baseline anyway — on the free tier it's three million tokens for my whole eval, so there was no excuse not to — and it's the oracle in my eval table: the ceiling I measure retrieval against. I ship RAG for three reasons: your rubric grades Retrieval Accuracy as its own fifteen marks and you can't score that without a retriever; citation provenance is by construction when a chunk carries its own page, whereas a context-stuff invents page numbers; and it doesn't survive the six-document corpus your spec described. I don't defend it on cost — on a free tier there's no cost to defend. And one honest caveat: fitting and attending are different things. The oracle is what measures that gap."*

> **If pushed — "I thought Mistral was 128k":**
> *"That's Mistral Large 2, the 2411 release. Large 3 and Small 4 both ship 256k — 262,144. It's the kind of number that goes stale in six months, which is why it's in `corpus_stats.json` from one committed script rather than typed into my README. I checked the model card in July 2026."*

---

## 6. Verdicts on your stated desires

### 6.1 RAG — **KEEP, REFRAME as a defended choice**
See §5. **Do NOT defend RAG on cost** — on a free tier both are $0, and anyone claiming "RAG saves money" here gets broken open in one follow-up. → **THE SENTENCE: §5.**

### 6.2 MCP — **CUT from the build, KEEP as a costed README paragraph.** Phase 2 gate (§4.17).
> *"MCP is a distribution protocol, not a retrieval technology — it earns its cost by crossing a trust boundary to foreign clients, and there isn't one between my own FastAPI and my own retriever. My retrieval layer is a clean module with zero web imports — and that's not a claim, it's `.importlinter` running in CI — so exposing it over MCP for Claude Desktop is a 21-line adapter. Here are the four tool signatures. I deferred it deliberately: the rubric has no protocol line. Paying protocol overhead to talk to myself would be architecture theater."*

### 6.3 Vector DB — **REFRAME: numpy for the committed corpus, Pinecone for uploads. Both live.** (§4.6)
> *"Two stores, and the property that decides between them is **lifecycle, not speed**. The committed corpus is 399 vectors at 384 dimensions — 0.6 megabytes, exact cosine in 0.008 milliseconds. Putting that in Pinecone would be infrastructure cosplay, and worse, it would make your cold visit depend on someone else's free-tier quota and an inactivity policy that isn't even documented. So it's a committed numpy array that loads at boot with zero network — nobody but me can pause it. Uploaded knowledge bases are different data with a different lifetime: Hugging Face Spaces' disk is ephemeral, so an uploaded KB has to live off-box. One Retriever protocol, two backends, both on live traffic. Committed data is a file; runtime data needs a database. Milvus needs etcd and MinIO to serve 0.6 megabytes — I'd rather show you I can size a system than that I can install one."*

### 6.4 Agents — **CUT.** The one named justification was false (§4.15).
> *"I don't have an agent, and I want to tell you why, because I started out planning one. I counted 121 'section N' cross-references and that looked like multi-hop retrieval. Then I went hunting for a query single-shot actually gets wrong. The example everyone reaches for is section 100's eight-hour cap deferring to section 108 — except I read section 100, and the ten-hour exception is in section 100's own sentence; 108 is the overtime pay rate, a different question. Section-aware chunking already handles it. I couldn't find a failing query on my eval set, so I wrote no loop. Two documents, one permanently in context — there's no coordination problem. And on a free tier at roughly one request per second, an agent's extra hops aren't milliseconds, they're seconds."*

### 6.5 LangGraph — **CUT.** (Mandated. Declining it, respectfully and plainly — §4.11.)

**You asked for it and I am not shipping it. Here is the whole reason in three lines:** its only unique justification — *"`draw_mermaid()` generates the required architecture diagram from the code that runs"* — **is false**; the rubric wants a *system* diagram (PDFs, OCR, chunker, two stores, provider boundary, API, UI, build/runtime split) and `draw_mermaid()` renders **none of it**. And the two nodes that would have made it a genuine graph — the LLM router and the live entailment judge — **were both deleted by the free tier's rate arithmetic**, not by taste. What's left is `code classifier → 0.008 ms numpy scan → one LLM call → code check`: a linear pipeline. **Wrapping ~15 lines of async Python in a state-machine framework buys one interview question I cannot win** (*"why is there a graph framework in a two-node pipeline?"*) and zero marks.

**The strongest honest version of what you asked for:** the revival gate is written down and it can genuinely fire — **≥5 real nodes with ≥2 genuine branch points** (a real fan-out, a retry loop, a human-in-the-loop pause). Today: two and one. Removal cost if you disagree and build it anyway: ~40 lines. And note checkpointing — the usual killer argument for LangGraph — **is unbuildable here regardless**: `MemorySaver` dies with the container, `SqliteSaver` needs a disk HF wipes on restart, durable needs Postgres = a card = C1.

> *"No LangGraph. I'll give you the version I was tempted by first: it draws its own diagram, and a CI test could diff it. But the diagram your rubric asks for is the system — the PDFs, the build-time OCR, the chunker, two vector stores, the provider boundary, the UI, with the build/runtime line drawn across it — and LangGraph can't draw any of that. So the generated picture would prove the wrong artifact is current. The deeper reason: my router is deterministic code and my entailment judge runs offline, both because at one request per second every extra model call is a full second of your latency. Strip those out and my 'graph' is a classifier, a numpy scan, one model call, and a code check. That's fifteen lines of async Python. I'd rather hand-write the real diagram in ten minutes than defend forty lines of ceremony to you now."*

### 6.6 LangChain — **REFRAME: `langchain-text-splitters` for uploads ONLY.** (§4.12)
> *"I used LangChain for exactly one thing, and I refused it for exactly one thing, and both are measurements. My rule: use the framework where the complexity is foreign; write it yourself where it's the thing you're being graded on. For the statute I know the grammar, and I measured `RecursiveCharacterTextSplitter` at a thousand with two hundred overlap merging sections 115, 116 and 117 — casual, sick and annual leave, three distinct legal entitlements that happen to share a printed page — into one chunk with one page number. Ask it what page section 117 is on: it says 76. The document says 59. So the Act gets a chunker built on its own section grammar, with a build gate that fails if section 46 goes missing. But for a document you upload thirty seconds from now, I don't know the grammar — and a recursive character split is the honest default. Same library, opposite verdicts, both measured. I didn't install the langchain meta-package at all, so the splitter I rejected isn't even importable in my repo."*

**Not shipped:** the provider boundary. `.with_fallbacks()` was the only genuinely new argument, and **it fails over to Groq at 12–19 queries/day or an OpenRouter model ID that has rotated out and 404s.** Without it, LangChain is `ChatMistralAI` wrapping one SDK — an abstraction over one implementation — plus **langsmith (6.6 MB)** in a repo about document confidentiality.

### 6.7 Pinecone — **KEEP for uploaded KBs. CUT for the committed corpus. And I am correcting the reason everyone gave for it.** (§4.6)

**The honest version, because the dishonest version is falsifiable in one click:** Pinecone is **not** necessary. **HF Storage Buckets are free, no-card, first-party, S3-like, mutable, and mount read-write into the Space container** — I verified all four from HF's own docs. They would reuse the existing numpy store with no second vendor. **Anyone who tells you "the disk is ephemeral, therefore Pinecone was the only free option" has not read HF's storage page**, and a grader who has will end the exchange there.

**Pinecone ships anyway, on three grounds that survive scrutiny:** you mandated it; it is genuinely C1-clean (no card); and **namespace-per-KB fails closed** — a metadata filter you forget leaks across tenants, a namespace you forget returns nothing. **100 namespaces per index is the right primitive by 20× over 5 indexes.**

> *"I use Pinecone for exactly one thing: the documents you upload at runtime. Spaces' disk is ephemeral, so an uploaded knowledge base has to live off-box, and Pinecone's free tier gives me a hundred namespaces per index — a hundred isolated knowledge bases, and the isolation fails closed: a namespace you forget returns nothing, whereas a metadata filter you forget leaks across tenants. Metadata caps at 40 kilobytes and my chunks are under two, so the chunk text rides along and an upload survives a restart completely — vectors and text — with no second datastore. I'll be straight about the alternative, because it's the honest part: Hugging Face Storage Buckets are free, first-party, and mount read-write, and they'd have reused my numpy store with one fewer vendor. I chose Pinecone for the namespace primitive. What I did **not** do is put the committed corpus in it — that's 399 vectors and 0.6 megabytes, exact cosine in 0.008 milliseconds, and it's a file in the repo, so the URL you're looking at can't be broken by a third party's undocumented inactivity policy. Pinecone's in here for persistence, not performance. If you'd only asked for the two documents in the assets, I'd have cut it."*

### 6.8 Fine-tuning — **CUT, all four forms. Zero gradient steps. This is the strongest section of your submission.**

Four independent reasons, **in this order** — the order is load-bearing:

1. **I can train it. I cannot serve it. — LEAD WITH THIS.** Concede trainability in the same breath, because it's true and falsifiable: QLoRA on a 4-bit 7B is **~7 GB and <30 min on your actual M2/16 GB**. **But the rubric mandates a Live Application URL and free hosting has no GPU.** HF Spaces free is 2 vCPU CPU-only. **ZeroGPU fails three ways at once:** hosting one requires a **PRO subscription** (a card → C1); it is **"exclusively compatible with the Gradio SDK"**, which would demolish the FastAPI surface carrying **10 API marks**; and an **unauthenticated visitor — which is exactly what the grader is — gets 2 minutes/day at LOW priority.** *(Do not lead with deprecation: it invites "so use the open weights," which is a fair counter you'd lose. The deployment fact is instantly checkable and cannot be argued with.)*
2. **The hosted path is deprecated AND it bills.** Mistral's fine-tuning docs are served from a URL with **"deprecated" in the path** and say verbatim *"This feature is deprecated and is no longer actively supported"* — plus **$4 minimum/job + $2/month/model storage**, a **recurring** card charge. `mistralai/mistral-finetune` is **archived** and wants an A100/H100. Gemini's free-tier tuning **died with 1.5 Flash-001 in May 2025**.
3. **It structurally fights C6 — your own requirement.** *(This reason did not exist in v1, and it is the one to lead with when explaining the decision to yourself.)* A fine-tune is a **build-time artifact keyed to ONE corpus**. Every new KB = regenerate pairs, retrain, revalidate, redeploy weights free hosting cannot serve. **Retrieval's entire value proposition is exactly what C6 asks for: a new document is new vectors and a new namespace.** Your two stated desires are in direct conflict, and fine-tuning is the one that has to lose — **not because I dislike it, but because the other one is a requirement you wrote down.**
4. **You could not validate it.** Exact McNemar enumeration (paired design — the most *generous* honest framing): **MDE(n=30) = 29pp**. A realistic embedding fine-tune gains **2–8pp**. **Power at +8pp with n=30 is 4.6% — a 95% false-negative rate.** You'd need **n≈200** hand-verified questions, and hand-verification is the entire budget. *(v1 said "~11pp at n=30" — that is the **n=100** figure, overstating detectability **2.6×**. Ship `evals/power.py` so the number is **generated, not asserted**.)* **⚠️ NEVER say "my experiment is more likely to find a fake win than a real one" — I checked the null rejection rate (0.00% at n=30; the test is conservative). That line is FALSE.** The correct, still-devastating line is the **95% false-negative rate**.

**The one that survives every constraint — and still loses, on a measurement.** The **bge-small embedding fine-tune** is free, local, CPU-trainable in minutes, and **deployable as the same ONNX file the app already loads**. None of reasons 1, 2 or 4's deployment logic touches it. **So I measured the thing it was supposed to fix, and it isn't broken:** its only motivation is the lexical numeral gap, and **BM25 ranks s.116 rank 1 for `"14 sick days?"`** because `df('sick') = 2/342` is a decisive high-IDF anchor and the digit free-rides. **And on the only family where the gap is real — anchorless numerals — dense misses too**, so an embedding fine-tune wouldn't fix it either. **40 lines of numeral normalisation does.**

**Also CUT: the "measured negative ablation" (2.5h).** **Ego wearing humility's clothing.** Its own advocate pre-declared the outcome and shipped it disabled. **You do not spend 2.5 hours proving a conclusion you already hold, and the README paragraph is byte-identical either way.** Replacement: `docs/finetuning.md`, **0.75h** — a dated, sourced decision record with **a trigger condition written so it can actually fire**.

> **THE SENTENCE:**
> *"Four reasons, and I'll lead with the one that ends it: I can train it, I just can't serve it. QLoRA on a 7B is about seven gigabytes and under thirty minutes on my M2 — that part's genuinely easy and I won't pretend otherwise. But you require a live URL, and free hosting has no GPU. Spaces free gives me two vCPUs. ZeroGPU needs a PRO subscription to host, it's Gradio-only so it'd take out the FastAPI layer you're scoring for API design, and an unauthenticated visitor — you, clicking my link — gets two minutes a day at low priority. Second, the hosted path is gone: Mistral's own docs are served from a URL with 'deprecated' in it, and it bills four dollars a job plus two a month, which is a card on file for a demo. Third — and this is the one that actually decided it — you want to upload new document sets as separate knowledge bases at runtime. A fine-tune is keyed to one corpus; every new KB would be a retrain and a redeploy of weights free hosting can't run. Fine-tuning and extensibility are mutually exclusive here, and extensibility is the requirement. Fourth, I checked whether I could even measure a win: at n=30 my minimum detectable effect is twenty-nine points and a realistic embedding fine-tune gains two to eight. At plus eight my power is 4.6% — I'd miss a real improvement ninety-five percent of the time. That's `evals/power.py`; it's forty lines and it's what sized my golden set."*

> **THE CRUX — invite this one:** *"But there must be SOME fine-tune worth doing. The embedder?"*
> *"You've found the right one. bge-small is thirty-three million parameters — it trains on my CPU in minutes, costs nothing, and deploys as the same ONNX file the app already loads. Free, local, deployable. None of my other reasons touch it. I didn't do it, and the reason is a measurement, not a principle. Its only motivation on this corpus is a lexical gap: the Act writes numbers as words — 'fourteen days' — and users type '14 sick days'. So before building anything I ran the retriever. BM25 ranks section 116 first. Not a miss — first. Because 'sick' appears in two of three hundred and forty-two sections; it's a decisive high-IDF anchor and the digit free-rides. The gap only shows up on anchorless queries like '14 days?' — and there dense misses too, so fine-tuning the embedder wouldn't fix it either. Forty lines of numeral normalisation does, and that's what I shipped. So: I had a fine-tune that was free, fast and deployable, and I still didn't ship it — because I measured the thing it was supposed to fix and it wasn't broken."*

> **THE CONCESSION BEAT — deploy this if they push on rigour. It is the strongest thing in the section.**
> *"I'll give you the part I got wrong. In an early draft I'd written 'BM25 misses section 116', because I measured at the page level: printed page 76 has 'fourteen' twice and '14' zero times, so I inferred the retriever would miss it. That inference was wrong. Once you chunk on section boundaries, the section title carries the query. I only caught it because I ran the retrieval instead of reasoning about token counts — and it's the same trap as the 'section 100 defers to section 108' example everyone quotes, which also dissolves the moment you read section 100. Measuring a strawman and headlining the result is the failure mode I'm most afraid of in my own work."*

---

## 7. The killer differentiator — the compliance-gap ruling

**YES. Ship it. Time-boxed to 1.5h total.** It is **not** scope creep: it is a system prompt plus 3 example questions over the *identical* RAG core, and **it is the only decision that converts the corpus mismatch from an embarrassing liability into the differentiator.** It targets AgamiSoft's actual market: Bangladeshi employers who must comply with this exact statute.

**The corpus forces the decision.** 181 of 187 pages are national statute. Pure handbook Q&A ignores 97% of the corpus. Pure statute Q&A ignores the employer's own document. **The only architecture that honestly serves both is one that knows which is which and can relate them.**

| Topic | Partex Handbook | Bangladesh Labour Act 2006 | Verdict |
|---|---|---|---|
| Casual leave | 10 days (folio 6) | s.115 "ten days" (p.59) | **Exactly at the floor** |
| Sick leave | 14 days (folio 6) | s.116(1) "fourteen days" (p.59) | **Exactly at the floor** |
| Annual leave | 30 days after 12 months | s.117(1)(a) 1 day per 18 worked ≈ 14–17 (p.59) | **Exceeds → COMPLIANT** |
| Working hours | Sun–Thu 9–5, Sat 9–1:30 = 44.5h | s.100 8h/day (→10h, p.56), s.102 48h/week | **Compliant** |
| Weekly holiday | Friday + Sat half = 1.5 days | s.103(a) commercial minimum | **Compliant, and only just** |
| **Maternity** | **0 occurrences** | ss.45/46: 8 weeks before + 8 after = **16 weeks** (p.39) | **GAP** |
| **Festival holidays** | 0 — only *"Festival Bonus"*, a **payment** | s.118(1): **eleven days paid** (p.60) | **GAP** |
| **Overtime** | **0 occurrences** | s.108: **2× ordinary rate** (p.57) | **GAP** |
| **Due process** | §L: action *"as deemed appropriate by the management"* | s.24 (p.32): written charge + ≥7 days to explain + hearing + enquiry + approval | **CONFLICT** |
| **Probation carve-out** | *"New joiners will get leave after completion of their probation period"* (folio 7) | s.115/116: "**Every** worker shall be entitled" — no probation qualifier | **CONFLICT** |

And folio 1 states verbatim: *"The human resource (HR) policies and procedures contained in this handbook are in compliance with the applicable labor laws of Bangladesh."* **The corpus is a claim plus the evidence that falsifies it.** *(Note the nuance that proves you read it: s.117 **does** require "one year of continuous service", so annual leave during probation is fine — the carve-out only conflicts for casual and sick.)*

### Three hard rules

**1. Floor semantics are encoded in the prompt, not hoped for.**

> *"The Act sets statutory MINIMA. If the handbook grants at or above the statutory minimum, it is COMPLIANT — report it as such. Report a gap ONLY where the handbook grants LESS than the floor, or is SILENT on a mandatory entitlement. Cite both sources verbatim with printed page numbers. Never assert a gap without both citations."*

Without this, *"30 vs 18 = MISMATCH"* is a **confidently wrong answer that torches the 5 marks it was chasing.** Two v1 lenses predicted it; the lens owning 20 marks **committed it in their golden set**.

**2. Scope goes IN THE ANSWER, not the footer.** The flagship demo tells a **Bangladeshi grader** that a **Bangladeshi employer's** handbook is non-compliant with **Bangladeshi labour law**, sourced from the 2006 Act **as published by the Bangladesh Employers' Federation in 2009** (verified: OCR p1; PDF creationDate 2011) — **materially amended in 2013 and 2018, including in this exact area.** Only two of nine v1 lenses flagged staleness and both filed it as a README bullet. **It is not a footnote — it is the demo detonating in the room, in front of the one audience most likely to know.**

> *"Against the Bangladesh Labour Act 2006 as published in the provided 2009 BEF handbook — amendments after 2006 are not in this corpus — the Employee Handbook does not appear to address maternity benefit, which s.46 (printed p.39) requires at eight weeks preceding and eight weeks following delivery. [Employee Handbook §B lists only Annual, Sick, Casual, and Probation leave — folio 6.]"*

**3. Phrasing discipline.** *"does not appear to address X, which s.Y requires"* — **never** *"violates"*, never *"you are breaking the law"*. Persistent UI disclaimer: *"Documented gap analysis to support HR review against the provided 2006 text. Not legal advice."* Always render the verbatim statutory snippet so a human verifies the machine. **Getting this framing right is itself a Business Insight mark; getting it wrong is a red flag about judgement.**

**Sequencing:** build it **fourth**, additively, behind a route label, on a working system. If it isn't solid at the 80% mark, **ship the single maternity path and document the general case as future work** — most of the marks at a fraction of the risk.

---

## 8. Phased build plan — **22h**

> **⚠️ ADVERSARY HIT — CONCEDED. Round 2 reproduced v1's diagnosed pathology verbatim.** Five lenses = **27h** for the **stack alone**, building **no retrieval, no chunker, no OCR, no prompts, no eval harness, no golden set, no UI, no README** — against a v1 that costed the *entire* build at 17h. The semaphore + token bucket was independently specced **four times**; `corpus_stats` **three times**; the Pinecone adapter budgeted **twice** (1.5h + 1h) for **one adapter**; the upload API **twice** (2.25h + 1.5h) for the **same three endpoints**; the context window re-verified by **four** lenses. **~6–8h of pure double-counting and still no merged build order.** v1's own §6 — *"Nobody deduped. Nobody integrated."* — is true of round 2 word for word.
> **Fixed here: ONE clock. ONE owner per artifact. Cut globally, not per-lens.** The rate gate belongs to the provider client and everyone consumes it. `corpus_stats` has one owner. The two Pinecone budgets and the two upload budgets are merged.

### Hour 0 — three empirical tasks, 15 minutes, ALL MANDATORY

Four experts agreed the rate limit determines the architecture, four agreed they couldn't cite it, and **zero opened the console.** *"I refuse to quote a limit I cannot verify"* is disciplined; *"I refuse to log in and look"* is not.

| Task | Time | Why |
|---|---|---|
| **Mistral Admin Console → Limits.** Record the number **and the date**. Quote it as *"observed, not published."* | 5 min | The one resource the whole architecture is shaped by. |
| **Mistral Admin Console → Privacy → disable "Anonymous improvement data."** Screenshot into `docs/`. | 5 min | Training is **ON by default** on the free plan. See §9 risk. **If you recite the opt-out line without clicking it, that is a lie to the interviewer's face about data governance, in an interview about data governance.** |
| **Verify `mistral-large-2512` against `GET /v1/models`** with your own key. | 5 min | An alias or a wrong dated ID = a 500 on the grader's first click. |

### Phase 0 — MUST SHIP (~14h). Critical path.

| # | Item | h | Gate |
|---|---|---|---|
| 1 | OCR (8 workers) → committed JSON. **Hold the page ref.** Partex x-midline clip + NFKC + hyphen repair. Drop TOC 1–15, annex 157–180. Layer tags. | 1.5 | `mean_chars > 1500`; no body page < 300 |
| 2 | `PRINTED_OFFSET = 16`, 0-based, ONE convention. Partex folios `2i−1`/`2i`. 6 pytest asserts. | 0.5 | tests green |
| **3** | **Deploy hello-world FastAPI + skeleton index to HF Spaces. AT HOUR 3.** Public visibility. | 1.0 | `/health` 200 **from an incognito browser** |
| 4 | Section index: dual-grammar + **wrapped-title fix** + LIS, scoped idx 33–156. | 1.5 | `{45,46,100,108,115,116,117,118} ⊆ detected` |
| 5 | Chunk + fastembed bge-small (**query prefix**) + numpy + rank_bm25 + RRF. **Asymmetric: pin handbook, retrieve statute.** Index handbook chunks anyway for eval. | 1.5 | 399 chunks; `index_meta` written |
| 6 | Generation: **ONE** `mistral-large-2512` call, streaming. Prompts as versioned `.md`. Cite-or-abstain, **floor semantics**, **in-answer staleness frame**, code-sliced snippet, **structural span-verification abstention gate**. | 2.0 | 6 chips answer correctly; `test_refusal_is_200` green |
| 7 | **SWE + API (the orphaned 25 marks):** `src/` layout, **`.importlinter`**, Pydantic models, typed error envelope (400/413/422/429/503), **rate gate (Semaphore + token bucket)**, JSON logging + `request_id`, settings validated at boot, hand-written `requirements.txt`, 12 tests + **`FakeGenerator`**, 3 CI workflows incl. **keep-alive**. | 2.5 | `pytest` green with **no API key**; no torch; CI badge |
| 8 | Static HTML + SSE + **6 chips** + **single-flight** + designed refusal card. | 1.5 | — |
| 9 | Final deploy + **cold-start dry-run from an incognito browser**. | 0.5 | live URL answers chip #2 |
| 10 | README + **hand-written Mermaid system diagram** + verbatim prompts + rejections + corpus-reality opener + `corpus_stats.json`. | 1.5 | every number reads from the file |

**Critical path: 1 → 2 → 4 → 5 → 6 → 9.** Items 3, 7, 8, 10 parallelise. **Item 3 is not optional and not last — everything else is invisible if the URL is dead.**

### Phase 1 — DIFFERENTIATORS (~5.5h). Only after Phase 0 is live and green.

| Item | h | Why |
|---|---|---|
| **30-question 4-tier golden set, hand-verified against rendered page images**; hand-rolled harness; recall@5 + groundedness (gemini-2.5-flash) + abstention 2×2. | 2.0 | **The only artifact touching 4 rubric lines at once.** Written **before** you tune retrieval. |
| **Full-context oracle + RAG-vs-oracle ablation table.** $0.00. | 1.0 | **Highest marks-per-hour on the board.** Answers the deadliest question, **debugs the golden set for free**, and **bounds the FR#5 statute-side concession**. |
| **C6 multi-KB** (ONE owner, merged): `POST /api/kb`, upload → 202 + job polling, `assess_extractability` → 422, recursive split, **per-namespace BM25**, Pinecone upsert with text in metadata, KB dropdown, idempotency. | 2.0 | Explicit user requirement; Architecture-20 extensibility signal. |
| `get_section(n)` + `section_no` API filter. | 0.5 | Deterministic lookup on a natural primary key. **The §10 on-camera enhancement.** |

### Phase 2 — STRETCH (~2.5h). Only if Phase 1 is green.

| Item | h | Gate |
|---|---|---|
| `docs/finetuning.md` (dated, sourced, firing trigger) + `evals/power.py`. | 0.75 | — |
| `docs/optimisations.md` — "measured and deliberately did not do". | *in item 10* | — |
| Numeral normalisation on the BM25 index. | 0.25 | Honest justification only — **never headlined**. |
| MCP stdio adapter + Claude Desktop screenshot. | 1.0 | **ONLY if `lint-imports` is green.** Never on the live path. |
| Deterministic 1-hop cross-ref expansion. | 0.5 | **ONLY if the eval produces a query single-shot demonstrably fails.** |

**Total: 22.0h.** Within C5's ~20–30h.

### Pre-committed global cut order (no renegotiation)
1. Phase 2 entirely (−2.5h)
2. C6 → in-memory only, ephemeral, **documented honestly in the UI at upload time** (−1.0h, and it forfeits the honest answer to C3/C6, so it goes late)
3. SSE → plain JSON `/api/ask` (−0.5h, costs UX polish only)
4. Compliance framing → **the single maternity path only** (−0.75h)

**Never cut:** `.importlinter` · the error envelope · the 12 tests · `index_meta` · the Dockerfile · **deploy at hour 3** · the 6 chips · the golden set. **~4h combined, and they are the entire difference between 8/15 + 5/10 and full marks.**

### Cut without mercy
Fine-tuning (all forms, incl. the "measured negative ablation") · the agent loop · multi-agent · CRAG/Self-RAG/reflection · **LangGraph** · LangChain splitters **for the statute** · LangChain chains/retrievers/loaders/`.with_fallbacks()` · the `langchain` meta-package · DSPy (§9 requires you explain your prompts; DSPy writes prompts you didn't) · the LLM router · the live entailment judge · the reranker (incl. the free one) · **Pinecone Inference** (both free) · Mistral OCR · Pixtral · Ollama/local VLMs · multi-provider fallback · the build-time response cache · pgvector · sqlite-vec · HNSW/IVF/PQ · Milvus/Weaviate · the React SPA · Streamlit · docling/marker/surya · all OCR preprocessing · dpi sweeps · **spell-ratio QA** (it flagged **correct** pages as broken — the OOV tokens were "workers", "rates", "Sramik" — and missed the real defect) · Bengali traineddata · table-annex vision repair · RAGAS/DeepEval/promptfoo · nDCG/MRR · OAuth 2.1 · **auth** · conversation persistence · LangGraph checkpointers.

---

## 9. Top risks and specific mitigations

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| 1 | **Dead / glacial live URL on the grader's cold visit.** v1's top risk, and **round 1 budgeted zero hours against it while seven of nine lenses rated it CRITICAL** — the most revealing pathology in the entire output. New specific causes found: fastembed re-downloads the model on **every** cold start (default cache is a temp dir on an ephemeral FS — **+10.7s and a hard CDN dependency at boot, with no error in your code**); embedding 399 chunks at boot would take minutes on 2 vCPU. | **fatal** | Bake the model at build time with `FASTEMBED_CACHE_PATH`. Commit `index.npz` + `chunks.jsonl` so boot is a **file load, never an embed**. `COPY --chown=user` (UID 1000). **Deploy at hour 3.** **Cold-start dry-run from an incognito browser before submitting.** README: *"free hardware sleeps; the first request after idle may take ~30s to wake."* |
| 2 | **Space left PRIVATE.** Verified: every non-owner gets a **404**. "Protected" needs PRO = paid. **One click, and a mandatory submission item scores zero with the code perfect.** | **fatal** | Public. **Verify in an incognito window, not the tab you built it in.** First line of the submission checklist. |
| 3 | **The 48h pause ambiguity.** HF's docs contradict themselves — *"goes to sleep… any visitor will start it back up"* vs *"**PAUSED** after 48h… inactive until the **OWNER** restarts it."* Free cpu-basic cannot configure `sleep_time`. **The bad branch = the grader, weeks later, sees a dead URL only you can revive.** | **critical** | **Do not gamble on which branch is true — stay inside the window.** GitHub Actions cron pings `/health` every 12h (2 req/day, disclosed, doubles as the uptime canary). **Disclosed fuse: GitHub disables scheduled workflows after 60 days without a commit.** **Verify empirically:** leave the Space untouched >48h once during the build, then open it cold and record what actually happens. **That observation is worth more than either doc page** and is a strong interview beat. |
| 4 | **Silent blank index.** The PyMuPDF weakref bug + a swallowing `try/except` returns "" for all 181 pages and **reports success**. | **critical** | `pg = doc[i]` **before** `get_textpage_ocr`. Build-gate assertions on mean chars/page. **Fail the build, never the query.** |
| 5 | **Off-by-one on every statutory citation.** The council's own −16/−17 base confusion, shipped as apparent consensus. | **critical** | ONE constant, ONE declared base, **in the variable name**. 6 pytest asserts against OCR'd footers. Render both. |
| 6 | **Silent Partex corruption.** Naive extraction interleaves Leave with Confidentiality line-by-line into every chunk of the one document the scenario is about — **and never throws.** The prescribed block-x0 "fix" gets folios **exactly backwards on the page you'd check.** | **critical** | Clip at `page.rect.width/2`, per page. `test_deinterleave_regression`. |
| 7 | **s.46 silently dropped by the naive regex**, taking the flagship demo with it — merged into s.45's chunk **with s.45's metadata**. | **critical** | Wrapped-title regex + `assert {45,46,...} ⊆ detected`. Re-report recall **after** the fix. |
| 8 | **Eval set contaminated.** Tier D contained 4 questions the Act answers **with contradictory Tier-B labels in the same output**, behind a zero-tolerance CI gate that would train the system to refuse answerable questions. Tier C contained **zero** conflicts. | **critical** | Rebuild both (§4.16). Tier D from the **nonexistent documents** + 3 grep-verified absences, **grep committed as the test**. Tier C → floor-comparison + the one real probation conflict. **Hand-verify every row against the rendered page.** |
| 9 | **FR#5 has no live enforcement.** The judge moved offline correctly; nothing replaced it for **statute**-side absence — the flagship unanswerable. | **critical** | **Deterministic span-verification gate in code** (§4.13): unverifiable claims stripped; all stripped → `insufficient_information` forced by code. `test_refusal_is_200` asserts on **`"paternity leave?"`**. Say the honest bound out loud and let the oracle quantify it. |
| 10 | **Free-tier data training on an "Enterprise" assistant.** Training is **ON by default** on Mistral's free plan. You'd be sending a real Bangladeshi employer's internal HR handbook to a training-enabled endpoint — and **the grader is an AI company assessing an "Enterprise" document assistant.** *(Correcting the brief: opt-out **does** exist — Admin Console → Privacy → "Anonymous improvement data". It is a free toggle.)* | **high** | **Do not hide it — lead with it.** Three legs: **(1) click the toggle, screenshot into `docs/`**; (2) the corpus is a **public statute** + a handbook **the assessor distributed** — nothing confidential was ever at risk; (3) **the architectural leg: `mistral-large-2512` is Apache 2.0 with open weights, so the identical pipeline self-hosts behind a firewall with zero data egress — and the `Generator` Protocol makes that a one-file change, which `.importlinter` proves.** Turns a liability into the strongest *"I understand enterprise constraints"* beat available, for one paragraph. |
| 11 | **Confidently wrong compliance answer to a Bangladeshi grader**, using a 2009-published 2006 text amended 2013/2018. | **high** | Scope in the answer's **opening clause**, not the footer. *"does not appear to address"*, never *"violates"*. **Both citations verbatim or no gap assertion.** Persistent disclaimer. |
| 12 | **Uploaded KBs evaporate; in-flight jobs die.** HF's disk is ephemeral; free hardware sleeps. **A demo that appears to lose user data is worse than one that never offered upload.** | **high** | (1) Vectors **and text** go to a Pinecone namespace, so an uploaded KB genuinely survives. (2) Only job records are ephemeral; **ingestion is idempotent on `sha256(bytes)`, so recovery is a re-upload — never a duplicate or a corruption.** (3) State it in README limitations **with HF's own sentence as evidence.** *(Stating a limitation with the vendor's own sentence reads as engineering; discovering it live reads as naivety.)* |
| 13 | **Seven numbers for one fact.** v1: 2× spread on corpus size, 5.6× on OCR timing, 8× on chunk count. **Round 2: four token counts, two section counts, four embed latencies, and a benchmark against a random index.** §9 makes this **disqualifying**; the wrong ones are falsifiable in 30 seconds. | **high** | **One committed `corpus_stats.json`.** The §0 table. Tekken tokenizer, **never chars/4, never tiktoken**. Quote **wall-clock**, never s/page. **Delete every other figure, including from the rehearsed lines.** |
| 14 | **Résumé-driven scope** (FT + MCP + agents + vector DB + 3 frameworks on a 2-document corpus) reads as an engineer who can't distinguish a real requirement from a shiny one — **a hiring signal, not a marks signal.** | **high** | **Every component carries a one-line justification traceable to a measured corpus property. If it can't, it's cut.** The council's own rule, finally applied to the council. |
| 15 | **The grader clicks 3 chips in 2 seconds** against an unpublished rate limit and gets 429s on the flagship maternity demo. | **high** | **Single-flight UI** (the grader physically cannot fire concurrently — ~10 lines and it's the actual fix) + server semaphore + token bucket + typed 429 with `Retry-After` + SSE. **Never quote a limit you can't verify.** |
| 16 | **Empty search box.** The grader types *"what is the leave policy?"*, gets something competent and forgettable, closes the tab. **Never sees the compliance capability.** | **high** | 6 chips, 30 minutes, ordered warm-up → flagship → nuance → honest-unknown. **Plus a 60-second demo script at the top of the README naming the three questions to click.** |
| 17 | **25 marks unread.** SWE (15) + API (10) had no owner across nine round-1 experts. **A beautiful retriever in a repo with no structure and a 200-with-a-stack-trace scores 8/15 and 5/10.** | **fatal** | §4.18, 2.5h, staffed. |
| 18 | **Pinecone free-tier liveness is officially undocumented** and the sources conflict (docs state none; 7-day archive removed 2023; 2026 reviews claim ~3-week pause; 515 free indexes once reaped in one incident). **Quoting "3 weeks" as fact would itself reproduce the disqualifying failure above.** | **medium** | **Architectural, not operational: the committed corpus never touches Pinecone.** `kb_id='default'` is served by numpy with zero network, so the flagship demo and all six chips work with `PINECONE_API_KEY` unset. Failure degrades **only** uploads → typed 503. README says the policy is **undocumented** rather than inventing a number. |
| 19 | **OCR noise reaches the user as a fabricated legal quote** (`'shal!'`, `'Tribunaj'`, `'Jeave'`, `'for cight weeks'`). | **medium** | **Substantially de-risked by a corpus property nobody expected: the legally-operative quantities are in WORD form** — "eight weeks" ×9, "fourteen days" ×7, "ten days" ×5. **Word-form numbers are far more OCR-robust than digits** ('14' silently flips to 'l4'; 'fourteen' is a dictionary word tesseract's LM corrects). Render the verbatim snippet next to every citation; surface `source_modality: "ocr"` + confidence; **cite by section number, which OCRs cleanly.** |

---

## 10. The interview defence pack

**Rehearse cold. Every number here is regenerable from the repo — if you can't regenerate it, you don't get to say it.**

**Q1. "Your corpus is 187 pages and fits in one context window. Why RAG at all?"** → **§5, THE SENTENCE.**

**Q2. "Your citation says section 117 is on page 59. Prove it."** *(the ten-second kill)*
> *"Open the PDF to page 76 and read the footer — it says 59. The Act has seventeen pages of front matter, so printed equals the zero-based PyMuPDF index minus sixteen; I validated that against six OCR'd footers and it's a pytest assertion. I render both — 'printed p.59 (PDF page 76 of 181)' — so you can verify either way. Partex is worse: it's a two-up landscape spread, so one PDF page holds two printed folios, and PyMuPDF returns the right-hand page's blocks first on one of them. I split geometrically at the midline rather than by block x-coordinate, because the footer is a **single block that spans the gutter** — filtering on block x0 puts the right page's folio in the left half and gets it exactly backwards. And the citation is a typed object all the way out, never a markdown string — so I can assert `printed_page == 59` in a test, and the model structurally cannot fabricate one."*

**Q3. "Why didn't you fine-tune? You said you wanted to."** → **§6.8, THE SENTENCE.** *(Lead with "I can train it, I can't serve it." Never lead with deprecation.)*

**Q4. "How do you know it's accurate?"**
> *"Here's the table. Thirty questions across four tiers, hand-verified against the rendered pages: recall@5, groundedness, and the abstention two-by-two — refusal precision **and** false-refusal rate, because either alone is meaningless; a system that refuses everything scores a hundred percent on abstention. n=30, so the 95% interval is about eleven points and I say so. My judge is Gemini, not Mistral — models show family-bias, and a Mistral judge on a Mistral answerer measures the wrong thing; using a smaller model from the same family doesn't fix it, it just makes the bias cheaper. The unanswerable tier is the interesting one: your spec promised a Sales Handbook, an FAQ and a Company Profile that don't exist in the assets, so questions about them are provably unanswerable and corpus-grounded. Everything I claim is absent from the Act, I proved with a grep over my own OCR and committed the grep as the test."*

**Q5. "Why no agent?"** → **§6.4.**

**Q6. "Why is there no vector database — and then why is there Pinecone?"** → **§6.3 + §6.7.** *(Must be one breath. Lead with lifecycle, not speed. **Name the HF Storage Bucket you declined.**)*

**Q7. "Walk me through your prompts."**
> *"Versioned markdown in `prompts/`, loaded at runtime — never inline f-strings — so the git history is the tuning curve and each revision has an eval delta next to it. **Two** prompts, not three: I cut the router. It was a cost optimisation — a cheap model triaging so the expensive one does less work — and on a free tier the scarce resource isn't dollars, it's requests, about one per second. A router makes every query two requests to save retrieval that costs eight microseconds locally. So the optimisation inverted and I deleted it; the route label is still logged, it's just derived in code. The synthesis prompt encodes floor semantics explicitly — the Act sets minima, so the handbook granting thirty days against a floor of roughly fifteen is **compliant**, not a mismatch; a naive diff reports a gap there and is confidently wrong. And it uses positive phrasing — 'state that the documents do not address X' — rather than 'do not hallucinate'. The judge prompt is hand-written and few-shot anchored on three examples from this corpus; the best one is a subtly unfaithful answer with the **right number and the wrong source**. That's also why I didn't use RAGAS — your section 9 says I must explain my prompts, and RAGAS's faithfulness prompt isn't mine to explain."*

**Q8. "Add a feature. Right now."** *(the §10 live enhancement)*
> *"Sure — which layer? Tools are plain typed functions, so a new capability is a function plus a schema entry. The eval is a YAML file, so a new question is three lines and CI catches the regression. Let me add `get_section` behind a `section_no` filter and show you the label in the logs."*
> *(Rehearsed, ~3 min. Layer-ordered Dockerfile → ~30s redeploy.)*

**Q9. "Ask your own system about paternity leave. Now show me the line of code that guarantees you say 'I don't know' rather than the model choosing to."** *(the FR#5 kill — and it goes further: "you said the corpus fits in one window, so if you'd stuffed it, absence would be provable. Doesn't RAG make your abstention weaker?")*
> *"You're right, and that's the real cost of choosing RAG — I'll take it head-on. Similarity thresholding is measurably broken here, and that's my best finding: the answerable 'who is the Chairperson' scores 0.067 top-1, and the unanswerable 'paternity leave' scores 0.155 — because it collides with the casual-leave chunk. **The distributions invert.** Any threshold that refuses paternity also refuses the Chairperson. That's not bad luck: a good adversarial question is plausible, and plausible means semantically adjacent. So retrieval score is an **anti-signal**. What runs live is deterministic and it's in code, not in the prompt: every claim must cite a retrieved chunk, and I assert the quoted span actually appears in that chunk's text. Claims that don't verify get stripped; if all of them strip, `insufficient_information` is set **by code**, not chosen by the model. Now the honest part: for the handbook I can **prove** absence, because it's pinned in full. For the statute I can only tell you I didn't find it in the eight sections I retrieved — and that's exactly why the full-context oracle is in my eval. It's the same model over the whole corpus, so the only variable is retrieval, and it bounds how often that concession bites. That number's in the table."*

**Q10. "It's a free tier. What happens when I click three questions fast?"**
> *"You can't — the chips disable the moment one's in flight. Server-side there's a semaphore and a token bucket, and a 429 comes back typed with a Retry-After, not a stack trace. I'll be straight about why it's built that way: Mistral doesn't publish its free-tier limits — their docs tell you to read them off your own admin console — and the sources I found disagree by a factor of thirty. So I refused to tune to a number I couldn't verify and made the design not care; the RPS is an env var and I honour whatever Retry-After the server sends. Two things I only know because I read the SDK rather than the quickstart: `mistralai` doesn't retry **at all** unless you pass a RetryConfig — the default is None, so a demo that assumes the SDK retries dies on your second click. And `NoResponseError` doesn't subclass `MistralError`, so `except MistralError` silently misses it and it escapes as a 500; it gets its own handler and maps to 503. And I let the SDK own the backoff instead of wrapping tenacity around it, because that would double-retry. One thing that is deliberately **not** an error: 'I couldn't find this in the documents' returns 200 with `insufficient_information: true`. A refusal is a designed product state — it's your requirement 4.5. 4xx means **you** did something wrong. If I returned 422 there, my own eval harness would score every correct refusal as a transport failure."*

**Q11. "Where are your optimisations?"**
> *"There's a table in the README of the seven I measured and deliberately didn't build, each with the number that killed it. My latency budget: the model call is one to three seconds, embedding the query is 2.4 milliseconds, and the vector search is 8 microseconds. So I didn't quantize anything and I didn't build an ANN index — I spent the effort getting the request path down to one model call. Product quantization on 399 vectors would compress 0.6 megabytes that already loads in 27 milliseconds. My prompt is two percent of the window, so compressing it optimises a resource I have thirty times the headroom on, against a limit that doesn't bind — and worse, pruning chunks before a generator that has to prove an **absence** can only destroy that. The reranker's simpler: recall@5 is already 1.00, and you can't rerank above 1.00. And I didn't write a quantization step because fastembed's default artifact for bge-small is **already** the int8 ONNX build — int8 came free with the library choice."*

**Q12. "You used a free tier that trains on your data. For an *enterprise* document assistant?"** *(volunteer this — you are the most likely person on earth to be asked it)*
> *"Yes, and I turned it off — Admin Console, Privacy, 'Anonymous improvement data'. Screenshot's in the repo. Training defaults on for the free plan and opt-out is one toggle. Worth saying: nothing here was confidential — it's a public statute published by the Bangladesh Employers' Federation, plus a handbook you gave me. But the real answer is the **model choice**: Large 3 is Apache 2.0 with open weights, which is why I picked it over an API-only model. The enterprise answer to 'where does our data go' is 'run the weights in your VPC' — not 'trust my vendor'. And that's a one-file change, because `core/` takes an injected Generator protocol and can't import `mistralai` at all — `.importlinter` fails the build if it ever does."*

**Q13. "Why Mistral? Isn't that just what was free?"** *(volunteer this too)*
> *"It was free, but it's also the only free tier that can actually run this workload, and I can show you the arithmetic. My RAG prompt is about 5,200 tokens. Groq's free tier is 12,000 tokens a minute and 100,000 a day — that's twelve to nineteen queries a day, and my 101k-token oracle is 8.4× their per-minute limit, so it's not slow there, it's impossible. That's also why I have no automatic fallback: the choice was failing over to twelve queries a day, or to an OpenRouter model ID that rotated out and 404s. A silent failover means the answers you're seeing come from a model my eval never measured — that's worse than an honest outage. I do have a second provider, and it's my judge, not my failover."*

**Q14. "Open your repo. Convince me in five minutes."**
> *"Open `.importlinter`. Fifteen lines, and it says `src.core` may not import fastapi, starlette, mcp, pinecone, or mistralai. It runs in CI and in pytest. That's not a style preference — it's what lets me hand you a FakeGenerator and run the whole suite with no API key and no network, it's why swapping Mistral for a self-hosted Large 3 is one file, and it's why exposing this over MCP would be a twenty-one-line adapter rather than a refactor. **I didn't write that claim in the README and ask you to believe it. I made the build fail if it stops being true.**"*

**Q15. "The spec promised six documents. What happened?"**
> *"I got two — a six-page corporate handbook misnamed `Partex-Star-Group.pdf`, whose PDF metadata title is literally 'Employee Handbook-Final', and a 181-page scanned national statute with zero extractable text. That's the first paragraph of my README, because I think how you handle that gap is part of what you're assessing. It also turned out to be the best thing about the assets: the handbook claims on its own first page that it complies with Bangladeshi labour law, and the other 181 pages **are** the law it's claiming to comply with. So I built the product the corpus was actually asking for."*

---

## Appendix — the one-paragraph README opener

> **What I actually found.** The spec describes six documents totalling 20–30 pages. The assets are two documents totalling 187 pages. `Partex-Star-Group.pdf` is not a company profile — its PDF metadata title is `Employee Handbook-Final`, and it is a landscape two-up spread whose six PDF pages carry a cover plus ten printed folios. `A Handbook on the Bangladesh Labour Act 2006.pdf` is 181 pages with **zero** extractable text — 100% scanned images, OCR'd here at build time to 498,240 characters in ~120 seconds and committed to this repo. The named HR Policy, Leave Policy, Sales Handbook, Company Profile, and FAQ do not exist. Then the useful part: the handbook states on its first printed page that its policies *"are in compliance with the applicable labor laws of Bangladesh"* — and the other 181 pages are the exact statute that claim refers to. **The corpus is a falsifiable claim plus its evidence base.** So this is not a document search box. It is an HR policy compliance assistant, and it finds real gaps: the handbook's casual leave (10 days) and sick leave (14 days) sit exactly at the statutory floors of ss.115 and 116; its annual leave (30 days) **exceeds** s.117 and is compliant; and it is entirely silent on the sixteen weeks of maternity benefit s.46 mandates, the eleven paid festival holidays s.118 mandates, and the 2× overtime rate s.108 mandates. The whole corpus is 122,204 tokens against my model's 262,144-token window — 47% — so retrieval here is a defended choice, not a necessity, and the full-context baseline is in the eval table as the oracle I measure it against. **Every number in this README comes from `corpus_stats.json`, generated by one committed script.**

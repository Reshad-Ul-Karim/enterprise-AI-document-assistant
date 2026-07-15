# Implementation Roadmap — Enterprise AI Document Assistant

**Status:** blueprint, ratified. **Budget: 22h.** Stack: Mistral + open source, **zero billing, no card on file**, free deployment.

This is the *what* and *when*. The *why* — every rejected alternative and the measurement that killed it — lives in
[`docs/DECISION_RECORD.md`](docs/DECISION_RECORD.md), produced by a 21-agent expert council across two adversarial rounds.
Read this file to build. Read that one before the interview.

---

## 0. The one-number rule

**One committed script emits `corpus_stats.json`. Every number in the README, the diagram, and your interview prep reads from
that file. Nothing else is quoted, ever.**

This rule exists because round 1 produced *seven* contradictory "measured" values for one fact, and round 2 — knowing that —
produced four token counts, two section counts, and benchmarked the vector store against a **randomly generated index**.
The assessment says *"You must fully understand your implementation."* A candidate who quotes seven numbers for one fact does not,
and each wrong number is falsifiable in 30 seconds.

Ground truth, re-measured and reproduced independently (some by me, directly, this session):

| Fact | Value | Method |
|---|---|---|
| Labour Act OCR characters | **498,240** | tesseract 5.5.2, `dpi=200`, 8 workers — *reproduced byte-exact, twice* |
| OCR wall clock | **~98s** | 8 workers, M2. Quote wall-clock, **never s/page** |
| Corpus tokens (full) | **122,204** | Tekken v13 tokenizer — **never chars/4, never tiktoken, never `MistralTokenizer.v3()`** |
| Corpus tokens (indexed scope) | **101,100** | same |
| Handbook tokens (clipped) | **3,166** | same |
| `mistral-large-2512` context | **262,144** | Mistral model card, fetched 2026-07 |
| Sections detected | **342 from 343 raw hits** | dual-grammar + LIS, idx 33–156 |
| Chunks | **399** (388 statute + 11 handbook) | sub-split >2000 chars |
| Index size | **0.596 MB** | 399 × 384 float32 |
| Exact cosine + top-8 | **0.0083 ms** | mean of 2000, **real** embedded chunks |
| Query embed (bge-small) | **2.4 ms** | mean of 50 |

**Delete on sight — these are poisoned numbers from superseded drafts:**
`113,240` · `134,631` · `128k window` · `43%` · `481 vectors` · `0.023 ms` · `35.1 ms` · `333 of 335` ·
`"BM25 misses s.116"` · `"MDE ~11pp at n=30"` · `"omitting the bge prefix costs recall"` · `"RAG is forced"`.

**Ratio to quote** (robust, unfalsifiable): model call **seconds** ≫ query embed **milliseconds** ≫ vector search **microseconds**.
Do not quote "1,500×".

---

## 1. What you are actually building

The spec describes six documents totalling 20–30 pages. **The assets are two documents totalling 187 pages**, and five of the six
named documents do not exist. That gap is not an obstacle to route around — it is the most interesting thing about the assignment,
and how you handle it is part of what is being assessed.

| Spec claims | Reality |
|---|---|
| 6 documents | **2** |
| 20–30 pages | **187** |
| Text-native | **97% scanned** — the Act has **zero** extractable text |
| `Employee Handbook.pdf`, `HR Policy.pdf`, `Leave Policy.pdf`, `Sales Handbook.pdf`, `Company Profile.pdf`, `FAQ.pdf` | `Partex-Star-Group.pdf` (**is** the Employee Handbook; metadata title `Employee Handbook-Final`; landscape **2-up spread**) and `A Handbook on the Bangladesh Labour Act 2006.pdf` (181p, 100% scanned) |

**The product insight that decides the architecture.** Handbook folio 1 states verbatim:

> *"The human resource (HR) policies and procedures contained in this handbook are in compliance with the applicable labor laws
> of Bangladesh."*

The other 181 pages **are that law**. The corpus is *a falsifiable claim plus its evidence base*. So this is not a document search
box — it is an **HR policy compliance assistant**, and it finds real, citable gaps. That framing is the only decision that converts
the corpus mismatch from a liability into the differentiator, and it targets AgamiSoft's actual market: Bangladeshi employers
governed by this exact statute.

### The three traps that fail silently

Every one of these produces *plausible wrong output with no exception*, which is this corpus's signature failure mode.

1. **Partex is a landscape 2-up spread.** Naive extraction interleaves two unrelated policies into one chunk. Worse, PyMuPDF returns
   the **right-hand folio's blocks first**. Verified directly: naive page idx 3 emits `6 / employee handbook / 5 / employee handbook…`.
   → Clip geometrically at `page.rect.width/2`. **Not** by block `x0` — the footer is a single block spanning the gutter, so an x0
   filter puts the right folio's number in the left half and gets it **exactly backwards on the page the grader would check**.
2. **s.46 — the flagship demo — is silently dropped** by the obvious regex. Its title wraps a line, so `[^:;\n]{3,95}` cannot match,
   and s.46 merges into s.45's chunk **carrying s.45's metadata**. You would ship a clean recall number and a confidently wrong
   citation on the one question the grader remembers.
3. **Printed page ≠ PDF index, differently in each document.** The Act has 17 pages of front matter. FR#4 demands page numbers, and
   this is a ten-second check for a grader.

### The abstention finding (the best original work in the record)

FR#5 — *"clearly state that sufficient information is unavailable"* — is the highest-signal requirement in the spec, and most
candidates will satisfy it with a prompt line and a similarity threshold, untested.

**Similarity thresholding is measurably broken on this corpus.** Reproduced independently, with different chunking, same conclusion:

| | query | top-1 | best match |
|---|---|---|---|
| ✅ answerable | Who is the Chairperson? | **0.179** | Handbook folio 1 |
| ✅ answerable | How much overtime pay is required? | **0.224** | Act s.108 |
| ❌ **unanswerable** | How many days of **paternity** leave? | **0.413** | Act s.115 *Casual leave* |

`SEPARABLE BY A THRESHOLD? -> False`. Any threshold that refuses paternity also refuses the Chairperson. This is not bad luck:
**a good adversarial question is *plausible*, and plausible means semantically adjacent. Retrieval score is an anti-signal.**

→ Abstention is enforced **structurally, in code** (§4), never by a threshold and never by asking the model nicely.

*(Exact values depend on chunker and vectoriser config — regenerate them from the committed script. Do not quote these.)*

---

## 2. Rulings — the short version

| Component | Ruling | One-line reason |
|---|---|---|
| **RAG** | **KEEP**, reframed | Corpus is 122,204 tok / 262,144 window = **46.6%. It fits.** RAG is a *defended choice*, and the oracle proves it. |
| **Generation** | `mistral-large-2512`, **pinned** | 256k ctx, Apache 2.0 **open weights**, `temperature=0`, streaming. Never `-latest` (an alias re-pointing mid-assessment = dead demo). |
| **Embeddings** | fastembed `BAAI/bge-small-en-v1.5`, 384d, **local** | A remote embedder spends the *scarcest* resource (requests) on what local hardware does in 2.4 ms free. bge-base measured recall@5 = 1.00 **both** — 768d buys nothing. |
| **Vector store** | **numpy for the committed corpus, Pinecone for uploads** | The axis is **data lifetime**, not speed. A file for what ships in the image; a database for what arrives after. |
| **Retrieval** | Hybrid BM25 + dense, **RRF k=60**, top-8, whole-section expansion | Asymmetric: **pin the handbook (3,166 tok), retrieve only the statute**. |
| **Router** | **CUT** | It was a *cost* optimisation. On a free tier dollars aren't scarce — **requests** are. A router doubles requests/query to save 8µs. **The optimisation inverted.** |
| **Reranking** | **CUT** (even though free) | recall@5 = **1.00**. You cannot rerank above 1.00 — and it *promotes* the handbook/statute near-duplicates (Jaccard 0.53), amplifying the one case that matters most. |
| **Agents** | **CUT** | The single named justification (s.100 defers to s.108) is **factually false** — the 10-hour cap is in s.100's own sentence. No lens across two rounds produced a failing query. |
| **LangGraph** | **CUT** (mandated; declined) | Its only unique claim — `draw_mermaid()` makes the required diagram — is false; the rubric wants a *system* diagram it cannot draw. Revival gate written down: **≥5 real nodes, ≥2 branch points.** |
| **LangChain** | **`langchain-text-splitters`, uploads ONLY** | Use the framework where complexity is **foreign**; write it yourself where it **is** the thing being graded. |
| **Pinecone** | **KEEP for uploads only** | Namespace-per-KB **fails closed**. Not necessary (HF Storage Buckets exist and are free) — **say so**; claiming otherwise is falsifiable in one click. |
| **Fine-tuning** | **CUT, all four forms** | **I can train it; I cannot serve it.** Free hosting has no GPU. And it structurally fights your own multi-KB requirement. |
| **MCP** | **CUT from build, README paragraph + Phase 2 gate** | Zero rubric lines. Value is crossing a trust boundary; there isn't one between my FastAPI and my retriever. |
| **Judge** | `gemini-2.5-flash`, **cross-family**, offline | Different tier ≠ different family. **The zero-cost constraint made the eval *more* valid.** |
| **Deploy** | HF Spaces free, Docker, port 7860 | 16 GB RAM. **Deploy hello-world at hour 3, not hour 12.** |

**Everything is cut unless it carries a one-line justification traceable to a measured property of this corpus.**

---

## 3. Repository layout

```
src/
  core/          # retrieval, chunking, sections, verification — ZERO protocol imports (MACHINE-ENFORCED)
    models.py        Pydantic: Chunk, Citation, Answer
    pagemap.py       PRINTED_OFFSET=16, partex_folios()
    sections.py      dual-grammar regex + LIS + build gate
    chunking.py      section-aware; sub-split >2000; per-definition for s.2
    embeddings.py    fastembed bge-small, query prefix
    retrieval.py     numpy cosine + BM25 + RRF; Retriever Protocol
    generator.py     Generator Protocol (NO mistralai import)
    verification.py  span verification -> insufficient_information
  ingest/        # OCR, extraction, index build, uploads — a real CLI
    ocr.py           tesseract, 8 workers, build-time only
    extract.py       Partex x-midline clip; NFKC; hyphen repair; exclusions
    build_index.py   -> index/index.npz, chunks.jsonl, index_meta.json
    corpus_stats.py  -> corpus_stats.json   (THE one-number rule)
    upload.py        langchain-text-splitters; the ONLY file importing it
  api/           # FastAPI, Pydantic models, error envelope, rate gate
    main.py  routes.py  errors.py  settings.py  rategate.py  logging.py
    providers/mistral.py   # the ONLY file importing mistralai
prompts/         # versioned .md loaded at runtime — NEVER inline f-strings
data/extracted/  # committed OCR JSON (~0.6 MB)
index/           # committed index.npz + chunks.jsonl + index_meta.json
evals/           # golden.yaml, harness.py, power.py, oracle_answers.json
tests/  docs/  static/
```

**`.importlinter` is the highest-leverage artifact in the build.** ~15 lines, wired as a pytest case so `pytest` alone proves it:

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

Two gotchas that make copy-pasted blog configs fail: `include_external_packages = True` is **required** when forbidding external
modules, and `root_packages` must be an **indented list, not inline**. `src/__init__.py` must exist.

> **This is why it matters:** *"I didn't write that claim in the README and ask you to believe it. I made the build fail if it stops
> being true."* It is what lets you hand the suite a `FakeGenerator` and run with **no API key and no network**; it is why swapping
> Mistral for self-hosted weights is one file; and it is why MCP would be a 21-line adapter rather than a refactor.

---

## 4. Architecture, component by component

### Ingestion — build-time, committed, never at runtime

**The split that makes free hosting survivable:** OCR, chunking and embedding run **once, on your Mac**. The artifact is committed.
The runtime image contains **no tesseract, no Ollama, no torch, no PDFs**. Ingestion is an offline batch pipeline; serving is a
stateless online service. Being able to draw that line *is* an architecture-marks answer.

- tesseract 5.5.2 via `pymupdf.get_textpage_ocr(dpi=200, full=True)`, `ProcessPoolExecutor(max_workers=8)`, **zero preprocessing**.
  Reopen the PDF once per worker (per-page opens were the measured bottleneck).
- Committed: `data/extracted/*.json`, `index/index.npz` (0.596 MB), `chunks.jsonl`, `index_meta.json` — **~2 MB, plain git, no LFS.**
- Exclusions, as **hardcoded constants citing their evidence**, not a heuristic classifier:
  - `TOC_RANGE = range(1, 16)` — dot-leader junk, lexically shadows every real heading. **Keep idx 16 (`PREFACE`).**
  - `ANNEX_RANGE = range(157, 181)` — ILO table → `'This / aw / is / not / in / force / in'`. Tagged `kind="table_unreliable"`,
    documented as a **deliberate, measured exclusion** — which outscores a half-working table parser and demonstrates FR#5 in the
    ingestion layer.
  - Layers: idx 17–32 = commentary **about** the Act; idx 33–156 = the Act **verbatim**. `get_section` indexes idx 33+ only.
- **Bengali OCR is a non-issue and knowing why is the point:** zero Bengali codepoints in 498,240 chars; s.354 is titled
  *"Original Text and Authentic English Text"* — this document **is** the authentic English text. One README line.

**Rejected:** Mistral OCR (needs a card; and the free run is one-time on your Mac anyway) · Pixtral / Ollama VLMs (build-time only,
no GPU on free hosting, and tesseract already OCRs at 94% mean confidence in 98s) · docling/marker/surya · all preprocessing ·
dpi sweeps · **spell-ratio QA** (it flagged *correct* pages as broken — the OOV tokens were "workers", "rates", "Sramik" — and missed
the real defect).

### Page fidelity — ONE constant, ONE declared base

```python
PRINTED_OFFSET = 16                 # printed = zero_based_pdf_index - 16
BODY_RANGE     = range(17, 157)     # printed 1..140
FRONT_MATTER   = range(0, 17)       # idx 16 == PREFACE == 'xvi'
# Partex: idx 0 = cover; for idx 1..5: left = 2*idx-1, right = 2*idx
```

Variables are `zero_based_pdf_index` and `printed_page`. **Never `page`. Never bare `idx`.** v1's council split 2–2 between offset
16 and 17 — they were not disagreeing, they used undeclared bases, which is **worse than disagreeing because it reads as
corroboration**. *A one-off is worse than a seventeen-off: seventeen looks like a bug, one looks like sloppiness the grader cannot bound.*

Verified against six OCR'd footers: idx 19→3, 40→24, 55→39, 75→59, 76→60, 90→74.

### Chunking

Dual-grammar regex + **longest-increasing-subsequence** over section numbers, scoped `layer == "statute"`. The Act uses **two**
header grammars (`N. Title : (1)` and `N. Title.— (1)`); a greedy monotonic scan gives 82% recall because one stray high number
poisons everything after it. LIS rejects the false positives the regex admits.

```python
SECTION_RE = re.compile(
    r"^\s{0,6}(\d{1,3})\s*[.,]\s+"
    r"([A-Z][^:;\n]{3,95}(?:\n[^:;\n]{1,60})?)"   # <-- allows ONE wrapped title line
    r"\s*[|!,.\s]{0,3}(?:[:;]|[—–-]{1,2}\s*\()",
    re.M,
)
```

**Build gate — fail the build, not the demo:** `assert {45,46,100,108,115,116,117,118} <= set(detected)`.
Do **not** anchor on roman chapter numerals — OCR mangles them (`XIL`, `Vv`, `Vill`); arabic digits survive.

Shape: 342 sections, median **594** chars. Sub-split only >2,000 chars (1,200 window / 1,000 stride) carrying parent metadata.
**Do not merge short sections — a short section is a complete legal unit.** s.2 (Definitions, 66 terms) sub-splits **per definition**.
Partex chunks per printed half-page. **399 total.**

### Retrieval — asymmetric, not stratified

**Pin the entire handbook; retrieve only over the statute.** The handbook is 3,166 tokens. *Retrieval over a document that already
fits can only lose information.* This eliminates the 37:1 base-rate problem **by construction** rather than by tuning a quota you'd
have to defend, and it makes *"the handbook is silent on maternity"* a **sound claim** rather than an inference from a failed top-k.

**Still index the 11 handbook chunks** (30 seconds) so recall@k is measurable across both documents — otherwise Retrieval Accuracy
is measured over 97% of the corpus while the document the scenario is about is invisible to it.

Statute: hybrid BM25 + dense, **RRF k=60** (no alpha to justify), top-8, small-to-big to the full parent section, assembled in
**section-number order** — statutes read sequentially.

**Why hybrid *here*, not the generic reason:** `gratuity` appears 10× in 61k body word-tokens, `retrenchment` 14× — rare high-IDF
terms of art where BM25 is near-perfect and dense blurs them into `compensation` (120×). Conversely *"can my boss make me work
overtime?"* has zero lexical overlap with the governing sections. **And the "OCR is noisy so BM25 breaks" argument is measured
false** — only 2 corrupted tokens in 61,098.

### Generation + abstention

**One LLM call per query.** Prompts are versioned `.md` loaded at runtime — never inline f-strings, because §9 requires you to
explain them and the git history is then your tuning curve.

**Abstention is a deterministic, non-LLM structural gate. Code, not goodwill. Zero extra LLM calls:**

1. **Handbook silence is *provable*** — it is pinned in full. Falls out of the asymmetric design for free.
2. Every claim must cite a retrieved chunk. **The verbatim snippet is sliced from the chunk by code, never generated.**
3. **Span verification:** assert the quoted span appears in the cited chunk (NFKC-normalised, whitespace-collapsed). A claim whose
   span does not verify is **stripped**. All stripped → `insufficient_information = true`, **forced by code, not chosen by the model**.
4. **Statute silence is *bounded*, not proved — and you say so.** *"For the handbook I can prove absence. For the statute I can only
   say I didn't find it in what I retrieved — and the oracle bounds how often that's wrong."* Choosing RAG re-introduces exactly the
   unprovability FR#5 needs; the honest concession is stronger than a fake guarantee.
5. **Measure the false-refusal rate.** A gate you haven't measured for over-triggering is a gate you can't defend.

**Refusal is `200 OK` + `insufficient_information: true` + populated `related_citations`** — never 422. A designed product state is
not an HTTP error; 4xx means the *caller* was wrong. Returning 422 would make your own harness score every correct refusal as a
transport failure.

**Citations are typed Pydantic objects the whole way out — never markdown strings.** A markdown citation is unassertable; you cannot
write `assert c.printed_page == 59` against `'— printed p.59 (PDF page 76)'` without a regex. Rendering happens in the UI from a
typed object, **so the model never emits a citation string and structurally cannot fabricate one.**

Format — print **both**, anchor on the section number:

```
Bangladesh Labour Act 2006, s.117 Annual leave with wages — printed p.59 (PDF page 76 of 181)
Employee Handbook (Partex Star Group), printed p.6 (PDF page 5, right half)
```

Printed matches what the document says about itself; PDF matches the grader's scrollbar; **the section number is the statute's
actual primary key — stable regardless of pagination, and it OCRs cleanly where footers do not** (`'ll'` for 11, `'Az'` for 47).
The harness asserts on the **section number**. `doc_title` comes from a **curated manifest, never the filename**.

### API

```
POST /api/ask            · POST /api/ask/stream (SSE)
GET  /health   → {status, index_loaded, chunk_count, index_version, kb_count, model_id, pinecone_reachable}  # 503 if index absent
GET  /api/documents → curated manifest (real page counts + modality; NEVER the filename)
POST /api/kb                        → 201
POST /api/kb/{kb_id}/documents      → 202 + Location: /api/jobs/{job_id}
GET  /api/jobs/{job_id}             → {state, progress, doc_id?, error?}
GET  /api/kb                        → describe_index_stats()['namespaces'] — the KB list for free
```

Typed error envelope, real codes: **400** malformed · **413** >32 MB · **422** semantic (scanned PDF upload) · **429** upstream rate
limit **echoing upstream `Retry-After` into both header and body** · **503** index not loaded / `NoResponseError`.
**Never a 200 with a stack trace.**

**Two SDK facts you only learn by reading the source, not the quickstart:**
- `mistralai`'s `retry_config` defaults to **`None`** — it does **not retry at all** unless you pass one. A demo that assumes the SDK
  retries dies on the grader's second click. *(And let the SDK own backoff — wrapping tenacity around it double-retries.)*
- **`NoResponseError` does not subclass `MistralError`** — `except MistralError` silently misses it and it escapes as a 500.
  It gets its own handler → 503.

### Rate limiting — the grader clicks three chips in two seconds

**Single-flight UI** (chips disable while one is in flight — ~10 lines, and it's the actual fix) + server `Semaphore` + token bucket
+ typed 429 with `Retry-After`. **Never quote a limit you haven't verified** — Mistral doesn't publish free-tier numbers; read your
own console, record the number *and the date*, and quote it as *"observed, not published."* The RPS is an env var and you honour
whatever `Retry-After` the server sends, so the design doesn't care.

### Multi-KB (C6)

`kb_id` is on every chunk. `namespace='kb_hr_2024'` per KB — **fails closed** (a metadata filter you forget *leaks across tenants*;
a namespace you forget *returns nothing*; when the whole feature is separation, fail-closed beats fail-open). 100 namespaces/index
is the right primitive by **20×** over 5 indexes.

**Chunk text rides in Pinecone metadata** (chunks 0.6–2 KB vs a 40 KB cap, ~20× headroom) so an upload survives a restart
**completely — vectors *and* text — with no second datastore.** `assert len(json.dumps(md)) < 40_000` at upsert: **fail the ingest,
never the query.**

Uploads get the **same hybrid path** — build `BM25Okapi` per-namespace in memory at upload (~milliseconds). Handing the grader a
demonstrably worse pipeline built from components you'll spend the interview rejecting is not an "honest asymmetry."

**Degrade path — the cold-visit insurance policy:** `PINECONE_API_KEY` unset → uploads return typed **503**; the baseline demo and
all six chips work with **zero network calls**. `/health` reports `pinecone_reachable` as a field **separate** from `index_loaded`.

**Honest limitation for the README:** job records are in-process and die on restart. Ingestion is idempotent on `sha256(bytes)`, so
recovery is a re-upload — never a duplicate or a corruption. *State a limitation with the vendor's own sentence as evidence; that
reads as engineering. Discovering it live reads as naivety.*

### Frontend

FastAPI-served static HTML + fetch + SSE. **6 seeded question chips — the highest-ROI 30 minutes in the build, non-negotiable.**
The grader cannot invent good questions about a Bangladeshi labour statute; an empty box means they type *"what is the leave
policy?"*, get something competent and forgettable, and close the tab **without ever seeing the compliance capability.**

Ordered to build an arc — warm-up → flagship → nuance → honest unknown:

1. *"How many days of casual leave am I entitled to?"* — handbook says 10 **and** s.115 says 10. Both agree. Shows the citation UI.
2. **FLAGSHIP:** *"Does our Employee Handbook comply with the Bangladesh Labour Act on maternity leave?"* — reasoning about an
   **absence**. ss.45/46 mandate 16 weeks; the handbook is silent while claiming compliance on folio 1.
3. *"We work Sun–Thu 9–5 and Sat 9:00–1:30. Is that legal?"* — 44.5h ≤ 48h (s.102) ✓; weekly holiday **exactly** at s.103(a)'s
   minimum. A nuanced *"compliant, and only just"* proves reasoning, not pattern-matching.
4. *"How much overtime pay is required?"* — handbook silent; s.108 = 2× ordinary rate.
5. *"What is the parental leave policy?"* — the honest, **designed** "I don't know." Verified absent from both.
6. *"Who is the Chairperson and where is the head office?"* — Sultana Hashem; Shanta Western Tower L-13, Tejgaon, Dhaka-1208.

**Rejected:** React SPA (6h → 0.83 marks/hour against a 5-mark line, plus a build step, a static path and a CORS surface — three new
ways for the live URL to die) · Streamlit (you must build FastAPI anyway for the separate 10 API marks, so a static page is *less* work).

### Deploy

**HF Spaces free** — 16 GB RAM, Docker on **port 7860**, `/tmp`-only writes. Render free is 512 MB + spindown.

**Bake the embedding model at BUILD time.** fastembed's default cache is a temp dir and HF's disk is ephemeral, so an unbaked model
re-downloads on **every cold start** (+10.7s and a hard dependency on HF's CDN at boot — a CDN hiccup boots the Space broken, on the
grader's click, with no error in your code). Baked: 0.5s.

**No torch** (~254 MB vs ~2.5 GB). The reason is **cold start**, not "it can't boot" — HF Spaces has 16 GB, and saying otherwise is a
credibility grenade. Hand-write `requirements.txt`; **never `pip freeze`**. CI gate: `assert not importlib.util.find_spec('torch')`.

**Deploy hello-world at hour 3.** A deploy that works at hour 3 and gets richer ships. A deploy attempted at hour 12 is a coin flip
at 11pm when onnxruntime needs a wheel the base image doesn't have. **Test an actual cold start from an incognito browser before
submitting** — the grader may open your URL weeks later.

### Eval

Hand-rolled, ~150–200 LOC, **30 hand-verified questions**, **three metrics only: recall@5 · groundedness · the abstention 2×2**.
Fold citation-correctness *into* groundedness (*"is this claim entailed by the cited section?"* answers both) — the highest-value
collapse available. **Report the 2×2 confusion matrix, never refusal rate alone** — a system that refuses everything scores 100%.

**Write the golden set BEFORE the retrieval pipeline** — the questions come from the PDFs, not from what the system happens to do well.

| Tier | n | Content |
|---|---|---|
| **A — Handbook only** | 8 | hours, dress code, transport, canteen, lunch/prayer, Chairperson, founded 1962 by M.A. Hashem, appraisal |
| **B — Statute only** | 8 | s.46 maternity 16wk (p.39), s.118 eleven festival holidays (p.60), s.108 overtime 2× (p.57), s.24 due process (p.32), s.138/140 min wage, s.33 grievance, s.26 notice, trade unions |
| **C — Floor comparison** | 8 | *renamed from "conflict".* casual 10 = s.115 floor · sick 14 = s.116(1) floor · annual 30 **>** s.117 → **compliant** · 44.5h ≤ 48h · weekly holiday exactly at minimum · **the probation carve-out — the one real conflict** |
| **D — Unanswerable** | 6 | **3 × the nonexistent documents** (Sales Handbook commission, FAQ, Company Profile) + WFH, paternity, pension — **each grep-verified, grep committed as the test** |

> **Tier D's construction is the one no other candidate will build — because no other candidate will notice the assets don't match
> the spec.** The spec *promises* a Sales Handbook and an FAQ; questions about them are **provably** unanswerable and corpus-grounded.

**Two contamination failures to never repeat** (both committed by round 1's own eval lead, who owned 20 marks):
- Tier D listed overtime, minimum wage, grievance and notice as "verified TRULY ABSENT" — **all four are in the Act**, and the *same
  output* listed two of them under Tier B ("MUST ANSWER"). Contradictory gold labels in one deliverable, behind a zero-tolerance CI
  gate — **so the harness would fail the build when the system correctly cites s.108.**
- Tier C listed *"casual (both say 10)"* as a **conflict**. Those are exact **matches**. s.117 is a statutory **floor**
  (*"shall be allowed… at the rate of"*), so 30 > 18 **exceeds → compliant**. **Graded against that set, correct answers would have
  been penalised.**

**Judge: `gemini-2.5-flash`** — free, no card, **cross-family**, offline in the harness only. v1 chose Haiku to judge Opus —
*"different tier, cheap insurance"* — but that's **different tier, same family**, and models exhibit documented family-bias. It bought
insurance that does not insure. **`mistral-small` judging `mistral-large` reproduces the identical error for free.** If `GEMINI_API_KEY`
is absent the harness **skips groundedness and says so** rather than silently scoring 0.

**Few-shot anchor the judge with 3 examples from this corpus.** Anchor #2 is the highest-value few-shot in the build:
*"You get 30 days annual leave [Labour Act s.117]"* — **right number, wrong source.** A naive judge waves it through.

**The full-context oracle — highest marks-per-hour on the board, and now free.** 101,100 tokens fits the 262,144 window at 38.6%.
Run it on the **same model** as the RAG path, so the only variable in the ablation is retrieval. *(A cross-provider oracle would be
**dishonest** — it conflates retrieval loss with model difference. Same model or no oracle.)* 30 × 101,100 = 3.03M tokens ≈ **0.3% of
the free monthly allowance = $0.00.** Cap at 4 calls/min; run **once**; commit `evals/oracle_answers.json`; **never on the live path.**
It debugs your golden set for free, and it is what **bounds the FR#5 statute-side concession**.

**Groq physically cannot run it** (101k is 8.4× its 12K TPM) — this is the one workload that proves Mistral was the right provider on
**engineering grounds, not preference**.

**Honest reporting: n=30 → 95% CI ≈ ±10.7pp at a 90% score. Say so.** Report the harness commit SHA. Do not invent a Cohen's κ you
didn't compute — hand-check the ~5 judge verdicts that disagree with your expectation and report that as *"spot-checked."*

**Rejected:** RAGAS/DeepEval/promptfoo — **spec-level, not taste:** §9 requires you to explain your prompts, and *RAGAS's faithfulness
prompt is not yours to explain*. None models the two-authority-level structure anyway. · nDCG/MRR (needs graded relevance; you have
binary labels) · 50–60 questions (hand-verification is what makes the number real, and it is the budget — **30 you checked beats 60 you didn't**).

---

## 5. The compliance differentiator — three hard rules

**Time-boxed to 1.5h.** It is a system prompt plus 3 questions over the *identical* RAG core. Build it **fourth**, additively,
behind a route label, on a working system.

| Topic | Handbook | Labour Act 2006 | Verdict |
|---|---|---|---|
| Casual leave | 10 days | s.115 "ten days" (p.59) | **At the floor** |
| Sick leave | 14 days | s.116(1) "fourteen days" (p.59) | **At the floor** |
| Annual leave | 30 days | s.117 1 per 18 worked ≈ 14–17 (p.59) | **Exceeds → COMPLIANT** |
| Working hours | 44.5h | s.100 8h→10h (p.56), s.102 48h | **Compliant** |
| Weekly holiday | 1.5 days | s.103(a) minimum | **Compliant, and only just** |
| **Maternity** | **0 occurrences** | ss.45/46 = **16 weeks** (p.39) | **GAP** |
| **Festival holidays** | 0 (only *"Festival Bonus"*, a payment) | s.118(1) **eleven paid days** (p.60) | **GAP** |
| **Overtime** | **0 occurrences** | s.108 **2× rate** (p.57) | **GAP** |
| **Due process** | §L *"as deemed appropriate by the management"* | s.24 (p.32) written charge + ≥7 days + hearing | **CONFLICT** |
| **Probation carve-out** | *"leave after completion of probation"* | s.115/116 *"**Every** worker"* | **CONFLICT** |

*(The nuance that proves you read it: s.117 **does** require one year of continuous service, so annual leave during probation is
fine — the carve-out only conflicts for casual and sick.)*

**1. Floor semantics are encoded in the prompt, not hoped for.**

> *"The Act sets statutory MINIMA. If the handbook grants at or above the statutory minimum, it is COMPLIANT — report it as such.
> Report a gap ONLY where the handbook grants LESS than the floor, or is SILENT on a mandatory entitlement. Cite both sources
> verbatim with printed page numbers. Never assert a gap without both citations."*

Without this, *"30 vs 18 = MISMATCH"* is a **confidently wrong answer that torches the 5 marks it was chasing.**

**2. Scope goes IN THE ANSWER, not the footer.** The flagship demo tells a **Bangladeshi grader** that a **Bangladeshi employer's**
handbook is non-compliant with **Bangladeshi labour law**, from the 2006 Act as published by the BEF in **2009** — materially amended
in **2013 and 2018**, including in this exact area. **It is not a footnote — it is the demo detonating in the room, in front of the
one audience most likely to know.**

> *"Against the Bangladesh Labour Act 2006 as published in the provided 2009 BEF handbook — amendments after 2006 are not in this
> corpus — the Employee Handbook does not appear to address maternity benefit, which s.46 (printed p.39) requires at eight weeks
> preceding and eight weeks following delivery."*

**3. Phrasing discipline.** *"does not appear to address X, which s.Y requires"* — **never "violates."** Persistent disclaimer:
*"Documented gap analysis to support HR review against the provided 2006 text. Not legal advice."* Always render the verbatim
statutory snippet so a human verifies the machine. **Getting this framing right is itself a Business Insight mark; getting it wrong
is a red flag about judgement.**

---

## 6. Build plan — 22h

### Hour 0 — three empirical tasks, 15 minutes, ALL MANDATORY

Four experts agreed the rate limit shapes the architecture, four agreed they couldn't cite it, and **zero opened the console.**
*"I refuse to quote a limit I cannot verify"* is disciplined; *"I refuse to log in and look"* is not.

| Task | Why |
|---|---|
| **Mistral Console → Limits.** Record the number **and the date**. Quote as *"observed, not published."* | The one resource the architecture is shaped by. |
| **Mistral Console → Privacy → disable "Anonymous improvement data."** Screenshot into `docs/`. | Training is **ON by default** on the free plan. **Reciting the opt-out without clicking it is a lie to the interviewer's face about data governance, in an interview about data governance.** |
| **Verify `mistral-large-2512` against `GET /v1/models`** with your own key. | A wrong dated ID = a 500 on the grader's first click. |

### Phase 0 — MUST SHIP (~14h). Critical path.

| # | Item | h | Gate |
|---|---|---|---|
| 1 | OCR (8 workers) → committed JSON. Partex x-midline clip + NFKC + hyphen repair. Drop TOC 1–15, annex 157–180. Layer tags. | 1.5 | `mean_chars > 1500`; no body page < 300 |
| 2 | `PRINTED_OFFSET = 16`, ONE convention. Partex folios `2i−1`/`2i`. 6 pytest asserts. | 0.5 | tests green |
| **3** | **Deploy hello-world FastAPI + skeleton index to HF Spaces. AT HOUR 3.** Public visibility. | 1.0 | `/health` 200 **from incognito** |
| 4 | Section index: dual-grammar + **wrapped-title fix** + LIS, idx 33–156. | 1.5 | `{45,46,100,108,115,116,117,118} ⊆ detected` |
| 5 | Chunk + fastembed bge-small (query prefix) + numpy + rank_bm25 + RRF. **Asymmetric.** Index handbook chunks anyway. | 1.5 | 399 chunks; `index_meta` written |
| 6 | Generation: **ONE** `mistral-large-2512` call, streaming. Prompts as versioned `.md`. Cite-or-abstain, floor semantics, staleness frame, code-sliced snippet, **span-verification gate**. | 2.0 | 6 chips correct; `test_refusal_is_200` green |
| 7 | **SWE + API (the orphaned 25 marks):** `src/` layout, **`.importlinter`**, Pydantic models, error envelope, **rate gate**, JSON logging + `request_id`, settings validated at boot, hand-written `requirements.txt`, 12 tests + **`FakeGenerator`**, 3 CI workflows incl. keep-alive. | 2.5 | `pytest` green **with no API key**; no torch |
| 8 | Static HTML + SSE + **6 chips** + **single-flight** + designed refusal card. | 1.5 | — |
| 9 | Final deploy + **cold-start dry-run from incognito**. | 0.5 | live URL answers chip #2 |
| 10 | README + **hand-written Mermaid system diagram** + verbatim prompts + rejections + corpus-reality opener + `corpus_stats.json`. | 1.5 | every number reads from the file |

**Critical path: 1 → 2 → 4 → 5 → 6 → 9.** Items 3, 7, 8, 10 parallelise.
**Item 3 is not optional and not last — everything else is invisible if the URL is dead.**

### Phase 1 — DIFFERENTIATORS (~5.5h). Only after Phase 0 is live and green.

| Item | h | Why |
|---|---|---|
| 30-question 4-tier golden set, **hand-verified against rendered pages**; harness; recall@5 + groundedness + abstention 2×2. | 2.0 | **The only artifact touching 4 rubric lines at once.** |
| **Full-context oracle + ablation table.** $0.00. | 1.0 | Highest marks-per-hour. Answers the deadliest question, debugs the golden set, **bounds the FR#5 concession**. |
| **C6 multi-KB:** `POST /api/kb`, upload → 202 + job polling, `assess_extractability` → 422, recursive split, per-namespace BM25, Pinecone upsert with text in metadata, KB dropdown, idempotency. | 2.0 | Explicit requirement; Architecture-20 extensibility signal. |
| `get_section(n)` + `section_no` filter. | 0.5 | **The §10 on-camera enhancement.** |

### Phase 2 — STRETCH (~2.5h). Only if Phase 1 is green.

| Item | h | Gate |
|---|---|---|
| `docs/finetuning.md` (dated, sourced, **firing** trigger) + `evals/power.py`. | 0.75 | — |
| Numeral normalisation on the BM25 index. | 0.25 | Honest justification only — **never headlined**. |
| MCP stdio adapter + Claude Desktop screenshot. | 1.0 | **ONLY if `lint-imports` is green.** Never on the live path. |
| Deterministic 1-hop cross-ref expansion. | 0.5 | **ONLY if the eval produces a query single-shot demonstrably fails.** |

### Pre-committed global cut order (no renegotiation)

1. Phase 2 entirely (−2.5h)
2. C6 → in-memory only, ephemeral, **documented honestly in the UI at upload time** (−1.0h; forfeits the honest C3/C6 answer, so it goes late)
3. SSE → plain JSON (−0.5h, costs UX polish only)
4. Compliance framing → **the single maternity path only** (−0.75h)

**Never cut:** `.importlinter` · the error envelope · the 12 tests · `index_meta` · the Dockerfile · **deploy at hour 3** · the 6 chips ·
the golden set. **~4h combined, and they are the entire difference between 8/15 + 5/10 and full marks.**

### Cut without mercy

Fine-tuning (all forms, incl. the "measured negative ablation") · the agent loop · multi-agent · CRAG/Self-RAG/reflection ·
**LangGraph** · LangChain splitters **for the statute** · LangChain chains/retrievers/loaders/`.with_fallbacks()` · **the `langchain`
meta-package** (not installing it makes the rejection *structural rather than aspirational*) · DSPy (§9 requires you explain your
prompts; DSPy writes prompts you didn't) · the LLM router · the live entailment judge · the reranker (incl. the free one) ·
Pinecone Inference (creates **two embedding spaces** — silently incomparable results) · Mistral OCR · Pixtral · Ollama/local VLMs ·
multi-provider fallback · pgvector · sqlite-vec · HNSW/IVF/PQ · Milvus/Weaviate · React SPA · Streamlit · docling/marker/surya ·
all OCR preprocessing · spell-ratio QA · Bengali traineddata · RAGAS/DeepEval/promptfoo · nDCG/MRR · OAuth 2.1 · auth ·
conversation persistence · LangGraph checkpointers.

---

## 7. Top risks

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| 1 | **Dead live URL** — a mandatory submission item, zero regardless of code quality. Seven of nine v1 lenses called this critical and **zero budgeted for it.** | **fatal** | Deploy at **hour 3**. Cold-start dry-run from incognito. Committed index, no boot-time fetch. |
| 2 | **Partex 2-up interleave** — silent, and it corrupts the document the business scenario is about. | **critical** | x-midline clip. `test_deinterleave_regression`. |
| 3 | **s.46 dropped** — takes the flagship demo, with s.45's metadata attached. | **critical** | Wrapped-title regex + build gate. Re-report recall **after** the fix. |
| 4 | **Eval contamination** — contradictory gold labels behind a zero-tolerance CI gate would train the system to refuse answerable questions. | **critical** | Tier D from the nonexistent documents + grep-verified absences, **grep committed as the test**. Hand-verify every row. |
| 5 | **FR#5 unenforced** — prompt-only refusal on a graded requirement inside the 20-mark line. | **critical** | Deterministic span-verification gate in code. `test_refusal_is_200` asserts on **`"paternity leave?"`**. |
| 6 | **Free-tier data training on an "enterprise" assistant** — ON by default, and the grader is an AI company. | **high** | **Lead with it, don't hide it.** (1) Click the toggle, screenshot into `docs/`. (2) The corpus is a public statute + a handbook the assessor distributed. (3) **`mistral-large-2512` is Apache 2.0 — the identical pipeline self-hosts behind a firewall, and `.importlinter` proves it's a one-file change.** |
| 7 | **Confidently wrong compliance answer** to a Bangladeshi grader from a 2009-published, 2013/2018-amended text. | **high** | Scope in the **opening clause**. *"does not appear to address"*, never *"violates"*. Both citations verbatim or no gap assertion. |
| 8 | **Uploaded KBs evaporate** — a demo that appears to lose user data is worse than one that never offered upload. | **high** | Text **and** vectors to Pinecone. Idempotent on `sha256`. State it in README limitations **with HF's own sentence as evidence.** |
| 9 | **Seven numbers for one fact** — §9 makes this disqualifying. | **high** | One `corpus_stats.json`. Delete every other figure, **including from rehearsed lines.** |
| 10 | **The grader clicks 3 chips in 2 seconds** → 429 on the flagship demo. | **high** | Single-flight UI + semaphore + token bucket + typed 429. |
| 11 | **Empty search box** → competent, forgettable, tab closed, compliance capability never seen. | **high** | 6 chips + a **60-second demo script at the top of the README naming the three questions to click.** |
| 12 | **Résumé-driven scope** reads as an engineer who can't tell a real requirement from a shiny one — a **hiring** signal, not a marks signal. | **high** | Every component carries a one-line justification traceable to a measured corpus property. If it can't, it's cut. |

---

## 8. Interview defence pack

Rehearse cold. **Every number here is regenerable from the repo — if you can't regenerate it, you don't get to say it.**

**Q. "Your corpus fits in one context window. Why RAG at all?"**
> *"I measured it — 122,204 tokens with Mistral's own tekken tokenizer, against Large 3's 262,144. It's 47%, so you're right, it
> fits, and I built the full-context version. It's in my eval as the oracle: it's the ceiling I measure retrieval against, and the
> gap is [X]. I ship RAG for three reasons — your rubric grades Retrieval Accuracy as its own fifteen marks and you can't score that
> without a retriever; citation provenance is by construction when a chunk carries its own page, whereas a context-stuff invents
> page numbers; and it doesn't survive the six-document corpus your spec described. I don't defend it on cost."*

**Q. "Your citation says s.117 is on page 59. Prove it."** *(the ten-second kill)*
> *"Open the PDF to page 76 and read the footer — it says 59. The Act has seventeen pages of front matter, so printed equals the
> zero-based index minus sixteen; I validated that against six OCR'd footers and it's a pytest assertion. I render both. Partex is
> worse: it's a two-up landscape spread, and PyMuPDF returns the right-hand folio's blocks first. I split geometrically at the
> midline rather than by block x-coordinate, because the footer is a single block spanning the gutter — filtering on x0 gets it
> exactly backwards. And the citation is a typed object all the way out, never a markdown string, so I can assert
> `printed_page == 59` in a test and the model structurally cannot fabricate one."*

**Q. "Why no agent?"**
> *"I don't have one, and I want to tell you why, because I planned one. I counted 121 cross-references and that looked like
> multi-hop. Then I went hunting for a query single-shot actually gets wrong. The example everyone reaches for is section 100's
> eight-hour cap deferring to section 108 — except I read section 100, and the ten-hour exception is in section 100's own sentence;
> 108 is the overtime pay rate, a different question. Section-aware chunking already handles it. I couldn't find a failing query, so
> I wrote no loop. And on a free tier at one request per second, an agent's extra hops aren't milliseconds, they're seconds."*

**Q. "Why is there no vector database — and then why is there Pinecone?"** *(must be one breath; lead with lifecycle, not speed)*
> *"Two stores, and the property that decides between them is lifecycle, not speed. The committed corpus is 399 vectors — 0.6
> megabytes, exact cosine in 0.008 milliseconds. Putting that in Pinecone would make your cold visit depend on someone else's free
> tier and an inactivity policy that isn't documented. So it's a file that loads at boot with zero network. Uploaded KBs are
> different data with a different lifetime: Spaces' disk is ephemeral, so they have to live off-box. One Retriever protocol, two
> backends, both on live traffic. I'll be straight about the alternative: HF Storage Buckets are free, first-party and mount
> read-write — they'd have reused my numpy store with one fewer vendor. I chose Pinecone for the namespace primitive, because
> isolation that fails closed beats a metadata filter you can forget."*

**Q. "Why didn't you fine-tune? You said you wanted to."**
> *"Four reasons, and I'll lead with the one that ends it: I can train it, I just can't serve it. QLoRA on a 7B is about seven
> gigabytes and under thirty minutes on my M2 — that part's genuinely easy. But you require a live URL, and free hosting has no GPU.
> ZeroGPU needs a PRO subscription, it's Gradio-only so it'd take out the FastAPI layer you're scoring for API design, and an
> unauthenticated visitor — you, clicking my link — gets two minutes a day. Second, Mistral's hosted path is served from a URL with
> 'deprecated' in it and bills four dollars a job plus two a month. Third, and this is what actually decided it: you want to upload
> new document sets as separate knowledge bases. A fine-tune is keyed to one corpus; every new KB is a retrain. Fine-tuning and
> extensibility are mutually exclusive here, and extensibility is the requirement. Fourth, at n=30 my minimum detectable effect is
> twenty-nine points and a realistic embedding fine-tune gains two to eight — my power is 4.6%. That's `evals/power.py`."*

**Q. "But there must be SOME fine-tune worth doing. The embedder?"** *(invite this)*
> *"You've found the right one. bge-small is thirty-three million parameters — trains on my CPU in minutes, deploys as the same ONNX
> file the app already loads. Free, local, deployable. None of my other reasons touch it. I didn't do it, and the reason is a
> measurement, not a principle. Its only motivation is a lexical gap: the Act writes 'fourteen days', users type '14 sick days'. So I
> ran the retriever. BM25 ranks section 116 **first**. Because 'sick' appears in two of three hundred and forty-two sections — a
> decisive high-IDF anchor, and the digit free-rides. The gap only appears on anchorless queries like '14 days?', and there dense
> misses too, so fine-tuning the embedder wouldn't fix it either. Forty lines of numeral normalisation does. I had a fine-tune that
> was free, fast and deployable, and I still didn't ship it — because I measured the thing it was supposed to fix and it wasn't broken."*

**Q. "How do you know it's accurate?"**
> *"Here's the table. Thirty questions across four tiers, hand-verified against the rendered pages: recall@5, groundedness, and the
> abstention two-by-two — refusal precision **and** false-refusal rate, because either alone is meaningless. n=30, so the interval is
> about eleven points and I say so. My judge is Gemini, not Mistral — models show family-bias, and a Mistral judge on a Mistral
> answerer measures the wrong thing; a smaller model from the same family doesn't fix it, it just makes the bias cheaper. The
> unanswerable tier is the interesting one: your spec promised a Sales Handbook and an FAQ that don't exist in the assets, so
> questions about them are provably unanswerable. Everything I claim is absent from the Act, I proved with a grep and committed the
> grep as the test."*

**Q. "Show me the line that guarantees you say 'I don't know' rather than the model choosing to."**
> *"Similarity thresholding is measurably broken here, and it's my best finding: the answerable 'who is the Chairperson' scores lower
> top-1 than the unanswerable 'paternity leave', because paternity collides with the casual-leave chunk. **The distributions invert.**
> Any threshold that refuses paternity refuses the Chairperson. That's not bad luck — a good adversarial question is plausible, and
> plausible means semantically adjacent. So retrieval score is an anti-signal. What runs live is deterministic and in code: every
> claim must cite a retrieved chunk, and I assert the quoted span appears in that chunk. Claims that don't verify get stripped; if
> all strip, `insufficient_information` is set **by code**, not chosen by the model. Now the honest part: for the handbook I can
> prove absence because it's pinned in full. For the statute I can only tell you I didn't find it in the eight sections I retrieved —
> which is exactly why the oracle is in my eval. Same model, whole corpus, so the only variable is retrieval, and it bounds how often
> that concession bites."*

**Q. "Why Mistral? Isn't that just what was free?"** *(volunteer this)*
> *"It was free, but it's the only free tier that can run this workload, and I can show you the arithmetic. My RAG prompt is about
> 5,200 tokens. Groq's free tier is 12,000 tokens a minute — that's twelve to nineteen queries a day, and my 101k-token oracle is
> 8.4× their per-minute limit, so it's not slow there, it's impossible. That's also why I have no automatic fallback: the choice was
> failing over to twelve queries a day, or to an OpenRouter model ID that rotated out and 404s. A silent failover means the answers
> you're seeing come from a model my eval never measured — worse than an honest outage. I do have a second provider: it's my judge,
> not my failover."*

**Q. "You used a free tier that trains on your data. For an *enterprise* assistant?"** *(volunteer this — you are the most likely person alive to be asked it)*
> *"Yes, and I turned it off — Admin Console, Privacy, 'Anonymous improvement data'. Screenshot's in the repo. Worth saying: nothing
> here was confidential — it's a public statute plus a handbook you gave me. But the real answer is the model choice: Large 3 is
> Apache 2.0 with open weights, which is why I picked it over an API-only model. The enterprise answer to 'where does our data go' is
> 'run the weights in your VPC' — not 'trust my vendor'. And that's a one-file change, because `core/` takes an injected Generator
> protocol and can't import `mistralai` at all — `.importlinter` fails the build if it ever does."*

**Q. "Open your repo. Convince me in five minutes."**
> *"Open `.importlinter`. Fifteen lines, and it says `src.core` may not import fastapi, starlette, mcp, pinecone, or mistralai. It
> runs in CI and in pytest. That's not a style preference — it's what lets me hand you a FakeGenerator and run the whole suite with no
> API key and no network, it's why swapping Mistral for self-hosted weights is one file, and it's why MCP would be a twenty-one-line
> adapter rather than a refactor. **I didn't write that claim in the README and ask you to believe it. I made the build fail if it
> stops being true.**"*

**Q. "The spec promised six documents. What happened?"**
> *"I got two — a six-page handbook misnamed `Partex-Star-Group.pdf`, whose metadata title is literally 'Employee Handbook-Final',
> and a 181-page scanned statute with zero extractable text. That's the first paragraph of my README, because how you handle that gap
> is part of what you're assessing. It also turned out to be the best thing about the assets: the handbook claims on its own first
> page that it complies with Bangladeshi labour law, and the other 181 pages **are** that law. So I built the product the corpus was
> actually asking for."*

**Q. "Add a feature. Right now."** *(the §10 live enhancement — rehearse it, ~3 min)*
> Add `get_section(n)` behind a `section_no` filter. Tools are plain typed functions; the eval is a YAML file, so a new question is
> three lines and CI catches the regression. Layer-ordered Dockerfile → ~30s redeploy.

---

## 9. The correction that matters most

**Do not "fix" the best answer in the record.**

This roadmap's principal briefed the round-2 council that *"Mistral Large is 128k, the corpus is ~128k, it does not fit, RAG is
FORCED, rewrite v1's headline."* **That was wrong on both halves** — Large 3 is 262,144, and the corpus is 122,204 measured with the
correct tokenizer. All four lenses refused the premise and went to primary sources.

Had that been rehearsed, the interviewer pulls up the model card and **the credibility of every other measured claim dies with it** —
the "seven numbers for one fact" disqualification, self-inflicted at the headline. *"RAG is forced"* is not a stronger position.
**It is not available.**

The lesson generalises, and it is the discipline this whole build runs on: **measure the thing, don't reason about it.** Round 1's
agent justification, its "96% unreachable" statistic, its "BM25 misses s.116" risk, and its own eval tiers were all *plausible
inferences that dissolved the moment someone ran the code.* Three of them were about to become headline interview answers.

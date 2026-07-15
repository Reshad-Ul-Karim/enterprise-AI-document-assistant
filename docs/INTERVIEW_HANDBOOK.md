# Interview Handbook — walking through this solution

**Audience: you, from zero.** This assumes you have never built RAG before and explains every
concept you will be asked about, in the order the interview will ask about it.

**The session is 30–45 minutes.** Four things happen: you demo it, you explain your design
decisions, you defend your trade-offs, and — possibly — you modify the code live.

> **The one rule.** Every number in here is regenerable by running `python -m src.ingest.corpus_stats`.
> **If you cannot regenerate a number, you do not get to say it.** The fastest way to lose this
> interview is to quote a figure that turns out to be wrong; the reviewer then discounts
> *everything* else you measured. This is not hypothetical — it happened during this project's own
> design process, and §9 covers it.

---

## Part 0 — The concepts, in plain language

Learn these six. Everything else in the interview is built from them.

**LLM (Large Language Model).** A model that predicts text. It knows nothing about *your*
documents. Ask it about Partex's leave policy and it will invent something plausible, because
producing plausible text is the only thing it does. That single fact is why this project exists.

**RAG (Retrieval-Augmented Generation).** Three steps: **find** the relevant bits of your
documents, **paste** them into the model's prompt, **ask** the question. The model answers from
text you supplied instead of from memory. "Retrieval" = the finding, "augmented" = the pasting,
"generation" = the answering.

**Embedding.** A model that turns text into a list of numbers (here, 1024 of them) positioned so
that *similar meanings land near each other*. "How much holiday do I get?" lands near "annual
leave with wages" even though they share no words. Comparing two embeddings = measuring the angle
between two arrows. That's **cosine similarity**: 1.0 = identical direction, 0 = unrelated.

**Chunk.** Documents are too big to embed whole, so you cut them into pieces. **How you cut is a
real engineering decision, and it is where most of this project's difficulty lives.** Cut badly
and you merge three different leave entitlements into one blob with one wrong page number.

**BM25.** Keyword search — the classic algorithm behind search engines. It rewards **rare** words:
if "gratuity" appears in only 10 places, a document containing it is very likely the one you want.
Embeddings understand *meaning*; BM25 nails *exact rare terms*. We use both ("hybrid search")
because this corpus needs both — see §3.

**Vector database.** A database specialised in "find the nearest embeddings." We use one for
uploads only, and §5 explains why using one for the main corpus would be a mistake.

---

## Part 1 — The 60-second demo (rehearse this cold)

Open the live URL. **Do not** start by explaining architecture. Show it working, in this order —
the order is an arc, and it is deliberate.

**Chip 1 — "How many days of casual leave am I entitled to?"**
> *"Ten days. It cites the handbook, printed page 6, with the exact sentence — and I can click
> through to that page and check. And note both documents agree here: the handbook says ten, and
> section 115 of the Act also says ten. It sits exactly at the statutory floor."*

**Chip 2 — "Does our Employee Handbook comply with the Labour Act on maternity leave?" ← THE ONE THAT MATTERS**
> *"This is the one I'd point you at. The handbook says on its own first page that it complies with
> Bangladeshi labour law. It never mentions maternity — zero occurrences. Section 46 mandates
> sixteen weeks. So the system reports a **gap**, cites the Act verbatim, and reasons about
> something that **isn't there** — which a search box fundamentally cannot do."*

**Chip 3 — "What is the parental leave policy?"**
> *"And here it says it doesn't know. That's the designed state, not an error — it's requirement
> 4.5. It still tells you what it searched and shows the closest related material, section 46 on
> maternity. And crucially that refusal is forced by code, not chosen by the model. I'll show you
> the line."*

**Then stop and let them ask.** Three chips, ninety seconds. You have shown: citations with page
numbers, cross-document reasoning, and honest refusal — which is the whole rubric.

---

## Part 2 — The story: what the assets actually were

**Open with this. It reframes everything and it is true.**

> *"The spec described six documents, twenty to thirty pages. I got two documents, 187 pages. Five
> of the six named files don't exist. `Partex-Star-Group.pdf` isn't a company profile — its PDF
> metadata title is literally `Employee Handbook-Final`. And the Labour Act is 181 pages with zero
> extractable text: it's a photograph of a book.*
>
> *That gap is the first paragraph of my README, because I think how you handle it is part of what
> you're assessing.*
>
> *Then I noticed the useful part. The handbook claims on its first page that its policies 'are in
> compliance with the applicable labor laws of Bangladesh' — and the other 181 pages **are** that
> law. **The corpus is a claim plus the evidence base that tests it.** So I didn't build a search
> box. I built a compliance assistant."*

**Why this works:** it converts your weakest fact (the assets were a mess) into your strongest
(you noticed, and you built the product the corpus was actually asking for). It also targets
AgamiSoft's real market — Bangladeshi employers governed by this exact statute.

### The gaps are real, not narrative

| Topic | Handbook | Act | Verdict |
|---|---|---|---|
| Casual leave | 10 days | s.115 "ten days" | At the floor |
| Sick leave | 14 days | s.116 "fourteen days" | At the floor |
| Annual leave | 30 days | s.117 ≈ 1 per 18 worked | **Exceeds → compliant** |
| **Maternity** | **0 mentions** | ss.45/46 = **16 weeks** | **GAP** |
| **Overtime** | **0 mentions** | s.108 = **2× rate** | **GAP** |
| **Festival holidays** | 0 (only a *bonus*, a payment) | s.118 = **11 paid days** | **GAP** |

**The nuance that proves you read it:** s.117 *does* require one year of continuous service, so the
handbook's "leave after probation" rule is fine for **annual** leave — it only conflicts for casual
and sick, where the Act says "**every** worker" with no probation qualifier. Knowing that is the
difference between having read the statute and having grepped it.

---

## Part 3 — The pipeline, stage by stage

Draw this on the whiteboard. **The horizontal line is the most important thing on it.**

```
BUILD TIME (my laptop, once)          │  RUNTIME (the free server, every request)
──────────────────────────────────────┼──────────────────────────────────────────
scanned PDF → OCR → sections →        │  question → embed → search → ONE model call
chunks → embeddings → index file      │  → verify citations in code → answer
                    ↓ committed to git ↑
```

### Stage 1 — OCR (turning a photo of a book into text)

The Act has **no text layer**; every page is an image. `tesseract` reads the pixels. 181 pages,
8 parallel workers, **498,240 characters in ~98 seconds**, and it's deterministic — rerunning
produces byte-identical output.

**The decision that matters: this runs on my laptop, once, and the output is committed to git.**

> *"If I OCR'd at runtime, your first click on a sleeping free-tier server would trigger 181 pages
> of OCR on two vCPUs while you waited. That blows the request timeout, the memory limit, and your
> patience simultaneously. So ingestion is an offline batch pipeline and serving is a stateless
> online service. The runtime image has no tesseract, no PDFs, and no PyTorch."*

That sentence is an architecture answer. **Being able to draw that line is the point.**

### Stage 2 — Page numbers (harder than it sounds)

Requirement #4 says show the page number. But **the PDF page index is not the printed page number**
— the Act has 17 pages of front matter, so `printed = pdf_index − 16`. I verified that against six
OCR'd page footers and it's a pytest assertion.

**If they ask "your citation says s.117 is on page 59 — prove it":**
> *"Open the PDF to page 76 and read the footer. It says 59. I render both — 'printed p.59 (PDF page
> 76 of 181)' — so you can verify either way. And the citation is a typed object all the way out,
> never a string, so I can assert `printed_page == 59` in a test and the model structurally cannot
> fabricate one."*

### Stage 3 — The two-up trap (the best "I found a real bug" story)

The handbook is a **landscape two-page spread**: each PDF page is a photo of an open book showing
**two** printed pages side by side. Extract it naively and you get two unrelated policies
interleaved line by line — with **no error raised**. Worse, PyMuPDF returns the **right-hand** page's
text first, so the page numbers come out backwards.

> *"The fix is geometric: I clip each PDF page at the horizontal midpoint and extract the halves
> separately. What I specifically did **not** do is filter text blocks by their x-coordinate —
> because the footer is a single block spanning the gutter, so an x-filter puts the right page's
> folio number in the left half and gets it exactly backwards on the page you'd check first."*

**The lesson to say out loud:** *"This corpus's signature failure mode is plausible wrong output
with no exception. That's why there's a regression test asserting the Leave Policy and the
Confidentiality Policy never share a chunk."*

### Stage 4 — Chunking (where the real thinking is)

A statute is **already chunked by its author**: the section is the natural unit and the section
number is a natural primary key. So I chunk on section boundaries.

Two traps, both silent:

1. **The Act uses two different heading grammars** — `46. Title : (1)` and `24. Title.— (1)`. A
   regex for one misses half the Act while appearing to work.
2. **Section titles can wrap a line — and s.46's does.** A regex whose title pattern forbids
   newlines can't match it, so **s.46 silently merges into s.45 carrying s.45's metadata.** You'd
   ship a clean recall number and a fabricated citation *on the flagship demo*.

> *"So there's a build gate: `assert {45, 46, 100, 108, 115, 116, 117, 118} ⊆ detected`. **It fails
> the build, not the demo.**"*

**And LIS** (longest increasing subsequence): section numbers ascend through a statute, so the real
headings form the longest increasing run; anything off it is a false positive. That recovers **342
sections from 343 raw regex hits** without hand-tuning.

> **If asked "why not `RecursiveCharacterTextSplitter`?"** — the standard LangChain answer:
> *"I measured it. At 1000 characters with 200 overlap it merges sections 115, 116 and 117 — casual,
> sick and annual leave, three distinct legal entitlements that happen to share a printed page —
> into one chunk with one page number. Ask it what page section 117 is on: it says 76. The document
> says 59."*

### Stage 5 — Retrieval (hybrid, and why)

**Asymmetric retrieval — the design I'm proudest of:**

> *"The handbook is 3,081 tokens. **Retrieval over a document that already fits can only lose
> information.** So I don't retrieve over it — I pin the whole thing in context, permanently, and
> only retrieve over the statute. That kills the imbalance problem by construction instead of by
> tuning a quota I'd have to justify, and it's what makes 'the handbook is silent on maternity' a
> **provable** claim rather than an inference from a failed search."*

For the statute: BM25 + embeddings, fused with **RRF** (reciprocal rank fusion — take both ranked
lists, score each result as `1/(60+rank)`, add them up). **Why RRF: there's no weight to justify.**
An interviewer asking "why is alpha 0.7?" has no target.

**Why hybrid *here* specifically — never give the generic answer:**
> *"Two measured reasons. First, IDF: 'gratuity' appears 10 times in 61,000 words, 'retrenchment'
> 14 — rare terms of art where BM25 is near-perfect and embeddings blur them into 'compensation',
> which appears 120 times. But 'can my boss make me work overtime?' shares no words with the
> governing section, so embeddings win there. Second — and this one surprised me — I checked whether
> OCR noise breaks BM25, and it doesn't: only 2 corrupted tokens in 61,098."*

### Stage 6 — Generation and verification

**One** model call per query. Then code checks the model's work.

The model must wrap every claim as `[[chunk:ID|exact quote]]`. Code then verifies that the quote
**actually appears** in that chunk. Claims that fail are **stripped**. If all are stripped,
`insufficient_information` is set **by code**.

> *"So the model never writes a citation string. It points at a chunk and quotes it, and code slices
> the snippet out of the source and builds a typed citation from that chunk's metadata. **A
> fabricated quote doesn't become a wrong answer — it becomes no answer.**"*

---

## Part 4 — How "I don't know" works (your strongest section)

**Requirement 4.5 is the highest-signal line in the spec**, and the obvious implementation is
*measurably wrong here*. Most candidates will set a similarity threshold and never test it.

**Measure it and it inverts:**

| | question | top-1 similarity |
|---|---|---|
| ✅ answerable | Who is the Chairperson? | **0.179** |
| ✅ answerable | How much overtime pay is required? | **0.224** |
| ❌ **unanswerable** | How many days of **paternity** leave? | **0.413** |

> *"The unanswerable question scores **higher** than two answerable ones, because 'paternity leave'
> collides with the casual-leave chunk. **The distributions invert.** Any threshold that refuses
> paternity also refuses 'who is the Chairperson?'. And that's not bad luck — it's structural: a
> good adversarial question is **plausible**, and plausible means semantically adjacent.
> **Retrieval score is an anti-signal for abstention.** So I threw thresholds out."*

What runs instead — deterministic, in code, zero extra model calls:

1. **Handbook silence is provable** — it's pinned in full, so absence is a fact, not a failed search.
2. Every claim must cite a retrieved chunk; the snippet is **sliced by code**.
3. **Span verification** — the quote must exist in the cited chunk, or the claim is stripped.
4. **Statute silence is bounded, not proved — and I say so.**

**The honest concession, which is stronger than a fake guarantee:**
> *"For the handbook I can **prove** absence. For the statute I can only tell you I didn't find it in
> the eight sections I retrieved. That's the real cost of choosing RAG, and it's exactly why the
> full-context oracle is in my eval — same model, whole corpus, so the only variable is retrieval,
> and it bounds how often that concession bites."*

**And refusal is `200 OK`, not an error:**
> *"A refusal is a designed product state — it's your requirement 4.5, the system working. 4xx means
> **you** did something wrong. If I returned 422 there, my own eval harness would score every
> correct refusal as a transport failure."*

---

## Part 5 — Trade-offs: the eight "why didn't you…" questions

The pattern for all of them: **name the thing, give the measurement, state when you'd revisit.**

### "Your corpus fits in one context window. Why RAG at all?"
> *"You're right, it fits — 122,119 tokens against Large 3's 262,144, so 47%. I measured it with
> Mistral's own tokenizer, not characters-over-four. So RAG here is a **choice, not a necessity**,
> and I built the full-context version too — it's in my eval as the oracle, the ceiling I measure
> retrieval against. I ship RAG for three reasons: your rubric grades Retrieval Accuracy as its own
> fifteen marks and you can't score that without a retriever; citation provenance is by construction
> when each chunk carries its own page number, whereas context-stuffing invents them; and it doesn't
> survive the six-document corpus your spec described. **I don't defend it on cost.**"*

### "Your embeddings are an API call. Didn't you say local compute was free?" *(volunteer this)*
> *"I did, and I was right — for the machine I was targeting. Local embeddings were the correct
> call for Hugging Face Spaces at sixteen gigabytes, where onnxruntime's two hundred and eighty
> megabytes is a rounding error, and the argument holds: a remote embedder puts a network call in
> the query path, and on a rate-limited free tier requests are the scarce resource.*
>
> *Then Hugging Face made Docker Spaces PRO-only, I moved to Render's five hundred and twelve
> megabytes, and my premise died without me noticing. Measured: three hundred and seventy megabytes
> baseline with onnxruntime, eighty-one without. An upload needs about a hundred and ninety. So
> uploads OOM-killed the container and the reviewer got a 502 — on the public demo, which shares
> nothing with uploads except a process. I tried capping and batching first; neither works, because
> no amount of batching fixes a baseline that's seventy-two percent of the ceiling. That's
> arithmetic, not tuning.*
>
> *Local compute is not free when memory is what you're short of. It's the same mistake as my
> router — a trade that was correct when I made it and wrong once its premise moved, and in both
> cases I didn't re-examine it until something broke. What it costs me now is about five hundred
> milliseconds per query and the claim that retrieval is network-free. What it buys is that the
> feature can't take down the demo."*

### "Why no vector database — and then why is Pinecone in here?"
*(Answer as one breath. Lead with lifecycle, not speed.)*
> *"Two stores, and what decides between them is **data lifetime, not performance**. The committed
> corpus is 482 vectors — 1.974 megabytes, exact cosine in 0.0148 milliseconds. Putting the *index* in
> Pinecone would make your cold visit depend on a third party's quota for something that's a file in
> my repo, so it loads at boot and is searched locally. I'll be precise, because it changed: the
> query's **embedding** is an API call now — about five hundred milliseconds — so retrieval isn't
> network-free end to end. The *index* is. Uploaded knowledge bases are different data with a
> different lifetime — the disk is ephemeral, so they must live off-box. One retriever protocol, two
> backends, both on live traffic. **And I'll be straight about the alternative:** Hugging Face
> Storage Buckets are free, first-party and mount read-write — they'd have reused my numpy store
> with one fewer vendor. I chose Pinecone for the namespace primitive, because isolation that
> **fails closed** beats a metadata filter you can forget. What I did **not** do is claim there was
> no alternative — you'd falsify that in one click."*

### "Why no ANN index / HNSW?"
> *"At 482 vectors, exact cosine is 0.008 milliseconds — a rounding error against a two-second model
> call. I'd add HNSW at m=16, ef_construction=200, ef_search=64 at roughly 50,000 vectors, where the
> exact scan crosses 10 milliseconds. Milvus needs etcd and MinIO to serve 0.7 megabytes. I'd rather
> show you I can **size** a system than that I can install one."*

*(Knowing the HNSW parameters **and** knowing not to use them is exactly what that question probes.)*

### "Why no agent?"
> *"I planned one. I counted 121 'section N' cross-references and that looked like multi-hop
> retrieval. Then I went hunting for a query single-shot actually gets wrong. The example everyone
> reaches for is section 100's eight-hour cap being 'subject to the provisions of section 108' —
> except I read section 100, and **the ten-hour exception is in section 100's own sentence**; 108 is
> the overtime **pay rate**, a different question entirely. Section-aware chunking already handles
> it. I couldn't find a failing query on my eval set, so I wrote no loop. And on a free tier at
> ~1 request/second, an agent's extra hops aren't milliseconds — they're seconds."*

### "Why no router model?"
> *"I had one, and deleting it is my favourite decision. A router is a **cost** optimisation — a
> cheap model triaging so the expensive one does less work. But on a free tier dollars aren't
> scarce, **requests** are. A router makes every query two requests to save retrieval that costs
> eight microseconds locally. **The optimisation inverted.** The route label is still logged — I
> derive it in code from which documents got cited."*

### "Why no reranker?"
> *"recall@5 is already 1.00 — you can't rerank above 1.00. And it would actively hurt: the
> handbook's leave clause is statutory boilerplate lifted from section 117 — Jaccard 0.53, whole
> phrases verbatim in both — so a similarity-maximising reranker **promotes both near-duplicates**,
> amplifying the one case where the system most needs to tell company policy apart from statutory
> floor. Pinecone gives me 500 free reranks a month. **Refusing a free thing because it's wrong is
> the discipline this build runs on.**"*

### "Why no fine-tuning? You said you wanted it."
> *"Four reasons, and I'll lead with the one that ends it: **I can train it, I just can't serve it.**
> QLoRA on a 7B is about seven gigabytes and under thirty minutes on my M2 — that part's genuinely
> easy. But you require a live URL and free hosting has no GPU. ZeroGPU needs a PRO subscription,
> it's Gradio-only so it'd take out the FastAPI layer you're scoring for API design, and an
> unauthenticated visitor — you, clicking my link — gets two minutes a day.*
>
> *Second, Mistral's hosted fine-tuning is served from a URL with 'deprecated' in the path and bills
> four dollars a job plus two a month — a card on file for a demo.*
>
> *Third, and this is what actually decided it: I want runtime upload of new knowledge bases. **A
> fine-tune is keyed to one corpus** — every new KB is a retrain and a redeploy of weights free
> hosting can't run. Fine-tuning and extensibility are mutually exclusive here, and extensibility is
> the requirement.*
>
> *Fourth, I checked whether I could even measure a win. At n=30 my minimum detectable effect is
> twenty-nine points; a realistic embedding fine-tune gains two to eight. My power is 4.6% — I'd
> miss a real improvement ninety-five percent of the time."*

**Invite the follow-up — it's your best beat:**
> **"But surely SOME fine-tune is worth it. The embedder?"**
> *"You've found the right one. bge-small is 33 million parameters — trains on my CPU in minutes,
> deploys as the same ONNX file the app already loads. Free, local, deployable; none of my other
> reasons touch it. I didn't do it, and the reason is a **measurement**, not a principle. Its only
> motivation here is a lexical gap: the Act writes 'fourteen days', users type '14 sick days'. So I
> ran the retriever before building anything. **BM25 ranks section 116 first.** Not a miss — first.
> Because 'sick' appears in 2 of 342 sections; it's a decisive high-IDF anchor and the digit
> free-rides. So I had a fine-tune that was free, fast and deployable — and I still didn't ship it,
> because I measured the thing it was supposed to fix and it wasn't broken."*

### "Why LangChain for uploads but not the statute?"
> *"My rule: **use the framework where the complexity is foreign; write it yourself where it's the
> thing being graded.** For the statute I know the grammar, and I measured the generic splitter
> destroying the citation anchor. For a document you upload thirty seconds from now, I **don't** know
> the grammar, and a recursive character split is the honest default. Same library, opposite
> verdicts, both measured. I didn't install the langchain meta-package at all, so the splitter I
> rejected isn't even importable."*

---

## Part 6 — "Open your repo. Convince me in five minutes."

**Open `.importlinter` first.** Fifteen lines.

> *"It says `src.core` may not import fastapi, starlette, mcp, pinecone, or mistralai. It runs in CI
> and in pytest. That's not a style preference — it's what lets me hand the suite a FakeGenerator
> and run everything with no API key and no network; it's why swapping the hosted API for
> self-hosted Apache-2.0 weights is a one-file change; and it's why exposing this over MCP would be
> a twenty-one-line adapter rather than a refactor. **I didn't write that claim in the README and
> ask you to believe it. I made the build fail if it stops being true.**"*

Then: `pytest -q` → 38 passed, **with no API key**. Then the layout: `core/` (pure logic),
`ingest/` (build-time CLI), `api/` (web). Then `prompts/*.md` — versioned, loaded at runtime, never
inline f-strings, so the git history is the tuning curve.

---

## Part 7 — "Add a feature. Right now." (rehearse this)

They may ask you to modify the app live. **Have one rehearsed.** Ask "which layer?" first — it
shows you think in layers — then do this one:

**`get_section(n)` behind an API filter.** It already exists in `core/retrieval.py`; you're exposing
it.

1. `AskRequest` already has `section_no: int | None = Field(ge=1, le=354)`.
2. `service.answer()` already branches on it.
3. So: add a test, run it, show the log line.

```bash
curl -X POST localhost:7860/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"What does this section say?","section_no":118}'
```

> *"Tools are plain typed functions, so a new capability is a function plus a schema entry. The eval
> is a YAML file, so a new question is three lines and CI catches the regression. The Dockerfile is
> layer-ordered so this redeploys in about thirty seconds."*

**If you freeze:** narrate. *"I'd add it here, in `core/`, because that's the layer with no web
imports — which means I can test it without a server."* Thinking out loud scores; silence doesn't.

---

## Part 8 — "How would you extend it?"

**Multi-tenancy / more knowledge bases.** *"`kb_id` is on every chunk and Pinecone gives 100
namespaces per index, so a new knowledge base is a namespace, not a schema change. Isolation fails
closed."*

**Documents that change hourly.** *"Today ingestion is a batch pipeline and the index is committed —
correct for a fixed two-document corpus. If documents changed hourly I'd need a real ingestion
service: a queue, a worker, incremental re-embedding keyed on content hash. The `index_meta.json`
already carries the source hashes and the chunker version, so I know exactly what to invalidate."*

**Scale.** *"At ~50k vectors I'd add pgvector with HNSW — same Postgres you already run rather than
a second stateful service. Not before: at 482 vectors an ANN index is strictly worse than not
building it."*

**Enterprise / data residency.** *"Large 3 is Apache 2.0 — run the weights in your VPC. That's a
one-file change because core takes an injected Generator protocol, and `.importlinter` proves it."*

**The amendments.** *"The biggest **product** gap: the Act I have is the 2006 text as published in
2009, amended in 2013 and 2018. Ingesting the amendments — and modelling *time*, so a policy is
checked against the law as it stood on a date — is what turns this from a demo into a product."*

---

## Part 9 — Questions you should volunteer

Raising these before they do reads as confidence. Being caught by them reads as naivety.

**"You used a free tier that trains on your data. For an *enterprise* assistant?"**
> *"Yes, and I turned it off — Console, Privacy, 'Anonymous improvement data'. Screenshot's in the
> repo. Training defaults on for the free plan. Worth saying: nothing here was confidential — it's a
> public statute plus a handbook you gave me. But the real answer is the model choice: Large 3 is
> Apache 2.0, so the enterprise answer to 'where does our data go' is 'run the weights in your VPC',
> not 'trust my vendor'."*

**"Why Mistral? Isn't that just what was free?"**
> *"It was free, but it's the only free tier that can run this workload, and I can show the
> arithmetic. My RAG prompt is ~5,200 tokens. Groq's free tier is 12,000 tokens a minute — that's
> twelve to nineteen queries a **day**, and my 101k-token oracle is 8.4× their per-minute limit, so
> it's not slow there, it's impossible. That's also why I have **no automatic fallback**: a silent
> failover means the answers you're seeing come from a model my eval never measured. That's worse
> than an honest outage. I do have a second provider — it's my **judge**, not my failover."*

**"It's a free tier. What if I click three questions fast?"**
> *"You can't — the chips disable while one's in flight. Server-side there's a semaphore and a token
> bucket, and a 429 comes back typed with a Retry-After, not a stack trace. And I'll be straight:
> Mistral doesn't publish free-tier limits — their docs tell you to read them off your own console.
> So I refused to tune to a number I couldn't verify and made the design not care."*

---

## Part 10 — The mistakes to own (this is a strength, used correctly)

Senior engineers are distinguished by how they talk about being wrong. **Have one ready.**

> **"I'll give you the one I got wrong. I'd convinced myself the corpus didn't fit in the context
> window — I'd measured 134,631 tokens against a 128k limit and had a whole argument built on 'RAG
> is forced, it's arithmetic'. Both halves were wrong. I'd used the old SentencePiece tokenizer
> instead of tekken — a 10% overcount — and I was quoting Mistral Large **2**'s window when Large 3
> is 256k. The real number is 122,119 tokens at 47%. It fits comfortably.**
>
> **What saved me was checking against the primary source instead of my own notes. And the lesson
> generalises: the 'section 100 defers to 108' agent argument, a '96% of sections are unreachable'
> statistic, a 'BM25 misses section 116' risk — every one of those was a plausible inference that
> dissolved the moment I ran the code instead of reasoning about it. Measure the thing; don't reason
> about the thing."**

**Also true and worth telling** — it shows your safety net catching a real error:
> *"When I first ran the maternity demo end-to-end, the model told me the handbook was **compliant** —
> its reasoning was 'silence isn't granting less than the minimum, so it meets the floor'. Confidently
> wrong, in the most dangerous direction, on my flagship question. Two things happened: my prompt's
> floor rule was ambiguous, and the model had ignored my citation format — so **every claim failed
> span verification and the whole thing collapsed to 'insufficient information' instead of reaching
> the user.** The bug caught the bug. I fixed the prompt to say silence is always a gap, and added a
> test. That's why the verification is in code and not in the prompt: prompts are requests, code is
> an invariant."*

---

## Part 11 — Ten-second cheat sheet

| Q | A |
|---|---|
| Corpus | 2 docs, 187pp, 122,119 tokens = **47%** of the window |
| OCR | 498,240 chars, ~98s, 8 workers, deterministic |
| Sections | **342** (dual-grammar + LIS) |
| Chunks | **482** (472 statute + 10 handbook) |
| Index | **1.974 MB**, exact cosine **0.0148 ms**, 1024-dim |
| Page map | `printed = pdf_index − 16`, 6 footers verified |
| Model | `mistral-large-2512`, 256k ctx, **Apache 2.0**, pinned |
| Embeddings | `llama-text-embed-v2` via **Pinecone Inference** (~500 ms, network) |
| Retrieval | BM25 + dense, **RRF k=60**, top-8 |
| Latency | model **seconds** ≫ embed **~500 ms** ≫ search **µs** |
| Tests | **38**, green with **no API key** |

**If you remember one sentence:** *"Ingestion is an offline batch pipeline; serving is a stateless
online service; and every claim the model makes is verified against the source by code before you
see it."*

---

## Part 12 — Rules for the room

1. **Never invent a number.** "I'd have to measure that" is a *good* answer. A wrong number
   discredits every right one.
2. **Answer, then evidence.** "Ten days — here's the citation," not three sentences of preamble.
3. **When you don't know, say so, then say how you'd find out.** That's literally what you built
   the product to do.
4. **Never say "best practice."** Say what you measured. "Best practice" means you copied it.
5. **Volunteer a limitation before they find it.** The staleness, the statute-side bound, the
   ephemeral job store. Naming them is authority; being caught is not.
6. **You will be asked something you didn't consider.** Say: *"I hadn't considered that. My instinct
   is X — but I'd want to measure it before claiming it."* That is exactly the discipline this whole
   project runs on, applied live.

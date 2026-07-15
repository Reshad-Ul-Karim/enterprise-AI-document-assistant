# Target: Render free tier -- 512 MB RAM, 0.1 CPU, no credit card, spins down after 15 min.
#
# NOT Hugging Face Spaces. As of 2026 HF requires a PRO subscription (a card) for Docker,
# Gradio AND Streamlit Spaces; only `static` Spaces remain free. Verified empirically
# against the API: creating a docker Space returns HTTP 402 Payment Required. Every guide
# describing "free 16 GB Docker Spaces" is describing a tier that no longer exists.
#
# The 512 MB ceiling is the binding constraint, and it is tight: measured peak RSS is
# ~435 MB (onnxruntime alone is ~280 MB resident). Hence the single-threaded env below --
# on 0.1 CPU there is nothing to parallelise anyway, and every arena costs headroom.
#
# What is NOT in this image, and why that is the whole design:
#   - tesseract        OCR is a BUILD-TIME step. 181 scanned pages on 2 vCPU during a cold
#                      start, while the reviewer waits, would blow the timeout and their
#                      patience. The extracted text is committed instead.
#   - the source PDFs  16.25 MB + 536 KB, .dockerignore'd. The index is 0.74 MB.
#   - torch            ~254 MB vs ~2.5 GB. The reason is COLD START (a sleeping Space means
#                      the reviewer's first click IS a cold start), not memory.
#
# Ingestion is an offline batch pipeline; serving is a stateless online service.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # 512 MB ceiling, 0.1 CPU: there is no parallelism to win, so every thread pool and
    # allocator arena is pure overhead. Measured: ~10 MB back, and it removes a class of
    # OOM-under-concurrency failure that would kill the URL on the reviewer's click.
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    # fastembed's default cache is a temp dir, and HF's disk is ephemeral -- an unbaked
    # model re-downloads on EVERY cold start (+10.7s, plus a hard dependency on a CDN at
    # boot: a hiccup boots the Space broken, on the reviewer's click, with no error in our
    # code). Bake it at build time instead.
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
    HF_HOME=/app/.cache/hf

WORKDIR /app

# Layer order is deliberate: deps change rarely, the index occasionally, source often. A
# code-only change rebuilds one small layer -- which is what makes the section-10 "add a
# feature right now" segment a ~30s redeploy rather than a full rebuild on a shared screen.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

COPY index/ ./index/
COPY prompts/ ./prompts/
COPY static/ ./static/
COPY src/ ./src/
COPY corpus_stats.json ./

EXPOSE 7860

# Asserts the index loads and reports WHY if it does not: a reviewer gets a diagnosis, not
# a blank page.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','7860'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/health').status==200 else 1)"

# Render injects $PORT at runtime; default keeps local/other hosts on 7860.
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]

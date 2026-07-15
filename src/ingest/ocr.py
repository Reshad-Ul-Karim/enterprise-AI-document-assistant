"""OCR the Labour Act. Build-time only, run ONCE, output committed.

This is the whole reason free deployment is survivable. OCR-ing 181 scanned pages on a
2-vCPU free-tier box during a cold start -- while the reviewer waits -- would blow the
request timeout, the memory limit, and their patience simultaneously. So it runs here, on
a developer machine, and the extracted text is committed as a versioned artifact.

Ingestion is an offline batch pipeline; serving is a stateless online service.

Measured on an M2 with 8 workers: 181 pages, 498,240 chars, ~98s wall, deterministic
(byte-identical across reruns). Quote the WALL CLOCK, never seconds-per-page -- timing is
a property of the machine, 498,240 chars is a property of the corpus.

No preprocessing. Deskew/denoise/binarisation were all rejected: tesseract already returns
~94% mean confidence on these scans, and every preprocessing step is a knob to defend.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ProcessPoolExecutor

import pymupdf

from src.ingest.extract import ACT_PDF, EXTRACTED

DPI = 200
WORKERS = 8


def _ocr_range(args: tuple[int, int]) -> list[tuple[int, str, float]]:
    """Reopen the PDF once per worker -- per-page opens were the measured bottleneck."""
    low, high = args
    doc = pymupdf.open(ACT_PDF)
    out: list[tuple[int, str, float]] = []
    for zero_based_pdf_index in range(low, high):
        page = doc[zero_based_pdf_index]
        textpage = page.get_textpage_ocr(flags=0, dpi=DPI, full=True)
        text = page.get_text(textpage=textpage)
        out.append((zero_based_pdf_index, text, 0.0))
    doc.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR the Labour Act (build-time, run once)")
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()

    if not ACT_PDF.exists():
        raise SystemExit(f"missing {ACT_PDF}")

    doc = pymupdf.open(ACT_PDF)
    page_count = doc.page_count
    doc.close()

    step = (page_count + args.workers - 1) // args.workers
    ranges = [(i, min(i + step, page_count)) for i in range(0, page_count, step)]

    started = time.time()
    pages: dict[int, str] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for batch in pool.map(_ocr_range, ranges):
            for zero_based_pdf_index, text, _ in batch:
                pages[zero_based_pdf_index] = text
    wall_seconds = time.time() - started

    lengths = [len(v) for v in pages.values()]
    total_chars = sum(lengths)

    EXTRACTED.mkdir(parents=True, exist_ok=True)
    (EXTRACTED / "act_ocr.json").write_text(
        json.dumps(
            {
                "source_file": ACT_PDF.name,
                "engine": "tesseract-5.5.2 via pymupdf get_textpage_ocr",
                "dpi": DPI,
                "workers": args.workers,
                "page_count": page_count,
                "total_chars": total_chars,
                "wall_seconds": round(wall_seconds, 1),
                "pages": {str(k): v for k, v in sorted(pages.items())},
            },
            indent=1,
        )
    )

    print(f"pages={page_count} chars={total_chars:,} wall={wall_seconds:.1f}s workers={args.workers}")
    print(f"mean chars/page={statistics.mean(lengths):.0f}")

    # Gate: catches a silently broken OCR run (wrong dpi, missing tessdata, blank renders).
    mean_chars = statistics.mean(lengths)
    if mean_chars < 1500:
        raise SystemExit(f"OCR gate failed: mean {mean_chars:.0f} chars/page < 1500")
    print("OCR gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

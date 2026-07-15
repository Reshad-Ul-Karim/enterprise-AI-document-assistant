"""Extraction. Build-time only -- nothing here ships in the runtime image.

THE TRAP: Partex-Star-Group.pdf is a LANDSCAPE 2-UP SPREAD. One PDF page carries two
printed folios, and PyMuPDF returns the RIGHT-hand folio's blocks first. Verified on the
real file -- naive extraction of idx 3 emits:

    6 / employee handbook / 5 / employee handbook / Sales Office: ...

Two folios, interleaved, out of order, with no exception raised. This is the document the
business scenario is actually about, and it is the one that breaks.

THE FIX, and why it is geometric: clip at page.rect.width/2 and extract each half
independently. Do NOT filter blocks by x0 -- the footer is a single block SPANNING THE
GUTTER, so an x0 filter assigns the right folio's page number to the left half and gets it
exactly backwards on the page a reviewer would check.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pymupdf

from src.core.pagemap import ACT_PDF_PAGES, act_layer, act_page_is_indexed

REPO = Path(__file__).resolve().parents[2]
ACT_PDF = REPO / "Assets" / "A Handbook on the Bangladesh Labour Act 2006.pdf"
HANDBOOK_PDF = REPO / "Assets" / "Partex-Star-Group.pdf"
EXTRACTED = REPO / "data" / "extracted"

# doc_title comes from a CURATED MANIFEST, never the filename. 'Partex-Star-Group.pdf' is
# misleadingly named -- its own PDF metadata title is 'Employee Handbook-Final'.
MANIFEST = {
    "handbook": {
        "doc_id": "handbook",
        "doc_title": "Employee Handbook (Partex Star Group)",
        "source_file": "Partex-Star-Group.pdf",
        "pdf_pages": 6,
        "printed_folios": 10,
        "modality": "text",
        "note": "Landscape 2-up spread; PDF metadata title is 'Employee Handbook-Final'.",
    },
    "statute": {
        "doc_id": "statute",
        "doc_title": "Bangladesh Labour Act 2006",
        "source_file": "A Handbook on the Bangladesh Labour Act 2006.pdf",
        "pdf_pages": 181,
        "printed_pages": 140,
        "modality": "ocr",
        "note": (
            "100% scanned images, zero extractable text; OCR'd at build time. Published by "
            "the Bangladesh Employers' Federation, 2009. Amended 2013 and 2018 -- those "
            "amendments are NOT in this corpus."
        ),
    },
}


def normalise(text: str) -> str:
    """NFKC then join end-of-line hyphenation.

    NFKC because the handbook uses ligatures -- 'con(fi)dential' is a different string from
    'confidential' to every tokeniser. The hyphen rule joins '-\\n' only, sparing 'pro-rata'.
    """
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)


def extract_handbook() -> list[tuple[int, str, str]]:
    """-> [(zero_based_pdf_index, half, text)] with the two folios separated."""
    doc = pymupdf.open(HANDBOOK_PDF)
    folios: list[tuple[int, str, str]] = []
    for zero_based_pdf_index in range(1, doc.page_count):  # idx 0 is the unnumbered cover
        page = doc[zero_based_pdf_index]
        width, height = page.rect.width, page.rect.height
        for half, rect in (
            ("left", pymupdf.Rect(0, 0, width / 2, height)),
            ("right", pymupdf.Rect(width / 2, 0, width, height)),
        ):
            text = normalise(page.get_text(clip=rect))
            if text.strip():
                folios.append((zero_based_pdf_index, half, text))
    doc.close()
    return folios


def load_act_ocr() -> dict[int, str]:
    """Load the committed OCR artifact. Produced once by `python -m src.ingest.ocr`."""
    path = EXTRACTED / "act_ocr.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing. Run `python -m src.ingest.ocr` once on a machine with "
            "tesseract. The runtime image deliberately has neither tesseract nor the PDF."
        )
    raw = json.loads(path.read_text())
    return {int(k): v for k, v in raw["pages"].items()}


def statute_layer_text(pages: dict[int, str]) -> tuple[str, list[tuple[int, int]]]:
    """Concatenate the statute layer, tracking where each page starts.

    Returns (text, [(char_offset, zero_based_pdf_index)]) so a section's character
    position maps back to the page it is printed on -- which is how a citation gets a page
    number at all.
    """
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for zero_based_pdf_index in range(ACT_PDF_PAGES):
        if act_layer(zero_based_pdf_index) != "statute":
            continue
        if not act_page_is_indexed(zero_based_pdf_index):
            continue
        text = normalise(pages.get(zero_based_pdf_index, ""))
        offsets.append((cursor, zero_based_pdf_index))
        parts.append(text)
        cursor += len(text) + 1
    return "\n".join(parts), offsets

"""The curated document manifest.

This lives in core/ and NOT in ingest/ for a reason that cost a failed deploy to learn.

It is *data*: what these documents are, what they are really called, and what a reader must
be told about them. It has nothing to do with PDF extraction. It was originally defined in
`ingest/extract.py` next to the code that reads the PDFs, which meant `api/main.py` had to
import from `ingest` to serve `GET /api/documents` -- and `ingest/extract.py` imports
PyMuPDF, a BUILD-TIME dependency deliberately excluded from the runtime image. The
container built cleanly and then died on boot with `ModuleNotFoundError: No module named
'pymupdf'`.

The lesson is about layering, not about a missing package: the API must never need to
import build-time code to answer a question about the corpus. `.importlinter` now forbids
`src.api` from importing `src.ingest` at all, so this cannot regress.

doc_title comes from here and NEVER from the filename: `Partex-Star-Group.pdf` is
misleadingly named -- its own PDF metadata title is `Employee Handbook-Final`.
"""

from __future__ import annotations

MANIFEST: dict[str, dict[str, object]] = {
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

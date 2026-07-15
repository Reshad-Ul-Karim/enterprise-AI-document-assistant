"""Chunking.

A short section is a complete legal unit -- do NOT merge short sections to hit a token
target. Sub-split only what is genuinely too long, and carry the parent's metadata so the
citation survives the split.
"""

from __future__ import annotations

import re

from src.core.models import Chunk
from src.core.pagemap import printed_page
from src.core.sections import Section

SUBSPLIT_THRESHOLD = 2000
SUBSPLIT_WINDOW = 1200
SUBSPLIT_STRIDE = 1000

# s.2 is the Definitions section: 66 defined terms in one section. It is the highest-value
# retrieval target in the Act ('what is a worker?') and splitting it by character windows
# would cut definitions in half. Split it per definition instead.
DEFINITIONS_SECTION = 2
_DEFINITION_RE = re.compile(r"\(\s*[ivxlcdm]{1,7}\s*\)\s*", re.I)


def _section_page(section: Section, page_offsets: list[tuple[int, int]]) -> int:
    """0-based PDF index of the page a section starts on.

    page_offsets is [(char_offset, zero_based_pdf_index)] ascending -- built when the
    statute layer is concatenated, so a section's char position maps back to its page.
    """
    page = page_offsets[0][1]
    for offset, idx in page_offsets:
        if section.start >= offset:
            page = idx
        else:
            break
    return page


def _windows(text: str) -> list[str]:
    out = []
    for start in range(0, len(text), SUBSPLIT_STRIDE):
        piece = text[start : start + SUBSPLIT_WINDOW]
        if piece.strip():
            out.append(piece)
        if start + SUBSPLIT_WINDOW >= len(text):
            break
    return out


def chunk_statute(
    sections: list[Section],
    page_offsets: list[tuple[int, int]],
    doc_id: str,
    doc_title: str,
    ocr_conf: dict[int, float] | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        idx = _section_page(section, page_offsets)
        conf = (ocr_conf or {}).get(idx)
        base = dict(
            kb_id="default",
            doc_id=doc_id,
            doc_title=doc_title,
            doc_kind="statute",
            layer="statute",
            section_no=section.number,
            section_title=section.title,
            zero_based_pdf_index=idx,
            printed_page=printed_page(idx),
            source_modality="ocr",
            ocr_mean_conf=conf,
        )

        if section.number == DEFINITIONS_SECTION and len(section.text) > SUBSPLIT_THRESHOLD:
            parts = [p for p in _DEFINITION_RE.split(section.text) if p.strip()]
            for n, part in enumerate(parts):
                chunks.append(
                    Chunk(chunk_id=f"{doc_id}:s{section.number}:def{n}", text=part.strip(),
                          is_definition=True, **base)
                )
            continue

        if len(section.text) > SUBSPLIT_THRESHOLD:
            for n, piece in enumerate(_windows(section.text)):
                chunks.append(
                    Chunk(chunk_id=f"{doc_id}:s{section.number}:w{n}", text=piece.strip(), **base)
                )
            continue

        chunks.append(Chunk(chunk_id=f"{doc_id}:s{section.number}", text=section.text.strip(), **base))
    return chunks


def chunk_handbook(folios: list[tuple[int, str, str]], doc_id: str, doc_title: str) -> list[Chunk]:
    """One printed half-page folio is one natural chunk (each is ~2-3k chars).

    folios: [(zero_based_pdf_index, half, text)]
    """
    chunks: list[Chunk] = []
    for zero_based_pdf_index, half, text in folios:
        folio = (2 * zero_based_pdf_index - 1) if half == "left" else (2 * zero_based_pdf_index)
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}:p{zero_based_pdf_index}:{half}",
                doc_id=doc_id,
                doc_title=doc_title,
                doc_kind="handbook",
                layer="handbook",
                text=text.strip(),
                zero_based_pdf_index=zero_based_pdf_index,
                printed_page=folio,
                half=half,  # type: ignore[arg-type]
                source_modality="text",
            )
        )
    return chunks

"""Chunking.

A short section is a complete legal unit -- do NOT merge short sections to hit a token
target. Sub-split only what is genuinely too long, and carry the parent's metadata so the
citation survives the split.
"""

from __future__ import annotations

import re

from src.core.models import Chunk, DocKind
from src.core.pagemap import printed_page
from src.core.sections import Section

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.M)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

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


def chunk_paper_pdf(pages: list[str], doc_id: str, doc_title: str) -> list[Chunk]:
    """One chunk per PDF page (sub-split via _windows() if a page runs long).

    Unlike chunk_markdown(), a publication PDF has real, simple pagination -- no landscape
    2-up spread, no OCR offset scheme (pagemap.py's PRINTED_OFFSET=16 is specific to the
    statute's front matter and does not apply here). Page index IS the printed page, so
    zero_based_pdf_index=i and printed_page=i+1 is the whole page-mapping rule. Leaving
    section_title unset means Citation.render()'s persona branch falls back to
    "{doc_title} — p.{printed_page}" (e.g. "IEEE Access paper — p.4"), which is the citation
    a paper actually wants -- a heading would be misleading since nothing here has one.
    """
    chunks: list[Chunk] = []
    for i, page_text in enumerate(pages):
        for j, window in enumerate(_windows(page_text)):
            if not window.strip():
                continue
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:p{i}:{j}",
                    doc_id=doc_id,
                    doc_title=doc_title,
                    doc_kind="portfolio",
                    text=window.strip(),
                    zero_based_pdf_index=i,
                    printed_page=i + 1,
                    source_modality="text",
                )
            )
    return chunks


def _slug(title: str) -> str:
    return _SLUG_RE.sub("-", title.lower()).strip("-") or "section"


def chunk_markdown(text: str, doc_id: str, doc_title: str, kind: DocKind) -> list[Chunk]:
    """Split markdown-sourced persona text (resume/project docs) on '#'/'##'/'###' headings.

    chunk_statute()'s section grammar is statute-specific (s.NN headings via sections.py);
    project write-ups and the resume have no such grammar, just plain markdown -- so this
    splits on heading level instead and carries each heading forward as section_title. Long
    sections still go through the shared _windows() sub-split so no single chunk balloons.

    Markdown sources have no real pagination (they're generated text, not a scanned PDF), so
    zero_based_pdf_index/printed_page are both fixed at 0/1 -- Citation.render() already
    prefers section_title over page number for doc_kind in ("resume", "portfolio"), so this
    never surfaces as a fake "page 1" in the UI.
    """
    parts = _HEADING_RE.split(text)
    chunks: list[Chunk] = []
    for heading_index, i in enumerate(range(1, len(parts), 3)):
        section_title = parts[i + 1].strip()
        body = parts[i + 2]
        # heading_index disambiguates chunk_id even when two DIFFERENT headings in the same
        # document slugify to the SAME string ("Overview" and "overview", "Tech Stack" and
        # "Tech-Stack") -- caught by a test, not by inspection: a bare slug collided and one
        # chunk's Chunk object silently replaced the other's in `by_id` at verification time,
        # which is the exact "wrong section's metadata on a real citation" failure mode
        # test_corpus_regression.py exists to catch for the statute (s.46 merging into s.45).
        slug = _slug(section_title)
        for j, window in enumerate(_windows(body) or [body.strip()]):
            if not window.strip():
                continue
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{slug}:{heading_index}:{j}",
                    doc_id=doc_id,
                    doc_title=doc_title,
                    doc_kind=kind,
                    section_title=section_title,
                    text=window.strip(),
                    zero_based_pdf_index=0,
                    printed_page=1,
                    source_modality="text",
                )
            )
    return chunks

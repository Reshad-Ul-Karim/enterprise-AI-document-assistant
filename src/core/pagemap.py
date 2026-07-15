"""Page-number provenance.

FR#4 requires citing a page number. Neither document's PDF index equals its printed
page number, and they break the mapping in two different ways. Getting this wrong is a
ten-second check for a reviewer holding the PDF.

ONE convention: every index in this codebase is a 0-based PyMuPDF page index. Variables
are named `zero_based_pdf_index` and `printed_page`. Never `page`. Never bare `idx`.
"""

from __future__ import annotations

# The Act carries 17 pages of front matter (roman numerals), so the printed folio number
# lags the PDF index by a constant. Verified against six OCR'd page footers:
#   idx 19->3, 40->24, 55->39, 75->59, 76->60, 90->74
PRINTED_OFFSET = 16

FRONT_MATTER = range(0, 17)  # idx 16 == PREFACE == printed 'xvi'
BODY_RANGE = range(17, 157)  # printed 1..140

# Excluded from the answer index. Hardcoded constants citing their evidence rather than a
# heuristic classifier, because the evidence is stable and a classifier would need defending.
TOC_RANGE = range(1, 16)  # dot-leader lines ('Procedure for leave : 27') that are
# lexically near-identical to every real section heading and
# carry zero answer content: maximally adversarial to BM25.
ANNEX_RANGE = range(157, 181)  # ILO ratification table; OCRs to 'This / aw / is / not / in / force'.

# The Act verbatim vs commentary about it. get_section indexes STATUTE_RANGE only --
# otherwise the section regex false-positives ss.1-6 onto the repealed-laws schedule.
COMMENTARY_RANGE = range(17, 33)
STATUTE_RANGE = range(33, 157)

ACT_PDF_PAGES = 181


def printed_page(zero_based_pdf_index: int) -> int:
    """Printed folio number for a 0-based PyMuPDF index of the Labour Act."""
    return zero_based_pdf_index - PRINTED_OFFSET


def zero_based_index(printed: int) -> int:
    """Inverse of `printed_page`."""
    return printed + PRINTED_OFFSET


def act_layer(zero_based_pdf_index: int) -> str:
    if zero_based_pdf_index in STATUTE_RANGE:
        return "statute"
    if zero_based_pdf_index in COMMENTARY_RANGE:
        return "commentary"
    if zero_based_pdf_index in ANNEX_RANGE:
        return "table_unreliable"
    return "front_matter"


def act_page_is_indexed(zero_based_pdf_index: int) -> bool:
    """Pages that reach the answer index. Excludes TOC and the ILO annex."""
    if zero_based_pdf_index in TOC_RANGE or zero_based_pdf_index in ANNEX_RANGE:
        return False
    return 0 <= zero_based_pdf_index < ACT_PDF_PAGES


def partex_folios(zero_based_pdf_index: int) -> tuple[int, int]:
    """(left, right) printed folio numbers on a Partex handbook PDF page.

    The handbook is a landscape 2-up spread: one PDF page carries two printed folios.
    idx 0 is an unnumbered cover; idx 1..5 carry folios 1..10.
    """
    if zero_based_pdf_index < 1:
        raise ValueError(f"idx {zero_based_pdf_index} is the cover; it has no folios")
    return (2 * zero_based_pdf_index - 1, 2 * zero_based_pdf_index)

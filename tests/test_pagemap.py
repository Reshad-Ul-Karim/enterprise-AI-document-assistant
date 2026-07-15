"""Page provenance. FR#4 demands a page number, and a wrong one is a ten-second kill.

Every constant here was read off an OCR'd page footer in the real PDF. If a reviewer opens
PDF page 76 of the Act, the footer says 59.
"""

from __future__ import annotations

import pytest

from src.core.pagemap import act_layer, act_page_is_indexed, partex_folios, printed_page


def test_printed_page_from_zero_based_index():
    # Verified against six OCR'd footers in the real scan.
    assert printed_page(75) == 59
    assert printed_page(76) == 60
    assert printed_page(55) == 39
    assert printed_page(40) == 24
    assert printed_page(19) == 3
    assert printed_page(90) == 74


def test_flagship_sections_land_on_their_real_pages():
    """The pages the compliance demo cites. s.46 is the flagship."""
    assert printed_page(55) == 39  # s.46  maternity
    assert printed_page(73) == 57  # s.108 overtime
    assert printed_page(75) == 59  # s.115/116/117 leave floors
    assert printed_page(76) == 60  # s.118 festival holidays


def test_partex_folios():
    # A landscape 2-up spread: one PDF page carries two printed folios.
    # This is the mapping that a block-x0 filter gets exactly backwards.
    assert partex_folios(1) == (1, 2)
    assert partex_folios(2) == (3, 4)
    assert partex_folios(5) == (9, 10)


def test_partex_cover_has_no_folios():
    with pytest.raises(ValueError):
        partex_folios(0)


def test_toc_and_annex_are_excluded_from_the_answer_index():
    # The TOC's dot-leader lines are lexically near-identical to every real section heading
    # and carry zero answer content: maximally adversarial to BM25.
    assert not act_page_is_indexed(5)
    # The ILO annex OCRs to word salad. Excluded deliberately and documented, which beats a
    # half-working table parser.
    assert not act_page_is_indexed(170)
    assert act_page_is_indexed(75)
    assert act_page_is_indexed(16)  # PREFACE -- kept; one draft range would have deleted it


def test_layers():
    assert act_layer(75) == "statute"
    assert act_layer(20) == "commentary"  # commentary ABOUT the Act, not the Act
    assert act_layer(170) == "table_unreliable"

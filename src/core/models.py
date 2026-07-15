"""Domain types.

Citations are typed objects the whole way out -- never markdown strings. A markdown
citation is unassertable: you cannot write `assert c.printed_page == 59` against
'-- printed p.59 (PDF page 76)' without a regex. Rendering happens in the UI layer from a
typed object, so the model never emits a citation string and structurally cannot
fabricate one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocKind = Literal["handbook", "statute", "uploaded"]
Modality = Literal["text", "ocr"]


class Chunk(BaseModel):
    """One retrievable unit. Carries its own provenance so a citation is by construction."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    kb_id: str = "default"
    doc_id: str
    doc_title: str  # from the curated manifest, NEVER the filename
    doc_kind: DocKind
    text: str

    layer: str | None = None  # statute | commentary | handbook
    section_no: int | None = None
    section_title: str | None = None
    is_definition: bool = False

    zero_based_pdf_index: int
    printed_page: int
    half: Literal["left", "right"] | None = None

    source_modality: Modality
    ocr_mean_conf: float | None = None


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    doc_title: str
    doc_kind: DocKind
    section_no: int | None = None
    section_title: str | None = None
    printed_page: int
    pdf_page: int
    half: Literal["left", "right"] | None = None
    snippet: str  # sliced from the chunk by code, never generated
    source_modality: Modality
    ocr_confidence: float | None = None

    def render(self) -> str:
        """The one f-string that ends the printed-vs-physical argument.

        Print both: printed matches what the document says about itself, PDF matches the
        reviewer's scrollbar. The section number is the anchor the eval asserts on -- it is
        the statute's actual primary key, stable regardless of pagination, and it OCRs
        cleanly where footers do not ('ll' for 11, 'Az' for 47).
        """
        if self.doc_kind == "statute" and self.section_no is not None:
            return (
                f"{self.doc_title}, s.{self.section_no} {self.section_title} "
                f"— printed p.{self.printed_page} (PDF page {self.pdf_page} of 181)"
            )
        if self.half:
            return (
                f"{self.doc_title}, printed p.{self.printed_page} "
                f"(PDF page {self.pdf_page}, {self.half} half)"
            )
        return f"{self.doc_title}, printed p.{self.printed_page} (PDF page {self.pdf_page})"


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    kb_id: str = "default"
    doc_filter: Literal["handbook", "statute"] | None = None
    section_no: int | None = Field(default=None, ge=1, le=354)  # a free 422 on nonsense


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    insufficient_information: bool
    route: str  # derived in code from which docs the cited chunks came from
    latency_ms: int
    request_id: str
    index_version: str

"""Statutory section detection over OCR'd text.

A statute is pre-chunked by its own author: the section IS the natural unit, and the
section number is the natural primary key. Recovering that structure from OCR is what
makes citations exact.

Two hazards, both of which fail silently:

1. The Act uses TWO header grammars -- 'N. Title : (1)' and 'N. Title.-- (1)'. A
   single-grammar regex misses half the Act while looking like it works.
2. Section titles can WRAP a line. s.46's does. A regex whose title class forbids
   newlines cannot match it, so s.46 merges into s.45's chunk CARRYING S.45'S METADATA --
   a confidently wrong citation on the flagship demo, with a clean recall number in the
   README. Hence the build gate below.

A greedy monotonic scan gives ~82% recall because one stray high number poisons every
section after it. Longest-increasing-subsequence over the detected numbers rejects the
false positives the regex admits, without hand-tuning.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SECTION_RE = re.compile(
    r"^\s{0,6}(\d{1,3})\s*[.,]\s+"  # '46.' / '46,' (OCR flips . to ,)
    r"([A-Z][^:;\n]{3,95}(?:\n[^:;\n]{1,60})?)"  # title, allowing ONE wrapped line
    r"\s*[|!,.\s]{0,3}(?:[:;]|[—–-]{1,2}\s*\()",  # ': ' or '.— (' -- both grammars
    re.M,
)

# Sections whose absence must fail the build rather than the demo. Each is load-bearing:
# 46 = maternity (the flagship), 100/108 = working hours + overtime rate,
# 115/116/117/118 = the leave floors the compliance comparison rests on.
REQUIRED_SECTIONS = frozenset({45, 46, 100, 108, 115, 116, 117, 118})


@dataclass(frozen=True)
class Section:
    number: int
    title: str
    start: int
    end: int
    text: str


def normalise(text: str) -> str:
    """NFKC + hyphenation repair.

    NFKC because the handbook uses ligatures: 'con(fi)dential' != 'confidential' to any
    tokeniser. The hyphen rule joins only end-of-line breaks and spares 'pro-rata'.
    """
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)
    return text


def _longest_increasing_subsequence(numbers: list[int]) -> list[int]:
    """Indices of the longest strictly-increasing subsequence.

    Section numbers ascend monotonically through a statute, so the true headers are the
    longest increasing run. Anything off that run is a false positive -- a cross-reference,
    a schedule entry, an OCR artifact.
    """
    if not numbers:
        return []
    best = [1] * len(numbers)
    parent = [-1] * len(numbers)
    for i in range(len(numbers)):
        for j in range(i):
            if numbers[j] < numbers[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                parent[i] = j
    end = max(range(len(numbers)), key=lambda i: best[i])
    out: list[int] = []
    while end != -1:
        out.append(end)
        end = parent[end]
    return out[::-1]


def detect_sections(statute_text: str) -> list[Section]:
    """Detect sections in the statute layer only (0-based idx 33..156)."""
    text = normalise(statute_text)
    hits = [(int(m.group(1)), m.start(), " ".join(m.group(2).split())) for m in SECTION_RE.finditer(text)]
    if not hits:
        return []
    keep = _longest_increasing_subsequence([n for n, _, _ in hits])
    kept = [hits[i] for i in keep]

    sections: list[Section] = []
    for k, (number, start, title) in enumerate(kept):
        end = kept[k + 1][1] if k + 1 < len(kept) else len(text)
        sections.append(Section(number=number, title=title, start=start, end=end, text=text[start:end]))
    return sections


def assert_build_gate(sections: list[Section]) -> None:
    """Fail the build, not the demo."""
    found = {s.number for s in sections}
    missing = REQUIRED_SECTIONS - found
    if missing:
        raise AssertionError(
            f"Section detection dropped required sections: {sorted(missing)}. "
            "s.46's title wraps a line -- if it is missing, the title regex is not "
            "allowing a wrapped line and s.46 has silently merged into s.45."
        )

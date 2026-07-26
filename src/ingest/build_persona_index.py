"""Build the persona corpus index (reshadulkarim.me's "Ask Reshad" widget).

Mirrors build_index.py's shape exactly -- same three output files, same embedder, same
"fail the build" philosophy -- but sources from the portfolio site repo instead of Assets/,
per docs/AI_ASSISTANT_PLAN.md. Emits index_persona/{index.npz,chunks.jsonl,index_meta.json},
loaded by a SECOND Corpus instance at boot (see src/api/main.py's lifespan) alongside the
original HR index -- same service, second corpus (plan sec.4), not a second deployment.

Run: python -m src.ingest.build_persona_index
Needs: PINECONE_API_KEY (embeddings only -- same provider as the HR index, see
src/core/embeddings.py; no Mistral key needed to build, only to serve).
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
from pathlib import Path

import numpy as np

from src.core.chunking import chunk_markdown, chunk_paper_pdf
from src.core.embeddings import EMBED_DIM, EMBED_MODEL_ID, INPUT_TYPE_QUERY
from src.core.manifest import MANIFEST
from src.core.models import Chunk

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "index_persona"
CHUNKER_VERSION = "1.0.0"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _strip_html(text: str) -> str:
    """data/projects.json and data/publications.json embed presentation markup for the site's
    OWN rendering -- '<strong>planner/router</strong>' -- inline in otherwise-plain fields.
    That is semantically fine for a webpage and semantically noisy for an LLM prompt, so it
    is stripped here rather than passed through into the persona corpus."""
    return _WS_RE.sub(" ", html_lib.unescape(_TAG_RE.sub("", text))).strip()

# The persona corpus is sourced from a SIBLING repo (the portfolio site itself), not from
# this repo's Assets/ -- overridable so this still works if the two repos ever move.
SITE_REPO = Path(os.environ.get("PERSONA_SITE_REPO", str(REPO.parent / "MyWebsite")))
RESUME_PDF = (
    SITE_REPO / "Resume___Reshad_Ul_karim__UIU_" / "src" / "resume_faangpath-main merged long.pdf"
)
PROJECTS_JSON = SITE_REPO / "data" / "projects.json"
PUBLICATIONS_JSON = SITE_REPO / "data" / "publications.json"
INDEX_HTML = SITE_REPO / "index.html"
PAPERS_DIR = SITE_REPO / "assets" / "papers" / "research"

# Publication slug -> filename in PAPERS_DIR. Hand-mapped rather than trusting
# publications.json's own `pdf` field, which (as of this build) still points at older slide
# decks for two of these four -- the full papers are a separate, newer addition to the site
# that the JSON metadata hasn't been updated to reference yet.
PAPER_FILES: dict[str, str] = {
    "stroke-xai-ieee-access": (
        "Optimizing_Stroke_Recognition_With_MediaPipe_and_Machine_Learning_An_Explainable_AI_"
        "Approach_for_Facial_Landmark_Analysis.pdf"
    ),
    "ppg-sleep-4stage-xai": (
        "Improved_Photoplethysmography-Based_Four-Stage_Sleep_Classification_with_Explainable_"
        "AI-Driven_Machine_Learning.pdf"
    ),
    "ppg-sleep-ml": "Machine_Learning_Approaches_in_Photoplethysmography-Based_Sleep_Stage_Classification.pdf",
    "gesture-keyboard-jcsse-2026": (
        "Vision-based_Hand_Gesture_Virtual_Keyboard-Mouse_framework_with_Bilingual_Next-word_"
        "prediction.pdf"
    ),
}

# The resume's own section headings, exactly as resume.cls renders them (all-caps; verified
# against pypdf's extraction of the actual compiled PDF, not assumed from the .tex source --
# LaTeX macros uppercase these, and guessing wrong here would silently merge two sections).
RESUME_HEADINGS = [
    "OBJECTIVE", "EDUCATION", "TECHNICAL SKILLS", "WORK EXPERIENCE", "PUBLICATIONS",
    "PROJECTS", "CERTIFICATIONS", "HONORS & AWARDS", "VOLUNTEER EXPERIENCE", "REFERENCES",
]

# Site homepage sections with genuinely unique prose (see plan sec.2.2) -- #projects and
# #research are deliberately EXCLUDED because they restate data/projects.json verbatim, and
# ingesting both would put every project fact in the corpus twice in near-identical wording
# (the exact "handbook's leave clause is statutory boilerplate" failure this project's own
# README warns about, self-inflicted a second time).
SITE_SECTIONS: list[tuple[str, str]] = [
    ("home", "Introduction"),
    ("about", "About"),
    ("experience", "Experience"),
    ("certifications", "Certifications"),
    ("awards", "Awards & Honors"),
    ("cultural", "Cultural & Extracurricular"),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _mark_resume_headings(text: str) -> str:
    """Prefix each known section heading with '## ' so chunk_markdown() can split on it.

    Contact/name info before the first heading is deliberately dropped: chunk_markdown()
    never emits a chunk for the preamble before the first '#' line (see its parts[0]
    handling), which is the behaviour we want here too -- a phone number is not a fact the
    assistant should be quoting back at a visitor.
    """
    heading_set = set(RESUME_HEADINGS)
    lines = []
    for line in text.split("\n"):
        if line.strip() in heading_set:
            lines.append(f"## {line.strip()}")
        else:
            lines.append(line)
    return "\n".join(lines)



# TECHNICAL SKILLS is a LaTeX tabular (label column + value column). pypdf's default
# extraction glues the two together with NO space when they land on the same text line --
# "LanguagesPython, JavaScript/TypeScript, C/C++, SQL" -- which is invisible to a human
# reader but breaks verification.find_span()'s token-based matching: "LanguagesPython," is
# ONE token, so the model's correct, verbatim quote "Python, JavaScript/TypeScript, C/C++,
# SQL" can never match it and a directly-answerable question gets force-refused. FOUND BY
# RUNNING THE PIPELINE END-TO-END against a real question, not by reading the code -- this
# is exactly the class of bug "eyeball the chunks" alone would not have caught, since the
# concatenation is invisible unless you `repr()` the string.
#
# pypdf's extraction_mode="layout" was tried as a general fix and rejected: it preserves
# this table's spacing but breaks OTHER paragraphs' spacing instead ("AI/MLengineerand...")
# by misjudging proportional-font column widths elsewhere on the same page. A targeted fix
# for the one known-bad section beats a "general" fix that trades one corruption for
# another silently, and the build gate below still catches it if the labels ever change.
_SKILL_LABELS = [
    "Generative AI & LLMs", "Agentic AI & NLP", "ML & Computer Vision", "MLOps & Deployment",
    "Backend & Tools", "Hardware & Robotics", "Deep Learning", "Languages",
]
_SKILL_LABEL_RE = re.compile(
    "(" + "|".join(re.escape(label) for label in _SKILL_LABELS) + r")(?=\S)"
)


def _fix_skill_table_spacing(text: str) -> str:
    return _SKILL_LABEL_RE.sub(r"\1 ", text)


def build_resume_chunks() -> list[Chunk]:
    from pypdf import PdfReader

    reader = PdfReader(RESUME_PDF)
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    full_text = _fix_skill_table_spacing(full_text)
    marked = _mark_resume_headings(full_text)
    found = {h for h in RESUME_HEADINGS if f"## {h}" in marked}
    missing = set(RESUME_HEADINGS) - found
    if missing:
        raise SystemExit(
            f"BUILD GATE: resume PDF is missing expected section(s) {sorted(missing)} -- "
            "either the resume changed or pypdf's extraction of it did. Re-check "
            "RESUME_HEADINGS against a fresh `page.extract_text()` before re-running."
        )
    return chunk_markdown(
        marked, doc_id=MANIFEST["resume"]["doc_id"], doc_title=MANIFEST["resume"]["doc_title"],
        kind="resume",
    )


def _project_markdown(project: dict) -> str:
    sections = project.get("sections") or []
    parts = []
    if sections:
        # The top-level `description` is a shorter restatement of the SAME facts the first
        # `sections` entry already covers in more detail (measured: for lumenaa, description
        # and sections[0]["Overview"] are two phrasings of the same claim) -- including both
        # is the exact near-duplicate failure the plan's README warns about, just
        # self-inflicted on this corpus instead of inherited from the original one. Only
        # `description` alone (no sections) is a genuinely distinct fact worth a chunk.
        for section in sections:
            body = _strip_html(section["body"])
            if section.get("bullets"):
                body += "\n" + "\n".join(f"- {_strip_html(b)}" for b in section["bullets"])
            parts.append(f"## {section['title']}\n{body}")
    else:
        parts.append(f"## Overview\n{_strip_html(project['description'])}")
    if project.get("skills"):
        parts.append("## Tech stack & skills\n" + ", ".join(project["skills"]))
    return "\n\n".join(parts)


def build_project_chunks() -> list[Chunk]:
    projects = json.loads(PROJECTS_JSON.read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    for project in projects:
        markdown = _project_markdown(project)
        chunks += chunk_markdown(
            markdown, doc_id=project["slug"], doc_title=project["title"], kind="portfolio",
        )
    return chunks


def _publication_markdown(pub: dict) -> str:
    venue = pub.get("venue") or {}
    venue_line = ", ".join(
        v for v in (venue.get("name"), pub.get("dateDisplay"), venue.get("qualifier")) if v
    )
    parts = [f"## Venue\n{venue_line}"]
    if pub.get("contribution"):
        parts.append(f"## Contribution\n{_strip_html(pub['contribution'])}")
    authors = pub.get("authorsShort") or ", ".join(pub.get("authors") or [])
    if authors:
        parts.append(f"## Authors\n{_strip_html(authors)} ({pub.get('authorRole', 'Author')})")
    apa = (pub.get("citation") or {}).get("apa")
    if apa:
        parts.append(f"## Citation\n{_strip_html(apa)}")
    return "\n\n".join(parts)


def build_publication_metadata_chunks() -> list[Chunk]:
    """Structured metadata (venue, contribution, citation) -- NOT the paper text itself.

    See build_paper_chunks() for the full-text PDF chunks, which carry real page numbers.
    This function's chunks exist for the metadata a paper's PDF text doesn't self-describe
    (which conference, whose idea it was, the formatted citation) -- doc_id matches the
    paper chunks' doc_id so both are pinned together when a visitor is on that paper's page.
    """
    pubs = json.loads(PUBLICATIONS_JSON.read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    for pub in pubs:
        markdown = _publication_markdown(pub)
        chunks += chunk_markdown(
            markdown, doc_id=pub["slug"], doc_title=pub["title"], kind="portfolio",
        )
    return chunks


def build_paper_chunks() -> list[Chunk]:
    from pypdf import PdfReader

    pubs = {p["slug"]: p for p in json.loads(PUBLICATIONS_JSON.read_text(encoding="utf-8"))}
    chunks: list[Chunk] = []
    for slug, filename in PAPER_FILES.items():
        path = PAPERS_DIR / filename
        if not path.exists():
            raise SystemExit(f"BUILD GATE: paper PDF missing for {slug!r}: {path}")
        reader = PdfReader(path)
        pages = [page.extract_text() for page in reader.pages]
        chunks += chunk_paper_pdf(pages, doc_id=slug, doc_title=pubs[slug]["title"])
    return chunks


_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_BLANKLINES_RE = re.compile(r"\n{2,}")


def _html_to_text(fragment: str) -> str:
    """Like _strip_html, but for a whole multi-paragraph section: strips <script>/<style>
    blocks first, and turns each tag into a newline (rather than nothing) so block-level
    elements don't run separate lines of prose together into one word-salad line."""
    fragment = _SCRIPT_STYLE_RE.sub(" ", fragment)
    fragment = _TAG_RE.sub("\n", fragment)
    fragment = html_lib.unescape(fragment)
    fragment = _WS_RE.sub(" ", fragment)
    lines = [line.strip() for line in fragment.split("\n")]
    fragment = "\n".join(line for line in lines if line)
    return _BLANKLINES_RE.sub("\n\n", fragment).strip()


def _extract_site_section(html: str, section_id: str) -> str:
    # [^>]* consumes the REST of the opening tag (class=, data-*, etc.) through its closing
    # '>' -- matching only up to the id="..." attribute left "class=\"hero ...\">" as
    # literal text with no leading '<' for _TAG_RE to strip, and it leaked into every
    # section's first line (caught by eyeballing the built chunks, not by inspection).
    start_re = re.compile(rf'<section\s+id="{re.escape(section_id)}"[^>]*>')
    m = start_re.search(html)
    if not m:
        raise SystemExit(f"BUILD GATE: index.html has no <section id=\"{section_id}\">")
    rest = html[m.end():]
    next_m = re.search(r'<section\s+id="', rest)
    body = rest[: next_m.start()] if next_m else rest
    return _html_to_text(body)


def build_site_chunks() -> list[Chunk]:
    raw_html = INDEX_HTML.read_text(encoding="utf-8")
    markdown_parts = []
    for section_id, heading in SITE_SECTIONS:
        text = _extract_site_section(raw_html, section_id)
        if text:
            markdown_parts.append(f"## {heading}\n{text}")
    markdown = "\n\n".join(markdown_parts)
    return chunk_markdown(
        markdown, doc_id="site-home", doc_title="reshadulkarim.me — Home Page", kind="portfolio",
    )


def assert_persona_gate(chunks: list[Chunk]) -> None:
    """Fail the build, not the demo -- same principle as sections.py's assert_build_gate.

    A silently-empty pinned layer is the worst possible failure here: the assistant would
    answer EVERYTHING with "he doesn't list that," which is worse than the corpus never
    having shipped at all.
    """
    pinned = [c for c in chunks if c.doc_kind == "resume"]
    if not pinned:
        raise SystemExit("BUILD GATE: resume produced no chunks -- the pinned layer would be empty")
    # chunk_markdown() puts the heading in section_title, not in text -- so "EDUCATION" the
    # heading is real signal here even though the body prose under it never spells the word
    # "education" out. Check both, not just the body.
    joined = " ".join(f"{c.section_title or ''} {c.text}".lower() for c in pinned)
    for required in ("education", "skill", "experience"):
        if required not in joined:
            raise SystemExit(f"BUILD GATE: resume pinned text missing '{required}'")
    doc_ids = {c.doc_id for c in chunks}
    if len(doc_ids) < 5:  # resume + site-home + >=3 distinct project/publication doc_ids
        raise SystemExit(
            f"BUILD GATE: only {len(doc_ids)} distinct doc_ids in the persona corpus -- "
            "expected resume + site-home + many individual projects/publications"
        )


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass  # CI and production set real env vars

    chunks = (
        build_resume_chunks()
        + build_project_chunks()
        + build_publication_metadata_chunks()
        + build_paper_chunks()
        + build_site_chunks()
    )
    assert_persona_gate(chunks)
    resume_n = sum(c.doc_kind == "resume" for c in chunks)
    print(f"chunks: {len(chunks)} ({resume_n} resume + {len(chunks) - resume_n} portfolio)")
    print(f"distinct doc_ids: {len(set(c.doc_id for c in chunks))}")

    from src.providers.pinecone_embed import PineconeEmbedder

    vectors = PineconeEmbedder().embed_passages([c.text for c in chunks])
    if vectors.shape != (len(chunks), EMBED_DIM):
        raise SystemExit(f"embedding shape {vectors.shape} != ({len(chunks)}, {EMBED_DIM})")

    INDEX.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(INDEX / "index.npz", vectors=vectors)
    with (INDEX / "chunks.jsonl").open("w") as handle:
        for chunk in chunks:
            handle.write(chunk.model_dump_json() + "\n")

    meta = {
        "index_version": CHUNKER_VERSION,
        "embed_model_id": EMBED_MODEL_ID,
        "embed_dim": EMBED_DIM,
        "query_input_type": INPUT_TYPE_QUERY,
        "chunker_version": CHUNKER_VERSION,
        "chunk_count": len(chunks),
        "source_sha256": {
            "resume": _sha256(RESUME_PDF) if RESUME_PDF.exists() else None,
            "projects_json": _sha256(PROJECTS_JSON) if PROJECTS_JSON.exists() else None,
            "publications_json": _sha256(PUBLICATIONS_JSON) if PUBLICATIONS_JSON.exists() else None,
        },
        "index_bytes": int(vectors.nbytes),
    }
    (INDEX / "index_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"index: {vectors.nbytes / 1e6:.3f} MB -> {INDEX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

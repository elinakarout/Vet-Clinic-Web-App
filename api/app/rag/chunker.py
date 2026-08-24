"""Splits documents into ~800-char chunks with 100-char overlap, headings first. (Phase 6)

Pure text handling: no ChromaDB, no database, no embedding model. That is
deliberate -- it is the one part of the RAG pipeline that can be tested with no
dependencies at all, and `tests/test_rag.py` leans on that.

Two choices here are worth knowing about before changing anything:

1. **Every chunk carries its heading path in the embedded text.** A chunk reading
   "Dogs: DHPP at 8, 12 and 16 weeks" is far harder to retrieve than the same
   chunk starting "Vaccination schedules > Dogs". The heading path is prepended
   to `Chunk.text`, so it is embedded along with the body rather than being
   metadata the vector never sees. This is the single biggest retrieval-quality
   lever in the phase.

2. **Overlap applies within a section, never across one.** Section boundaries are
   already topical breaks; carrying 100 characters of vaccination schedule into
   the top of the surgery-aftercare chunk would just make both slightly wrong.

The size guarantee is ``len(chunk.text) <= max_chars + overlap``, not
``<= max_chars``. Body text is packed to a budget of ``max_chars`` minus the
heading prefix, and the carried overlap is then added on top of that budget --
so a chunk can run up to one overlap over. ``tests/test_rag.py`` asserts the
real bound rather than the round number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 800
OVERLAP = 100

# A line like "## Opening hours". Setext headings (underlined with === or ---)
# are not supported: nothing in data/knowledge/ uses them, and the fetcher emits
# ATX only.
_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
# Sentence end followed by whitespace. Deliberately crude -- it only has to find
# a decent split point inside an over-long paragraph, not parse English.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    """One embeddable slice of a document.

    `text` is what gets embedded and what the chatbot is shown, heading path
    included. `index` is the document-wide sequence used to build the chunk's
    deterministic id, `f"{document_id}:{chunk_index}"`.
    """

    text: str
    index: int
    heading_path: str


def split_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Peel a leading `---` YAML block off a document.

    scripts/fetch_external.py writes `title`/`source_url`/`fetched_at` there, and
    ingest reads them back for attribution. Only flat `key: value` pairs are
    understood -- this is not a YAML parser and does not need to be.
    """
    if not raw.startswith("---"):
        return {}, raw

    lines = raw.splitlines()
    # lines[0] is the opening fence; find the closing one.
    for end, line in enumerate(lines[1:], start=1):
        if line.strip() in {"---", "..."}:
            meta: dict[str, str] = {}
            for entry in lines[1:end]:
                key, sep, value = entry.partition(":")
                if sep and key.strip():
                    meta[key.strip()] = value.strip().strip("\"'")
            return meta, "\n".join(lines[end + 1 :])

    # An unterminated fence is not front matter -- treat the whole file as body.
    return {}, raw


def _sections(text: str) -> list[tuple[str, str]]:
    """Split on ATX headings into (heading_path, body) pairs, in document order.

    Fenced code blocks are tracked so a `#` comment inside one is not mistaken
    for a heading -- the clinic docs contain none today, but external HTML is
    converted to Markdown and can.
    """
    stack: list[tuple[int, str]] = []
    out: list[tuple[str, str]] = []
    body: list[str] = []
    in_fence = False
    fence_marker = ""

    def flush() -> None:
        joined = "\n".join(body).strip()
        path = " > ".join(title for _, title in stack)
        if joined or path:
            out.append((path, joined))
        body.clear()

    for line in text.splitlines():
        fence = _FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            body.append(line)
            continue

        heading = None if in_fence else _ATX.match(line)
        if heading is None:
            body.append(line)
            continue

        flush()
        level, title = len(heading.group(1)), heading.group(2).strip()
        # Pop siblings and deeper headings, keeping the ancestors this one sits
        # under, so an H3 still knows its H1 and H2.
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))

    flush()
    return out


def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _hard_split(text: str, limit: int) -> list[str]:
    """Last resort for a paragraph with no usable sentence break.

    Splits on whitespace so a word is never cut in half; a single token longer
    than `limit` (a URL, typically) is emitted whole rather than mangled.
    """
    pieces: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > limit:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _fit(paragraph: str, limit: int) -> list[str]:
    """Break one over-long paragraph into pieces that each fit `limit`."""
    if len(paragraph) <= limit:
        return [paragraph]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(paragraph):
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)

    # A "sentence" can still be longer than the limit on its own.
    out: list[str] = []
    for piece in pieces:
        out.extend(_hard_split(piece, limit) if len(piece) > limit else [piece])
    return out


def _tail(text: str, overlap: int) -> str:
    """The last ~`overlap` characters of `text`, trimmed to a word boundary."""
    if overlap <= 0 or not text:
        return ""
    tail = text[-overlap:]
    space = tail.find(" ")
    # Drop the partial leading word, unless that would leave nothing useful.
    return tail[space + 1 :] if 0 <= space < len(tail) - 1 else tail


def chunk_markdown(
    text: str, *, max_chars: int = MAX_CHARS, overlap: int = OVERLAP
) -> list[Chunk]:
    """Split a Markdown document into embeddable chunks.

    Headings first, then paragraphs for anything still too long, with `overlap`
    characters carried between consecutive chunks of the same section so a
    sentence spanning a boundary still appears whole somewhere.

    Deterministic: the same input always produces the same chunks, which is what
    lets ingest detect an unchanged file by comparing chunk text.
    """
    _, body = split_front_matter(text)
    chunks: list[Chunk] = []

    for heading_path, section_body in _sections(body):
        prefix = f"{heading_path}\n\n" if heading_path else ""
        # The prefix is embedded too, so the budget for body text is what is
        # left after it.
        budget = max(max_chars - len(prefix), 200)

        pieces: list[str] = []
        for paragraph in _paragraphs(section_body):
            pieces.extend(_fit(paragraph, budget))
        if not pieces:
            continue

        packed: list[str] = []
        current = ""
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if current and len(candidate) > budget:
                packed.append(current)
                carry = _tail(current, overlap)
                current = f"{carry}\n\n{piece}" if carry else piece
            else:
                current = candidate
        if current:
            packed.append(current)

        for piece in packed:
            chunks.append(
                Chunk(
                    text=f"{prefix}{piece}".strip(),
                    index=len(chunks),
                    heading_path=heading_path,
                )
            )

    return chunks

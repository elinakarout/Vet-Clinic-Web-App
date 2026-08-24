"""search_knowledge(query, k) -> passages, with a similarity floor. (Phase 6)

This module is the whole point of Phase 6 and the entire surface Phase 7 sees.
It is a plain function, not an endpoint: `POST /chat` and the
`search_clinic_knowledge` tool that wraps this are Phase 7's job.

**Returning nothing is a valid answer.** Chroma will always hand back its
``n_results`` nearest neighbours, however far away they are, so an unfiltered
search answers "what is the capital of France" with five confident-looking
paragraphs about rabbit vaccination. The floor is what turns that into an empty
list, and an empty list is what makes the chatbot say "I don't have that, please
call the clinic" instead of reciting something irrelevant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings
from app.rag import store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Passage:
    """One retrieved chunk, with enough metadata to cite it."""

    text: str
    title: str
    source_type: str
    source_url: str | None
    document_id: int
    chunk_index: int
    score: float


def _to_passages(results: dict) -> list[Passage]:
    """Flatten one query's Chroma results into Passages.

    Chroma returns cosine *distance*; the score below is ``1 - distance``. That is
    a true cosine similarity because the embedding function L2-normalises its
    output, and it is deliberately not clamped -- a negative similarity is
    meaningful and the floor discards it anyway.
    """
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    passages: list[Passage] = []
    for text, meta, distance in zip(documents, metadatas, distances):
        meta = meta or {}
        url = meta.get("source_url") or None
        passages.append(
            Passage(
                text=text,
                title=str(meta.get("title") or "Untitled"),
                source_type=str(meta.get("source_type") or ""),
                source_url=url,
                document_id=int(meta.get("document_id") or 0),
                chunk_index=int(meta.get("chunk_index") or 0),
                score=1.0 - float(distance),
            )
        )
    return passages


def search_knowledge(
    query: str,
    k: int | None = None,
    min_score: float | None = None,
) -> list[Passage]:
    """Search the clinic knowledge base, best match first.

    Returns at most ``k`` passages scoring at least ``min_score``, and an empty
    list when nothing clears the floor -- which is a normal outcome, not an error.
    Both arguments default to the configured values.
    """
    if not query or not query.strip():
        return []

    k = settings.retrieval_k if k is None else k
    floor = settings.retrieval_min_score if min_score is None else min_score
    if k <= 0:
        return []

    try:
        collection = store.get_collection()
        if collection.count() == 0:
            logger.warning(
                "Knowledge base is empty; run scripts/ingest_knowledge.py. "
                "Returning no passages."
            )
            return []
        results = collection.query(query_texts=[query], n_results=k)
    except store.VectorStoreError:
        # A store built with the wrong distance metric is a real misconfiguration
        # and must not be papered over.
        raise
    except Exception:
        # Anything else -- a missing directory, a corrupt store -- degrades to "no
        # information" so the chatbot stays up and honest.
        logger.exception("Knowledge base search failed; returning no passages.")
        return []

    passages = [p for p in _to_passages(results) if p.score >= floor]
    passages.sort(key=lambda p: p.score, reverse=True)
    return passages

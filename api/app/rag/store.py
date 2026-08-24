"""ChromaDB client + collection setup. (Phase 6)

Three things here are load-bearing and easy to break by accident.

**The client is lazy.** Everything else shared in this codebase -- ``settings``,
``engine``, ``pwd_context``, ``CLINIC_TZ`` -- is built eagerly at import, because
none of it costs anything. A ChromaDB client and an ONNX embedding model do, and
``tests/conftest.py`` imports ``app.main``, so an eager singleton here would make
all 185 pre-existing tests pay for a vector store they never touch. Hence
``get_collection()`` rather than a module-level constant.

**The space is cosine, and that is checked.** Chroma's default HNSW space is
``l2``. all-MiniLM-L6-v2 output is L2-normalised, so cosine is the meaningful
metric and ``score = 1 - distance`` is a real cosine similarity. The trap:
``get_or_create_collection`` on an existing directory returns the collection that
is *already there*, silently ignoring the configuration you asked for. A store
built as l2 would keep working, return plausible numbers, and make the similarity
floor meaningless -- with nothing failing. ``_check_space`` turns that into a
loud error.

**The embedder is Chroma's bundled ONNX all-MiniLM-L6-v2**, not
sentence-transformers. Same model -- Chroma's own source says it "implements the
same functionality as all-MiniLM-L6-v2 from sentence-transformers" -- but it
rides on onnxruntime, which chromadb already requires, instead of pulling torch.
See PHASE_6.md. The ~80 MB model downloads to ~/.cache/chroma/ on first *use*,
not on construction, so building the function stays cheap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.config import settings

if TYPE_CHECKING:  # pragma: no cover - import cost is the whole point
    from chromadb.api.models.Collection import Collection

SPACE = "cosine"

_collection: Any = None


class VectorStoreError(RuntimeError):
    """The store on disk is not the store this code expects."""


def _check_space(collection: Any) -> None:
    """Refuse a collection that was not built with cosine distance."""
    try:
        hnsw = (collection.configuration or {}).get("hnsw") or {}
        space = hnsw.get("space")
    except Exception:  # pragma: no cover - older/newer Chroma shapes
        return
    if space is not None and space != SPACE:
        raise VectorStoreError(
            f"Collection {collection.name!r} was created with hnsw space "
            f"{space!r}, but retrieval scores assume {SPACE!r}. Delete the store "
            f"and re-ingest:  rm -rf {settings.chroma_path} && "
            "python scripts/ingest_knowledge.py"
        )


def get_collection() -> Collection:
    """The one knowledge collection, created on first use and then memoised."""
    global _collection
    if _collection is not None:
        return _collection

    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name=settings.chroma_collection,
        embedding_function=embedding_functions.DefaultEmbeddingFunction(),
        configuration={"hnsw": {"space": SPACE}},
    )
    _check_space(collection)
    _collection = collection
    return collection


def reset_collection_cache() -> None:
    """Drop the memoised collection.

    Tests call this after re-pointing ``settings.chroma_path`` at a tmp_path;
    without it the second test in a module would silently reuse the first one's
    store.
    """
    global _collection
    _collection = None


def drop_collection() -> None:
    """Delete the collection entirely. Backs ``ingest_knowledge.py --rebuild``."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(settings.chroma_collection)
    except Exception:
        # Not existing is the desired end state, so it is not an error.
        pass
    reset_collection_cache()


def upsert_chunks(
    *,
    document_id: int,
    title: str,
    source_type: str,
    source_url: str | None,
    chunks: list[tuple[int, str]],
) -> None:
    """Write one document's chunks, keyed ``f"{document_id}:{chunk_index}"``.

    ``chunks`` is a list of ``(chunk_index, text)``. Chroma metadata values must
    be scalars, so a null source_url is stored as an empty string and read back
    as None by retrieve.py.
    """
    if not chunks:
        return
    collection = get_collection()
    collection.upsert(
        ids=[f"{document_id}:{index}" for index, _ in chunks],
        documents=[text for _, text in chunks],
        metadatas=[
            {
                "document_id": document_id,
                "title": title,
                "source_type": source_type,
                "source_url": source_url or "",
                "chunk_index": index,
            }
            for index, _ in chunks
        ],
    )


def delete_document_chunks(document_id: int) -> None:
    """Remove every chunk belonging to one document."""
    get_collection().delete(where={"document_id": document_id})


def all_ids() -> set[str]:
    """Every id currently in the collection, for the orphan sweep in ingest."""
    got = get_collection().get(include=[])
    return set(got.get("ids") or [])


def count() -> int:
    return get_collection().count()

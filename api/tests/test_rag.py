"""Phase 6 -- the RAG knowledge base: chunker, store, ingest, retrieval.

Two tiers, because they have very different costs.

**The chunker tests are pure.** No chromadb, no model, no database, no network.
They are the majority of this file and they run in milliseconds.

**The store/ingest/retrieval tests need chromadb** and are skipped without it, so
a checkout that has not installed the Phase 6 dependency still gets a green
suite. They inject a deterministic fake embedding function instead of the real
ONNX MiniLM: the real embedder is an ~80 MB download and a fresh model load per
process, and none of what is under test here is the *quality* of the vectors --
it is the plumbing around them. Retrieval quality is calibrated separately and
the measured numbers live in PHASE_6.md.

Isolation matters more than usual in the second tier. ``app.rag.store`` memoises
its collection in a module global, so every test that re-points
``settings.chroma_path`` must also call ``reset_collection_cache()`` or it
silently reuses the previous test's store. The ``rag_env`` fixture does both.

Three guards here were verified by breaking them and watching the test go red,
per this project's rule; the mutations are recorded in PHASE_6.md §Tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.rag.chunker import Chunk, chunk_markdown, split_front_matter

# --------------------------------------------------------------------------
# Tier 1: the chunker. Pure functions, no dependencies.
# --------------------------------------------------------------------------


def test_empty_document_produces_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  \n") == []


def test_a_document_with_no_headings_still_chunks():
    chunks = chunk_markdown("Just a sentence about cats.")
    assert len(chunks) == 1
    assert chunks[0].heading_path == ""
    assert "Just a sentence about cats." in chunks[0].text


def test_front_matter_is_split_off_not_embedded():
    raw = (
        "---\n"
        "title: Opening hours\n"
        "source_url: https://example.test/hours\n"
        "---\n\n"
        "# Opening hours\n\nWe open at nine.\n"
    )
    meta, body = split_front_matter(raw)
    assert meta["title"] == "Opening hours"
    assert meta["source_url"] == "https://example.test/hours"
    assert body.lstrip().startswith("# Opening hours")
    assert "source_url" not in body


def test_a_document_without_front_matter_is_returned_unchanged():
    raw = "# Hours\n\nNine to five.\n"
    meta, body = split_front_matter(raw)
    assert meta == {}
    assert body == raw


def test_a_hash_inside_a_fenced_code_block_is_not_a_heading():
    # The obvious line-by-line implementation gets this wrong, and the failure
    # is invisible: the chunk just gets filed under a heading that is really a
    # Python comment.
    text = (
        "# Real heading\n\n"
        "Some prose.\n\n"
        "```python\n"
        "# not a heading, this is a comment\n"
        "x = 1\n"
        "```\n\n"
        "More prose.\n"
    )
    paths = {c.heading_path for c in chunk_markdown(text)}
    assert paths == {"Real heading"}


def test_heading_path_is_prepended_to_the_embedded_text():
    text = "# Services\n\n## Dentistry\n\nDental cleaning costs 180 USD.\n"
    chunk = next(c for c in chunk_markdown(text) if "180 USD" in c.text)
    assert chunk.heading_path == "Services > Dentistry"
    # This is the retrieval lever: the chunk must *start* with its path so the
    # embedding carries the context, not just the bare sentence.
    assert chunk.text.startswith("Services > Dentistry")


def test_chunk_indexes_are_contiguous_from_zero():
    text = "# A\n\n" + "\n\n".join(f"Paragraph number {n}. " * 20 for n in range(8))
    chunks = chunk_markdown(text, max_chars=300, overlap=50)
    assert len(chunks) > 1
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_a_paragraph_longer_than_max_chars_is_split():
    long_paragraph = "The dog barked. " * 200  # ~3200 chars, one paragraph
    chunks = chunk_markdown("# Dogs\n\n" + long_paragraph, max_chars=400, overlap=50)
    assert len(chunks) > 1
    # The real bound is max_chars plus the carried overlap -- the overlap is
    # prepended on top of a full body budget rather than counted inside it.
    assert all(len(c.text) <= 400 + 50 for c in chunks)


def test_overlap_is_carried_within_a_section():
    text = "# One\n\n" + "\n\n".join(f"Sentence {n} about vaccination boosters." for n in range(30))
    chunks = chunk_markdown(text, max_chars=200, overlap=60)
    assert len(chunks) > 1
    first_tail = chunks[0].text[-40:]
    # Some part of the previous chunk's tail must reappear at the head of the
    # next one, or a fact split across the boundary is unfindable from either.
    assert any(word in chunks[1].text for word in first_tail.split() if len(word) > 4)


def test_overlap_is_not_carried_across_sections():
    text = (
        "# Vaccination\n\nRabies is given at sixteen weeks precisely.\n\n"
        "# Surgery\n\nFasting starts the night before.\n"
    )
    chunks = chunk_markdown(text, max_chars=200, overlap=60)
    surgery = next(c for c in chunks if c.heading_path == "Surgery")
    # A section boundary is already a topical break; carrying text across it
    # just files vaccination facts under Surgery.
    assert "Rabies" not in surgery.text


def test_heading_only_sections_are_dropped():
    text = "# Empty section\n\n## Also empty\n\n# Real\n\nContent here.\n"
    chunks = chunk_markdown(text)
    assert len(chunks) == 1
    assert "Content here." in chunks[0].text


def test_chunking_is_deterministic():
    text = "# A\n\nOne.\n\n## B\n\n" + ("Two. " * 300)
    assert chunk_markdown(text, max_chars=250) == chunk_markdown(text, max_chars=250)


def test_chunk_is_hashable_and_frozen():
    chunk = Chunk(text="x", index=0, heading_path="A")
    with pytest.raises(Exception):
        chunk.index = 1  # type: ignore[misc]


# --------------------------------------------------------------------------
# Tier 2: store, ingest and retrieval. Needs chromadb.
# --------------------------------------------------------------------------

chromadb = pytest.importorskip("chromadb", reason="Phase 6 dependency not installed")

from app.config import settings  # noqa: E402
from app.models import KnowledgeChunk, KnowledgeDocument, SourceType  # noqa: E402
from app.rag import ingest as ingest_mod  # noqa: E402
from app.rag import retrieve as retrieve_mod  # noqa: E402
from app.rag import store as store_mod  # noqa: E402

DIM = 64


class FakeEmbeddingFunction(chromadb.api.types.EmbeddingFunction):
    """Deterministic bag-of-words vectors. Same text in, same vector out.

    Not a good embedder -- it has no notion of synonymy -- but it is a *real*
    cosine space: documents sharing words score high, documents sharing none
    score near zero. That is exactly the property the floor and the ordering
    tests depend on, and it costs no download.

    Subclassing Chroma's EmbeddingFunction is not optional: the base class
    supplies ``embed_query``/``embed_documents``, which Collection.query calls.
    A plain callable embeds on write and then raises AttributeError on read --
    which retrieve.py catches and degrades to [], so the floor test would pass
    for entirely the wrong reason.
    """

    def __init__(self) -> None:
        # Chroma warns without one, and will require it.
        pass

    @staticmethod
    def name() -> str:
        return "fake-bow"

    @staticmethod
    def is_legacy() -> bool:
        return False

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * DIM
        for word in "".join(c.lower() if c.isalnum() else " " for c in text).split():
            digest = hashlib.sha1(word.encode()).digest()
            vector[digest[0] % DIM] += 1.0
        norm = sum(v * v for v in vector) ** 0.5
        return [v / norm for v in vector] if norm else [1.0] + [0.0] * (DIM - 1)

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "FakeEmbeddingFunction":
        return FakeEmbeddingFunction()


@pytest.fixture()
def rag_env(tmp_path, monkeypatch):
    """A knowledge base in tmp_path: own dirs, own store, own embedder.

    Never points at api/data -- neither dev.db nor the real Chroma directory is
    reachable from these tests.
    """
    from chromadb.utils import embedding_functions

    clinic = tmp_path / "knowledge" / "clinic"
    external = tmp_path / "knowledge" / "external"
    clinic.mkdir(parents=True)
    external.mkdir(parents=True)

    monkeypatch.setattr(settings, "clinic_knowledge_dir", str(clinic))
    monkeypatch.setattr(settings, "external_knowledge_dir", str(external))
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "chroma_collection", "test_knowledge")
    monkeypatch.setattr(
        embedding_functions, "DefaultEmbeddingFunction", FakeEmbeddingFunction
    )

    store_mod.reset_collection_cache()
    try:
        yield clinic, external
    finally:
        store_mod.reset_collection_cache()


def write(path: Path, name: str, body: str) -> Path:
    target = path / name
    target.write_text(body, encoding="utf-8")
    return target


PRICES = """# Services and prices

## Vaccination

A dog vaccination costs 40 to 85 USD depending on the vaccine given.

## Dentistry

A dental cleaning costs 180 USD and includes scaling and polishing.
"""

HOURS = """# Opening hours

The clinic is open Monday to Friday. We are closed at the weekend.
"""


def test_ingest_creates_documents_and_chunks(rag_env, db_session):
    clinic, _ = rag_env
    write(clinic, "services-and-prices.md", PRICES)
    write(clinic, "opening-hours.md", HOURS)

    report = ingest_mod.ingest_all(db_session)

    assert [r.status for r in report.files] == ["created", "created"]
    documents = db_session.query(KnowledgeDocument).all()
    assert len(documents) == 2
    assert {d.source_type for d in documents} == {SourceType.CLINIC}
    # The two halves of the dual write must agree. They are separate stores with
    # no shared transaction, so this is the assertion that catches drift.
    assert db_session.query(KnowledgeChunk).count() == store_mod.count()


def test_a_second_ingest_changes_nothing(rag_env, db_session):
    clinic, _ = rag_env
    write(clinic, "services-and-prices.md", PRICES)

    first = ingest_mod.ingest_all(db_session)
    sql_before = db_session.query(KnowledgeChunk).count()
    chroma_before = store_mod.count()

    second = ingest_mod.ingest_all(db_session)

    assert [r.status for r in second.files] == ["unchanged"]
    assert sum(r.chunks for r in second.files) == sum(r.chunks for r in first.files)
    assert db_session.query(KnowledgeChunk).count() == sql_before
    assert store_mod.count() == chroma_before


def test_editing_a_file_replaces_its_chunks_rather_than_adding_to_them(
    rag_env, db_session
):
    """MUTATION GUARD: delete-before-write in ingest_file.

    Removing the delete makes this test go red rather than the idempotency test
    above -- an unchanged file is skipped before the write path is reached, so
    only an *edited* file exercises the delete.
    """
    clinic, _ = rag_env
    path = write(clinic, "services-and-prices.md", PRICES)
    ingest_mod.ingest_all(db_session)
    before = db_session.query(KnowledgeChunk).count()

    path.write_text(PRICES.replace("180 USD", "195 USD"), encoding="utf-8")
    report = ingest_mod.ingest_all(db_session)

    assert [r.status for r in report.files] == ["updated"]
    assert db_session.query(KnowledgeChunk).count() == before
    assert store_mod.count() == before
    texts = " ".join(c.text for c in db_session.query(KnowledgeChunk).all())
    assert "195 USD" in texts and "180 USD" not in texts


def test_shortening_a_file_leaves_no_stale_vectors_behind(rag_env, db_session):
    """MUTATION GUARD: store.delete_document_chunks in ingest_file.

    Deliberately calls ingest_file rather than ingest_all. Chroma ids are
    deterministic, so an upsert overwrites chunks 0..n-1 and the counts still
    match when a file keeps its length -- only a file that gets *shorter*
    strands the tail vectors, and a stranded vector is worse than a missing one:
    it stays retrievable, gets cited, and is out of date.

    Going through ingest_all hides the bug entirely, because sweep_orphans
    repairs it on the way out. That sweep is the backstop for a half-failed
    write, not the mechanism, and ingest_file is public API in its own right --
    an earlier version of this test used ingest_all and passed with the delete
    removed.
    """
    clinic, _ = rag_env
    path = write(clinic, "services-and-prices.md", PRICES)
    ingest_mod.ingest_file(db_session, path, SourceType.CLINIC)
    assert store_mod.count() > 1

    path.write_text("# Services and prices\n\nAsk the front desk.\n", encoding="utf-8")
    ingest_mod.ingest_file(db_session, path, SourceType.CLINIC)

    assert db_session.query(KnowledgeChunk).count() == store_mod.count()
    assert retrieve_mod.search_knowledge("dental cleaning scaling", min_score=0.05) == []


def test_deleting_a_file_removes_its_document_chunks_and_vectors(rag_env, db_session):
    clinic, _ = rag_env
    write(clinic, "services-and-prices.md", PRICES)
    path = write(clinic, "opening-hours.md", HOURS)
    ingest_mod.ingest_all(db_session)
    total = store_mod.count()

    path.unlink()
    report = ingest_mod.ingest_all(db_session)

    assert len(report.deleted) == 1
    assert db_session.query(KnowledgeDocument).count() == 1
    assert store_mod.count() < total
    assert db_session.query(KnowledgeChunk).count() == store_mod.count()


def test_no_prune_keeps_a_document_whose_file_is_gone(rag_env, db_session):
    clinic, _ = rag_env
    path = write(clinic, "opening-hours.md", HOURS)
    ingest_mod.ingest_all(db_session)

    path.unlink()
    report = ingest_mod.ingest_all(db_session, prune=False)

    assert report.deleted == []
    assert db_session.query(KnowledgeDocument).count() == 1


def test_orphan_vectors_are_swept(rag_env, db_session):
    """The backstop for a Chroma write that outlived its SQL transaction."""
    clinic, _ = rag_env
    write(clinic, "opening-hours.md", HOURS)
    ingest_mod.ingest_all(db_session)
    real = store_mod.count()

    store_mod.get_collection().upsert(
        ids=["999:0"],
        documents=["An orphan with no row in knowledge_chunks."],
        metadatas=[{"document_id": 999, "title": "Ghost", "source_type": "CLINIC",
                    "source_url": "", "chunk_index": 0}],
    )
    assert store_mod.count() == real + 1

    removed = ingest_mod.sweep_orphans(db_session)

    assert removed == 1
    assert store_mod.count() == real


def test_external_front_matter_becomes_the_source_url(rag_env, db_session):
    _, external = rag_env
    write(
        external,
        "fda-chocolate.md",
        "---\ntitle: Chocolate is toxic to dogs (FDA)\n"
        "source_url: https://www.fda.gov/example\n---\n\n"
        "# Chocolate\n\nTheobromine is toxic to dogs and can cause seizures.\n",
    )
    ingest_mod.ingest_all(db_session)

    document = db_session.query(KnowledgeDocument).one()
    assert document.source_type == SourceType.EXTERNAL
    assert document.title == "Chocolate is toxic to dogs (FDA)"
    assert document.source_url == "https://www.fda.gov/example"


def test_search_returns_the_right_document_with_its_source(rag_env, db_session):
    clinic, _ = rag_env
    write(clinic, "services-and-prices.md", PRICES)
    write(clinic, "opening-hours.md", HOURS)
    ingest_mod.ingest_all(db_session)

    passages = retrieve_mod.search_knowledge("dental cleaning price", min_score=0.05)

    assert passages
    assert "dental cleaning" in passages[0].text.lower()
    assert passages[0].title == "Services and prices"
    assert passages[0].source_type == "CLINIC"
    assert passages[0].document_id > 0


def test_results_are_ordered_by_descending_score(rag_env, db_session):
    """MUTATION GUARD: score = 1 - distance.

    Returning the raw distance inverts the ranking, which no smoke test would
    notice -- the same passages come back, in the wrong order.
    """
    clinic, _ = rag_env
    write(clinic, "services-and-prices.md", PRICES)
    write(clinic, "opening-hours.md", HOURS)
    ingest_mod.ingest_all(db_session)

    passages = retrieve_mod.search_knowledge("dental cleaning scaling polishing",
                                             k=5, min_score=-1.0)

    assert len(passages) > 1
    assert [p.score for p in passages] == sorted((p.score for p in passages), reverse=True)
    assert "dental" in passages[0].text.lower()
    assert passages[0].score > passages[-1].score


def test_an_unrelated_query_returns_nothing(rag_env, db_session):
    """MUTATION GUARD: the >= min_score filter.

    Without the floor a vector search always returns its k nearest neighbours,
    however far away they are -- so the chatbot would confidently cite the
    price list when asked about matrix rotation.
    """
    clinic, _ = rag_env
    write(clinic, "services-and-prices.md", PRICES)
    ingest_mod.ingest_all(db_session)

    assert retrieve_mod.search_knowledge("quantum chromodynamics lagrangian") == []


def test_an_empty_query_never_touches_the_store(rag_env):
    assert retrieve_mod.search_knowledge("") == []
    assert retrieve_mod.search_knowledge("   ") == []
    assert retrieve_mod.search_knowledge("anything", k=0) == []


def test_an_empty_store_returns_no_passages_rather_than_raising(rag_env):
    # Phase 7's tool must be able to say "I don't have that" instead of 500ing
    # the chat endpoint when the ingest script has not been run.
    assert retrieve_mod.search_knowledge("dog vaccination cost") == []


def test_a_collection_built_with_the_wrong_space_is_refused(rag_env):
    """get_or_create_collection silently returns the *existing* collection.

    So a store built when the space was l2 keeps being used with cosine scoring
    and every score is wrong, with nothing failing. The guard turns that into a
    loud error naming the fix.
    """
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    client.get_or_create_collection(
        name=settings.chroma_collection,
        embedding_function=FakeEmbeddingFunction(),
        configuration={"hnsw": {"space": "l2"}},
    )
    store_mod.reset_collection_cache()

    with pytest.raises(store_mod.VectorStoreError) as exc:
        store_mod.get_collection()
    assert "rm -rf" in str(exc.value)


def test_drop_collection_empties_the_store(rag_env, db_session):
    clinic, _ = rag_env
    write(clinic, "opening-hours.md", HOURS)
    ingest_mod.ingest_all(db_session)
    assert store_mod.count() > 0

    store_mod.drop_collection()

    assert store_mod.count() == 0


def test_discover_finds_clinic_and_external_markdown_only(rag_env):
    clinic, external = rag_env
    write(clinic, "opening-hours.md", HOURS)
    write(external, "fda.md", "# X\n\nY.\n")
    write(clinic, "notes.txt", "not markdown")

    found = ingest_mod.discover()

    assert {p.name for p, _ in found} == {"opening-hours.md", "fda.md"}
    assert dict((p.name, t) for p, t in found)["fda.md"] == SourceType.EXTERNAL


def test_an_empty_markdown_file_is_reported_not_ingested(rag_env, db_session):
    clinic, _ = rag_env
    write(clinic, "blank.md", "\n\n   \n")

    report = ingest_mod.ingest_all(db_session)

    assert [r.status for r in report.files] == ["empty"]
    assert db_session.query(KnowledgeChunk).count() == 0

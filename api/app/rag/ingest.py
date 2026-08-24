"""load -> chunk -> embed -> store pipeline, idempotent by document_id. (Phase 6)

Ingest writes to two places that cannot share a transaction: the SQL tables
``knowledge_documents``/``knowledge_chunks``, and the ChromaDB collection. Four
rules keep them in step.

1. **Documents are keyed by ``source_path``.** Phase 1 gave that column a unique
   index for exactly this -- it is how a file on disk maps back to its row on the
   next run.

2. **Chunk ids are deterministic:** ``f"{document_id}:{chunk_index}"``. Re-running
   overwrites the same ids rather than adding new ones, which is what makes the
   whole script idempotent.

3. **An unchanged file is skipped entirely** -- no embedding, no upsert. There is
   no ``content_hash`` column and adding one would mean a migration, so "changed"
   is decided by comparing the freshly computed chunk texts against the chunk rows
   already in SQL. The chunker is deterministic, so that comparison is exact.

4. **Chroma is written before the SQL commit**, and ``ingest_all`` finishes with a
   sweep that deletes Chroma ids with no SQL row behind them. Chroma has no
   rollback, so the order puts the un-undoable write first: if it throws, SQL rolls
   back and nothing is half-done. The one gap left -- Chroma succeeded, the commit
   then failed -- is repaired by the sweep on the next run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import KnowledgeChunk, KnowledgeDocument, SourceType
from app.rag import store
from app.rag.chunker import chunk_markdown, split_front_matter

# Where source_path is measured from. Both roots are recorded relative to the
# api/ working directory, so "knowledge/clinic/opening-hours.md" and
# "data/knowledge/external/foo.md" are stable across machines.
_BASE = Path(".")


@dataclass
class FileResult:
    source_path: str
    title: str
    status: str  # created | updated | unchanged | empty
    chunks: int = 0


@dataclass
class IngestReport:
    files: list[FileResult] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    orphans_removed: int = 0

    def count(self, status: str) -> int:
        return sum(1 for f in self.files if f.status == status)

    @property
    def total_chunks(self) -> int:
        return sum(f.chunks for f in self.files)


def _roots() -> list[tuple[Path, SourceType]]:
    return [
        (Path(settings.clinic_knowledge_dir), SourceType.CLINIC),
        (Path(settings.external_knowledge_dir), SourceType.EXTERNAL),
    ]


def _relative(path: Path) -> str:
    """The stored source_path: relative to api/ where possible, else absolute."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(_BASE.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _title_for(path: Path, meta: dict[str, str], body: str) -> str:
    """Front-matter title, else the first H1, else a prettified filename."""
    if meta.get("title"):
        return meta["title"][:300]
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()[:300]
    return path.stem.replace("-", " ").replace("_", " ").capitalize()[:300]


def discover(source_type: SourceType | None = None) -> list[tuple[Path, SourceType]]:
    """Every Markdown file under the knowledge roots, sorted for stable output."""
    found: list[tuple[Path, SourceType]] = []
    for root, kind in _roots():
        if source_type is not None and kind is not source_type:
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.is_file():
                found.append((path, kind))
    return found


def ingest_file(db: Session, path: Path, source_type: SourceType) -> FileResult:
    """Bring one file's SQL rows and Chroma vectors up to date."""
    raw = path.read_text(encoding="utf-8")
    meta, body = split_front_matter(raw)
    source_path = _relative(path)
    title = _title_for(path, meta, body)
    source_url = meta.get("source_url") or None

    chunks = chunk_markdown(raw)
    if not chunks:
        return FileResult(source_path=source_path, title=title, status="empty")

    document = db.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.source_path == source_path)
    )
    created = document is None
    if document is None:
        document = KnowledgeDocument(
            title=title,
            source_type=source_type,
            source_url=source_url,
            source_path=source_path,
        )
        db.add(document)
    else:
        document.title = title
        document.source_type = source_type
        document.source_url = source_url

    # document.id is an autoincrement PK, and chroma_id is built from it, so the
    # row has to reach the database before the ids can be formed.
    db.flush()

    existing = list(
        db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document.id)
            .order_by(KnowledgeChunk.chunk_index)
        )
    )
    if not created and [c.text for c in existing] == [c.text for c in chunks]:
        # Same bytes in, same chunks out. Nothing to embed.
        return FileResult(
            source_path=source_path,
            title=title,
            status="unchanged",
            chunks=len(existing),
        )

    for row in existing:
        db.delete(row)
    db.flush()

    for chunk in chunks:
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=chunk.index,
                text=chunk.text,
                chroma_id=f"{document.id}:{chunk.index}",
            )
        )

    # Chroma first: it cannot be rolled back, so a failure here must leave the
    # database untouched rather than the other way round.
    store.delete_document_chunks(document.id)
    store.upsert_chunks(
        document_id=document.id,
        title=title,
        source_type=source_type.value,
        source_url=source_url,
        chunks=[(c.index, c.text) for c in chunks],
    )
    db.commit()

    return FileResult(
        source_path=source_path,
        title=title,
        status="created" if created else "updated",
        chunks=len(chunks),
    )


def prune_deleted(db: Session) -> list[str]:
    """Drop documents whose file is gone from disk. Chunks cascade."""
    removed: list[str] = []
    for document in db.scalars(select(KnowledgeDocument)).all():
        if document.source_path and Path(document.source_path).exists():
            continue
        store.delete_document_chunks(document.id)
        removed.append(document.source_path or document.title)
        db.delete(document)
    if removed:
        db.commit()
    return removed


def sweep_orphans(db: Session) -> int:
    """Delete Chroma ids with no chunk row behind them.

    The backstop for the one window the write order cannot protect: the Chroma
    upsert landed and the SQL commit then failed. Ids are deterministic, so the
    next run always sees the discrepancy.
    """
    known = set(db.scalars(select(KnowledgeChunk.chroma_id)).all())
    orphans = sorted(store.all_ids() - known)
    if orphans:
        store.get_collection().delete(ids=orphans)
    return len(orphans)


def ingest_all(db: Session, *, prune: bool = True) -> IngestReport:
    """Run the whole pipeline over both knowledge roots."""
    report = IngestReport()
    for path, source_type in discover():
        report.files.append(ingest_file(db, path, source_type))
    if prune:
        report.deleted = prune_deleted(db)
    report.orphans_removed = sweep_orphans(db)
    return report

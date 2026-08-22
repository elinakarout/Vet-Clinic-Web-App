"""SQLAlchemy models: knowledge_documents, knowledge_chunks. (Phase 1 schema, Phase 6 uses it)"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceType(str, enum.Enum):
    CLINIC = "CLINIC"      # markdown written by the clinic
    EXTERNAL = "EXTERNAL"  # fetched from an allowlisted source


class KnowledgeDocument(Base):
    """One source document. Its chunks are what actually get embedded."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", native_enum=False, length=16, validate_strings=True),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(String(1000))
    # Relative to api/data/knowledge/, so re-ingest can find the file again.
    source_path: Mapped[str | None] = mapped_column(String(500), unique=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeChunk.chunk_index",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<KnowledgeDocument id={self.id} title={self.title!r}>"


class KnowledgeChunk(Base):
    """A ~800-character slice of a document. chroma_id is f"{document_id}:{chunk_index}"."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chroma_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<KnowledgeChunk id={self.id} chroma_id={self.chroma_id!r}>"

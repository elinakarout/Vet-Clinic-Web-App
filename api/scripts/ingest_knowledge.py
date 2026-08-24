"""Rebuilds the ChromaDB vector store from data/knowledge/. Idempotent. (Phase 6)

Reads Markdown from two roots -- the tracked, hand-written clinic docs in
api/knowledge/clinic/ and whatever scripts/fetch_external.py has fetched into
api/data/knowledge/external/ -- chunks it, embeds it locally, and writes both the
SQL bookkeeping rows and the vectors.

Running it twice changes nothing: the second run reports every document as
"unchanged" and neither the chunk count nor the vector count moves.

Run from api/ with the venv active:

    python scripts/ingest_knowledge.py
    python scripts/ingest_knowledge.py --rebuild     # drop the vectors first
    python scripts/ingest_knowledge.py --dry-run     # chunk only, write nothing
    python scripts/ingest_knowledge.py --no-prune    # keep rows for deleted files
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow "python scripts/ingest_knowledge.py" without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import SessionLocal
from app.rag import store
from app.rag.chunker import chunk_markdown
from app.rag.ingest import discover, ingest_all


def _dry_run() -> None:
    """Chunk everything and report, without touching the database or Chroma."""
    files = discover()
    if not files:
        print("No Markdown found. Looked in:")
        print(f"  {settings.clinic_knowledge_dir}")
        print(f"  {settings.external_knowledge_dir}")
        return

    total = 0
    print(f"{'chunks':>7}  {'chars':>7}  source")
    print(f"{'-' * 7}  {'-' * 7}  {'-' * 50}")
    for path, _ in files:
        chunks = chunk_markdown(path.read_text(encoding="utf-8"))
        total += len(chunks)
        longest = max((len(c.text) for c in chunks), default=0)
        print(f"{len(chunks):>7}  {longest:>7}  {path}")
    print(f"\n{total} chunks from {len(files)} file(s). Nothing was written.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="delete the Chroma collection first, then ingest everything fresh",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="chunk and report only; write nothing",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="keep rows whose source file has been deleted from disk",
    )
    args = parser.parse_args()

    if args.dry_run:
        _dry_run()
        return

    if args.rebuild:
        store.drop_collection()
        print("Dropped the existing collection.")

    with SessionLocal() as db:
        report = ingest_all(db, prune=not args.no_prune)

    if not report.files:
        print("No Markdown found. Looked in:")
        print(f"  {settings.clinic_knowledge_dir}")
        print(f"  {settings.external_knowledge_dir}")
        return

    print(f"{'status':>9}  {'chunks':>6}  source")
    print(f"{'-' * 9}  {'-' * 6}  {'-' * 50}")
    for result in report.files:
        print(f"{result.status:>9}  {result.chunks:>6}  {result.source_path}")

    for path in report.deleted:
        print(f"{'deleted':>9}  {'-':>6}  {path}")

    print(
        f"\n{report.count('created')} created, "
        f"{report.count('updated')} updated, "
        f"{report.count('unchanged')} unchanged, "
        f"{len(report.deleted)} deleted."
    )
    if report.orphans_removed:
        print(f"Swept {report.orphans_removed} orphaned vector(s).")
    print(f"{report.total_chunks} chunks in SQL, {store.count()} vectors in Chroma.")


if __name__ == "__main__":
    main()

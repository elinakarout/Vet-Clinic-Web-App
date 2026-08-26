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


def _embedder_cache_hint() -> str:
    """Describe the local ONNX model cache, if it looks incomplete. (Phase 9)

    Chroma downloads all-MiniLM-L6-v2 on first use and unpacks it beside the
    tarball. Phase 9's QA pass hit a half-written onnx.tar.gz -- 1.6 MB of an
    80 MB file, left behind by an earlier timeout -- and every retry spent 49
    seconds re-reading it before dying in an httpx traceback that never named
    the file. A partial download is the likeliest cause of a timeout here, so
    say so.
    """
    cache = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2"
    tarball = cache / "onnx.tar.gz"
    unpacked = cache / "onnx"
    if unpacked.is_dir():
        return ""
    if tarball.exists():
        mb = tarball.stat().st_size / 1_000_000
        return (
            f"\n  The model cache at {cache} looks incomplete:\n"
            f"  onnx.tar.gz is {mb:.1f} MB (a complete one is ~80 MB) and has not\n"
            f"  been unpacked. Delete that directory and run this again to\n"
            f"  re-download it, or copy a working cache in from another machine."
        )
    return (
        f"\n  The embedding model is not cached yet ({cache} is empty), so this\n"
        f"  run had to download ~80 MB. That is a one-time cost; the retry will\n"
        f"  resume from whatever completed."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("\nInterrupted. Nothing was left half-written: each file is\ncommitted separately, so re-running picks up where this stopped.") from None
    except Exception as exc:  # noqa: BLE001 -- a CLI's job is to not show a traceback
        # Anything that reaches here is a failed run, not a bug the user can
        # act on from a stack trace. Network faults dominate: the embedder
        # download is the only step that touches the internet.
        name = type(exc).__name__
        detail = str(exc).strip() or "(no message)"
        message = [
            "",
            "Ingest failed.",
            "",
            f"  {name}: {detail}",
        ]
        if "timeout" in name.lower() or "timeout" in detail.lower() or "connect" in name.lower():
            hint = _embedder_cache_hint()
            if hint:
                message.append(hint)
        message += [
            "",
            "  Nothing is half-written: documents are committed one at a time and",
            "  ingest is idempotent, so running it again resumes safely.",
            "  Re-run with --dry-run to chunk everything without touching the store.",
            "",
        ]
        raise SystemExit("\n".join(message)) from None

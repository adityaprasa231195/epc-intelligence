"""
RAGEngine — Pure Python in-memory store (no ChromaDB).

Replaces ChromaDB to avoid segfaults on Streamlit Cloud Linux environment.
Uses keyword overlap scoring — sufficient since RFI agent uses full-context injection.
"""
import os
import uuid
import logging
import hashlib
from typing import Any

import config

logger = logging.getLogger(__name__)


def _keyword_score(query: str, chunk: str) -> float:
    """BM25-style term overlap score."""
    q_terms = set(query.lower().split())
    c_terms = set(chunk.lower().split())
    if not q_terms:
        return 0.0
    return len(q_terms & c_terms) / len(q_terms)


class RAGEngine:
    """
    Pure Python in-memory document store with keyword search.
    No external dependencies — zero crash risk on any platform.
    """

    def __init__(self) -> None:
        # Simple list of {id, document, source}
        self._store: list[dict] = []
        logger.info("RAGEngine initialised (pure Python in-memory store)")

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk(
        text: str,
        size: int = config.RAG_CHUNK_SIZE,
        overlap: int = config.RAG_CHUNK_OVERLAP,
    ) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + size].strip())
            start += size - overlap
        return [c for c in chunks if c]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(self, text: str, source_label: str) -> int:
        """Chunk and store text. Returns number of chunks stored."""
        chunks = self._chunk(text)
        for chunk in chunks:
            self._store.append({
                "id": str(uuid.uuid4()),
                "document": chunk,
                "source": source_label,
            })
        logger.info("Ingested %d chunks from '%s'", len(chunks), source_label)
        return len(chunks)

    def ingest_file(self, filepath: str, source_label: str | None = None) -> int:
        """Read a .txt or .pdf file and ingest it."""
        label = source_label or os.path.basename(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(filepath)
                text = "\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
            except Exception as exc:
                logger.warning("PDF read failed for %s: %s", filepath, exc)
                return 0
        else:
            with open(filepath, encoding="utf-8") as f:
                text = f.read()
        return self.ingest(text, label)

    def query(self, question: str, top_k: int = config.RAG_TOP_K) -> list[dict[str, Any]]:
        """
        Keyword overlap search. Returns top-k results sorted by score.
        """
        if not self._store:
            return []
        scored = [
            {
                "chunk": doc["document"],
                "source": doc["source"],
                "score": _keyword_score(question, doc["document"]),
            }
            for doc in self._store
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def collection_count(self) -> int:
        return len(self._store)

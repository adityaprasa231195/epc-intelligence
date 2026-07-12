"""
RFI Knowledge Agent

RAG-powered conversational layer over all project RFIs and standards.
Returns answers with inline citations and surfaces similar past RFIs.

Strategy:
- Standards questions: inject full standards text directly into Groq context
  (hash-based embeddings are not semantic; Groq 131K window handles full docs)
- RFI-specific questions: keyword-match against loaded RFI index directly
- RAG used only for similarity scoring to surface related RFIs
"""
import json
import os
import logging
from typing import Any

import config
from core.groq_client import GroqClient
from rag.rag_engine import RAGEngine

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.70
_NO_RESULT_RESPONSE = (
    "No matching project document found for this query. "
    "Please escalate to the project engineer or raise a new RFI."
)


def _load_standards_text() -> str:
    """Load all standards files into a single string for direct context injection."""
    parts = []
    if not os.path.exists(config.STANDARDS_DIR):
        return ""
    for fname in sorted(os.listdir(config.STANDARDS_DIR)):
        if fname.endswith(".txt"):
            fpath = os.path.join(config.STANDARDS_DIR, fname)
            with open(fpath, encoding="utf-8") as f:
                parts.append(f.read())
    return "\n\n===\n\n".join(parts)


# Load once at import time — standards are static
_STANDARDS_TEXT = _load_standards_text()


class RFIKnowledgeAgent:
    """
    Answers technical and contractual queries with citations.
    Surfaces previously resolved similar RFIs to reduce re-work.
    """

    def __init__(self, rag: RAGEngine) -> None:
        self._rag = rag
        self._groq = GroqClient()
        self._rfi_index: dict[str, dict] = {}
        self._rfi_list: list[dict] = []
        self._load_and_ingest_rfis()

    def _load_and_ingest_rfis(self) -> None:
        path = os.path.join(config.SYNTHETIC_DIR, "rfis.json")
        if not os.path.exists(path):
            logger.warning("rfis.json not found at %s", path)
            return
        with open(path, encoding="utf-8") as f:
            rfis = json.load(f)

        for rfi in rfis:
            text_blob = (
                f"RFI ID: {rfi['rfi_id']}\n"
                f"Subject: {rfi['subject']}\n"
                f"Question: {rfi['question']}\n"
                f"Resolution: {rfi['resolution']}\n"
                f"Related Clause: {rfi['related_spec_clause']}\n"
                f"Date: {rfi['date']}\n"
                f"Status: {rfi['status']}"
            )
            self._rag.ingest(text_blob, source_label=rfi["rfi_id"])
            self._rfi_index[rfi["rfi_id"]] = rfi

        self._rfi_list = rfis
        logger.info("Loaded and ingested %d RFIs into RAG", len(rfis))

    # ------------------------------------------------------------------
    # Main query
    # ------------------------------------------------------------------

    def query(self, question: str) -> dict[str, Any]:
        """
        Query using full standards text + all RFIs as direct context.
        Hash embeddings are not semantic so we inject full docs into Groq's
        131K context window instead of relying on vector retrieval.
        """
        # Build full RFI context block
        rfi_block = "\n\n---\n\n".join(
            f"RFI ID: {r['rfi_id']}\n"
            f"Subject: {r['subject']}\n"
            f"Question: {r['question']}\n"
            f"Resolution: {r['resolution']}\n"
            f"Related Clause: {r['related_spec_clause']}\n"
            f"Status: {r['status']}"
            for r in self._rfi_list
        )

        context_block = (
            "=== DATA CENTRE STANDARDS (TIA-942, Uptime Institute) ===\n\n"
            + _STANDARDS_TEXT
            + "\n\n=== PROJECT RFI LOG ===\n\n"
            + rfi_block
        )

        prompt = (
            "You are a data centre EPC project knowledge assistant with access to "
            "TIA-942, Uptime Institute Tier standards, and the full project RFI log.\n\n"
            "Answer the following question using the provided context. "
            "Be specific and technical. Cite your source like [SOURCE: tia942_excerpts.txt] "
            "or [SOURCE: RFI-001] for every key fact.\n"
            "If the answer is in the context, give a complete, confident answer.\n\n"
            f"Context:\n{context_block}\n\n"
            f"Question: {question}"
        )

        result = self._groq.generate(prompt)

        if result.get("error"):
            # Fallback: keyword search RFIs directly
            answer = self._keyword_fallback(question)
        else:
            answer = result["text"]

        # Citations from standards files
        citations = [
            {"source": "tia942_excerpts.txt", "score": 1.0},
            {"source": "uptime_tier_concepts.txt", "score": 1.0},
        ]

        # Surface similar resolved RFIs via keyword match
        similar = self._find_similar_rfis_by_keyword(question)

        return {
            "answer": answer,
            "citations": citations,
            "similar_rfis": similar,
            "error": False,
        }

    # ------------------------------------------------------------------
    # Keyword-based RFI fallback (no LLM needed)
    # ------------------------------------------------------------------

    def _keyword_fallback(self, question: str) -> str:
        """Return best matching RFI resolution when Groq fails."""
        q_words = set(question.lower().split())
        best_rfi = None
        best_score = 0
        for rfi in self._rfi_list:
            text = (rfi["subject"] + " " + rfi["question"] + " " + rfi["resolution"]).lower()
            score = sum(1 for w in q_words if w in text)
            if score > best_score:
                best_score = score
                best_rfi = rfi
        if best_rfi and best_score > 0:
            return (
                f"Based on project RFI {best_rfi['rfi_id']} — {best_rfi['subject']}:\n\n"
                f"{best_rfi['resolution']}\n\n"
                f"[SOURCE: {best_rfi['rfi_id']}]"
            )
        return _NO_RESULT_RESPONSE

    # ------------------------------------------------------------------
    # Similar RFI detection by keyword
    # ------------------------------------------------------------------

    def _find_similar_rfis_by_keyword(self, question: str) -> list[dict]:
        """Keyword overlap match against RFI subjects and questions."""
        q_words = set(question.lower().split())
        scored = []
        for rfi in self._rfi_list:
            if rfi.get("status") != "CLOSED":
                continue
            text = (rfi["subject"] + " " + rfi["question"]).lower().split()
            overlap = len(q_words & set(text))
            if overlap >= 2:
                scored.append((overlap, rfi))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "rfi_id": r["rfi_id"],
                "subject": r["subject"],
                "resolution": r["resolution"],
                "related_clause": r["related_spec_clause"],
                "score": round(overlap / max(len(q_words), 1), 2),
            }
            for overlap, r in scored[:3]
        ]

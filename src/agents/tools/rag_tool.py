"""
RAG Tool -- Internal knowledge-base retrieval via CAG + CRAG pipeline.
"""

from loguru import logger
import time
from typing import Any, Dict, List, Optional

from infrastructure.config import (
    TOP_K_RESULTS,
    SIMILARITY_THRESHOLD,
    CRAG_CONFIDENCE_THRESHOLD,
    CRAG_EXPANDED_K,
)
from infrastructure.observability import observe, update_current_observation


class RAGTool:
    """
    Internal-KB retrieval tool backed by CAGService (cache) + CRAGService (CRAG).

    The tool is a thin wrapper that:
    1. Builds the service stack (CAGCache -> CRAGService -> CAGService)
    2. Delegates all retrieval to CAGService.generate()
    3. Handles warm-up, stats, and dispatch routing
    """

    def __init__(
        self,
        embedder: Any,
        llm: Optional[Any] = None,
    ) -> None:
        self.embedder = embedder
        self.llm = llm

        from services.chat_service.cag_cache import CAGCache
        from services.chat_service.rag_service import QdrantRetriever, RAGService
        from services.chat_service.crag_service import CRAGService
        from services.chat_service.cag_service import CAGService

        self._cache = CAGCache(embedder=embedder)

        self._cag_service: Optional[CAGService] = None

        if llm is not None:
            retriever = QdrantRetriever(
                embedder=embedder,
                top_k=TOP_K_RESULTS,
                score_threshold=SIMILARITY_THRESHOLD,
            )

            crag_service = CRAGService(
                retriever=retriever,
                llm=llm,
                initial_k=TOP_K_RESULTS,
                expanded_k=CRAG_EXPANDED_K,
            )

            self._cag_service = CAGService(
                crag_service=crag_service,
                cache=self._cache,
            )

            logger.info(
                "RAGTool initialised: CAG cache ({}) -> CRAG (k={}, expanded_k={}, threshold={:.2f})",
                self._cache,
                TOP_K_RESULTS,
                CRAG_EXPANDED_K,
                CRAG_CONFIDENCE_THRESHOLD,
            )
        else:
            logger.info("RAGTool initialised in raw-chunk mode (no LLM)")

    @observe(name="rag_search")
    def search(
        self,
        query: str,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD,
        use_cache: bool = True,
    ) -> str:
        """
        Retrieve + generate an answer from the internal KB.

        Pipeline: CAG cache check -> CRAG (confidence-gated) -> answer
        """
        if self._cag_service is not None:
            try:
                result = self._cag_service.generate(query, use_cache=use_cache)
                return result.get("answer", "") or "No relevant information found in the internal knowledge base."
            except Exception as exc:
                logger.error("CAG+CRAG pipeline failed: {}", exc)
                return self._raw_search(query, top_k, threshold)
        else:
            return self._raw_search(query, top_k, threshold)

    def _raw_search(
        self,
        query: str,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> str:
        """Fallback: direct Qdrant search returning formatted chunks (no LLM)."""
        from infrastructure.db.qdrant_client import search_chunks

        try:
            query_vec = self.embedder.embed_query(query)
        except Exception as exc:
            logger.error("Embedding query failed: {}", exc)
            return f"RAG embedding error: {exc}"

        try:
            results = search_chunks(
                query_vector=query_vec,
                top_k=top_k,
                score_threshold=threshold,
            )
        except Exception as exc:
            logger.error("Qdrant search failed: {}", exc)
            return f"RAG search error: {exc}"

        if not results:
            return ""

        seen_parents: set = set()
        lines: List[str] = [f"Internal KB results ({len(results)} chunks):"]

        for idx, hit in enumerate(results, 1):
            parent_id = hit.get("parent_id")
            if parent_id and parent_id in seen_parents:
                continue
            if parent_id:
                seen_parents.add(parent_id)

            sim = f"{hit['score']:.2f}"
            title = hit.get("title") or "Untitled"
            url = hit.get("url") or "N/A"
            text = hit.get("parent_text", hit["chunk_text"])
            lines.append(f"\n--- Chunk {idx} (similarity {sim}) ---")
            lines.append(f"Source: {title} ({url})")
            lines.append(text)

        return "\n".join(lines)

    def warm_cache(self, queries: List[str]) -> int:
        """Pre-populate CAG cache with common queries via CRAG pipeline."""
        if self._cag_service is None:
            return 0
        return self._cag_service.warm_cache(queries)

    def cache_stats(self) -> Dict[str, Any]:
        return self._cache.stats()

    def clear_cache(self) -> None:
        self._cache.clear()
        logger.info("CAG cache cleared")

    def dispatch(self, action: str, params: Dict[str, Any]) -> str:
        """
        Dispatch a RAG action.

        Resilient to router slip-ups: filters kwargs the action doesn't
        accept (so an extra ``time_frame`` or similar doesn't crash) and
        gives a useful error string if the query is missing instead of
        500-erroring.
        """
        import inspect

        handlers = {
            "search": self.search,
            "cache_stats": lambda: f"CAG cache: {self.cache_stats()}",
            "clear_cache": lambda: (self.clear_cache(), "CAG cache cleared.")[1],
        }
        handler = handlers.get(action)
        if handler is None:
            return f"Unknown RAG action: {action}. Available: {list(handlers)}"

        if action == "search":
            sig = inspect.signature(self.search)
            accepted = {p.name for p in sig.parameters.values()}
            clean = {k: v for k, v in (params or {}).items() if k in accepted and v is not None}
            if not clean.get("query"):
                # The router didn't extract a query — return a clear message
                # the synth can turn into "what would you like me to search?"
                return (
                    "RAG search requires a query string but none was provided. "
                    "Please rephrase the question with a specific topic."
                )
            return self.search(**clean)

        return handler()

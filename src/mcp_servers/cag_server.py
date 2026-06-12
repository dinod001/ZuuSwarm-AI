"""
CAG Cache MCP Server — exposes the Qdrant-backed semantic cache over MCP.

Wraps ``src/services/chat_service/cag_cache.py``. Lets any MCP host
check or populate the same cache the agent uses, so pre-computed
answers (FAQs, policies, etc.) become sharable across apps.

Transport: stdio

Run standalone:
    python -m mcp_servers.cag_server

Inspect:
    npx @modelcontextprotocol/inspector python -m mcp_servers.cag_server
"""

import os
import sys
from typing import Any, Dict, List, Optional

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
# Subprocess CWD is src/, but .env lives at project root
_PROJECT_ROOT = os.path.dirname(_SRC)
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from loguru import logger
from mcp.server.fastmcp import FastMCP

from infrastructure.llm.embeddings import get_default_embeddings
from services.chat_service.cag_cache import CAGCache


mcp = FastMCP("machina-cag")

_cache: CAGCache | None = None


def _get_cache() -> CAGCache:
    global _cache
    if _cache is None:
        logger.info("Initialising CAGCache inside MCP server...")
        _cache = CAGCache(embedder=get_default_embeddings())
    return _cache


@mcp.tool()
def cag_get(query: str) -> Dict[str, Any]:
    """
    Semantic lookup in the CAG cache.

    Embeds the query and runs a KNN-1 search against the Qdrant
    ``cag_cache`` collection. Returns the cached answer if
    cosine similarity ≥ configured threshold (default 0.90).

    Returns a dict with:
      - hit: bool
      - query: the cached query that matched (empty on miss)
      - answer: the cached answer (empty on miss)
      - source_file: list of source URLs for the cached answer
      - score: cosine similarity of the match (0.0 on miss)
      - ts: unix timestamp the entry was written
    """
    hit = _get_cache().get(query)
    if hit is None:
        return {
            "hit": False,
            "query": "",
            "answer": "",
            "source_file": [],
            "score": 0.0,
            "ts": 0.0,
        }
    return {
        "hit": True,
        "query": hit.get("query", ""),
        "answer": hit.get("answer", ""),
        "source_file": hit.get("source_file", []),
        "score": float(hit.get("score", 0.0)),
        "ts": float(hit.get("ts", 0.0)),
    }


@mcp.tool()
def cag_set(
    query: str,
    answer: str,
    source_file: str,
) -> str:
    """
    Write an entry to the CAG cache, indexed by the query's embedding.

    Future semantically-similar queries (≥0.90 cosine) will HIT the
    cached answer. Existing near-identical entries (≥0.99 cosine) are
    replaced to prevent duplicate bloat.

    Use this to warm the cache with known T1
    any response you want to serve sub-second without re-running RAG.
    """
    _get_cache().set(query, {"answer": answer, "source_file": source_file})
    return f"cached: '{query[:80]}'"


@mcp.tool()
def cag_stats() -> Dict[str, Any]:
    """
    Return CAG cache statistics — entry count, collection name,
    similarity threshold, TTL, backend, and availability flag.
    """
    return _get_cache().stats()


@mcp.tool()
def cag_clear() -> str:
    """
    Drop and recreate the CAG cache collection.

    DESTRUCTIVE — removes every cached entry. The collection is
    recreated empty so subsequent SETs work without reinit.
    """
    _get_cache().clear()
    return "CAG cache cleared"


if __name__ == "__main__":
    logger.info("Starting machina-cag MCP server on stdio...")
    mcp.run()

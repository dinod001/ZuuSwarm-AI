"""
RAG MCP Server — exposes the RAGTool over the Model Context Protocol.

Transport: stdio

Run standalone:
    python -m mcp_servers.rag_server

Inspect interactively:
    npx @modelcontextprotocol/inspector python -m mcp_servers.rag_server
"""

import os
import sys

# Ensure src/ is importable when run as a script
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
# Subprocess CWD is src/, but .env lives at project root
_PROJECT_ROOT = os.path.dirname(_SRC)
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from loguru import logger
from mcp.server.fastmcp import FastMCP

from agents.tools.rag_tool import RAGTool
from infrastructure.llm.embeddings import get_default_embeddings
from infrastructure.llm.llm_provider import get_chat_llm

mcp = FastMCP("machina-rag")

_rag: RAGTool | None = None

def _get_rag() -> RAGTool:
    global _rag
    if _rag is None:
        logger.info("Initialising RAGTool inside MCP server...")
        _rag = RAGTool(
            embedder=get_default_embeddings(),
            llm=get_chat_llm()
        )
    return _rag

@mcp.tool()
def rag_search(
    query: str,
    top_k: int = 5,
    threshold: float = 0.70,
    use_cache: bool = True,
) -> str:
    """
    Retrieve + generate an answer from the internal KB.
    """
    return _get_rag().dispatch(
        "search",
        {
            "query": query,
            "top_k": top_k,
            "threshold": threshold,
            "use_cache": use_cache,
        }
    )

@mcp.tool()
def rag_cache_stats() -> str:
    """Return CAG cache statistics for the RAG pipeline."""
    return _get_rag().dispatch("cache_stats", {})

@mcp.tool()
def rag_clear_cache() -> str:
    """Clear the CAG cache for the RAG pipeline."""
    return _get_rag().dispatch("clear_cache", {})


if __name__ == "__main__":
    logger.info("Starting machina-rag MCP server on stdio...")
    mcp.run()

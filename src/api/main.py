import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Ensure src/ is on the path regardless of launch cwd
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
load_dotenv()

from api.middleware import install_middleware
from api.routers import chat_sessions as chat_sessions_router
from api.routers import chat as chat_router
from api.routers import health as health_router
from api.routers import auth as auth_router

# Tool routers (Currently disabled/missing in ZuuSwarm)
# from api.routers.tools import cag as cag_router
# from api.routers.tools import crm as crm_router
# from api.routers.tools import rag as rag_router
# from api.routers.tools import memory as memory_router


async def warmup_system(agent):
    """
    Warm up the LLMs and essential tools before the first user request.
    
    Why we are doing this:
    -----------------------
    When the server starts, the LLMs and external tools (like Groq, Langfuse,
    Qdrant, and MCP servers) have not yet established HTTP connection pools or 
    loaded initial states into memory (the "cold-start" problem). If we don't 
    warm them up, the very first user who sends a request will experience a 
    massive latency spike (often 5-10 seconds) while these connections are 
    initialized. 
    
    By executing these harmless, lightweight requests during the FastAPI 
    lifespan (startup phase), we force the system to establish all necessary 
    network connections and load models into memory in the background. 
    Consequently, the first actual user request will hit a "hot" system and 
    respond with sub-second latency.
    """
    logger.info("🔥 Warming up LLMs and tools to reduce cold-start latency...")
    try:
        # 1. Warm up all LLMs simultaneously to establish API connection pools
        warmup_msg = [{"role": "user", "content": "Hi"}]
        await asyncio.gather(
            agent.llm_chat.ainvoke(warmup_msg),
            agent.llm_fast.ainvoke(warmup_msg),
            agent.llm_router.ainvoke(warmup_msg),
        )
        logger.info("✅ LLMs warmed up successfully. Connection pools established.")
        
        # 2. Warm up CRM tool (machina-crm) by checking a generic service status
        if agent.crm_tool:
            await agent.crm_tool.adispatch("check_service_status", {"service_name": "API"})
            logger.info("✅ CRM tool warmed up successfully.")
            
        # 3. Warm up RAG tool (machina-rag) to initialize Qdrant connections
        if agent.rag_tool:
            await agent.rag_tool.adispatch("search", {"query": "warmup test", "use_cache": False})
            logger.info("✅ RAG tool warmed up successfully.")
            
        logger.info("🚀 System warmup complete! Ready for sub-second responses.")
    except Exception as e:
        logger.warning(f"⚠️ Warmup encountered an error (safe to ignore): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting ZuuSwarm AI API...")

    from agents.orchestrator import build_agent
    from agents.prompts.agent_prompts import LANGFUSE_PROMPT_NAMES as AGENT_PROMPTS
    from memory.prompts import LANGFUSE_PROMPT_NAMES as MEMORY_PROMPTS
    from infrastructure.llm.embeddings import get_default_embeddings, get_local_embedder
    from infrastructure.observability import prefetch_prompts
    from services.chat_service.cag_cache import CAGCache

    ALL_PROMPT_NAMES = list(AGENT_PROMPTS.values()) + list(MEMORY_PROMPTS.values())

    # Pre-fetch prompts from LangFuse
    try:
        await asyncio.to_thread(prefetch_prompts, ALL_PROMPT_NAMES)
    except Exception as e:
        logger.warning(f"Prompt prefetch skipped: {e}")

    # Heavy, mostly I/O-bound — off the event loop
    agent = await asyncio.to_thread(
        build_agent, enable_crm=True, enable_rag=True
    )
    embedder = agent.rag_tool.embedder if agent.rag_tool else get_default_embeddings()
    local_embedder = await asyncio.to_thread(get_local_embedder)

    try:
        from infrastructure.db.qdrant_client import get_qdrant_client, collection_exists
        _qc = get_qdrant_client()
        if collection_exists("cag_cache_local"):
            await asyncio.to_thread(_qc.delete_collection, "cag_cache_local")
            logger.info("CAG cache_local: dropped stale collection for clean warmup")
    except Exception as _exc:
        logger.warning("CAG cache_local purge skipped: {}", _exc)

    cag_cache = await asyncio.to_thread(
        CAGCache,
        local_embedder,
        "cag_cache_local",
        local_embedder.dim,
    )

    if agent.rag_tool is not None:
        agent.rag_tool._cache = cag_cache
        cag_service = getattr(agent.rag_tool, "_cag_service", None)
        if cag_service is not None:
            cag_service.cache = cag_cache
    
    agent.cag_cache = cag_cache

    app.state.agent = agent
    app.state.embedder = embedder              # remote, for LT memory + RAG index
    app.state.local_embedder = local_embedder  # local, for CAG short-circuit
    app.state.cag_cache = cag_cache
    app.state.session_cache = {}  # In-memory warm cache for ST turns per session

    # Execute our warmup sequence here during startup
    await warmup_system(agent)

    yield

    logger.info("Shutting down ZuuSwarm AI API...")


# Initialize FastAPI app
app = FastAPI(
    title="ZuuSwarm AI API",
    description="IT Operations Multi-Agent API",
    version="1.0.0",
    lifespan=lifespan
)

# Apply middlewares (CORS, Request ID, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_middleware(app)

# Include core routers
app.include_router(health_router.router, prefix="/api/v1/health", tags=["System"])
app.include_router(chat_router.router, prefix="/api/v1", tags=["Chat"])
app.include_router(chat_sessions_router.router, prefix="/api/v1/sessions", tags=["Sessions"])
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["Auth"])

# Include Tool routers (Disabled)
# app.include_router(cag_router.router, prefix="/api/v1/tools/cag", tags=["Tools - CAG"])
# app.include_router(crm_router.router, prefix="/api/v1/tools/crm", tags=["Tools - CRM"])
# app.include_router(rag_router.router, prefix="/api/v1/tools/rag", tags=["Tools - RAG"])
# app.include_router(memory_router.router, prefix="/api/v1/tools/memory", tags=["Tools - Memory"])
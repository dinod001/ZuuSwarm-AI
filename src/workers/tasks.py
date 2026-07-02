"""
Arq background tasks — the *non-blocking* post-turn bookkeeping for chat.

Each task is fire-and-forget from the API's perspective. The API enqueues
a job and returns immediately; this worker process pulls jobs off Redis,
executes them, and Arq handles retries + dead-letter on persistent failure.

Tasks defined here:

- `save_chat_turn`     — write user + assistant turn into short-term store
- `auto_title_session` — if title still default + enough turns, LLM-rename
- `distill_facts`      — every Nth turn, extract LT memory facts via LLM

Run with:

    arq src.workers.tasks.WorkerSettings
"""

from __future__ import annotations

import os
import time
from typing import Any

from arq.connections import RedisSettings
from loguru import logger

from memory.schemas import ConversationTurn


# ── Redis connection settings ─────────────────────────────────────────

def _redis_settings() -> RedisSettings:
    """
    Build the Arq Redis connection settings from REDIS_URL.
    """
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "redis",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or "0"),
        password=parsed.password,
    )


# ── Orchestrator lifecycle (shared across tasks in this worker) ───────

async def _startup(ctx: dict) -> None:
    """
    Build the orchestrator once when the worker boots, reuse across jobs.
    """
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True))

    from infrastructure.log import setup_logging
    setup_logging()

    logger.info("Arq worker boot — building agent orchestrator...")
    from agents.orchestrator import build_agent
    ctx["orchestrator"] = build_agent()
    logger.success("Arq worker ready — orchestrator + tools wired")


async def _shutdown(ctx: dict) -> None:
    """Drain any final tasks + close connections."""
    logger.info("Arq worker shutting down")


# ── Tasks ─────────────────────────────────────────────────────────────

async def save_chat_turn(
    ctx: dict,
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> dict:
    """
    Persist one chat turn (user + assistant) into the short-term store.
    """
    orchestrator = ctx["orchestrator"]
    now = time.time()
    
    if hasattr(orchestrator, "st_store") and orchestrator.st_store:
        orchestrator.st_store.add(
            user_id, session_id,
            ConversationTurn(
                user_id=user_id, session_id=session_id,
                role="user", content=user_message, ts=now,
            ),
        )
        orchestrator.st_store.add(
            user_id, session_id,
            ConversationTurn(
                user_id=user_id, session_id=session_id,
                role="assistant", content=assistant_message, ts=now,
            ),
        )
        logger.debug(f"save_chat_turn: {session_id} (user_id={user_id})")
        
    return {"status": "ok", "session_id": session_id}


async def auto_title_session(
    ctx: dict,
    *,
    user_id: str,
    session_id: str,
) -> dict:
    """
    Maybe LLM-rename a session if it still has the default title.
    """
    orchestrator = ctx["orchestrator"]
    llm = getattr(orchestrator, "llm_fast", None) or getattr(orchestrator, "llm_chat", None)

    try:
        from api.routers.chat_sessions import maybe_auto_title_sync
        if hasattr(orchestrator, "st_store") and orchestrator.st_store and llm:
            maybe_auto_title_sync(
                session_id=session_id,
                user_id=user_id,
                st_store=orchestrator.st_store,
                llm=llm,
            )
    except Exception as e:
        logger.warning(f"auto_title_session skipped/failed: {e}")
        
    return {"status": "ok"}


async def distill_facts(
    ctx: dict,
    *,
    user_id: str,
    session_id: str,
) -> dict:
    """
    Run long-term distillation on recent turns if the heuristic says so.
    """
    orchestrator = ctx["orchestrator"]
    try:
        if hasattr(orchestrator, "st_store") and hasattr(orchestrator, "distiller"):
            recent = orchestrator.st_store.recent(user_id, session_id, k=5)
            if orchestrator.distiller.should_distill(recent):
                logger.info(f"distill_facts: triggering LT distillation for {user_id}")
                orchestrator.distiller.distill(user_id, recent)
    except Exception as e:
        logger.warning(f"distill_facts failed (non-fatal): {e}")
    return {"status": "ok"}


# ── Arq worker config ─────────────────────────────────────────────────

class WorkerSettings:
    """
    Arq picks this up via `arq src.workers.tasks.WorkerSettings`.
    """
    functions = [save_chat_turn, auto_title_session, distill_facts]
    redis_settings = _redis_settings()
    on_startup = _startup
    on_shutdown = _shutdown

    max_jobs = 10
    job_timeout = 60
    keep_result = 60 * 5
    health_check_interval = 30

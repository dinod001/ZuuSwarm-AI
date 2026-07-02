"""
ZuuSwarm AI — Conversational Chat Endpoint (Low-Latency Hot Path).

Architecture:
─────────────
    POST /chat
        │
        │  ── Phase 1 — Parallel fan-out via asyncio.gather ───────
        │       guardrail + router   (~250 ms — Groq Llama 8B)
        │       memory recall        (~200 ms — ST + LT semantic)
        │
        │  → Out of scope?  → return refusal instantly
        │  → CAG route?     → run CAG fastpath (clearance + RAG)
        │  → T4 critical?   → escalate to voice immediately
        │
        │  ── Phase 2 — LangGraph orchestrator invocation ─────────
        │       The full L1→L2→L3→L4 graph runs as a single
        │       `agent.app.ainvoke(...)` call. Each node uses direct
        │       `adispatch` to CRM/RAG tools (NO llm.bind_tools).
        │
        │  ── Phase 3 — Background tasks (after response) ─────────
        │       memory distillation, CAG cache warming
        │
        └──► ChatResponse(answer, route, latency_ms, timings, ticket_id)

Latency Optimizations:
    1. Guardrail + Router run in parallel (asyncio.gather)
    2. Memory recall runs concurrently with classification
    3. Session cache avoids repeated Supabase round-trips
    4. Orchestrator nodes use direct adispatch (no bind_tools)
    5. Background tasks (distill, CAG write) happen AFTER response
"""

import asyncio
import json
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from api.deps import get_agent, get_cag_cache, get_st_store
from api.event_labels import stage_label, tool_label
from api.routers.chat_sessions import touch_session_sync
from api.schemas import (
    ChatRequest,
    ChatResetRequest,
    ChatResetResponse,
    ChatResponse,
    SessionTurnsResponse,
    SessionWarmupRequest,
    SessionWarmupResponse,
    TurnItem,
)
from workers.enqueue import enqueue_chat_bookkeeping

# Type alias for the SSE event emitter callback.
EmitFn = Callable[[Dict[str, Any]], Awaitable[None]]


async def _noop_emit(_event: Dict[str, Any]) -> None:
    """Default emitter for the non-streaming path (events are discarded)."""
    return None


router = APIRouter(tags=["Chat"])


# ── Helpers ──────────────────────────────────────────────────────────

def _ms(start: float) -> int:
    """Convert a perf_counter delta to integer milliseconds."""
    return int((time.perf_counter() - start) * 1000)


def _store_turn_pair(st_store, user_id: str, session_id: str, user_msg: str, answer: str) -> None:
    """Persist a user+assistant turn pair into short-term memory (sync, for background tasks)."""
    from memory.schemas import ConversationTurn
    now = time.time()
    st_store.add(user_id, session_id, ConversationTurn(
        user_id=user_id, session_id=session_id, role="user", content=user_msg, ts=now,
    ))
    st_store.add(user_id, session_id, ConversationTurn(
        user_id=user_id, session_id=session_id, role="assistant", content=answer, ts=now,
    ))


# ── Session Cache ────────────────────────────────────────────────────
# In-memory dict that mirrors recent ST turns so we avoid a Supabase
# round-trip on every single chat message. Populated by /sessions/warmup
# and kept warm by _append_to_cached_turns after each response.

_CACHE_MAX_TURNS = 6


def _cache_key(user_id: str, session_id: str):
    return (user_id, session_id)


def _append_to_cached_turns(app_state, user_id: str, session_id: str,
                             user_msg: str, answer: str) -> None:
    """Write-through: mirror every turn into the warm session cache so
    the next request doesn't need a Supabase fetch."""
    from memory.schemas import ConversationTurn

    cache = getattr(app_state, "session_cache", None)
    if cache is None:
        return
    entry = cache.get(_cache_key(user_id, session_id))
    if entry is None:
        return
    now = time.time()
    turns = list(entry.get("st_turns") or [])
    turns.append(ConversationTurn(
        user_id=user_id, session_id=session_id, role="user", content=user_msg, ts=now,
    ))
    turns.append(ConversationTurn(
        user_id=user_id, session_id=session_id, role="assistant", content=answer, ts=now,
    ))
    entry["st_turns"] = turns[-_CACHE_MAX_TURNS:]


# ── CAG Cache Helpers ────────────────────────────────────────────────
# CRM actions whose answers are employee-agnostic (reference data, not
# personal). Safe to share via the semantic cache across users.
_CACHEABLE_CRM_ACTIONS = {"get_all_service_names", "get_all_asset_names"}


def _safe_cag_set(cag, query: str, answer: str) -> None:
    """Background CAG write — never fails the request on Qdrant errors."""
    try:
        cag.set(query, {"answer": answer, "evidence_urls": []})
    except Exception as exc:
        logger.warning("Background CAG set failed: {}", exc)


# ── Distillation (LT Memory) ────────────────────────────────────────
# Distill is an LLM call + Qdrant upsert — expensive. We only run it
# every Nth turn unless the user explicitly asks us to "remember".

_DISTILL_EVERY_N_TURNS = 4
_DISTILL_KEYWORDS = ("remember", "from now on", "remind me", "always", "never")
_distill_counters: Dict[tuple, int] = {}


def _maybe_distill(distiller, st_store, user_id: str, session_id: str) -> None:
    """Background task: conditionally distill recent turns into LT facts."""
    try:
        recent = st_store.recent(user_id, session_id, k=2)
        if not recent:
            return

        # Immediate distill if user explicitly says "remember" etc.
        explicit = any(
            any(kw in (t.content or "").lower() for kw in _DISTILL_KEYWORDS)
            for t in recent
        )

        if not explicit:
            key = (user_id, session_id)
            count = _distill_counters.get(key, 0) + 1
            _distill_counters[key] = count
            if count % _DISTILL_EVERY_N_TURNS != 0:
                return

        if distiller.should_distill(recent):
            distiller.distill(user_id, recent)
    except Exception as exc:
        logger.warning("Background distill failed: {}", exc)


# ── Main Chat Pipeline ──────────────────────────────────────────────
#
# Both POST /chat (sync) and POST /chat/stream (SSE) call this function.
# The only difference is the `emit` callback they pass.

async def _run_chat_pipeline(
    req: ChatRequest,
    *,
    request: Request,
    background: BackgroundTasks,
    emit: EmitFn,
) -> ChatResponse:
    """
    The core chat pipeline. Runs classification, tool dispatch via the
    LangGraph orchestrator, and returns the synthesised answer.
    """
    t_total = time.perf_counter()
    timings: Dict[str, int] = {}

    agent = get_agent(request)
    cag = get_cag_cache(request)
    st_store = get_st_store(request)

    # ── Phase 1a — Memory recall (parallel with classification) ──
    # Try the warm session cache first; fall back to a live Supabase fetch.
    cache_entry = getattr(request.app.state, "session_cache", {}).get(
        _cache_key(req.user_id, req.session_id)
    )

    async def _recall_task():
        t0 = time.perf_counter()
        await emit({"type": "stage_start", "stage": "recall_st",
                    "label": stage_label("recall_st")})
        try:
            if cache_entry is not None:
                # Hot path: use cached turns (0 ms network)
                cached_turns = cache_entry.get("st_turns") or []
                ctx = agent.recaller.format_context(cached_turns)
            else:
                # Cold path: fetch from Supabase
                st_turns = await asyncio.to_thread(
                    agent.st_store.recent, req.user_id, req.session_id, 6,
                )
                ctx = agent.recaller.format_context(st_turns)
        except Exception as exc:
            logger.warning("ST recall failed: {}", exc)
            ctx = ""
        ms = _ms(t0)
        timings["recall_st"] = ms
        await emit({"type": "stage_done", "stage": "recall_st", "ms": ms})
        return ctx

    async def _recall_lt_task(query: str) -> str:
        """LT semantic recall — runs after classification if needed."""
        t0 = time.perf_counter()
        await emit({"type": "stage_start", "stage": "recall_lt",
                    "label": stage_label("recall_lt")})
        try:
            lt_facts = await asyncio.to_thread(
                agent.lt_store.query,
                user_id=req.user_id,
                query_text=query,
                k=5,
                threshold=0.5,
            )
            if not lt_facts:
                ms = _ms(t0)
                timings["recall_lt"] = ms
                await emit({"type": "stage_done", "stage": "recall_lt", "ms": ms})
                return ""
            ctx = "\n=== LONG-TERM FACTS ===\n"
            for f in lt_facts:
                ctx += f"- {getattr(f, 'text', '')}\n"
        except Exception as exc:
            logger.warning("LT recall failed: {}", exc)
            ctx = ""
            lt_facts = []
        ms = _ms(t0)
        timings["recall_lt"] = ms
        await emit({"type": "stage_done", "stage": "recall_lt", "ms": ms})
        return ctx

    # ── Phase 1b — Classification (guardrail + router, parallel) ──
    # Both run on the fast Groq 8B model. The guardrail decides scope,
    # the router classifies the ticket type and picks the route.
    async def _classify_task():
        t0 = time.perf_counter()
        await emit({"type": "stage_start", "stage": "route",
                    "label": stage_label("route")})
        try:
            # Build a minimal router context from the warm cache
            router_ctx = ""
            if cache_entry is not None:
                recent = (cache_entry.get("st_turns") or [])[-4:]
                router_ctx = agent.recaller.format_context(recent)

            # Run guardrail + router in parallel
            decision_state = await agent.decision_graph.ainvoke({
                "message": req.message,
                "router_context": router_ctx,
            })
        except Exception as exc:
            logger.warning("Decision graph failed: {}", exc)
            decision_state = {"guardrail": "in_scope", "decision": {
                "ticket_type": "T2", "severity": "medium",
                "route": "l2_investigator", "reasoning": f"Fallback: {exc}"
            }}
        ms = _ms(t0)
        timings["route"] = ms
        await emit({"type": "stage_done", "stage": "route", "ms": ms})
        return decision_state

    # Fan-out: memory recall + classification run concurrently
    st_context, decision_state = await asyncio.gather(
        _recall_task(), _classify_task()
    )

    guardrail_verdict = decision_state.get("guardrail", "in_scope")
    decision = decision_state.get("decision", {})
    route = decision.get("route", "l2_investigator")

    # ── Phase 1c — Guardrail short-circuit ───────────────────────
    if guardrail_verdict == "out_of_scope":
        from agents.guardrail import OUT_OF_SCOPE_REPLY
        refusal = getattr(
            __import__("agents.guardrail", fromlist=["OUT_OF_SCOPE_REPLY"]),
            "OUT_OF_SCOPE_REPLY",
            "I'm sorry, but that question is outside my IT operations domain. "
            "I can help with system incidents, access issues, asset provisioning, "
            "and service health monitoring."
        )
        await emit({"type": "tool_invoke", "route": "out_of_scope",
                    "label": tool_label("out_of_scope")})

        enqueued = await enqueue_chat_bookkeeping(
            user_id=req.user_id,
            session_id=req.session_id,
            user_message=req.message,
            assistant_message=refusal,
        )
        if not enqueued:
            background.add_task(
                _store_turn_pair, st_store, req.user_id, req.session_id,
                req.message, refusal,
            )
        background.add_task(
            touch_session_sync, req.user_id, req.session_id
        )
        return ChatResponse(
            answer=refusal,
            route="out_of_scope",
            cached=False,
            latency_ms=_ms(t_total),
            timings=timings,
            model_used="guardrail",
        )

    # ── Phase 1d — Direct Chat short-circuit ─────────────────────
    if route == "direct_chat":
        await emit({"type": "stage_start", "stage": "direct_chat",
                    "label": "Conversational Reply"})
        try:
            sys_content = "You are ZuuSwarm AI, a friendly IT operations assistant. Keep your response brief and polite."
            if st_context:
                sys_content += f"\n\nRecent conversation history:\n{st_context}"
                
            msgs = [
                SystemMessage(content=sys_content),
                HumanMessage(content=req.message)
            ]
            answer = ""
            async for chunk in agent.llm_fast.astream(msgs):
                if chunk.content:
                    answer += chunk.content
                    await emit({"type": "token", "content": chunk.content})
        except Exception as e:
            logger.error(f"direct_chat failed: {e}")
            answer = "Hello! How can I help you with your IT operations today?"
        
        await emit({"type": "stage_done", "stage": "direct_chat", "ms": 50})
        
        enqueued = await enqueue_chat_bookkeeping(
            user_id=req.user_id,
            session_id=req.session_id,
            user_message=req.message,
            assistant_message=answer,
        )
        if not enqueued:
            background.add_task(
                _store_turn_pair, st_store, req.user_id, req.session_id,
                req.message, answer,
            )
        background.add_task(
            touch_session_sync, req.user_id, req.session_id
        )
        return ChatResponse(
            answer=answer,
            route="direct_chat",
            cached=False,
            latency_ms=_ms(t_total),
            timings=timings,
            model_used=getattr(agent.llm_fast, "model_name", "unknown"),
        )

    # ── Phase 2 — Pure Python Orchestration (Direct Dispatch) ────────────
    # Bypassing LangGraph entirely to eliminate framework overhead while
    # preserving the multi-agent logic flow.
    t_graph = time.perf_counter()
    await emit({"type": "stage_start", "stage": "tool", "label": stage_label("tool")})

    try:
        from langchain_core.messages import HumanMessage as HM
        state = {
            "messages": [HM(content=req.message)],
            "user_id": req.user_id,
            "session_id": req.session_id,
            "user_email": req.user_email or req.user_id,
            "memory_context": st_context,
            "route_decision": decision,
            "retry_count": 0,
            "emit": emit,  # Pass emit callback to state so l4_supervisor_node can stream!
        }

        lt_task = asyncio.create_task(_recall_lt_task(req.message))

        # 1. Triage & Ticket Creation
        t_node = time.perf_counter()
        await emit({"type": "stage_start", "stage": "l1_triage_node", "label": stage_label("l1_triage_node")})
        out1 = await agent.l1_triage_node(state)
        state.update(out1)
        await emit({"type": "stage_done", "stage": "l1_triage_node", "ms": _ms(t_node)})

        # Route might have been updated by triage, fallback to phase 1 classification
        route = state.get("route_decision", {}).get("route", "l2_investigator")

        # 2. Branch Execution
        if route == "cag":
            t_node = time.perf_counter()
            await emit({"type": "stage_start", "stage": "cag_fastpath_node", "label": stage_label("cag_fastpath_node")})
            out = await agent.cag_fastpath_node(state)
            state.update(out)
            await emit({"type": "stage_done", "stage": "cag_fastpath_node", "ms": _ms(t_node)})

        elif route in ("l4_voice", "voice"):
            await emit({"type": "stage_start", "stage": "l4_voice", "label": "Critical Outage: Escalating to Voice Protocol"})
            await emit({"type": "action", "action": "open_voice", "autoStart": True})
            state["final_answer"] = "I have detected a critical IT issue. Escalating to the Voice response team automatically. Please hold..."

        else: # l2_investigator
            t_node = time.perf_counter()
            await emit({"type": "stage_start", "stage": "l2_investigator_node", "label": stage_label("l2_investigator_node")})
            out2 = await agent.l2_investigator_node(state)
            state.update(out2)
            await emit({"type": "stage_done", "stage": "l2_investigator_node", "ms": _ms(t_node)})
            
            t_node = time.perf_counter()
            await emit({"type": "stage_start", "stage": "l3_resolver_node", "label": stage_label("l3_resolver_node")})
            out3 = await agent.l3_resolver_node(state)
            state.update(out3)
            await emit({"type": "stage_done", "stage": "l3_resolver_node", "ms": _ms(t_node)})

            # Intelligent Retry Loop
            while "fail" in str(state.get("action_taken", "")).lower() and state.get("retry_count", 0) <= 3:
                t_node = time.perf_counter()
                await emit({"type": "stage_start", "stage": "l2_investigator_node", "label": f"Retrying Investigation (#{state['retry_count']})"})
                out2 = await agent.l2_investigator_node(state)
                state.update(out2)
                await emit({"type": "stage_done", "stage": "l2_investigator_node", "ms": _ms(t_node)})
                
                t_node = time.perf_counter()
                await emit({"type": "stage_start", "stage": "l3_resolver_node", "label": f"Retrying Resolution (#{state['retry_count']})"})
                out3 = await agent.l3_resolver_node(state)
                state.update(out3)
                await emit({"type": "stage_done", "stage": "l3_resolver_node", "ms": _ms(t_node)})

        lt_context = await lt_task

        # 3. L4 Supervisor (Finalization & Synthesis)
        t_node = time.perf_counter()
        await emit({"type": "stage_start", "stage": "l4_supervisor_node", "label": stage_label("l4_supervisor_node")})
        
        # This will stream tokens directly via the emit callback passed in state
        out4 = await agent.l4_supervisor_node(state)
        state.update(out4)
        
        await emit({"type": "stage_done", "stage": "l4_supervisor_node", "ms": _ms(t_node)})

        answer = state.get("final_answer", "")
        ticket_id = state.get("ticket_id")

        if not answer:
            answer = (
                state.get("action_taken")
                or state.get("investigation_results")
                or "I was unable to process your request. Please try again."
            )

    except Exception as exc:
        logger.exception("Python Orchestrator failed: {}", exc)
        answer = f"I encountered an error processing your request: {exc}"
        ticket_id = None

    timings["tool"] = _ms(t_graph)
    await emit({"type": "stage_done", "stage": "tool", "ms": timings["tool"]})

    # ── Phase 3 — Background tasks (fire-and-forget after response) ─
    # These run AFTER the response is sent to the user, so they don't
    # add to perceived latency.
    if answer:
        _append_to_cached_turns(
            request.app.state, req.user_id, req.session_id,
            req.message, answer,
        )
        enqueued = await enqueue_chat_bookkeeping(
            user_id=req.user_id,
            session_id=req.session_id,
            user_message=req.message,
            assistant_message=answer,
        )
        
        background.add_task(
            touch_session_sync, req.user_id, req.session_id
        )
        
        if not enqueued:
            # ST persistence happens in the graph's memory_save_node already,
            # but we also do it here defensively in case the graph skipped it.
            background.add_task(
                _store_turn_pair, st_store, req.user_id, req.session_id,
                req.message, answer,
            )
            background.add_task(
                _maybe_distill, agent.distiller, st_store,
                req.user_id, req.session_id,
            )
            
        # Warm the CAG cache for RAG-route answers (employee-agnostic)
        if route == "cag" and cag:
            background.add_task(_safe_cag_set, cag, req.message, answer)

    model_used = getattr(agent.llm_chat, "model_name", None) or getattr(agent.llm_chat, "model", "unknown")

    return ChatResponse(
        answer=answer,
        route=route,
        cached=False,
        latency_ms=_ms(t_total),
        timings=timings,
        ticket_id=ticket_id,
        model_used=model_used,
    )


# ── POST /chat — Non-streaming endpoint ─────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    background: BackgroundTasks,
) -> ChatResponse:
    """Run the full pipeline and return the complete response in one shot."""
    return await _run_chat_pipeline(
        req, request=request, background=background, emit=_noop_emit,
    )


# ── POST /chat/stream — SSE streaming endpoint ──────────────────────

@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    background: BackgroundTasks,
) -> StreamingResponse:
    """
    Stream the chain-of-thought as the pipeline runs via Server-Sent Events.

    Each SSE event is a JSON object with a ``type`` field. The final event
    has ``type: "final"`` and contains the same fields as the non-streaming
    ``/chat`` response. Clients that only want the answer can ignore
    everything except the final event.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: Dict[str, Any]) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            final = await _run_chat_pipeline(
                req, request=request, background=background, emit=emit,
            )
            await queue.put({
                "type": "final",
                "answer": final.answer,
                "route": final.route,
                "cached": final.cached,
                "latency_ms": final.latency_ms,
                "timings": final.timings,
                "ticket_id": final.ticket_id,
                "model_used": final.model_used,
            })
        except HTTPException as exc:
            await queue.put({"type": "error", "status": exc.status_code,
                             "message": str(exc.detail)})
        except Exception as exc:
            logger.exception("Streaming chat failed: {}", exc)
            await queue.put({"type": "error", "status": 500, "message": str(exc)})
        finally:
            await queue.put(None)  # sentinel — closes the stream

    asyncio.create_task(run())

    async def event_generator():
        # Force browser to flush by sending 2048 bytes of padding
        padding = " " * 2048
        yield f": stream-open {padding}\n\n"
        while True:
            event = await queue.get()
            if event is None:
                break
            # Pad every chunk with spaces to defeat browser buffering (many browsers buffer < 1KB chunks)
            chunk_padding = " " * 1024
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n:{chunk_padding}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
            "connection": "keep-alive",
        },
    )


# ── POST /chat/reset ─────────────────────────────────────────────────

@router.post("/chat/reset", response_model=ChatResetResponse)
async def chat_reset(
    req: ChatResetRequest,
    request: Request,
    st_store=Depends(get_st_store),
) -> ChatResetResponse:
    """Clear the short-term memory for a session. Useful for testing."""
    await asyncio.to_thread(st_store.clear, req.user_id, req.session_id)
    session_cache = getattr(request.app.state, "session_cache", {})
    session_cache.pop(_cache_key(req.user_id, req.session_id), None)
    return ChatResetResponse(
        cleared=True,
        user_id=req.user_id,
        session_id=req.session_id,
    )


# ── POST /sessions/warmup ────────────────────────────────────────────

@router.post("/sessions/warmup", response_model=SessionWarmupResponse)
async def session_warmup(
    req: SessionWarmupRequest,
    request: Request,
) -> SessionWarmupResponse:
    """
    Preload recent ST turns into the in-memory session cache.

    The UI calls this on login or session switch so the first chat
    message doesn't pay for the Supabase round-trip (~300-500 ms).
    Runs the fetch in parallel to mask the I/O latency.
    """
    t0 = time.perf_counter()
    agent = get_agent(request)

    async def _fetch_st():
        try:
            turns = await asyncio.to_thread(
                agent.st_store.recent, req.user_id, req.session_id, _CACHE_MAX_TURNS,
            )
            return list(turns or [])
        except Exception as exc:
            logger.warning("warmup: ST fetch failed: {}", exc)
            return []

    st_turns = await _fetch_st()

    session_cache = getattr(request.app.state, "session_cache", {})
    session_cache[_cache_key(req.user_id, req.session_id)] = {
        "st_turns": st_turns,
    }

    return SessionWarmupResponse(
        warmed=True,
        st_turn_count=len(st_turns),
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


# ── GET /sessions/{sid}/turns ────────────────────────────────────────

@router.get("/sessions/{session_id}/turns", response_model=SessionTurnsResponse)
async def session_turns(
    session_id: str,
    user_id: str,
    limit: int = 20,
    st_store=Depends(get_st_store),
) -> SessionTurnsResponse:
    """Retrieve the conversation history for a session."""
    turns = await asyncio.to_thread(st_store.recent, user_id, session_id, limit)
    items = [
        TurnItem(
            role=getattr(t, "role", "user"),
            content=getattr(t, "content", ""),
            ts=float(getattr(t, "ts", 0.0)),
        )
        for t in (turns or [])
    ]
    return SessionTurnsResponse(
        user_id=user_id,
        session_id=session_id,
        turn_count=len(items),
        turns=items,
    )
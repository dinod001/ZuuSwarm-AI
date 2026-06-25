"""
LangGraph Orchestrator for ZuuSwarm AI.
Implements the full L1 -> L4 graph with 4-tier memory integration.
Now completely Object-Oriented and integrated with MultiServerMCPClient.
"""

import time
import json
import re
from typing import Literal, Optional, List
from infrastructure.log import get_logger
logger = get_logger("orchestrator")
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
load_dotenv()

from agents.state import AgentState
from agents.prompts.agent_prompts import (
    build_l2_investigator_prompt,
    build_l3_resolver_prompt,
    build_synthesiser_prompt,
)
from memory.memory_ops import MemoryRecaller, MemoryDistiller
from memory.schemas import ConversationTurn

# LangChain MCP Client
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp_servers.mcp_config import build_mcp_server_config

# Infrastructure
from memory.st_store import ShortTermMemoryStore
from memory.lt_store import LongTermMemoryStore
from memory.episodic_store import EpisodicMemoryStore, create_episode_from_turns
from infrastructure.llm.embeddings import get_default_embeddings
from infrastructure.llm.llm_provider import get_chat_llm, get_router_llm
from agents.guardrail import Guardrail
from agents.decision_graph import build_decision_graph
from agents.router import QueryRouter
from dataclasses import dataclass, field

@dataclass
class AgentResponse:
    """
    Complete agent response with metadata for the UI/Notebooks and Voice Layer.
    """
    answer: str
    route: str = "direct"
    routes: List[str] = field(default_factory=list)
    action: Optional[str] = None
    tool_output: str = ""
    memory_context: str = ""
    latency_ms: int = 0

class AgentOrchestrator:
    """
    Main Orchestrator Class for ZuuSwarm AI.
    Runs the LangGraph nodes as async instance methods.
    """
    
    def __init__(
        self,
        llm_chat,
        llm_router,
        st_store,
        lt_store,
        recaller,
        distiller,
        llm_fast=None,
        llm_guardrail=None,
        crm_tool=None,
        rag_tool=None,
    ):
        self.llm_chat = llm_chat
        self.reasoning_llm = llm_chat # Alias for compatibility
        self.llm_fast = llm_fast
        self.llm_router = llm_router
        self.router_llm = llm_router # Alias for compatibility
        self.llm_guardrail = llm_guardrail or llm_router
        
        self.st_store = st_store
        self.lt_store = lt_store
        self.recaller = recaller
        self.distiller = distiller
        
        self.crm_tool = crm_tool
        self.rag_tool = rag_tool
        
        self.guardrail = Guardrail(llm=self.llm_guardrail)
        self.query_router = QueryRouter(llm=self.llm_router)
        self.decision_graph = self._build_decision_graph()
        self.app = self.build_graph()
    
    def _build_decision_graph(self):
        """Compile the parallel-classifier LangGraph used by the chat
        API hot path. See ``agents.decision_graph`` for the topology
        and node behaviour. The CAG cache is read via a getter
        closure so the graph survives the late-binding pattern used
        by the FastAPI lifespan.
        """
        return build_decision_graph(
            guardrail=self.guardrail,
            router=self.query_router
        )

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------

    async def memory_ingest_node(self, state: AgentState) -> dict:
        """1. Load ST and LT memory for context."""
        user_id = state.get("user_id", "default_user")
        session_id = state.get("session_id", "default_session")
        logger.info(f"📥 [Memory Ingest] Loading memory for user={user_id}, session={session_id}")
        
        user_message = state["messages"][-1].content if state["messages"] else ""
            
        try:
            st_turns, lt_facts = self.recaller.recall(
                user_id=user_id,
                session_id=session_id,
                query=str(user_message),
            )
            out = self.recaller.format_context(st_turns)
            if lt_facts:
                out += "\n=== LONG-TERM FACTS ===\n"
                for f in lt_facts:
                    out += f"- {f.text}\n"
            
            logger.info(f"📥 [Memory Ingest] Loaded {len(st_turns)} ST turns, {len(lt_facts)} LT facts")
            return {"memory_context": out, "retry_count": 0}
        except Exception as e:
            logger.error(f"❌ [Memory Ingest] Failed: {e}")
            return {"memory_context": "(Memory unavailable)", "retry_count": 0}


    async def l1_triage_node(self, state: AgentState) -> dict:
        """2. Classify and Route."""
        user_message = state["messages"][-1].content if state["messages"] else ""
        memory_context = state.get("memory_context", "")
        logger.info(f"🏷️ [L1 Triage] Classifying user message...")
        
        try:
            decision = await self.query_router.aroute(user_message=str(user_message), memory_context=memory_context)
            logger.info(f"🏷️ [L1 Triage] Decision: type={decision.get('ticket_type')}, severity={decision.get('severity')}, route={decision.get('route')}")
            
            ticket_id = "UNKNOWN"
            try:
                type_map = {
                    "T1": "access_identity",
                    "T2": "asset_provisioning",
                    "T3": "service_degradation",
                    "T4": "critical_outage"
                }
                mapped_type = type_map.get(decision.get("ticket_type"), "service_degradation")

                if self.crm_tool:
                    res = await self.crm_tool.adispatch("create_ticket", {
                        "issue_description": str(user_message),
                        "ticket_type": mapped_type,
                        "severity": decision["severity"],
                        "reported_by": state.get("user_id", "unknown"),
                    })
                    res_str = str(res)
                    if "Ticket " in res_str:
                        try:
                            ticket_id = res_str.split("Ticket ")[1].split(" ")[0]
                        except IndexError:
                            pass
                    logger.info(f"🎫 [L1 Triage] Ticket created: {ticket_id}")
            except Exception as e:
                logger.error(f"❌ [L1 Triage] Failed to create ticket: {e}")

            return {"route_decision": decision, "ticket_id": ticket_id}
        except Exception as e:
            logger.error(f"❌ [L1 Triage] Classification failed: {e}")
            fallback_decision = {
                "ticket_type": "T2",
                "severity": "medium",
                "route": "l2_investigator",
                "reasoning": f"Fallback routing due to error: {e}"
            }
            return {"route_decision": fallback_decision}


    async def cag_fastpath_node(self, state: AgentState) -> dict:
        """3. CAG for T1 Access & Identity with SQL Clearance Check."""
        user_id = state.get("user_id", "unknown")
        user_email = state.get("user_email", user_id)
        user_message = state["messages"][-1].content if state["messages"] else ""
        logger.info(f"⚡ [CAG FastPath] Checking clearance for user={user_email}")
        
        try:
            clearance_res = await self.crm_tool.adispatch("check_user_clearance", {"email": user_email}) if self.crm_tool else "0"
            
            match = re.search(r'\d+', str(clearance_res))
            clearance = int(match.group()) if match else 0
            
            logger.info(f"⚡ [CAG FastPath] User clearance level: {clearance} (raw={str(clearance_res)[:50]})")
                
            if clearance >= 3:
                logger.info(f"✅ [CAG FastPath] Clearance APPROVED (level {clearance} >= 3). Querying RAG...")
                answer_text = await self.rag_tool.adispatch("search", {"query": str(user_message), "use_cache": True}) if self.rag_tool else "RAG unavailable."
                answer = f"CAG FastPath (Clearance Level {clearance} Approved):\n{answer_text}"
            else:
                logger.warning(f"🚫 [CAG FastPath] Clearance REJECTED (level {clearance} < 3)")
                answer = f"CAG FastPath Rejected: You do not have the required SQL clearance (Level 3+) for this request. Your level is {clearance}."
        except Exception as e:
            logger.error(f"❌ [CAG FastPath] Failed: {e}")
            answer = f"CAG failed: {e}"
            
        return {"action_taken": answer}


    async def l2_investigator_node(self, state: AgentState) -> dict:
        """4. Query Observability Metrics directly without LLM tool binding to save latency."""
        retry_count = state.get("retry_count", 0) + 1
        decision = state.get("route_decision", {})
        user_message = state["messages"][-1].content if state["messages"] else ""
        
        logger.info(f"🔍 [L2 Investigator] Starting investigation (retry #{retry_count})")
        
        try:
            # Quickly extract asset or service name using router LLM and the LangFuse persona
            system_prompt = build_l2_investigator_prompt()
            
            # Fetch valid catalogs from CRM so the LLM doesn't guess blindly
            if self.crm_tool:
                valid_assets = await self.crm_tool.adispatch("get_all_asset_names", {})
                valid_services = await self.crm_tool.adispatch("get_all_service_names", {})
            else:
                valid_assets = "Unknown"
                valid_services = "Unknown"
                
            extract_prompt = (
                f"Extract the affected asset or service name from this issue. If multiple, pick the main one.\n"
                f"Output ONLY the exact name from the valid lists below, nothing else.\n\n"
                f"Valid Assets: {valid_assets}\n"
                f"Valid Services: {valid_services}\n\n"
                f"Issue: {user_message}"
            )
            
            res = await self.router_llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": extract_prompt}
            ])
            target_name = res.content.strip()
            
            logger.info(f"🔍 [L2 Investigator] Extracted target: {target_name}")
            
            # Directly call the CRM tool adapter to save LLM round-trip time
            if self.crm_tool:
                status_res = await self.crm_tool.adispatch("check_service_status", {"service_name": target_name})
                health_res = await self.crm_tool.adispatch("get_asset_health", {"asset_name": target_name})
                investigation_results = f"[check_service_status]\n{status_res}\n\n[get_asset_health]\n{health_res}"
            else:
                investigation_results = "CRM tool unavailable."
                
            logger.info(f"🔍 [L2 Investigator] Investigation complete.")
            return {"investigation_results": investigation_results.strip(), "retry_count": retry_count}
        except Exception as e:
            logger.error(f"❌ [L2 Investigator] Failed: {e}")
            return {"investigation_results": f"Investigator error: {e}", "retry_count": retry_count}


    async def l3_resolver_node(self, state: AgentState) -> dict:
        """6. Execute fix using RAG and SQL History directly without LLM tool binding."""
        retry_count = state.get("retry_count", 0) + 1
        investigation = state.get("investigation_results", "")
        ticket_id = state.get("ticket_id", "UNKNOWN")
        user_message = state["messages"][-1].content if state["messages"] else ""
        
        logger.info(f"🔧 [L3 Resolver] Starting resolution for ticket={ticket_id} (retry #{retry_count})")
        
        try:
            # 1. Force RAG Search directly
            rag_query = str(user_message)
            runbook_res = await self.rag_tool.adispatch("search", {"query": rag_query, "use_cache": True}) if self.rag_tool else ""
            runbook_str = str(runbook_res) if runbook_res else ""
            runbook = f"[RAG Runbook]\n{runbook_str}" if runbook_str else ""
            
            # 2. Extract affected service to force Incident History check
            extract_prompt = f"Extract ONLY the core affected service or system name from this issue (e.g. 'auth-api', 'PostgreSQL', 'VPN'). Output nothing else. Issue: {user_message}\nInvestigation: {investigation}"
            service_name_res = await self.router_llm.ainvoke([{"role": "user", "content": extract_prompt}])
            service_name = service_name_res.content.strip()
            
            history_res = await self.crm_tool.adispatch("check_incident_history", {"affected_service": service_name}) if self.crm_tool else ""
            history_str = str(history_res) if history_res else ""
            action_res = f"[Incident History]\n{history_str}" if history_str else ""
            
            # Combine Context
            combined_context = f"{runbook}\n\n{action_res}".strip()
            logger.info(f"🔧 [L3 Resolver] Gathered Context length: {len(combined_context)}")
            
            # 3. Check if empty
            no_runbook = ("No results" in runbook_str) or not runbook_str.strip()
            no_history = ("No past incidents" in history_str) or ("not found" in history_str) or not history_str.strip()
            
            if no_runbook and no_history:
                logger.warning(f"🔧 [L3 Resolver] No context found. Escaping without action.")
                return {
                    "retrieved_runbook": combined_context,
                    "action_taken": "It seems there is no previous incident or runbook, please contact a senior officer.",
                    "retry_count": retry_count
                }
            
            # 4. Use LLM just to extract the required action parameters, bypassing slow bind_tools
            system_prompt = build_l3_resolver_prompt()
            action_prompt = f"Based on the issue, investigation, and runbook below, determine the system action to take. Return ONLY a JSON object with 'action_type' and 'resolution_notes'.\nIssue: {user_message}\nInvestigation: {investigation}\nContext:\n{combined_context}"
            
            res = await self.router_llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": action_prompt}
            ])
            
            match = re.search(r'\{.*\}', res.content, re.DOTALL)
            if match:
                try:
                    action_data = json.loads(match.group())
                    action_type = action_data.get("action_type", "unknown_action")
                    notes = action_data.get("resolution_notes", "Automated fix applied.")
                except Exception:
                    action_type = "unknown_action"
                    notes = res.content.strip()
            else:
                action_type = "unknown_action"
                notes = res.content.strip()

            if self.crm_tool:
                final_action_res = await self.crm_tool.adispatch("perform_system_action", {
                    "ticket_id": ticket_id,
                    "action_type": action_type,
                    "resolution_notes": notes
                })
                final_action = f"[perform_system_action]\n{final_action_res}"
            else:
                final_action = "CRM tool unavailable to perform system action."
                
            logger.info(f"🔧 [L3 Resolver] Resolution complete. Action result preview: {final_action[:150]}")
            
            return {
                "retrieved_runbook": combined_context,
                "action_taken": final_action,
                "retry_count": retry_count
            }
        except Exception as e:
            logger.error(f"❌ [L3 Resolver] Action failed: {e}")
            return {"action_taken": f"Action failed: {e}", "retry_count": retry_count}


    async def l4_supervisor_node(self, state: AgentState) -> dict:
        """5. L4 Supervisor - Escalates T4 or finalizes T2/T3 directly."""
        retry_count = state.get("retry_count", 0)
        route = state.get("route_decision", {}).get("route", "unknown")
        ticket_id = state.get("ticket_id", "UNKNOWN")
        
        logger.info(f"👔 [L4 Supervisor] Evaluating ticket={ticket_id}, route={route}, retries={retry_count}")
        
        # If it's a direct T4 Voice escalation
        if route == "l4_voice":
            logger.warning(f"🚨 [L4 Supervisor] T4 Critical — escalating to LiveKit Voice Agent")
            return {"final_answer": "🚨 ESCALATED TO LIVEKIT VOICE AGENT. (Sub-2s latency path triggered). Waiting for DevOps clearance..."}
            
        # Otherwise, act as finalizer for T2/T3
        if retry_count > 3:
            logger.warning(f"⚠️ [L4 Supervisor] Max retries ({retry_count}) exceeded — escalating to human engineer")
            return {"final_answer": "I apologize, but I am unable to resolve this issue automatically. I have escalated this ticket to a human engineer."}
        
        if "final_answer" in state and state["final_answer"]:
            return {}
            
        user_message = state["messages"][-1].content if state["messages"] else ""
        memory_context = state.get("memory_context", "")
        tool_output = state.get("action_taken", state.get("investigation_results", "No output generated."))
        
        try:
            # Generate final conversational response
            # For CAG route, the RAG answer is already good — use fast LLM to rephrase
            # For T2/T3 routes, use the full chat LLM for more thorough synthesis
            system_prompt, user_prompt = build_synthesiser_prompt(
                user_message=str(user_message),
                memory_context=memory_context,
                route=route,
                tool_output=tool_output
            )
            
            synth_llm = self.llm_fast if route == "cag" else self.llm_chat
            
            # Run ticket update and LLM synthesis in PARALLEL
            import asyncio
            
            async def _update_ticket():
                if self.crm_tool and ticket_id != "UNKNOWN":
                    await self.crm_tool.adispatch("update_ticket", {
                        "ticket_id": ticket_id,
                        "status": "resolved",
                        "resolution_notes": tool_output
                    })
            
            async def _synthesize():
                if route in ("voice", "l4_voice"):
                    from langchain_core.messages import AIMessage
                    ans = state.get("final_answer", "I have detected a critical IT issue. Escalating to the Voice response team automatically. Please hold...")
                    emit_cb = state.get("emit")
                    if emit_cb:
                        await emit_cb({"type": "token", "content": ans})
                    return AIMessage(content=ans)

                msgs = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Ticket ID: {ticket_id}\n\n{user_prompt}\n\nPlease generate a friendly final response explaining the resolution."}
                ]
                ans = ""
                from langchain_core.messages import AIMessage
                emit_cb = state.get("emit")
                async for chunk in synth_llm.astream(msgs, config={"tags": ["final_synthesis"]}):
                    if chunk.content:
                        ans += chunk.content
                        if emit_cb:
                            await emit_cb({"type": "token", "content": chunk.content})
                return AIMessage(content=ans)
            
            _, response = await asyncio.gather(_update_ticket(), _synthesize())
            
            final_ans = response.content
            logger.info(f"👔 [L4 Supervisor] Final answer generated ({len(final_ans)} chars)")
            return {"final_answer": final_ans}
        except Exception as e:
            logger.error(f"❌ [L4 Supervisor] Error: {e}")
            return {"final_answer": f"L4 Supervisor error: {e}"}


    async def memory_save_node(self, state: AgentState) -> dict:
        """8. Save ST and distill LT facts."""
        user_id = state.get("user_id", "default_user")
        session_id = state.get("session_id", "default_session")
        logger.info(f"💾 [Memory Save] Persisting conversation for user={user_id}, session={session_id}")
        
        if not state.get("messages"):
            return {}
            
        user_message = state["messages"][-1].content
        final_answer = state.get("final_answer", "")
        
        try:
            turn_u = ConversationTurn(user_id=user_id, session_id=session_id, role="user", content=str(user_message), ts=time.time())
            turn_a = ConversationTurn(user_id=user_id, session_id=session_id, role="assistant", content=str(final_answer), ts=time.time())
            self.st_store.add(user_id, session_id, turn_u)
            self.st_store.add(user_id, session_id, turn_a)
            logger.info(f"💾 [Memory Save] ST turns saved (user + assistant)")
            
            recent_turns = self.st_store.recent(user_id, session_id, k=6)
            if self.distiller.should_distill(recent_turns):
                self.distiller.distill(user_id, recent_turns)
                logger.info(f"💾 [Memory Save] LT distillation triggered")
                
        except Exception as e:
            logger.error(f"❌ [Memory Save] Failed: {e}")
            
        return {}


    # ---------------------------------------------------------------------------
    # Graph Compilation
    # ---------------------------------------------------------------------------

    def build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        
        workflow.add_node("memory_ingest_node", self.memory_ingest_node)
        workflow.add_node("l1_triage_node", self.l1_triage_node)
        workflow.add_node("cag_fastpath_node", self.cag_fastpath_node)
        workflow.add_node("l2_investigator_node", self.l2_investigator_node)
        workflow.add_node("l3_resolver_node", self.l3_resolver_node)
        workflow.add_node("l4_supervisor_node", self.l4_supervisor_node)
        workflow.add_node("memory_save_node", self.memory_save_node)
        
        workflow.add_edge(START, "memory_ingest_node")
        workflow.add_edge("memory_ingest_node", "l1_triage_node")
        
        def route_triage(state: AgentState) -> Literal["cag_fastpath_node", "l2_investigator_node", "l4_supervisor_node"]:
            route = state.get("route_decision", {}).get("route", "l2_investigator")
            logger.info(f"🔀 [Router] Triage routing to: {route}")
            if route == "cag":
                return "cag_fastpath_node"
            elif route == "l4_voice":
                return "l4_supervisor_node"
            return "l2_investigator_node"

        def route_retry_l2(state: AgentState) -> Literal["l3_resolver_node", "l4_supervisor_node"]:
            retry_count = state.get("retry_count", 0)
            if retry_count > 3:
                logger.warning(f"🔀 [Router] L2 retry count ({retry_count}) exceeded — escalating to L4")
                return "l4_supervisor_node"
            logger.info(f"🔀 [Router] L2 → L3 (retry #{retry_count})")
            return "l3_resolver_node"

        def route_retry_l3(state: AgentState) -> Literal["l4_supervisor_node", "l2_investigator_node"]:
            action = str(state.get("action_taken", "")).lower()
            retry_count = state.get("retry_count", 0)
            # If the action failed or had an error, loop back to L2 for reinvestigation
            if "fail" in action or "error" in action or "exception" in action:
                if retry_count <= 3:
                    logger.warning(f"🔄 [Router] L3 action FAILED — looping back to L2 (retry #{retry_count})")
                    return "l2_investigator_node"
            logger.info(f"🔀 [Router] L3 → L4 (finalizing)")
            return "l4_supervisor_node"
            
        workflow.add_conditional_edges("l1_triage_node", route_triage)
        workflow.add_conditional_edges("l2_investigator_node", route_retry_l2)
        workflow.add_conditional_edges("l3_resolver_node", route_retry_l3)
        
        workflow.add_edge("cag_fastpath_node", "l4_supervisor_node")
        workflow.add_edge("l4_supervisor_node", "memory_save_node")
        workflow.add_edge("memory_save_node", END)
        
        return workflow.compile()

    # ── Voice Fast Path ────────────────────────────────────────

    async def achat_stream_fast(
        self,
        user_message: str,
        user_id: str,
        session_id: str,
    ):
        """Single-LLM streaming path for voice. Yields chunks for TTS synthesis."""
        import asyncio as _asyncio
        from langchain_core.messages import SystemMessage, HumanMessage

        t_start = time.perf_counter()

        # 1. Gather Memory Context
        memory_context = ""
        cache = getattr(self, "_voice_ctx_cache", None)
        if cache is None:
            cache = self._voice_ctx_cache = {}
        cached_turns = cache.get(session_id)
        if cached_turns:
            memory_context = self.recaller.format_context(cached_turns)
        else:
            try:
                recent = await _asyncio.wait_for(
                    _asyncio.to_thread(self.st_store.recent, user_id, session_id, 6),
                    timeout=0.6,
                )
                if recent:
                    memory_context = self.recaller.format_context(recent)
                    cache[session_id] = list(recent)
            except _asyncio.TimeoutError:
                logger.warning("voice: first-turn memory fetch slow (>0.6s) — proceeding")
            except Exception as e:
                logger.debug(f"voice: memory fetch failed (non-fatal): {e}")

        tool_output = ""
        route = "direct_chat"
        was_cancelled = False
        running = ""

        # 2. Classification (Guardrail + Router)
        try:
            decision_state = await self.decision_graph.ainvoke({
                "message": user_message,
                "router_context": memory_context,
            })
            guardrail_verdict = decision_state.get("guardrail", "in_scope")
            decision = decision_state.get("decision", {})
            route = decision.get("route", "direct_chat")
            
            # Short-circuit: Out of scope
            if guardrail_verdict == "out_of_scope":
                refusal = "I'm sorry, but that question is outside my IT operations domain. How else can I help you today?"
                yield ("token", refusal)
                yield ("partial", refusal)
                await self._save_voice_turn_async(user_id=user_id, session_id=session_id, user_message=user_message, assistant_message=refusal, was_interrupted=False)
                from api.schemas import ChatResponse
                yield ("final", ChatResponse(answer=refusal, route="out_of_scope", latency_ms=int((time.perf_counter() - t_start) * 1000)))
                return

            # Short-circuit: Direct chat (no heavy tools needed)
            if route == "direct_chat":
                # Skip manual orchestration entirely, use final fast LLM prompt below
                pass
            else:
                # Heavy path: CAG or L2/L3 workflow
                filler1 = "I am looking into this for you right now... "
                yield ("token", filler1)
                running += filler1
                yield ("partial", running)

                q = _asyncio.Queue()

                async def _q_emit(ev):
                    if ev.get("type") == "voice_filler":
                        await q.put(ev["content"])

                state = {
                    "messages": [HumanMessage(content=user_message)],
                    "user_id": user_id,
                    "session_id": session_id,
                    "user_email": user_id,
                    "memory_context": memory_context,
                    "route_decision": decision,
                    "retry_count": 0,
                    "emit": _q_emit,
                }

                # Background task for the graph execution
                async def run_manual_graph():
                    # L1 Triage
                    out1 = await self.l1_triage_node(state)
                    state.update(out1)
                    current_route = state.get("route_decision", {}).get("route", route)

                    if current_route == "cag":
                        out = await self.cag_fastpath_node(state)
                        state.update(out)
                    elif current_route in ("l2_investigator", "l4_voice"):
                        await _q_emit({"type": "voice_filler", "content": "I'm starting to investigate the issue right now. "})
                        # L2 Investigate
                        out2 = await self.l2_investigator_node(state)
                        state.update(out2)
                        # L3 Resolve
                        out3 = await self.l3_resolver_node(state)
                        state.update(out3)
                        
                        # We do NOT loop retries on voice to keep latency bounded
                    
                    await q.put(None) # Signal completion
                    return state

                task = _asyncio.create_task(run_manual_graph())
                
                try:
                    while True:
                        try:
                            item = await _asyncio.wait_for(q.get(), timeout=8.0)
                            if item is None:
                                break
                            yield ("token", item)
                            running += item
                            yield ("partial", running)
                        except _asyncio.TimeoutError:
                            if not task.done():
                                filler2 = "Still checking the systems, please bear with me... "
                                yield ("token", filler2)
                                running += filler2
                                yield ("partial", running)
                except _asyncio.CancelledError:
                    task.cancel()
                    raise

                final_state = task.result()
                
                # Build context for final TTS synthesis
                if final_state.get("cag_context"):
                    tool_output = f"KNOWLEDGE: {final_state.get('cag_context')}"
                else:
                    inv = final_state.get("investigation_results", "")
                    act = final_state.get("action_taken", "")
                    tool_output = ""
                    if inv: tool_output += f"INVESTIGATION: {inv}\n"
                    if act: tool_output += f"RESOLUTION: {act}\n"

        except _asyncio.CancelledError:
            was_cancelled = True
            logger.info(f"voice: cancelled mid-stream (barge-in) during orchestration.")
            return
        except Exception as e:
            logger.warning(f"voice: orchestration failed (non-fatal): {e}")

        # 3. Final Voice Synthesis
        system = (
            "You are the ZuuSwarm AI IT Operations voice assistant on a live phone "
            "call. Keep replies short, warm, conversational — under three "
            "sentences. No markdown, no tables, no bullet points, no asterisks. "
            "The caller is listening, not reading; read names and numbers naturally.\n\n"
            "Conversation rules:\n"
            "- STAY on the current IT issue or access request.\n"
            "- If the caller asks to check a ticket, ask for the ticket number if you don't know it.\n"
            "- If the information below doesn't answer the question, say so in "
            "one short sentence and offer to create a new ticket — never invent facts.\n\n"
            "IT quick facts:\n"
            "- The IT Helpdesk is available 24/7 for critical P1/P2 issues.\n"
            "- Routine access requests may take up to 24 hours.\n\n"
        )
        if tool_output:
            system += (
                "Answer using ONLY the information below — it is the live source "
                "of truth from the IT systems. Do NOT invent details.\n\n"
                f"=== INFORMATION ===\n{tool_output}\n\n"
            )
        system += f"=== RECENT CONVERSATION ===\n{memory_context}"
        
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user_message),
        ]

        llm = getattr(self, "llm_fast", self.llm_chat)
        answer_parts: list[str] = []

        try:
            async for chunk in llm.astream(messages):
                content = getattr(chunk, "content", None)
                if not content:
                    continue
                answer_parts.append(content)
                running += content
                yield ("token", content)
                yield ("partial", running)
                await _asyncio.sleep(0)
        except _asyncio.CancelledError:
            was_cancelled = True
            logger.info(f"voice: cancelled mid-stream (barge-in) during synthesis.")

        answer_final = "".join(answer_parts).strip()
        latency = int((time.perf_counter() - t_start) * 1000)

        if answer_final or running:
            await self._save_voice_turn_async(
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
                assistant_message=running,
                was_interrupted=was_cancelled,
            )

        if was_cancelled:
            return

        from api.schemas import ChatResponse
        yield (
            "final",
            ChatResponse(
                answer=running,
                route=route,
                latency_ms=latency,
            ),
        )

    async def _voice_dispatch_tool(self, decision, *, reported_by, fallback_query=""):
        route = decision.get("route", "direct") if isinstance(decision, dict) else "direct"
        try:
            if route in ("cag_fastpath", "l3_resolver") and self.rag_tool is not None:
                return await self.rag_tool.adispatch("search", {"query": fallback_query})
            if route == "l2_investigator" and self.crm_tool is not None:
                return await self.crm_tool.adispatch("create_ticket", {
                    "issue_description": fallback_query,
                    "ticket_type": decision.get("ticket_type", "T2"),
                    "severity": decision.get("severity", "medium"),
                    "reported_by": reported_by,
                })
        except Exception as e:
            logger.warning(f"voice: tool dispatch ({route}) failed: {e}")
        return ""

    async def _save_voice_turn_async(self, *, user_id, session_id, user_message, assistant_message, was_interrupted):
        import asyncio as _asyncio
        stored_assistant = f"[interrupted] {assistant_message}" if was_interrupted and assistant_message else assistant_message
        
        def _do_save():
            try:
                now = time.time()
                self.st_store.add(user_id, session_id, ConversationTurn(user_id=user_id, session_id=session_id, role="user", content=user_message, ts=now))
                self.st_store.add(user_id, session_id, ConversationTurn(user_id=user_id, session_id=session_id, role="assistant", content=stored_assistant, ts=now))
                
                try:
                    _cache = getattr(self, "_voice_ctx_cache", None)
                    if _cache is None:
                        _cache = self._voice_ctx_cache = {}
                    _turns = list(_cache.get(session_id) or [])
                    _turns.append(ConversationTurn(user_id=user_id, session_id=session_id, role="user", content=user_message, ts=now))
                    _turns.append(ConversationTurn(user_id=user_id, session_id=session_id, role="assistant", content=stored_assistant, ts=now))
                    _cache[session_id] = _turns[-6:]
                except Exception: pass
                
                # Long-term distillation
                if not was_interrupted and hasattr(self, "distiller"):
                    try:
                        recent = self.st_store.recent(user_id, session_id, k=5)
                        if self.distiller.should_distill(recent):
                            logger.info(f"voice: distilling LT facts for {user_id}")
                            self.distiller.distill(user_id, recent)
                    except Exception as e:
                        logger.debug(f"voice: distillation failed (non-fatal): {e}")

            except Exception as e:
                logger.warning(f"voice: memory write failed: {e}")

        try:
            await _asyncio.to_thread(_do_save)
        except Exception as e:
            logger.warning(f"voice: save task failed: {e}")

# ---------------------------------------------------------------------------
# Setup Factory
# ---------------------------------------------------------------------------

def build_agent(enable_crm: bool = True, enable_rag: bool = True) -> AgentOrchestrator:
    """Builds the Multi-Agent Orchestrator."""
    from infrastructure.llm.llm_provider import (
        get_chat_llm,
        get_fast_chat_llm,
        get_router_llm,
        get_extractor_llm,
    )
    from infrastructure.llm.embeddings import get_default_embeddings
    from memory.st_store import ShortTermMemoryStore
    from memory.lt_store import LongTermMemoryStore
    from memory.memory_ops import MemoryRecaller, MemoryDistiller

    llm_chat = get_chat_llm(temperature=0)
    llm_fast = get_fast_chat_llm(temperature=0)
    llm_router = get_router_llm(temperature=0)
    llm_extractor = get_extractor_llm(temperature=0)
    embedder = get_default_embeddings()

    st_store = ShortTermMemoryStore()
    lt_store = LongTermMemoryStore(embedder)
    recaller = MemoryRecaller(st_store, lt_store)
    distiller = MemoryDistiller(llm=llm_extractor, lt_store=lt_store)

    crm_tool = None
    if enable_crm:
        try:
            from agents.tools import CRMTool
            crm_tool = CRMTool()
            logger.info("CRM tool initialised")
        except Exception as e:
            logger.warning(f"CRM tool unavailable: {e}")

    rag_tool = None
    if enable_rag:
        try:
            from agents.tools import RAGTool
            rag_tool = RAGTool(embedder=embedder, llm=llm_fast)
            logger.info("RAG tool initialised")
        except Exception as e:
            logger.warning(f"RAG tool unavailable: {e}")

    return AgentOrchestrator(
        llm_chat=llm_chat,
        llm_fast=llm_fast,
        llm_router=llm_router,
        llm_guardrail=llm_extractor,
        st_store=st_store,
        lt_store=lt_store,
        recaller=recaller,
        distiller=distiller,
        crm_tool=crm_tool,
        rag_tool=rag_tool,
    )


# ── MCP-backed factory (teaching demo) ─────────────────────────

async def _mcp_invoke_async(tool, params: dict) -> str:
    """
    Direct async invocation to avoid blocking nodes and reduce latency.
    """
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    raw = await tool.ainvoke(clean)
    if isinstance(raw, list):
        return "\n".join(
            item.get("text", str(item))
            for item in raw
            if isinstance(item, dict)
        ) or str(raw)
    return str(raw)

class _MCPCRMToolAdapter:
    """
    Adapter: MCP CRM tools → CRMTool interface.
    """
    _ACTION_TO_TOOL = {
        "create_ticket": "create_ticket",
        "update_ticket": "update_ticket",
        "check_user_clearance": "check_user_clearance",
        "get_asset_health": "get_asset_health",
        "check_service_status": "check_service_status",
        "check_incident_history": "check_incident_history",
        "perform_system_action": "perform_system_action",
    }

    def __init__(self, tools_by_name: dict):
        self._tools = tools_by_name

    async def adispatch(self, action: str, params: dict) -> str:
        tool_name = self._ACTION_TO_TOOL.get(action)
        if not tool_name or tool_name not in self._tools:
            return f"Unavailable CRM action: {action}."
        try:
            return await _mcp_invoke_async(self._tools[tool_name], params)
        except Exception as exc:
            logger.error(f"MCP CRM tool '{tool_name}' failed: {exc}")
            return f"Error: {exc}"

class _MCPRAGToolAdapter:
    """
    Adapter: MCP RAG tools → RAGTool interface.
    """
    _ACTION_TO_TOOL = {
        "search": "rag_search",
        "cache_stats": "cache_stats",
        "clear_cache": "clear_cache",
    }

    def __init__(self, tools_by_name: dict):
        self._tools = tools_by_name

    async def adispatch(self, action: str, params: dict) -> str:
        tool_name = self._ACTION_TO_TOOL.get(action)
        if not tool_name or tool_name not in self._tools:
            return f"Unavailable RAG action: {action}."
        try:
            return await _mcp_invoke_async(self._tools[tool_name], params)
        except Exception as exc:
            logger.error(f"MCP RAG tool '{tool_name}' failed: {exc}")
            return f"Error: {exc}"


async def build_agent_mcp() -> AgentOrchestrator:
    """
    MCP-backed variant of build_agent() — ALL tools via MCP.
    """
    from infrastructure.llm.llm_provider import (
        get_chat_llm, get_router_llm, get_extractor_llm
    )
    from infrastructure.llm.embeddings import get_default_embeddings
    from memory.st_store import ShortTermMemoryStore
    from memory.lt_store import LongTermMemoryStore
    from memory.memory_ops import MemoryRecaller, MemoryDistiller
    from langchain_mcp_adapters.client import MultiServerMCPClient

    from mcp_servers.mcp_config import build_mcp_server_config

    llm_chat = get_chat_llm(temperature=0)
    llm_router = get_router_llm(temperature=0)
    llm_extractor = get_extractor_llm(temperature=0)
    embedder = get_default_embeddings()

    st_store = ShortTermMemoryStore()
    lt_store = LongTermMemoryStore(embedder)
    recaller = MemoryRecaller(st_store, lt_store)
    distiller = MemoryDistiller(llm=llm_extractor, lt_store=lt_store)

    server_config = build_mcp_server_config()
    logger.info(f"Connecting to MCP servers: {list(server_config.keys())}")
    mcp_client = MultiServerMCPClient(server_config)

    all_tools = await mcp_client.get_tools()
    tools_by_name = {t.name: t for t in all_tools}
    logger.info(f"Loaded {len(all_tools)} tools via MCP: {list(tools_by_name.keys())}")

    crm_tool = _MCPCRMToolAdapter(tools_by_name)
    logger.info("CRM tool backed by machina-crm MCP server")

    rag_tool = _MCPRAGToolAdapter(tools_by_name)
    logger.info("RAG tool backed by machina-rag MCP server")

    orchestrator = AgentOrchestrator(
        llm_chat=llm_chat,
        llm_router=llm_router,
        llm_guardrail=llm_extractor,
        st_store=st_store,
        lt_store=lt_store,
        recaller=recaller,
        distiller=distiller,
        crm_tool=crm_tool,
        rag_tool=rag_tool,
    )

    orchestrator.mcp_client = mcp_client
    orchestrator.mcp_tools = tools_by_name

    return orchestrator

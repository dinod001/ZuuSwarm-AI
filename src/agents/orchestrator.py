"""
LangGraph Orchestrator for ZuuSwarm AI.
Implements the full L1 -> L4 graph with 4-tier memory integration.
Now completely Object-Oriented and integrated with MultiServerMCPClient.
"""

import time
from typing import Literal, Optional, List
from infrastructure.log import get_logger
logger = get_logger("orchestrator")
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
load_dotenv()

from agents.state import AgentState
from agents.router import query_router
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


class AgentOrchestrator:
    """
    Main Orchestrator Class for ZuuSwarm AI.
    Runs the LangGraph nodes as async instance methods.
    """
    
    def __init__(
        self,
        mcp_client: MultiServerMCPClient,
        reasoning_llm,
        router_llm,
        st_store: ShortTermMemoryStore,
        lt_store: LongTermMemoryStore,
        ep_store: EpisodicMemoryStore,
        mcp_tools: List = None,
    ):
        self.mcp_client = mcp_client
        self.reasoning_llm = reasoning_llm
        self.router_llm = router_llm
        self.st_store = st_store
        self.lt_store = lt_store
        self.ep_store = ep_store
        self.mcp_tools = mcp_tools or []
        
        self.recaller = MemoryRecaller(st_store, lt_store)
        self.distiller = MemoryDistiller(llm=router_llm, lt_store=lt_store)
        
        self.app = self.build_graph()

    async def mcp_invoke(self, server_name: str, tool_name: str, params: dict) -> str:
        """
        Helper method to manually invoke an MCP tool dynamically.
        Finds the LangChain tool from the client and executes it.
        """
        try:
            for t in self.mcp_tools:
                if t.name == tool_name:
                    logger.info(f"🚀 [{server_name}] Invoking MCP Tool: {tool_name}")
                    logger.debug(f"   📋 Params: {params}")
                    start = time.time()
                    res = await t.ainvoke(params)
                    elapsed = round((time.time() - start) * 1000)
                    logger.info(f"✅ [{server_name}] {tool_name} completed in {elapsed}ms")
                    logger.debug(f"   📦 Result preview: {str(res)[:200]}")
                    return res
            logger.warning(f"⚠️ Tool '{tool_name}' not found in loaded MCP tools.")
            return f"Error: Tool '{tool_name}' not found."
        except Exception as e:
            logger.error(f"❌ [{server_name}] MCP invoke FAILED for {tool_name}: {e}")
            return f"MCP error: {e}"

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
            decision = query_router(user_message=str(user_message), memory_context=memory_context)
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

                res = await self.mcp_invoke("machina-crm", "create_ticket", {
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
            clearance_res = await self.mcp_invoke("machina-crm", "check_user_clearance", {"email": user_email})
            
            import re
            match = re.search(r'\d+', str(clearance_res))
            if match:
                clearance = int(match.group())
            else:
                clearance = 0
            
            logger.info(f"⚡ [CAG FastPath] User clearance level: {clearance} (raw={str(clearance_res)[:50]})")
                
            if clearance >= 3:
                logger.info(f"✅ [CAG FastPath] Clearance APPROVED (level {clearance} >= 3). Querying RAG...")
                answer_text = await self.mcp_invoke("machina-rag", "rag_search", {"query": str(user_message), "use_cache": True})
                answer = f"CAG FastPath (Clearance Level {clearance} Approved):\n{answer_text}"
            else:
                logger.warning(f"🚫 [CAG FastPath] Clearance REJECTED (level {clearance} < 3)")
                answer = f"CAG FastPath Rejected: You do not have the required SQL clearance (Level 3+) for this request. Your level is {clearance}."
        except Exception as e:
            logger.error(f"❌ [CAG FastPath] Failed: {e}")
            answer = f"CAG failed: {e}"
            
        return {"action_taken": answer}


    async def l2_investigator_node(self, state: AgentState) -> dict:
        """4. Query Observability Metrics using LLM Tool Calling."""
        retry_count = state.get("retry_count", 0) + 1
        decision = state.get("route_decision", {})
        user_message = state["messages"][-1].content if state["messages"] else ""
        prev_failure = state.get("action_taken", "")
        
        logger.info(f"🔍 [L2 Investigator] Starting investigation (retry #{retry_count})")
        
        try:
            l2_tools = [t for t in self.mcp_tools if t.name in ["get_asset_health", "check_service_status"]]
            llm = self.reasoning_llm.bind_tools(l2_tools)
            
            system_prompt = build_l2_investigator_prompt()
            
            # On retry, include previous failure context so L2 doesn't repeat the same approach
            user_content = f"Ticket Route Info: {decision}\n\nUser Message: {user_message}\n\nExtract the asset/service name and check its status."
            if retry_count > 1 and prev_failure:
                user_content += f"\n\n⚠️ PREVIOUS ATTEMPT FAILED (retry #{retry_count}). Previous L3 result: {prev_failure}\nTry a DIFFERENT investigation approach."
                logger.warning(f"🔄 [L2 Investigator] Retry #{retry_count} — injecting previous failure context")
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            response = await llm.ainvoke(messages)
            
            investigation_results = ""
            
            if response.tool_calls:
                tool_calls_to_run = response.tool_calls[:3]
                logger.info(f"🔍 [L2 Investigator] LLM requested {len(response.tool_calls)} tool call(s). Executing max {len(tool_calls_to_run)}.")
                for tc in tool_calls_to_run:
                    res = await self.mcp_invoke("machina-crm", tc["name"], tc["args"])
                    investigation_results += f"[{tc['name']}]\n{res}\n\n"
            
            if not investigation_results:
                investigation_results = response.content
            
            logger.info(f"🔍 [L2 Investigator] Investigation complete. Result length: {len(investigation_results)} chars")
            return {"investigation_results": investigation_results.strip(), "retry_count": retry_count}
        except Exception as e:
            logger.error(f"❌ [L2 Investigator] Failed: {e}")
            return {"investigation_results": f"Investigator error: {e}", "retry_count": retry_count}


    async def l3_resolver_node(self, state: AgentState) -> dict:
        """6. Execute fix using RAG and SQL History."""
        retry_count = state.get("retry_count", 0) + 1
        investigation = state.get("investigation_results", "")
        ticket_id = state.get("ticket_id", "UNKNOWN")
        user_message = state["messages"][-1].content if state["messages"] else ""
        
        logger.info(f"🔧 [L3 Resolver] Starting resolution for ticket={ticket_id} (retry #{retry_count})")
        
        try:
            # 1. Force RAG Search
            rag_query = str(user_message)
            runbook_res = await self.mcp_invoke("machina-rag", "rag_search", {"query": rag_query, "use_cache": True})
            runbook_str = str(runbook_res) if runbook_res else ""
            runbook = f"[RAG Runbook]\n{runbook_str}" if runbook_str else ""
            
            # 2. Extract affected service to force Incident History check
            extract_prompt = f"Extract ONLY the core affected service or system name from this issue (e.g. 'auth-api', 'PostgreSQL', 'VPN'). Output nothing else. Issue: {user_message}\nInvestigation: {investigation}"
            service_name_res = await self.router_llm.ainvoke([{"role": "user", "content": extract_prompt}])
            service_name = service_name_res.content.strip()
            
            history_res = await self.mcp_invoke("machina-crm", "check_incident_history", {"affected_service": service_name})
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
            
            # 4. Use Context to perform system action
            l3_tools = [t for t in self.mcp_tools if t.name == "perform_system_action"]
            llm = self.reasoning_llm.bind_tools(l3_tools)
            
            system_prompt = build_l3_resolver_prompt()
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Ticket ID: {ticket_id}\nUser Issue: {user_message}\nL2 Investigation: {investigation}\n\nCombined Context:\n{combined_context}\n\nPlease execute `perform_system_action` to fix the issue."}
            ]
            
            response = await llm.ainvoke(messages)
            
            final_action = response.content
            if response.tool_calls:
                tc = response.tool_calls[0] # Take the first tool call
                if tc["name"] == "perform_system_action":
                    res = await self.mcp_invoke("machina-crm", tc["name"], tc["args"])
                    final_action = f"[{tc['name']}]\n{res}"
            
            if not final_action:
                final_action = "perform_system_action was not called by the LLM."
                
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
        """5. L4 Supervisor - Escalates T4 or finalizes T2/T3."""
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
            l4_tools = [t for t in self.mcp_tools if t.name in ["update_ticket", "check_service_status"]]
            llm = self.reasoning_llm.bind_tools(l4_tools)
            
            system_prompt, user_prompt = build_synthesiser_prompt(
                user_message=str(user_message),
                memory_context=memory_context,
                route=route,
                tool_output=tool_output
            )
            
            response = await llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Ticket ID: {ticket_id}\n\n{user_prompt}\n\nVerify and close the ticket if resolved."}
            ])
            
            supervisor_logs = ""
            if response.tool_calls:
                tool_calls_to_run = response.tool_calls[:3]
                logger.info(f"👔 [L4 Supervisor] LLM requested {len(response.tool_calls)} tool call(s). Executing max {len(tool_calls_to_run)}.")
                for tc in tool_calls_to_run:
                    if tc["name"] in ["update_ticket", "perform_system_action"]:
                        # Force the correct ticket_id if LLM forgot or used UNKNOWN
                        if tc["args"].get("ticket_id") in ["UNKNOWN", None, ""]:
                            tc["args"]["ticket_id"] = ticket_id
                            
                        res = await self.mcp_invoke("machina-crm", tc["name"], tc["args"])
                        supervisor_logs += f"[{tc['name']}] -> {res}\n"
                    
            # Fallback text if LLM just called tools without generating a response string
            final_ans = response.content
            if not final_ans:
                # If LLM produces tool calls but no output content, ask it to summarize the L3 action into a friendly final response
                summary_prompt = f"The issue was resolved with the following actions:\n{tool_output}\n\nPlease generate a friendly final response to the user explaining how the issue was resolved."
                summary_response = await self.reasoning_llm.ainvoke([
                    {"role": "user", "content": summary_prompt}
                ])
                final_ans = summary_response.content if summary_response.content else tool_output
            
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
                
            # Also capture the episode
            all_turns = self.st_store.recent(user_id, session_id, k=100)
            if len(all_turns) >= 2:
                episode = create_episode_from_turns(user_id, session_id, all_turns, self.reasoning_llm)
                self.ep_store.store_episode(episode)
                logger.info(f"💾 [Memory Save] Episodic memory saved for session {session_id}")
                
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


# ---------------------------------------------------------------------------
# Setup Factory
# ---------------------------------------------------------------------------

async def build_agent_mcp() -> AgentOrchestrator:
    """
    Initializes MCP client and dependencies, and returns an AgentOrchestrator instance.
    """
    logger.info("Building AgentOrchestrator and connecting to MCP servers...")
    config = build_mcp_server_config()
    mcp_client = MultiServerMCPClient(config)
    # Initialize connection here so TaskGroups bind to the main event loop
    # instead of inside transient LangGraph node contexts.
    tools = await mcp_client.get_tools()
    logger.info("MCP client initialized and tools loaded.")
    
    embedder = get_default_embeddings()
    llm_reasoning = get_chat_llm()
    llm_router = get_router_llm(temperature=0)
    
    st_store = ShortTermMemoryStore()
    lt_store = LongTermMemoryStore(embedder)
    ep_store = EpisodicMemoryStore(embedder)
    
    return AgentOrchestrator(
        mcp_client=mcp_client,
        reasoning_llm=llm_reasoning,
        router_llm=llm_router,
        st_store=st_store,
        lt_store=lt_store,
        ep_store=ep_store,
        mcp_tools=tools
    )

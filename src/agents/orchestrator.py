"""
LangGraph Orchestrator for ZuuSwarm AI.
Implements the full L1 -> L4 graph with 4-tier memory integration.
Now completely Object-Oriented and integrated with MultiServerMCPClient.
"""

import time
from typing import Literal, Optional, List
from loguru import logger
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
                    logger.info(f"🚀 Invoking MCP Tool: {tool_name} with params: {params}")
                    res = await t.ainvoke(params)
                    logger.info(f"✅ MCP Tool finished: {tool_name}")
                    return res
            return f"Error: Tool '{tool_name}' not found."
        except Exception as e:
            logger.error(f"MCP invoke failed for {tool_name}: {e}")
            return f"MCP error: {e}"

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------

    async def memory_ingest_node(self, state: AgentState) -> dict:
        """1. Load ST and LT memory for context."""
        user_id = state.get("user_id", "default_user")
        session_id = state.get("session_id", "default_session")
        
        user_message = state["messages"][-1].content if state["messages"] else ""
            
        try:
            # recall is currently synchronous in memory_ops, but we can run it safely
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
            
            return {"memory_context": out, "retry_count": 0}
        except Exception as e:
            logger.error(f"Memory ingest failed: {e}")
            return {"memory_context": "(Memory unavailable)", "retry_count": 0}


    async def l1_triage_node(self, state: AgentState) -> dict:
        """2. Classify and Route."""
        user_message = state["messages"][-1].content if state["messages"] else ""
        memory_context = state.get("memory_context", "")
        
        try:
            # Router is sync
            decision = query_router(user_message=str(user_message), memory_context=memory_context)
            
            ticket_id = "UNKNOWN"
            try:
                # Map Router T1-T4 to CRM Enums
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
                if isinstance(res, str) and "Ticket " in res:
                    ticket_id = res.split("Ticket ")[1].split(" ")[0]
            except Exception as e:
                logger.error(f"Failed to create ticket: {e}")

            return {"route_decision": decision, "ticket_id": ticket_id}
        except Exception as e:
            logger.error(f"L1 Triage failed: {e}")
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
        user_message = state["messages"][-1].content if state["messages"] else ""
        
        try:
            clearance_str = await self.mcp_invoke("machina-crm", "check_user_clearance", {"email": user_id})
            
            try:
                clearance = int(clearance_str)
            except (ValueError, TypeError):
                clearance = 0
                
            if clearance >= 3:
                # Authorized -> Retrieve CAG response from machina-rag
                answer_text = await self.mcp_invoke("machina-rag", "search", {"query": str(user_message), "use_cache": True})
                answer = f"CAG FastPath (Clearance Level {clearance} Approved):\n{answer_text}"
            else:
                # Unauthorized
                answer = f"CAG FastPath Rejected: You do not have the required SQL clearance (Level 3+) for this request. Your level is {clearance}."
        except Exception as e:
            answer = f"CAG failed: {e}"
            
        return {"action_taken": answer}


    async def l2_investigator_node(self, state: AgentState) -> dict:
        """4. Query Observability Metrics using LLM Tool Calling."""
        retry_count = state.get("retry_count", 0) + 1
        decision = state.get("route_decision", {})
        user_message = state["messages"][-1].content if state["messages"] else ""
        
        try:
            # Bind L2 tools
            l2_tools = [t for t in self.mcp_tools if t.name in ["get_asset_health", "check_service_status"]]
            llm = self.reasoning_llm.bind_tools(l2_tools)
            
            system_prompt = build_l2_investigator_prompt()
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Ticket Route Info: {decision}\n\nUser Message: {user_message}\n\nExtract the asset/service name and check its status."}
            ]
            
            response = await llm.ainvoke(messages)
            
            investigation_results = ""
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    res = await self.mcp_invoke("machina-crm", tc["name"], tc["args"])
                    investigation_results += f"[{tc['name']}]\n{res}\n\n"
            
            if not investigation_results:
                investigation_results = response.content
                
            return {"investigation_results": investigation_results.strip(), "retry_count": retry_count}
        except Exception as e:
            return {"investigation_results": f"Investigator error: {e}", "retry_count": retry_count}


    async def l3_resolver_node(self, state: AgentState) -> dict:
        """6. Execute fix using RAG and SQL History Tool Calling."""
        retry_count = state.get("retry_count", 0) + 1
        investigation = state.get("investigation_results", "")
        ticket_id = state.get("ticket_id", "UNKNOWN")
        user_message = state["messages"][-1].content if state["messages"] else ""
        
        try:
            l3_tools = [t for t in self.mcp_tools if t.name in ["check_incident_history", "search", "perform_system_action"]]
            llm = self.reasoning_llm.bind_tools(l3_tools)
            
            system_prompt = build_l3_resolver_prompt()
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Ticket ID: {ticket_id}\nUser Issue: {user_message}\nL2 Investigation: {investigation}\n\nRetrieve runbooks/history and perform the fix."}
            ]
            
            response = await llm.ainvoke(messages)
            
            runbook = ""
            action_res = ""
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    if tc["name"] == "search":
                        runbook += "[RAG Runbook]\n" + str(await self.mcp_invoke("machina-rag", tc["name"], tc["args"])) + "\n"
                    else:
                        action_res += f"[{tc['name']}]\n" + str(await self.mcp_invoke("machina-crm", tc["name"], tc["args"])) + "\n"
                        
            return {
                "retrieved_runbook": runbook.strip(),
                "action_taken": action_res.strip() if action_res else response.content,
                "retry_count": retry_count
            }
        except Exception as e:
            return {"action_taken": f"Action failed: {e}", "retry_count": retry_count}


    async def l4_supervisor_node(self, state: AgentState) -> dict:
        """5. L4 Supervisor - Escalates T4 or finalizes T2/T3."""
        retry_count = state.get("retry_count", 0)
        route = state.get("route_decision", {}).get("route", "unknown")
        
        # If it's a direct T4 Voice escalation
        if route == "l4_voice":
            return {"final_answer": "🚨 ESCALATED TO LIVEKIT VOICE AGENT. (Sub-2s latency path triggered). Waiting for DevOps clearance..."}
            
        # Otherwise, act as finalizer for T2/T3
        if retry_count > 3:
            return {"final_answer": "I apologize, but I am unable to resolve this issue automatically. I have escalated this ticket to a human engineer."}
        
        if "final_answer" in state and state["final_answer"]:
            return {}
            
        user_message = state["messages"][-1].content if state["messages"] else ""
        memory_context = state.get("memory_context", "")
        tool_output = state.get("action_taken", state.get("investigation_results", "No output generated."))
        ticket_id = state.get("ticket_id", "UNKNOWN")
        
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
            
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self.mcp_invoke("machina-crm", tc["name"], tc["args"])
                    
            # Fallback text if LLM just called tools without generating a response string
            final_ans = response.content if response.content else "Ticket verified and closed by L4 Supervisor."
            
            return {"final_answer": final_ans}
        except Exception as e:
            return {"final_answer": f"L4 Supervisor error: {e}"}


    async def memory_save_node(self, state: AgentState) -> dict:
        """8. Save ST and distill LT facts."""
        user_id = state.get("user_id", "default_user")
        session_id = state.get("session_id", "default_session")
        
        if not state.get("messages"):
            return {}
            
        user_message = state["messages"][-1].content
        final_answer = state.get("final_answer", "")
        
        try:
            turn_u = ConversationTurn(user_id=user_id, session_id=session_id, role="user", content=str(user_message), ts=time.time())
            turn_a = ConversationTurn(user_id=user_id, session_id=session_id, role="assistant", content=str(final_answer), ts=time.time())
            self.st_store.add(user_id, session_id, turn_u)
            self.st_store.add(user_id, session_id, turn_a)
            
            recent_turns = self.st_store.recent(user_id, session_id, k=6)
            if self.distiller.should_distill(recent_turns):
                self.distiller.distill(user_id, recent_turns)
                
            # Also capture the episode
            all_turns = self.st_store.recent(user_id, session_id, k=100)
            if len(all_turns) >= 2:
                # Need to run create_episode_from_turns with the LLM synchronously or wrap it properly.
                # Since memory_save_node is async, we can do it normally.
                episode = create_episode_from_turns(user_id, session_id, all_turns, self.reasoning_llm)
                self.ep_store.store_episode(episode)
                logger.info(f"💾 Episodic memory saved for session {session_id}")
                
        except Exception as e:
            logger.error(f"Memory save failed: {e}")
            
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
            if route == "cag":
                return "cag_fastpath_node"
            elif route == "l4_voice":
                return "l4_supervisor_node"
            return "l2_investigator_node"

        def route_retry_l2(state: AgentState) -> Literal["l3_resolver_node", "l4_supervisor_node"]:
            if state.get("retry_count", 0) > 3:
                return "l4_supervisor_node"
            return "l3_resolver_node"

        def route_retry_l3(state: AgentState) -> Literal["l4_supervisor_node"]:
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

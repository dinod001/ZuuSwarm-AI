"""
AgentState — the shared state dictionary for the LangGraph StateGraph.

Every node in the graph reads from and writes back to this TypedDict.
Think of it as the "conveyor belt" that carries data through the pipeline
from L1 Triage -> L2 Investigator -> L3 Resolver -> L4 Supervisor.
"""

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── Standard LangGraph State ──
    messages: Annotated[list[AnyMessage], add_messages]
    
    # User / session identifiers (passed through every node)
    user_id: str
    user_email: Optional[str]
    session_id: str
    
    # Context
    memory_context: Optional[str]

    # ── L1 Triage State ──
    # Holds the JSON from query_router (ticket_type, severity, route, reasoning)
    route_decision: Optional[dict]  
    # The ID of the ticket created in the live_tickets table
    ticket_id: Optional[str]        

    # ── L2 Investigator State ──
    # Output from Observability tools (CPU/RAM/Load) passed to L3
    investigation_results: Optional[str] 

    # ── L3 Resolver State ──
    # Markdown runbook content retrieved from Qdrant via RAG
    retrieved_runbook: Optional[str]     
    # Description of the system action or fix applied
    action_taken: Optional[str]          

    # ── Final Outputs ──
    # What the user actually sees at the end of the flow
    final_answer: Optional[str]          

    # ── Guardrails ──
    # Tracks tool invocation loops to prevent infinite loops (Max 3 retries)
    retry_count: Optional[int]

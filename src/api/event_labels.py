"""
Friendly labels for the chain-of-thought timeline.

Maps internal stage / tool identifiers to human-readable strings the
UI shows users while their request is in flight. Keeps the wording
in one place so the chain-of-thought never says "get_asset_health" but
"Querying asset health metrics".
"""

from typing import Optional, Tuple


STAGE_LABELS: dict[str, str] = {
    "cache":                "Looking in cache for similar issues",
    "recall_st":            "Loading your conversation history",
    "recall_lt":            "Searching your long-term memory",
    "patient":              "Verifying your IT clearance profile",
    "route":                "Routing your issue to the right agent",
    "guardrail":            "Checking the issue is in scope",
    "tool":                 "Executing the diagnostic or resolution tool",
    "synth":                "Composing your resolution report",
    "save":                 "Saving the incident conversation",
    
    # LangGraph Orchestrator Nodes
    "memory_ingest_node":   "Loading your conversation history",
    "l1_triage_node":       "Triaging and routing your issue",
    "cag_fastpath_node":    "Checking cache for an instant resolution",
    "l2_investigator_node": "Investigating system health and metrics",
    "l3_resolver_node":     "Executing resolution steps based on runbooks",
    "l4_supervisor_node":   "Verifying resolution and closing ticket",
    "memory_save_node":     "Saving incident history",
}


# Tool-level labels keyed by (route, action). action is None for routes
# without a sub-action (rag / web_search / direct).
_TOOL_LABELS: dict[Tuple[str, Optional[str]], str] = {
    ("crm", "create_ticket"):            "Creating a support ticket in the CRM",
    ("crm", "update_ticket"):            "Updating ticket details in the CRM",
    ("crm", "check_user_clearance"):     "Verifying your security clearance",
    ("crm", "get_asset_health"):         "Querying asset health metrics",
    ("crm", "check_service_status"):     "Checking live service status",
    ("crm", "check_incident_history"):   "Searching past incident history",
    ("crm", "perform_system_action"):    "Executing an automated system action",
    
    ("rag", None):                       "Searching IT runbooks and knowledge base",
    ("rag", "search"):                   "Searching IT runbooks and knowledge base",
    ("rag", "rag_search"):               "Searching IT runbooks and knowledge base",
    ("rag", "cache_stats"):              "Checking knowledge base cache statistics",
    ("rag", "clear_cache"):              "Clearing the knowledge base cache",
    
    ("direct", None):                    "Composing a direct reply",
    ("multi", None):                     "Running multiple IT diagnostics in parallel",
    ("cag_hit", None):                   "Returning a cached instant resolution",
    ("out_of_scope", None):              "Politely declining — outside IT operations domain",
}


def tool_label(route: str, action: Optional[str] = None) -> str:
    """Friendly label for a single tool invocation."""
    return (
        _TOOL_LABELS.get((route, action))
        or _TOOL_LABELS.get((route, None))
        or f"Running {route}{' / ' + action if action else ''}"
    )


def stage_label(stage: str) -> str:
    """Friendly label for a pipeline stage."""
    return STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())

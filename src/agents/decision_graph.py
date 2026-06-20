from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, Literal, Optional, TypedDict

from loguru import logger
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from agents.guardrail import Guardrail
from agents.router import QueryRouter,RouteDecision

# ──────────────────────────────────────────────────────────────────
# State schema
# ──────────────────────────────────────────────────────────────────


GuardrailVerdict = Literal["in_scope", "out_of_scope"]
DecisionVerdict = Literal["out_of_scope", "main_router"]
MultiRouteDecision = Dict[str, Any]

class DecisionState(TypedDict, total=False):
    """Mutable state passed between nodes.

    Inputs are filled by the chat router before ``ainvoke``.
    Each parallel node writes to a single dedicated key, so the
    default replace-reducer is safe (no concurrent writes to the
    same field). The ``decide`` node reads everything and produces
    the final ``verdict``.
    """

    # ── inputs ─────────────────────────────────────────────────
    message: str
    router_context: str

    # ── parallel node outputs ─────────────────────────────────
    guardrail: GuardrailVerdict
    decision: MultiRouteDecision

    # ── final verdict (set by decide_node) ────────────────────
    verdict: DecisionVerdict
    primary_route: str

def make_guardrail_node(guardrail: Guardrail):
    """Closure factory: returns a node bound to the given Guardrail.

    The closure captures ``guardrail`` so the graph builder doesn't
    need to know about the orchestrator's instance state.
    """

    async def guardrail_node(
        state: DecisionState,
        config: Optional[RunnableConfig] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            # Pass conversation context so follow-ups like "how did you fix it"
            # are correctly classified as in_scope when prior turns are IT-related
            context = state.get("router_context", "")
            msg_with_context = state["message"]
            if context:
                msg_with_context = f"[Conversation context: {context[-500:]}]\nCurrent message: {state['message']}"
            verdict = await guardrail.aclassify(msg_with_context)
        except Exception as exc:
            logger.warning("Guardrail node failed (defaulting in_scope): {}", exc)
            verdict = "in_scope"
        return {"guardrail": verdict}

    return guardrail_node


def make_router_node(router: QueryRouter):
    """Closure factory: router_node bound to the given QueryRouter."""

    async def router_node(
        state: DecisionState,
        config: Optional[RunnableConfig] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            decision = await router.aroute(
                state["message"], state.get("router_context", "")
            )
        except Exception as exc:
            logger.warning("Router node failed (defaulting direct): {}", exc)
            decision = {"route": "direct", "confidence": 0.0}
            
        return {"decision": decision}

    return router_node

def decide_node(
    state: DecisionState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """
    Decide node reads all parallel outputs and produces the final verdict.
    
    Priority:
      1. If guardrail is out_of_scope → verdict='out_of_scope'
      2. Check router decisions for routing hints
      3. Default to 'main_router' if nothing else matches
    
    This node is intentionally simple and deterministic.
    """
    
    # 1. Guardrail check takes priority
    if state.get("guardrail") == "out_of_scope":
        return {
            "verdict": "out_of_scope",
            "primary_route": None,
        }
    
    # 2. Examine router decision
    primary = state.get("decision", {})
    
    # 3. Determine primary route based on decision
    if primary and primary.get("route") in ["cag", "l2_investigator", "l3_resolver", "voice", "direct_chat"]:
        return {
            "verdict": "main_router",
            "primary_route": primary["route"],
        }
    
    # 4. Fallback: Default to main router if no clear decision
    return {
        "verdict": "main_router",
        "primary_route": "direct",  # Default direct routing
    }

def build_decision_graph(
    *,
    guardrail: Guardrail,
    router: QueryRouter,
):
    """
    Build the parallel-merge-decide graph:
      Guardrail → Router → Decide → END
    """

    builder = StateGraph(DecisionState)

    # Nodes
    g_node = make_guardrail_node(guardrail)
    r_node = make_router_node(router)

    # Add nodes
    builder.add_node("guardrail", g_node)
    builder.add_node("route", r_node)
    builder.add_node("decide", decide_node)

    # Edges (Sequential execution for simplicity)
    builder.add_edge(START, "guardrail")
    builder.add_edge("guardrail", "route")
    builder.add_edge("route", "decide")
    builder.add_edge("decide", END)

    return builder.compile()
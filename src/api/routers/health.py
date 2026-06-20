from fastapi import APIRouter, Request
from typing import Dict, Any
import time

router = APIRouter()

# Keep track of when the server started
START_TIME = time.time()

@router.get("")
@router.get("/")
async def check_health(request: Request, ping_tools: bool = False) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint.
    Verifies the status of the server, orchestrator, LLMs, and MCP tools.
    
    Args:
        request: The FastAPI request object.
        ping_tools: If True, attempts to actively dispatch a safe test request to the tools.
    """
    uptime = time.time() - START_TIME
    
    agent = getattr(request.app.state, "agent", None)
    
    health_status = {
        "status": "ok",
        "service": "ZuuSwarm AI",
        "uptime_seconds": round(uptime, 2),
        "components": {
            "orchestrator": "offline",
            "llms": {
                "chat": "offline",
                "fast": "offline",
                "router": "offline",
            },
            "tools": {
                "crm": "offline",
                "rag": "offline"
            }
        }
    }
    
    if not agent:
        health_status["status"] = "degraded"
        health_status["message"] = "Agent orchestrator is not yet initialized."
        return health_status

    # Orchestrator is up
    health_status["components"]["orchestrator"] = "online"
    
    # Check LLMs
    if getattr(agent, "llm_chat", None):
        health_status["components"]["llms"]["chat"] = "online"
    if getattr(agent, "llm_fast", None):
        health_status["components"]["llms"]["fast"] = "online"
    if getattr(agent, "llm_router", None):
        health_status["components"]["llms"]["router"] = "online"

    # Check CRM Tool
    crm_tool = getattr(agent, "crm_tool", None)
    if crm_tool:
        if ping_tools:
            try:
                # Dispatch a lightweight, safe read operation to verify connection
                await crm_tool.adispatch("check_service_status", {"service_name": "API"})
                health_status["components"]["tools"]["crm"] = "online (pinged)"
            except Exception as e:
                health_status["components"]["tools"]["crm"] = f"error: {str(e)}"
                health_status["status"] = "degraded"
        else:
            health_status["components"]["tools"]["crm"] = "online"

    # Check RAG Tool
    rag_tool = getattr(agent, "rag_tool", None)
    if rag_tool:
        if ping_tools:
            try:
                # Dispatch a lightweight search to verify vector DB/MCP connection
                await rag_tool.adispatch("search", {"query": "health check", "use_cache": True})
                health_status["components"]["tools"]["rag"] = "online (pinged)"
            except Exception as e:
                health_status["components"]["tools"]["rag"] = f"error: {str(e)}"
                health_status["status"] = "degraded"
        else:
            health_status["components"]["tools"]["rag"] = "online"

    # If any essential component is offline, mark degraded
    if health_status["components"]["tools"]["crm"] == "offline" or health_status["components"]["tools"]["rag"] == "offline":
        health_status["status"] = "degraded"
        health_status["message"] = "One or more essential tools are offline."

    return health_status

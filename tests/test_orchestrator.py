import sys
import os
import json
import asyncio
from dotenv import load_dotenv

# Load .env file
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

# Ensure src is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from langchain_core.messages import HumanMessage
from agents.orchestrator import build_agent_mcp
from loguru import logger

async def test_orchestrator():
    # Load incidents
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "all_distilled_incidents.json"))
    with open(data_path, "r", encoding="utf-8") as f:
        incidents = json.load(f)

    # Pick a couple of questions
    logger.info("🚀 Initializing AgentOrchestrator... (This will start MCP servers)")
    orchestrator = await build_agent_mcp()
    logger.success("✅ Initialization Complete!\n")

    user_id = "EMP-0408" # Valid employee ID
    session_id = "test-session-001"

    # Test 1: T1 Access (Should route to CAG)
    logger.info("-" * 50)
    logger.info("🔹 TEST 1: T1 Access/Identity (Routing to CAG FastPath)")
    logger.info("-" * 50)
    t1_prob = incidents[0]["problem"]
    logger.info(f"User: {t1_prob}\n")
    
    state = {
        "messages": [HumanMessage(content=t1_prob)],
        "user_id": user_id,
        "session_id": session_id,
        "retry_count": 0,
    }
    
    # We invoke the graph
    result_state = await orchestrator.app.ainvoke(state)
    
    # --- Logging fetched RAG/SQL data ---
    from langchain_core.messages import ToolMessage
    for msg in result_state.get("messages", []):
        if isinstance(msg, ToolMessage):
            logger.debug(f"🔍 Fetched from {msg.name}: {msg.content[:200]}...")
            
    logger.success(f"🤖 ZuuSwarm: {result_state.get('final_answer', 'No Answer')}\n")


    # Test 2: T3/T4 Critical DB Issue
    logger.info("-" * 50)
    logger.info("🔹 TEST 2: Critical Database Issue (Routing to L2/L3/L4)")
    logger.info("-" * 50)
    t3_prob = incidents[4]["problem"] # "PostgreSQL high CPU utilization..."
    logger.info(f"User: {t3_prob}\n")
    
    state = {
        "messages": [HumanMessage(content=t3_prob)],
        "user_id": user_id,
        "session_id": session_id,
        "retry_count": 0,
    }
    
    result_state = await orchestrator.app.ainvoke(state)
    
    # --- Logging fetched RAG/SQL data ---
    from langchain_core.messages import ToolMessage
    for msg in result_state.get("messages", []):
        if isinstance(msg, ToolMessage):
            logger.debug(f"🔍 Fetched from {msg.name}: {msg.content[:200]}...")
            
    logger.success(f"🤖 ZuuSwarm: {result_state.get('final_answer', 'No Answer')}\n")

    logger.info("-" * 50)
    logger.success("✅ Tests completed.")


if __name__ == "__main__":
    asyncio.run(test_orchestrator())

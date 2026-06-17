import json
import re
from loguru import logger
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from infrastructure.llm.llm_provider import get_router_llm
from agents.prompts.agent_prompts import build_l1_triage_prompt

class RouteDecision(BaseModel):
    ticket_type: str = Field(description="T1, T2, T3, or T4")
    severity: str = Field(description="low, medium, or critical")
    route: str = Field(description="cag, l2_investigator, l3_resolver, or voice")
    reasoning: str = Field(description="one-sentence technical explanation")

def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Try finding any JSON object in the text
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not extract JSON from response: {text[:200]}")

class QueryRouter:
    """Class-based wrapper for L1 Triage Agent routing logic."""
    
    def __init__(self, llm=None):
        self.llm = llm or get_router_llm(temperature=0)
        
    async def aroute(self, user_message: str, memory_context: str) -> dict:
        """Classifies the user message and decides the route."""
        system_prompt, user_prompt = build_l1_triage_prompt(
            user_message=user_message,
            memory_context=memory_context
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        # We use ainvoke since the graph awaits aroute
        response = await self.llm.ainvoke(messages)
        
        try:
            parsed = _extract_json(response.content)
            
            decision = RouteDecision(**parsed)
            return decision.model_dump()
        except Exception as e:
            logger.error(f"Router JSON parse failed: {e}. Raw: {response.content[:300]}")
            # Fallback
            fallback = {
                "ticket_type": "T2",
                "severity": "medium",
                "route": "l2_investigator",
                "reasoning": f"Fallback: could not parse router output — {e}"
            }
            return {"decisions": [fallback]}


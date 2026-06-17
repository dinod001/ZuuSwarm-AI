from __future__ import annotations

from typing import Any, Literal
from infrastructure.log import get_logger

logger = get_logger(__name__)

GuardrailVerdict = Literal["in_scope", "out_of_scope"]

# THIS IS THE GURADARIN PROMPT 
#DEINF WHAT INSSIDE SCOPE , WHAT IS OUT OF SCOPE 
_GUARDRAIL_SYSTEM = """\
You are a scope filter for ZuuSwarm AI, an intelligent IT incident resolution platform.

Decide whether the user's message is within the assistant's domain.

IN-SCOPE — the assistant should help with:
  • Access & Identity (VPN resets, password issues, permissions, 2FA)
  • Asset Provisioning (New laptops, broken hardware, software licenses)
  • Service Degradation (Slow APIs, database latency, network issues)
  • Critical Outages (Total system failures, OOM errors, services down)
  • Checking system status, incident history, retrieving IT runbooks
  • Executing system actions, analyzing observability metrics (CPU, memory)
  • Greetings, small talk, thanks (these are still in-scope; the
    main assistant handles them)

OUT-OF-SCOPE — politely refuse:
  • General world knowledge (presidents, capitals, sports, history,
    celebrities, politics, science trivia)
  • Other businesses, brands, services, products unrelated to IT operations
  • Generic weather, news, stock prices, sports scores
  • Writing code, general software development, math problems, jokes, riddles
  • Gibberish or random non-questions
  • Anything you can't confidently tie to IT support, system incidents,
    or infrastructure

Answer with ONE WORD ONLY: ``in_scope`` or ``out_of_scope``.
No explanation, no punctuation, no other tokens.
"""

# Few-shot examples baked into the user-prompt template — keeps the
# 8B model honest without burning a separate fine-tune.
_GUARDRAIL_EXAMPLES = """\
Examples:
  USER: "Critical system failure! Website down!"    → in_scope
  USER: "My VPN is not connecting."                 → in_scope
  USER: "Can you check the Redis memory usage?"     → in_scope
  USER: "I need a new laptop provisioned."          → in_scope
  USER: "Hey there, I need help with an IT issue"   → in_scope
  USER: "Who is the president of the USA?"          → out_of_scope
  USER: "What's the weather in Sri Lanka?"          → out_of_scope
  USER: "Write me a Python script to sort a list"   → out_of_scope
  USER: "How do I bake a cake?"                     → out_of_scope
  USER: "What's the capital of France?"             → out_of_scope
"""

def _build_user_prompt(message: str) -> str:
    return f"{_GUARDRAIL_EXAMPLES}\n\nUSER: \"{(message or '').strip()}\"\n→"

class Guardrail:
    """Binary in_scope / out_of_scope classifier."""

    def __init__(self, llm: Any) -> None:
        """
        Args:
            llm: A LangChain ``ChatOpenAI``-compatible instance.
                Use the extractor LLM (Llama 3.1 8B on Groq) — it's
                cheap and fast enough that parallel guardrail latency
                is hidden behind the router (~800 ms) in every gather.
        """
        self.llm = llm

    async def aclassify(self, message: str) -> GuardrailVerdict:
        """Classify *message* as ``in_scope`` or ``out_of_scope``.

        Fails open: any LLM error returns ``in_scope`` so transient
        provider issues don't lock real users out of the assistant.
        """
        msgs = [
            {"role": "system", "content": _GUARDRAIL_SYSTEM},
            {"role": "user", "content": _build_user_prompt(message)},
        ]
        try:
            response = await self.llm.ainvoke(msgs)
        except Exception as exc:
            logger.warning("Guardrail LLM error (failing open): {}", exc)
            return "in_scope"

        raw = (
            response.content if hasattr(response, "content") else str(response)
        ).strip().lower()

        # Be permissive in parsing — the model occasionally adds quotes,
        # backticks, or trailing punctuation despite the instruction.
        verdict: GuardrailVerdict
        if "out_of_scope" in raw or "out-of-scope" in raw or "out of scope" in raw:
            verdict = "out_of_scope"
        elif "in_scope" in raw or "in-scope" in raw or "in scope" in raw:
            verdict = "in_scope"
        else:
            # Unrecognised response — safest default is to let the
            # normal pipeline handle it.
            logger.debug("Guardrail unparsable response {!r} → defaulting in_scope", raw[:50])
            verdict = "in_scope"
            
        return verdict
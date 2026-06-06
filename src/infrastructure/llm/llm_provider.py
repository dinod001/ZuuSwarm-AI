"""
Chat LLM providers — 3-model architecture.

Three specialised LLMs for different tasks:
  - Router:    gpt-4o-mini via OpenRouter (reliable JSON output)
  - Extractor: llama-3.1-8b-instant via Groq (ultra-fast structured extraction)
  - Chat:      gemini-2.0-flash via OpenRouter (high quality synthesis)
"""

from typing import Optional, Any
from langchain_openai import ChatOpenAI

from infrastructure.config import (
    ROUTER_MODEL,
    ROUTER_PROVIDER,
    EXTRACTOR_MODEL,
    EXTRACTOR_PROVIDER,
    GROQ_BASE_URL,
    CHAT_MODEL,
    CHAT_PROVIDER,
    FAST_CHAT_MODEL,
    FAST_CHAT_PROVIDER,
    OPENROUTER_BASE_URL,
    get_api_key,
)


def _build_llm(
    model: str,
    provider: str,
    temperature: float = 0,
    streaming: bool = False,
    max_tokens: Optional[int] = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """Internal factory — builds a ChatOpenAI for any provider."""
    llm_kwargs: dict[str, Any] = dict(
        model=model,
        temperature=temperature,
        streaming=streaming,
        max_tokens=max_tokens,
        **kwargs,
    )

    if provider == "openrouter":
        llm_kwargs["openai_api_base"] = OPENROUTER_BASE_URL
        llm_kwargs["openai_api_key"] = get_api_key("openrouter")
    elif provider == "groq":
        llm_kwargs["openai_api_base"] = GROQ_BASE_URL
        llm_kwargs["openai_api_key"] = get_api_key("groq")
    elif provider == "openai":
        llm_kwargs["openai_api_key"] = get_api_key("openai")

    return ChatOpenAI(**llm_kwargs)


def get_router_llm(temperature: float = 0, **kwargs: Any) -> ChatOpenAI:
    """LLM for intent classification (routing).

    Model: llama-3.1-8b-instant via Groq.
    LPU hardware delivers ~600 tok/s — a 150-token JSON route decision
    returns in ~250ms vs. 2-3s on gpt-4o-mini-via-OpenRouter, with the
    same accuracy on this classification task.
    """
    return _build_llm(ROUTER_MODEL, ROUTER_PROVIDER, temperature=temperature, **kwargs)


def get_fast_chat_llm(temperature: float = 0.3, **kwargs: Any) -> ChatOpenAI:
    """LLM for the "direct" route — greetings, concierge, follow-ups.

    Model: llama-3.1-8b-instant via Groq.
    Returns short conversational replies in ~150-400ms. Heavier
    flagship synthesis is reserved for tool-backed routes (RAG/CRM/Web)
    via ``get_chat_llm``.
    """
    return _build_llm(FAST_CHAT_MODEL, FAST_CHAT_PROVIDER, temperature=temperature, **kwargs)


def get_extractor_llm(temperature: float = 0, **kwargs: Any) -> ChatOpenAI:
    """LLM for extraction tasks (distillation, topic tagging, trigger checks).

    Model: llama-3.1-8b-instant via Groq.
    Ultra-fast (~50ms), free tier, perfect for structured extraction.
    """
    return _build_llm(EXTRACTOR_MODEL, EXTRACTOR_PROVIDER, temperature=temperature, **kwargs)


def get_chat_llm(temperature: float = 0, **kwargs: Any) -> ChatOpenAI:
    """LLM for user-facing responses (synthesis, RAG generation).

    Model: gemini-2.0-flash via OpenRouter.
    High quality, generous context window, natural tone.
    """
    return _build_llm(CHAT_MODEL, CHAT_PROVIDER, temperature=temperature, **kwargs)

SYSTEM_HEADER = """You are an expert AI Support Engineer for ZuuSwarm AI.
Your goal is to resolve technical incidents or answer queries using ONLY the provided context."""

RAG_TEMPLATE = SYSTEM_HEADER + """

CRITICAL RULES:
1. ONLY use information from the CONTEXT below. Do not use outside knowledge.
2. If the CONTEXT does not contain the answer, say exactly: "I cannot find the answer in the provided documentation. Escalate to human support."
3. Your answer must state the exact steps, terminal commands, or mitigation steps applied to resolve the issue.
4. Write your response in a very polite, friendly, and beautiful human-readable format. Start with a friendly greeting (e.g., "Hi there! I can help you with that...") and explain the technical steps clearly so anyone can understand.
5. Always cite the Source File at the end of your answer as: [Source: <filename>]

CONTEXT:
{context}

QUESTION:
{question}

YOUR ANSWER:"""

# ========================================
# Helper Functions
# ========================================

def build_rag_prompt(context: str, question: str) -> str:
    """
    Build a complete RAG prompt from template, pre-injecting the static 
    and general system header to maintain clean KV-cache alignment.

    Args:
        context: Formatted text containing the source file and content
        question: User query or system alert

    Returns:
        Complete prompt string
    """
    return RAG_TEMPLATE.format(
        system_header=SYSTEM_HEADER, 
        context=context, 
        question=question
    )


def build_system_message() -> str:
    """
    Build the general system message for chat context tracking.

    Returns:
        System prompt string
    """
    return SYSTEM_HEADER
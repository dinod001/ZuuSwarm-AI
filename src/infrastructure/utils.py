from typing import List, Any
from langchain_core.documents import Document

def format_docs(docs: List[Document]) -> str:
    """
    Format a list of LangChain Document objects into a single context string
    for the RAG prompt.
    """
    formatted = []
    for i, doc in enumerate(docs):
        source = doc.metadata.get("source_file", "Unknown")
        problem = doc.metadata.get("problem", "")
        resolution = doc.metadata.get("resolution", "")
        
        # Combine the text with structured incident data if available
        content_parts = []
        if problem:
            content_parts.append(f"Problem: {problem}")
        if resolution:
            content_parts.append(f"Resolution: {resolution}")
        if doc.page_content:
            content_parts.append(f"Details: {doc.page_content}")
            
        body = "\n".join(content_parts)
        
        formatted.append(f"Document [{i+1}] [Source: {source}]:\n{body}\n")
        
    return "\n---\n".join(formatted)

def calculate_confidence(docs: List[Document], query: str) -> float:
    """
    Calculate a confidence score (0.0 to 1.0) based on the retrieved documents.
    Used by CRAG to determine if corrective retrieval is needed.
    """
    if not docs:
        return 0.0
        
    # We use the Qdrant cosine similarity scores stored in metadata
    scores = [float(doc.metadata.get("score", 0.0)) for doc in docs if "score" in doc.metadata]
    
    if not scores:
        return 0.0
        
    # Using the highest score as the confidence metric
    # If the best document is highly relevant, we are confident.
    return max(scores)

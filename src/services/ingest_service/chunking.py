from typing import Any
import json

def custom_chunking(incidents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    texts_to_embed = []

    count = 1
    for incident in incidents:
        # Remove newlines from resolution and problem/root_cause just in case
        problem = incident['problem'].replace('\n', ' ').strip()
        root_cause = incident['root_cause'].replace('\n', ' ').strip()
        resolution = incident['resolution'].replace('\n', ' ').strip()
        
        formatted_text = f"Chunk Index: {count} || Problem: {problem} || Root Cause: {root_cause} || Resolution: {resolution} || Tier: {incident['tier']} || Source File: {incident['source_file']}"
        
        # Attach back to incident dictionary
        incident['chunk_text'] = formatted_text
        incident['chunk_index'] = count
        
        texts_to_embed.append(formatted_text)
        count += 1

    return incidents, texts_to_embed

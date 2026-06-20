import json
import time
import requests

def test_stream():
    url = "http://localhost:8000/api/v1/chat/stream"
    payload = {
        "user_id": "test_user",
        "session_id": "test_session",
        "message": "Critical outage in Kubernetes with 4 nodes not ready"
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"Starting request to {url} at {time.time()}")
    start_time = time.time()
    
    # We use requests.post with stream=True to process chunks as they arrive
    with requests.post(url, json=payload, headers=headers, stream=True) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=None):
            if chunk:
                # Decoded chunk
                text = chunk.decode("utf-8")
                t = time.time() - start_time
                print(f"[{t:.3f}s] Received chunk:\n{text}\n")
                
if __name__ == "__main__":
    test_stream()

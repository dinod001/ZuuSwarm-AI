# 🌟 ZuuSwarm AI

ZuuSwarm AI is an advanced intelligent incident resolution platform. It leverages LLMs for distilling chaotic incident data and utilizes vector databases for high-speed semantic search and targeted context-aware retrieval.

## 🏗️ Architecture & Data Pipeline

The core data ingestion pipeline handles the flow from raw transcripts to structured embeddings stored in Qdrant, optimizing for both massive data retrieval and lightning-fast short-circuit caching for high-priority items.

```mermaid
graph TD
    %% Styling
    classDef default fill:#1E293B,stroke:#38BDF8,stroke-width:2px,color:#fff;
    classDef llm fill:#7C3AED,stroke:#A78BFA,stroke-width:2px,color:#fff;
    classDef db fill:#059669,stroke:#34D399,stroke-width:2px,color:#fff;
    classDef cache fill:#F59E0B,stroke:#FCD34D,stroke-width:2px,color:#111;

    subgraph "1. Raw Data Sources"
        R1[Local Markdown Runbooks]
        R2[Historical Transcripts]
    end

    subgraph "2. S3 Ingestion"
        S3[(AWS S3 Bucket)]
        R2 -- "s3_ingesting.py" --> S3
    end

    subgraph "3. LLM Distillation"
        LLM[OpenAI LLM Distillation]:::llm
        S3 -- "data_generator.py" --> LLM
        R1 -- "data_generator.py" --> LLM
        LLM -- "Extracts" --> EX["Problem, Root Cause, Resolution, Tier"]
    end

    subgraph "4. Formatting & Storage"
        LOCAL["all_distilled_incidents.json"]
        EX --> LOCAL
        LOCAL -- "chunking.py" --> CH[Chunked Text & Metadata]
    end

    subgraph "5. Embeddings"
        EMB[OpenAI Embeddings Model]:::llm
        CH --> EMB
    end

    subgraph "6. Vector Database (Qdrant)"
        MAIN[(Main Qdrant Collection)]:::db
        CAG[(CAG Cache - Tier 1 Only)]:::cache
        
        EMB -- "Upsert All Chunks" --> MAIN
        EMB -- "Conditional: if tier == 1" --> CAG
    end
```

## 🚀 Pipeline Execution Steps

1. **S3 Upload (`s3_ingesting.py`)**: Validates raw JSON incident transcripts and securely uploads them to AWS S3.
2. **LLM Distillation (`data_generator.py`)**: Retrieves documents from S3 and local Markdown runbooks, piping them into an OpenAI model to extract the core `problem`, `root_cause`, `resolution`, and priority `tier`.
3. **Data Combination**: Extracted data from all sources is unified and backed up locally as `all_distilled_incidents.json`.
4. **Chunking (`chunking.py`)**: Takes the structured dictionaries and formats them into clean, standardized strings optimized for dense vector embeddings.
5. **Embeddings Generation**: The text chunks are processed through an embedding provider (e.g., `text-embedding-3-small`) to generate dense semantic vectors.
6. **Main Collection Upsert (`qdrant_client.py`)**: All vector embeddings and metadata are upserted into the primary Qdrant collection.
7. **CAG Cache Injection**: High-priority incidents (Tier 1) are specifically filtered and injected into the specialized `CAG Cache` collection to dramatically speed up retrieval for the L1 System Header prompt.

## 🛠️ Usage

To run the complete end-to-end data ingestion pipeline:

```bash
python src/services/ingest_service/pipeline.py
```

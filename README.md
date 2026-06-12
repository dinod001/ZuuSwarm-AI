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

### 🧠 Agent & MCP Architecture

This describes the execution flow during live incident resolution, utilizing our custom MCP servers to bridge the AI Swarm with the underlying databases.

```mermaid
graph TD
    %% Styling
    classDef agent fill:#EC4899,stroke:#BE185D,stroke-width:2px,color:#fff;
    classDef mcp fill:#3B82F6,stroke:#2563EB,stroke-width:2px,color:#fff;
    classDef db fill:#059669,stroke:#34D399,stroke-width:2px,color:#fff;

    subgraph "LangGraph Swarm (WIP)"
        L1[L1 Triage Agent]:::agent
        L2[L2 Investigator Agent]:::agent
        L3[L3 Resolution Agent]:::agent
        L1 <--> L2
        L2 <--> L3
    end

    subgraph "MCP Servers (Stdio Transport)"
        MCP_CRM[machina-crm]:::mcp
        MCP_RAG[machina-rag]:::mcp
        MCP_CAG[machina-cag]:::mcp
        MCP_MEM[machina-memory]:::mcp
    end

    subgraph "Internal Databases & Knowledge Base"
        DB_SQL[(IT Ops DB: Tickets, Metrics, etc.)]:::db
        DB_QDRANT[(Qdrant: Procedural Memory & CAG)]:::db
        DB_SUPA[(Supabase: 4-Tier Memory)]:::db
    end

    %% Connections
    L1 -.-> |Tool Calls| MCP_CAG
    L1 -.-> |Tool Calls| MCP_CRM
    L2 -.-> |Tool Calls| MCP_CRM
    L2 -.-> |Tool Calls| MCP_MEM
    L3 -.-> |Tool Calls| MCP_RAG
    L3 -.-> |Tool Calls| MCP_CRM

    MCP_CRM --> DB_SQL
    MCP_RAG --> DB_QDRANT
    MCP_CAG --> DB_QDRANT
    MCP_MEM --> DB_SUPA
```

### 🔄 Full Incident Resolution Workflow (L1 -> L4 + Voice Agent)

When a user reports an issue (e.g., *"Critical system failure! Website down!"*), the Swarm executes the following flow:

1. **L1 Agent (Triage)**:
   - Classifies the problem into one of the 4 core ticket types:
     - **T1 (Access & Identity)**: High volume, low severity (e.g., VPN reset).
     - **T2 (Asset Provisioning)**: Medium volume, low severity (e.g., Broken laptop).
     - **T3 (Service Degradation)**: Low volume, medium severity (e.g., Slow API).
     - **T4 (Critical Outages)**: Rare, critical severity (e.g., Redis OOM).
   - Inserts the incident into the `live_tickets` table (e.g., `status='open'`, `severity='critical'`, `ticket_type='critical_outage'`).
   - **Routing Decision**: 
     - **T1**: Calls the CAG (Cache-Augmented Generation) layer directly for an instant response.
     - **T2 & T3**: Escalated to the lower-level agents (L2/L3).
     - **T4**: Routes to the LiveKit Voice Agent for real-time escalation and verification.

2. **L2 Agent (Investigator)**:
   - Utilizes Observability MCP tools (e.g., `get_asset_health`).
   - Queries the `assets_inventory` (and `server_metrics`) tables to check server status, CPU, and memory usage to identify the root cause.

3. **L3 Agent (Resolver)**:
   - Uses the `check_incident_history` tool to query the `incident_history` table and review how similar past incidents were resolved.
   - Retrieves the relevant execution runbook from **Qdrant** (Procedural Memory).
   - Applies the fix using the `perform_system_action` tool (Action MCP).

4. **L4 Agent (Supervisor/Finalizer)**:
   - Reviews and validates the fix applied by the L3 agent.
   - Uses the `update_ticket_status` tool to mark the ticket as resolved in the `live_tickets` table.
   - Notifies the user: *"Problem solved."*

#### 🚨 T4 Deep Dive: Critical Incident Workflow (Voice Escalation)
For **T4 (Critical Outage)** scenarios like a total system crash, the Swarm executes a specialized high-priority flow:
- **Trigger & Alert (L1)**: Logs the critical ticket and immediately triggers the **LiveKit Voice Agent** to call a human DevOps engineer for real-time awareness.
- **Monitoring & Oversight (L4)**: The L4 Supervisor assumes active oversight (Monitored State) to coordinate the resolution.
- **Root Cause Analysis (L2)**: Rapidly pulls CPU/RAM/Load metrics via the Observability MCP to pinpoint the failure point.
- **Resolution Strategy (L3)**: Cross-references Qdrant runbooks with `incident_history` and executes the emergency fix (e.g., restarting Redis) via the Action MCP.
- **Final Verification (L4)**: Verifies system stability post-fix and closes the ticket.

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

## 🤖 Model Context Protocol (MCP) Integration

ZuuSwarm AI is built to be modular and accessible by any MCP-compliant client (LangGraph agents, Claude Desktop, Cursor, etc.). We expose our core capabilities as independent MCP servers communicating over `stdio`:

- **`machina-crm`**: IT Operations CRM. Exposes tools for ticketing (`create_ticket`, `update_ticket`), observability (`get_asset_health`, `check_service_status`), and system actions (`check_incident_history`, `perform_system_action`).
- **`machina-rag`**: Internal knowledge base retrieval. Exposes the CAG + CRAG pipeline (`rag_search`, `rag_cache_stats`).
- **`machina-cag`**: Direct access to the Qdrant-backed semantic cache (`cag_get`, `cag_set`, `cag_clear`).
- **`machina-memory`**: 4-tier persistent semantic memory. Allows agents to seamlessly recall recent conversation turns and store/query long-term facts (`recall_context`, `add_turn`, `store_fact`, `search_facts`).
- **`machina-web`** & **`machina-crawler`**: Web search and asynchronous web crawling tools.

### Inspecting MCP Servers
You can run and test any server interactively using the official MCP Inspector:
```bash
npx @modelcontextprotocol/inspector python -m mcp_servers.crm_server
```

## 🚀 What's Next (Hackathon Action Plan)

Based on the Zuu Crew AI challenge, the following critical milestones are up next:

1. **Multi-Agent Swarm (LangGraph)**: Build the L1/L2/L3 agent architecture to automatically triage tickets, investigate using MCP logs/metrics, and retrieve runbooks via RAG.
2. **Voice Escalation (LiveKit)**: Implement real-time voice escalations for Type 4 (Critical Outage) scenarios (e.g., verifying DevOps clearance before mock restarting a Redis OOM issue).
3. **Full Observability**: Integrate Langfuse to track, trace, and monitor the entire multi-agent swarm's execution paths and token usage.

# ZuuSwarm AI - Multi-Agent IT Operations Chat Architecture

ZuuSwarm AI කියන්නේ සංකීර්ණ IT Operations සහ DevOps ගැටලු ස්වයංක්‍රීයව විසඳන්න හදපු **Multi-Agent System** එකක්. මේකෙදි LangGraph පදනම් කරගෙන විවිධ AI Agents ලා කිහිපදෙනෙක් එකට වැඩ කරලා (Swarm Intelligence) User ගේ ප්‍රශ්න වලට උත්තර හොයනවා.

## ප්‍රධාන කොටස් (Core Architecture)

### 1. Multi-Agent Orchestration (LangGraph)
මෙහි ප්‍රධාන මොළය විදියට ක්‍රියාත්මක වෙන්නේ `AgentOrchestrator` එකයි. මේකෙදි ප්‍රශ්නයක් ආවම ඒක පියවරෙන් පියවර අදාල Agent ට යොමු කරනවා.

*   **L1 Triage Agent:** මුලින්ම ප්‍රශ්නය කියවලා ඒක මොන ජාතියේ එකක්ද (Access Issue ද, Server Crash එකක්ද ආදී වශයෙන්) කියලා වෙන් කරනවා.
*   **CAG FastPath (Level 1):** සරල ගැටලු (උදා: Password Reset, SQL Clearance) වලට කෙලින්ම උත්තර දෙනවා.
*   **L2 Investigator:** ගැටලුව ටිකක් බරපතල නම්, අදාල සර්වර් වල Logs සහ Health Metrics (CRM Tools හරහා) අරගෙන පරික්ෂා කරනවා.
*   **L3 Resolver:** හොයාගත්තු දත්ත පදනම් කරගෙන, RAG (Retrieval-Augmented Generation) හරහා කලින් තිබ්බ Runbooks බලලා අදාල විසඳුම (Resolution) ක්‍රියාත්මක කරනවා.
*   **L4 Supervisor:** අවසාන තීරණය අරගෙන User ට උත්තරය දෙනවා. Critical Outage (T4) එකක් නම් කෙලින්ම LiveKit හරහා Voice Agent කෙනෙක්ට හෝ Human Engineer කෙනෙක්ට transfer කරනවා.

### 2. 4-Tier Memory System (මතක පද්ධතිය)
ZuuSwarm AI වලට විශේෂ මතක පද්ධතියක් තියෙනවා:
*   **Short-Term Memory (ST Store):** දැනට කතා කරමින් ඉන්න Session එකේ මතකය.
*   **Long-Term Memory (LT Store):** Vector Database (Qdrant) එකක් හරහා කලින් විසඳපු ටිකට් සහ User ගේ පුරුදු මතක තියාගන්නවා.
*   **Episodic Memory:** සම්පූර්ණ Incident එකක් ඉවර වුනාම ඒක එක Episode එකක් විදියට save කරනවා.

### 3. Model Architecture (LLM Routing)
වේගය සහ කාර්යක්ෂමතාවය (Latency optimization) වෙනුවෙන් Models 3ක් පාවිච්චි කරනවා:
*   **Router / Triage:** `gpt-4o-mini` (OpenRouter) - නිවැරදිව JSON Output එකක් ගන්න.
*   **Extractor / Fast Chat:** `llama-3.1-8b-instant` (Groq) - මිලි තත්පර ගානෙන් දත්ත වෙන් කරගන්න (50ms - 250ms latency).
*   **Synthesis (Final Answer):** `gemini-2.0-flash` (OpenRouter) - ලස්සනට පැහැදිලිව User ට උත්තරේ හදලා දෙන්න.

### 4. Real-time Streaming (SSE)
User ට "Connecting..." කියලා ගොඩක් වෙලා බලන් ඉන්න දෙන්නේ නැතුව, Backend එකේ වෙන දේවල් (Routing, Investigating, Resolving) ඒ වෙලාවෙම UI එකට පෙන්නන්න **Server-Sent Events (SSE)** පාවිච්චි කරනවා. FastAPI හරහා `astream_events` යොදාගෙන තත්පරෙන් තත්පරේට UI එක අප්ඩේට් කරනවා.

### 5. MCP (Model Context Protocol) Integration
CRM Tools (ටිකට් හදන්න, Status බලන්න) සහ RAG Tools (Docs කියවන්න) කෙලින්ම LLM එකට සම්බන්ධ කරන්නේ `MultiServerMCPClient` එක හරහායි. මේකෙන් Tools වල Security සහ Modularity එක වැඩි වෙනවා.

---
**Tech Stack:**
*   **Backend:** FastAPI, Python, LangGraph, LangChain
*   **Frontend:** React, TypeScript, Vite
*   **LLMs:** OpenRouter (Gemini / GPT), Groq (Llama 3)
*   **Vector DB:** Qdrant

# AI Intelligence Platform for Data Centre EPC Project Delivery
**ET AI Hackathon 2026 — Build Summary**

---

## Problem Statement

India's data centre capacity is growing from 900 MW (2024) to 2,700 MW by 2027 — a $15B investment.
A single hyperscale facility involves 15,000–40,000 equipment line items, 200 concurrent contractors,
and thousands of commissioning test procedures. 67% of Asia-Pacific EPC projects face schedule overruns
exceeding 10% due to information fragmentation across disconnected systems.

---

## Solution

An AI-powered EPC Project Intelligence Platform that unifies project documents, specifications,
schedules, procurement data, and quality records into a living intelligence layer — built for the
hackathon in a single session.

---

## Architecture

```
Streamlit UI (5-tab dashboard + sidebar orchestrator)
        |
Orchestrator Agent (keyword routing + Llama 3.3 70B classification)
        |
 ┌──────┴────────────────────────────────────────────┐
 │  Spec       Schedule   Supply    Commission   RFI  │
 │  Compliance Risk       Chain     QA Copilot  Agent │
 └──────┬────────────────────────────────────────────┘
        |
 Groq API (Llama 3.3 70B + Llama 4 Scout Vision)
        |
 ChromaDB (local RAG, hash embeddings) + Synthetic Project Data
```

---

## Tech Stack

| Component         | Technology                          |
|-------------------|-------------------------------------|
| LLM               | Groq — Llama 3.3 70B Versatile      |
| Vision            | Groq — Llama 4 Scout 17B (vision)   |
| Vector DB         | ChromaDB (in-process, no server)    |
| Embeddings        | Local SHA256 hash (no downloads)    |
| UI                | Streamlit                           |
| Config            | python-dotenv                       |
| PDF ingestion     | pypdf                               |
| Language          | Python 3.10                         |

---

## Project Structure

```
epc-intelligence/
├── .env                          # API keys (gitignored)
├── .env.example                  # Template
├── .gitignore                    # Protects .env from GitHub
├── config.py                     # Central config loader
├── requirements.txt              # groq, chromadb, streamlit, pypdf, python-dotenv
├── core/
│   └── groq_client.py            # Singleton Groq wrapper with retry + fallback
├── rag/
│   └── rag_engine.py             # ChromaDB + LocalHashEmbedding + keyword fallback
├── agents/
│   ├── spec_compliance.py        # NCR detection + Llama 4 Scout vision analysis
│   ├── schedule_risk.py          # CPM risk engine + Groq mitigations
│   ├── supply_chain.py           # Shipment tracking + alternative sourcing
│   ├── commissioning_qa.py       # TIA-942 test sequences + auto PASS/FAIL
│   ├── rfi_knowledge.py          # Full-context RAG Q&A with citations
│   └── orchestrator.py           # Multi-agent router
├── ui/
│   └── app.py                    # Streamlit 5-tab dashboard
└── data/
    ├── standards/
    │   ├── tia942_excerpts.txt   # TIA-942-B excerpts
    │   └── uptime_tier_concepts.txt  # Uptime Institute Tier III concepts
    └── synthetic/
        ├── procurement_items.csv     # 50 items, 4 deliberate NCR deviations
        ├── project_schedule.json     # 15 tasks, 2 critical path violations
        ├── supplier_locations.json   # 10 suppliers, 2 at-risk deliveries
        └── rfis.json                 # 20 RFIs with resolutions
```

---

## The 5 Agents

### 1. Spec & Quality Compliance Agent
- Loads 50 procurement items from CSV
- Deterministic string comparison: spec_requirement vs vendor_submitted_value
- Flags 4 NCRs automatically (3 CRITICAL, 1 MEDIUM)
- Generates formal NCR narratives via Groq
- Drawing/submittal analysis using Llama 4 Scout vision (real image reading)
- Fallback: filename-based analysis if vision fails

### 2. Predictive Schedule Risk Engine
- Loads 15 schedule tasks from JSON
- Deterministic CPM logic: flags tasks where delay_days > 0 or risk_score > threshold
- Identifies 2 critical path violations
- Groq generates 3 actionable mitigation options per at-risk task
- Fallback: hardcoded mitigation templates per equipment category

### 3. Supply Chain Visibility Agent
- Tracks 10 suppliers with geospatial coordinates
- Flags 2 at-risk shipments (ETA < 7 days threshold)
- Interactive map via Streamlit st.map()
- Groq generates alternative supplier recommendations
- Fallback: hardcoded Indian vendor list per equipment type

### 4. Commissioning QA Copilot
- Grounded in TIA-942-B and Uptime Institute Tier III standards
- 4 system types: power, cooling, network, fire
- Each system has a hardcoded fallback checklist (7 steps for power)
- Deterministic PASS/FAIL validation (numeric comparison + keyword detection)
- Groq generates formal test record documents
- Download test record as .txt

### 5. Project Knowledge & RFI Intelligence Agent
- Bypasses vector retrieval for standards questions (hash embeddings not semantic)
- Injects full TIA-942 + Uptime Institute text directly into Groq's 131K context
- Injects all 20 RFIs as direct context
- Keyword-based similar RFI detection
- Returns answers with inline citations [SOURCE: tia942_excerpts.txt]
- Fallback: keyword match against RFI resolutions when Groq fails

### Orchestrator
- Step 1: Keyword classification (instant, no LLM)
- Step 2: Groq Llama 3.3 70B classification if ambiguous
- Renders results as clean readable summaries (not raw JSON)
- Per-agent rendering: compliance table, schedule violations, supply chain map data, commissioning steps, RFI answers

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| LLM | Groq Llama 3.3 70B | No quota limits, 131K context, fast inference |
| Vision | Groq Llama 4 Scout | Free tier, real image reading, no extra SDK |
| Vector DB | ChromaDB in-process | Zero infra, no Docker, hyper-minimalism |
| Embeddings | SHA256 hash | No network downloads, no ONNX model fetching |
| RFI RAG strategy | Full-context injection | Hash embeddings not semantic; Groq 131K handles full docs |
| Agent pattern | Orchestrator + 5 specialists | Incremental testability, clean separation |
| UI | Streamlit | 15% UX score, fast to build, judge-friendly |
| Fallbacks | Deterministic hardcoded | Zero tolerance for errors in EPC context |

---

## Issues Fixed During Build

| Error | Root Cause | Fix |
|-------|-----------|-----|
| `AttributeError: GEMINI_API_KEY` | ui/app.py not updated after migration | Updated all references to GROQ_API_KEY |
| `httpx.ConnectError` in ChromaDB upsert | ChromaDB trying to download ONNX model | Replaced with LocalHashEmbedding (pure Python, no network) |
| `TypeError: proxies` in Groq client | groq==0.10.0 incompatible with httpx | Upgraded to groq==1.5.0 |
| `AttributeError: _gemini` in agents | Missed references after Gemini→Groq migration | Fixed in supply_chain.py and commissioning_qa.py |
| RFI agent says "not enough context" | Hash embeddings not semantic, wrong chunks retrieved | Switched to full-context injection into Groq |
| Orchestrator shows raw JSON | No rendering logic for agent results | Added per-agent readable renderer in sidebar |
| Drawing upload does nothing | No vision support | Added Llama 4 Scout vision with base64 encoding |

---

## Synthetic Data Summary

| Dataset | Records | Notable |
|---------|---------|---------|
| procurement_items.csv | 50 items | 4 deliberate deviations (UPS kVA, Chiller RT, Switch port, Battery Ah) |
| project_schedule.json | 15 tasks | 2 critical path violations (Generator delivery, LV switchboard) |
| supplier_locations.json | 10 suppliers | 2 at-risk (ETA < 7 days) |
| rfis.json | 20 RFIs | Mix of OPEN/CLOSED, covering power, cooling, civil, network |
| tia942_excerpts.txt | Standards | TIA-942-B Rating 3/4 requirements |
| uptime_tier_concepts.txt | Standards | Uptime Institute Tier III/IV concepts |

---

## Judging Criteria Alignment

| Criteria | Weight | How addressed |
|----------|--------|---------------|
| Innovation | 25% | Multi-agent + vision + full-context RAG strategy |
| Business Impact | 25% | Directly addresses 67% schedule overrun problem; measurable NCR detection |
| Technical Excellence | 20% | Deterministic fallbacks, retry logic, singleton pattern, clean separation |
| Scalability | 15% | Modular agents, ChromaDB persistent, Groq 131K context for real specs |
| User Experience | 15% | Streamlit 5-tab dashboard, clean text symbols, readable orchestrator output |

---

## How to Run

```bash
cd epc-intelligence
pip install -r requirements.txt
# Add GROQ_API_KEY to .env
python -m streamlit run ui/app.py
# Open http://localhost:8501
```

---

## How to Deploy (Streamlit Cloud)

1. Push repo to GitHub (`.env` is gitignored — safe)
2. Go to share.streamlit.io
3. New app → select repo → Main file: `ui/app.py`
4. Advanced settings → Secrets → add:
```toml
GROQ_API_KEY = "your_key_here"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
```
5. Deploy → get public URL

---

## Requirements

```
groq==1.5.0
chromadb==0.6.3
pypdf==4.2.0
streamlit==1.41.0
python-dotenv==1.0.1
```

---

*Built for ET AI Hackathon 2026 — AI Intelligence Platform for Data Centre EPC Project Delivery*

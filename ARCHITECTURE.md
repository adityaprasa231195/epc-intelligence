# Architecture — EPC Intelligence Platform

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT UI  (ui/app.py)                    │
│                                                                     │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐  ┌───────┐  │
│  │ Compliance │  │ Schedule │  │  Supply  │  │ QA   │  │  RFI  │  │
│  │    Tab     │  │  Risk    │  │  Chain   │  │Copil │  │ Chat  │  │
│  └─────┬──────┘  └────┬─────┘  └────┬─────┘  └──┬───┘  └───┬───┘  │
│        │              │             │            │          │       │
│  ┌─────┴──────────────┴─────────────┴────────────┴──────────┴─────┐ │
│  │               ORCHESTRATOR  (sidebar)                          │ │
│  │  Keyword match → agent key  OR  Groq classify → agent key      │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
         │              │             │            │          │
         ▼              ▼             ▼            ▼          ▼
┌──────────────┐ ┌──────────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐
│    Spec      │ │   Schedule   │ │  Supply  │ │Commiss- │ │  RFI   │
│ Compliance   │ │    Risk      │ │  Chain   │ │ioning   │ │  Know- │
│   Agent      │ │   Engine     │ │  Agent   │ │  QA     │ │ ledge  │
│              │ │              │ │          │ │Copilot  │ │ Agent  │
└──────┬───────┘ └──────┬───────┘ └────┬─────┘ └────┬────┘ └───┬────┘
       │                │              │             │          │
       └────────────────┴──────────────┴─────────────┴──────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
             ┌──────▼──────┐                    ┌─────────▼────────┐
             │  GroqClient │                    │    RAG Engine    │
             │  (lazy init)│                    │  (pure Python    │
             │             │                    │  in-memory store)│
             │  llama-3.3- │                    │                  │
             │  70b-vers.  │                    │  keyword search  │
             └──────┬──────┘                    └─────────┬────────┘
                    │                                     │
                    ▼                                     ▼
             ┌─────────────┐                    ┌─────────────────┐
             │  Groq API   │                    │   data/         │
             │  (external) │                    │   standards/    │
             └─────────────┘                    │   synthetic/    │
                                                └─────────────────┘
```

---

## Agent Design

Each agent follows the same pattern:

```
Agent.__init__(rag)
  └── lazy-load data from data/synthetic/*.json
  └── store GroqClient reference (not initialised yet)

Agent.method()
  └── load synthetic/real data
  └── deterministic logic first (no LLM)
  └── if LLM needed: GroqClient.generate(prompt)
        └── if Groq fails: return fallback data
  └── return typed result dict
```

No agent makes an LLM call at startup. All Groq calls happen only when the user clicks a button or submits a query.

---

## Data Flow — Compliance Check

```
spec_requirements.json ──┐
                          ├──► SpecComplianceAgent.check_all()
vendor_submittals.json ───┘         │
                                    │  deterministic comparison
                                    │  (spec value vs submitted value)
                                    ▼
                           deviations list + NCR log
                                    │
                          if drawing uploaded:
                                    │
                           base64(image) ──► Groq Llama 4 Scout
                                              (vision API)
                                                    │
                                                    ▼
                                           drawing_review text
```

---

## Data Flow — Schedule Risk

```
project_schedule.json ──► ScheduleRiskEngine.analyse()
                                    │
                          for each task:
                            planned_end vs actual_start + lead_time
                            delay_days = actual - planned
                            risk_score = delay * criticality_weight
                                    │
                          critical_path_violations (delay > threshold)
                                    │
                          if skip_mitigations=False:
                            for each violation:
                              Groq.generate(mitigation_prompt)
                                    │
                                    ▼
                           ScheduleReport(overall_risk, violations, mitigations)
```

---

## Data Flow — RFI Query

```
user question
      │
      ▼
RFIKnowledgeAgent.query()
      │
      ├── load all standards text (tia942_excerpts.txt + uptime_tier_concepts.txt)
      │
      ├── load all RFI records (rfis.json)
      │
      ├── build context block (standards + RFIs, injected directly into prompt)
      │   (We inject full docs into Groq's 131K context window
      │    instead of relying on vector similarity — more reliable
      │    for exact spec lookups)
      │
      ├── Groq.generate(context + question)
      │         │
      │         ├── success → answer with [SOURCE: ...] citations
      │         └── fail → keyword_fallback() against RFI index
      │
      └── _find_similar_rfis_by_keyword()
            └── keyword overlap against closed RFIs
            └── return top 3 similar resolved RFIs
```

---

## Data Flow — Commissioning QA

```
user selects system type (power / cooling / network / fire)
      │
      ▼
CommissioningQACopilot.get_test_sequence(system)
      │
      ├── RAG.query("commissioning test sequence {system}")
      │         │
      │         ├── score > 0.3 → Groq formats into structured checklist
      │         └── score ≤ 0.3 → hardcoded fallback checklist (TIA-942 based)
      │
      ▼
checklist: [{step, description, acceptance, source}]
      │
for each step, user enters measured value:
      │
      ▼
validate_test_result(description, measured, acceptance)
      │
      ├── extract number from measured string
      ├── parse operator from acceptance criteria (< > range)
      ├── deterministic comparison → PASS / FAIL
      └── keyword check (pass/fail/confirmed) → PASS / FAIL / MANUAL_REVIEW
      │
      ▼
generate_test_record() → TestRecord dataclass
      │
format_test_record_text() → Groq formats into professional document
      │
download_button → .txt file
```

---

## Orchestrator Routing

```
user query (free text)
      │
      ▼
_keyword_classify(query)
      │
      ├── score keywords for each of 5 agents
      │   (compliance, schedule, supply_chain, commissioning, rfi)
      │
      ├── best score > 0 → return agent key  (method: "keyword")
      │
      └── all scores = 0 → _gemini_classify(query)
                              │
                              └── Groq: "classify into one of 5 categories"
                              └── return agent key  (method: "groq")
      │
      ▼
_dispatch(agent_key, agent, query)
      │
      └── calls the right method on the right agent
      └── returns structured result dict
      │
      ▼
_render_orchestrator_result()
      └── formats result as natural language in sidebar
```

---

## Why Pure Python RAG (No ChromaDB)

ChromaDB installs `hnswlib` which is a C++ library. On Streamlit Cloud's Linux container, the C++ extension triggers a segfault at process spawn time — before any app code runs. We replaced ChromaDB with a plain Python list + keyword overlap scoring.

The tradeoff is that retrieval is less semantically precise. We compensate for this in the RFI agent by injecting full document context directly into Groq's 131K token context window instead of relying on similarity search. For the commissioning agent, hardcoded fallback checklists ensure correctness regardless of retrieval quality.

---

## Configuration

```
config.py
  └── _get(key) → os.environ → st.secrets → default
  └── GROQ_API_KEY
  └── GROQ_TEXT_MODEL  (default: llama-3.3-70b-versatile)
  └── RAG_CHUNK_SIZE   (512 tokens)
  └── RAG_CHUNK_OVERLAP (64 tokens)
  └── RAG_TOP_K        (5 results)
  └── RISK_THRESHOLD_DAYS (7 days)
  └── paths: BASE_DIR / DATA_DIR / SYNTHETIC_DIR / STANDARDS_DIR
```

---

## Dependency Graph

```
ui/app.py
  └── config
  └── agents/orchestrator       ← agents/spec_compliance
  └── agents/spec_compliance    │   agents/schedule_risk
  └── agents/schedule_risk      │   agents/supply_chain
  └── agents/supply_chain       │   agents/commissioning_qa
  └── agents/commissioning_qa   │   agents/rfi_knowledge
  └── agents/rfi_knowledge      │
                                └── core/groq_client
                                └── rag/rag_engine
```

No circular imports. Each agent only imports from `core/` and `rag/`. The orchestrator imports agents lazily inside `_build_agent()` to avoid circular dependency at module load time.

---

## Streamlit State Management

The app uses `st.session_state` and `st.cache_resource` to prevent redundant computation:

```
st.cache_resource → init_platform()
  └── agents dict (loaded once per session, not per rerun)
  └── RAGEngine with ingested standards

st.session_state["project_stats"]    ← computed once on first sidebar render
st.session_state["compliance_report"] ← computed once, reused across tabs
st.session_state["schedule_report"]   ← computed once, reused across tabs
st.session_state["checklist"]         ← commissioning checklist for current session
st.session_state["test_results"]      ← per-step results dict
st.session_state["test_record_doc"]   ← generated document text (persists download button)
st.session_state["drawing_review"]    ← vision analysis result (persists download button)
st.session_state["rfi_history"]       ← chat message history
```

Download buttons use session state keys so they survive Streamlit reruns. Without this, the download button disappears after the first click.

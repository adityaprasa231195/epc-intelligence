# EPC Intelligence Platform

AI-powered project intelligence system for data centre construction. Built for the ET AI Hackathon 2026.

---

## What it does

Data centre EPC projects are notoriously hard to manage. A single hyperscale facility involves tens of thousands of equipment line items, hundreds of contractors, and commissioning sequences that span every major system — power, cooling, network, fire. When something slips through the cracks it is expensive, and when it fails during commissioning it can cost weeks.

This platform puts an AI layer over all of that. It connects project specs, procurement records, schedules, supply chain data, and commissioning standards into one place, and lets engineers query everything in plain English.

There are five core agents:

- **Specification & Quality Compliance** — checks procurement orders and vendor submittals against your spec and raises NCRs automatically
- **Schedule Risk Engine** — analyses your project schedule for critical path violations and generates mitigation options via Groq
- **Supply Chain Visibility** — tracks all equipment shipments, flags at-risk deliveries, and suggests alternative suppliers
- **Commissioning QA Copilot** — walks engineers through TIA-942 and Uptime Institute Tier III test sequences, validates measured values against acceptance criteria, and generates formal test records
- **RFI Intelligence** — RAG-powered chat over all project RFIs and standards documents with citations

There is also an Orchestrator that sits in the sidebar. You ask it anything, and it routes your question to the right agent automatically — either by keyword matching or by asking the LLM to classify.

---

## Tech stack

| Layer | What we used |
|---|---|
| LLM | Groq (llama-3.3-70b-versatile, free tier) |
| RAG | Pure Python in-memory keyword store (no ChromaDB) |
| Vision | Groq Llama 4 Scout via base64 image input |
| UI | Streamlit 1.32.0 |
| PDF parsing | pypdf 4.3.1 |
| Config | python-dotenv |

We deliberately kept the dependency list minimal. No vector databases, no heavy ML frameworks, no native C extensions. The entire requirements.txt is four packages. This was intentional — Streamlit Cloud's free tier has a 1GB RAM limit and kills processes that exceed it.

---

## Project structure

```
epc-intelligence/
├── agents/
│   ├── commissioning_qa.py    # TIA-942 test sequences, result validation, test records
│   ├── orchestrator.py        # Query routing — keyword-first, Groq fallback
│   ├── rfi_knowledge.py       # RAG chat over RFIs and standards
│   ├── schedule_risk.py       # CPM-based schedule analysis + Groq mitigations
│   ├── spec_compliance.py     # Procurement compliance checker + NCR log
│   └── supply_chain.py        # Shipment tracking + alternative supplier lookup
├── core/
│   └── groq_client.py         # Lazy-init Groq wrapper with deterministic fallback
├── data/
│   ├── standards/             # TIA-942 excerpts, Uptime Institute Tier concepts
│   └── synthetic/             # rfis.json, equipment.json, schedule.json, suppliers.json
├── rag/
│   └── rag_engine.py          # Pure Python in-memory RAG (no external deps)
├── ui/
│   └── app.py                 # Streamlit app — all five tabs + orchestrator sidebar
├── .streamlit/
│   └── config.toml            # Streamlit server config
├── config.py                  # Central config — reads from .env or Streamlit secrets
└── requirements.txt
```

---

## Running locally

**Requirements:** Python 3.11, a free Groq API key from [console.groq.com](https://console.groq.com)

```bash
git clone https://github.com/adityaprasa231195/epc-intelligence.git
cd epc-intelligence

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your GROQ_API_KEY

streamlit run ui/app.py
```

Open `http://localhost:8501` in your browser.

---

## Deploying to Streamlit Cloud

1. Fork or push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and create a new app
3. Set main file path to `ui/app.py`
4. Under **Advanced settings**, select **Python 3.11** (important — Python 3.14 causes crashes)
5. Under **Secrets**, add:

```toml
GROQ_API_KEY = "your_groq_api_key_here"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
```

6. Deploy

The app loads in under 30 seconds on a cold start.

---

## Testing the deployed app

Once it is live, here are the queries to test each feature:

**Orchestrator sidebar (routes automatically):**
- `Is the UPS delivery going to make the installation window?` → routes to Supply Chain
- `What are the critical path delays on this project?` → routes to Schedule
- `Are there any non-conformances on the generator spec?` → routes to Compliance
- `What does TIA-942 say about earthing resistance?` → routes to RFI

**Compliance tab:**
- NCR table should show 4 open NCRs
- Upload any PNG/JPG → Llama 4 Scout vision analysis appears

**Schedule tab:**
- Risk level shows HIGH
- Click Generate Mitigations on any critical task → 3 options from Groq

**Supply Chain tab:**
- Click Find Alternative Suppliers on any at-risk item

**Commissioning tab:**
- Select power → Load Test Sequence
- Enter `0.5 ohm` in Step 1 → auto-validates as PASS
- Enter `50 MΩ` in Step 2 → auto-validates as FAIL (needs >100)
- Fill tester name → Generate Test Record → Download

**RFI Intelligence tab:**
- `What is the UPS battery autonomy requirement for Tier III?`
- `Generator start time requirement for ATS transfer?`
- `What does TIA-942 say about earthing resistance?`

---

## Groq free tier limits

Groq's free tier has no daily token quota — it is rate-limited at ~30 requests/minute. For a hackathon demo this is more than enough. If you hit a rate limit the app falls back gracefully to pre-computed data rather than crashing.

---

## Judging criteria alignment

| Criteria | What we built |
|---|---|
| Innovation | Multi-agent orchestration with keyword + LLM routing |
| Business Impact | Addresses the 67% schedule overrun problem in APAC EPC projects |
| Technical Excellence | Lazy imports, session state, pure Python RAG — no unnecessary deps |
| Scalability | Swap in-memory store for ChromaDB/Pinecone with one file change |
| User Experience | Tab-based UI with one-click queries, download buttons, auto-validation |

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | Get free at console.groq.com |
| `GROQ_TEXT_MODEL` | No | `llama-3.3-70b-versatile` | Any Groq-supported model |

---

## License

MIT

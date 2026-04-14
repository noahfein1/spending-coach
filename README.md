# 💰 Spending Coach

An AI-powered personal finance coach that categorizes bank transactions,
detects overspending against your own budgets, and generates plain-English
weekly summaries — 100% locally, with zero financial data leaving your machine.

## Why I built this
Most budgeting apps either require linking your bank account (privacy risk)
or manual entry (tedious). This app takes a CSV export from any bank and
runs all AI processing locally using Ollama + Llama 3.2.

## Features
- **Universal CSV ingestion** — works with Wells Fargo, Chase, BoA, or any bank
- **Local LLM categorization** — Llama 3.2 via Ollama classifies merchant names
- **Smart caching** — LLM only runs on new merchants, repeat runs are instant
- **User-defined budgets** — compare against your goals, not your habits
- **Prorated budget comparison** — fair comparison regardless of date range uploaded
- **Anomaly detection** — Isolation Forest flags unusually large transactions
- **Transfer filtering** — strips Venmo, Zelle, and bank transfers automatically
- **Category correction** — fix miscategorized merchants, cached permanently

## Stack
Python · Ollama (Llama 3.2) · LangChain · Pandas · Scikit-learn · Plotly · Streamlit

## Setup

### Prerequisites
- Python 3.9+
- [Ollama](https://ollama.com) installed and running

```bash
ollama pull llama3.2
```

### Install
```bash
git clone https://github.com/noahfein1/spending-coach.git
cd spending-coach
pip install -r requirements.txt
streamlit run app.py
```

### Usage
1. Export transactions from your bank as CSV
2. Upload in the sidebar
3. Set your monthly budgets on first run
4. Ask questions about your spending

## Architecture
CSV Upload → ingest.py (clean + filter transfers)
→ categorize.py (Llama 3.2 via Ollama + JSON cache)
→ analyze.py (budget comparison + Isolation Forest)
→ app.py (Streamlit dashboard + Plotly charts)

## Privacy
No data is sent to any external API. The only network calls are to your
local Ollama server (127.0.0.1). Your transactions never leave your machine.

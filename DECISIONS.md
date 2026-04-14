# Technical Decisions

This document explains the key architectural choices made in this project
and the reasoning behind each one. Written for anyone reviewing the codebase
— including future me.

---

## 1. Local LLM (Ollama + Llama 3.2) over OpenAI API

**Decision:** Use a locally-running Llama 3.2 model via Ollama instead of
calling the OpenAI API for transaction categorization.

**Why:** This app processes personal financial data — merchant names, spending
amounts, and transaction dates. Sending that data to a third-party API
introduces unnecessary privacy risk. With Ollama, the model runs entirely
on the user's machine. Nothing leaves the local environment.

**Tradeoff:** Llama 3.2 is less accurate than GPT-4o-mini on ambiguous
merchant names (e.g. "CPP*PINE ORCHARD" is harder to classify). We mitigate
this with a manual correction layer that caches user overrides permanently.
For a finance app, privacy > marginal accuracy improvement.

---

## 2. JSON cache for LLM categorization

**Decision:** After the LLM categorizes a merchant, the result is saved to
`category_cache.json`. Subsequent runs skip the LLM for known merchants.

**Why:** Calling a local LLM for every transaction on every run would make
the app unusably slow on real data (91 transactions × ~2s each = 3 minutes).
In practice, most months reuse the same 20-30 merchants. After the first run,
categorization is near-instant.

**Tradeoff:** Cache can become stale if a merchant changes category (rare).
User can clear `category_cache.json` to force a full re-categorization.

---

## 3. User-defined budgets with proration over rolling baselines

**Decision:** Compare actual spending against user-set monthly budgets
(prorated to the date range of the uploaded CSV) rather than against the
user's own historical average.

**Why:** A rolling baseline learns from your habits — including bad ones.
If you consistently overspend on food, your baseline rises to match, and
the alert never fires. A fixed budget reflects your *intention*, not your
history. Proration ensures fairness: if you upload 15 days of data, the
budget is halved so you're not flagged for "only spending $150 of a $300
food budget" mid-month.

**Tradeoff:** Requires user input upfront. We provide sensible defaults
so the app is immediately useful without configuration.

---

## 4. Isolation Forest for anomaly detection

**Decision:** Use Scikit-learn's Isolation Forest to flag individual
transactions that are unusually large within their category.

**Why:** Isolation Forest works by randomly partitioning data points —
anomalies (outliers) get isolated in fewer splits and receive lower scores.
It handles small, non-normal distributions well, which is important here
since some categories may only have 5-10 transactions. A simple z-score
approach would require normally distributed data and break on small samples.

**Tradeoff:** Requires minimum 5 transactions per category to fit a
meaningful model. Categories with fewer transactions skip anomaly detection.
The 10% contamination parameter assumes roughly 1-in-10 transactions is
anomalous — tunable based on user preference.

---

## 5. Fuzzy column detection over hardcoded bank formats

**Decision:** Infer CSV structure by inspecting column names and cell values
rather than maintaining a lookup table of known bank formats.

**Why:** There are hundreds of bank CSV formats. Hardcoding Chase, BoA,
and Wells Fargo covers maybe 40% of users. The fuzzy matcher looks for
columns containing "date", "amount", "description" (and variants) in any
order, and separately detects whether the file has headers at all. This
handles any bank without code changes.

**Tradeoff:** Can misfire on unusual formats. We log which columns were
detected so users can debug edge cases.

---

## 6. Transfer and noise filtering in ingestion

**Decision:** Strip transactions matching known transfer/payment keywords
(VENMO, ZELLE, TRANSFER, etc.) before any analysis runs.

**Why:** Bank CSVs include money movements between accounts — tuition
payments, rent transfers, Venmo settlements — that are not discretionary
spending. Including them inflates category totals and makes budget
comparisons meaningless. A $18,000 tuition transfer is not a "shopping"
expense.

**Tradeoff:** Overly aggressive filtering could remove legitimate expenses.
Keywords were chosen conservatively to only match clear transfer patterns.
Users can inspect the raw transaction count vs loaded count to verify.

---

## 7. Streamlit for the dashboard

**Decision:** Use Streamlit rather than a full React/Flask web app.

**Why:** This is a personal tool meant to be run locally. Streamlit provides
interactive UI, file upload, session state, and Plotly chart rendering with
minimal boilerplate. A React frontend would add significant complexity
(separate backend API, build tooling, deployment) for no benefit in a
single-user local app.

**Tradeoff:** Streamlit is not suitable for multi-user production deployment.
If this were to scale beyond personal use, a proper frontend/backend
separation would be needed.
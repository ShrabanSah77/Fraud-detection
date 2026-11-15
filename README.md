# AML Shield 3.0 — IBM AML Investigation Platform

An offline academic full-stack application built from the uploaded IBM HI-Small dataset. **No Flask, Node, or npm needed** to run the interface: Python standard-library HTTP server + SQLite backend + JavaScript frontend. Scikit-learn is needed only for optional retraining.

## Quick start (Windows)

1. Extract the ZIP.
2. Open a terminal inside `AML_Shield_3`.
3. Run `py app.py` (or `python app.py`).
4. Open http://localhost:8000

The ZIP includes the prepared SQLite database and two fitted model files, so initial setup requires no pip installations. It also includes the HI-Small account metadata and pattern annotations. The full 454 MB transaction CSV is **not duplicated** in the ZIP; the prepared database is included instead.

## Pages

- **Overview:** counts from all 5,078,345 transactions; indexed sample timeline; recent synthetic laundering labels; investigation workload.
- **AML Alerts:** searchable/paginated transaction queue, labeled or normal transaction filter.
- **Transaction details:** actual account transfer details, descriptive risk indicators, related indexed transfers and a network graph.
- **Investigations:** persistent SQLite cases, analyst assignment, priority, notes, status and audit log.
- **Model Lab:** held-out sampled-pool results for Logistic Regression and Random Forest; actual confusion matrices.

## Rebuild from full transaction CSV (optional)

Install: `py -m pip install -r requirements-train.txt`

Place `HI-Small_Trans.csv` inside `data/`, then run `py prepare.py`. This **replaces** the database and deletes existing cases. Alternatively set the `AML_TRANSACTIONS` environment variable to its path. It can take a few minutes.

## Dataset and methodological honesty

- Source: IBM synthetic AML HI-Small transaction dataset, not real customer data.
- Full file: **5,078,345 transactions**, **5,177 labeled laundering**. Full-file counts are computed during ingestion.
- Indexed SQLite subset: **96,242 transactions**, retaining all 5,177 positive labels and a deterministic sample of negatives. Indexed charts and queues are explicitly labeled as sampled.
- ML training pool: approximately 2,500 negative rows per 100,000-row chunk plus all positives. A 25% stratified holdout is used. Therefore the evaluation prevalence is **artificially enriched** and measured AUPRC/precision do not reflect performance at the original base rate. Use these only as exploratory classroom model comparisons.
- A random transaction-level split can share accounts between train and test. Future improvement: temporal split, account-disjoint validation, and scoring all transactions out-of-sample.
- Network graph is only the **indexed one-hop neighborhood**; it is not a verified complete laundering cycle or proven layering scheme.
- Nominal values across currencies are not comparable without FX conversion. Large nominal payment indicators are descriptive, not standardized AML thresholds.
- Pattern text files provide synthetic laundering scenario annotations; they are included as reference data but **not yet parsed into an authoritative pattern-matching graph**.
- Two models are actually fitted: Logistic Regression and Random Forest. No XGBoost or SMOTE results are claimed.
- This is a **local classroom demonstration**, not a production AML platform. It has no authentication or access control. Do not expose it to the public internet or use real banking/customer information.

## API

GET `/api/overview`, `/api/transactions?label=1&page=1&search=...`, `/api/transaction/{id}`, `/api/cases`, `/api/case/{id}`, `/api/health`.

POST `/api/cases` with `{"transaction_id":123}`, POST `/api/case/{id}` with `{"status":"Investigating","priority":"High","assignee":"Analyst","notes":"..."}`.

## Future research improvements

1. Account-level graph feature engineering and time-respecting detection of fan-in, fan-out, cycles and gather-scatter patterns.
2. Test on the original full class prevalence and evaluate precision at fixed investigation capacity.
3. Compare XGBoost, weighted trees and SMOTE fitted strictly on training folds.
4. Explain individual ML scores using feature contributions and calibration.
5. Authentication, immutable audit trail, privacy controls, and role-based access for a real-world deployment.

## Backend-integrated transaction streaming simulator

Open **Live Simulator** in the left navigation. Start replay to send five historical indexed HI-Small transactions per HTTP request to `POST /api/stream/control` every 1.5 seconds. Each request executes `best_model.joblib` inference, applies illustrative AML risk rules, persists results in SQLite `stream_events`, and returns new events for the UI. Pause, single-step, and reset controls are provided. The state persists across page refreshes; streaming is browser-driven and pauses if the page is closed. API endpoints: `GET /api/stream`, `POST /api/stream/control` with `{ "action": "start" | "pause" | "step" | "reset", "batch": 5 }`. Start before step.

**Important limitations:** This is replay of the previously indexed case-enriched HI-Small subset (96,242 records), not the entire 5.08-million-row CSV or a connected bank. Ground-truth laundering labels are used only for post-prediction comparison, not model features or rule scoring. The ML score is uncalibrated, the risk formula is illustrative, and nominal values in different currencies are not converted. Rules are transaction-level, not validated multi-hop network detection. No authenticated banking integration, message broker, or regulatory SAR submission is implemented. For a production system use event streaming, event-time state, deduplication, authentication, audit security, model calibration, and bank-specific validation.

**Live demo:** Start server with `python app.py`, open `http://localhost:8000`, select Live Simulator, press Start replay, watch processed/alerts counters and event table, pause and click Investigate on a transaction, then open a case. For deterministic explanation, use One transaction to advance manually.

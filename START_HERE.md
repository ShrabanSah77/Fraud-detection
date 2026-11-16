# AML Shield — Six-Part University Demo

## Requirements
Python 3.10+; pip install -r requirements-train.txt (pandas, scikit-learn, joblib, numpy). This bundle includes an existing indexed SQLite database and fitted models from the supplied project; **no training is required to run the demo**.

## Run (Windows PowerShell)
```powershell
cd AML_Shield_Complete_Demo
python -m pip install -r requirements-train.txt
python -m py_compile app.py
python app.py
```
Open http://127.0.0.1:8000. Stop with Ctrl+C.

## Presentation sequence
1. Overview: dataset totals vs indexed subset; labeled cases are synthetic ground truth.
2. Live Simulator: Start replay; the browser repeatedly calls POST /api/stream/control and backend runs saved model inference on historical indexed records.
3. AML Alerts: investigate labeled transactions. Labels are NOT model alerts. Streaming risk alerts are separately visible in Live Simulator.
4. Network Analysis: enter an account ID (or open a transaction and select Analyze sender network). See actual indexed edges and exploratory fan-in/fan-out/cycles.
5. Investigations: open a case, assign analyst, save status, priority, notes; SQLite audit trail.
6. Model Lab: display measured Logistic Regression and Random Forest metrics stored in metadata. Case-enriched random split; not deployment performance.

## Limitations
Not connected to real bank data. Account patterns cover indexed/sampled records, not full transaction history. A directed three-account cycle is a candidate topological cycle only; no chronological or value matching is asserted. Classifier probabilities are not calibrated. No XGBoost training or temporal evaluation is claimed.

## Files
app.py backend; static/index.html, app.js, style.css frontend; data/aml.db indexed database; data/*.joblib fitted models; prepare.py optional re-preparation script (requires original source data).

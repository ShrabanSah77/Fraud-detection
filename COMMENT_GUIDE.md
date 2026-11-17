# AML Shield — Code walkthrough

This copy adds comments for teaching and presentation. All executable statements in the source files are unchanged.

- `prepare.py`: loads IBM HI-Small CSV chunks, selects an indexed subset, creates features, trains Logistic Regression and Random Forest, and evaluates on a case-enriched sample. **Running this script rebuilds the database**; do not rerun unless you intend to regenerate it.
- `app.py`: serves APIs, reads SQLite, scores historical replay transactions using the saved model, applies illustrative risk rules, queries account networks, and saves investigation cases.
- `static/app.js`: handles navigation, fetches APIs, draws charts/networks, and submits investigation changes.
- `static/index.html`: defines the sidebar, heading, content region, and script inclusion.
- `static/style.css`: controls visual design and responsive layout.
- `data/*.db` and `data/*.joblib`: existing database and model files, not source code; comments cannot be embedded in binary files.
- `requirements-train.txt`: Python package dependencies.

**Caution:** Synthetic laundering labels are dataset annotations; alerts and graph indicators do not prove real-world criminal activity.

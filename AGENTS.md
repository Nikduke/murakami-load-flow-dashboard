# Instructions for future changes

- Treat supplied PowerFactory CSVs and project archives as engineering source data. Do not edit, commit, or copy proprietary examples into this repository.
- Keep parsing, token filtering, semantic channel discovery and Plotly construction independent of Streamlit. Keep `app.py` focused on UI and orchestration.
- Match channels by object name and exact metric description; preserve source column positions, case tokens, sweep indices and numeric precision. Do not infer object classes from arbitrary name fragments.
- Preserve the specified X/Y pair and sign for each chart. Do not label the POC spectrum as THD or make compliance conclusions.
- Add focused synthetic tests for changes and real-export regressions when relevant. Run `python -m pytest tests -q` in `.venv` and record what was actually checked.
- Update `docs/APP_REFERENCE.md`, `docs/VALIDATION.md`, and related user/data documents when behaviour changes.
- Keep local inputs, uploads, credentials, generated chart exports and `.venv` out of Git.
- Use British English in application and documentation text.

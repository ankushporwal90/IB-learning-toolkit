# AI SEC Filing + Earnings Call Analyzer

Production-style learning project for SEC filing, earnings call, and investor presentation analysis.

Start here:

- Phase 1 guide: `docs/PHASE_1_BEGINNER_MVP.md`
- Streamlit app: `app/main.py`

## Run Locally

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python -m streamlit run app\main.py
```

Add your Groq API key to `.env` before generating AI summaries.

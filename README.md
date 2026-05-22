# AI SEC Filing + Earnings Call Analyzer

Production-style learning project for SEC filing, earnings call, and investor presentation analysis.

Current scope:

- Upload a local filing PDF
- Fetch the latest SEC 10-K and 10-Q by ticker
- Choose which extracted document to summarize
- Generate a Groq-powered finance summary

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

Add your Groq API key and SEC user agent to `.env` before generating AI summaries:

```text
GROQ_API_KEY=your_groq_api_key_here
SEC_USER_AGENT=Your Name your.email@example.com
```

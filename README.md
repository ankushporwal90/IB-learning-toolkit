# AI SEC Filing + Earnings Call Analyzer

Production-style learning project for SEC filing, earnings call, and investor presentation analysis.

Current scope:

- Upload a local filing PDF
- Fetch the latest SEC 10-K and 10-Q by ticker
- Choose which extracted document to summarize
- Generate a Groq-powered finance summary
- Generate structured financial intelligence across revenue, risks, MD&A, metrics, tone, and insights
- Index filings into ChromaDB for RAG-based cited Q&A
- Generate RAG-powered financial intelligence with citations per finance section
- Use hybrid retrieval and revenue metric extraction for exact financial questions
- Use section-aware RAG and query routing for better filing retrieval
- Use SEC XBRL companyfacts for official financial metrics

Start here:

- Phase 1 guide: `docs/PHASE_1_BEGINNER_MVP.md`
- Phase 2 guide: `docs/PHASE_2_FINANCIAL_INTELLIGENCE.md`
- Phase 3 guide: `docs/PHASE_3_RAG_ARCHITECTURE.md`
- Phase 3.5 guide: `docs/PHASE_3_5_RAG_FINANCIAL_INTELLIGENCE.md`
- Phase 3.6 guide: `docs/PHASE_3_6_RAG_RETRIEVAL_QUALITY.md`
- Phase 3.7/3.8 guide: `docs/PHASE_3_7_3_8_SECTION_RAG_XBRL.md`
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

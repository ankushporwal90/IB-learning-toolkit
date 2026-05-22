"""Streamlit entrypoint for the AI SEC Filing Analyzer.

Run locally:
    streamlit run app/main.py
"""

import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.services.phase1_filing_summary import extract_pdf_text, summarize_filing
from src.services.sec_edgar_service import (
    fetch_latest_annual_and_quarterly_filings,
    filing_to_extraction,
)


def render_phase1_mvp() -> None:
    """Render the beginner SEC filing summarizer."""

    st.set_page_config(
        page_title="AI SEC Filing Analyzer",
        page_icon=":bar_chart:",
        layout="wide",
    )

    st.title("AI SEC Filing + Earnings Call Analyzer")
    st.caption(
        "Phase 1.5: upload a filing PDF or fetch the latest SEC 10-K and 10-Q, "
        "then generate a Groq summary."
    )

    st.warning(
        "Educational use only. This app summarizes source documents and does not provide "
        "investment advice."
    )

    with st.sidebar:
        st.header("Phase 1.5")
        st.write("Current scope:")
        st.write("- PDF upload")
        st.write("- Latest 10-K and 10-Q fetch")
        st.write("- Text extraction")
        st.write("- Groq summary")
        st.write("- No RAG yet")

    st.markdown("#### Why this phase matters")
    st.write(
        "Before adding RAG, memory, guardrails, or databases, we need one reliable "
        "end-to-end loop. In finance terms, this is the first version of an analyst "
        "reading a filing and producing a structured first-pass brief."
    )

    input_tab, sec_tab = st.tabs(["Upload PDF", "Fetch SEC Filings"])

    with input_tab:
        handle_pdf_upload()

    with sec_tab:
        handle_sec_fetch()

    render_available_documents()


def handle_pdf_upload() -> None:
    """Allow users to upload a local PDF filing."""

    uploaded_file = st.file_uploader(
        "Upload one SEC filing, annual report, or investor presentation PDF",
        type=["pdf"],
        accept_multiple_files=False,
    )

    if uploaded_file is None:
        st.info("Upload a PDF to extract text, or use the SEC tab to fetch filings by ticker.")
        return

    with st.spinner("Extracting text from the PDF..."):
        extraction = extract_pdf_text(
            pdf_bytes=uploaded_file.getvalue(),
            document_name=uploaded_file.name,
        )

    st.session_state.available_documents = {
        **st.session_state.get("available_documents", {}),
        f"Uploaded PDF: {uploaded_file.name}": extraction,
    }

    render_extraction_metrics(extraction)


def handle_sec_fetch() -> None:
    """Fetch and store both latest 10-K and latest 10-Q from SEC EDGAR."""

    st.write(
        "Enter a ticker. The app will fetch both the latest annual report and the latest "
        "quarterly report so you can choose which one to summarize."
    )
    ticker = st.text_input("Ticker", value=st.session_state.get("last_ticker", "AAPL"))

    if st.button("Fetch Latest 10-K and 10-Q", type="primary"):
        with st.spinner(f"Fetching latest 10-K and 10-Q for {ticker.upper()} from SEC EDGAR..."):
            try:
                filings = fetch_latest_annual_and_quarterly_filings(ticker)
            except Exception as exc:
                st.error(f"Could not fetch SEC filings: {exc}")
                return

        st.session_state.last_ticker = ticker.upper().strip()
        st.session_state.sec_filings = filings
        st.session_state.available_documents = {
            **st.session_state.get("available_documents", {}),
            **{
                f"SEC {form_type}: {filing.display_name}": filing_to_extraction(filing)
                for form_type, filing in filings.items()
            },
        }
        st.success(f"Fetched latest 10-K and 10-Q for {ticker.upper().strip()}.")

    filings = st.session_state.get("sec_filings", {})
    if filings:
        st.markdown("#### Fetched SEC Filings")
        for filing in filings.values():
            st.write(f"**{filing.display_name}**")
            st.link_button(f"Open {filing.form} on SEC", filing.filing_url)


def render_available_documents() -> None:
    """Let the user choose which extracted document Groq should summarize."""

    documents = st.session_state.get("available_documents", {})
    if not documents:
        return

    st.markdown("#### Choose Document for Summarization")
    selected_label = st.selectbox("Document", options=list(documents.keys()))
    extraction = documents[selected_label]

    metric_cols = st.columns(3)
    metric_cols[0].metric("PDF Pages", extraction.page_count)
    metric_cols[1].metric("Readable Pages", extraction.extracted_page_count)
    metric_cols[2].metric("Extracted Characters", f"{len(extraction.text):,}")

    if not extraction.text:
        st.error(
            "No readable text was found. Try another PDF, or use a text-based filing instead "
            "of a scanned document."
        )
        return

    with st.expander("Preview extracted text"):
        st.write(extraction.text[:3_000] + ("..." if len(extraction.text) > 3_000 else ""))

    if st.button("Generate Phase 1 Summary", type="primary"):
        with st.spinner("Asking Groq to summarize the filing..."):
            st.session_state.phase1_summary = summarize_filing(extraction)

    if st.session_state.get("phase1_summary"):
        st.markdown("#### AI Filing Summary")
        st.write(st.session_state.phase1_summary)


def render_extraction_metrics(extraction: object) -> None:
    """Show document extraction status immediately after upload."""

    metric_cols = st.columns(3)
    metric_cols[0].metric("Pages", extraction.page_count)
    metric_cols[1].metric("Readable Pages", extraction.extracted_page_count)
    metric_cols[2].metric("Characters", f"{len(extraction.text):,}")


if __name__ == "__main__":
    render_phase1_mvp()

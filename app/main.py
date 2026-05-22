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


def render_phase1_mvp() -> None:
    """Render the beginner SEC filing summarizer."""

    st.set_page_config(
        page_title="AI SEC Filing Analyzer",
        page_icon=":bar_chart:",
        layout="wide",
    )

    st.title("AI SEC Filing + Earnings Call Analyzer")
    st.caption("Phase 1: upload a filing PDF, extract text, and generate a Groq summary.")

    st.warning(
        "Educational use only. This app summarizes source documents and does not provide "
        "investment advice."
    )

    with st.sidebar:
        st.header("Phase 1")
        st.write("Current scope:")
        st.write("- PDF upload")
        st.write("- Text extraction")
        st.write("- Groq summary")
        st.write("- No RAG yet")

    st.markdown("#### Why this phase matters")
    st.write(
        "Before adding RAG, memory, guardrails, or databases, we need one reliable "
        "end-to-end loop. In finance terms, this is the first version of an analyst "
        "reading a filing and producing a structured first-pass brief."
    )

    uploaded_file = st.file_uploader(
        "Upload one SEC filing, annual report, or investor presentation PDF",
        type=["pdf"],
        accept_multiple_files=False,
    )

    if uploaded_file is None:
        st.info("Upload a PDF to extract text and generate the first AI summary.")
        return

    pdf_bytes = uploaded_file.getvalue()
    with st.spinner("Extracting text from the PDF..."):
        extraction = extract_pdf_text(pdf_bytes=pdf_bytes, document_name=uploaded_file.name)

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


if __name__ == "__main__":
    render_phase1_mvp()

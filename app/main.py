"""Streamlit entrypoint for the AI SEC Filing Analyzer.

Run locally:
    streamlit run app/main.py
"""

import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.services.financial_analysis_service import (
    FinancialAnalysisResult,
    analyze_financial_document,
)
from src.services.financial_metric_service import answer_metric_question
from src.services.xbrl_companyfacts_service import answer_xbrl_metric_question
from src.rag.pipeline import (
    RagPipeline,
    RetrievedChunk,
    answer_question_with_rag,
)
from src.services.rag_financial_analysis_service import (
    RagFinancialAnalysisResult,
    RagSectionAnalysis,
    analyze_financial_document_with_rag,
)
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
        "Phase 3.6: upload or fetch SEC filings, summarize, analyze, ask cited RAG questions, "
        "and answer exact finance metrics with hybrid retrieval."
    )

    st.warning(
        "Educational use only. This app summarizes source documents and does not provide "
        "investment advice."
    )

    with st.sidebar:
        st.header("Phase 3.6")
        st.write("Current scope:")
        st.write("- PDF upload")
        st.write("- Latest 10-K and 10-Q fetch")
        st.write("- Text extraction")
        st.write("- Groq summary")
        st.write("- Structured finance analysis")
        st.write("- ChromaDB RAG with citations")
        st.write("- RAG-powered finance tabs")
        st.write("- Hybrid retrieval for exact metrics")

    st.markdown("#### Why this phase matters")
    st.write(
        "Phase 3.6 improves retrieval quality for finance questions. It combines semantic "
        "search with keyword scoring and metric extraction, so questions like latest revenue "
        "can find filing terms such as total net sales."
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

    st.markdown("#### Choose Document for Analysis")
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

    action_cols = st.columns(4)
    if action_cols[0].button("Generate Phase 1 Summary", type="secondary"):
        with st.spinner("Asking Groq to summarize the filing..."):
            try:
                st.session_state.phase1_summary = summarize_filing(extraction)
            except Exception as exc:
                st.error(f"Could not generate summary: {type(exc).__name__}: {exc}")
                return

    if action_cols[1].button("Generate Phase 2 Financial Analysis", type="primary"):
        with st.spinner("Extracting structured financial intelligence..."):
            st.session_state.phase2_analysis = analyze_financial_document(extraction)

    if action_cols[2].button("Index for RAG", type="secondary"):
        with st.spinner("Chunking, embedding, and indexing the selected document..."):
            try:
                chunk_count = get_rag_pipeline().ingest_extraction(extraction)
            except Exception as exc:
                st.error(f"Could not index document for RAG: {type(exc).__name__}: {exc}")
                return
        st.session_state.last_indexed_document = extraction.document_name
        st.success(f"Indexed {chunk_count} chunks for retrieval.")

    if action_cols[3].button("Generate RAG Financial Intelligence", type="primary"):
        if st.session_state.get("last_indexed_document") != extraction.document_name:
            st.warning("Index the selected document for RAG before generating RAG financial intelligence.")
            return
        with st.spinner("Retrieving targeted filing evidence and generating cited finance tabs..."):
            try:
                st.session_state.rag_financial_analysis = analyze_financial_document_with_rag(
                    extraction=extraction,
                    rag_pipeline=get_rag_pipeline(),
                )
            except Exception as exc:
                st.error(f"Could not generate RAG financial intelligence: {type(exc).__name__}: {exc}")
                return

    result_tab, analysis_tab, rag_analysis_tab, rag_tab = st.tabs(
        ["Summary", "Financial Intelligence", "RAG Financial Intelligence", "RAG Q&A"]
    )

    with result_tab:
        if st.session_state.get("phase1_summary"):
            st.markdown("#### AI Filing Summary")
            st.write(st.session_state.phase1_summary)
        else:
            st.info("Generate a Phase 1 summary to see the narrative filing brief.")

    with analysis_tab:
        analysis = st.session_state.get("phase2_analysis")
        if analysis:
            render_financial_analysis(analysis)
        else:
            st.info("Generate Phase 2 financial analysis to see structured analyst outputs.")

    with rag_analysis_tab:
        rag_analysis = st.session_state.get("rag_financial_analysis")
        if rag_analysis:
            render_rag_financial_analysis(rag_analysis)
        else:
            st.info(
                "Click `Index for RAG`, then `Generate RAG Financial Intelligence` "
                "to see citation-backed finance tabs."
            )

    with rag_tab:
        render_rag_qa(selected_document_name=extraction.document_name)


def render_extraction_metrics(extraction: object) -> None:
    """Show document extraction status immediately after upload."""

    metric_cols = st.columns(3)
    metric_cols[0].metric("Pages", extraction.page_count)
    metric_cols[1].metric("Readable Pages", extraction.extracted_page_count)
    metric_cols[2].metric("Characters", f"{len(extraction.text):,}")


def render_financial_analysis(analysis: FinancialAnalysisResult) -> None:
    """Render Phase 2 structured financial analysis."""

    overview_tab, revenue_tab, risks_tab, mda_tab, metrics_tab, tone_tab, insights_tab = st.tabs(
        ["Overview", "Revenue", "Risks", "MD&A", "Metrics", "Tone", "Insights"]
    )

    with overview_tab:
        st.markdown("#### Business Overview")
        st.write(analysis.business_overview or "Not specified.")
        render_limitations(analysis)

    with revenue_tab:
        st.markdown("#### Revenue Drivers")
        render_bullets(analysis.revenue_drivers, "No revenue drivers were extracted.")

    with risks_tab:
        st.markdown("#### Risk Extraction")
        if not analysis.risks:
            st.info("No risks were extracted.")
        for risk in analysis.risks:
            st.write(f"**{risk.title}** | Severity: `{risk.severity}`")
            st.write(risk.description)

    with mda_tab:
        st.markdown("#### Management Discussion Themes")
        render_bullets(analysis.mda_themes, "No MD&A themes were extracted.")

    with metrics_tab:
        st.markdown("#### Key Metrics")
        if not analysis.key_metrics:
            st.info("No key metrics were extracted.")
        for metric in analysis.key_metrics:
            st.write(f"**{metric.name}:** {metric.value}")
            st.caption(metric.context)

    with tone_tab:
        st.markdown("#### Management Tone")
        tone_cols = st.columns(2)
        tone_cols[0].metric("Overall Tone", analysis.tone.overall_tone.title())
        tone_cols[1].metric("Confidence", analysis.tone.confidence.title())
        st.write(analysis.tone.explanation or "No tone explanation was provided.")

    with insights_tab:
        st.markdown("#### Investment Insights")
        render_bullets(analysis.investment_insights, "No investment insights were extracted.")
        if analysis.raw_response and analysis.limitations:
            with st.expander("Raw model response"):
                st.write(analysis.raw_response)


def render_bullets(items: list[str], empty_message: str) -> None:
    """Render a simple bullet list."""

    if not items:
        st.info(empty_message)
        return
    for item in items:
        st.write(f"- {item}")


def render_limitations(analysis: FinancialAnalysisResult) -> None:
    """Show analysis limitations to reduce overconfidence."""

    if not analysis.limitations:
        return
    st.markdown("#### Limitations")
    render_bullets(analysis.limitations, "No limitations were provided.")


def get_rag_pipeline() -> RagPipeline:
    """Create one RAG pipeline per Streamlit session."""

    if "rag_pipeline" not in st.session_state:
        st.session_state.rag_pipeline = RagPipeline()
    return st.session_state.rag_pipeline


def render_rag_qa(selected_document_name: str | None = None) -> None:
    """Render citation-aware RAG question answering."""

    rag_pipeline = get_rag_pipeline()
    st.markdown("#### Citation-Aware Filing Q&A")
    try:
        indexed_chunks = rag_pipeline.indexed_chunk_count()
    except Exception as exc:
        st.error(f"Could not read RAG index: {type(exc).__name__}: {exc}")
        if st.button("Reset RAG Connection"):
            reset_rag_session()
        return

    st.metric("Indexed Chunks", indexed_chunks)
    if st.button("Reset RAG Connection"):
        reset_rag_session()

    last_indexed = st.session_state.get("last_indexed_document")
    if last_indexed:
        st.caption(f"Latest indexed document: {last_indexed}")
    else:
        st.info("Click `Index for RAG` on a selected document before asking questions.")

    question = st.text_input(
        "Ask a question about the indexed filing",
        value="What are the most important risk factors discussed?",
    )

    if st.button("Ask with RAG", type="primary"):
        document_filter = selected_document_name if selected_document_name == last_indexed else last_indexed
        with st.spinner("Retrieving relevant chunks and generating a cited answer..."):
            try:
                xbrl_answer = None
                ticker = st.session_state.get("last_ticker")
                if ticker:
                    xbrl_answer = answer_xbrl_metric_question(ticker=ticker, question=question)
                chunks = rag_pipeline.retrieve_section_aware(
                    question,
                    top_k=8,
                    document_name=document_filter,
                )
                answer = xbrl_answer or answer_metric_question(question, chunks) or answer_question_with_rag(
                    question,
                    chunks,
                )
            except Exception as exc:
                st.error(f"RAG retrieval failed: {type(exc).__name__}: {exc}")
                return
        st.session_state.rag_answer = answer
        st.session_state.rag_sources = chunks

    if st.session_state.get("rag_answer"):
        st.markdown("#### Answer")
        st.write(st.session_state.rag_answer)
        render_rag_sources(st.session_state.get("rag_sources", []))


def render_rag_sources(chunks: list[RetrievedChunk]) -> None:
    """Display retrieved chunks as citations."""

    if not chunks:
        return
    st.markdown("#### Retrieved Sources")
    for index, chunk in enumerate(chunks, start=1):
        distance = f"{chunk.distance:.4f}" if chunk.distance is not None else "n/a"
        with st.expander(f"Source {index}: {chunk.citation} | distance {distance}"):
            st.write(chunk.text)


def reset_rag_session() -> None:
    """Reset Streamlit's RAG objects after a local Chroma runtime issue."""

    st.session_state.pop("rag_pipeline", None)
    st.session_state.pop("rag_answer", None)
    st.session_state.pop("rag_sources", None)
    st.session_state.pop("rag_financial_analysis", None)
    st.session_state.pop("last_indexed_document", None)
    st.success("RAG connection reset. Re-index the selected document if needed.")
    st.rerun()


def render_rag_financial_analysis(analysis: RagFinancialAnalysisResult) -> None:
    """Render Phase 3.5 citation-backed financial intelligence."""

    st.caption(f"RAG analysis for: {analysis.document_name}")
    overview_tab, revenue_tab, risks_tab, mda_tab, metrics_tab, tone_tab, insights_tab = st.tabs(
        ["Overview", "Revenue", "Risks", "MD&A", "Metrics", "Tone", "Insights"]
    )
    sections = [
        (overview_tab, analysis.business_overview),
        (revenue_tab, analysis.revenue),
        (risks_tab, analysis.risks),
        (mda_tab, analysis.mda),
        (metrics_tab, analysis.metrics),
        (tone_tab, analysis.tone),
        (insights_tab, analysis.insights),
    ]
    for tab, section in sections:
        with tab:
            render_rag_section_analysis(section)


def render_rag_section_analysis(section: RagSectionAnalysis) -> None:
    """Render one citation-backed finance section."""

    st.markdown(f"#### {section.title}")
    if section.limitations:
        render_bullets(section.limitations, "No limitations were provided.")

    if not section.findings:
        st.info("No cited findings were generated for this section.")
    for finding in section.findings:
        st.write(f"**{finding.finding}**")
        st.write(f"Evidence: {finding.evidence}")
        st.caption(
            f"Citation: {finding.citation} | Confidence: {finding.confidence} | "
            f"Finance relevance: {finding.finance_relevance}"
        )

    if section.sources:
        render_rag_sources(section.sources)


if __name__ == "__main__":
    render_phase1_mvp()

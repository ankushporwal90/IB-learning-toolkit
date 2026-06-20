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
from src.services.financial_statement_service import (
    FinancialStatementData,
    extract_financial_statement_data,
    financial_statement_data_to_markdown,
)
from src.services.ib_workflow_service import IbBrief, generate_ib_brief, ib_brief_to_markdown
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
from src.services.ir_document_service import discover_ir_pdf_links, download_ir_pdf
from src.services.phase1_filing_summary import extract_pdf_text, summarize_filing
from src.services.sec_edgar_service import (
    fetch_latest_annual_and_quarterly_filings,
    fetch_latest_earnings_8k,
    filing_to_extraction,
)
from src.storage.session_store import (
    AnalysisEvent,
    create_analysis_session,
    export_session_markdown,
    initialize_session_store,
    list_analysis_events,
    list_analysis_sessions,
    save_analysis_event,
)


ENERGY_COMPANIES = [
    {
        "name": "Diamondback Energy",
        "ticker": "FANG",
        "sector": "Upstream",
        "ir_url": "https://ir.diamondbackenergy.com/events-and-presentations",
    },
    {
        "name": "Permian Resources",
        "ticker": "PR",
        "sector": "Upstream",
        "ir_url": "https://www.permianres.com/investor-relations/events-presentations/default.aspx",
    },
    {
        "name": "Devon Energy",
        "ticker": "DVN",
        "sector": "Upstream",
        "ir_url": "https://investors.devonenergy.com/events-and-presentations/default.aspx",
    },
    {
        "name": "Exxon Mobil",
        "ticker": "XOM",
        "sector": "Integrated / Downstream",
        "ir_url": "https://investor.exxonmobil.com/news-events/events-presentations",
    },
    {
        "name": "Chevron",
        "ticker": "CVX",
        "sector": "Integrated / Downstream",
        "ir_url": "https://www.chevron.com/investors/events-presentations",
    },
    {
        "name": "Energy Transfer",
        "ticker": "ET",
        "sector": "Midstream",
        "ir_url": "https://ir.energytransfer.com/events-and-presentations",
    },
    {
        "name": "Kinder Morgan",
        "ticker": "KMI",
        "sector": "Midstream",
        "ir_url": "https://ir.kindermorgan.com/events-and-presentations",
    },
    {
        "name": "SLB",
        "ticker": "SLB",
        "sector": "Oilfield Services",
        "ir_url": "https://investorcenter.slb.com/news-releases/events-presentations",
    },
    {
        "name": "Halliburton",
        "ticker": "HAL",
        "sector": "Oilfield Services",
        "ir_url": "https://ir.halliburton.com/news-and-events/events-presentations",
    },
]

ENERGY_COMPANY_OPTIONS = [
    f"{company['name']} ({company['ticker']}) - {company['sector']}"
    for company in ENERGY_COMPANIES
]

ENERGY_REPORT_TYPES = [
    "Investor presentation",
    "Earnings presentation",
    "Acquisition press release",
    "Earnings press release (8-K)",
    "10-K",
    "10-Q",
]


def render_phase1_mvp() -> None:
    """Render the beginner SEC filing summarizer."""

    initialize_session_store()
    st.set_page_config(
        page_title="AI SEC Filing Analyzer",
        page_icon=":bar_chart:",
        layout="wide",
    )

    st.title("AI SEC Filing + Earnings Call Analyzer")
    st.caption(
        "Phase 5: upload or fetch SEC filings, extract financials, ask cited RAG questions, "
        "save research sessions, and generate IB-style filing briefs."
    )

    st.warning(
        "Educational use only. This app summarizes source documents and does not provide "
        "investment advice."
    )

    with st.sidebar:
        st.header("Phase 5")
        st.write("Current scope:")
        st.write("- PDF upload")
        st.write("- Latest 10-K and 10-Q fetch")
        st.write("- Text extraction")
        st.write("- Groq summary")
        st.write("- Structured finance analysis")
        st.write("- ChromaDB RAG with citations")
        st.write("- RAG-powered finance tabs")
        st.write("- Hybrid retrieval for exact metrics")
        st.write("- XBRL financial statement extraction")
        st.write("- Saved analysis sessions")
        st.write("- IB filing brief workflow")
        render_memory_sidebar()

    st.markdown("#### Why this phase matters")
    st.write(
        "Phase 5 turns the analysis into banker workflow outputs: company profile, "
        "financial snapshot, transaction angles, diligence questions, risk flags, and "
        "recent changes."
    )

    energy_tab, general_tab = st.tabs(["Energy company IB Assistant", "General Filing Analyzer"])

    with energy_tab:
        render_energy_company_ib_assistant()

    with general_tab:
        render_general_filing_analyzer()


def render_energy_company_ib_assistant() -> None:
    """Render the Houston energy banking workflow shell."""

    st.markdown("#### Energy Company IB Assistant")
    st.write(
        "A Houston energy banking workflow for upstream, downstream, midstream, and OFS "
        "companies. Add a company list next, then use this workspace to review investor "
        "presentations, earnings presentations, acquisition press releases, 10-Ks, and 10-Qs."
    )

    selector_cols = st.columns([2, 2, 1])
    selected_company_label = selector_cols[0].selectbox(
        "Company",
        options=ENERGY_COMPANY_OPTIONS,
        key="energy_company",
    )
    selected_company = ENERGY_COMPANIES[ENERGY_COMPANY_OPTIONS.index(selected_company_label)]
    selected_report_type = selector_cols[1].selectbox(
        "Report type",
        options=ENERGY_REPORT_TYPES,
        key="energy_report_type",
    )
    selector_cols[2].metric("Ticker", selected_company["ticker"])
    st.caption(f"Coverage group: {selected_company['sector']}")

    st.markdown("#### Report Source")
    source_tab, fetch_tab = st.tabs(["Upload report", "Fetch report"])

    with source_tab:
        uploaded_file = st.file_uploader(
            "Upload an energy company report PDF",
            type=["pdf"],
            accept_multiple_files=False,
            key="energy_report_upload",
        )
        if uploaded_file is not None:
            with st.spinner("Extracting text from uploaded energy report..."):
                extraction = extract_pdf_text(
                    pdf_bytes=uploaded_file.getvalue(),
                    document_name=(
                        f"{selected_company['name']} ({selected_company['ticker']}) - "
                        f"{selected_report_type} - {uploaded_file.name}"
                    ),
                )
            st.session_state.available_documents = {
                **st.session_state.get("available_documents", {}),
                f"Energy Upload: {uploaded_file.name}": extraction,
            }
            render_extraction_metrics(extraction)
            st.success("Uploaded report is now available in the document analysis area below.")

    with fetch_tab:
        if selected_report_type in {"10-K", "10-Q", "Earnings press release (8-K)"}:
            sec_form = "8-K" if selected_report_type == "Earnings press release (8-K)" else selected_report_type
            st.info(
                f"Fetch the latest {selected_report_type} for "
                f"{selected_company['name']} directly from SEC EDGAR."
            )
            if selected_report_type == "Earnings press release (8-K)":
                st.caption(
                    "The app prefers an earnings-related 8-K with Item 2.02 when SEC metadata "
                    "provides it, then falls back to the latest 8-K."
                )

            if st.button(
                f"Fetch latest {selected_report_type} for {selected_company['ticker']}",
                key="energy_fetch_selected_report",
                type="primary",
            ):
                with st.spinner(
                    f"Fetching latest {selected_report_type} for "
                    f"{selected_company['ticker']} from SEC EDGAR..."
                ):
                    try:
                        if selected_report_type == "Earnings press release (8-K)":
                            filing = fetch_latest_earnings_8k(selected_company["ticker"])
                        else:
                            filings = fetch_latest_annual_and_quarterly_filings(
                                selected_company["ticker"]
                            )
                            filing = filings[selected_report_type]
                    except Exception as exc:
                        st.error(f"Could not fetch {selected_report_type}: {exc}")
                        return

                document_label = f"Energy SEC {sec_form}: {filing.display_name}"
                extraction = filing_to_extraction(filing)
                st.session_state.last_ticker = selected_company["ticker"]
                st.session_state.sec_filings = {
                    **st.session_state.get("sec_filings", {}),
                    sec_form: filing,
                }
                st.session_state.available_documents = {
                    **st.session_state.get("available_documents", {}),
                    document_label: extraction,
                }
                st.success(f"Fetched {filing.display_name} and added it for analysis.")
                st.link_button(f"Open {sec_form} on SEC", filing.filing_url)
                render_extraction_metrics(extraction)

        elif selected_report_type in {"Investor presentation", "Earnings presentation"}:
            st.info(
                f"Search {selected_company['name']}'s investor relations page for likely "
                f"{selected_report_type.lower()} PDFs."
            )
            st.link_button("Open company IR source page", selected_company["ir_url"])
            if st.button(
                f"Find and fetch latest {selected_report_type.lower()}",
                key="energy_fetch_ir_presentation",
                type="primary",
            ):
                with st.spinner(f"Searching {selected_company['name']} investor relations PDFs..."):
                    try:
                        candidates = discover_ir_pdf_links(
                            selected_company["ir_url"],
                            selected_report_type,
                        )
                    except Exception as exc:
                        st.error(f"Could not search company IR page: {type(exc).__name__}: {exc}")
                        return

                if not candidates:
                    st.warning(
                        "No matching PDF links were found automatically. Some IR sites load "
                        "documents with JavaScript, so use the source page link or upload the PDF."
                    )
                    return

                candidate = candidates[0]
                with st.spinner(f"Downloading {candidate.title}..."):
                    try:
                        pdf_bytes = download_ir_pdf(candidate)
                        extraction = extract_pdf_text(
                            pdf_bytes=pdf_bytes,
                            document_name=(
                                f"{selected_company['name']} ({selected_company['ticker']}) - "
                                f"{selected_report_type} - {candidate.title}"
                            ),
                        )
                    except Exception as exc:
                        st.error(f"Could not download or parse IR PDF: {type(exc).__name__}: {exc}")
                        st.link_button("Open PDF manually", candidate.url)
                        return

                document_label = f"Energy IR {selected_report_type}: {candidate.title}"
                st.session_state.last_ticker = selected_company["ticker"]
                st.session_state.available_documents = {
                    **st.session_state.get("available_documents", {}),
                    document_label: extraction,
                }
                st.success(f"Fetched {candidate.title} and added it for analysis.")
                st.link_button("Open source PDF", candidate.url)
                render_extraction_metrics(extraction)
        else:
            st.warning(
                "Acquisition press releases are not standardized across SEC and IR sites yet. "
                "Upload the PDF for now; next we can add deal-news and 8-K exhibit search."
            )

    st.markdown("#### Energy IB Question Bank")
    st.info(
        "Once you provide the question list, this section will generate report-specific "
        "answers for acreage, production, reserves, commodity mix, gathering/processing, "
        "refining margins, capex, leverage, FCF, M&A rationale, and management outlook."
    )

    render_available_documents()


def render_general_filing_analyzer() -> None:
    """Render the general SEC filing analyzer workflow."""

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

    action_cols = st.columns(6)
    if action_cols[0].button("Generate Phase 1 Summary", type="secondary"):
        with st.spinner("Asking Groq to summarize the filing..."):
            try:
                st.session_state.phase1_summary = summarize_filing(extraction)
                save_current_event(
                    event_type="phase_1_summary",
                    content=st.session_state.phase1_summary,
                    document_name=extraction.document_name,
                )
            except Exception as exc:
                st.error(f"Could not generate summary: {type(exc).__name__}: {exc}")
                return

    if action_cols[1].button("Generate Phase 2 Financial Analysis", type="primary"):
        with st.spinner("Extracting structured financial intelligence..."):
            st.session_state.phase2_analysis = analyze_financial_document(extraction)
            save_current_event(
                event_type="phase_2_financial_analysis",
                content=summarize_financial_analysis(st.session_state.phase2_analysis),
                document_name=extraction.document_name,
            )

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
                save_current_event(
                    event_type="rag_financial_analysis",
                    content=summarize_rag_financial_analysis(st.session_state.rag_financial_analysis),
                    document_name=extraction.document_name,
                )
            except Exception as exc:
                st.error(f"Could not generate RAG financial intelligence: {type(exc).__name__}: {exc}")
                return

    if action_cols[4].button("Extract Financial Statements", type="primary"):
        ticker = st.session_state.get("last_ticker")
        if not ticker:
            st.warning("Fetch a company by ticker first so SEC XBRL facts can be loaded.")
            return
        with st.spinner(f"Extracting financial statement data for {ticker} from SEC XBRL..."):
            try:
                st.session_state.financial_statement_data = extract_financial_statement_data(ticker)
                save_current_event(
                    event_type="financial_statement_data",
                    content=financial_statement_data_to_markdown(
                        st.session_state.financial_statement_data
                    ),
                    document_name=extraction.document_name,
                )
            except Exception as exc:
                st.error(f"Could not extract financial statement data: {type(exc).__name__}: {exc}")
                return

    if action_cols[5].button("Generate IB Brief", type="primary"):
        if st.session_state.get("last_indexed_document") != extraction.document_name:
            st.warning("Index the selected document for RAG before generating the IB brief.")
            return
        with st.spinner("Generating banker-style filing brief..."):
            try:
                st.session_state.ib_brief = generate_ib_brief(
                    extraction=extraction,
                    rag_pipeline=get_rag_pipeline(),
                    financial_data=st.session_state.get("financial_statement_data"),
                )
                save_current_event(
                    event_type="ib_filing_brief",
                    content=ib_brief_to_markdown(st.session_state.ib_brief),
                    document_name=extraction.document_name,
                )
            except Exception as exc:
                st.error(f"Could not generate IB brief: {type(exc).__name__}: {exc}")
                return

    result_tab, analysis_tab, statement_tab, ib_tab, rag_analysis_tab, rag_tab, memory_tab = st.tabs(
        [
            "Summary",
            "Financial Intelligence",
            "Financial Statements",
            "IB Brief",
            "RAG Financial Intelligence",
            "RAG Q&A",
            "Memory",
        ]
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

    with statement_tab:
        statement_data = st.session_state.get("financial_statement_data")
        if statement_data:
            render_financial_statement_data(statement_data)
        else:
            st.info("Click `Extract Financial Statements` after fetching a ticker.")

    with ib_tab:
        ib_brief = st.session_state.get("ib_brief")
        if ib_brief:
            render_ib_brief(ib_brief)
        else:
            st.info("Click `Index for RAG`, optionally extract financial statements, then `Generate IB Brief`.")

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

    with memory_tab:
        render_memory_tab()


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
        save_current_event(
            event_type="rag_question_answer",
            content=answer,
            document_name=document_filter or "",
            question=question,
        )

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


def render_financial_statement_data(data: FinancialStatementData) -> None:
    """Render extracted SEC XBRL financial statement data."""

    st.markdown(f"#### {data.company_name} ({data.ticker})")
    line_tab, derived_tab, limitations_tab = st.tabs(["Line Items", "Derived Metrics", "Limitations"])

    with line_tab:
        if not data.line_items:
            st.info("No line items were extracted.")
        for item in data.line_items:
            cols = st.columns([2, 1, 1])
            cols[0].write(f"**{item.label}**")
            cols[1].write(item.value)
            cols[2].caption(f"FY {item.fiscal_year or 'n/a'}")
            st.caption(f"Tag: `{item.source_tag}` | {item.notes}")

    with derived_tab:
        if not data.derived_metrics:
            st.info("No derived metrics were calculated.")
        for metric in data.derived_metrics:
            st.write(f"**{metric.label}:** {metric.value}")
            st.caption(f"{metric.formula}. {metric.notes}")

    with limitations_tab:
        render_bullets(data.limitations, "No extraction limitations were recorded.")


def render_ib_brief(brief: IbBrief) -> None:
    """Render banker-style filing brief."""

    profile_tab, snapshot_tab, angles_tab, diligence_tab, risks_tab, changes_tab = st.tabs(
        ["Profile", "Snapshot", "Angles", "Diligence", "Risk Flags", "Changes"]
    )
    with profile_tab:
        render_bullets(brief.company_profile, "No company profile bullets were generated.")
    with snapshot_tab:
        render_bullets(brief.financial_snapshot, "No financial snapshot bullets were generated.")
    with angles_tab:
        render_bullets(brief.transaction_angles, "No transaction angles were generated.")
    with diligence_tab:
        render_bullets(brief.diligence_questions, "No diligence questions were generated.")
    with risks_tab:
        render_bullets(brief.risk_flags, "No risk flags were generated.")
        if brief.limitations:
            st.markdown("#### Limitations")
            render_bullets(brief.limitations, "No limitations were provided.")
    with changes_tab:
        render_bullets(brief.recent_changes, "No recent changes were generated.")

    st.download_button(
        "Download IB Brief Markdown",
        data=ib_brief_to_markdown(brief),
        file_name="ib_filing_brief.md",
        mime="text/markdown",
    )


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


def render_memory_sidebar() -> None:
    """Render analysis session controls in the sidebar."""

    st.markdown("#### Session Memory")
    default_name = f"{st.session_state.get('last_ticker', 'Company')} Filing Review"
    session_name = st.text_input("Session name", value=default_name, key="new_session_name")
    if st.button("Create Session"):
        session_id = create_analysis_session(
            name=session_name,
            ticker=st.session_state.get("last_ticker", ""),
        )
        st.session_state.active_session_id = session_id
        st.success("Session created.")

    sessions = list_analysis_sessions(limit=20)
    if not sessions:
        st.caption("No saved sessions yet.")
        return

    labels = [f"{session.id}: {session.name}" for session in sessions]
    active_id = st.session_state.get("active_session_id", sessions[0].id)
    default_index = next(
        (index for index, session in enumerate(sessions) if session.id == active_id),
        0,
    )
    selected_label = st.selectbox("Active session", labels, index=default_index)
    st.session_state.active_session_id = int(selected_label.split(":", 1)[0])


def save_current_event(
    event_type: str,
    content: str,
    document_name: str = "",
    question: str = "",
) -> None:
    """Save an event when a memory session is active."""

    session_id = st.session_state.get("active_session_id")
    if not session_id:
        return
    save_analysis_event(
        session_id=int(session_id),
        event_type=event_type,
        content=content,
        document_name=document_name,
        question=question,
    )


def render_memory_tab() -> None:
    """Render saved session history and export controls."""

    st.markdown("#### Analysis Session Memory")
    session_id = st.session_state.get("active_session_id")
    if not session_id:
        st.info("Create or select a session in the sidebar to save analysis history.")
        return

    events = list_analysis_events(session_id=int(session_id), limit=50)
    st.metric("Saved Events", len(events))

    markdown = export_session_markdown(session_id=int(session_id))
    st.download_button(
        "Download Session Markdown",
        data=markdown,
        file_name=f"analysis_session_{session_id}.md",
        mime="text/markdown",
    )

    if not events:
        st.info("No saved events yet. Generate a summary, analysis, or RAG answer.")
        return
    for event in events:
        render_memory_event(event)


def render_memory_event(event: AnalysisEvent) -> None:
    """Render one saved memory event."""

    title = f"{event.created_at} | {event.event_type.replace('_', ' ').title()}"
    with st.expander(title):
        if event.document_name:
            st.write(f"**Document:** {event.document_name}")
        if event.question:
            st.write(f"**Question:** {event.question}")
        st.write(event.content)


def summarize_financial_analysis(analysis: FinancialAnalysisResult) -> str:
    """Convert structured Phase 2 analysis to Markdown for memory."""

    lines = [
        "## Business Overview",
        analysis.business_overview or "Not specified.",
        "",
        "## Revenue Drivers",
        *[f"- {item}" for item in analysis.revenue_drivers],
        "",
        "## Risks",
        *[f"- {risk.title} ({risk.severity}): {risk.description}" for risk in analysis.risks],
        "",
        "## MD&A Themes",
        *[f"- {item}" for item in analysis.mda_themes],
        "",
        "## Key Metrics",
        *[f"- {metric.name}: {metric.value} - {metric.context}" for metric in analysis.key_metrics],
        "",
        "## Tone",
        f"{analysis.tone.overall_tone}: {analysis.tone.explanation}",
        "",
        "## Insights",
        *[f"- {item}" for item in analysis.investment_insights],
    ]
    return "\n".join(lines)


def summarize_rag_financial_analysis(analysis: RagFinancialAnalysisResult) -> str:
    """Convert RAG financial intelligence to Markdown for memory."""

    sections = [
        analysis.business_overview,
        analysis.revenue,
        analysis.risks,
        analysis.mda,
        analysis.metrics,
        analysis.tone,
        analysis.insights,
    ]
    lines = [f"# RAG Financial Intelligence: {analysis.document_name}", ""]
    for section in sections:
        lines.extend([f"## {section.title}", ""])
        if section.limitations:
            lines.extend([f"- Limitation: {item}" for item in section.limitations])
        for finding in section.findings:
            lines.append(
                f"- {finding.finding} | Evidence: {finding.evidence} | "
                f"Citation: {finding.citation} | Confidence: {finding.confidence}"
            )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    render_phase1_mvp()

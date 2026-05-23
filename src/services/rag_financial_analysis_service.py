"""Phase 3.5 RAG-powered financial intelligence.

This service improves the Phase 2 financial tabs by retrieving targeted filing
chunks for each analysis area and asking the LLM for cited findings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.rag.pipeline import RagPipeline, RetrievedChunk
from src.services.financial_analysis_service import extract_json_object
from src.services.llm_service import LLMService
from src.services.phase1_filing_summary import FilingExtractionResult


@dataclass
class CitedFinding:
    """One cited analyst finding."""

    finding: str
    evidence: str
    citation: str
    confidence: str = "medium"
    finance_relevance: str = ""


@dataclass
class RagSectionAnalysis:
    """RAG output for one finance section."""

    title: str
    question: str
    findings: list[CitedFinding] = field(default_factory=list)
    sources: list[RetrievedChunk] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    raw_response: str = ""


@dataclass
class RagFinancialAnalysisResult:
    """RAG-powered financial intelligence across major analyst sections."""

    document_name: str
    business_overview: RagSectionAnalysis
    revenue: RagSectionAnalysis
    risks: RagSectionAnalysis
    mda: RagSectionAnalysis
    metrics: RagSectionAnalysis
    tone: RagSectionAnalysis
    insights: RagSectionAnalysis


SECTION_QUERIES: dict[str, tuple[str, str]] = {
    "business_overview": (
        "Business Overview",
        "What does the filing say about the company's business model, products, services, customers, and segments?",
    ),
    "revenue": (
        "Revenue Drivers",
        "What revenue drivers, segment trends, product trends, pricing, volume, geography, or customer drivers are discussed?",
    ),
    "risks": (
        "Risk Factors",
        "What are the most important business, financial, market, regulatory, liquidity, and operational risks discussed?",
    ),
    "mda": (
        "MD&A Themes",
        "What does management discuss about operating results, margins, liquidity, cash flow, outlook, and recent changes?",
    ),
    "metrics": (
        "Key Metrics",
        "What financial metrics, operating metrics, revenue figures, margin figures, cash flow figures, or liquidity figures are reported?",
    ),
    "tone": (
        "Management Tone",
        "What language indicates management tone, confidence, caution, uncertainty, pressure, or optimism?",
    ),
    "insights": (
        "Investment Insights",
        "What analyst-style investment insights are supported by the filing context without making buy sell or hold recommendations?",
    ),
}


def analyze_financial_document_with_rag(
    extraction: FilingExtractionResult,
    rag_pipeline: RagPipeline,
    llm_service: LLMService | None = None,
    top_k: int = 4,
) -> RagFinancialAnalysisResult:
    """Generate targeted, cited financial analysis with RAG."""

    sections: dict[str, RagSectionAnalysis] = {}
    for key, (title, question) in SECTION_QUERIES.items():
        try:
            chunks = rag_pipeline.retrieve(
                question=question,
                top_k=top_k,
                document_name=extraction.document_name,
            )
        except Exception as exc:
            sections[key] = RagSectionAnalysis(
                title=title,
                question=question,
                limitations=[
                    "Retrieval failed before the model could analyze this section.",
                    f"{type(exc).__name__}: {exc}",
                ],
            )
            continue
        sections[key] = analyze_rag_section(
            title=title,
            question=question,
            chunks=chunks,
            llm_service=llm_service,
        )

    return RagFinancialAnalysisResult(
        document_name=extraction.document_name,
        business_overview=sections["business_overview"],
        revenue=sections["revenue"],
        risks=sections["risks"],
        mda=sections["mda"],
        metrics=sections["metrics"],
        tone=sections["tone"],
        insights=sections["insights"],
    )


def analyze_rag_section(
    title: str,
    question: str,
    chunks: list[RetrievedChunk],
    llm_service: LLMService | None = None,
) -> RagSectionAnalysis:
    """Analyze one finance section from retrieved chunks."""

    if not chunks:
        return RagSectionAnalysis(
            title=title,
            question=question,
            limitations=["No relevant chunks were retrieved for this section."],
        )

    llm = llm_service or LLMService()
    if not llm.is_configured():
        return RagSectionAnalysis(
            title=title,
            question=question,
            sources=chunks,
            limitations=["Groq is not configured. Retrieved sources are shown, but no analysis was generated."],
        )

    response = ""
    try:
        response = llm.generate(
            system_prompt=(
                "You are a careful finance analyst. Return valid JSON only. "
                "Every finding must be supported by the provided sources."
            ),
            user_prompt=build_rag_section_prompt(title=title, question=question, chunks=chunks),
        )
        findings = parse_cited_findings(response)
        return RagSectionAnalysis(
            title=title,
            question=question,
            findings=findings,
            sources=chunks,
            raw_response=response,
            limitations=[] if findings else ["No supported findings were returned."],
        )
    except Exception as exc:
        return RagSectionAnalysis(
            title=title,
            question=question,
            sources=chunks,
            raw_response=response,
            limitations=[f"Section analysis failed: {type(exc).__name__}: {exc}"],
        )


def build_rag_section_prompt(title: str, question: str, chunks: list[RetrievedChunk]) -> str:
    """Build a JSON prompt for one RAG-powered section."""

    context = "\n\n".join(
        f"[Source {index}] {chunk.citation}\n{chunk.text}"
        for index, chunk in enumerate(chunks, start=1)
    )
    return f"""
Analyze this finance section using only the retrieved filing sources.

Section: {title}
Question: {question}

Return valid JSON only with this schema:
{{
  "findings": [
    {{
      "finding": "concise analyst finding",
      "evidence": "short source-backed evidence",
      "citation": "[Source 1]",
      "confidence": "low|medium|high",
      "finance_relevance": "why this matters for company analysis"
    }}
  ],
  "limitations": ["what the retrieved sources do not answer"]
}}

Rules:
- Use only the sources below.
- Include source citations like [Source 1].
- Do not provide buy, sell, or hold recommendations.
- Return 2 to 5 high-quality findings when supported.
- If evidence is weak, lower confidence or add a limitation.

Sources:
{context}
""".strip()


def parse_cited_findings(response: str) -> list[CitedFinding]:
    """Parse cited findings from model JSON."""

    data = json.loads(extract_json_object(response))
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        return []
    parsed: list[CitedFinding] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        parsed.append(
            CitedFinding(
                finding=str(item.get("finding", "")),
                evidence=str(item.get("evidence", "")),
                citation=str(item.get("citation", "")),
                confidence=str(item.get("confidence", "medium")),
                finance_relevance=str(item.get("finance_relevance", "")),
            )
        )
    return [finding for finding in parsed if finding.finding.strip()]

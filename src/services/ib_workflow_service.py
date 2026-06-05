"""Phase 5 investment banking workflow outputs.

This service turns filing analysis into banker-facing deliverables: company
profile, transaction angles, diligence questions, risk flags, and change notes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.rag.pipeline import RagPipeline, RetrievedChunk
from src.services.financial_analysis_service import extract_json_object
from src.services.financial_statement_service import (
    FinancialStatementData,
    financial_statement_data_to_markdown,
)
from src.services.llm_service import LLMService
from src.services.phase1_filing_summary import FilingExtractionResult


@dataclass
class IbBrief:
    """Banker-facing filing brief."""

    company_profile: list[str] = field(default_factory=list)
    transaction_angles: list[str] = field(default_factory=list)
    diligence_questions: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    financial_snapshot: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    raw_response: str = ""


IB_RETRIEVAL_QUESTIONS = [
    "What does the company do, what are its products, services, end markets, and segments?",
    "What are the main revenue drivers, growth trends, margin trends, and recent operating changes?",
    "What risks, liquidity issues, competition, customer concentration, or regulatory issues should bankers know?",
    "What diligence questions should an investment banker ask management based on this filing?",
    "What transaction angles, strategic buyer considerations, or sponsor considerations are supported by the filing?",
]


def generate_ib_brief(
    extraction: FilingExtractionResult,
    rag_pipeline: RagPipeline,
    financial_data: FinancialStatementData | None = None,
    llm_service: LLMService | None = None,
) -> IbBrief:
    """Generate an IB-style company filing brief."""

    chunks = retrieve_ib_context(extraction=extraction, rag_pipeline=rag_pipeline)
    if not chunks:
        return IbBrief(limitations=["No RAG context was retrieved. Index the filing first."])

    llm = llm_service or LLMService()
    if not llm.is_configured():
        return IbBrief(
            limitations=["Groq is not configured. Retrieved context is available but no brief was generated."]
        )

    prompt = build_ib_brief_prompt(
        extraction=extraction,
        chunks=chunks,
        financial_data=financial_data,
    )
    response = ""
    try:
        response = llm.generate(
            system_prompt=(
                "You are an investment banking analyst preparing a source-grounded "
                "company filing brief. Return valid JSON only."
            ),
            user_prompt=prompt,
        )
        return parse_ib_brief(response)
    except Exception as exc:
        return IbBrief(
            limitations=[f"IB brief generation failed: {type(exc).__name__}: {exc}"],
            raw_response=response,
        )


def retrieve_ib_context(
    extraction: FilingExtractionResult,
    rag_pipeline: RagPipeline,
) -> list[RetrievedChunk]:
    """Retrieve source chunks across the banker workflow questions."""

    seen: dict[tuple[str, int], RetrievedChunk] = {}
    for question in IB_RETRIEVAL_QUESTIONS:
        for chunk in rag_pipeline.retrieve_section_aware(
            question=question,
            top_k=4,
            document_name=extraction.document_name,
        ):
            seen[(chunk.document_name, chunk.chunk_index)] = chunk
    return list(seen.values())[:12]


def build_ib_brief_prompt(
    extraction: FilingExtractionResult,
    chunks: list[RetrievedChunk],
    financial_data: FinancialStatementData | None = None,
) -> str:
    """Build JSON-only IB brief prompt."""

    context = "\n\n".join(
        f"[Source {index}] {chunk.citation}\n{chunk.text}"
        for index, chunk in enumerate(chunks, start=1)
    )
    financial_snapshot = (
        financial_statement_data_to_markdown(financial_data)
        if financial_data
        else "No structured financial statement data was provided."
    )
    return f"""
Create an investment banking filing brief for this company.

Document: {extraction.document_name}

Structured financial statement data:
{financial_snapshot}

Retrieved filing context:
{context}

Return valid JSON only with this schema:
{{
  "company_profile": ["source-grounded profile bullet"],
  "transaction_angles": ["strategic or sponsor angle supported by the filing"],
  "diligence_questions": ["management diligence question"],
  "risk_flags": ["risk flag a banker should track"],
  "recent_changes": ["what appears to have changed recently"],
  "financial_snapshot": ["hard financial or derived metric bullet"],
  "limitations": ["what is missing or should be verified"]
}}

Rules:
- Use banker language but keep it clear.
- Cite sources inline using [Source 1], [Source 2] when based on retrieved context.
- Do not provide buy/sell/hold recommendations.
- Do not invent valuation, deal probability, or market rumors.
- Include 4 to 8 diligence questions.
- Tie transaction angles to evidence or clearly mark them as preliminary.
""".strip()


def parse_ib_brief(response: str) -> IbBrief:
    """Parse IB brief JSON."""

    data = json.loads(extract_json_object(response))
    return IbBrief(
        company_profile=coerce_string_list(data.get("company_profile")),
        transaction_angles=coerce_string_list(data.get("transaction_angles")),
        diligence_questions=coerce_string_list(data.get("diligence_questions")),
        risk_flags=coerce_string_list(data.get("risk_flags")),
        recent_changes=coerce_string_list(data.get("recent_changes")),
        financial_snapshot=coerce_string_list(data.get("financial_snapshot")),
        limitations=coerce_string_list(data.get("limitations")),
        raw_response=response,
    )


def coerce_string_list(value: object) -> list[str]:
    """Convert model list output to strings."""

    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def ib_brief_to_markdown(brief: IbBrief) -> str:
    """Convert IB brief to Markdown for memory/export."""

    sections = [
        ("Company Profile", brief.company_profile),
        ("Financial Snapshot", brief.financial_snapshot),
        ("Transaction Angles", brief.transaction_angles),
        ("Diligence Questions", brief.diligence_questions),
        ("Risk Flags", brief.risk_flags),
        ("Recent Changes", brief.recent_changes),
        ("Limitations", brief.limitations),
    ]
    lines = ["# IB Filing Brief", ""]
    for title, items in sections:
        lines.extend([f"## {title}", ""])
        if not items:
            lines.append("- Not generated.")
        else:
            lines.extend([f"- {item}" for item in items])
        lines.append("")
    return "\n".join(lines)

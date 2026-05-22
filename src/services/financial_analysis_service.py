"""Phase 2 structured financial analysis service.

Phase 1 asked the model for a general filing summary. Phase 2 asks for a
structured analyst-style output that the UI can render in separate sections.
This is still pre-RAG: we use a controlled document excerpt, not embeddings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.services.llm_service import LLMService
from src.services.phase1_filing_summary import FilingExtractionResult, truncate_for_prompt


ANALYSIS_PROMPT_CHARACTERS = 10_000


@dataclass
class RiskItem:
    """One business or financial risk extracted from the document."""

    title: str
    description: str
    severity: str = "medium"


@dataclass
class MetricItem:
    """One financial or operating metric mentioned in the document."""

    name: str
    value: str
    context: str


@dataclass
class ToneAnalysis:
    """Management tone assessment."""

    overall_tone: str
    explanation: str
    confidence: str = "medium"


@dataclass
class FinancialAnalysisResult:
    """Structured Phase 2 analysis result."""

    business_overview: str = ""
    revenue_drivers: list[str] = field(default_factory=list)
    risks: list[RiskItem] = field(default_factory=list)
    mda_themes: list[str] = field(default_factory=list)
    key_metrics: list[MetricItem] = field(default_factory=list)
    tone: ToneAnalysis = field(
        default_factory=lambda: ToneAnalysis(
            overall_tone="unknown",
            explanation="No tone analysis available.",
        )
    )
    investment_insights: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    raw_response: str = ""


def analyze_financial_document(
    extraction: FilingExtractionResult,
    llm_service: LLMService | None = None,
) -> FinancialAnalysisResult:
    """Generate a structured analyst-style financial analysis."""

    if not extraction.text:
        return FinancialAnalysisResult(
            limitations=["No readable document text was available for analysis."]
        )

    llm = llm_service or LLMService()
    if not llm.is_configured():
        return build_unconfigured_analysis(extraction)

    system_prompt = (
        "You are a careful finance analyst. Extract only what is supported by the "
        "provided filing excerpt. Return valid JSON only, with no markdown fences."
    )
    user_prompt = build_financial_analysis_prompt(extraction)

    try:
        response = llm.generate(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception as exc:
        return FinancialAnalysisResult(
            limitations=[f"LLM request failed: {type(exc).__name__}: {exc}"]
        )

    return parse_financial_analysis_response(response)


def build_financial_analysis_prompt(extraction: FilingExtractionResult) -> str:
    """Build a JSON-focused prompt for Phase 2 analysis."""

    filing_text = truncate_for_prompt(extraction.text, max_characters=ANALYSIS_PROMPT_CHARACTERS)
    return f"""
Analyze this filing excerpt and return valid JSON only.

Document name: {extraction.document_name}

Required JSON schema:
{{
  "business_overview": "plain English overview",
  "revenue_drivers": ["driver 1", "driver 2"],
  "risks": [
    {{"title": "risk name", "description": "why it matters", "severity": "low|medium|high"}}
  ],
  "mda_themes": ["theme 1", "theme 2"],
  "key_metrics": [
    {{"name": "metric name", "value": "reported value or not specified", "context": "why it matters"}}
  ],
  "tone": {{
    "overall_tone": "confident|neutral|cautious|mixed|unknown",
    "explanation": "brief support from the filing excerpt",
    "confidence": "low|medium|high"
  }},
  "investment_insights": ["insight 1", "insight 2"],
  "limitations": ["what the excerpt does not support"]
}}

Rules:
- Return JSON only.
- Do not include a buy, sell, or hold recommendation.
- If a field is not supported, use an empty list or say "not specified".
- Prefer extraction over inference.
- Keep each list to 3 to 6 high-value items.

Filing excerpt:
{filing_text}
""".strip()


def parse_financial_analysis_response(response: str) -> FinancialAnalysisResult:
    """Parse model JSON into dataclasses with defensive fallbacks."""

    try:
        data = json.loads(extract_json_object(response))
    except json.JSONDecodeError:
        return FinancialAnalysisResult(
            limitations=["The model did not return valid JSON. Showing raw response instead."],
            raw_response=response,
        )

    return FinancialAnalysisResult(
        business_overview=str(data.get("business_overview", "")),
        revenue_drivers=coerce_string_list(data.get("revenue_drivers")),
        risks=[
            RiskItem(
                title=str(item.get("title", "Risk")),
                description=str(item.get("description", "")),
                severity=str(item.get("severity", "medium")),
            )
            for item in coerce_dict_list(data.get("risks"))
        ],
        mda_themes=coerce_string_list(data.get("mda_themes")),
        key_metrics=[
            MetricItem(
                name=str(item.get("name", "Metric")),
                value=str(item.get("value", "not specified")),
                context=str(item.get("context", "")),
            )
            for item in coerce_dict_list(data.get("key_metrics"))
        ],
        tone=parse_tone(data.get("tone")),
        investment_insights=coerce_string_list(data.get("investment_insights")),
        limitations=coerce_string_list(data.get("limitations")),
        raw_response=response,
    )


def extract_json_object(response: str) -> str:
    """Extract the first JSON object from a model response."""

    stripped = response.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.removeprefix("json").strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1]


def parse_tone(value: Any) -> ToneAnalysis:
    """Parse tone field from model JSON."""

    if not isinstance(value, dict):
        return ToneAnalysis(overall_tone="unknown", explanation="Tone was not specified.")
    return ToneAnalysis(
        overall_tone=str(value.get("overall_tone", "unknown")),
        explanation=str(value.get("explanation", "")),
        confidence=str(value.get("confidence", "medium")),
    )


def coerce_string_list(value: Any) -> list[str]:
    """Return a clean list of strings from flexible model output."""

    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def coerce_dict_list(value: Any) -> list[dict[str, Any]]:
    """Return only dictionary items from flexible model output."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def build_unconfigured_analysis(extraction: FilingExtractionResult) -> FinancialAnalysisResult:
    """Return a useful fallback when Groq is not configured."""

    return FinancialAnalysisResult(
        business_overview="Groq is not configured, so structured analysis was not generated.",
        limitations=[
            "Add GROQ_API_KEY to .env and restart the app.",
            f"Document text extraction worked for {extraction.document_name}.",
        ],
    )

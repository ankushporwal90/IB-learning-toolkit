"""Financial metric extraction helpers for exact-answer RAG questions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.rag.pipeline import RetrievedChunk


@dataclass
class MetricAnswer:
    """A source-backed metric answer."""

    metric_name: str
    value: str
    unit: str
    citation: str
    evidence: str


REVENUE_PATTERNS = [
    re.compile(
        r"(?:total\s+)?net\s+sales\s+\$?\s*([0-9][0-9,]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:total\s+)?revenue\s+\$?\s*([0-9][0-9,]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"revenue\s+(?:was|of|totaled|increased\s+to)\s+\$?\s*([0-9][0-9,]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    ),
]


def answer_metric_question(question: str, chunks: list[RetrievedChunk]) -> str | None:
    """Answer exact metric questions when a supported metric is detected."""

    if not is_revenue_question(question):
        return None

    metric = extract_latest_revenue(chunks)
    if not metric:
        return None

    return (
        f"The latest revenue figure I found is **{metric.value} {metric.unit}** "
        f"for **{metric.metric_name}**. Evidence: {metric.evidence} "
        f"[Source: {metric.citation}]."
    )


def is_revenue_question(question: str) -> bool:
    """Return whether the user is asking for revenue or sales."""

    lowered = question.lower()
    return any(term in lowered for term in ["revenue", "net sales", "sales"])


def extract_latest_revenue(chunks: list[RetrievedChunk]) -> MetricAnswer | None:
    """Extract the most likely latest revenue/net sales figure from retrieved chunks."""

    for chunk in chunks:
        normalized = normalize_financial_text(chunk.text)
        if not likely_revenue_context(normalized):
            continue
        for pattern in REVENUE_PATTERNS:
            match = pattern.search(normalized)
            if not match:
                continue
            value = match.group(1)
            return MetricAnswer(
                metric_name="total revenue / net sales",
                value=format_metric_value(value),
                unit=infer_unit(normalized),
                citation=chunk.citation,
                evidence=build_evidence_snippet(normalized, match.start(), match.end()),
            )
    return None


def likely_revenue_context(text: str) -> bool:
    """Check whether text appears to contain a revenue table or statement line."""

    lowered = text.lower()
    return any(term in lowered for term in ["net sales", "total revenue", "revenue"])


def normalize_financial_text(text: str) -> str:
    """Normalize common filing punctuation around numbers."""

    return " ".join(
        text.replace("$", " $ ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("\u2014", " ")
        .split()
    )


def infer_unit(text: str) -> str:
    """Infer whether a filing table is in millions or billions."""

    lowered = text.lower()
    if "in millions" in lowered or "millions" in lowered:
        return "million"
    if "in billions" in lowered or "billions" in lowered:
        return "billion"
    return "as reported in filing units"


def format_metric_value(value: str) -> str:
    """Format numeric filing values while preserving scale."""

    return "$" + value


def build_evidence_snippet(text: str, start: int, end: int, radius: int = 180) -> str:
    """Return a compact source snippet around a matched metric."""

    snippet_start = max(start - radius, 0)
    snippet_end = min(end + radius, len(text))
    return text[snippet_start:snippet_end].strip()

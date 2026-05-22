"""Phase 1 SEC filing summarization service.

Phase 1 teaches the simplest useful AI workflow:

    PDF upload -> text extraction -> prompt -> LLM summary
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from src.services.llm_service import LLMService


MAX_PROMPT_CHARACTERS = 9_000


@dataclass
class FilingExtractionResult:
    """Text and metadata extracted from an uploaded PDF."""

    document_name: str
    text: str
    page_count: int
    extracted_page_count: int


def extract_pdf_text(pdf_bytes: bytes, document_name: str) -> FilingExtractionResult:
    """Extract readable text from a PDF file."""

    reader = PdfReader(BytesIO(pdf_bytes))
    page_texts: list[str] = []

    for page in reader.pages:
        page_text = clean_text(page.extract_text() or "")
        if page_text:
            page_texts.append(page_text)

    return FilingExtractionResult(
        document_name=document_name,
        text="\n\n".join(page_texts),
        page_count=len(reader.pages),
        extracted_page_count=len(page_texts),
    )


def build_filing_summary_prompt(extraction: FilingExtractionResult) -> str:
    """Create a beginner-friendly finance prompt for filing analysis."""

    filing_text = truncate_for_prompt(extraction.text)
    return f"""
Analyze this SEC filing or investor document for an MBA student learning finance.

Document name: {extraction.document_name}
Pages with extracted text: {extraction.extracted_page_count} of {extraction.page_count}

Return a concise but useful summary with these sections:
1. Business Overview
2. Revenue Drivers
3. Key Risks
4. Management Discussion Themes
5. Segment or Product Notes
6. Financial Trends Mentioned
7. Sentiment and Tone
8. Investment Insights

Rules:
- Use plain English.
- Do not provide investment advice or a buy/sell recommendation.
- If the document does not contain enough information for a section, say so.
- Base the answer only on the text below.

Filing text:
{filing_text}
""".strip()


def summarize_filing(
    extraction: FilingExtractionResult,
    llm_service: LLMService | None = None,
) -> str:
    """Summarize an extracted filing with Groq, or return a helpful fallback."""

    if not extraction.text:
        return (
            "No readable text was extracted from this PDF. It may be scanned, image-based, "
            "password-protected, or formatted in a way that basic PDF parsing cannot read."
        )

    llm = llm_service or LLMService()
    if not llm.is_configured():
        return build_unconfigured_groq_message(extraction)

    system_prompt = (
        "You are a careful finance analyst. Explain SEC filing content clearly, "
        "avoid unsupported claims, and include a brief educational note when useful."
    )
    user_prompt = build_filing_summary_prompt(extraction)
    try:
        return llm.generate(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception as exc:
        return (
            "The LLM request failed. For Phase 1, the most common cause is a free-tier "
            "token limit when summarizing long SEC filings. The app now sends a shorter "
            f"document excerpt, but this request still failed with: {type(exc).__name__}: {exc}"
        )


def clean_text(text: str) -> str:
    """Normalize whitespace while preserving readable sentences."""

    return " ".join(text.split())


def truncate_for_prompt(text: str, max_characters: int = MAX_PROMPT_CHARACTERS) -> str:
    """Keep prompts within a beginner-friendly size limit."""

    cleaned = clean_text(text)
    if len(cleaned) <= max_characters:
        return cleaned
    return cleaned[:max_characters] + "\n\n[Text truncated for Phase 1 prompt size.]"


def build_unconfigured_groq_message(extraction: FilingExtractionResult) -> str:
    """Explain the setup problem without failing the whole app."""

    preview = truncate_for_prompt(extraction.text, max_characters=900)
    return (
        "Groq is not configured yet. Add `GROQ_API_KEY` to your `.env` file, then rerun "
        "the app.\n\n"
        f"PDF text extraction worked: {extraction.extracted_page_count} of "
        f"{extraction.page_count} pages produced readable text.\n\n"
        f"Text preview:\n\n{preview}"
    )

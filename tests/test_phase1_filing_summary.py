from src.services.phase1_filing_summary import (
    FilingExtractionResult,
    build_filing_summary_prompt,
    summarize_filing,
    truncate_for_prompt,
)


class FakeUnconfiguredLLM:
    def is_configured(self) -> bool:
        return False

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("generate should not be called without a configured API key")


class FakeConfiguredLLM:
    def is_configured(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        assert "careful finance analyst" in system_prompt
        assert "Business Overview" in user_prompt
        assert "Revenue increased" in user_prompt
        return "Structured filing summary"


def test_build_filing_summary_prompt_includes_finance_sections() -> None:
    extraction = FilingExtractionResult(
        document_name="sample-10k.pdf",
        text="Revenue increased because demand grew.",
        page_count=2,
        extracted_page_count=2,
    )

    prompt = build_filing_summary_prompt(extraction)

    assert "Business Overview" in prompt
    assert "Revenue Drivers" in prompt
    assert "Key Risks" in prompt
    assert "sample-10k.pdf" in prompt


def test_summarize_filing_returns_fallback_without_api_key() -> None:
    extraction = FilingExtractionResult(
        document_name="sample-10k.pdf",
        text="Revenue increased because demand grew.",
        page_count=2,
        extracted_page_count=2,
    )

    summary = summarize_filing(extraction, llm_service=FakeUnconfiguredLLM())

    assert "Groq is not configured" in summary
    assert "PDF text extraction worked" in summary


def test_summarize_filing_calls_llm_when_configured() -> None:
    extraction = FilingExtractionResult(
        document_name="sample-10k.pdf",
        text="Revenue increased because demand grew.",
        page_count=2,
        extracted_page_count=2,
    )

    summary = summarize_filing(extraction, llm_service=FakeConfiguredLLM())

    assert summary == "Structured filing summary"


def test_truncate_for_prompt_marks_truncated_text() -> None:
    text = "a" * 25

    truncated = truncate_for_prompt(text, max_characters=10)

    assert truncated.startswith("aaaaaaaaaa")
    assert "Text truncated" in truncated

from src.rag.pipeline import (
    RetrievedChunk,
    answer_question_with_rag,
    build_rag_prompt,
    chunk_extraction,
    split_text,
)
from src.services.phase1_filing_summary import FilingExtractionResult


class FakeUnconfiguredLLM:
    def is_configured(self) -> bool:
        return False

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("generate should not be called without an API key")


class FakeConfiguredLLM:
    def is_configured(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        assert "cite the retrieved sources" in system_prompt
        assert "[Source 1]" in user_prompt
        assert "Risk factors include competition" in user_prompt
        return "Competition is a key risk [Source 1]."


def test_split_text_uses_overlap() -> None:
    chunks = split_text("abcdefghij", chunk_size=6, chunk_overlap=2)

    assert chunks == ["abcdef", "efghij"]


def test_chunk_extraction_preserves_document_name() -> None:
    extraction = FilingExtractionResult(
        document_name="AAPL 10-K",
        text="Revenue increased. Competition risk remains elevated.",
        page_count=1,
        extracted_page_count=1,
    )

    chunks = chunk_extraction(extraction, chunk_size=30, chunk_overlap=5)

    assert chunks[0].document_name == "AAPL 10-K"
    assert chunks[0].chunk_index == 0


def test_build_rag_prompt_includes_citations() -> None:
    chunks = [
        RetrievedChunk(
            text="Risk factors include competition.",
            document_name="AAPL 10-K",
            chunk_index=3,
        )
    ]

    prompt = build_rag_prompt("What are the risks?", chunks)

    assert "[Source 1]" in prompt
    assert "AAPL 10-K, chunk 3" in prompt
    assert "Risk factors include competition." in prompt


def test_answer_question_with_rag_returns_fallback_without_api_key() -> None:
    chunks = [
        RetrievedChunk(
            text="Risk factors include competition.",
            document_name="AAPL 10-K",
            chunk_index=3,
        )
    ]

    answer = answer_question_with_rag(
        "What are the risks?",
        chunks,
        llm_service=FakeUnconfiguredLLM(),
    )

    assert "Groq is not configured" in answer
    assert "AAPL 10-K, chunk 3" in answer


def test_answer_question_with_rag_uses_configured_llm() -> None:
    chunks = [
        RetrievedChunk(
            text="Risk factors include competition.",
            document_name="AAPL 10-K",
            chunk_index=3,
        )
    ]

    answer = answer_question_with_rag(
        "What are the risks?",
        chunks,
        llm_service=FakeConfiguredLLM(),
    )

    assert answer == "Competition is a key risk [Source 1]."

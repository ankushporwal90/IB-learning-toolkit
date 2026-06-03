from src.rag.pipeline import RetrievedChunk
from src.services.phase1_filing_summary import FilingExtractionResult
from src.services.rag_financial_analysis_service import (
    analyze_financial_document_with_rag,
    analyze_rag_section,
    build_rag_section_prompt,
    parse_cited_findings,
)


class FakeRagPipeline:
    def __init__(self) -> None:
        self.questions: list[str] = []
        self.document_names: list[str | None] = []

    def retrieve(
        self,
        question: str,
        top_k: int = 4,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        self.questions.append(question)
        self.document_names.append(document_name)
        return [
            RetrievedChunk(
                text="Revenue increased due to enterprise customer growth.",
                document_name=document_name or "sample filing",
                chunk_index=1,
            )
        ]

    def retrieve_section_aware(
        self,
        question: str,
        top_k: int = 4,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        return self.retrieve(question=question, top_k=top_k, document_name=document_name)


class FailingRagPipeline:
    def retrieve_section_aware(
        self,
        question: str,
        top_k: int = 4,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        raise AttributeError("'RustBindingsAPI' object has no attribute 'bindings'")


class FakeConfiguredLLM:
    def is_configured(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        assert "valid JSON only" in system_prompt
        assert "[Source 1]" in user_prompt
        return """
        {
          "findings": [
            {
              "finding": "Revenue growth was supported by enterprise customers.",
              "evidence": "The source states revenue increased due to enterprise customer growth.",
              "citation": "[Source 1]",
              "confidence": "high",
              "finance_relevance": "Enterprise demand can indicate durable top-line momentum."
            }
          ],
          "limitations": []
        }
        """


class FakeUnconfiguredLLM:
    def is_configured(self) -> bool:
        return False

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("generate should not run without an API key")


def test_build_rag_section_prompt_requires_citations() -> None:
    chunks = [
        RetrievedChunk(
            text="Risk factors include competition.",
            document_name="AAPL 10-K",
            chunk_index=2,
        )
    ]

    prompt = build_rag_section_prompt("Risks", "What are the risks?", chunks)

    assert "citation" in prompt
    assert "[Source 1]" in prompt
    assert "Risk factors include competition." in prompt


def test_parse_cited_findings_maps_json() -> None:
    findings = parse_cited_findings(
        """
        {
          "findings": [
            {
              "finding": "Margins expanded.",
              "evidence": "Gross margin increased.",
              "citation": "[Source 1]",
              "confidence": "medium",
              "finance_relevance": "Margins affect profitability."
            }
          ]
        }
        """
    )

    assert findings[0].finding == "Margins expanded."
    assert findings[0].citation == "[Source 1]"
    assert findings[0].finance_relevance == "Margins affect profitability."


def test_analyze_rag_section_returns_unconfigured_fallback() -> None:
    chunks = [
        RetrievedChunk(text="Revenue increased.", document_name="AAPL 10-Q", chunk_index=1)
    ]

    section = analyze_rag_section(
        title="Revenue",
        question="What drove revenue?",
        chunks=chunks,
        llm_service=FakeUnconfiguredLLM(),
    )

    assert "Groq is not configured" in section.limitations[0]
    assert section.sources == chunks


def test_analyze_financial_document_with_rag_retrieves_each_section() -> None:
    extraction = FilingExtractionResult(
        document_name="AAPL 10-Q",
        text="Revenue increased.",
        page_count=1,
        extracted_page_count=1,
    )
    rag_pipeline = FakeRagPipeline()

    result = analyze_financial_document_with_rag(
        extraction=extraction,
        rag_pipeline=rag_pipeline,
        llm_service=FakeConfiguredLLM(),
    )

    assert len(rag_pipeline.questions) == 7
    assert set(rag_pipeline.document_names) == {"AAPL 10-Q"}
    assert result.revenue.findings[0].citation == "[Source 1]"
    assert result.document_name == "AAPL 10-Q"


def test_analyze_financial_document_with_rag_handles_retrieval_failure() -> None:
    extraction = FilingExtractionResult(
        document_name="AAPL 10-Q",
        text="Revenue increased.",
        page_count=1,
        extracted_page_count=1,
    )

    result = analyze_financial_document_with_rag(
        extraction=extraction,
        rag_pipeline=FailingRagPipeline(),
        llm_service=FakeConfiguredLLM(),
    )

    assert "Retrieval failed" in result.revenue.limitations[0]
    assert "RustBindingsAPI" in result.revenue.limitations[1]

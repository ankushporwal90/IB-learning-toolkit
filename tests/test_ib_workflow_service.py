from src.rag.pipeline import RetrievedChunk
from src.services.ib_workflow_service import (
    build_ib_brief_prompt,
    ib_brief_to_markdown,
    parse_ib_brief,
    retrieve_ib_context,
)
from src.services.phase1_filing_summary import FilingExtractionResult


class FakeRagPipeline:
    def retrieve_section_aware(
        self,
        question: str,
        top_k: int = 4,
        document_name: str | None = None,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                text="The company sells cloud software and faces competition.",
                document_name=document_name or "sample filing",
                chunk_index=1,
                section="business",
            )
        ]


def test_retrieve_ib_context_deduplicates_chunks() -> None:
    extraction = FilingExtractionResult("AAPL 10-K", "text", 1, 1)

    chunks = retrieve_ib_context(extraction, FakeRagPipeline())

    assert len(chunks) == 1
    assert chunks[0].document_name == "AAPL 10-K"


def test_build_ib_brief_prompt_includes_schema_and_sources() -> None:
    extraction = FilingExtractionResult("AAPL 10-K", "text", 1, 1)
    chunks = [
        RetrievedChunk(
            text="The company sells devices and services.",
            document_name="AAPL 10-K",
            chunk_index=2,
        )
    ]

    prompt = build_ib_brief_prompt(extraction, chunks)

    assert "transaction_angles" in prompt
    assert "diligence_questions" in prompt
    assert "[Source 1]" in prompt


def test_parse_ib_brief_maps_json_lists() -> None:
    brief = parse_ib_brief(
        """
        {
          "company_profile": ["Profile bullet"],
          "transaction_angles": ["Angle bullet"],
          "diligence_questions": ["Question?"],
          "risk_flags": ["Risk flag"],
          "recent_changes": ["Change"],
          "financial_snapshot": ["Revenue bullet"],
          "limitations": ["Limitation"]
        }
        """
    )

    assert brief.company_profile == ["Profile bullet"]
    assert brief.diligence_questions == ["Question?"]
    assert brief.financial_snapshot == ["Revenue bullet"]


def test_ib_brief_to_markdown_includes_sections() -> None:
    brief = parse_ib_brief(
        """
        {
          "company_profile": ["Profile bullet"],
          "transaction_angles": ["Angle bullet"],
          "diligence_questions": ["Question?"],
          "risk_flags": ["Risk flag"],
          "recent_changes": ["Change"],
          "financial_snapshot": ["Revenue bullet"],
          "limitations": []
        }
        """
    )

    markdown = ib_brief_to_markdown(brief)

    assert "# IB Filing Brief" in markdown
    assert "## Diligence Questions" in markdown
    assert "Question?" in markdown

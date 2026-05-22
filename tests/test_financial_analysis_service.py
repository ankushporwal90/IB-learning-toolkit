from src.services.financial_analysis_service import (
    analyze_financial_document,
    build_financial_analysis_prompt,
    parse_financial_analysis_response,
)
from src.services.phase1_filing_summary import FilingExtractionResult


class FakeUnconfiguredLLM:
    def is_configured(self) -> bool:
        return False

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("generate should not be called without a configured API key")


class FakeConfiguredLLM:
    def is_configured(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        assert "valid JSON only" in system_prompt
        assert "Required JSON schema" in user_prompt
        return """
        {
          "business_overview": "The company sells software.",
          "revenue_drivers": ["Subscription growth", "Enterprise demand"],
          "risks": [
            {"title": "Competition", "description": "The market is competitive.", "severity": "high"}
          ],
          "mda_themes": ["Margin expansion"],
          "key_metrics": [
            {"name": "Revenue", "value": "$10 million", "context": "Top-line scale"}
          ],
          "tone": {
            "overall_tone": "confident",
            "explanation": "Management emphasized growth.",
            "confidence": "medium"
          },
          "investment_insights": ["Watch renewal rates"],
          "limitations": ["Excerpt may omit financial statements"]
        }
        """


def test_build_financial_analysis_prompt_includes_required_schema() -> None:
    extraction = FilingExtractionResult(
        document_name="sample-10k",
        text="Revenue increased and margins expanded.",
        page_count=1,
        extracted_page_count=1,
    )

    prompt = build_financial_analysis_prompt(extraction)

    assert "revenue_drivers" in prompt
    assert "risks" in prompt
    assert "key_metrics" in prompt
    assert "Revenue increased" in prompt


def test_parse_financial_analysis_response_maps_json_to_dataclasses() -> None:
    response = """
    {
      "business_overview": "Business summary",
      "revenue_drivers": ["Pricing"],
      "risks": [{"title": "FX", "description": "Currency changes", "severity": "medium"}],
      "mda_themes": ["Cost control"],
      "key_metrics": [{"name": "Gross margin", "value": "45%", "context": "Profitability"}],
      "tone": {"overall_tone": "cautious", "explanation": "Risk language increased", "confidence": "high"},
      "investment_insights": ["Monitor demand"],
      "limitations": ["No full filing context"]
    }
    """

    analysis = parse_financial_analysis_response(response)

    assert analysis.business_overview == "Business summary"
    assert analysis.revenue_drivers == ["Pricing"]
    assert analysis.risks[0].title == "FX"
    assert analysis.key_metrics[0].name == "Gross margin"
    assert analysis.tone.overall_tone == "cautious"


def test_parse_financial_analysis_response_keeps_raw_text_for_invalid_json() -> None:
    analysis = parse_financial_analysis_response("not json")

    assert "valid JSON" in analysis.limitations[0]
    assert analysis.raw_response == "not json"


def test_analyze_financial_document_uses_configured_llm() -> None:
    extraction = FilingExtractionResult(
        document_name="sample-10q",
        text="Revenue increased and competition remains intense.",
        page_count=1,
        extracted_page_count=1,
    )

    analysis = analyze_financial_document(extraction, llm_service=FakeConfiguredLLM())

    assert analysis.business_overview == "The company sells software."
    assert analysis.revenue_drivers == ["Subscription growth", "Enterprise demand"]
    assert analysis.risks[0].severity == "high"


def test_analyze_financial_document_returns_fallback_without_api_key() -> None:
    extraction = FilingExtractionResult(
        document_name="sample-10q",
        text="Revenue increased.",
        page_count=1,
        extracted_page_count=1,
    )

    analysis = analyze_financial_document(extraction, llm_service=FakeUnconfiguredLLM())

    assert "Groq is not configured" in analysis.business_overview
    assert "GROQ_API_KEY" in analysis.limitations[0]

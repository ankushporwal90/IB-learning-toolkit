from src.rag.pipeline import RetrievedChunk
from src.services.financial_metric_service import answer_metric_question, extract_latest_revenue


def test_extract_latest_revenue_from_net_sales_chunk() -> None:
    chunks = [
        RetrievedChunk(
            text=(
                "CONSOLIDATED STATEMENTS OF OPERATIONS - in millions "
                "Net sales 416,161 391,035 383,285"
            ),
            document_name="AAPL 10-K",
            chunk_index=10,
        )
    ]

    metric = extract_latest_revenue(chunks)

    assert metric is not None
    assert metric.value == "$416,161"
    assert metric.unit == "million"
    assert metric.citation == "AAPL 10-K, chunk 10"


def test_answer_metric_question_returns_revenue_answer() -> None:
    chunks = [
        RetrievedChunk(
            text="Total revenue 100,000 90,000 80,000 in millions",
            document_name="MSFT 10-K",
            chunk_index=7,
        )
    ]

    answer = answer_metric_question("What was the latest revenue?", chunks)

    assert answer is not None
    assert "$100,000 million" in answer
    assert "MSFT 10-K, chunk 7" in answer


def test_answer_metric_question_ignores_non_revenue_questions() -> None:
    chunks = [
        RetrievedChunk(text="Net sales 100,000", document_name="AAPL 10-K", chunk_index=1)
    ]

    assert answer_metric_question("What are the main risks?", chunks) is None

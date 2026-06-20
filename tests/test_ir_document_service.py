from src.services.ir_document_service import (
    IrDocumentCandidate,
    discover_ir_pdf_links,
    filter_candidates,
)


class FakeResponse:
    def __init__(self, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        assert headers["User-Agent"]
        assert timeout > 0
        return self.response


def test_discover_ir_pdf_links_returns_matching_absolute_pdf_links() -> None:
    html = """
    <html><body>
      <a href="/files/q1-earnings-presentation.pdf">Q1 Earnings Presentation</a>
      <a href="/files/sustainability.pdf">Sustainability Report</a>
    </body></html>
    """

    candidates = discover_ir_pdf_links(
        "https://example.com/events",
        "Earnings presentation",
        session=FakeSession(FakeResponse(text=html)),
    )

    assert len(candidates) == 1
    assert candidates[0].title == "Q1 Earnings Presentation"
    assert candidates[0].url == "https://example.com/files/q1-earnings-presentation.pdf"


def test_filter_candidates_prefers_requested_report_type_keywords() -> None:
    candidates = [
        IrDocumentCandidate("Corporate Overview", "https://example.com/overview.pdf", "source"),
        IrDocumentCandidate("Q2 Earnings Slides", "https://example.com/q2.pdf", "source"),
    ]

    filtered = filter_candidates(candidates, "Earnings presentation")

    assert filtered == [candidates[1]]
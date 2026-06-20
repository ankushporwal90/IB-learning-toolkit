from src.services.sec_edgar_service import (
    SecCompany,
    SecFiling,
    filing_to_extraction,
    find_latest_filing_metadata,
    html_to_text,
    lookup_company_by_ticker,
)


class FakeResponse:
    def __init__(self, payload: dict | None = None, text: str = "") -> None:
        self.payload = payload or {}
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        assert headers["User-Agent"]
        assert timeout > 0
        return self.response


def test_lookup_company_by_ticker_returns_sec_company() -> None:
    response = FakeResponse(
        {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
        }
    )

    company = lookup_company_by_ticker("aapl", session=FakeSession(response))

    assert company == SecCompany(ticker="AAPL", name="Apple Inc.", cik=320193)


def test_find_latest_filing_metadata_returns_requested_form() -> None:
    filings = {
        "form": ["8-K", "10-Q", "10-K"],
        "accessionNumber": ["a1", "q1", "k1"],
        "filingDate": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "primaryDocument": ["a.htm", "q.htm", "k.htm"],
    }

    metadata = find_latest_filing_metadata(filings, "10-Q")

    assert metadata["accession_number"] == "q1"
    assert metadata["filing_date"] == "2026-02-01"
    assert metadata["primary_document"] == "q.htm"
    assert metadata["form"] == "10-Q"




def test_find_latest_filing_metadata_filters_by_item_when_requested() -> None:
    filings = {
        "form": ["8-K", "8-K"],
        "accessionNumber": ["general", "earnings"],
        "filingDate": ["2026-01-01", "2026-02-01"],
        "primaryDocument": ["general.htm", "earnings.htm"],
        "items": ["7.01,9.01", "2.02,9.01"],
    }

    metadata = find_latest_filing_metadata(filings, "8-K", item_filter="2.02")

    assert metadata["accession_number"] == "earnings"
    assert metadata["primary_document"] == "earnings.htm"

def test_html_to_text_removes_tags_and_normalizes_spacing() -> None:
    text = html_to_text("<html><body><h1>Revenue</h1><p> increased   year over year.</p></body></html>")

    assert text == "Revenue increased year over year."


def test_filing_to_extraction_uses_display_name_and_text() -> None:
    company = SecCompany(ticker="AAPL", name="Apple Inc.", cik=320193)
    filing = SecFiling(
        company=company,
        form="10-K",
        filing_date="2025-10-31",
        accession_number="0000320193-25-000079",
        primary_document="aapl-20250927.htm",
        filing_url="https://www.sec.gov/example",
        text="Business overview text",
    )

    extraction = filing_to_extraction(filing)

    assert extraction.document_name == "AAPL 10-K filed 2025-10-31"
    assert extraction.text == "Business overview text"
    assert extraction.extracted_page_count == 1

"""SEC EDGAR filing lookup and download service.

Phase 1.5 concept:
    Instead of forcing the user to manually find and upload PDFs, we can fetch
    the latest annual and quarterly filings directly from SEC EDGAR.
"""

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import requests

from src.services.phase1_filing_summary import FilingExtractionResult, clean_text
from src.utils.config import get_settings


SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik_padded}.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class SecCompany:
    """Basic SEC company identity."""

    ticker: str
    name: str
    cik: int


@dataclass
class SecFiling:
    """Metadata and text for one downloaded SEC filing."""

    company: SecCompany
    form: str
    filing_date: str
    accession_number: str
    primary_document: str
    filing_url: str
    text: str

    @property
    def display_name(self) -> str:
        """Human-readable filing label for the UI."""

        return f"{self.company.ticker} {self.form} filed {self.filing_date}"


class SecTextParser(HTMLParser):
    """Small HTML-to-text parser for SEC filing documents."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = clean_text(data)
        if cleaned:
            self.parts.append(cleaned)

    def text(self) -> str:
        """Return parsed text with readable spacing."""

        return clean_text(" ".join(self.parts))


def fetch_latest_annual_and_quarterly_filings(ticker: str) -> dict[str, SecFiling]:
    """Fetch the latest 10-K and latest 10-Q for a ticker."""

    return {
        "10-K": fetch_latest_filing(ticker, "10-K"),
        "10-Q": fetch_latest_filing(ticker, "10-Q"),
    }


def fetch_latest_filing(ticker: str, form_type: str) -> SecFiling:
    """Fetch the latest SEC filing for a ticker and form type."""

    company = lookup_company_by_ticker(ticker)
    filings = get_recent_filings(company)
    metadata = find_latest_filing_metadata(filings, form_type)
    return download_filing(company=company, metadata=metadata)


def fetch_latest_earnings_8k(ticker: str) -> SecFiling:
    """Fetch the latest earnings-related 8-K, preferring Item 2.02 when available."""

    company = lookup_company_by_ticker(ticker)
    filings = get_recent_filings(company)
    try:
        metadata = find_latest_filing_metadata(filings, "8-K", item_filter="2.02")
    except ValueError:
        metadata = find_latest_filing_metadata(filings, "8-K")
    return download_filing(company=company, metadata=metadata)


def lookup_company_by_ticker(ticker: str, session: requests.Session | None = None) -> SecCompany:
    """Resolve a stock ticker to SEC company metadata."""

    normalized_ticker = ticker.upper().strip()
    if not normalized_ticker:
        raise ValueError("Enter a stock ticker such as AAPL, MSFT, or NVDA.")

    response = get_session(session).get(
        SEC_TICKER_URL,
        headers=build_sec_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    companies = response.json()

    for company_data in companies.values():
        if company_data.get("ticker", "").upper() == normalized_ticker:
            return SecCompany(
                ticker=company_data["ticker"].upper(),
                name=company_data["title"],
                cik=int(company_data["cik_str"]),
            )

    raise ValueError(f"Could not find SEC company metadata for ticker '{ticker}'.")


def get_recent_filings(
    company: SecCompany,
    session: requests.Session | None = None,
) -> dict[str, list[Any]]:
    """Return recent filing metadata from SEC submissions."""

    cik_padded = str(company.cik).zfill(10)
    response = get_session(session).get(
        SEC_SUBMISSIONS_URL.format(cik_padded=cik_padded),
        headers=build_sec_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["filings"]["recent"]


def find_latest_filing_metadata(
    filings: dict[str, list[Any]],
    form_type: str,
    item_filter: str | None = None,
) -> dict[str, Any]:
    """Find the latest filing row for a specific SEC form type."""

    forms = filings.get("form", [])
    items = filings.get("items", [])
    for index, form in enumerate(forms):
        if form != form_type:
            continue
        if item_filter and item_filter not in str(items[index] if index < len(items) else ""):
            continue
        return {
            "accession_number": filings["accessionNumber"][index],
            "filing_date": filings["filingDate"][index],
            "primary_document": filings["primaryDocument"][index],
            "form": form,
        }

    item_message = f" with Item {item_filter}" if item_filter else ""
    raise ValueError(f"No recent {form_type}{item_message} filing was found for this company.")


def download_filing(
    company: SecCompany,
    metadata: dict[str, Any],
    session: requests.Session | None = None,
) -> SecFiling:
    """Download an SEC filing document and convert it to readable text."""

    accession = metadata["accession_number"].replace("-", "")
    filing_url = SEC_ARCHIVES_URL.format(
        cik=company.cik,
        accession=accession,
        document=metadata["primary_document"],
    )
    response = get_session(session).get(
        filing_url,
        headers=build_sec_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return SecFiling(
        company=company,
        form=metadata["form"],
        filing_date=metadata["filing_date"],
        accession_number=metadata["accession_number"],
        primary_document=metadata["primary_document"],
        filing_url=filing_url,
        text=html_to_text(response.text),
    )


def filing_to_extraction(filing: SecFiling) -> FilingExtractionResult:
    """Convert downloaded SEC filing text into the existing summarization shape."""

    return FilingExtractionResult(
        document_name=filing.display_name,
        text=filing.text,
        page_count=1,
        extracted_page_count=1 if filing.text else 0,
    )


def html_to_text(html: str) -> str:
    """Convert SEC HTML or inline XBRL document content into plain text."""

    parser = SecTextParser()
    parser.feed(html)
    return parser.text()


def build_sec_headers() -> dict[str, str]:
    """Build SEC-friendly request headers."""

    settings = get_settings()
    return {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


def get_session(session: requests.Session | None = None) -> requests.Session:
    """Return provided session or a default requests session."""

    return session or requests.Session()

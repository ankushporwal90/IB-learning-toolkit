"""Investor-relations document discovery for energy company presentations.

Investor presentations and earnings decks are not standardized like SEC filings.
This service uses company-specific IR source pages and a lightweight PDF link finder.
Some IR sites are JavaScript-heavy or block automated requests, so callers should
show the source page as a fallback when no PDF candidate is found.
"""

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests


REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class IrDocumentCandidate:
    """A possible investor-relations PDF document discovered on a company website."""

    title: str
    url: str
    source_url: str


class PdfLinkParser(HTMLParser):
    """Collect links and nearby anchor text from an IR webpage."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[IrDocumentCandidate] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if not href:
            return
        self._active_href = urljoin(self.base_url, href)
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            cleaned = " ".join(data.split())
            if cleaned:
                self._active_text.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_href:
            return
        title = " ".join(self._active_text).strip() or self._active_href.rsplit("/", 1)[-1]
        if ".pdf" in self._active_href.lower():
            self.links.append(
                IrDocumentCandidate(
                    title=title,
                    url=self._active_href,
                    source_url=self.base_url,
                )
            )
        self._active_href = None
        self._active_text = []


def discover_ir_pdf_links(
    source_url: str,
    report_type: str,
    session: requests.Session | None = None,
) -> list[IrDocumentCandidate]:
    """Return likely presentation PDFs from a company IR source page."""

    response = get_session(session).get(
        source_url,
        headers={"User-Agent": "Mozilla/5.0 IB Learning Toolkit learning project"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    parser = PdfLinkParser(source_url)
    parser.feed(response.text)
    return filter_candidates(parser.links, report_type)


def download_ir_pdf(
    candidate: IrDocumentCandidate,
    session: requests.Session | None = None,
) -> bytes:
    """Download a discovered IR PDF candidate."""

    response = get_session(session).get(
        candidate.url,
        headers={"User-Agent": "Mozilla/5.0 IB Learning Toolkit learning project"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content


def filter_candidates(
    candidates: list[IrDocumentCandidate],
    report_type: str,
) -> list[IrDocumentCandidate]:
    """Rank PDF links by whether they look like the requested presentation type."""

    keywords = keywords_for_report_type(report_type)
    scored: list[tuple[int, IrDocumentCandidate]] = []
    for candidate in candidates:
        haystack = f"{candidate.title} {candidate.url}".lower()
        score = sum(1 for keyword in keywords if keyword in haystack)
        if score > 0:
            scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in scored]


def keywords_for_report_type(report_type: str) -> list[str]:
    """Map UI report types to IR webpage search terms."""

    normalized = report_type.lower()
    if "earnings" in normalized:
        return ["earnings", "quarter", "results", "presentation", "slides"]
    if "investor" in normalized:
        return ["investor", "presentation", "overview", "deck", "corporate"]
    return ["presentation", "pdf"]


def get_session(session: requests.Session | None = None) -> requests.Session:
    """Return provided session or a default requests session."""

    return session or requests.Session()
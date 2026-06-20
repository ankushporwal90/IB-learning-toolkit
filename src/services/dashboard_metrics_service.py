"""Dashboard financial metrics for the IB Learning Toolkit.

The dashboard combines two free student-budget sources:
- Yahoo Finance quote endpoint for market data like price and market cap.
- SEC XBRL companyfacts for filing-derived fundamentals like revenue, debt, cash flow, and D&A.

Values can be missing because public APIs differ by company and reporting taxonomy. The
front-end only receives metrics with sourced values; missing items are captured as limitations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from src.services.xbrl_companyfacts_service import (
    XbrlMetric,
    fetch_companyfacts,
    latest_metric_from_companyfacts,
)


YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class DashboardMetric:
    """One sourced metric for the company dashboard."""

    label: str
    value: str
    source: str
    notes: str = ""
    period: str = ""
    source_detail: str = ""


@dataclass
class DashboardMetrics:
    """Collection of market and filing metrics for the dashboard."""

    ticker: str
    company_name: str = ""
    metrics: list[DashboardMetric] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def fetch_dashboard_metrics(
    ticker: str,
    session: requests.Session | None = None,
) -> DashboardMetrics:
    """Fetch market and SEC XBRL metrics for a dashboard ticker."""

    normalized_ticker = ticker.upper().strip()
    metrics: list[DashboardMetric] = []
    limitations: list[str] = []

    try:
        quote = fetch_yahoo_quote(normalized_ticker, session=session)
    except Exception as exc:
        quote = {}
        limitations.append(
            "Yahoo Finance quote data was unavailable, so market price and market cap "
            f"were not displayed. Error: {type(exc).__name__}."
        )

    company, facts = fetch_companyfacts(ticker=normalized_ticker, session=session)

    add_market_metrics(metrics=metrics, quote=quote)
    add_xbrl_metrics(metrics=metrics, limitations=limitations, facts=facts)

    reliable_metrics, missing_metric_labels = split_reliable_metrics(metrics)
    limitations.extend(
        f"{label} was not displayed because no reliable sourced value was available."
        for label in missing_metric_labels
    )

    return DashboardMetrics(
        ticker=normalized_ticker,
        company_name=company.name,
        metrics=reliable_metrics,
        limitations=limitations,
    )


def fetch_yahoo_quote(
    ticker: str,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch quote data from Yahoo Finance's free quote endpoint."""

    response = get_session(session).get(
        YAHOO_QUOTE_URL,
        params={"symbols": ticker},
        headers={"User-Agent": "Mozilla/5.0 IB Learning Toolkit learning project"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    results = response.json().get("quoteResponse", {}).get("result", [])
    return results[0] if results else {}


def add_market_metrics(metrics: list[DashboardMetric], quote: dict[str, Any]) -> None:
    """Append market-data metrics from a Yahoo quote payload."""

    quote_period = format_quote_period(quote)
    quote_source = "Yahoo Finance quote endpoint"
    metrics.extend(
        [
            DashboardMetric(
                label="Share Price",
                value=format_currency(quote.get("regularMarketPrice")),
                source="Yahoo Finance quote",
                notes="Latest available quote from free endpoint.",
                period=quote_period,
                source_detail=quote_source,
            ),
            DashboardMetric(
                label="Market Cap",
                value=format_compact_currency(quote.get("marketCap")),
                source="Yahoo Finance quote",
                notes="Equity value from public market data.",
                period=quote_period,
                source_detail=quote_source,
            ),
            DashboardMetric(
                label="52W Range",
                value=format_range(quote.get("fiftyTwoWeekLow"), quote.get("fiftyTwoWeekHigh")),
                source="Yahoo Finance quote",
                notes="Useful for quick trading-context scan.",
                period=quote_period,
                source_detail=quote_source,
            ),
        ]
    )


def add_xbrl_metrics(
    metrics: list[DashboardMetric],
    limitations: list[str],
    facts: dict[str, Any],
) -> None:
    """Append filing-derived metrics from SEC XBRL companyfacts."""

    revenue = latest_metric_from_companyfacts(facts=facts, metric="revenue")
    operating_income = latest_metric_from_companyfacts(facts=facts, metric="operating_income")
    d_and_a = latest_metric_from_companyfacts(facts=facts, metric="depreciation_and_amortization")
    operating_cash_flow = latest_metric_from_companyfacts(facts=facts, metric="operating_cash_flow")
    capex = latest_metric_from_companyfacts(facts=facts, metric="capital_expenditures")
    cash = latest_metric_from_companyfacts(facts=facts, metric="cash_and_equivalents")
    long_term_debt = latest_metric_from_companyfacts(facts=facts, metric="long_term_debt")
    short_term_debt = latest_metric_from_companyfacts(facts=facts, metric="short_term_debt")

    metrics.append(metric_from_xbrl("FY Revenue", revenue, "SEC XBRL companyfacts"))

    ebitda_inputs = [operating_income, d_and_a]
    ebitda_value = combine_metric_values(ebitda_inputs)
    metrics.append(
        DashboardMetric(
            label="EBITDA Proxy",
            value=format_compact_currency(ebitda_value),
            source="SEC XBRL companyfacts",
            notes="Operating income + D&A. Proxy, not company-adjusted EBITDA.",
            period=combine_metric_period(ebitda_inputs),
            source_detail=combine_metric_source_detail(ebitda_inputs),
        )
    )

    debt_inputs = [long_term_debt, short_term_debt]
    debt_value = combine_metric_values(debt_inputs)
    metrics.append(
        DashboardMetric(
            label="Total Debt",
            value=format_compact_currency(debt_value),
            source="SEC XBRL companyfacts",
            notes="Long-term debt + short-term debt when available.",
            period=combine_metric_period(debt_inputs),
            source_detail=combine_metric_source_detail(debt_inputs),
        )
    )

    net_debt = debt_value - cash.value if debt_value is not None and cash is not None else None
    net_debt_inputs = [long_term_debt, short_term_debt, cash]
    metrics.append(
        DashboardMetric(
            label="Net Debt",
            value=format_compact_currency(net_debt),
            source="SEC XBRL companyfacts",
            notes="Debt less cash and equivalents when both are available.",
            period=combine_metric_period(net_debt_inputs),
            source_detail=combine_metric_source_detail(net_debt_inputs),
        )
    )

    fcf_value = None
    if operating_cash_flow is not None and capex is not None:
        fcf_value = operating_cash_flow.value - abs(capex.value)
    fcf_inputs = [operating_cash_flow, capex]
    metrics.append(
        DashboardMetric(
            label="FCF Proxy",
            value=format_compact_currency(fcf_value),
            source="SEC XBRL companyfacts",
            notes="Operating cash flow less capex. Proxy, not company-defined FCF.",
            period=combine_metric_period(fcf_inputs),
            source_detail=combine_metric_source_detail(fcf_inputs),
        )
    )

    if revenue is None:
        limitations.append("No recent SEC XBRL revenue fact found.")
    if ebitda_value is None:
        limitations.append("EBITDA proxy was unavailable because operating income and D&A were missing.")
    if fcf_value is None:
        limitations.append("FCF proxy was unavailable because operating cash flow or capex was missing.")
    if debt_value is None:
        limitations.append("Debt metrics need long-term or short-term debt facts; none were found.")
    if cash is None:
        limitations.append("Net debt needs a cash and equivalents fact; none was found.")


def split_reliable_metrics(metrics: list[DashboardMetric]) -> tuple[list[DashboardMetric], list[str]]:
    """Separate metrics with real sourced values from unavailable metrics."""

    reliable: list[DashboardMetric] = []
    missing_labels: list[str] = []
    for metric in metrics:
        if is_reliable_metric(metric):
            reliable.append(metric)
        else:
            missing_labels.append(metric.label)
    return reliable, missing_labels


def is_reliable_metric(metric: DashboardMetric) -> bool:
    """Return True when a metric should be shown on the front-end dashboard."""

    value = metric.value.strip().lower()
    return value not in {"", "n/a", "nan", "none"}


def metric_from_xbrl(label: str, metric: XbrlMetric | None, source: str) -> DashboardMetric:
    """Create a display metric from an XBRL fact."""

    if metric is None:
        return DashboardMetric(label=label, value="n/a", source=source, notes="No fact found.")
    return DashboardMetric(
        label=label,
        value=format_compact_currency(metric.value),
        source=source,
        notes="As reported in SEC XBRL companyfacts.",
        period=format_metric_period(metric),
        source_detail=format_metric_source_detail(metric),
    )


def format_quote_period(quote: dict[str, Any]) -> str:
    """Return quote timing when Yahoo provides it."""

    market_time = quote.get("regularMarketTime")
    if market_time is None:
        return "Latest available quote"
    timestamp = datetime.fromtimestamp(float(market_time), tz=timezone.utc)
    return f"Quote timestamp: {timestamp:%Y-%m-%d %H:%M UTC}"


def format_metric_period(metric: XbrlMetric) -> str:
    """Describe the fiscal period for one XBRL fact."""

    return f"FY {metric.fiscal_year} {metric.fiscal_period}"


def format_metric_source_detail(metric: XbrlMetric) -> str:
    """Describe the SEC filing source for one XBRL fact."""

    return f"{metric.form}, filed {metric.filed}, tag {metric.tag}"


def combine_metric_period(metrics: list[XbrlMetric | None]) -> str:
    """Combine fiscal periods used by a derived metric."""

    periods = sorted({format_metric_period(metric) for metric in metrics if metric is not None})
    return "; ".join(periods)


def combine_metric_source_detail(metrics: list[XbrlMetric | None]) -> str:
    """Combine source filings and tags used by a derived metric."""

    details = [format_metric_source_detail(metric) for metric in metrics if metric is not None]
    return " | ".join(details)


def combine_metric_values(metrics: list[XbrlMetric | None]) -> float | None:
    """Sum available XBRL values, returning None when all values are missing."""

    values = [metric.value for metric in metrics if metric is not None]
    return sum(values) if values else None


def format_currency(value: Any) -> str:
    """Format a raw numeric value as dollars."""

    if value is None:
        return "n/a"
    return f"${float(value):,.2f}"


def format_compact_currency(value: Any) -> str:
    """Format large currency values for dashboard cards."""

    if value is None:
        return "n/a"
    numeric = float(value)
    sign = "-" if numeric < 0 else ""
    numeric = abs(numeric)
    if numeric >= 1_000_000_000:
        return f"{sign}${numeric / 1_000_000_000:,.1f}B"
    if numeric >= 1_000_000:
        return f"{sign}${numeric / 1_000_000:,.1f}M"
    return f"{sign}${numeric:,.0f}"


def format_range(low: Any, high: Any) -> str:
    """Format a low/high price range."""

    if low is None or high is None:
        return "n/a"
    return f"${float(low):,.2f} - ${float(high):,.2f}"


def get_session(session: requests.Session | None = None) -> requests.Session:
    """Return provided session or a default requests session."""

    return session or requests.Session()
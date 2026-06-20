"""SEC XBRL companyfacts metric extraction.

Phase 3.8 concept:
    Exact financial metrics should come from structured SEC facts when possible,
    not only from vector retrieval over filing text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from src.services.sec_edgar_service import (
    REQUEST_TIMEOUT_SECONDS,
    SecCompany,
    build_sec_headers,
    get_session,
    lookup_company_by_ticker,
)


COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"


@dataclass
class XbrlMetric:
    """One official SEC XBRL metric fact."""

    label: str
    tag: str
    value: float
    unit: str
    fiscal_year: int
    fiscal_period: str
    form: str
    filed: str
    accession_number: str
    frame: str = ""

    @property
    def formatted_value(self) -> str:
        """Format XBRL value for display."""

        if self.unit == "USD":
            return f"${self.value:,.0f}"
        return f"{self.value:,.0f} {self.unit}"


METRIC_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ],
    "research_and_development": ["ResearchAndDevelopmentExpense"],
    "selling_general_admin": ["SellingGeneralAndAdministrativeExpense"],
    "operating_expenses": ["OperatingExpenses"],
    "interest_income": ["InterestIncomeExpenseNonOperatingNet", "InterestIncomeNonOperating"],
    "interest_expense": ["InterestExpenseNonOperating", "InterestExpense"],
    "income_tax_expense": ["IncomeTaxExpenseBenefit"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
    "net_income": ["NetIncomeLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capital_expenditures": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "CapitalExpenditures",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "depreciation_and_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationExpense",
        "DepreciationAndAmortization",
    ],
    "share_based_compensation": ["ShareBasedCompensation"],
    "accounts_receivable_change": ["IncreaseDecreaseInAccountsReceivable"],
    "inventory_change": ["IncreaseDecreaseInInventories"],
    "accounts_payable_change": ["IncreaseDecreaseInAccountsPayable"],
    "contract_liabilities_change": ["IncreaseDecreaseInContractWithCustomerLiability"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "short_term_debt": ["ShortTermBorrowings", "ShortTermDebt", "LongTermDebtCurrent"],
    "assets": ["Assets"],
}


def fetch_companyfacts(
    ticker: str,
    session: requests.Session | None = None,
) -> tuple[SecCompany, dict[str, Any]]:
    """Fetch SEC companyfacts JSON for a ticker."""

    company = lookup_company_by_ticker(ticker, session=session)
    cik_padded = str(company.cik).zfill(10)
    response = get_session(session).get(
        COMPANYFACTS_URL.format(cik_padded=cik_padded),
        headers=build_sec_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return company, response.json()


def latest_metric_for_ticker(
    ticker: str,
    metric: str,
    annual_only: bool = True,
    session: requests.Session | None = None,
) -> XbrlMetric | None:
    """Return the latest available XBRL metric for a ticker."""

    _, facts = fetch_companyfacts(ticker=ticker, session=session)
    return latest_metric_from_companyfacts(facts=facts, metric=metric, annual_only=annual_only)


def latest_metric_from_companyfacts(
    facts: dict[str, Any],
    metric: str,
    annual_only: bool = True,
) -> XbrlMetric | None:
    """Extract the latest fact for one supported metric from companyfacts JSON."""

    tags = METRIC_TAGS.get(metric, [])
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    candidates: list[XbrlMetric] = []

    for tag in tags:
        tag_data = us_gaap.get(tag)
        if not tag_data:
            continue
        units = tag_data.get("units", {})
        for unit, facts_list in units.items():
            for fact in facts_list:
                if annual_only and fact.get("fp") != "FY":
                    continue
                if fact.get("form") not in {"10-K", "10-Q"}:
                    continue
                value = fact.get("val")
                fiscal_year = fact.get("fy")
                if value is None or fiscal_year is None:
                    continue
                candidates.append(
                    XbrlMetric(
                        label=tag_data.get("label", metric),
                        tag=tag,
                        value=float(value),
                        unit=unit,
                        fiscal_year=int(fiscal_year),
                        fiscal_period=str(fact.get("fp", "")),
                        form=str(fact.get("form", "")),
                        filed=str(fact.get("filed", "")),
                        accession_number=str(fact.get("accn", "")),
                        frame=str(fact.get("frame", "")),
                    )
                )

    if not candidates:
        return None
    return sorted(candidates, key=metric_sort_key, reverse=True)[0]


def metric_sort_key(metric: XbrlMetric) -> tuple[int, str, int, float]:
    """Sort facts toward the latest annual total for a metric."""

    expected_frame = f"CY{metric.fiscal_year}"
    frame_match = 1 if metric.frame == expected_frame else 0
    return (metric.fiscal_year, metric.filed, frame_match, metric.value)


def answer_xbrl_metric_question(ticker: str, question: str) -> str | None:
    """Answer supported metric questions from SEC XBRL facts."""

    metric = detect_metric(question)
    if not metric:
        return None
    fact = latest_metric_for_ticker(ticker=ticker, metric=metric)
    if not fact:
        return None
    return (
        f"From SEC XBRL companyfacts, latest {metric.replace('_', ' ')} is "
        f"**{fact.formatted_value}** for fiscal {fact.fiscal_year} "
        f"({fact.form}, filed {fact.filed}, tag `{fact.tag}`)."
    )


def detect_metric(question: str) -> str | None:
    """Map a user question to a supported XBRL metric key."""

    lowered = question.lower()
    if any(term in lowered for term in ["revenue", "sales", "net sales"]):
        return "revenue"
    if "cost of revenue" in lowered or "cost of sales" in lowered:
        return "cost_of_revenue"
    if "interest income" in lowered:
        return "interest_income"
    if "interest expense" in lowered:
        return "interest_expense"
    if "tax" in lowered:
        return "income_tax_expense"
    if "depreciation" in lowered or "amortization" in lowered:
        return "depreciation_and_amortization"
    if "stock compensation" in lowered or "share based" in lowered or "share-based" in lowered:
        return "share_based_compensation"
    if "net income" in lowered or "profit" in lowered or "earnings" in lowered:
        return "net_income"
    if "operating income" in lowered:
        return "operating_income"
    if "cash flow" in lowered or "operating cash" in lowered:
        return "operating_cash_flow"
    if "assets" in lowered:
        return "assets"
    return None

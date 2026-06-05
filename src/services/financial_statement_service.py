"""Financial statement data extraction for banker workflows.

Phase 4.5 focuses on hard financial data. Narrative RAG is useful, but bankers
also need dependable line items and ratios from structured SEC XBRL facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.services.xbrl_companyfacts_service import (
    XbrlMetric,
    fetch_companyfacts,
    latest_metric_from_companyfacts,
)


@dataclass
class StatementLineItem:
    """One extracted financial statement line item."""

    key: str
    label: str
    value: str
    fiscal_year: int | None
    source_tag: str
    notes: str = ""


@dataclass
class DerivedMetric:
    """One calculated financial metric."""

    label: str
    value: str
    formula: str
    notes: str = ""


@dataclass
class FinancialStatementData:
    """Banker-friendly financial statement extraction package."""

    ticker: str
    company_name: str
    line_items: list[StatementLineItem] = field(default_factory=list)
    derived_metrics: list[DerivedMetric] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


LINE_ITEM_DEFINITIONS: list[tuple[str, str]] = [
    ("revenue", "Revenue / Net Sales"),
    ("cost_of_revenue", "Cost of Revenue / Cost of Sales"),
    ("research_and_development", "Research and Development"),
    ("selling_general_admin", "Selling, General and Administrative"),
    ("operating_expenses", "Operating Expenses"),
    ("operating_income", "Operating Income"),
    ("interest_income", "Interest Income"),
    ("interest_expense", "Interest Expense"),
    ("pretax_income", "Pre-Tax Income"),
    ("income_tax_expense", "Income Tax Expense"),
    ("net_income", "Net Income"),
    ("operating_cash_flow", "Operating Cash Flow"),
    ("depreciation_and_amortization", "Depreciation and Amortization"),
    ("share_based_compensation", "Share-Based Compensation"),
    ("accounts_receivable_change", "Change in Accounts Receivable"),
    ("inventory_change", "Change in Inventory"),
    ("accounts_payable_change", "Change in Accounts Payable"),
    ("contract_liabilities_change", "Change in Contract Liabilities"),
    ("current_assets", "Current Assets"),
    ("current_liabilities", "Current Liabilities"),
    ("long_term_debt", "Long-Term Debt"),
    ("short_term_debt", "Short-Term Debt"),
    ("assets", "Total Assets"),
]


def extract_financial_statement_data(ticker: str) -> FinancialStatementData:
    """Extract financial statement facts and derived metrics from SEC XBRL."""

    company, facts = fetch_companyfacts(ticker=ticker)
    metrics: dict[str, XbrlMetric] = {}
    line_items: list[StatementLineItem] = []
    limitations: list[str] = []

    for key, label in LINE_ITEM_DEFINITIONS:
        metric = latest_metric_from_companyfacts(facts=facts, metric=key)
        if metric:
            metrics[key] = metric
            line_items.append(metric_to_line_item(key=key, label=label, metric=metric))
        else:
            limitations.append(f"No recent SEC XBRL fact found for {label}.")

    latest_year = max(
        (item.fiscal_year for item in line_items if item.fiscal_year is not None),
        default=None,
    )
    if latest_year is not None:
        for item in line_items:
            if item.fiscal_year is not None and item.fiscal_year < latest_year:
                item.notes = f"{item.notes}; older available fact than latest FY {latest_year}"

    return FinancialStatementData(
        ticker=company.ticker,
        company_name=company.name,
        line_items=line_items,
        derived_metrics=build_derived_metrics(metrics),
        limitations=limitations,
    )


def metric_to_line_item(key: str, label: str, metric: XbrlMetric) -> StatementLineItem:
    """Convert one XBRL metric into a display row."""

    return StatementLineItem(
        key=key,
        label=label,
        value=metric.formatted_value,
        fiscal_year=metric.fiscal_year,
        source_tag=metric.tag,
        notes=f"{metric.form}, filed {metric.filed}",
    )


def build_derived_metrics(metrics: dict[str, XbrlMetric]) -> list[DerivedMetric]:
    """Calculate banker-relevant derived metrics from extracted facts."""

    derived: list[DerivedMetric] = []

    effective_tax_rate = safe_ratio(
        numerator=metrics.get("income_tax_expense"),
        denominator=metrics.get("pretax_income"),
    )
    if effective_tax_rate is not None:
        derived.append(
            DerivedMetric(
                label="Effective Tax Rate",
                value=format_percent(effective_tax_rate),
                formula="Income tax expense / pre-tax income",
            )
        )

    debt_value = sum(
        metric.value
        for metric in [metrics.get("long_term_debt"), metrics.get("short_term_debt")]
        if metric is not None
    )
    interest_expense = metrics.get("interest_expense")
    if interest_expense and debt_value:
        derived.append(
            DerivedMetric(
                label="Approximate Effective Interest Rate on Debt",
                value=format_percent(abs(interest_expense.value) / debt_value),
                formula="Interest expense / latest reported debt balance",
                notes="Approximation because average debt balance and note-level coupon schedules may differ.",
            )
        )

    current_assets = metrics.get("current_assets")
    current_liabilities = metrics.get("current_liabilities")
    if current_assets and current_liabilities:
        derived.append(
            DerivedMetric(
                label="Working Capital",
                value=format_currency(current_assets.value - current_liabilities.value),
                formula="Current assets - current liabilities",
            )
        )

    return derived


def safe_ratio(numerator: XbrlMetric | None, denominator: XbrlMetric | None) -> float | None:
    """Safely calculate ratio from two XBRL metrics."""

    if not numerator or not denominator or denominator.value == 0:
        return None
    return numerator.value / denominator.value


def format_percent(value: float) -> str:
    """Format a decimal ratio as a percentage."""

    return f"{value * 100:.2f}%"


def format_currency(value: float) -> str:
    """Format a currency value."""

    return f"${value:,.0f}"


def financial_statement_data_to_markdown(data: FinancialStatementData) -> str:
    """Convert financial statement data to Markdown for memory/export."""

    lines = [f"# Financial Statement Data: {data.company_name} ({data.ticker})", ""]
    lines.append("## Extracted Line Items")
    for item in data.line_items:
        lines.append(
            f"- {item.label}: {item.value} | FY {item.fiscal_year or 'n/a'} | "
            f"Tag: `{item.source_tag}` | {item.notes}"
        )
    lines.extend(["", "## Derived Metrics"])
    for metric in data.derived_metrics:
        lines.append(f"- {metric.label}: {metric.value} | {metric.formula} {metric.notes}")
    if data.limitations:
        lines.extend(["", "## Limitations"])
        lines.extend([f"- {limitation}" for limitation in data.limitations])
    return "\n".join(lines)

from src.services.financial_statement_service import (
    build_derived_metrics,
    financial_statement_data_to_markdown,
    metric_to_line_item,
)
from src.services.xbrl_companyfacts_service import XbrlMetric


def make_metric(tag: str, value: float, fy: int = 2025) -> XbrlMetric:
    return XbrlMetric(
        label=tag,
        tag=tag,
        value=value,
        unit="USD",
        fiscal_year=fy,
        fiscal_period="FY",
        form="10-K",
        filed="2025-10-31",
        accession_number="abc",
        frame="CY2025",
    )


def test_metric_to_line_item_formats_xbrl_fact() -> None:
    metric = make_metric("RevenueFromContractWithCustomerExcludingAssessedTax", 416161000000)

    item = metric_to_line_item("revenue", "Revenue / Net Sales", metric)

    assert item.label == "Revenue / Net Sales"
    assert item.value == "$416,161,000,000"
    assert item.fiscal_year == 2025
    assert item.source_tag == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_build_derived_metrics_calculates_tax_rate_interest_rate_and_working_capital() -> None:
    metrics = {
        "income_tax_expense": make_metric("IncomeTaxExpenseBenefit", 10),
        "pretax_income": make_metric("PretaxIncome", 100),
        "interest_expense": make_metric("InterestExpense", 5),
        "long_term_debt": make_metric("LongTermDebt", 80),
        "short_term_debt": make_metric("ShortTermDebt", 20),
        "current_assets": make_metric("AssetsCurrent", 150),
        "current_liabilities": make_metric("LiabilitiesCurrent", 90),
    }

    derived = build_derived_metrics(metrics)
    values = {metric.label: metric.value for metric in derived}

    assert values["Effective Tax Rate"] == "10.00%"
    assert values["Approximate Effective Interest Rate on Debt"] == "5.00%"
    assert values["Working Capital"] == "$60"


def test_financial_statement_data_to_markdown_includes_line_items() -> None:
    from src.services.financial_statement_service import FinancialStatementData

    data = FinancialStatementData(
        ticker="AAPL",
        company_name="Apple Inc.",
        line_items=[
            metric_to_line_item(
                key="revenue",
                label="Revenue / Net Sales",
                metric=make_metric("RevenueFromContractWithCustomerExcludingAssessedTax", 416161000000),
            )
        ],
    )

    markdown = financial_statement_data_to_markdown(data)

    assert "Apple Inc." in markdown
    assert "Revenue / Net Sales" in markdown
    assert "$416,161,000,000" in markdown

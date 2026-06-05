# Phase 4.5 - Financial Statement Data Engine

## Objective

Build a banker-grade financial statement extraction layer before the IB workflow layer.

The app now extracts SEC XBRL facts for:

- Revenue / net sales
- Cost of revenue / cost of sales
- R&D
- SG&A
- Operating expenses
- Operating income
- Interest income
- Interest expense
- Pre-tax income
- Income tax expense
- Net income
- Operating cash flow
- Depreciation and amortization
- Share-based compensation
- Working-capital adjustment facts
- Current assets and current liabilities
- Short-term and long-term debt
- Total assets

## Derived Metrics

The app calculates:

- Effective tax rate = income tax expense / pre-tax income
- Approximate effective interest rate on debt = interest expense / latest reported debt balance
- Working capital = current assets - current liabilities

## Why This Matters For IB

Bankers need hard numbers before writing a company profile, CIM summary, or diligence question list.

This engine supports:

- Financial snapshot
- Quality of earnings prep
- Working capital review
- Debt and interest cost review
- Tax rate review
- D&A and stock-comp add-back discussion
- Early EBITDA-style thinking

## Architecture

```mermaid
flowchart LR
    Ticker[Ticker] --> SEC[SEC Companyfacts API]
    SEC --> Facts[XBRL Facts]
    Facts --> Lines[Line Item Extractor]
    Lines --> Derived[Derived Metric Calculator]
    Derived --> UI[Financial Statements Tab]
    UI --> Memory[Saved Session Memory]
```

## Limitations

This is not a full accounting model yet.

Known limitations:

- XBRL tag availability varies by company.
- Effective interest rate is approximate without average debt and note-level coupon schedules.
- Depreciation method language is usually narrative, so RAG should supplement XBRL.
- Working capital adjustments may be reported differently by company.
- Later phases can add table rendering and XBRL taxonomy normalization.

## Suggested Exercises

1. Fetch AAPL and extract financial statements.
2. Compare revenue from XBRL with RAG table extraction.
3. Ask RAG for depreciation method language.
4. Add EBITDA-style addbacks using D&A and share-based compensation.
5. Add a warning when a metric is missing or company-specific.

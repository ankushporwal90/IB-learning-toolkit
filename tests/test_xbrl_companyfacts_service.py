from src.services.xbrl_companyfacts_service import (
    detect_metric,
    latest_metric_from_companyfacts,
)


def test_detect_metric_maps_revenue_question() -> None:
    assert detect_metric("What was Apple's latest revenue?") == "revenue"


def test_latest_metric_from_companyfacts_returns_latest_annual_revenue() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": 391035000000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "accn": "old",
                            },
                            {
                                "val": 416161000000,
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "new",
                                "frame": "CY2025",
                            },
                            {
                                "val": 391035000000,
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "new",
                                "frame": "CY2024",
                            },
                        ]
                    },
                }
            }
        }
    }

    metric = latest_metric_from_companyfacts(facts, "revenue")

    assert metric is not None
    assert metric.formatted_value == "$416,161,000,000"
    assert metric.fiscal_year == 2025
    assert metric.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"

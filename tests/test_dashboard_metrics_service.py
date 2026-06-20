from src.services.dashboard_metrics_service import (
    add_market_metrics,
    fetch_yahoo_quote,
    format_compact_currency,
    format_range,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, url: str, params: dict, headers: dict[str, str], timeout: int) -> FakeResponse:
        assert params["symbols"] == "ET"
        assert headers["User-Agent"]
        assert timeout > 0
        return self.response


def test_fetch_yahoo_quote_returns_first_quote_result() -> None:
    response = FakeResponse(
        {
            "quoteResponse": {
                "result": [
                    {
                        "symbol": "ET",
                        "regularMarketPrice": 18.25,
                        "marketCap": 62_000_000_000,
                    }
                ]
            }
        }
    )

    quote = fetch_yahoo_quote("ET", session=FakeSession(response))

    assert quote["symbol"] == "ET"
    assert quote["marketCap"] == 62_000_000_000


def test_add_market_metrics_formats_quote_values() -> None:
    metrics = []

    add_market_metrics(
        metrics,
        {
            "regularMarketPrice": 18.25,
            "marketCap": 62_000_000_000,
            "fiftyTwoWeekLow": 14.0,
            "fiftyTwoWeekHigh": 21.5,
        },
    )

    assert [metric.label for metric in metrics] == ["Share Price", "Market Cap", "52W Range"]
    assert metrics[0].value == "$18.25"
    assert metrics[1].value == "$62.0B"
    assert metrics[2].value == "$14.00 - $21.50"


def test_format_helpers_handle_missing_and_negative_values() -> None:
    assert format_compact_currency(None) == "n/a"
    assert format_compact_currency(-1_500_000_000) == "-$1.5B"
    assert format_range(None, 10) == "n/a"

def test_fetch_dashboard_metrics_continues_when_quote_fails(monkeypatch) -> None:
    from src.services import dashboard_metrics_service as service
    from src.services.sec_edgar_service import SecCompany

    def raise_quote_error(ticker: str, session=None):
        raise RuntimeError("blocked")

    def fake_fetch_companyfacts(ticker: str, session=None):
        return SecCompany(ticker="ET", name="Energy Transfer LP", cik=1276187), {"facts": {"us-gaap": {}}}

    monkeypatch.setattr(service, "fetch_yahoo_quote", raise_quote_error)
    monkeypatch.setattr(service, "fetch_companyfacts", fake_fetch_companyfacts)

    data = service.fetch_dashboard_metrics("ET")

    assert data.ticker == "ET"
    assert data.metrics[0].label == "Share Price"
    assert data.metrics[0].value == "n/a"
    assert any("Yahoo Finance quote data was unavailable" in item for item in data.limitations)
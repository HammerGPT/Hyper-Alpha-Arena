import time
from datetime import date

from services import adanos_sentiment
from services.adanos_sentiment import (
    AdanosConfig,
    _date_window,
    build_adanos_sentiment_context,
    parse_adanos_variables,
)


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_parse_adanos_prompt_variables():
    variables = parse_adanos_variables(
        "{adanos_sentiment}\n{adanos_sentiment_14d}\n{BTC_adanos_sentiment}\n{ETH_adanos_sentiment_30d}"
    )

    assert variables == {
        "adanos_sentiment": {"symbol": None, "days": 7},
        "adanos_sentiment_14d": {"symbol": None, "days": 14},
        "BTC_adanos_sentiment": {"symbol": "BTC", "days": 7},
        "ETH_adanos_sentiment_30d": {"symbol": "ETH", "days": 30},
    }


def test_date_window_uses_inclusive_lookback_days():
    assert _date_window(7, today=date(2026, 6, 27)) == ("2026-06-21", "2026-06-27")


def test_disabled_adanos_variable_does_not_fetch(monkeypatch):
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    monkeypatch.setenv("ADANOS_DISABLE", "0")

    context = build_adanos_sentiment_context("{BTC_adanos_sentiment}", ["BTC"])

    assert context == {
        "BTC_adanos_sentiment": (
            "Adanos sentiment unavailable: set ADANOS_API_KEY to enable this optional data source."
        )
    }


def test_builds_symbol_and_global_context(monkeypatch):
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        symbol = url.rsplit("/", 1)[-1]
        return _Response(
            payload={
                "data": {
                    "symbol": symbol,
                    "found": True,
                    "sentiment_score": 0.31,
                    "buzz_score": 64.2,
                    "mention_count": 123,
                    "bullish_ratio": 0.43,
                    "bearish_ratio": 0.19,
                    "trend": "rising",
                }
            }
        )

    monkeypatch.setattr(adanos_sentiment.requests, "get", fake_get)

    context = build_adanos_sentiment_context(
        "{adanos_sentiment}\n{BTC_adanos_sentiment}",
        ["BTC", "ETH"],
        cfg=AdanosConfig(
            api_base="https://api.example.test/reddit/crypto/v1",
            api_key="sk_test",
            request_timeout_s=3,
            total_timeout_s=10,
            max_symbols=2,
            max_workers=2,
        ),
    )

    assert "Adanos crypto sentiment (7d):" in context["adanos_sentiment"]
    assert (
        "BTC: sentiment=0.31, buzz=64.20, mentions=123"
        in context["BTC_adanos_sentiment"]
    )
    assert len(calls) == 2
    assert calls[0]["headers"] == {"X-API-Key": "sk_test"}
    assert set(calls[0]["params"]) == {"from", "to"}
    assert calls[0]["timeout"] == 3


def test_prompt_generation_validator_accepts_adanos_variables():
    from services.ai_prompt_generation_service import _validate_variable

    assert _validate_variable("adanos_sentiment")
    assert _validate_variable("adanos_sentiment_14d")
    assert _validate_variable("BTC_adanos_sentiment")
    assert _validate_variable("ETH_adanos_sentiment_30d")


def test_fetches_distinct_lookback_windows(monkeypatch):
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(params)
        return _Response(
            payload={
                "symbol": "BTC",
                "found": True,
                "sentiment_score": 0.2,
                "buzz_score": 20,
                "mentions": 10,
            }
        )

    monkeypatch.setattr(adanos_sentiment.requests, "get", fake_get)

    context = build_adanos_sentiment_context(
        "{BTC_adanos_sentiment}\n{BTC_adanos_sentiment_30d}",
        ["BTC"],
        cfg=AdanosConfig(api_key="sk_test", max_workers=1),
    )

    assert "BTC_adanos_sentiment" in context
    assert "BTC_adanos_sentiment_30d" in context
    assert len(calls) == 2
    assert calls[0] != calls[1]


def test_explicit_symbol_variables_respect_symbol_cap(monkeypatch):
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(url)
        symbol = url.rsplit("/", 1)[-1]
        return _Response(payload={"symbol": symbol, "found": True, "mentions": 1})

    monkeypatch.setattr(adanos_sentiment.requests, "get", fake_get)

    context = build_adanos_sentiment_context(
        "{BTC_adanos_sentiment}\n{ETH_adanos_sentiment}\n{SOL_adanos_sentiment}",
        [],
        cfg=AdanosConfig(api_key="sk_test", max_symbols=2, max_workers=2),
    )

    assert len(calls) == 2
    assert "BTC: sentiment=N/A" in context["BTC_adanos_sentiment"]
    assert "ETH: sentiment=N/A" in context["ETH_adanos_sentiment"]
    assert context["SOL_adanos_sentiment"] == (
        "SOL: Adanos sentiment unavailable for the last 7d."
    )


def test_explicit_symbol_variables_have_priority_over_global_fanout(monkeypatch):
    calls = []

    def fake_get(url, headers, params, timeout):
        symbol = url.rsplit("/", 1)[-1]
        calls.append(symbol)
        return _Response(payload={"symbol": symbol, "found": True, "mentions": 1})

    monkeypatch.setattr(adanos_sentiment.requests, "get", fake_get)

    context = build_adanos_sentiment_context(
        "{adanos_sentiment}\n{SOL_adanos_sentiment}",
        ["BTC", "ETH", "DOGE", "XRP"],
        cfg=AdanosConfig(api_key="sk_test", max_symbols=2, max_workers=2),
    )

    assert set(calls) == {"SOL", "BTC"}
    assert len(calls) == 2
    assert "SOL: sentiment=N/A" in context["SOL_adanos_sentiment"]


def test_404_is_rendered_as_no_data(monkeypatch):
    monkeypatch.setattr(
        adanos_sentiment.requests,
        "get",
        lambda *args, **kwargs: _Response(status_code=404),
    )

    context = build_adanos_sentiment_context(
        "{DOGE_adanos_sentiment}",
        ["DOGE"],
        cfg=AdanosConfig(api_key="sk_test"),
    )

    assert context["DOGE_adanos_sentiment"] == (
        "DOGE: no Adanos sentiment available for the last 7d."
    )


def test_total_timeout_returns_fail_open_context(monkeypatch):
    def slow_fetch(*args, **kwargs):
        time.sleep(0.1)
        return {"symbol": "BTC", "found": True}

    monkeypatch.setattr(adanos_sentiment, "_fetch_symbol", slow_fetch)

    context = build_adanos_sentiment_context(
        "{adanos_sentiment}",
        ["BTC"],
        cfg=AdanosConfig(api_key="sk_test", total_timeout_s=0.01, max_workers=1),
    )

    assert "- BTC: Adanos sentiment unavailable." in context["adanos_sentiment"]
    assert "timed out after 0.0s total budget" in context["adanos_sentiment"]

"""
Optional Adanos Market Sentiment prompt variables.

The integration is intentionally prompt-scoped: no API key means no runtime
effect unless a template explicitly references an Adanos variable.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

import requests


DEFAULT_API_BASE = "https://api.adanos.org/reddit/crypto/v1"
DEFAULT_LOOKBACK_DAYS = 7

GLOBAL_PATTERN = re.compile(r"\{(adanos_sentiment(?:_(\d+)d)?)\}")
SYMBOL_PATTERN = re.compile(r"\{([A-Za-z0-9]{1,20})_adanos_sentiment(?:_(\d+)d)?\}")


@dataclass(frozen=True)
class AdanosConfig:
    api_base: str = DEFAULT_API_BASE
    api_key: Optional[str] = None
    request_timeout_s: float = 5.0
    total_timeout_s: float = 20.0
    max_symbols: int = 8
    max_workers: int = 4

    @classmethod
    def from_env(cls) -> "AdanosConfig":
        return cls(
            api_base=(os.getenv("ADANOS_API_BASE") or DEFAULT_API_BASE)
            .strip()
            .rstrip("/"),
            api_key=(os.getenv("ADANOS_API_KEY") or "").strip() or None,
            request_timeout_s=float(os.getenv("ADANOS_TIMEOUT_S") or "5"),
            total_timeout_s=float(os.getenv("ADANOS_TOTAL_TIMEOUT_S") or "20"),
            max_symbols=max(1, int(os.getenv("ADANOS_SYMBOL_MAX") or "8")),
            max_workers=max(1, int(os.getenv("ADANOS_MAX_WORKERS") or "4")),
        )


def adanos_prompt_variables_enabled(cfg: Optional[AdanosConfig] = None) -> bool:
    if (os.getenv("ADANOS_DISABLE") or "").lower() in ("1", "true", "yes"):
        return False
    if cfg:
        return bool(cfg.api_key)
    return bool((os.getenv("ADANOS_API_KEY") or "").strip())


def _parse_days(raw_days: Optional[str]) -> int:
    if not raw_days:
        return DEFAULT_LOOKBACK_DAYS
    return min(365, max(1, int(raw_days)))


def parse_adanos_variables(template_text: str) -> Dict[str, Dict[str, Any]]:
    if not template_text:
        return {}

    variables: Dict[str, Dict[str, Any]] = {}
    for match in GLOBAL_PATTERN.finditer(template_text):
        var_name, days = match.groups()
        variables[var_name] = {"symbol": None, "days": _parse_days(days)}

    for match in SYMBOL_PATTERN.finditer(template_text):
        symbol, days = match.groups()
        var_name = f"{symbol}_adanos_sentiment" + (f"_{days}d" if days else "")
        variables[var_name] = {"symbol": symbol.upper(), "days": _parse_days(days)}

    return variables


def _symbols_for_variables(
    variables: Dict[str, Dict[str, Any]],
    selected_symbols: List[str],
    max_symbols: int,
) -> List[str]:
    symbols: List[str] = []
    seen: Set[str] = set()

    def add(symbol: str) -> None:
        normalized = (
            str(symbol).upper().strip().replace("/USDT", "").replace("-USDT", "")
        )
        if normalized and normalized not in seen and len(symbols) < max_symbols:
            seen.add(normalized)
            symbols.append(normalized)

    for spec in variables.values():
        if spec.get("symbol"):
            add(spec["symbol"])

    if any(spec.get("symbol") is None for spec in variables.values()):
        for symbol in selected_symbols:
            add(symbol)

    return symbols


def _date_window(days: int, today: Optional[date] = None) -> tuple[str, str]:
    end = today or datetime.now(timezone.utc).date()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _fetch_symbol(symbol: str, days: int, cfg: AdanosConfig) -> Dict[str, Any]:
    start, end = _date_window(days)
    response = requests.get(
        f"{cfg.api_base}/token/{quote(symbol, safe='')}",
        headers={"X-API-Key": cfg.api_key or ""},
        params={"from": start, "to": end},
        timeout=cfg.request_timeout_s,
    )
    if response.status_code == 404:
        return {"symbol": symbol, "found": False}
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Adanos response is not a JSON object")
    return _normalize_payload(symbol, payload)


def _first_value(payload: Dict[str, Any], *names: str) -> Any:
    for name in names:
        value = payload.get(name)
        if value is not None:
            return value
    return None


def _normalize_payload(symbol: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data")
    source = data if isinstance(data, dict) else payload

    bullish = _first_value(source, "bullish_pct", "bullish_percentage", "bullish_ratio")
    bearish = _first_value(source, "bearish_pct", "bearish_percentage", "bearish_ratio")
    if isinstance(bullish, float) and 0 <= bullish <= 1:
        bullish *= 100
    if isinstance(bearish, float) and 0 <= bearish <= 1:
        bearish *= 100

    return {
        "symbol": str(source.get("symbol") or payload.get("symbol") or symbol).upper(),
        "found": source.get("found", True),
        "sentiment_score": _first_value(
            source, "sentiment_score", "sentiment", "score"
        ),
        "buzz_score": _first_value(source, "buzz_score", "buzzScore"),
        "mentions": _first_value(source, "mentions", "mention_count", "mentionCount"),
        "bullish_pct": bullish,
        "bearish_pct": bearish,
        "trend": source.get("trend"),
    }


def _fetch_sentiment_rows(
    requests_to_fetch: List[tuple[str, int]],
    cfg: AdanosConfig,
) -> tuple[Dict[tuple[str, int], Dict[str, Any]], List[str]]:
    rows: Dict[tuple[str, int], Dict[str, Any]] = {}
    errors: List[str] = []
    if not requests_to_fetch:
        return rows, errors

    executor = ThreadPoolExecutor(
        max_workers=min(cfg.max_workers, len(requests_to_fetch))
    )
    futures = {
        executor.submit(_fetch_symbol, symbol, days, cfg): (symbol, days)
        for symbol, days in requests_to_fetch
    }
    done, pending = wait(futures, timeout=cfg.total_timeout_s)

    for future in done:
        symbol, days = futures[future]
        try:
            rows[(symbol, days)] = future.result()
        except Exception as exc:
            errors.append(f"{symbol}/{days}d: {exc}")

    for future in pending:
        symbol, days = futures[future]
        future.cancel()
        errors.append(
            f"{symbol}/{days}d: timed out after {cfg.total_timeout_s:.1f}s total budget"
        )

    executor.shutdown(wait=False, cancel_futures=True)
    return rows, errors


def _fmt_number(value: Any, suffix: str = "") -> str:
    if isinstance(value, int):
        return f"{value}{suffix}"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return "N/A"


def _format_row(row: Dict[str, Any], days: int) -> str:
    symbol = str(row.get("symbol") or "UNKNOWN").upper()
    if row.get("found") is False:
        return f"{symbol}: no Adanos sentiment available for the last {days}d."

    return (
        f"{symbol}: sentiment={_fmt_number(row.get('sentiment_score'))}, "
        f"buzz={_fmt_number(row.get('buzz_score'))}, mentions={_fmt_number(row.get('mentions'))}, "
        f"bullish={_fmt_number(row.get('bullish_pct'), '%')}, "
        f"bearish={_fmt_number(row.get('bearish_pct'), '%')}, "
        f"trend={row.get('trend') or 'N/A'}"
    )


def build_adanos_sentiment_context(
    template_text: str,
    selected_symbols: List[str],
    *,
    cfg: Optional[AdanosConfig] = None,
) -> Dict[str, str]:
    variables = parse_adanos_variables(template_text)
    if not variables:
        return {}

    cfg = cfg or AdanosConfig.from_env()
    if not adanos_prompt_variables_enabled(cfg):
        return {
            name: "Adanos sentiment unavailable: set ADANOS_API_KEY to enable this optional data source."
            for name in variables
        }

    symbols = _symbols_for_variables(variables, selected_symbols, cfg.max_symbols)
    allowed_symbols = set(symbols)
    requests_to_fetch: List[tuple[str, int]] = []
    seen_requests: Set[tuple[str, int]] = set()

    def add_fetch(symbol: str, days: int) -> None:
        key = (symbol, days)
        if key not in seen_requests:
            seen_requests.add(key)
            requests_to_fetch.append(key)

    for spec in variables.values():
        days = int(spec["days"])
        if spec.get("symbol"):
            if spec["symbol"] in allowed_symbols:
                add_fetch(spec["symbol"], days)
        else:
            for symbol in symbols:
                add_fetch(symbol, days)

    rows, errors = _fetch_sentiment_rows(requests_to_fetch, cfg)
    context: Dict[str, str] = {}

    for name, spec in variables.items():
        days = int(spec["days"])
        if spec.get("symbol"):
            symbol = spec["symbol"]
            row = rows.get((symbol, days))
            context[name] = (
                _format_row(row, days)
                if row
                else f"{symbol}: Adanos sentiment unavailable for the last {days}d."
            )
            continue

        lines = [f"Adanos crypto sentiment ({days}d):"]
        for symbol in symbols:
            row = rows.get((symbol, days))
            lines.append(
                f"- {_format_row(row, days)}"
                if row
                else f"- {symbol}: Adanos sentiment unavailable."
            )
        if errors:
            lines.append(f"Partial errors: {'; '.join(errors[:3])}")
        context[name] = "\n".join(lines)

    return context

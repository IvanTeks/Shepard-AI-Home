from __future__ import annotations

import csv
import io
import json
import math
import ssl
import statistics
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


STOOQ_DOWNLOAD = "https://stooq.com/q/d/l/"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
NASDAQ_IPO_CALENDAR = "https://api.nasdaq.com/api/ipo/calendar"
DEFAULT_MARKET_CONFIG = Path(__file__).resolve().parents[1] / "config" / "market-watchlist.json"


def _trusted_ssl_context() -> ssl.SSLContext:
    candidates = [
        ssl.get_default_verify_paths().cafile,
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


@dataclass(frozen=True)
class PriceSnapshot:
    symbol: str
    as_of: str
    price: float
    change_1d: float | None
    change_5d: float | None
    change_20d: float | None
    change_60d: float | None
    volatility_20d: float | None
    drawdown_60d: float | None
    volume_ratio_20d: float | None
    source_url: str


def load_market_config(path: str | Path | None = None) -> tuple[float, list[str]]:
    config_path = Path(path or DEFAULT_MARKET_CONFIG)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    price_cap = float(raw.get("price_cap_usd", 50))
    if not 1 <= price_cap <= 10_000:
        raise ValueError("Market price cap must be between $1 and $10,000")
    symbols: list[str] = []
    for value in raw.get("symbols", []):
        symbol = str(value).strip().upper()
        if symbol and symbol.replace("-", "").isalnum() and symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        raise ValueError("Market watchlist must contain at least one ticker symbol")
    return price_cap, symbols[:80]


def _download_text(url: str, *, headers: dict[str, str] | None = None,
                   timeout: float = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Shepard-Hen/0.1 (+https://github.com/IvanTeks/Shepard-AI-Home)",
                 **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout, context=_trusted_ssl_context()) as response:
        return response.read().decode("utf-8", errors="replace")


def _percent(current: float, earlier: float) -> float | None:
    if earlier <= 0:
        return None
    return (current / earlier - 1) * 100


def parse_stooq_history(symbol: str, text: str, *, source_url: str) -> PriceSnapshot:
    rows: list[dict[str, float | str]] = []
    for raw in csv.DictReader(io.StringIO(text)):
        try:
            rows.append({
                "date": str(raw["Date"]),
                "close": float(raw["Close"]),
                "volume": float(raw.get("Volume") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda row: str(row["date"]))
    if len(rows) < 2:
        raise ValueError(f"No usable daily price history returned for {symbol}")
    rows = rows[-90:]
    closes = [float(row["close"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    current = closes[-1]

    def change(sessions: int) -> float | None:
        return _percent(current, closes[-sessions - 1]) if len(closes) > sessions else None

    daily_returns = [closes[index] / closes[index - 1] - 1
                     for index in range(max(1, len(closes) - 20), len(closes))
                     if closes[index - 1] > 0]
    volatility = (
        statistics.pstdev(daily_returns) * math.sqrt(252) * 100
        if len(daily_returns) >= 2 else None
    )
    high_60 = max(closes[-60:])
    average_volume = statistics.fmean(volumes[-20:]) if volumes[-20:] else 0
    return PriceSnapshot(
        symbol=symbol,
        as_of=str(rows[-1]["date"]),
        price=current,
        change_1d=change(1),
        change_5d=change(5),
        change_20d=change(20),
        change_60d=change(60),
        volatility_20d=volatility,
        drawdown_60d=_percent(current, high_60),
        volume_ratio_20d=(volumes[-1] / average_volume if average_volume > 0 else None),
        source_url=source_url,
    )


def fetch_price_snapshot(symbol: str, *, downloader: Callable[..., str] = _download_text,
                         today: date | None = None) -> PriceSnapshot:
    del today  # The chart endpoint supplies a rolling three-month window.
    query = urllib.parse.urlencode({
        "range": "3mo", "interval": "1d", "events": "div,splits",
    })
    url = f"{YAHOO_CHART}{urllib.parse.quote(symbol)}?{query}"
    payload = json.loads(downloader(url))
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        closes = quote["close"]
        volumes = quote["volume"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"No usable daily chart returned for {symbol}") from exc
    rows = []
    for stamp, close, volume in zip(timestamps, closes, volumes):
        if close is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(int(stamp), timezone.utc).date().isoformat(),
            "close": float(close),
            "volume": float(volume or 0),
        })
    csv_text = "Date,Close,Volume\n" + "\n".join(
        f"{row['date']},{row['close']},{row['volume']}" for row in rows
    )
    return parse_stooq_history(symbol, csv_text, source_url=url)


def fetch_ipo_calendar(*, downloader: Callable[..., str] = _download_text,
                       today: date | None = None) -> list[dict[str, str]]:
    """Read Nasdaq's public calendar; every item still requires SEC/source verification."""
    current = today or datetime.now(timezone.utc).date()
    url = f"{NASDAQ_IPO_CALENDAR}?{urllib.parse.urlencode({'date': current.strftime('%Y-%m')})}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nasdaq.com/market-activity/ipos",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
        ),
    }
    try:
        raw = downloader(url, headers=headers)
    except urllib.error.HTTPError as exc:
        if exc.code != 403 or downloader is not _download_text:
            raise
        command = ["curl", "-fsSL", "--max-time", "20"]
        for key, value in headers.items():
            command.extend(["-H", f"{key}: {value}"])
        command.append(url)
        completed = subprocess.run(command, capture_output=True, text=True, timeout=25, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Nasdaq calendar request failed") from exc
        raw = completed.stdout
    payload = json.loads(raw)
    data = payload.get("data") or {}
    candidates: list[dict[str, str]] = []
    groups = (
        ("upcoming", ((data.get("upcoming") or {}).get("upcomingTable") or {}).get("rows") or []),
        ("priced", (data.get("priced") or {}).get("rows") or []),
    )
    for status, rows in groups:
        for row in rows:
            candidates.append({
                "status": status,
                "symbol": str(row.get("proposedTickerSymbol") or "").strip(),
                "company": str(row.get("companyName") or "").strip(),
                "exchange": str(row.get("proposedExchange") or "").strip(),
                "price": str(row.get("proposedSharePrice") or "Not stated").strip(),
                "date": str(row.get("expectedPriceDate") or row.get("pricedDate") or "Not stated").strip(),
                "source_url": url,
            })
    return candidates[:30]


def _metric(value: float | None, *, suffix: str = "%") -> str:
    return "n/a" if value is None else f"{value:+.2f}{suffix}"


def collect_market_evidence(config_path: str | Path | None = None, *,
                            downloader: Callable[..., str] = _download_text) -> str:
    price_cap, symbols = load_market_config(config_path)
    snapshots: list[PriceSnapshot] = []
    warnings: list[str] = []
    for symbol in symbols:
        try:
            snapshots.append(fetch_price_snapshot(symbol, downloader=downloader))
        except Exception as exc:  # A partial brief is safer than inventing a missing quote.
            warnings.append(f"{symbol}: {exc}")
    try:
        filings = fetch_ipo_calendar(downloader=downloader)
    except Exception as exc:
        filings = []
        warnings.append(f"Nasdaq IPO calendar: {exc}")
    if not snapshots and not filings:
        raise RuntimeError("Hen could not reach any configured public market source")

    eligible = sorted(
        (item for item in snapshots if item.price <= price_cap),
        key=lambda item: (item.change_20d is None, -(item.change_20d or -10_000)),
    )
    lines = [
        "# Hen market evidence packet",
        f"Collected: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Owner price filter: closing price at or below ${price_cap:.2f}",
        "Scope warning: this is a configured watchlist scan, not the entire market. A low share price does not mean a company is inexpensive or suitable; fractional shares can make higher-priced securities accessible.",
        "Price source: Yahoo Finance public chart responses (no API key). This is an unofficial integration that can change; prices may be delayed and must be rechecked with a broker before any decision.",
        "IPO source: Nasdaq's public IPO calendar. Calendar entries can change and are not proof that an offering will occur; verify each candidate against its SEC registration statement and final prospectus.",
        "",
        "## Watchlist securities currently within the price filter",
        "| Symbol | As of | Close | 1d | 5d | 20d | 60d | 20d ann. volatility | Drawdown from 60d high | Volume / 20d avg | Source |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if eligible:
        for item in eligible:
            lines.append(
                f"| {item.symbol} | {item.as_of} | ${item.price:.2f} | {_metric(item.change_1d)} | "
                f"{_metric(item.change_5d)} | {_metric(item.change_20d)} | {_metric(item.change_60d)} | "
                f"{_metric(item.volatility_20d)} | {_metric(item.drawdown_60d)} | "
                f"{_metric(item.volume_ratio_20d, suffix='x')} | {item.source_url} |"
            )
    else:
        lines.append("| None | — | — | — | — | — | — | — | — | — | — |")

    positive_both = [item.symbol for item in eligible
                     if (item.change_20d or 0) > 0 and (item.change_60d or 0) > 0]
    lower_volatility = [item.symbol for item in eligible
                        if item.volatility_20d is not None and item.volatility_20d <= 30]
    high_volatility = [item.symbol for item in eligible
                       if item.volatility_20d is not None and item.volatility_20d >= 50]
    deep_drawdown = [item.symbol for item in eligible
                     if item.drawdown_60d is not None and item.drawdown_60d <= -20]
    unusual_volume = [item.symbol for item in eligible
                      if item.volume_ratio_20d is not None and item.volume_ratio_20d >= 1.5]
    lines.extend([
        "",
        "## Mechanical screen labels (descriptive, not recommendations)",
        f"- Positive 20-day and 60-day price change: {', '.join(positive_both) or 'None'}.",
        f"- Lower measured 20-day annualized volatility (30% or less): {', '.join(lower_volatility) or 'None'}.",
        f"- High measured volatility (50% or more): {', '.join(high_volatility) or 'None'}.",
        f"- At least 20% below the 60-day high: {', '.join(deep_drawdown) or 'None'}.",
        f"- Latest volume at least 1.5× the 20-day average: {', '.join(unusual_volume) or 'None'}.",
        "These labels describe the supplied price series only. They do not measure valuation, profitability, debt, dilution, competitive position, or suitability.",
    ])

    lines.extend(["", "## IPO calendar signals requiring SEC verification"])
    if filings:
        for filing in filings:
            lines.append(
                f"- {filing['date']} · {filing['status']} · {filing['symbol'] or 'symbol pending'} · "
                f"{filing['company'] or 'company unavailable'} · proposed price {filing['price']} · "
                f"{filing['exchange'] or 'exchange unavailable'} · {filing['source_url']}"
            )
    else:
        lines.append("- Nasdaq IPO calendar unavailable or empty during this run.")
    if warnings:
        lines.extend(["", "## Collection warnings", *[f"- {warning}" for warning in warnings]])
    return "\n".join(lines)[:48_000]

"""Symbol normalization for crypto and forex."""

from __future__ import annotations

from dataclasses import dataclass

CRYPTO_QUOTES = {"USDT", "USDC", "BUSD", "USD", "BTC", "ETH", "EUR"}
FOREX_QUOTES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "CNH", "MXN", "ZAR"}
COMMODITIES = {"XAUUSD", "XAGUSD", "WTIUSD", "BRENT"}


@dataclass(frozen=True)
class Instrument:
    raw: str
    base: str
    quote: str
    market: str  # "crypto" | "forex" | "commodity"

    @property
    def ccxt_symbol(self) -> str:
        return f"{self.base}/{self.quote}"

    @property
    def yf_symbol(self) -> str:
        if self.market == "forex":
            return f"{self.base}{self.quote}=X"
        if self.market == "commodity":
            return self.raw
        return f"{self.base}-{self.quote}"

    @property
    def display(self) -> str:
        return f"{self.base}/{self.quote}"


def parse_symbol(raw: str) -> Instrument:
    s = raw.strip().upper().replace(" ", "")
    s = s.replace("-", "").replace("_", "").replace("/", "")

    if s in COMMODITIES:
        return Instrument(raw=s, base=s[:3], quote=s[3:], market="commodity")

    if s.endswith("USDT"):
        return Instrument(raw=raw, base=s[:-4], quote="USDT", market="crypto")
    if s.endswith("USDC"):
        return Instrument(raw=raw, base=s[:-4], quote="USDC", market="crypto")
    if s.endswith("BUSD"):
        return Instrument(raw=raw, base=s[:-4], quote="BUSD", market="crypto")

    if len(s) == 6:
        base, quote = s[:3], s[3:]
        if quote in FOREX_QUOTES and base in FOREX_QUOTES | {"XAU", "XAG"}:
            market = "commodity" if base in {"XAU", "XAG"} else "forex"
            return Instrument(raw=raw, base=base, quote=quote, market=market)
        if quote in CRYPTO_QUOTES:
            return Instrument(raw=raw, base=base, quote=quote, market="crypto")

    if len(s) >= 6:
        for q_len in (4, 3):
            quote = s[-q_len:]
            base = s[:-q_len]
            if quote in CRYPTO_QUOTES and base:
                return Instrument(raw=raw, base=base, quote=quote, market="crypto")

    raise ValueError(f"Unknown symbol: {raw}")


TIMEFRAME_TO_MINUTES: dict[str, int] = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "1d": 1440,
    "1w": 10080,
}


def yf_interval(tf: str) -> str:
    """Map our timeframe to a yfinance interval."""
    mapping = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "60m",
        "4h": "1h",  # yfinance has no 4h, we resample externally
        "1d": "1d",
        "1w": "1wk",
    }
    return mapping.get(tf, "15m")


def yf_period(tf: str) -> str:
    """Reasonable history period for a timeframe so we have enough candles."""
    mapping = {
        "1m": "5d",
        "5m": "1mo",
        "15m": "1mo",
        "30m": "2mo",
        "1h": "3mo",
        "4h": "6mo",
        "1d": "2y",
        "1w": "5y",
    }
    return mapping.get(tf, "1mo")

"""Unified market data layer for crypto (CCXT) and forex (yfinance / Twelve Data)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import ccxt.async_support as ccxt
import httpx
import pandas as pd
import yfinance as yf
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from ..utils.symbols import (
    TIMEFRAME_TO_MINUTES,
    Instrument,
    parse_symbol,
    yf_interval,
    yf_period,
)

EXCHANGE_FALLBACK = ["bybit", "kucoin", "okx", "kraken", "binance"]


class MarketDataService:
    """Fetches OHLCV from the appropriate venue based on instrument type.

    Tries a fallback chain of exchanges because some venues (Binance) are
    geo-blocked in some hosting regions.
    """

    def __init__(self) -> None:
        self._exchanges: dict[str, ccxt.Exchange] = {}
        self._http: httpx.AsyncClient | None = None

    async def _get_exchange(self, name: str) -> ccxt.Exchange:
        if name not in self._exchanges:
            cls = getattr(ccxt, name)
            self._exchanges[name] = cls({"enableRateLimit": True})
        return self._exchanges[name]

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=20.0)
        return self._http

    async def close(self) -> None:
        for ex in self._exchanges.values():
            try:
                await ex.close()
            except Exception:
                pass
        self._exchanges.clear()
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def fetch_ohlcv(
        self, raw_symbol: str, timeframe: str = "15m", limit: int = 500
    ) -> tuple[Instrument, pd.DataFrame]:
        inst = parse_symbol(raw_symbol)
        if inst.market == "crypto":
            df = await self._fetch_ccxt(inst, timeframe, limit)
        else:
            df = await self._fetch_yfinance(inst, timeframe, limit)
        return inst, df

    async def _fetch_ccxt(self, inst: Instrument, timeframe: str, limit: int) -> pd.DataFrame:
        symbol = inst.ccxt_symbol
        last_err: Exception | None = None
        for venue in EXCHANGE_FALLBACK:
            try:
                df = await self._fetch_ccxt_one(venue, symbol, timeframe, limit)
                return df
            except ccxt.BadSymbol:
                alt = f"{inst.base}/USDT"
                if alt != symbol:
                    try:
                        df = await self._fetch_ccxt_one(venue, alt, timeframe, limit)
                        return df
                    except Exception as exc:
                        last_err = exc
                        continue
            except Exception as exc:
                last_err = exc
                logger.debug(f"{venue} failed for {symbol} {timeframe}: {exc}")
                continue
        raise RuntimeError(f"All exchanges failed for {symbol} {timeframe}: {last_err}")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.5, max=4))
    async def _fetch_ccxt_one(self, venue: str, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        ex = await self._get_exchange(venue)
        data = await ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp")
        return df.astype(float)

    async def _fetch_yfinance(self, inst: Instrument, timeframe: str, limit: int) -> pd.DataFrame:
        loop = asyncio.get_running_loop()

        def _download() -> pd.DataFrame:
            interval = yf_interval(timeframe)
            period = yf_period(timeframe)
            ticker = yf.Ticker(inst.yf_symbol)
            hist = ticker.history(period=period, interval=interval, auto_adjust=False)
            if hist.empty:
                return pd.DataFrame()
            hist = hist.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )[["open", "high", "low", "close", "volume"]]
            hist.index = pd.to_datetime(hist.index, utc=True)
            return hist

        df = await loop.run_in_executor(None, _download)
        if df.empty:
            raise RuntimeError(f"No data returned for {inst.display} ({timeframe})")

        if timeframe == "4h":
            df = self._resample(df, "4h")

        return df.tail(limit)

    @staticmethod
    def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
        return df.resample(rule).agg(agg).dropna()

    async def fetch_multi(
        self, raw_symbol: str, timeframes: list[str], limit: int = 500
    ) -> tuple[Instrument, dict[str, pd.DataFrame]]:
        inst = parse_symbol(raw_symbol)
        tasks = [self.fetch_ohlcv(raw_symbol, tf, limit) for tf in timeframes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: dict[str, pd.DataFrame] = {}
        for tf, res in zip(timeframes, results, strict=True):
            if isinstance(res, Exception):
                logger.warning(f"Failed to fetch {raw_symbol} {tf}: {res}")
                continue
            _, df = res
            out[tf] = df
        if not out:
            raise RuntimeError(f"All timeframe fetches failed for {raw_symbol}")
        return inst, out

    async def fetch_last_price(self, raw_symbol: str) -> tuple[Instrument, float]:
        inst, df = await self.fetch_ohlcv(raw_symbol, "1m", 1)
        return inst, float(df["close"].iloc[-1])

    async def is_market_open(self, inst: Instrument) -> bool:
        if inst.market == "crypto":
            return True
        now = datetime.now(UTC)
        # Forex market: closed roughly Friday 22:00 UTC -> Sunday 22:00 UTC
        weekday = now.weekday()
        if weekday == 5:
            return False
        if weekday == 4 and now.hour >= 22:
            return False
        if weekday == 6 and now.hour < 22:
            return False
        return True


_service: MarketDataService | None = None


def get_market_service() -> MarketDataService:
    global _service
    if _service is None:
        _service = MarketDataService()
    return _service


__all__ = [
    "TIMEFRAME_TO_MINUTES",
    "MarketDataService",
    "get_market_service",
    "settings",
]

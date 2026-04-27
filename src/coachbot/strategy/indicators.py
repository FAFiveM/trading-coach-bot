"""Technical indicators implemented in pure pandas/numpy (no ta-lib dependency)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(50.0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session-anchored VWAP (anchors at each UTC date change)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    day = df.index.tz_convert("UTC").date if df.index.tz else df.index.date
    grouper = pd.Series(day, index=df.index)
    cum_pv = pv.groupby(grouper).cumsum()
    cum_vol = df["volume"].groupby(grouper).cumsum().replace(0.0, np.nan)
    return (cum_pv / cum_vol).fillna(method="ffill")


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(
    series: pd.Series, period: int = 20, mult: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(series, period)
    std = series.rolling(period).std()
    upper = mid + mult * std
    lower = mid - mult * std
    return upper, mid, lower


def swing_points(df: pd.DataFrame, lookback: int = 5) -> tuple[pd.Series, pd.Series]:
    """Boolean series for swing highs and swing lows using fractal rule."""
    highs = df["high"]
    lows = df["low"]
    sh = (highs == highs.rolling(lookback * 2 + 1, center=True).max()) & highs.notna()
    sl = (lows == lows.rolling(lookback * 2 + 1, center=True).min()) & lows.notna()
    return sh.fillna(False), sl.fillna(False)


def rsi_divergence(df: pd.DataFrame, period: int = 14, lookback: int = 30) -> str:
    """Detect bullish/bearish RSI divergence on the latest swing.

    Returns one of: "bullish", "bearish", "none".
    """
    if len(df) < lookback + period:
        return "none"
    close = df["close"]
    rsi_s = rsi(close, period)

    recent = df.iloc[-lookback:]
    rsi_recent = rsi_s.iloc[-lookback:]

    # Look at lows for bullish divergence
    low_idx = recent["low"].idxmin()
    prev_low_window = recent.iloc[: recent.index.get_loc(low_idx)]
    if not prev_low_window.empty:
        prev_low_idx = prev_low_window["low"].idxmin()
        if (
            recent["low"].loc[low_idx] < recent["low"].loc[prev_low_idx]
            and rsi_recent.loc[low_idx] > rsi_recent.loc[prev_low_idx]
        ):
            return "bullish"

    high_idx = recent["high"].idxmax()
    prev_high_window = recent.iloc[: recent.index.get_loc(high_idx)]
    if not prev_high_window.empty:
        prev_high_idx = prev_high_window["high"].idxmax()
        if (
            recent["high"].loc[high_idx] > recent["high"].loc[prev_high_idx]
            and rsi_recent.loc[high_idx] < rsi_recent.loc[prev_high_idx]
        ):
            return "bearish"

    return "none"


def trend_label(df: pd.DataFrame) -> str:
    """Simple trend classification from EMA stack."""
    if len(df) < 200:
        return "unknown"
    e20 = ema(df["close"], 20).iloc[-1]
    e50 = ema(df["close"], 50).iloc[-1]
    e200 = ema(df["close"], 200).iloc[-1]
    last = df["close"].iloc[-1]
    if last > e20 > e50 > e200:
        return "strong_up"
    if last > e50 > e200:
        return "up"
    if last < e20 < e50 < e200:
        return "strong_down"
    if last < e50 < e200:
        return "down"
    return "range"

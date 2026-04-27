"""Smart Money Concepts: Order Blocks, Fair Value Gaps, Liquidity Sweeps, BOS/CHoCH."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import swing_points


@dataclass
class OrderBlock:
    direction: str  # "bullish" | "bearish"
    top: float
    bottom: float
    timestamp: pd.Timestamp


@dataclass
class FairValueGap:
    direction: str
    top: float
    bottom: float
    timestamp: pd.Timestamp
    filled: bool = False


@dataclass
class LiquiditySweep:
    direction: str  # "high_swept" (bearish) | "low_swept" (bullish)
    level: float
    timestamp: pd.Timestamp


@dataclass
class StructureEvent:
    kind: str  # "BOS" | "CHoCH"
    direction: str  # "bullish" | "bearish"
    level: float
    timestamp: pd.Timestamp


def find_order_blocks(df: pd.DataFrame, lookback: int = 50) -> list[OrderBlock]:
    """Detect last few order blocks: candle before a strong impulsive move."""
    if len(df) < lookback + 5:
        return []
    blocks: list[OrderBlock] = []
    sub = df.iloc[-lookback:].copy()
    body = (sub["close"] - sub["open"]).abs()
    avg_body = body.rolling(10).mean()
    for i in range(2, len(sub) - 1):
        cur_body = body.iloc[i]
        prior_avg = avg_body.iloc[i - 1]
        if pd.isna(prior_avg) or prior_avg == 0:
            continue
        if cur_body > prior_avg * 1.8:
            prev = sub.iloc[i - 1]
            cur = sub.iloc[i]
            if cur["close"] > cur["open"] and prev["close"] < prev["open"]:
                blocks.append(
                    OrderBlock(
                        direction="bullish",
                        top=float(prev["open"]),
                        bottom=float(prev["low"]),
                        timestamp=sub.index[i - 1],
                    )
                )
            elif cur["close"] < cur["open"] and prev["close"] > prev["open"]:
                blocks.append(
                    OrderBlock(
                        direction="bearish",
                        top=float(prev["high"]),
                        bottom=float(prev["open"]),
                        timestamp=sub.index[i - 1],
                    )
                )
    return blocks[-5:]


def find_fair_value_gaps(df: pd.DataFrame, lookback: int = 80) -> list[FairValueGap]:
    if len(df) < 5:
        return []
    fvgs: list[FairValueGap] = []
    sub = df.iloc[-lookback:]
    for i in range(2, len(sub)):
        c1 = sub.iloc[i - 2]
        c3 = sub.iloc[i]
        ts = sub.index[i - 1]
        if c1["high"] < c3["low"]:
            top = float(c3["low"])
            bottom = float(c1["high"])
            filled = bool((sub.iloc[i:]["low"] <= bottom).any())
            fvgs.append(FairValueGap("bullish", top, bottom, ts, filled))
        elif c1["low"] > c3["high"]:
            top = float(c1["low"])
            bottom = float(c3["high"])
            filled = bool((sub.iloc[i:]["high"] >= top).any())
            fvgs.append(FairValueGap("bearish", top, bottom, ts, filled))
    return [g for g in fvgs if not g.filled][-5:]


def find_liquidity_sweeps(df: pd.DataFrame, lookback: int = 60) -> list[LiquiditySweep]:
    """A sweep = price pierces a recent swing high/low and closes back inside."""
    if len(df) < lookback + 10:
        return []
    sweeps: list[LiquiditySweep] = []
    sh, sl = swing_points(df, lookback=3)
    swing_highs = df.loc[sh, "high"]
    swing_lows = df.loc[sl, "low"]
    for i in range(len(df) - lookback, len(df)):
        if i < 0:
            continue
        cur = df.iloc[i]
        ts = df.index[i]
        prior_highs = swing_highs[swing_highs.index < ts]
        prior_lows = swing_lows[swing_lows.index < ts]
        if not prior_highs.empty:
            last_high = float(prior_highs.iloc[-1])
            if cur["high"] > last_high and cur["close"] < last_high:
                sweeps.append(LiquiditySweep("high_swept", last_high, ts))
        if not prior_lows.empty:
            last_low = float(prior_lows.iloc[-1])
            if cur["low"] < last_low and cur["close"] > last_low:
                sweeps.append(LiquiditySweep("low_swept", last_low, ts))
    return sweeps[-5:]


def detect_structure(df: pd.DataFrame, lookback: int = 100) -> list[StructureEvent]:
    """Naive BOS/CHoCH on swing highs/lows."""
    if len(df) < lookback:
        return []
    sh, sl = swing_points(df, lookback=3)
    highs = df.loc[sh, "high"]
    lows = df.loc[sl, "low"]
    if len(highs) < 2 or len(lows) < 2:
        return []
    events: list[StructureEvent] = []
    last_trend = None
    for ts, _row in df.iloc[-lookback:].iterrows():
        recent_highs = highs[highs.index <= ts]
        recent_lows = lows[lows.index <= ts]
        if len(recent_highs) < 2 or len(recent_lows) < 2:
            continue
        prev_high = float(recent_highs.iloc[-2])
        prev_low = float(recent_lows.iloc[-2])
        close = float(df.loc[ts, "close"])
        if close > prev_high:
            kind = "CHoCH" if last_trend == "bearish" else "BOS"
            events.append(StructureEvent(kind, "bullish", prev_high, ts))
            last_trend = "bullish"
        elif close < prev_low:
            kind = "CHoCH" if last_trend == "bullish" else "BOS"
            events.append(StructureEvent(kind, "bearish", prev_low, ts))
            last_trend = "bearish"
    return events[-5:]

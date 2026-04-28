"""The 'Liquidity Sweep + MTF Confluence' strategy.

Goal: produce a trade idea on the 1m timeframe that is anchored to higher-timeframe
context (4H/1H bias) and a confirmed liquidity sweep / order block on 15m or 5m.

Output: TradeIdea dataclass with entry, SL, TP1/TP2/TP3, R:R and a confidence 0-100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from . import indicators as I
from . import patterns as P
from . import smc

Side = Literal["long", "short", "none"]


@dataclass
class Bias:
    timeframe: str
    label: str  # "bullish" | "bearish" | "neutral"
    score: float  # -1..1
    reasons: list[str] = field(default_factory=list)


@dataclass
class TradeIdea:
    symbol: str
    side: Side
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    rr_1: float
    rr_2: float
    rr_3: float
    confidence: int  # 0..100
    biases: list[Bias]
    confluences: list[str]
    invalidations: list[str]
    notes: list[str]
    chart_levels: dict[str, float]
    timeframe_entry: str = "1m"

    @property
    def avg_rr(self) -> float:
        return round((self.rr_1 + self.rr_2 + self.rr_3) / 3, 2)

    def to_summary(self) -> str:
        emoji = "🟢" if self.side == "long" else "🔴" if self.side == "short" else "⚪"
        if self.side == "none":
            return f"{emoji} **{self.symbol}** — No clean setup. Confidence {self.confidence}%."
        return (
            f"{emoji} **{self.symbol}** — {self.side.upper()}\n"
            f"Entry `{self.entry:.6g}` · SL `{self.stop_loss:.6g}`\n"
            f"TP1 `{self.take_profit_1:.6g}` (1:{self.rr_1:.2f}) · "
            f"TP2 `{self.take_profit_2:.6g}` (1:{self.rr_2:.2f}) · "
            f"TP3 `{self.take_profit_3:.6g}` (1:{self.rr_3:.2f})\n"
            f"Confidence **{self.confidence}%** · Entry TF {self.timeframe_entry}"
        )


def _bias_from_htf(df: pd.DataFrame, tf: str) -> Bias:
    reasons: list[str] = []
    score = 0.0
    if len(df) < 50:
        return Bias(tf, "neutral", 0.0, ["insufficient data"])
    close = df["close"]
    e20 = I.ema(close, 20).iloc[-1]
    e50 = I.ema(close, 50).iloc[-1]
    e200 = I.ema(close, min(200, len(df) - 1)).iloc[-1]
    last = close.iloc[-1]

    if last > e50:
        score += 0.4
        reasons.append("price > EMA50")
    else:
        score -= 0.4
        reasons.append("price < EMA50")
    if e20 > e50:
        score += 0.3
        reasons.append("EMA20 > EMA50")
    else:
        score -= 0.3
        reasons.append("EMA20 < EMA50")
    if last > e200:
        score += 0.3
        reasons.append("price > EMA200 (long-term bullish)")
    else:
        score -= 0.3
        reasons.append("price < EMA200 (long-term bearish)")

    div = I.rsi_divergence(df)
    if div == "bullish":
        score += 0.2
        reasons.append("bullish RSI divergence")
    elif div == "bearish":
        score -= 0.2
        reasons.append("bearish RSI divergence")

    structure = smc.detect_structure(df)
    if structure:
        last_evt = structure[-1]
        if last_evt.direction == "bullish":
            score += 0.15
            reasons.append(f"{last_evt.kind} bullish on {tf}")
        else:
            score -= 0.15
            reasons.append(f"{last_evt.kind} bearish on {tf}")

    score = max(-1.0, min(1.0, score))
    label = "bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral"
    return Bias(tf, label, score, reasons)


def _aggregate_bias(biases: list[Bias]) -> tuple[Side, float]:
    weights = {"4h": 0.4, "1h": 0.3, "15m": 0.2, "5m": 0.1}
    total = 0.0
    weight_sum = 0.0
    for b in biases:
        w = weights.get(b.timeframe, 0.1)
        total += b.score * w
        weight_sum += w
    if weight_sum == 0:
        return "none", 0.0
    avg = total / weight_sum
    if avg > 0.25:
        return "long", avg
    if avg < -0.25:
        return "short", avg
    return "none", avg


def build_trade_idea(
    symbol: str, mtf: dict[str, pd.DataFrame], rr_min: float = 2.0, rr_max: float = 5.0
) -> TradeIdea:
    biases: list[Bias] = []
    for tf in ("4h", "1h", "15m", "5m"):
        if tf in mtf and len(mtf[tf]) > 30:
            biases.append(_bias_from_htf(mtf[tf], tf))

    side, agg_score = _aggregate_bias(biases)

    confluences: list[str] = []
    invalidations: list[str] = []
    notes: list[str] = []

    df1m = mtf.get("1m")
    df5m = mtf.get("5m")
    df15m = mtf.get("15m")
    df_entry = df1m if df1m is not None and not df1m.empty else df5m
    if df_entry is None or df_entry.empty:
        return TradeIdea(
            symbol=symbol,
            side="none",
            entry=0,
            stop_loss=0,
            take_profit_1=0,
            take_profit_2=0,
            take_profit_3=0,
            rr_1=0,
            rr_2=0,
            rr_3=0,
            confidence=0,
            biases=biases,
            confluences=[],
            invalidations=["no entry-timeframe data"],
            notes=[],
            chart_levels={},
        )

    last = float(df_entry["close"].iloc[-1])
    atr_1m = float(I.atr(df_entry, 14).iloc[-1])
    atr_15m = float(I.atr(df15m, 14).iloc[-1]) if df15m is not None and len(df15m) > 20 else atr_1m * 4

    confidence = int(min(60, abs(agg_score) * 100))

    sweeps_15m = smc.find_liquidity_sweeps(df15m) if df15m is not None else []
    obs_15m = smc.find_order_blocks(df15m) if df15m is not None else []
    fvgs_15m = smc.find_fair_value_gaps(df15m) if df15m is not None else []

    if sweeps_15m:
        last_sweep = sweeps_15m[-1]
        if side == "long" and last_sweep.direction == "low_swept":
            confluences.append(f"Liquidity sweep below {last_sweep.level:.6g} on 15m")
            confidence += 15
        elif side == "short" and last_sweep.direction == "high_swept":
            confluences.append(f"Liquidity sweep above {last_sweep.level:.6g} on 15m")
            confidence += 15

    aligned_obs = [
        ob
        for ob in obs_15m
        if (side == "long" and ob.direction == "bullish") or (side == "short" and ob.direction == "bearish")
    ]
    if aligned_obs:
        ob = aligned_obs[-1]
        confluences.append(f"Order Block ({ob.direction}) on 15m between {ob.bottom:.6g}-{ob.top:.6g}")
        confidence += 10

    aligned_fvgs = [
        g
        for g in fvgs_15m
        if (side == "long" and g.direction == "bullish") or (side == "short" and g.direction == "bearish")
    ]
    if aligned_fvgs:
        g = aligned_fvgs[-1]
        confluences.append(f"Unfilled Fair Value Gap between {g.bottom:.6g}-{g.top:.6g}")
        confidence += 8

    pats = P.detect_patterns(df15m) if df15m is not None else []
    for p in pats:
        confluences.append(f"Chart pattern: {p}")
        confidence += 4

    confidence = max(0, min(99, confidence))

    if side == "none" or confidence < 35:
        notes.append("Signal is weak — wait for additional confirmation.")
        return TradeIdea(
            symbol=symbol,
            side="none",
            entry=last,
            stop_loss=last,
            take_profit_1=last,
            take_profit_2=last,
            take_profit_3=last,
            rr_1=0,
            rr_2=0,
            rr_3=0,
            confidence=confidence,
            biases=biases,
            confluences=confluences,
            invalidations=invalidations,
            notes=notes,
            chart_levels={},
        )

    risk_unit = max(atr_1m * 1.2, atr_15m * 0.25)
    if risk_unit <= 0:
        risk_unit = last * 0.0015

    if side == "long":
        entry = last
        stop_loss = entry - risk_unit
        if aligned_obs:
            stop_loss = min(stop_loss, aligned_obs[-1].bottom - atr_1m * 0.3)
        risk = entry - stop_loss
    else:
        entry = last
        stop_loss = entry + risk_unit
        if aligned_obs:
            stop_loss = max(stop_loss, aligned_obs[-1].top + atr_1m * 0.3)
        risk = stop_loss - entry

    risk = max(risk, last * 0.0005)

    rr1 = max(rr_min, 2.0)
    rr3 = min(rr_max, 5.0)
    rr2 = (rr1 + rr3) / 2
    if confidence >= 75:
        rr1, rr2, rr3 = 2.5, 3.5, 5.0
    elif confidence >= 55:
        rr1, rr2, rr3 = 2.0, 3.0, 4.0
    else:
        rr1, rr2, rr3 = 2.0, 2.5, 3.0

    if side == "long":
        tp1 = entry + risk * rr1
        tp2 = entry + risk * rr2
        tp3 = entry + risk * rr3
    else:
        tp1 = entry - risk * rr1
        tp2 = entry - risk * rr2
        tp3 = entry - risk * rr3

    invalidations.append(
        f"Idea invalid if a 15m candle closes {'below' if side == 'long' else 'above'} {stop_loss:.6g}"
    )
    notes.append("Prefer entry after a clean 1m break of structure with a volume expansion.")

    chart_levels = {
        "entry": entry,
        "sl": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
    }

    return TradeIdea(
        symbol=symbol,
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        take_profit_1=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
        rr_1=rr1,
        rr_2=rr2,
        rr_3=rr3,
        confidence=confidence,
        biases=biases,
        confluences=confluences,
        invalidations=invalidations,
        notes=notes,
        chart_levels=chart_levels,
    )

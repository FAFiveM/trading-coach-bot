"""The 'A+ Confluence' trading strategy.

The bot only flags a setup as A+ (high-confidence) when MANY independent
filters line up at once. The model layers:

  1. Multi-timeframe bias alignment (4H + 1H + 15m all on the same side)
  2. Price-action structure: liquidity sweep + Order Block + Fair Value Gap
  3. Momentum: MACD on 1H and 15m, RSI not exhausted against the idea
  4. Volume expansion on the trigger candle
  5. Volatility gate: ATR within a reasonable band
  6. Risk profile: ATR-based stop with R:R >= 1:2.5 achievable
  7. Trading-session filter (forex during London / NY only)

Confidence is built additively from these checks. >= 85% means almost every
filter aligned, which is rare and only happens at major confluence zones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    confidence: int  # 0..99
    biases: list[Bias]
    confluences: list[str]
    invalidations: list[str]
    notes: list[str]
    chart_levels: dict[str, float]
    timeframe_entry: str = "1m"

    @property
    def avg_rr(self) -> float:
        return round((self.rr_1 + self.rr_2 + self.rr_3) / 3, 2)

    @property
    def grade(self) -> str:
        if self.confidence >= 85:
            return "A+"
        if self.confidence >= 70:
            return "A"
        if self.confidence >= 55:
            return "B"
        if self.confidence >= 35:
            return "C"
        return "D"

    def to_summary(self) -> str:
        emoji = "🟢" if self.side == "long" else "🔴" if self.side == "short" else "⚪"
        if self.side == "none":
            return f"{emoji} **{self.symbol}** — No clean setup. Confidence {self.confidence}%."
        return (
            f"{emoji} **{self.symbol}** — {self.side.upper()}  ·  Grade **{self.grade}**\n"
            f"Entry `{self.entry:.6g}` · SL `{self.stop_loss:.6g}`\n"
            f"TP1 `{self.take_profit_1:.6g}` (1:{self.rr_1:.2f}) · "
            f"TP2 `{self.take_profit_2:.6g}` (1:{self.rr_2:.2f}) · "
            f"TP3 `{self.take_profit_3:.6g}` (1:{self.rr_3:.2f})\n"
            f"Confidence **{self.confidence}%** · Entry TF {self.timeframe_entry}"
        )


def _bias_from_htf(df: pd.DataFrame, tf: str) -> Bias:
    """Classify higher-timeframe bias from EMA stack + RSI divergence + structure."""
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


def _macd_aligned(df: pd.DataFrame, side: Side) -> tuple[bool, str]:
    if df is None or len(df) < 35:
        return False, "MACD: insufficient data"
    macd_line, signal_line, hist = I.macd(df["close"])
    last_macd = float(macd_line.iloc[-1])
    last_signal = float(signal_line.iloc[-1])
    last_hist = float(hist.iloc[-1])
    prev_hist = float(hist.iloc[-2])
    if side == "long":
        ok = last_macd > last_signal and last_hist > prev_hist
        return ok, "MACD bullish & rising" if ok else "MACD not aligned long"
    if side == "short":
        ok = last_macd < last_signal and last_hist < prev_hist
        return ok, "MACD bearish & falling" if ok else "MACD not aligned short"
    return False, "no side"


def _rsi_not_exhausted(df: pd.DataFrame, side: Side) -> tuple[bool, str]:
    """Reject if RSI is already deeply extended against a fresh entry."""
    if df is None or len(df) < 20:
        return True, ""
    last_rsi = float(I.rsi(df["close"]).iloc[-1])
    if side == "long" and last_rsi > 78:
        return False, f"RSI {last_rsi:.0f} overbought — exhaustion risk"
    if side == "short" and last_rsi < 22:
        return False, f"RSI {last_rsi:.0f} oversold — exhaustion risk"
    return True, f"RSI {last_rsi:.0f} healthy"


def _volume_expansion(df: pd.DataFrame) -> tuple[bool, str]:
    if df is None or len(df) < 25 or "volume" not in df.columns:
        return False, "volume: n/a"
    vol = df["volume"]
    if vol.iloc[-20:].sum() <= 0:
        return False, "no volume data"
    avg = vol.iloc[-20:-1].mean()
    last = vol.iloc[-1]
    if avg <= 0:
        return False, "no volume baseline"
    ratio = last / avg
    if ratio >= 1.4:
        return True, f"volume {ratio:.2f}× avg (expansion)"
    return False, f"volume {ratio:.2f}× avg (no expansion)"


def _volatility_gate(df15m: pd.DataFrame, last_price: float) -> tuple[bool, str]:
    """Reject dead markets and absurdly volatile spikes."""
    if df15m is None or len(df15m) < 30 or last_price <= 0:
        return True, ""
    atr_v = float(I.atr(df15m, 14).iloc[-1])
    pct = atr_v / last_price
    if pct < 0.0005:
        return False, f"ATR/price {pct * 100:.3f}% — market too quiet"
    if pct > 0.05:
        return False, f"ATR/price {pct * 100:.2f}% — abnormal volatility"
    return True, f"volatility {pct * 100:.2f}% (healthy)"


def _session_for_symbol(symbol: str, now: datetime | None = None) -> tuple[bool, str]:
    """Allow forex only during London (7-16 UTC) or NY (12-21 UTC) sessions.

    Crypto runs 24/7, gold/oil follow forex sessions loosely.
    """
    now = now or datetime.now(UTC)
    h = now.hour
    sym = symbol.upper()
    is_crypto = "USDT" in sym or "/USDT" in sym or "/USDC" in sym or "USDC" in sym
    if is_crypto:
        return True, "crypto 24/7"
    london = 7 <= h < 16
    ny = 12 <= h < 21
    if london or ny:
        active = "London" if london else ""
        if ny:
            active = active + ("/NY" if active else "NY")
        return True, f"{active} session active"
    return False, "outside London/NY sessions"


def _last_swing_levels(df: pd.DataFrame) -> tuple[float | None, float | None]:
    if df is None or len(df) < 20:
        return None, None
    sh, sl = I.swing_points(df, lookback=3)
    highs = df.loc[sh, "high"]
    lows = df.loc[sl, "low"]
    last_high = float(highs.iloc[-1]) if not highs.empty else None
    last_low = float(lows.iloc[-1]) if not lows.empty else None
    return last_high, last_low


def build_trade_idea(
    symbol: str,
    mtf: dict[str, pd.DataFrame],
    rr_min: float = 2.0,
    rr_max: float = 5.0,
) -> TradeIdea:
    biases: list[Bias] = []
    for tf in ("4h", "1h", "15m", "5m"):
        if tf in mtf and len(mtf[tf]) > 30:
            biases.append(_bias_from_htf(mtf[tf], tf))

    side, _agg_score = _aggregate_bias(biases)

    confluences: list[str] = []
    invalidations: list[str] = []
    notes: list[str] = []
    rejections: list[str] = []

    df1m = mtf.get("1m")
    df5m = mtf.get("5m")
    df15m = mtf.get("15m")
    df1h = mtf.get("1h")

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

    confidence = 0
    high_tier_eligible = True

    htf_biases = {b.timeframe: b for b in biases}

    b4h = htf_biases.get("4h")
    b1h = htf_biases.get("1h")
    b15 = htf_biases.get("15m")

    if side != "none" and b4h and b1h and b4h.label != "neutral" and b1h.label != "neutral":
        wanted = "bullish" if side == "long" else "bearish"
        if b4h.label == wanted and b1h.label == wanted:
            confluences.append("HTF aligned: 4H + 1H both " + wanted)
            confidence += 25
        else:
            high_tier_eligible = False
            rejections.append("4H/1H not aligned with signal direction")
    else:
        high_tier_eligible = False
        rejections.append("4H or 1H bias is neutral")

    if side != "none" and b15 and b15.label != "neutral":
        wanted = "bullish" if side == "long" else "bearish"
        if b15.label == wanted:
            confluences.append("15m bias confirms HTF direction")
            confidence += 10
        else:
            high_tier_eligible = False
            rejections.append("15m bias diverges from HTF")
    elif side != "none":
        rejections.append("15m bias unclear")

    sweeps_15m = smc.find_liquidity_sweeps(df15m) if df15m is not None else []
    obs_15m = smc.find_order_blocks(df15m) if df15m is not None else []
    fvgs_15m = smc.find_fair_value_gaps(df15m) if df15m is not None else []

    sweep_recent = False
    if sweeps_15m and side != "none":
        last_sweep = sweeps_15m[-1]
        if df15m is not None and len(df15m) > 0:
            try:
                sweep_pos = df15m.index.get_loc(last_sweep.timestamp)
                age = len(df15m) - 1 - sweep_pos
            except Exception:
                age = 99
        else:
            age = 99
        wanted_dir = "low_swept" if side == "long" else "high_swept"
        if last_sweep.direction == wanted_dir and age <= 8:
            confluences.append(
                f"Fresh liquidity sweep ({last_sweep.direction.replace('_', ' ')}) at {last_sweep.level:.6g}"
            )
            confidence += 15
            sweep_recent = True
    if not sweep_recent:
        high_tier_eligible = False
        rejections.append("no fresh liquidity sweep aligned with side (within 8 candles)")

    aligned_obs = [
        ob
        for ob in obs_15m
        if (side == "long" and ob.direction == "bullish") or (side == "short" and ob.direction == "bearish")
    ]
    ob_zone = None
    if aligned_obs:
        ob = aligned_obs[-1]
        ob_zone = ob
        confluences.append(f"Order Block ({ob.direction}) on 15m between {ob.bottom:.6g}-{ob.top:.6g}")
        confidence += 10
    else:
        high_tier_eligible = False
        rejections.append("no aligned Order Block on 15m")

    aligned_fvgs = [
        g
        for g in fvgs_15m
        if (side == "long" and g.direction == "bullish") or (side == "short" and g.direction == "bearish")
    ]
    if aligned_fvgs:
        g = aligned_fvgs[-1]
        confluences.append(f"Unfilled Fair Value Gap between {g.bottom:.6g}-{g.top:.6g}")
        confidence += 8
    else:
        high_tier_eligible = False
        rejections.append("no aligned unfilled FVG on 15m")

    macd_1h_ok, macd_1h_msg = _macd_aligned(df1h, side)
    if macd_1h_ok:
        confluences.append("1H " + macd_1h_msg)
        confidence += 7
    else:
        if side != "none":
            high_tier_eligible = False
            rejections.append(macd_1h_msg)

    macd_15_ok, macd_15_msg = _macd_aligned(df15m, side)
    if macd_15_ok:
        confluences.append("15m " + macd_15_msg)
        confidence += 6
    else:
        if side != "none":
            high_tier_eligible = False
            rejections.append(macd_15_msg)

    rsi_ok, rsi_msg = _rsi_not_exhausted(df15m, side)
    if rsi_ok:
        if rsi_msg:
            confluences.append("15m " + rsi_msg)
            confidence += 4
    else:
        high_tier_eligible = False
        rejections.append(rsi_msg)

    vol_ok, vol_msg = _volume_expansion(df_entry)
    if vol_ok:
        confluences.append(vol_msg + " on entry candle")
        confidence += 6

    vola_ok, vola_msg = _volatility_gate(df15m, last)
    if vola_ok:
        if vola_msg:
            confluences.append(vola_msg)
            confidence += 4
    else:
        high_tier_eligible = False
        rejections.append(vola_msg)

    sess_ok, sess_msg = _session_for_symbol(symbol)
    if sess_ok:
        confluences.append(sess_msg)
        confidence += 4
    else:
        high_tier_eligible = False
        rejections.append(sess_msg)

    pats = P.detect_patterns(df15m) if df15m is not None else []
    for p in pats:
        confluences.append(f"Chart pattern: {p}")
        confidence += 3

    if not high_tier_eligible:
        confidence = min(confidence, 75)

    confidence = max(0, min(99, confidence))

    if side == "none" or confidence < 35:
        notes.append("Signal is weak — wait for additional confirmation.")
        if rejections:
            notes.append("Missing: " + "; ".join(rejections[:5]))
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

    last_high, last_low = _last_swing_levels(df15m if df15m is not None else df_entry)

    risk_unit = max(atr_1m * 1.2, atr_15m * 0.25)
    if risk_unit <= 0:
        risk_unit = last * 0.0015

    if side == "long":
        entry = last
        stop_loss = entry - risk_unit
        if ob_zone is not None:
            stop_loss = min(stop_loss, ob_zone.bottom - atr_1m * 0.3)
        if last_low is not None:
            stop_loss = min(stop_loss, last_low - atr_1m * 0.2)
        risk = entry - stop_loss
    else:
        entry = last
        stop_loss = entry + risk_unit
        if ob_zone is not None:
            stop_loss = max(stop_loss, ob_zone.top + atr_1m * 0.3)
        if last_high is not None:
            stop_loss = max(stop_loss, last_high + atr_1m * 0.2)
        risk = stop_loss - entry

    risk = max(risk, last * 0.0005)

    if confidence >= 85:
        rr1, rr2, rr3 = 2.5, 4.0, 5.0
    elif confidence >= 70:
        rr1, rr2, rr3 = 2.0, 3.0, 4.5
    elif confidence >= 55:
        rr1, rr2, rr3 = 2.0, 2.75, 3.5
    else:
        rr1, rr2, rr3 = 2.0, 2.5, 3.0

    rr1 = max(rr1, rr_min)
    rr3 = min(rr3, rr_max)

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
    if rejections and confidence < 85:
        notes.append("To reach A+ tier still need: " + "; ".join(rejections[:3]))

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

"""Lightweight chart pattern recognition."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import swing_points


def detect_patterns(df: pd.DataFrame, lookback: int = 80) -> list[str]:
    if len(df) < lookback:
        return []
    sub = df.iloc[-lookback:]
    sh, sl = swing_points(sub, lookback=3)
    highs = sub.loc[sh, "high"]
    lows = sub.loc[sl, "low"]
    out: list[str] = []

    # Double top / bottom
    if len(highs) >= 2:
        h1, h2 = highs.iloc[-2], highs.iloc[-1]
        if abs(h1 - h2) / max(h1, 1e-9) < 0.005:
            out.append("Double Top")
    if len(lows) >= 2:
        l1, l2 = lows.iloc[-2], lows.iloc[-1]
        if abs(l1 - l2) / max(l1, 1e-9) < 0.005:
            out.append("Double Bottom")

    # Head & shoulders
    if len(highs) >= 3:
        a, b, c = highs.iloc[-3:]
        if b > a and b > c and abs(a - c) / max(b, 1e-9) < 0.01:
            out.append("Head & Shoulders")
    if len(lows) >= 3:
        a, b, c = lows.iloc[-3:]
        if b < a and b < c and abs(a - c) / max(abs(b), 1e-9) < 0.01:
            out.append("Inverse Head & Shoulders")

    # Ascending / descending triangle via linear regression on highs/lows
    if len(sub) >= 30:
        y_high = sub["high"].values[-30:]
        y_low = sub["low"].values[-30:]
        x = np.arange(30)
        slope_h = np.polyfit(x, y_high, 1)[0]
        slope_l = np.polyfit(x, y_low, 1)[0]
        rng = float(sub["high"].max() - sub["low"].min())
        if rng > 0:
            sh_norm = slope_h * 30 / rng
            sl_norm = slope_l * 30 / rng
            if abs(sh_norm) < 0.05 and sl_norm > 0.1:
                out.append("Ascending Triangle")
            elif abs(sl_norm) < 0.05 and sh_norm < -0.1:
                out.append("Descending Triangle")
            elif sh_norm < -0.1 and sl_norm > 0.1:
                out.append("Symmetrical Triangle")

    return out

"""Chart rendering with mplfinance — branded dark theme, entry/SL/TP overlays, EMAs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from ..config import settings
from ..strategy.engine import TradeIdea


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def render_trade_chart(symbol: str, timeframe: str, df: pd.DataFrame, idea: TradeIdea) -> Path:
    settings.charts_dir.mkdir(parents=True, exist_ok=True)
    safe_sym = symbol.replace("/", "_").replace(" ", "_")
    out = settings.charts_dir / f"{safe_sym}_{timeframe}_{int(datetime.utcnow().timestamp())}.png"

    df = df.tail(150).copy()
    df.index.name = "Date"

    market_colors = mpf.make_marketcolors(
        up="#16C784",
        down="#EA3943",
        edge={"up": "#16C784", "down": "#EA3943"},
        wick={"up": "#16C784", "down": "#EA3943"},
        volume={"up": "#16C78488", "down": "#EA394388"},
    )
    style = mpf.make_mpf_style(
        marketcolors=market_colors,
        gridstyle=":",
        gridcolor="#2a2f3a",
        facecolor="#0d1117",
        edgecolor="#0d1117",
        figcolor="#0d1117",
        rc={
            "axes.edgecolor": "#30363d",
            "axes.labelcolor": "#c9d1d9",
            "axes.facecolor": "#0d1117",
            "axes.titlecolor": "#f0f6fc",
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "figure.facecolor": "#0d1117",
            "xtick.color": "#8b949e",
            "ytick.color": "#8b949e",
            "text.color": "#c9d1d9",
            "savefig.facecolor": "#0d1117",
            "savefig.edgecolor": "#0d1117",
        },
    )

    addplots = []
    if len(df) >= 21:
        addplots.append(mpf.make_addplot(_ema(df["close"], 20), color="#4DA3FF", width=1.0, alpha=0.85))
    if len(df) >= 51:
        addplots.append(mpf.make_addplot(_ema(df["close"], 50), color="#F7B500", width=1.0, alpha=0.85))
    if len(df) >= 100:
        ema200_len = min(200, len(df) - 1)
        addplots.append(
            mpf.make_addplot(_ema(df["close"], ema200_len), color="#9B5DE5", width=1.2, alpha=0.85)
        )

    levels = idea.chart_levels
    if levels:
        for key, color, width in [
            ("entry", "#FFFFFF", 1.4),
            ("sl", "#EA3943", 1.2),
            ("tp1", "#16C784", 1.0),
            ("tp2", "#16C784", 1.0),
            ("tp3", "#16C784", 1.0),
        ]:
            level = levels.get(key)
            if level is None or level == 0:
                continue
            series = pd.Series([level] * len(df), index=df.index)
            addplots.append(mpf.make_addplot(series, color=color, width=width, linestyle="--", alpha=0.9))

    side_label = idea.side.upper() if idea.side != "none" else "NO SETUP"
    title = f"{symbol}  ·  {timeframe}  ·  {side_label}  ·  Conf {idea.confidence}%"

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=style,
        addplot=addplots if addplots else None,
        volume=True,
        title=title,
        figsize=(12, 7),
        returnfig=True,
        tight_layout=True,
        ylabel="Price",
        ylabel_lower="Volume",
        panel_ratios=(4, 1),
    )

    if levels and axes:
        ax = axes[0]
        x_right = len(df) - 1
        prices = [v for v in levels.values() if v]
        if prices:
            data_low = float(df["low"].min())
            data_high = float(df["high"].max())
            y_min = min(data_low, min(prices))
            y_max = max(data_high, max(prices))
            pad = (y_max - y_min) * 0.05 or 1
            ax.set_ylim(y_min - pad, y_max + pad)
        for key, label, color in [
            ("entry", "Entry", "#FFFFFF"),
            ("sl", "SL", "#EA3943"),
            ("tp1", "TP1", "#16C784"),
            ("tp2", "TP2", "#16C784"),
            ("tp3", "TP3", "#16C784"),
        ]:
            level = levels.get(key)
            if level is None or level == 0:
                continue
            ax.text(
                x_right + 0.5,
                level,
                f" {label} {level:.6g}",
                color=color,
                fontsize=8,
                fontweight="bold",
                va="center",
                ha="left",
            )

    fig.text(
        0.99,
        0.01,
        "khadooojjjjiFX • Trading Coach",
        color="#4DA3FF",
        fontsize=9,
        ha="right",
        va="bottom",
        alpha=0.85,
    )

    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    return out

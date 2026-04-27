"""Chart rendering with mplfinance + entry/SL/TP overlays."""

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


def render_trade_chart(symbol: str, timeframe: str, df: pd.DataFrame, idea: TradeIdea) -> Path:
    settings.charts_dir.mkdir(parents=True, exist_ok=True)
    safe_sym = symbol.replace("/", "_").replace(" ", "_")
    out = settings.charts_dir / f"{safe_sym}_{timeframe}_{int(datetime.utcnow().timestamp())}.png"

    df = df.tail(120).copy()
    df.index.name = "Date"

    style = mpf.make_mpf_style(
        base_mpf_style="charles",
        rc={
            "axes.edgecolor": "#444",
            "axes.labelcolor": "#cfcfcf",
            "axes.facecolor": "#1e1e1e",
            "figure.facecolor": "#1e1e1e",
            "xtick.color": "#cfcfcf",
            "ytick.color": "#cfcfcf",
            "text.color": "#eaeaea",
            "grid.color": "#333",
        },
    )

    addplots = []
    levels = idea.chart_levels
    if levels:
        for _label, key, color in [
            ("Entry", "entry", "#ffffff"),
            ("SL", "sl", "#ff5252"),
            ("TP1", "tp1", "#4caf50"),
            ("TP2", "tp2", "#66bb6a"),
            ("TP3", "tp3", "#81c784"),
        ]:
            if key in levels:
                series = pd.Series([levels[key]] * len(df), index=df.index)
                addplots.append(mpf.make_addplot(series, color=color, width=1.0, linestyle="--"))

    title = f"{symbol} ({timeframe}) — {idea.side.upper() if idea.side != 'none' else 'NO SETUP'} | Conf {idea.confidence}%"

    fig, _ = mpf.plot(
        df,
        type="candle",
        style=style,
        addplot=addplots if addplots else None,
        volume=False,
        title=title,
        figsize=(11, 6),
        returnfig=True,
        tight_layout=True,
        ylabel="Price",
    )
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out

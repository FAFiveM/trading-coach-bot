"""Simple walk-forward backtest of the strategy on historical data."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import indicators as I
from . import smc


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_rr: float
    total_r: float
    max_dd_r: float

    def to_text(self) -> str:
        return (
            f"📊 **Backtest** — `{self.symbol}` ({self.timeframe})\n"
            f"Trades: {self.trades} · Wins: {self.wins} · Losses: {self.losses}\n"
            f"Win rate: {self.win_rate:.1f}% · Avg R/trade: {self.avg_rr:.2f}\n"
            f"Total R: {self.total_r:+.2f} · Max drawdown: {self.max_dd_r:.2f}R"
        )


def backtest(symbol: str, df: pd.DataFrame, timeframe: str = "15m") -> BacktestResult:
    """Walk forward bar by bar; enter on liquidity sweep + EMA50 alignment, fixed 1:3 R:R."""
    if len(df) < 200:
        return BacktestResult(symbol, timeframe, 0, 0, 0, 0.0, 0.0, 0.0, 0.0)

    df = df.copy()
    df["ema50"] = I.ema(df["close"], 50)
    df["ema200"] = I.ema(df["close"], 200)
    df["atr"] = I.atr(df, 14)

    trades = 0
    wins = 0
    losses = 0
    total_r = 0.0
    equity_r = 0.0
    peak_r = 0.0
    max_dd = 0.0

    in_trade = False
    side = ""
    entry = sl = tp = 0.0

    for i in range(50, len(df) - 1):
        bar = df.iloc[i]
        if in_trade:
            high = bar["high"]
            low = bar["low"]
            if side == "long":
                if low <= sl:
                    losses += 1
                    total_r -= 1.0
                    equity_r -= 1.0
                    in_trade = False
                elif high >= tp:
                    wins += 1
                    total_r += 3.0
                    equity_r += 3.0
                    in_trade = False
            else:
                if high >= sl:
                    losses += 1
                    total_r -= 1.0
                    equity_r -= 1.0
                    in_trade = False
                elif low <= tp:
                    wins += 1
                    total_r += 3.0
                    equity_r += 3.0
                    in_trade = False
            peak_r = max(peak_r, equity_r)
            max_dd = max(max_dd, peak_r - equity_r)
            if not in_trade:
                trades += 1
            continue

        sub = df.iloc[: i + 1]
        sweeps = smc.find_liquidity_sweeps(sub.iloc[-30:])
        if not sweeps:
            continue
        sweep = sweeps[-1]
        if sweep.timestamp != sub.index[-1]:
            continue

        atr_val = float(sub["atr"].iloc[-1])
        ema50_val = float(sub["ema50"].iloc[-1])
        if atr_val <= 0 or pd.isna(ema50_val):
            continue

        close_p = float(sub["close"].iloc[-1])
        if sweep.direction == "low_swept" and close_p > ema50_val:
            side = "long"
            entry = close_p
            sl = entry - atr_val * 1.2
            tp = entry + (entry - sl) * 3.0
            in_trade = True
        elif sweep.direction == "high_swept" and close_p < ema50_val:
            side = "short"
            entry = close_p
            sl = entry + atr_val * 1.2
            tp = entry - (sl - entry) * 3.0
            in_trade = True

    win_rate = (wins / trades * 100) if trades > 0 else 0.0
    avg_rr = (total_r / trades) if trades > 0 else 0.0
    return BacktestResult(symbol, timeframe, trades, wins, losses, win_rate, avg_rr, total_r, max_dd)

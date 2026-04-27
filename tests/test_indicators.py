import numpy as np
import pandas as pd

from coachbot.strategy import indicators as I


def _make_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = close + rng.uniform(0.1, 0.6, n)
    low = close - rng.uniform(0.1, 0.6, n)
    open_ = close + rng.uniform(-0.3, 0.3, n)
    vol = rng.uniform(100, 1000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def test_ema_length():
    df = _make_df()
    out = I.ema(df["close"], 20)
    assert len(out) == len(df)
    assert not out.isna().all()


def test_rsi_bounds():
    df = _make_df()
    out = I.rsi(df["close"], 14)
    sub = out.dropna()
    assert (sub >= 0).all() and (sub <= 100).all()


def test_atr_positive():
    df = _make_df()
    out = I.atr(df, 14).dropna()
    assert (out > 0).all()


def test_trend_label():
    df = _make_df()
    label = I.trend_label(df)
    assert label in {"strong_up", "up", "range", "down", "strong_down", "unknown"}

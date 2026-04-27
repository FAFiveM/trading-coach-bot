import numpy as np
import pandas as pd

from coachbot.strategy.engine import build_trade_idea


def _make_df(n: int = 400, drift: float = 0.05) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 0.4, n)
    close = 100 + np.cumsum(noise + drift)
    high = close + rng.uniform(0.1, 0.6, n)
    low = close - rng.uniform(0.1, 0.6, n)
    open_ = close + rng.uniform(-0.3, 0.3, n)
    vol = rng.uniform(100, 1000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def test_build_idea_runs():
    mtf = {tf: _make_df() for tf in ("4h", "1h", "15m", "5m", "1m")}
    idea = build_trade_idea("TEST", mtf)
    assert idea.symbol == "TEST"
    assert idea.side in {"long", "short", "none"}
    assert 0 <= idea.confidence <= 99
    if idea.side != "none":
        assert idea.stop_loss != idea.entry
        assert idea.rr_1 >= 2.0
        assert idea.rr_3 <= 5.0

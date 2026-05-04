"""User trade profile — dollar-based stake, SL, and TP bands.

Defaults match the user's preferred profile:
    stake_usd  = 100   ($ risked per trade)
    sl band    = $70 .. $100  (max acceptable loss)
    tp band    = $300 .. $600 (target reward)

Implies an R:R range of roughly 1:3 to 1:6 — these targets gate which signals
are flagged as A+ at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from .db.models import UserSettings
from .db.session import get_session


@dataclass
class TradeProfile:
    stake_usd: float = 100.0
    sl_min_usd: float = 70.0
    sl_max_usd: float = 100.0
    tp_min_usd: float = 300.0
    tp_max_usd: float = 600.0

    @property
    def risk_target(self) -> float:
        """Use stake_usd as the canonical risk-per-trade target."""
        return self.stake_usd

    @property
    def rr_min(self) -> float:
        return self.tp_min_usd / max(self.sl_max_usd, 1.0)

    @property
    def rr_max(self) -> float:
        return self.tp_max_usd / max(self.sl_min_usd, 1.0)


DEFAULT_PROFILE = TradeProfile()


async def get_profile_for_user(user_id: str) -> TradeProfile:
    """Return the user's saved profile, or defaults if not set."""
    async with get_session() as s:
        u = await s.get(UserSettings, str(user_id))
    if u is None:
        return DEFAULT_PROFILE
    return TradeProfile(
        stake_usd=float(u.stake_usd or 100.0),
        sl_min_usd=float(u.sl_min_usd or 70.0),
        sl_max_usd=float(u.sl_max_usd or 100.0),
        tp_min_usd=float(u.tp_min_usd or 300.0),
        tp_max_usd=float(u.tp_max_usd or 600.0),
    )


async def get_default_or_first_profile() -> TradeProfile:
    """For auto-broadcast where there's no single user — pick the first profile
    (the bot owner) or return defaults.
    """
    async with get_session() as s:
        res = await s.execute(select(UserSettings).limit(1))
        u = res.scalar_one_or_none()
    if u is None:
        return DEFAULT_PROFILE
    return TradeProfile(
        stake_usd=float(u.stake_usd or 100.0),
        sl_min_usd=float(u.sl_min_usd or 70.0),
        sl_max_usd=float(u.sl_max_usd or 100.0),
        tp_min_usd=float(u.tp_min_usd or 300.0),
        tp_max_usd=float(u.tp_max_usd or 600.0),
    )

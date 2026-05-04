"""SQLAlchemy models for portfolio, journal, watchlist, alerts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    symbol = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_watch_user_symbol"),)


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    symbol = Column(String(32), nullable=False)
    side = Column(String(8), nullable=False)
    entry = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=True)
    size = Column(Float, default=1.0)
    status = Column(String(16), default="open")  # open|closed
    exit_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    rr = Column(Float, nullable=True)
    notes = Column(Text, default="")
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    journal_entries = relationship("JournalEntry", back_populates="trade", cascade="all, delete-orphan")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    trade = relationship("Trade", back_populates="journal_entries")


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    channel_id = Column(String(64), nullable=False)
    symbol = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=False)  # above|below
    target = Column(Float, nullable=False)
    note = Column(String(255), default="")
    triggered = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id = Column(String(64), primary_key=True)
    daily_alerts_channel = Column(String(64), nullable=True)
    risk_pct = Column(Float, default=1.0)
    max_daily_loss_pct = Column(Float, default=3.0)
    coach_mode = Column(Integer, default=1)
    timezone = Column(String(64), default="UTC")
    # Dollar-based trade profile (per-trade)
    stake_usd = Column(Float, default=100.0)
    sl_min_usd = Column(Float, default=70.0)
    sl_max_usd = Column(Float, default=100.0)
    tp_min_usd = Column(Float, default=300.0)
    tp_max_usd = Column(Float, default=600.0)


class SignalsChannel(Base):
    """A channel that opted in to receive A+ auto-signals and hourly briefings."""

    __tablename__ = "signals_channels"
    channel_id = Column(String(64), primary_key=True)
    guild_id = Column(String(64), nullable=True)
    enabled_by = Column(String(64), nullable=False)
    mention_everyone = Column(Integer, default=1)
    min_confidence = Column(Integer, default=85)
    created_at = Column(DateTime, default=datetime.utcnow)


class DispatchedSignal(Base):
    """Tracks signals already broadcast so we never send the same setup twice."""

    __tablename__ = "dispatched_signals"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(32), index=True, nullable=False)
    side = Column(String(8), nullable=False)
    entry = Column(Float, nullable=False)
    confidence = Column(Integer, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)

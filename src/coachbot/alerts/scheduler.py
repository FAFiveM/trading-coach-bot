"""Async scheduler: daily market scan, price alerts, news alerts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import select, update

from ..config import settings
from ..data.feeds import fetch_calendar
from ..data.market_data import get_market_service
from ..data.news import aggregate_sentiment, fetch_news
from ..db.models import PriceAlert, UserSettings, WatchlistItem
from ..db.session import get_session
from ..strategy.engine import build_trade_idea


class CoachScheduler:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self._scheduler.add_job(
            self._daily_scan,
            "cron",
            hour=settings.coach_daily_hour_utc,
            minute=0,
            id="daily_scan",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._tick_alerts, "interval", minutes=1, id="price_alerts", replace_existing=True
        )
        self._scheduler.add_job(
            self._calendar_watch, "interval", minutes=15, id="calendar", replace_existing=True
        )
        self._scheduler.start()
        logger.info("scheduler started")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def _daily_scan(self) -> None:
        try:
            ms = get_market_service()
            symbols_default = ["BTCUSDT", "ETHUSDT", "EURUSD", "GBPUSD", "XAUUSD"]
            ideas = []
            for sym in symbols_default:
                try:
                    _, mtf = await ms.fetch_multi(sym, ["4h", "1h", "15m", "5m", "1m"], limit=400)
                    idea = build_trade_idea(sym, mtf)
                    if idea.side != "none":
                        ideas.append(idea)
                except Exception as exc:
                    logger.warning(f"daily scan {sym}: {exc}")

            news = await fetch_news("all", 8)
            label, score = aggregate_sentiment(news)

            lines = [
                f"☀️ **Daily Briefing** · {datetime.now(UTC).strftime('%A, %d %b %Y')}",
                f"Sentiment: **{label}** ({score:+.2f})",
                "",
                "📌 **Top Opportunities:**",
            ]
            if ideas:
                ideas.sort(key=lambda i: i.confidence, reverse=True)
                for idea in ideas[:5]:
                    lines.append(idea.to_summary())
                    lines.append("")
            else:
                lines.append("No high-quality setups right now — standing by for fresh liquidity.")

            lines.append("📰 **Top Headlines:**")
            for n in news[:3]:
                emoji = "📈" if n.sentiment > 0 else "📉" if n.sentiment < 0 else "➖"
                lines.append(f"{emoji} [{n.title}]({n.link})")

            text = "\n".join(lines)
            await self._broadcast(text)
        except Exception as exc:
            logger.exception(f"daily scan failed: {exc}")

    async def _tick_alerts(self) -> None:
        async with get_session() as s:
            res = await s.execute(select(PriceAlert).where(PriceAlert.triggered == 0))
            alerts = list(res.scalars())
        if not alerts:
            return
        ms = get_market_service()
        triggered_ids: list[int] = []
        for a in alerts:
            try:
                _, price = await ms.fetch_last_price(a.symbol)
            except Exception as exc:
                logger.debug(f"alert price fail {a.symbol}: {exc}")
                continue
            hit = (a.direction == "above" and price >= a.target) or (
                a.direction == "below" and price <= a.target
            )
            if hit:
                channel = self.bot.get_channel(int(a.channel_id))
                if channel:
                    arrow = "⬆️" if a.direction == "above" else "⬇️"
                    note = f" — *{a.note}*" if a.note else ""
                    try:
                        await channel.send(
                            f"{arrow} <@{a.user_id}> **{a.symbol}** hit `{price:.6g}` "
                            f"(target `{a.target:.6g}`){note}"
                        )
                    except Exception as exc:
                        logger.warning(f"alert send failed: {exc}")
                triggered_ids.append(a.id)
        if triggered_ids:
            async with get_session() as s:
                await s.execute(
                    update(PriceAlert).where(PriceAlert.id.in_(triggered_ids)).values(triggered=1)
                )
                await s.commit()

    async def _calendar_watch(self) -> None:
        try:
            events = await fetch_calendar("high")
        except Exception:
            return
        now = datetime.now(UTC)
        upcoming = [e for e in events if 0 < (e.when - now).total_seconds() < 30 * 60]
        if not upcoming:
            return
        text = "🚨 **High-impact event in <30min:**\n" + "\n".join(
            f"• **{e.country}** — {e.title} (`{e.when.strftime('%H:%M UTC')}`)" for e in upcoming
        )
        await self._broadcast(text)

    async def _broadcast(self, text: str) -> None:
        async with get_session() as s:
            res = await s.execute(select(UserSettings).where(UserSettings.daily_alerts_channel.isnot(None)))
            users = list(res.scalars())
            wl_res = await s.execute(select(WatchlistItem))
            _ = list(wl_res.scalars())  # warm cache
        seen: set[str] = set()
        for u in users:
            if u.daily_alerts_channel in seen:
                continue
            seen.add(u.daily_alerts_channel)
            channel = self.bot.get_channel(int(u.daily_alerts_channel))
            if not channel:
                continue
            try:
                await channel.send(text[:1990])
            except Exception as exc:
                logger.warning(f"broadcast failed: {exc}")
            await asyncio.sleep(0.2)

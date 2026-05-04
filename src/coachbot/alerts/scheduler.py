"""Async scheduler: continuous A+ scanner, hourly briefing, daily report,
price alerts, news/calendar alerts.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import delete, select, update

from .. import ui
from ..charts.render import render_trade_chart
from ..config import settings
from ..data.feeds import fetch_calendar
from ..data.market_data import get_market_service
from ..data.news import aggregate_sentiment, fetch_news
from ..db.models import (
    DispatchedSignal,
    PriceAlert,
    SignalsChannel,
    UserSettings,
)
from ..db.session import get_session
from ..profile import get_default_or_first_profile
from ..signal_view import TradeIdeaView, build_signal_embed
from ..strategy.engine import TradeIdea, build_trade_idea

SCAN_FOREX = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "NZDUSD",
    "USDCAD",
    "USDCHF",
    "EURJPY",
    "GBPJPY",
    "EURGBP",
    "AUDJPY",
    "EURAUD",
    "XAUUSD",
]

SCAN_CRYPTO = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
]

SCAN_TIMEFRAMES = ["4h", "1h", "15m", "5m", "1m"]
DEDUPE_WINDOW = timedelta(hours=4)
SIGNAL_PRICE_TOLERANCE = 0.0035  # 0.35% — same setup if entry within this band


class CoachScheduler:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scan_lock = asyncio.Lock()

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
            self._continuous_scan,
            "interval",
            minutes=10,
            id="continuous_scan",
            replace_existing=True,
            next_run_time=datetime.now(UTC) + timedelta(seconds=45),
        )
        self._scheduler.add_job(
            self._hourly_briefing,
            "cron",
            minute=5,
            id="hourly_briefing",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._tick_alerts, "interval", minutes=1, id="price_alerts", replace_existing=True
        )
        self._scheduler.add_job(
            self._calendar_watch, "interval", minutes=15, id="calendar", replace_existing=True
        )
        self._scheduler.add_job(
            self._cleanup_dispatched,
            "interval",
            hours=6,
            id="cleanup_dispatched",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("scheduler started (continuous A+ scanner + hourly briefing enabled)")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ---------- continuous A+ scanner ---------- #

    async def _continuous_scan(self) -> None:
        if self._scan_lock.locked():
            logger.debug("continuous_scan still running, skipping cycle")
            return
        async with self._scan_lock:
            ms = get_market_service()
            symbols = SCAN_FOREX + SCAN_CRYPTO
            sent = 0
            scanned = 0
            for sym in symbols:
                try:
                    _, mtf = await ms.fetch_multi(sym, SCAN_TIMEFRAMES, limit=400)
                except Exception as exc:
                    logger.debug(f"scan fetch failed {sym}: {exc}")
                    continue
                scanned += 1
                try:
                    idea = build_trade_idea(sym, mtf)
                except Exception as exc:
                    logger.warning(f"scan idea failed {sym}: {exc}")
                    continue
                if idea.side == "none" or idea.confidence < 85:
                    continue
                already = await self._already_dispatched(sym, idea)
                if already:
                    continue
                df_chart = None
                for key in ("15m", "5m", "1m"):
                    cand = mtf.get(key)
                    if cand is not None and not cand.empty:
                        df_chart = cand
                        break
                chart_path = None
                if df_chart is not None and not df_chart.empty:
                    try:
                        chart_path = render_trade_chart(sym, "15m", df_chart, idea)
                    except Exception as exc:
                        logger.warning(f"scan chart failed {sym}: {exc}")
                ok = await self._broadcast_signal(idea, chart_path)
                if ok:
                    await self._record_dispatched(idea)
                    sent += 1
                if sent >= 5:
                    break
            logger.info(f"continuous_scan: scanned {scanned}/{len(symbols)} symbols, dispatched {sent}")

    async def _already_dispatched(self, symbol: str, idea: TradeIdea) -> bool:
        cutoff = datetime.utcnow() - DEDUPE_WINDOW
        async with get_session() as s:
            res = await s.execute(
                select(DispatchedSignal)
                .where(DispatchedSignal.symbol == symbol)
                .where(DispatchedSignal.side == idea.side)
                .where(DispatchedSignal.sent_at >= cutoff)
            )
            rows = list(res.scalars())
        for r in rows:
            if r.entry == 0:
                continue
            if abs(idea.entry - r.entry) / abs(r.entry) <= SIGNAL_PRICE_TOLERANCE:
                return True
        return False

    async def _record_dispatched(self, idea: TradeIdea) -> None:
        async with get_session() as s:
            s.add(
                DispatchedSignal(
                    symbol=idea.symbol,
                    side=idea.side,
                    entry=float(idea.entry),
                    confidence=int(idea.confidence),
                )
            )
            await s.commit()

    async def _cleanup_dispatched(self) -> None:
        cutoff = datetime.utcnow() - timedelta(days=3)
        async with get_session() as s:
            await s.execute(delete(DispatchedSignal).where(DispatchedSignal.sent_at < cutoff))
            await s.commit()

    async def _broadcast_signal(self, idea: TradeIdea, chart_path) -> bool:
        async with get_session() as s:
            res = await s.execute(select(SignalsChannel))
            chans = list(res.scalars())
        if not chans:
            return False
        profile = await get_default_or_first_profile()
        embed = build_signal_embed(idea, profile=profile)
        sent_any = False
        for c in chans:
            if idea.confidence < int(c.min_confidence or 85):
                continue
            channel = self.bot.get_channel(int(c.channel_id))
            if channel is None:
                continue
            content = "@everyone" if c.mention_everyone else None
            try:
                file = discord.File(str(chart_path)) if chart_path else None
                if file:
                    embed.set_image(url=f"attachment://{chart_path.name}")
                view = TradeIdeaView(idea)
                await channel.send(
                    content=content,
                    embed=embed,
                    file=file,
                    view=view,
                    allowed_mentions=discord.AllowedMentions(everyone=True),
                )
                sent_any = True
            except Exception as exc:
                logger.warning(f"signal broadcast failed for channel {c.channel_id}: {exc}")
            await asyncio.sleep(0.3)
        return sent_any

    # ---------- hourly market briefing ---------- #

    async def _hourly_briefing(self) -> None:
        async with get_session() as s:
            res = await s.execute(select(SignalsChannel))
            chans = list(res.scalars())
        if not chans:
            return
        try:
            ms = get_market_service()
            top_lines: list[str] = []
            best: list[TradeIdea] = []
            for sym in SCAN_FOREX[:6] + SCAN_CRYPTO[:3]:
                try:
                    _, mtf = await ms.fetch_multi(sym, ["1h", "15m", "5m", "1m"], limit=300)
                    idea = build_trade_idea(sym, mtf)
                    best.append(idea)
                except Exception as exc:
                    logger.debug(f"hourly idea fail {sym}: {exc}")
            best.sort(key=lambda i: i.confidence, reverse=True)
            for idea in best[:5]:
                arrow = ui.side_arrow(idea.side)
                top_lines.append(f"{arrow}  **{idea.symbol}** — {idea.confidence}% ({idea.grade})")
            news = await fetch_news("all", 5)
            label, score = aggregate_sentiment(news)

            embed = ui.base_embed(
                f"🕐 Hourly Market Pulse · {datetime.now(UTC).strftime('%H:%M UTC')}",
                color=ui.COLOR_INFO,
            )
            embed.description = (
                f"Sentiment: **{label}** ({score:+.2f})\nTop setups across major forex + crypto right now:"
            )
            embed.add_field(
                name="📊 Top Setups",
                value="\n".join(top_lines) if top_lines else "No setups detected.",
                inline=False,
            )
            if news:
                head = "\n".join(f"• [{n.title[:90]}]({n.link})" for n in news[:3])
                embed.add_field(name="📰 Headlines", value=head, inline=False)
        except Exception as exc:
            logger.exception(f"hourly briefing build failed: {exc}")
            return

        for c in chans:
            channel = self.bot.get_channel(int(c.channel_id))
            if channel is None:
                continue
            try:
                await channel.send(embed=embed)
            except Exception as exc:
                logger.warning(f"hourly briefing send failed: {exc}")
            await asyncio.sleep(0.25)

    # ---------- daily scan (kept) ---------- #

    async def _daily_scan(self) -> None:
        try:
            ms = get_market_service()
            symbols_default = SCAN_FOREX[:5] + SCAN_CRYPTO[:3]
            ideas = []
            for sym in symbols_default:
                try:
                    _, mtf = await ms.fetch_multi(sym, SCAN_TIMEFRAMES, limit=400)
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
            sig_res = await s.execute(select(SignalsChannel))
            sig_chans = list(sig_res.scalars())
        seen: set[str] = set()
        targets: list[str] = []
        for u in users:
            if u.daily_alerts_channel and u.daily_alerts_channel not in seen:
                seen.add(u.daily_alerts_channel)
                targets.append(u.daily_alerts_channel)
        for c in sig_chans:
            if c.channel_id not in seen:
                seen.add(c.channel_id)
                targets.append(c.channel_id)
        for cid in targets:
            channel = self.bot.get_channel(int(cid))
            if not channel:
                continue
            try:
                await channel.send(text[:1990])
            except Exception as exc:
                logger.warning(f"broadcast failed: {exc}")
            await asyncio.sleep(0.2)

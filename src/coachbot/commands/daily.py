"""/daily and /set_daily_channel commands."""

from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord import app_commands
from loguru import logger
from sqlalchemy import select

from .. import ui
from ..data.feeds import fetch_calendar
from ..data.market_data import get_market_service
from ..data.news import aggregate_sentiment, fetch_cryptopanic, fetch_news
from ..db.models import UserSettings
from ..db.session import get_session
from ..strategy.engine import build_trade_idea


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(
        name="daily",
        description="Daily market briefing — top opportunities, news, sentiment, calendar.",
    )
    async def daily(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        ms = get_market_service()
        symbols = ["BTCUSDT", "ETHUSDT", "EURUSD", "GBPUSD", "XAUUSD"]
        ideas = []
        for sym in symbols:
            try:
                _, mtf = await ms.fetch_multi(sym, ["4h", "1h", "15m", "5m", "1m"], limit=400)
                idea = build_trade_idea(sym, mtf)
                ideas.append(idea)
            except Exception as exc:
                logger.warning(f"daily {sym}: {exc}")
        ideas.sort(key=lambda i: i.confidence, reverse=True)

        news = await fetch_news("all", 10)
        cp = await fetch_cryptopanic(limit=5)
        all_news = news + cp
        label, score = aggregate_sentiment(all_news)
        cal = await fetch_calendar("high")

        title = f"☀️ Daily Briefing — {datetime.now(UTC).strftime('%A, %d %b %Y')}"
        embed = ui.base_embed(
            title,
            color=ui.COLOR_INFO,
            description=(
                "Your end-of-cycle market scan: structural bias, top opportunities, "
                "narrative sentiment, and the calendar that can break the tape."
            ),
        )

        sentiment_emoji = ui.sentiment_emoji(score)
        embed.add_field(
            name="🌡️ Market Sentiment",
            value=f"{sentiment_emoji} **{label}** ({score:+.2f})  ·  {len(all_news)} headlines analyzed",
            inline=False,
        )

        opp = [i for i in ideas if i.side != "none"]
        watched_count = len([i for i in ideas if i.side == "none"])
        if opp:
            chunks = []
            for i in opp[:3]:
                bar = ui.confidence_bar(i.confidence, slots=10)
                chunks.append(f"{i.to_summary()}\n`{bar}` **{i.confidence}%**")
            embed.add_field(
                name="🎯 Top Opportunities",
                value="\n\n".join(chunks),
                inline=False,
            )
        if watched_count:
            embed.add_field(
                name="👁️ On Watch (no clean setup yet)",
                value=", ".join(f"`{i.symbol}`" for i in ideas if i.side == "none")[:1024],
                inline=False,
            )
        if not opp and not watched_count:
            embed.add_field(
                name="🎯 Opportunities",
                value="No clean signals across the universe right now. Patience.",
                inline=False,
            )

        if all_news:
            embed.add_field(
                name="📰 Headlines",
                value="\n".join(
                    f"{ui.sentiment_emoji(n.sentiment)} [{n.title[:90]}]({n.link})" for n in all_news[:6]
                ),
                inline=False,
            )

        if cal:
            now = datetime.now(UTC)
            today = [e for e in cal if e.when.date() == now.date() and e.when >= now]
            if today:
                embed.add_field(
                    name="📅 High-Impact Events Today",
                    value="\n".join(
                        f"• `{e.when.strftime('%H:%M')} UTC` — **{e.country}** {e.title}" for e in today[:6]
                    ),
                    inline=False,
                )

        await interaction.followup.send(embed=embed)

    @tree.command(
        name="set_daily_channel",
        description="Subscribe this channel to receive the automated daily briefing.",
    )
    async def set_daily(interaction: discord.Interaction) -> None:
        async with get_session() as s:
            res = await s.execute(
                select(UserSettings).where(UserSettings.user_id == str(interaction.user.id))
            )
            us = res.scalar_one_or_none()
            if us is None:
                us = UserSettings(user_id=str(interaction.user.id))
                s.add(us)
            us.daily_alerts_channel = str(interaction.channel_id)
            await s.commit()
        embed = ui.base_embed(
            "📡 Daily Briefing — Channel Linked",
            color=ui.COLOR_LONG,
            description=(
                "This channel will receive the automated daily briefing.\n"
                "Delivery: **every day at the configured UTC hour**.\n"
                "You can run `/daily` any time for an on-demand snapshot."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

"""/daily and /set_daily_channel commands."""

from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord import app_commands
from loguru import logger
from sqlalchemy import select

from ..data.feeds import fetch_calendar
from ..data.market_data import get_market_service
from ..data.news import aggregate_sentiment, fetch_cryptopanic, fetch_news
from ..db.models import UserSettings
from ..db.session import get_session
from ..strategy.engine import build_trade_idea


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="daily", description="الملخص اليومي للسوق وأهم الفرص")
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

        news = await fetch_news("all", 8)
        cp = await fetch_cryptopanic(limit=5)
        all_news = news + cp
        label, score = aggregate_sentiment(all_news)
        cal = await fetch_calendar("high")

        embed = discord.Embed(
            title=f"☀️ Daily Briefing — {datetime.now(UTC).strftime('%Y-%m-%d')}",
            color=0x42A5F5,
        )
        embed.add_field(name="🌡️ مزاج السوق", value=f"{label} ({score:+.2f})", inline=False)

        opp = [i for i in ideas if i.side != "none"]
        if opp:
            embed.add_field(
                name="🎯 أعلى 3 فرص",
                value="\n\n".join(i.to_summary() for i in opp[:3]),
                inline=False,
            )
        else:
            embed.add_field(name="🎯 الفرص", value="لا توجد فرص واضحة الآن.", inline=False)

        if all_news:
            embed.add_field(
                name="📰 أهم الأخبار",
                value="\n".join(
                    f"{'📈' if n.sentiment > 0 else '📉' if n.sentiment < 0 else '➖'} [{n.title[:80]}]({n.link})"
                    for n in all_news[:5]
                ),
                inline=False,
            )

        if cal:
            now = datetime.now(UTC)
            today = [e for e in cal if e.when.date() == now.date()]
            if today:
                embed.add_field(
                    name="📅 أحداث اليوم (تأثير عالي)",
                    value="\n".join(
                        f"• {e.country} — {e.title} ({e.when.strftime('%H:%M UTC')})" for e in today[:6]
                    ),
                    inline=False,
                )

        await interaction.followup.send(embed=embed)

    @tree.command(name="set_daily_channel", description="اختر القناة اللي تستقبل الملخص اليومي")
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
        await interaction.response.send_message(
            f"✅ راح تستلم الملخص اليومي في هذه القناة الساعة <t:{0}:t> UTC.",
            ephemeral=True,
        )

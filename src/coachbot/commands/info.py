"""Misc info commands: news, whales, traders, calendar, lesson, backtest, compare, coach."""

from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord import app_commands

from ..coach.lessons import COACH_QUESTIONS, random_lesson
from ..data.feeds import fetch_calendar, fetch_cot_summary, fetch_trader_feed
from ..data.market_data import get_market_service
from ..data.news import aggregate_sentiment, fetch_cryptopanic, fetch_news
from ..data.onchain import fetch_btc_metrics, fetch_eth_whales, fetch_funding
from ..strategy.backtest import backtest
from ..strategy.engine import build_trade_idea
from ..utils.symbols import parse_symbol


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="news", description="آخر الأخبار + sentiment")
    @app_commands.choices(
        market=[
            app_commands.Choice(name="all", value="all"),
            app_commands.Choice(name="crypto", value="crypto"),
            app_commands.Choice(name="forex", value="forex"),
        ]
    )
    async def news_cmd(
        interaction: discord.Interaction, market: app_commands.Choice[str] | None = None
    ) -> None:
        await interaction.response.defer(thinking=True)
        m = market.value if market else "all"
        rss = await fetch_news(m, 8)
        cp = await fetch_cryptopanic(limit=5) if m in ("all", "crypto") else []
        items = rss + cp
        if not items:
            await interaction.followup.send("لا توجد أخبار حالياً.")
            return
        label, score = aggregate_sentiment(items)
        embed = discord.Embed(title=f"📰 الأخبار — {label} ({score:+.2f})", color=0xFF9800)
        embed.description = "\n".join(
            f"{'📈' if n.sentiment > 0 else '📉' if n.sentiment < 0 else '➖'} [{n.title[:80]}]({n.link})"
            for n in items[:10]
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="whales", description="حركات المحافظ الكبيرة + funding")
    async def whales_cmd(interaction: discord.Interaction, symbol: str = "BTC") -> None:
        await interaction.response.defer(thinking=True)
        base = symbol.upper().replace("USDT", "").replace("USD", "")
        funding = await fetch_funding(base)
        whales = await fetch_eth_whales() if base == "ETH" else []
        embed = discord.Embed(title=f"🐋 {base} — Whale & Derivatives", color=0x6A1B9A)
        if funding:
            ls = f"{funding.long_short_ratio:.2f}" if funding.long_short_ratio else "—"
            oi = f"{funding.open_interest:,.0f}" if funding.open_interest else "—"
            embed.add_field(
                name="Derivatives",
                value=(
                    f"Funding: `{funding.funding_rate * 100:+.4f}%`\n"
                    f"Open Interest: `{oi}`\n"
                    f"Long/Short Ratio: `{ls}`"
                ),
                inline=False,
            )
        if whales:
            text = "\n".join(
                f"• {w.value_eth:.0f} ETH — `{w.from_addr[:8]}…` → `{w.to_addr[:8]}…` ([tx](https://etherscan.io/tx/{w.hash}))"
                for w in whales[:5]
            )
            embed.add_field(name="آخر تحويلات الحيتان", value=text, inline=False)
        if base == "BTC":
            metrics = await fetch_btc_metrics()
            if metrics:
                embed.add_field(
                    name="Network",
                    value=f"Hashrate: `{metrics.get('hashrate_ehs', 0):.1f} EH/s`\nMempool: `{int(metrics.get('mempool_count', 0))} txs`",
                    inline=False,
                )
        if not embed.fields:
            embed.description = "لا توجد بيانات متاحة (قد تحتاج Etherscan API key للحيتان)."
        await interaction.followup.send(embed=embed)

    @tree.command(name="traders", description="آخر تغريدات متداولين معروفين")
    async def traders_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        posts = await fetch_trader_feed()
        if not posts:
            await interaction.followup.send("لا توجد بيانات (Nitter قد يكون محجوب).")
            return
        embed = discord.Embed(title="👥 Top Traders Feed", color=0x1DA1F2)
        embed.description = "\n".join(f"• **@{p.handle}** — [{p.title[:80]}]({p.link})" for p in posts[:10])
        await interaction.followup.send(embed=embed)

    @tree.command(name="calendar", description="أحداث اقتصادية مهمة قادمة")
    async def calendar_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        events = await fetch_calendar("high")
        if not events:
            await interaction.followup.send("لا توجد أحداث.")
            return
        now = datetime.now(UTC)
        upcoming = [e for e in events if e.when >= now][:8]
        embed = discord.Embed(title="📅 Economic Calendar (high)", color=0xFF5722)
        embed.description = "\n".join(
            f"• `{e.when.strftime('%a %H:%M UTC')}` — **{e.country}** {e.title}" for e in upcoming
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="cot", description="تقرير COT الأسبوعي (المضاربون الكبار)")
    async def cot_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        text = await fetch_cot_summary()
        if not text:
            await interaction.followup.send("تعذّر جلب COT.")
            return
        await interaction.followup.send(f"```\n{text[:1900]}\n```")

    @tree.command(name="lesson", description="درس تداول قصير لليوم")
    async def lesson_cmd(interaction: discord.Interaction) -> None:
        title, body = random_lesson()
        embed = discord.Embed(title=f"🎓 {title}", description=body, color=0x4CAF50)
        await interaction.response.send_message(embed=embed)

    @tree.command(name="coach", description="أسئلة المدرّب قبل دخول الصفقة")
    async def coach_cmd(interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="🧠 قبل الدخول، اسأل نفسك:", color=0x8E24AA)
        embed.description = "\n".join(f"• {q}" for q in COACH_QUESTIONS)
        await interaction.response.send_message(embed=embed)

    @tree.command(name="backtest", description="باك تيست بسيط للاستراتيجية")
    async def backtest_cmd(interaction: discord.Interaction, symbol: str, timeframe: str = "15m") -> None:
        await interaction.response.defer(thinking=True)
        ms = get_market_service()
        try:
            inst, df = await ms.fetch_ohlcv(symbol, timeframe, 1000)
        except Exception as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return
        result = backtest(inst.display, df, timeframe)
        await interaction.followup.send(result.to_text())

    @tree.command(name="compare", description="قارن تحليلك بتحليل البوت")
    async def compare_cmd(
        interaction: discord.Interaction,
        symbol: str,
        my_side: str,
        my_entry: float,
        my_sl: float,
        my_tp: float,
    ) -> None:
        await interaction.response.defer(thinking=True)
        ms = get_market_service()
        try:
            inst, mtf = await ms.fetch_multi(symbol, ["4h", "1h", "15m", "5m", "1m"], limit=400)
        except Exception as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return
        idea = build_trade_idea(inst.display, mtf)
        my_rr = abs(my_tp - my_entry) / max(abs(my_entry - my_sl), 1e-9)
        agreement = "متفق" if my_side.lower() == idea.side else "مختلف"
        embed = discord.Embed(title=f"🔍 مقارنة — {inst.display}", color=0x00897B)
        embed.add_field(
            name="تحليلك",
            value=f"{my_side.upper()} @ {my_entry} | SL {my_sl} | TP {my_tp} | R:R 1:{my_rr:.2f}",
            inline=False,
        )
        embed.add_field(name="تحليل البوت", value=idea.to_summary(), inline=False)
        embed.add_field(name="التطابق", value=f"**{agreement}** | الثقة: {idea.confidence}%", inline=False)
        if idea.confluences:
            embed.add_field(
                name="ملاحظات البوت", value="\n".join(f"• {c}" for c in idea.confluences[:5]), inline=False
            )
        await interaction.followup.send(embed=embed)

    @tree.command(name="price", description="سعر فوري لزوج")
    async def price_cmd(interaction: discord.Interaction, symbol: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            inst = parse_symbol(symbol)
            ms = get_market_service()
            _, p = await ms.fetch_last_price(symbol)
        except Exception as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return
        await interaction.followup.send(f"💰 **{inst.display}** = `{p:.6g}`")

    @tree.command(name="help_coach", description="عرض كل أوامر البوت")
    async def help_cmd(interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="📖 أوامر البوت", color=0x37474F)
        embed.description = (
            "**التحليل**\n"
            "`/analyze symbol` — تحليل MTF + خطة دخول 1m + شارت\n"
            "`/compare symbol my_side my_entry my_sl my_tp` — قارن تحليلك\n"
            "`/backtest symbol [tf]` — باك تيست\n"
            "`/price symbol` — سعر فوري\n\n"
            "**اليومي والمتابعة**\n"
            "`/daily` — ملخص السوق + أهم 3 فرص + أخبار\n"
            "`/set_daily_channel` — اختر قناة الإشعارات اليومية\n"
            "`/watchlist add/remove/show` — قائمة متابعة\n"
            "`/alert add/list/remove` — تنبيهات الأسعار\n\n"
            "**معلومات**\n"
            "`/news` `/whales` `/traders` `/calendar` `/cot`\n\n"
            "**المحفظة والجورنال**\n"
            "`/portfolio open/close/show` — تتبع الصفقات\n"
            "`/journal add/show` — جورنال\n\n"
            "**الكوتش**\n"
            "`/coach` — أسئلة قبل الدخول\n"
            "`/lesson` — درس اليوم"
        )
        await interaction.response.send_message(embed=embed)

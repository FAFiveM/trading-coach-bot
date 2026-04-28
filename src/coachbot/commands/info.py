"""Misc info commands: news, whales, traders, calendar, lesson, backtest, compare, coach, price, help."""

from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord import app_commands

from .. import ui
from ..coach.lessons import COACH_QUESTIONS, random_lesson
from ..data.feeds import fetch_calendar, fetch_cot_summary, fetch_trader_feed
from ..data.market_data import get_market_service
from ..data.news import aggregate_sentiment, fetch_cryptopanic, fetch_news
from ..data.onchain import fetch_btc_metrics, fetch_eth_whales, fetch_funding
from ..strategy.backtest import backtest
from ..strategy.engine import build_trade_idea
from ..utils.symbols import parse_symbol


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="news", description="Latest market news with aggregated sentiment.")
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
        rss = await fetch_news(m, 10)
        cp = await fetch_cryptopanic(limit=5) if m in ("all", "crypto") else []
        items = rss + cp
        if not items:
            embed = ui.base_embed(
                "📰 News Feed",
                color=ui.COLOR_WARN,
                description="No news available right now — try again in a few minutes.",
            )
            await interaction.followup.send(embed=embed)
            return
        label, score = aggregate_sentiment(items)
        emoji = ui.sentiment_emoji(score)
        title = f"📰 News & Narrative — {emoji} {label} ({score:+.2f})"
        embed = ui.base_embed(title, color=ui.COLOR_INFO)
        embed.description = "\n".join(
            f"{ui.sentiment_emoji(n.sentiment)} [{n.title[:100]}]({n.link})" for n in items[:12]
        )
        embed.add_field(
            name="🧠 Read",
            value=(
                f"Aggregate score across **{len(items)}** headlines. "
                "Use this as backdrop, not as a trigger — narratives lead price only "
                "when liquidity confirms."
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="whales", description="On-chain whale moves + derivatives positioning.")
    async def whales_cmd(interaction: discord.Interaction, symbol: str = "BTC") -> None:
        await interaction.response.defer(thinking=True)
        base = symbol.upper().replace("USDT", "").replace("USD", "")
        funding = await fetch_funding(base)
        whales = await fetch_eth_whales() if base == "ETH" else []
        embed = ui.base_embed(
            f"🐋 {base} — Whale & Derivatives Intel",
            color=ui.COLOR_PURPLE,
            description="Smart-money flows + perpetual positioning. Read it for context, not signals.",
        )
        if funding:
            ls = f"{funding.long_short_ratio:.2f}" if funding.long_short_ratio else "—"
            oi = f"{funding.open_interest:,.0f}" if funding.open_interest else "—"
            embed.add_field(
                name="📐 Derivatives",
                value=(
                    f"Funding rate: `{funding.funding_rate * 100:+.4f}%`\n"
                    f"Open Interest: `{oi}`\n"
                    f"Long / Short: `{ls}`"
                ),
                inline=False,
            )
        if whales:
            text = "\n".join(
                f"• **{w.value_eth:.0f} ETH** — `{w.from_addr[:8]}…` → `{w.to_addr[:8]}…` "
                f"([tx](https://etherscan.io/tx/{w.hash}))"
                for w in whales[:5]
            )
            embed.add_field(name="🐋 Recent Whale Transfers", value=text, inline=False)
        if base == "BTC":
            metrics = await fetch_btc_metrics()
            if metrics:
                embed.add_field(
                    name="🛰️ Network",
                    value=(
                        f"Hashrate: `{metrics.get('hashrate_ehs', 0):.1f} EH/s`\n"
                        f"Mempool: `{int(metrics.get('mempool_count', 0))} txs`"
                    ),
                    inline=False,
                )
        if not embed.fields:
            embed.description = (
                "No data returned for this symbol right now. "
                "Whale telemetry needs an Etherscan API key for ETH."
            )
        await interaction.followup.send(embed=embed)

    @tree.command(name="traders", description="Latest posts from notable trader accounts.")
    async def traders_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        posts = await fetch_trader_feed()
        if not posts:
            embed = ui.base_embed(
                "👥 Top Traders Feed",
                color=ui.COLOR_WARN,
                description="No data available — Nitter mirrors may be rate-limited. Retry later.",
            )
            await interaction.followup.send(embed=embed)
            return
        embed = ui.base_embed(
            "👥 Top Traders — Live Feed",
            color=ui.COLOR_CYAN,
            description="Headlines from monitored handles. Cross-reference with your own thesis.",
        )
        embed.description = (
            (embed.description or "")
            + "\n\n"
            + "\n".join(f"• **@{p.handle}** — [{p.title[:90]}]({p.link})" for p in posts[:10])
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="calendar", description="Upcoming high-impact economic events (UTC).")
    async def calendar_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        events = await fetch_calendar("high")
        if not events:
            embed = ui.base_embed(
                "📅 Economic Calendar",
                color=ui.COLOR_WARN,
                description="No high-impact events on the wire.",
            )
            await interaction.followup.send(embed=embed)
            return
        now = datetime.now(UTC)
        upcoming = [e for e in events if e.when >= now][:10]
        embed = ui.base_embed(
            "📅 Economic Calendar — High Impact",
            color=ui.COLOR_DANGER,
            description="Tighten risk and avoid new entries 30 minutes before each release.",
        )
        embed.description += "\n\n" + "\n".join(
            f"• `{e.when.strftime('%a %d %b · %H:%M UTC')}` — **{e.country}** {e.title}" for e in upcoming
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="cot", description="Weekly CFTC Commitment of Traders summary.")
    async def cot_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        text = await fetch_cot_summary()
        if not text:
            embed = ui.base_embed(
                "🏦 CFTC COT Report",
                color=ui.COLOR_WARN,
                description="Could not fetch the COT report. Retry later.",
            )
            await interaction.followup.send(embed=embed)
            return
        embed = ui.base_embed(
            "🏦 CFTC — Commitment of Traders",
            color=ui.COLOR_INFO,
            description="Smart-money positioning across the major futures markets.",
        )
        embed.add_field(name="Snapshot", value=ui.code_block(text[:1800]), inline=False)
        await interaction.followup.send(embed=embed)

    @tree.command(name="lesson", description="A short trading lesson — daily reminder.")
    async def lesson_cmd(interaction: discord.Interaction) -> None:
        title, body = random_lesson()
        embed = ui.base_embed(f"🎓 Lesson — {title}", color=ui.COLOR_LONG, description=body)
        embed.add_field(
            name="✍️ Apply It",
            value="Open `/journal add` and write one sentence on how this lesson applies to your last trade.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @tree.command(name="coach", description="Pre-entry checklist — ask yourself before every click.")
    async def coach_cmd(interaction: discord.Interaction) -> None:
        embed = ui.base_embed(
            "🧠 Pre-Entry Checklist",
            color=ui.COLOR_PURPLE,
            description="Run this list before every order. If any answer is unclear — don't trade.",
        )
        embed.add_field(
            name="Checklist",
            value="\n".join(f"☐ {q}" for q in COACH_QUESTIONS),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @tree.command(name="backtest", description="Walk-forward backtest of the strategy.")
    async def backtest_cmd(interaction: discord.Interaction, symbol: str, timeframe: str = "15m") -> None:
        await interaction.response.defer(thinking=True)
        ms = get_market_service()
        try:
            inst, df = await ms.fetch_ohlcv(symbol, timeframe, 1000)
        except Exception as exc:
            embed = ui.base_embed("⚠️ Backtest Failed", color=ui.COLOR_DANGER, description=f"```\n{exc}\n```")
            await interaction.followup.send(embed=embed)
            return
        result = backtest(inst.display, df, timeframe)
        embed = ui.base_embed(
            f"📊 Backtest — {inst.display} ({timeframe})",
            color=ui.COLOR_INFO,
            description="Liquidity Sweep + EMA50 alignment, fixed 1:3 R:R, 1R risk per trade.",
        )
        embed.add_field(
            name="Results",
            value=ui.code_block(
                f"Trades        : {result.trades}\n"
                f"Wins          : {result.wins}\n"
                f"Losses        : {result.losses}\n"
                f"Win rate      : {result.win_rate:.1f}%\n"
                f"Avg R / trade : {result.avg_rr:+.2f}\n"
                f"Total R       : {result.total_r:+.2f}\n"
                f"Max DD        : {result.max_dd_r:.2f}R",
                "yaml",
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="compare", description="Compare your trade idea with the bot's view.")
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
            await interaction.followup.send(
                embed=ui.base_embed(
                    "⚠️ Compare Failed",
                    color=ui.COLOR_DANGER,
                    description=f"```\n{exc}\n```",
                )
            )
            return
        idea = build_trade_idea(inst.display, mtf)
        my_rr = abs(my_tp - my_entry) / max(abs(my_entry - my_sl), 1e-9)
        agreement = my_side.lower() == idea.side
        verdict = "✅ Aligned" if agreement else "⚠️ Diverging"
        color = ui.COLOR_LONG if agreement else ui.COLOR_WARN

        embed = ui.base_embed(f"🔍 Compare — {inst.display}", color=color, description=verdict)
        embed.add_field(
            name="🧑 Your Plan",
            value=ui.code_block(
                f"Side  : {my_side.upper()}\n"
                f"Entry : {my_entry}\n"
                f"SL    : {my_sl}\n"
                f"TP    : {my_tp}\n"
                f"R:R   : 1:{my_rr:.2f}",
                "yaml",
            ),
            inline=False,
        )
        embed.add_field(name="🤖 Bot Plan", value=idea.to_summary(), inline=False)
        embed.add_field(
            name="📈 Confidence",
            value=f"`{ui.confidence_bar(idea.confidence)}`  **{idea.confidence}%**",
            inline=False,
        )
        if idea.confluences:
            embed.add_field(
                name="✅ Bot Confluences",
                value="\n".join(f"• {c}" for c in idea.confluences[:6]),
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @tree.command(name="price", description="Live last price for a symbol.")
    async def price_cmd(interaction: discord.Interaction, symbol: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            inst = parse_symbol(symbol)
            ms = get_market_service()
            _, p = await ms.fetch_last_price(symbol)
        except Exception as exc:
            embed = ui.base_embed(
                "⚠️ Price Lookup Failed",
                color=ui.COLOR_DANGER,
                description=f"```\n{exc}\n```",
            )
            await interaction.followup.send(embed=embed)
            return
        embed = ui.base_embed(
            f"💰 {inst.display}", color=ui.COLOR_INFO, description=f"## `{ui.fmt_price(p)}`"
        )
        embed.add_field(
            name="Quick Action",
            value=f"`/analyze {inst.display}` for a full multi-TF read on this pair.",
            inline=False,
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="help_coach", description="Show every command and what it does.")
    async def help_cmd(interaction: discord.Interaction) -> None:
        embed = ui.base_embed(
            "📖 khadooojjjjiFX Trading Coach — Command Reference",
            color=ui.COLOR_PURPLE,
            description=(
                "Your 24/7 multi-timeframe trading copilot. All commands are slash-commands.\n"
                "Type `/` and pick a command to autocomplete arguments."
            ),
        )
        embed.add_field(
            name="📊 Analysis",
            value=(
                "`/analyze <symbol>` — full MTF read + chart + trade plan\n"
                "`/compare <symbol> <side> <entry> <sl> <tp>` — your plan vs the bot\n"
                "`/backtest <symbol> [tf]` — walk-forward strategy stats\n"
                "`/price <symbol>` — live last price"
            ),
            inline=False,
        )
        embed.add_field(
            name="📰 Market Context",
            value=(
                "`/daily` — full daily briefing (opportunities + news + calendar)\n"
                "`/news [market]` — headlines + sentiment score\n"
                "`/calendar` — upcoming high-impact economic events\n"
                "`/cot` — weekly CFTC positioning\n"
                "`/whales [symbol]` — on-chain whale moves + derivatives\n"
                "`/traders` — latest posts from notable trader handles"
            ),
            inline=False,
        )
        embed.add_field(
            name="📡 Watch & Alerts",
            value=(
                "`/watchlist add|remove|show` — manage your favorites\n"
                "`/alert add|list|remove` — price-cross alerts ping you on hit\n"
                "`/set_daily_channel` — auto-post daily briefing here"
            ),
            inline=False,
        )
        embed.add_field(
            name="💼 Portfolio & Journal",
            value=(
                "`/portfolio open|close|show` — track every trade and live R:R\n"
                "`/journal add|show` — log your thesis and emotions"
            ),
            inline=False,
        )
        embed.add_field(
            name="🧠 Coach",
            value=("`/coach` — pre-entry checklist\n`/lesson` — daily trading lesson"),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

"""/analyze command — multi-timeframe trade idea + chart screenshot."""

from __future__ import annotations

import discord
from discord import app_commands
from loguru import logger

from .. import ui
from ..charts.render import render_trade_chart
from ..coach.lessons import COACH_QUESTIONS
from ..data.market_data import get_market_service
from ..profile import get_profile_for_user
from ..signal_view import TradeIdeaView, one_tap_copy_block, usd_breakdown
from ..strategy.engine import build_trade_idea


def _bias_label_emoji(label: str) -> str:
    if label == "bullish":
        return "🟢"
    if label == "bearish":
        return "🔴"
    return "⚪"


def _format_idea_embed(idea, inst_display: str, profile=None) -> discord.Embed:
    color = ui.side_color(idea.side)
    title = f"📊 {inst_display} — {ui.side_arrow(idea.side)}"

    if idea.side == "none":
        description = (
            "**No clean setup right now.** The market lacks the structural "
            "alignment required by the Liquidity Sweep + MTF Confluence model. "
            "Stand by — capital preserved is capital ready."
        )
    else:
        verb = "Long" if idea.side == "long" else "Short"
        description = (
            f"**Tactical {verb} Setup detected** on `{inst_display}`.\n"
            "Every level below is anchored to higher-timeframe context, "
            "smart-money liquidity events, and ATR-scaled risk."
        )

    embed = ui.base_embed(title, color=color, description=description)

    bias_lines = []
    for b in idea.biases:
        emo = _bias_label_emoji(b.label)
        reasons = " · ".join(b.reasons[:2]) or "—"
        bias_lines.append(f"{emo} `{b.timeframe:>3}` **{b.label.title()}** ({b.score:+.2f}) — {reasons}")
    embed.add_field(
        name="🧭 Multi-Timeframe Bias",
        value="\n".join(bias_lines) or "—",
        inline=False,
    )

    if idea.side != "none":
        plan_table = (
            f"Entry  →  {ui.fmt_price(idea.entry):>14}\n"
            f"Stop   →  {ui.fmt_price(idea.stop_loss):>14}\n"
            f"TP1    →  {ui.fmt_price(idea.take_profit_1):>14}   (1:{idea.rr_1:.2f})\n"
            f"TP2    →  {ui.fmt_price(idea.take_profit_2):>14}   (1:{idea.rr_2:.2f})\n"
            f"TP3    →  {ui.fmt_price(idea.take_profit_3):>14}   (1:{idea.rr_3:.2f})"
        )
        embed.add_field(
            name="🎯 Trade Plan",
            value=ui.code_block(plan_table, "yaml"),
            inline=False,
        )

        risk_pips = abs(idea.entry - idea.stop_loss)
        embed.add_field(
            name="🛡️ Risk Profile",
            value=(
                f"Risk per unit: `{ui.fmt_price(risk_pips)}`\n"
                f"Avg target: **1:{idea.avg_rr:.2f}** R:R\n"
                f"Suggested risk: **≤1% of equity per trade**"
            ),
            inline=True,
        )

        bar = ui.confidence_bar(idea.confidence)
        embed.add_field(
            name="📈 Confidence",
            value=f"`{bar}`  **{idea.confidence}%**  ·  Grade **{idea.grade}**",
            inline=True,
        )

        if profile is not None:
            embed.add_field(
                name=f"💰 Trade in USD (${profile.stake_usd:.0f} stake)",
                value=ui.code_block(usd_breakdown(idea, profile)),
                inline=False,
            )

        embed.add_field(
            name="📋 One-Tap Copy",
            value=one_tap_copy_block(idea),
            inline=False,
        )

    if idea.confluences:
        embed.add_field(
            name=f"✅ Confluences ({len(idea.confluences)})",
            value="\n".join(f"• {c}" for c in idea.confluences[:8]),
            inline=False,
        )
    if idea.invalidations:
        embed.add_field(
            name="❌ Invalidation",
            value="\n".join(f"• {x}" for x in idea.invalidations),
            inline=False,
        )
    if idea.notes:
        embed.add_field(
            name="📝 Execution Notes",
            value="\n".join(f"• {n}" for n in idea.notes),
            inline=False,
        )

    embed.add_field(
        name="🧠 Pre-Entry Checklist",
        value="\n".join(f"☐ {q}" for q in COACH_QUESTIONS[:4]),
        inline=False,
    )
    return embed


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(
        name="analyze",
        description="Full multi-timeframe analysis with chart, bias, and trade plan.",
    )
    @app_commands.describe(
        symbol="Symbol — e.g. EURUSD, BTCUSDT, XAUUSD, ETH/USDT",
        entry_tf="Entry timeframe label (default: 1m)",
    )
    async def analyze(
        interaction: discord.Interaction,
        symbol: str,
        entry_tf: str = "1m",
    ) -> None:
        await interaction.response.defer(thinking=True)
        ms = get_market_service()
        try:
            inst, mtf = await ms.fetch_multi(symbol, ["4h", "1h", "15m", "5m", "1m"], limit=400)
        except Exception as exc:
            logger.warning(f"analyze fetch failed: {exc}")
            embed = ui.base_embed(
                f"⚠️ Could not load market data for `{symbol}`",
                color=ui.COLOR_DANGER,
                description=f"```\n{exc}\n```",
            )
            await interaction.followup.send(embed=embed)
            return

        profile = await get_profile_for_user(str(interaction.user.id))
        idea = build_trade_idea(
            inst.display,
            mtf,
            rr_min=max(2.0, profile.rr_min),
            rr_max=max(profile.rr_max, profile.rr_min + 1.0),
        )
        idea.timeframe_entry = entry_tf
        embed = _format_idea_embed(idea, inst.display, profile=profile)

        files: list[discord.File] = []
        chart_path = None
        try:
            df_for_chart = None
            for tf in ("15m", "5m", "1h", "4h", "1m"):
                df = mtf.get(tf)
                if df is not None and not df.empty:
                    df_for_chart = df
                    break
            if df_for_chart is None and mtf:
                df_for_chart = next(iter(mtf.values()))
            if df_for_chart is not None:
                chart_path = render_trade_chart(inst.display, "15m", df_for_chart, idea)
        except Exception as exc:
            logger.warning(f"chart render failed: {exc}")

        if chart_path is not None:
            files.append(discord.File(str(chart_path), filename=chart_path.name))
            embed.set_image(url=f"attachment://{chart_path.name}")
        else:
            embed.add_field(
                name="🖼️ Chart",
                value="Chart could not be rendered for this timeframe.",
                inline=False,
            )

        view = TradeIdeaView(idea) if idea.side != "none" else None
        await interaction.followup.send(embed=embed, files=files, view=view)

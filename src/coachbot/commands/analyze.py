"""/analyze command — multi-timeframe trade idea + chart."""

from __future__ import annotations

import discord
from discord import app_commands
from loguru import logger

from ..charts.render import render_trade_chart
from ..coach.lessons import COACH_QUESTIONS
from ..data.market_data import get_market_service
from ..strategy.engine import build_trade_idea


def _format_idea_embed(idea, inst_display: str) -> discord.Embed:
    color = 0x4CAF50 if idea.side == "long" else 0xEF5350 if idea.side == "short" else 0x9E9E9E
    title = f"{inst_display} — {idea.side.upper() if idea.side != 'none' else 'NO SETUP'}"
    embed = discord.Embed(title=title, color=color)
    embed.add_field(
        name="📈 الإطار العام",
        value="\n".join(
            f"• {b.timeframe}: **{b.label}** ({b.score:+.2f}) — {' / '.join(b.reasons[:2])}"
            for b in idea.biases
        )
        or "—",
        inline=False,
    )

    if idea.side != "none":
        embed.add_field(
            name="🎯 خطة الصفقة",
            value=(
                f"الدخول: `{idea.entry:.6g}`\n"
                f"وقف الخسارة: `{idea.stop_loss:.6g}`\n"
                f"TP1: `{idea.take_profit_1:.6g}` (1:{idea.rr_1:.2f})\n"
                f"TP2: `{idea.take_profit_2:.6g}` (1:{idea.rr_2:.2f})\n"
                f"TP3: `{idea.take_profit_3:.6g}` (1:{idea.rr_3:.2f})"
            ),
            inline=False,
        )

    if idea.confluences:
        embed.add_field(
            name="✅ التأكيدات", value="\n".join(f"• {c}" for c in idea.confluences[:6]), inline=False
        )
    if idea.invalidations:
        embed.add_field(name="❌ نقاط الإلغاء", value="\n".join(idea.invalidations), inline=False)
    if idea.notes:
        embed.add_field(name="📝 ملاحظات", value="\n".join(idea.notes), inline=False)

    embed.add_field(
        name="🧠 أسئلة المدرّب",
        value="\n".join(f"• {q}" for q in COACH_QUESTIONS[:3]),
        inline=False,
    )
    embed.set_footer(text=f"Confidence {idea.confidence}% | Entry TF: {idea.timeframe_entry}")
    return embed


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="analyze", description="تحليل متعدد الفريمات لزوج معيّن")
    @app_commands.describe(symbol="مثال: EURUSD، BTCUSDT، XAUUSD", entry_tf="فريم الدخول (1m افتراضي)")
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
            await interaction.followup.send(f"⚠️ تعذّر جلب بيانات {symbol}: `{exc}`")
            return

        idea = build_trade_idea(inst.display, mtf)
        idea.timeframe_entry = entry_tf
        embed = _format_idea_embed(idea, inst.display)

        chart_path = None
        try:
            df_for_chart = mtf.get("15m") or mtf.get("5m") or next(iter(mtf.values()))
            chart_path = render_trade_chart(inst.display, "15m", df_for_chart, idea)
        except Exception as exc:
            logger.warning(f"chart failed: {exc}")

        files = []
        if chart_path:
            files.append(discord.File(str(chart_path), filename=chart_path.name))
            embed.set_image(url=f"attachment://{chart_path.name}")

        await interaction.followup.send(embed=embed, files=files)

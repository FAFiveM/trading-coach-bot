"""Reusable Discord embed + interactive Copy view for trade ideas.

The view exposes one button per level (Entry / SL / TP1 / TP2 / TP3). Clicking
a button replies to the user ephemerally with a single tap-to-copy code block
containing only that level's price — the easiest possible way to copy on
mobile and desktop.
"""

from __future__ import annotations

import discord

from . import ui
from .profile import DEFAULT_PROFILE, TradeProfile
from .strategy.engine import TradeIdea


def _fmt_price_copy(p: float) -> str:
    """Format price for clean copy-paste — no thousand separators."""
    if p == 0:
        return "0"
    if abs(p) >= 1000:
        return f"{p:.4f}"
    if abs(p) >= 10:
        return f"{p:.4f}"
    if abs(p) >= 1:
        return f"{p:.5f}"
    return f"{p:.6f}"


def usd_breakdown(idea: TradeIdea, profile: TradeProfile = DEFAULT_PROFILE) -> str:
    """Pre-formatted dollar P/L line based on the user's stake profile."""
    if idea.side == "none":
        return "—"
    risk = profile.stake_usd
    return (
        f"Risk      −${risk:.0f}\n"
        f"TP1 hit   +${risk * idea.rr_1:.0f}   (1:{idea.rr_1:.2f})\n"
        f"TP2 hit   +${risk * idea.rr_2:.0f}   (1:{idea.rr_2:.2f})\n"
        f"TP3 hit   +${risk * idea.rr_3:.0f}   (1:{idea.rr_3:.2f})"
    )


def one_tap_copy_block(idea: TradeIdea) -> str:
    """Each level on its own line, in inline code, so a single tap copies it."""
    if idea.side == "none":
        return "—"
    lines = [
        f"Entry  →  `{_fmt_price_copy(idea.entry)}`",
        f"SL     →  `{_fmt_price_copy(idea.stop_loss)}`",
        f"TP1    →  `{_fmt_price_copy(idea.take_profit_1)}`",
        f"TP2    →  `{_fmt_price_copy(idea.take_profit_2)}`",
        f"TP3    →  `{_fmt_price_copy(idea.take_profit_3)}`",
    ]
    return "\n".join(lines)


class CopyLevelButton(discord.ui.Button):
    def __init__(self, label: str, value: float, style: discord.ButtonStyle):
        super().__init__(label=label, style=style)
        self.value = value

    async def callback(self, interaction: discord.Interaction) -> None:
        price = _fmt_price_copy(self.value)
        await interaction.response.send_message(
            f"📋 **{self.label}** — tap the value to copy:\n```\n{price}\n```",
            ephemeral=True,
        )


class TradeIdeaView(discord.ui.View):
    """Persistent-style view with one Copy button per level. timeout=None so it
    stays interactive until the bot restarts.
    """

    def __init__(self, idea: TradeIdea):
        super().__init__(timeout=None)
        if idea.side == "none":
            return
        self.add_item(CopyLevelButton("Entry", idea.entry, discord.ButtonStyle.primary))
        self.add_item(CopyLevelButton("SL", idea.stop_loss, discord.ButtonStyle.danger))
        self.add_item(CopyLevelButton("TP1", idea.take_profit_1, discord.ButtonStyle.success))
        self.add_item(CopyLevelButton("TP2", idea.take_profit_2, discord.ButtonStyle.success))
        self.add_item(CopyLevelButton("TP3", idea.take_profit_3, discord.ButtonStyle.success))


def build_signal_embed(
    idea: TradeIdea,
    profile: TradeProfile = DEFAULT_PROFILE,
    title_prefix: str = "⚡ A+ Auto-Signal",
    show_disclaimer: bool = True,
) -> discord.Embed:
    """Branded embed used for both /analyze and the auto-broadcast scanner."""
    title = f"{title_prefix} · {idea.symbol} · {ui.side_arrow(idea.side)}"
    color = ui.side_color(idea.side)
    embed = ui.base_embed(title, color=color)
    embed.description = (
        f"**Confidence:** {idea.confidence}%  ·  Grade **{idea.grade}**\n"
        f"`{ui.confidence_bar(idea.confidence)}`"
    )
    plan = (
        f"Entry  {ui.fmt_price(idea.entry)}\n"
        f"SL     {ui.fmt_price(idea.stop_loss)}\n"
        f"TP1    {ui.fmt_price(idea.take_profit_1)}   (1:{idea.rr_1:.2f})\n"
        f"TP2    {ui.fmt_price(idea.take_profit_2)}   (1:{idea.rr_2:.2f})\n"
        f"TP3    {ui.fmt_price(idea.take_profit_3)}   (1:{idea.rr_3:.2f})"
    )
    embed.add_field(name="📐 Trade Plan", value=ui.code_block(plan), inline=False)
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
            name=f"🧬 Confluences ({len(idea.confluences)})",
            value="\n".join(f"• {c}" for c in idea.confluences[:6]),
            inline=False,
        )
    if idea.invalidations:
        embed.add_field(
            name="🛑 Invalidation",
            value="\n".join(f"• {c}" for c in idea.invalidations[:3]),
            inline=False,
        )
    if show_disclaimer:
        embed.add_field(
            name="ℹ️ Reminder",
            value=(
                "Confidence reflects how many filters aligned — **not** a guaranteed win rate. "
                f"Size every entry so a stop-loss hit costs ~${profile.stake_usd:.0f}."
            ),
            inline=False,
        )
    return embed

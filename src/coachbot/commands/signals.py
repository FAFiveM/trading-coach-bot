"""Signals channel commands: opt a channel in/out for A+ auto-broadcast."""

from __future__ import annotations

import discord
from discord import app_commands
from sqlalchemy import delete, select

from .. import ui
from ..db.models import SignalsChannel
from ..db.session import get_session


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(
        name="set_signals_channel",
        description="Subscribe this channel to A+ auto-signals (>= confidence threshold).",
    )
    @app_commands.describe(
        min_confidence="Minimum confidence to broadcast (default 85).",
        mention_everyone="Ping @everyone on each signal (default true).",
    )
    async def set_signals(
        interaction: discord.Interaction,
        min_confidence: app_commands.Range[int, 60, 99] = 85,
        mention_everyone: bool = True,
    ) -> None:
        await interaction.response.defer(ephemeral=False, thinking=True)
        ch = interaction.channel
        if ch is None:
            await interaction.followup.send("❌ Channel not resolvable.")
            return
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        async with get_session() as s:
            existing = await s.get(SignalsChannel, str(ch.id))
            if existing:
                existing.min_confidence = int(min_confidence)
                existing.mention_everyone = 1 if mention_everyone else 0
                existing.guild_id = guild_id
            else:
                s.add(
                    SignalsChannel(
                        channel_id=str(ch.id),
                        guild_id=guild_id,
                        enabled_by=str(interaction.user.id),
                        mention_everyone=1 if mention_everyone else 0,
                        min_confidence=int(min_confidence),
                    )
                )
            await s.commit()
        embed = ui.base_embed(
            "🛰️ Signals Channel Linked",
            color=ui.COLOR_LONG,
            description=(
                f"This channel will now receive **A+ auto-signals** 24/7.\n\n"
                f"• Minimum confidence: **{int(min_confidence)}%**\n"
                f"• Mention @everyone: **{'yes' if mention_everyone else 'no'}**\n"
                f"• Hourly market briefings will also post here.\n\n"
                "Each signal is unique and deduped per symbol/side over a 4h window."
            ),
        )
        await interaction.followup.send(embed=embed)

    @tree.command(
        name="unset_signals_channel",
        description="Stop receiving A+ auto-signals in this channel.",
    )
    async def unset_signals(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False, thinking=True)
        ch = interaction.channel
        if ch is None:
            await interaction.followup.send("❌ Channel not resolvable.")
            return
        async with get_session() as s:
            await s.execute(delete(SignalsChannel).where(SignalsChannel.channel_id == str(ch.id)))
            await s.commit()
        embed = ui.base_embed(
            "🔇 Signals Channel Unlinked",
            color=ui.COLOR_NEUTRAL,
            description="This channel will no longer receive A+ auto-signals.",
        )
        await interaction.followup.send(embed=embed)

    @tree.command(
        name="signals_status",
        description="Show all channels in this guild that are subscribed to A+ signals.",
    )
    async def signals_status(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        async with get_session() as s:
            res = await s.execute(select(SignalsChannel).where(SignalsChannel.guild_id == gid))
            chans = list(res.scalars())
        if not chans:
            embed = ui.base_embed(
                "🛰️ Signal Subscriptions",
                color=ui.COLOR_NEUTRAL,
                description="No channels in this guild are subscribed yet. Use `/set_signals_channel` in the channel you want.",
            )
        else:
            lines = [
                f"• <#{c.channel_id}> — min **{c.min_confidence}%** "
                f"{'· @everyone' if c.mention_everyone else ''}"
                for c in chans
            ]
            embed = ui.base_embed(
                "🛰️ Signal Subscriptions",
                color=ui.COLOR_INFO,
                description="\n".join(lines),
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

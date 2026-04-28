"""Watchlist commands."""

from __future__ import annotations

import discord
from discord import app_commands
from sqlalchemy import delete, select

from .. import ui
from ..db.models import WatchlistItem
from ..db.session import get_session
from ..utils.symbols import parse_symbol


def register(tree: app_commands.CommandTree) -> None:
    group = app_commands.Group(name="watchlist", description="Manage your watchlist")

    @group.command(name="add", description="Add a symbol to your watchlist.")
    async def add(interaction: discord.Interaction, symbol: str) -> None:
        try:
            inst = parse_symbol(symbol)
        except ValueError as exc:
            await interaction.response.send_message(
                embed=ui.base_embed("⚠️ Invalid Symbol", color=ui.COLOR_DANGER, description=str(exc)),
                ephemeral=True,
            )
            return
        async with get_session() as s:
            existing = await s.execute(
                select(WatchlistItem).where(
                    WatchlistItem.user_id == str(interaction.user.id),
                    WatchlistItem.symbol == inst.display,
                )
            )
            if existing.scalar_one_or_none():
                await interaction.response.send_message(
                    embed=ui.base_embed(
                        "ℹ️ Already on Watchlist",
                        color=ui.COLOR_NEUTRAL,
                        description=f"`{inst.display}` is already on your list.",
                    ),
                    ephemeral=True,
                )
                return
            s.add(WatchlistItem(user_id=str(interaction.user.id), symbol=inst.display))
            await s.commit()
        embed = ui.base_embed(
            "✅ Added to Watchlist",
            color=ui.COLOR_LONG,
            description=f"**{inst.display}** is now on your watchlist.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="remove", description="Remove a symbol from your watchlist.")
    async def remove(interaction: discord.Interaction, symbol: str) -> None:
        async with get_session() as s:
            await s.execute(
                delete(WatchlistItem).where(
                    WatchlistItem.user_id == str(interaction.user.id),
                    WatchlistItem.symbol == symbol.upper(),
                )
            )
            await s.commit()
        embed = ui.base_embed(
            "🗑️ Removed",
            color=ui.COLOR_NEUTRAL,
            description=f"**{symbol.upper()}** removed from your watchlist.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="show", description="Show your watchlist.")
    async def show(interaction: discord.Interaction) -> None:
        async with get_session() as s:
            res = await s.execute(
                select(WatchlistItem).where(WatchlistItem.user_id == str(interaction.user.id))
            )
            items = list(res.scalars())
        if not items:
            embed = ui.base_embed(
                "📋 Watchlist",
                color=ui.COLOR_NEUTRAL,
                description="Empty. Use `/watchlist add SYMBOL` to add your first pair.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        text = "\n".join(f"• **{i.symbol}**" for i in items)
        embed = ui.base_embed(
            f"📋 Watchlist — {len(items)} symbols",
            color=ui.COLOR_INFO,
            description=text,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(group)

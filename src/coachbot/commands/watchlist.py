"""Watchlist commands."""

from __future__ import annotations

import discord
from discord import app_commands
from sqlalchemy import delete, select

from ..db.models import WatchlistItem
from ..db.session import get_session
from ..utils.symbols import parse_symbol


def register(tree: app_commands.CommandTree) -> None:
    group = app_commands.Group(name="watchlist", description="إدارة قائمة المتابعة")

    @group.command(name="add", description="أضف زوج لقائمة المتابعة")
    async def add(interaction: discord.Interaction, symbol: str) -> None:
        try:
            inst = parse_symbol(symbol)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        async with get_session() as s:
            existing = await s.execute(
                select(WatchlistItem).where(
                    WatchlistItem.user_id == str(interaction.user.id),
                    WatchlistItem.symbol == inst.display,
                )
            )
            if existing.scalar_one_or_none():
                await interaction.response.send_message(f"موجود مسبقاً: {inst.display}", ephemeral=True)
                return
            s.add(WatchlistItem(user_id=str(interaction.user.id), symbol=inst.display))
            await s.commit()
        await interaction.response.send_message(f"✅ أُضيف {inst.display}", ephemeral=True)

    @group.command(name="remove", description="احذف زوج من القائمة")
    async def remove(interaction: discord.Interaction, symbol: str) -> None:
        async with get_session() as s:
            await s.execute(
                delete(WatchlistItem).where(
                    WatchlistItem.user_id == str(interaction.user.id),
                    WatchlistItem.symbol == symbol.upper(),
                )
            )
            await s.commit()
        await interaction.response.send_message(f"🗑️ حُذف {symbol}", ephemeral=True)

    @group.command(name="show", description="عرض قائمتك")
    async def show(interaction: discord.Interaction) -> None:
        async with get_session() as s:
            res = await s.execute(
                select(WatchlistItem).where(WatchlistItem.user_id == str(interaction.user.id))
            )
            items = list(res.scalars())
        if not items:
            await interaction.response.send_message("القائمة فارغة. استخدم `/watchlist add`.", ephemeral=True)
            return
        text = "\n".join(f"• {i.symbol}" for i in items)
        await interaction.response.send_message(f"📋 قائمتك:\n{text}", ephemeral=True)

    tree.add_command(group)

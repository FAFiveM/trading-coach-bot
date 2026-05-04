"""Price alert commands."""

from __future__ import annotations

import discord
from discord import app_commands
from sqlalchemy import delete, select

from .. import ui
from ..data.market_data import get_market_service
from ..db.models import PriceAlert
from ..db.session import get_session
from ..utils.symbols import parse_symbol


def register(tree: app_commands.CommandTree) -> None:
    group = app_commands.Group(name="alert", description="Price alerts")

    @group.command(name="add", description="Set a price alert.")
    @app_commands.choices(
        direction=[
            app_commands.Choice(name="above", value="above"),
            app_commands.Choice(name="below", value="below"),
        ]
    )
    async def add(
        interaction: discord.Interaction,
        symbol: str,
        direction: app_commands.Choice[str],
        target: float,
        note: str = "",
    ) -> None:
        try:
            inst = parse_symbol(symbol)
        except ValueError as exc:
            await interaction.response.send_message(
                embed=ui.base_embed("⚠️ Invalid Symbol", color=ui.COLOR_DANGER, description=str(exc)),
                ephemeral=True,
            )
            return
        ms = get_market_service()
        try:
            _, current = await ms.fetch_last_price(symbol)
        except Exception as exc:
            await interaction.response.send_message(
                embed=ui.base_embed(
                    "⚠️ Could Not Verify Price",
                    color=ui.COLOR_DANGER,
                    description=f"```\n{exc}\n```",
                ),
                ephemeral=True,
            )
            return
        async with get_session() as s:
            s.add(
                PriceAlert(
                    user_id=str(interaction.user.id),
                    channel_id=str(interaction.channel_id),
                    symbol=inst.display,
                    direction=direction.value,
                    target=float(target),
                    note=note,
                )
            )
            await s.commit()
        embed = ui.base_embed(
            "🔔 Alert Armed",
            color=ui.COLOR_LONG,
            description=(
                f"**{inst.display}**  ·  {direction.value.upper()}  `{target}`\n"
                f"Current: `{ui.fmt_price(current)}`" + (f"\nNote: *{note}*" if note else "")
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="list", description="Show your active alerts.")
    async def list_(interaction: discord.Interaction) -> None:
        async with get_session() as s:
            res = await s.execute(
                select(PriceAlert).where(
                    PriceAlert.user_id == str(interaction.user.id),
                    PriceAlert.triggered == 0,
                )
            )
            alerts = list(res.scalars())
        if not alerts:
            embed = ui.base_embed(
                "🔔 Active Alerts",
                color=ui.COLOR_NEUTRAL,
                description="No active alerts. Use `/alert add` to arm one.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        text = "\n".join(
            f"`#{a.id}` **{a.symbol}** {a.direction} `{a.target}`" + (f" — {a.note}" if a.note else "")
            for a in alerts
        )
        embed = ui.base_embed(
            f"🔔 Active Alerts — {len(alerts)}",
            color=ui.COLOR_INFO,
            description=text,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="remove", description="Remove an alert by its ID.")
    async def remove(interaction: discord.Interaction, alert_id: int) -> None:
        async with get_session() as s:
            await s.execute(
                delete(PriceAlert).where(
                    PriceAlert.id == alert_id,
                    PriceAlert.user_id == str(interaction.user.id),
                )
            )
            await s.commit()
        embed = ui.base_embed(
            "🗑️ Alert Removed",
            color=ui.COLOR_NEUTRAL,
            description=f"Alert `#{alert_id}` is now disabled.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(group)

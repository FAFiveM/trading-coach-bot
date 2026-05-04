"""/profile commands — user trade profile (stake / SL / TP bands in USD)."""

from __future__ import annotations

import discord
from discord import app_commands

from .. import ui
from ..db.models import UserSettings
from ..db.session import get_session
from ..profile import get_profile_for_user


def register(tree: app_commands.CommandTree) -> None:
    profile_group = app_commands.Group(
        name="profile",
        description="Your dollar-based trade profile (stake, SL band, TP band).",
    )

    @profile_group.command(name="show", description="Show your current trade profile.")
    async def show(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        p = await get_profile_for_user(str(interaction.user.id))
        embed = ui.base_embed("💼 Your Trade Profile", color=ui.COLOR_INFO)
        embed.add_field(
            name="📊 Stake & Risk Bands",
            value=ui.code_block(
                f"Stake per trade   ${p.stake_usd:.0f}\n"
                f"Max acceptable SL ${p.sl_min_usd:.0f}–${p.sl_max_usd:.0f}\n"
                f"TP target band    ${p.tp_min_usd:.0f}–${p.tp_max_usd:.0f}"
            ),
            inline=False,
        )
        embed.add_field(
            name="📐 Implied R:R",
            value=ui.code_block(f"Min  1:{p.rr_min:.2f}\nMax  1:{p.rr_max:.2f}"),
            inline=False,
        )
        embed.add_field(
            name="ℹ️ How it's used",
            value=(
                "All A+ signals are sized so that hitting SL costs about your stake, "
                "and TP1 reaches at least the minimum reward in your band."
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @profile_group.command(
        name="set",
        description="Update your stake, SL band, or TP band (in USD).",
    )
    @app_commands.describe(
        stake="USD risked per trade (default 100)",
        sl_min="Lowest acceptable SL loss in USD (default 70)",
        sl_max="Highest acceptable SL loss in USD (default 100)",
        tp_min="Lowest acceptable TP reward in USD (default 300)",
        tp_max="Highest TP target in USD (default 600)",
    )
    async def set_profile(
        interaction: discord.Interaction,
        stake: app_commands.Range[float, 1, 100000] | None = None,
        sl_min: app_commands.Range[float, 1, 100000] | None = None,
        sl_max: app_commands.Range[float, 1, 100000] | None = None,
        tp_min: app_commands.Range[float, 1, 1000000] | None = None,
        tp_max: app_commands.Range[float, 1, 1000000] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with get_session() as s:
            u = await s.get(UserSettings, str(interaction.user.id))
            if u is None:
                u = UserSettings(user_id=str(interaction.user.id))
                s.add(u)
            if stake is not None:
                u.stake_usd = float(stake)
            if sl_min is not None:
                u.sl_min_usd = float(sl_min)
            if sl_max is not None:
                u.sl_max_usd = float(sl_max)
            if tp_min is not None:
                u.tp_min_usd = float(tp_min)
            if tp_max is not None:
                u.tp_max_usd = float(tp_max)
            await s.commit()
        p = await get_profile_for_user(str(interaction.user.id))
        embed = ui.base_embed(
            "💼 Profile Updated",
            color=ui.COLOR_LONG,
            description=(
                f"Stake **${p.stake_usd:.0f}**  ·  "
                f"SL **${p.sl_min_usd:.0f}–${p.sl_max_usd:.0f}**  ·  "
                f"TP **${p.tp_min_usd:.0f}–${p.tp_max_usd:.0f}**\n"
                f"Implied R:R **1:{p.rr_min:.2f}** to **1:{p.rr_max:.2f}**"
            ),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    tree.add_command(profile_group)

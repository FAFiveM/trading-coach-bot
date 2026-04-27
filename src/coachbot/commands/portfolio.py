"""Portfolio + journal commands."""

from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands
from sqlalchemy import select

from ..data.market_data import get_market_service
from ..db.models import JournalEntry, Trade
from ..db.session import get_session


def register(tree: app_commands.CommandTree) -> None:
    p_group = app_commands.Group(name="portfolio", description="محفظتك")
    j_group = app_commands.Group(name="journal", description="جورنال التداول")

    @p_group.command(name="open", description="افتح صفقة جديدة")
    @app_commands.choices(
        side=[
            app_commands.Choice(name="long", value="long"),
            app_commands.Choice(name="short", value="short"),
        ]
    )
    async def open_trade(
        interaction: discord.Interaction,
        symbol: str,
        side: app_commands.Choice[str],
        entry: float,
        stop_loss: float,
        take_profit: float,
        size: float = 1.0,
    ) -> None:
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr = reward / risk if risk > 0 else 0.0
        async with get_session() as s:
            t = Trade(
                user_id=str(interaction.user.id),
                symbol=symbol.upper(),
                side=side.value,
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size=size,
                rr=rr,
            )
            s.add(t)
            await s.commit()
            await s.refresh(t)
        await interaction.response.send_message(
            f"📒 صفقة #{t.id} مفتوحة: {symbol.upper()} {side.value.upper()} @ {entry} | SL {stop_loss} | TP {take_profit} | R:R 1:{rr:.2f}",
            ephemeral=True,
        )

    @p_group.command(name="close", description="أغلق صفقة برقمها")
    async def close_trade(interaction: discord.Interaction, trade_id: int, exit_price: float) -> None:
        async with get_session() as s:
            res = await s.execute(
                select(Trade).where(Trade.id == trade_id, Trade.user_id == str(interaction.user.id))
            )
            t = res.scalar_one_or_none()
            if not t:
                await interaction.response.send_message("الصفقة غير موجودة.", ephemeral=True)
                return
            if t.status == "closed":
                await interaction.response.send_message("مغلقة مسبقاً.", ephemeral=True)
                return
            if t.side == "long":
                pnl = (exit_price - t.entry) * t.size
                r_mult = (exit_price - t.entry) / max(abs(t.entry - t.stop_loss), 1e-9)
            else:
                pnl = (t.entry - exit_price) * t.size
                r_mult = (t.entry - exit_price) / max(abs(t.stop_loss - t.entry), 1e-9)
            t.exit_price = exit_price
            t.pnl = pnl
            t.rr = r_mult
            t.status = "closed"
            t.closed_at = datetime.utcnow()
            await s.commit()
        await interaction.response.send_message(
            f"✅ #{trade_id} أُغلقت @ {exit_price} | PnL {pnl:+.4f} | {r_mult:+.2f}R",
            ephemeral=True,
        )

    @p_group.command(name="show", description="ملخص محفظتك")
    async def show(interaction: discord.Interaction) -> None:
        async with get_session() as s:
            res = await s.execute(select(Trade).where(Trade.user_id == str(interaction.user.id)))
            trades = list(res.scalars())
        if not trades:
            await interaction.response.send_message("لا توجد صفقات بعد.", ephemeral=True)
            return
        closed = [t for t in trades if t.status == "closed"]
        wins = [t for t in closed if (t.pnl or 0) > 0]
        wr = (len(wins) / len(closed) * 100) if closed else 0.0
        total_pnl = sum(t.pnl or 0 for t in closed)
        total_r = sum(t.rr or 0 for t in closed)
        ms = get_market_service()
        open_lines = []
        for t in trades:
            if t.status != "open":
                continue
            try:
                _, p = await ms.fetch_last_price(t.symbol)
                if t.side == "long":
                    rr_now = (p - t.entry) / max(abs(t.entry - t.stop_loss), 1e-9)
                else:
                    rr_now = (t.entry - p) / max(abs(t.stop_loss - t.entry), 1e-9)
                open_lines.append(f"• #{t.id} {t.symbol} {t.side} @ {t.entry} → {p:.6g} ({rr_now:+.2f}R)")
            except Exception:
                open_lines.append(f"• #{t.id} {t.symbol} {t.side} @ {t.entry}")

        embed = discord.Embed(title="💼 محفظتك", color=0x29B6F6)
        embed.add_field(
            name="إجماليات",
            value=(
                f"الصفقات: {len(trades)} (مفتوحة {len(trades) - len(closed)})\n"
                f"نسبة الفوز: {wr:.1f}% | إجمالي PnL: {total_pnl:+.4f} | إجمالي R: {total_r:+.2f}"
            ),
            inline=False,
        )
        if open_lines:
            embed.add_field(name="🟢 الصفقات المفتوحة", value="\n".join(open_lines)[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @j_group.command(name="add", description="أضف ملاحظة جورنال")
    async def jadd(interaction: discord.Interaction, text: str, trade_id: int = 0) -> None:
        async with get_session() as s:
            entry = JournalEntry(
                user_id=str(interaction.user.id),
                trade_id=trade_id or None,
                text=text,
            )
            s.add(entry)
            await s.commit()
        await interaction.response.send_message("📝 سُجّل.", ephemeral=True)

    @j_group.command(name="show", description="آخر 10 ملاحظات")
    async def jshow(interaction: discord.Interaction) -> None:
        async with get_session() as s:
            res = await s.execute(
                select(JournalEntry)
                .where(JournalEntry.user_id == str(interaction.user.id))
                .order_by(JournalEntry.created_at.desc())
                .limit(10)
            )
            items = list(res.scalars())
        if not items:
            await interaction.response.send_message("الجورنال فاضي.", ephemeral=True)
            return
        text = "\n\n".join(
            f"`{i.created_at:%Y-%m-%d %H:%M}` {'#' + str(i.trade_id) + ' — ' if i.trade_id else ''}{i.text}"
            for i in items
        )
        await interaction.response.send_message(text[:1990], ephemeral=True)

    tree.add_command(p_group)
    tree.add_command(j_group)

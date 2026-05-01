"""Discord bot entry point."""

from __future__ import annotations

import asyncio
import sys

import discord
from discord import app_commands
from loguru import logger

from .alerts.scheduler import CoachScheduler
from .commands import alerts as alert_cmds
from .commands import analyze as analyze_cmds
from .commands import daily as daily_cmds
from .commands import info as info_cmds
from .commands import portfolio as portfolio_cmds
from .commands import signals as signals_cmds
from .commands import watchlist as watchlist_cmds
from .config import settings
from .data.market_data import get_market_service
from .db.session import init_db


class CoachBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.scheduler: CoachScheduler | None = None

    async def setup_hook(self) -> None:
        await init_db()

        analyze_cmds.register(self.tree)
        daily_cmds.register(self.tree)
        watchlist_cmds.register(self.tree)
        alert_cmds.register(self.tree)
        portfolio_cmds.register(self.tree)
        info_cmds.register(self.tree)
        signals_cmds.register(self.tree)

        if settings.coach_guild_id:
            guild = discord.Object(id=settings.coach_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"synced commands to guild {settings.coach_guild_id}")
        else:
            await self.tree.sync()
            logger.info("synced global commands (may take up to 1h to propagate)")

        self.scheduler = CoachScheduler(self)
        self.scheduler.start()

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info(f"logged in as {self.user} (id={self.user.id})")
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name="khadooojjjjiFX"),
        )

    async def close(self) -> None:
        if self.scheduler:
            self.scheduler.shutdown()
        await get_market_service().close()
        await super().close()


def _configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)


def main() -> None:
    _configure_logging()
    if not settings.discord_bot_token:
        logger.error("DISCORD_BOT_TOKEN is missing. Set it in .env or environment.")
        sys.exit(2)
    bot = CoachBot()
    try:
        asyncio.run(bot.start(settings.discord_bot_token))
    except KeyboardInterrupt:
        logger.info("shutting down")


if __name__ == "__main__":
    main()

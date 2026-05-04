"""Async DB session helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from .models import Base

_engine = create_async_engine(settings.coach_db_url, future=True, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


# Lightweight column migrations for SQLite — keyed by table name, value is a
# list of (column_name, "ALTER TABLE ... ADD COLUMN ...") tuples.
_LIGHTWEIGHT_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "user_settings": [
        ("stake_usd", "ALTER TABLE user_settings ADD COLUMN stake_usd FLOAT DEFAULT 100.0"),
        ("sl_min_usd", "ALTER TABLE user_settings ADD COLUMN sl_min_usd FLOAT DEFAULT 70.0"),
        ("sl_max_usd", "ALTER TABLE user_settings ADD COLUMN sl_max_usd FLOAT DEFAULT 100.0"),
        ("tp_min_usd", "ALTER TABLE user_settings ADD COLUMN tp_min_usd FLOAT DEFAULT 300.0"),
        ("tp_max_usd", "ALTER TABLE user_settings ADD COLUMN tp_max_usd FLOAT DEFAULT 600.0"),
    ],
}


async def _apply_lightweight_migrations() -> None:
    async with _engine.begin() as conn:
        for table, cols in _LIGHTWEIGHT_MIGRATIONS.items():
            try:
                res = await conn.execute(text(f"PRAGMA table_info({table})"))
                rows = res.fetchall()
            except Exception as exc:
                logger.debug(f"PRAGMA table_info({table}) failed: {exc}")
                continue
            existing = {r[1] for r in rows}
            for col_name, ddl in cols:
                if col_name in existing:
                    continue
                try:
                    await conn.execute(text(ddl))
                    logger.info(f"migrated: added {table}.{col_name}")
                except Exception as exc:
                    logger.warning(f"migration failed {table}.{col_name}: {exc}")


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _apply_lightweight_migrations()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with _session_factory() as session:
        yield session

"""Shared visual helpers for Discord embeds — branded, dense, English-only."""

from __future__ import annotations

from datetime import UTC, datetime

import discord

BRAND_NAME = "khadooojjjjiFX"
BRAND_TAG = f"{BRAND_NAME} • Trading Coach"

COLOR_LONG = 0x16C784
COLOR_SHORT = 0xEA3943
COLOR_NEUTRAL = 0x6E7681
COLOR_INFO = 0x4DA3FF
COLOR_WARN = 0xF7B500
COLOR_DANGER = 0xEA3943
COLOR_PURPLE = 0x9B5DE5
COLOR_CYAN = 0x00BBF9


def side_color(side: str) -> int:
    s = side.lower()
    if s == "long":
        return COLOR_LONG
    if s == "short":
        return COLOR_SHORT
    return COLOR_NEUTRAL


def side_arrow(side: str) -> str:
    s = side.lower()
    if s == "long":
        return "🟢 LONG"
    if s == "short":
        return "🔴 SHORT"
    return "⚪ NO SETUP"


def confidence_bar(pct: int, slots: int = 12) -> str:
    """Render a unicode progress bar for a 0-100 confidence value."""
    pct = max(0, min(100, int(pct)))
    filled = round(pct / 100 * slots)
    return "▰" * filled + "▱" * (slots - filled)


def sentiment_emoji(score: float) -> str:
    if score > 0.15:
        return "🟢"
    if score < -0.15:
        return "🔴"
    return "⚪"


def base_embed(
    title: str,
    color: int = COLOR_INFO,
    description: str | None = None,
) -> discord.Embed:
    """Return an embed with branded title formatting and footer/timestamp set."""
    embed = discord.Embed(
        title=title,
        color=color,
        description=description,
        timestamp=datetime.now(UTC),
    )
    embed.set_footer(text=BRAND_TAG)
    return embed


def divider() -> str:
    return "━━━━━━━━━━━━━━━━━━━━━━━━"


def fmt_price(p: float) -> str:
    if p == 0:
        return "—"
    if abs(p) >= 1000:
        return f"{p:,.2f}"
    return f"{p:.6g}"


def fmt_pct(p: float) -> str:
    sign = "+" if p > 0 else ""
    return f"{sign}{p * 100:.2f}%"


def code_block(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```"

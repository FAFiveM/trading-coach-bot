"""Top trader & news calendar feeds via Nitter (Twitter mirror) + ForexFactory RSS."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser
from loguru import logger

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

DEFAULT_TRADERS = [
    "CryptoCapo_",
    "PeterLBrandt",
    "AltcoinPsycho",
    "VentureCoinist",
    "ForexLive",
]

CALENDAR_RSS = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"


@dataclass
class TraderPost:
    handle: str
    title: str
    link: str
    published: str


@dataclass
class CalendarEvent:
    title: str
    country: str
    impact: str  # high|medium|low
    when: datetime


async def fetch_trader_feed(handles: list[str] | None = None, limit: int = 10) -> list[TraderPost]:
    handles = handles or DEFAULT_TRADERS
    loop = asyncio.get_running_loop()

    async def _try(handle: str) -> list[TraderPost]:
        for base in NITTER_INSTANCES:
            url = f"{base}/{handle}/rss"
            try:
                feed = await loop.run_in_executor(None, feedparser.parse, url)
                if feed.entries:
                    return [
                        TraderPost(
                            handle=handle,
                            title=getattr(e, "title", ""),
                            link=getattr(e, "link", ""),
                            published=getattr(e, "published", ""),
                        )
                        for e in feed.entries[:3]
                    ]
            except Exception as exc:
                logger.debug(f"nitter {base} {handle} failed: {exc}")
        return []

    results = await asyncio.gather(*[_try(h) for h in handles])
    out: list[TraderPost] = []
    for r in results:
        out.extend(r)
    return out[:limit]


async def fetch_calendar(impact_filter: str = "high") -> list[CalendarEvent]:
    loop = asyncio.get_running_loop()
    try:
        feed = await loop.run_in_executor(None, feedparser.parse, CALENDAR_RSS)
    except Exception as exc:
        logger.warning(f"calendar fetch failed: {exc}")
        return []
    out: list[CalendarEvent] = []
    for e in feed.entries:
        title = getattr(e, "title", "")
        country = getattr(e, "country", "") if hasattr(e, "country") else ""
        impact = (getattr(e, "impact", "") or "").lower()
        if impact_filter and impact != impact_filter:
            if impact_filter == "high" and impact not in {"high"}:
                continue
        try:
            when = datetime(*e.published_parsed[:6], tzinfo=UTC)
        except Exception:
            when = datetime.now(UTC)
        out.append(CalendarEvent(title=title, country=country, impact=impact or "low", when=when))
    return out


async def fetch_cot_summary() -> str:
    """Summarize CFTC COT report via faireconomy/forexfactory text feed."""
    url = "https://www.cftc.gov/dea/futures/deafincomelf.htm"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            text = r.text
    except Exception as exc:
        logger.warning(f"COT fetch failed: {exc}")
        return ""

    snippet = text[:2000].replace("\n\n", "\n")
    return snippet

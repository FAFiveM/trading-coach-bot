"""News + sentiment via free RSS feeds and CryptoPanic public API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import feedparser
import httpx
from loguru import logger

from ..config import settings

POSITIVE_WORDS = {
    "surge",
    "soar",
    "rally",
    "bull",
    "gain",
    "record",
    "breakout",
    "support",
    "upgrade",
    "optimistic",
    "approve",
    "approved",
    "buy",
    "accumulate",
    "rise",
}
NEGATIVE_WORDS = {
    "plunge",
    "crash",
    "bear",
    "loss",
    "drop",
    "decline",
    "ban",
    "hack",
    "exploit",
    "downgrade",
    "fud",
    "sell-off",
    "fall",
    "fell",
    "warning",
    "risk",
    "panic",
}

CRYPTO_RSS = [
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]
FOREX_RSS = [
    "https://www.forexlive.com/feed/",
    "https://www.fxstreet.com/rss/news",
]


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    sentiment: int  # -1, 0, 1


def _classify(text: str) -> int:
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


async def _fetch_rss(url: str) -> list[NewsItem]:
    loop = asyncio.get_running_loop()
    try:
        feed = await loop.run_in_executor(None, feedparser.parse, url)
    except Exception as exc:
        logger.warning(f"RSS failed {url}: {exc}")
        return []
    items: list[NewsItem] = []
    for entry in feed.entries[:8]:
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        items.append(NewsItem(title=title, link=link, source=url, sentiment=_classify(title)))
    return items


async def fetch_news(market: str = "all", limit: int = 12) -> list[NewsItem]:
    feeds = []
    if market in ("all", "crypto"):
        feeds.extend(CRYPTO_RSS)
    if market in ("all", "forex"):
        feeds.extend(FOREX_RSS)
    results = await asyncio.gather(*[_fetch_rss(u) for u in feeds], return_exceptions=True)
    out: list[NewsItem] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    return out[:limit]


async def fetch_cryptopanic(currency: str | None = None, limit: int = 10) -> list[NewsItem]:
    if not settings.cryptopanic_api_key:
        return []
    params = {
        "auth_token": settings.cryptopanic_api_key,
        "kind": "news",
        "public": "true",
    }
    if currency:
        params["currencies"] = currency
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://cryptopanic.com/api/v1/posts/", params=params)
            r.raise_for_status()
            payload = r.json()
    except Exception as exc:
        logger.warning(f"CryptoPanic failed: {exc}")
        return []
    items: list[NewsItem] = []
    for entry in payload.get("results", [])[:limit]:
        title = entry.get("title", "")
        link = entry.get("url", "")
        votes = entry.get("votes") or {}
        s = 0
        if votes.get("positive", 0) > votes.get("negative", 0):
            s = 1
        elif votes.get("negative", 0) > votes.get("positive", 0):
            s = -1
        if s == 0:
            s = _classify(title)
        items.append(NewsItem(title=title, link=link, source="cryptopanic", sentiment=s))
    return items


def aggregate_sentiment(items: list[NewsItem]) -> tuple[str, float]:
    if not items:
        return "neutral", 0.0
    score = sum(i.sentiment for i in items) / len(items)
    if score > 0.15:
        label = "Bullish"
    elif score < -0.15:
        label = "Bearish"
    else:
        label = "Neutral"
    return label, round(score, 2)

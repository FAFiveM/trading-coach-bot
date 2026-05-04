"""On-chain analytics: funding rates, OI, long/short ratio, ETH whale txs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from loguru import logger

from ..config import settings


@dataclass
class FundingInfo:
    symbol: str
    funding_rate: float
    next_funding_time: int
    open_interest: float | None = None
    long_short_ratio: float | None = None


async def fetch_funding(base: str) -> FundingInfo | None:
    sym = f"{base.upper()}USDT"
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"symbol": sym})
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning(f"funding fetch failed {sym}: {exc}")
        return None

    info = FundingInfo(
        symbol=sym,
        funding_rate=float(data.get("lastFundingRate", 0.0)),
        next_funding_time=int(data.get("nextFundingTime", 0)),
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            oi = await client.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": sym})
            if oi.status_code == 200:
                info.open_interest = float(oi.json().get("openInterest", 0.0))
            ls = await client.get(
                "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                params={"symbol": sym, "period": "1h", "limit": 1},
            )
            if ls.status_code == 200 and ls.json():
                info.long_short_ratio = float(ls.json()[0]["longShortRatio"])
    except Exception as exc:
        logger.debug(f"OI/LS fetch failed: {exc}")

    return info


@dataclass
class WhaleTransfer:
    hash: str
    from_addr: str
    to_addr: str
    value_eth: float
    timestamp: int


async def fetch_eth_whales(min_value_eth: float = 500.0, limit: int = 5) -> list[WhaleTransfer]:
    """Pulls the latest large ETH transfers via Etherscan if API key is set."""
    if not settings.etherscan_api_key:
        return []
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "txlist",
        "address": "0x00000000219ab540356cBB839Cbe05303d7705Fa",  # ETH2 deposit contract — proxy for big movers
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 25,
        "sort": "desc",
        "apikey": settings.etherscan_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
    except Exception as exc:
        logger.warning(f"etherscan failed: {exc}")
        return []
    out: list[WhaleTransfer] = []
    for tx in payload.get("result", []):
        try:
            value = int(tx["value"]) / 1e18
        except (KeyError, ValueError):
            continue
        if value < min_value_eth:
            continue
        out.append(
            WhaleTransfer(
                hash=tx["hash"],
                from_addr=tx["from"],
                to_addr=tx["to"],
                value_eth=value,
                timestamp=int(tx["timeStamp"]),
            )
        )
        if len(out) >= limit:
            break
    return out


async def fetch_btc_metrics() -> dict[str, float]:
    """Free public metrics from Blockchain.info: hashrate, mempool size."""
    out: dict[str, float] = {}
    endpoints = {
        "hashrate_ehs": "https://api.blockchain.info/charts/hash-rate?timespan=2days&format=json",
        "mempool_count": "https://api.blockchain.info/q/unconfirmedcount",
    }
    async with httpx.AsyncClient(timeout=10) as client:

        async def _go(key: str, url: str) -> None:
            try:
                r = await client.get(url)
                r.raise_for_status()
                if key == "mempool_count":
                    out[key] = float(r.text)
                else:
                    values = r.json().get("values", [])
                    if values:
                        out[key] = float(values[-1].get("y", 0))
            except Exception as exc:
                logger.debug(f"btc metric {key} failed: {exc}")

        await asyncio.gather(*[_go(k, u) for k, u in endpoints.items()])
    return out

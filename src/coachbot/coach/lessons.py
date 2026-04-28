"""Daily trading lessons and coach prompts."""

from __future__ import annotations

import random

LESSONS: list[tuple[str, str]] = [
    (
        "Risk First",
        "Never risk more than 1% of your account on a single idea. Capital is the only "
        "ammo you have — protect it before chasing returns.",
    ),
    (
        "Top-Down Always",
        "Start every analysis on 4H or Daily to fix the bias, then drop to 15m for the "
        "setup and 1m for execution. Trading without HTF context is gambling.",
    ),
    (
        "Liquidity Is Fuel",
        "Markets hunt liquidity. Equal highs/lows, prior swing extremes and round numbers "
        "are magnets. Wait for the sweep, then look for displacement back into range.",
    ),
    (
        "Consistency > Accuracy",
        "A simple system you actually follow beats a brilliant one you abandon at the "
        "first loss. Define your rules, journal them, and execute mechanically.",
    ),
    (
        "Kill Revenge Trades",
        "Never re-enter immediately after a loss to 'get it back'. Stand up, breathe, "
        "review the journal, and only return when the chart — not your emotions — calls.",
    ),
    (
        "R:R Is Edge",
        "Aim for 1:2 minimum. With a 40% hit rate at 1:3 you are profitable long-term. "
        "Where R:R is poor, the trade is poor — even if the setup looks 'pretty'.",
    ),
    (
        "Confluence Is King",
        "Don't enter on a single signal. Stack at least three: HTF bias + liquidity event + "
        "Order Block / FVG + structure shift. Three or more, or no trade.",
    ),
    (
        "Respect News Volatility",
        "Avoid new entries 30 minutes before NFP / FOMC / CPI. Spreads widen, stops get "
        "hunted, and your edge collapses inside the spike. Sit out, then reassess.",
    ),
    (
        "Journal Religiously",
        "Log every trade: thesis, emotion, screenshot, outcome. Weekly review of your own "
        "tape will improve you faster than any course.",
    ),
    (
        "Patience Pays",
        "Not every day is a trading day. Sometimes the best trade is the one you didn't "
        "take. The market always comes back.",
    ),
    (
        "Trade the Plan",
        "Decide entry, stop and targets BEFORE the candle closes. Once in, you only manage. "
        "Discretion mid-trade is where most accounts die.",
    ),
    (
        "Volume Confirms",
        "Breakouts without expanding volume are traps. Real moves leave volume footprints; "
        "fake moves don't. Read the tape, not just the candle.",
    ),
]


def random_lesson() -> tuple[str, str]:
    return random.choice(LESSONS)


COACH_QUESTIONS = [
    "Does the higher-timeframe bias align with this trade?",
    "What is the precise invalidation level for this idea?",
    "Is the reward-to-risk at least 1:2 — and ideally 1:3+?",
    "Is your position size such that a full SL is ≤1% of equity?",
    "Are there any high-impact events within the next hour?",
    "What is your emotional state right now: calm, fear, greed, revenge?",
    "Have you logged the thesis before clicking buy/sell?",
    "What would make you exit early — apart from SL/TP being hit?",
]

"""
KnockOutIQ — The Odds API Client
DraftKings, FanDuel, BetMGM moneylines and totals for boxing.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from config import ODDS_API_BASE_URL, ODDS_API_KEY

log = logging.getLogger(__name__)

_TIMEOUT = 15
_SPORT = "boxing_boxing"


def _get(endpoint: str, params: dict | None = None) -> Any:
    url = f"{ODDS_API_BASE_URL}{endpoint}"
    params = params or {}
    params["apiKey"] = ODDS_API_KEY
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    remaining = resp.headers.get("x-requests-remaining")
    used = resp.headers.get("x-requests-used")
    cost = resp.headers.get("x-requests-last")
    if cost or used:
        log.debug(
            "OddsAPI quota — cost: %s | used: %s | remaining: %s",
            cost, used, remaining,
        )
    return resp.json()


# ─── Endpoints ────────────────────────────────────────────────────────────────

def get_events(odds_format: str = "american") -> list[dict]:
    """
    Upcoming and live boxing events (event id, fighters, commence time).
    Free — does NOT count against the usage quota.
    Use this to discover fight IDs before calling get_event_odds().
    """
    return _get(
        f"/sports/{_SPORT}/events",
        params={"oddsFormat": odds_format},
    )


def get_current_odds(
    regions: str = "us,uk,eu",
    bookmakers: str | None = None,
    markets: str = "h2h,totals",
    odds_format: str = "american",
) -> list[dict]:
    """
    Current boxing odds from bookmakers across US, UK and EU regions.
    Quota cost: [markets] x [regions].  Default = 2 markets x 3 regions = 6.
    Pass bookmakers= to restrict to specific books instead of regions.
    """
    params: dict[str, str] = {
        "markets": markets,
        "oddsFormat": odds_format,
    }
    if bookmakers:
        params["bookmakers"] = bookmakers
    else:
        params["regions"] = regions
    return _get(f"/sports/{_SPORT}/odds", params=params)


def get_event_odds(
    event_id: str,
    regions: str = "us,uk,eu",
    markets: str = "h2h,totals",
    odds_format: str = "american",
) -> dict:
    """
    All bookmaker odds for a single fight.
    Use when you have a specific event_id from get_events().
    Quota cost: [unique markets returned] x [regions].
    """
    return _get(
        f"/sports/{_SPORT}/events/{event_id}/odds",
        params={
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
        },
    )


def get_historical_odds(
    date_str: str,
    regions: str = "us",
    markets: str = "h2h",
    odds_format: str = "american",
) -> list[dict]:
    """
    Historical odds snapshot at a specific ISO-8601 datetime.
    Available from May 2023. Requires paid API tier.
    Quota cost: 10 x [markets] x [regions].
    date_str example: '2024-06-01T00:00:00Z'
    """
    result = _get(
        f"/historical/sports/{_SPORT}/odds",
        params={
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "date": date_str,
        },
    )
    # Response is wrapped: {"timestamp": ..., "data": [...]}
    if isinstance(result, dict):
        return result.get("data", [])
    return result


def get_scores(days_from: int = 3) -> list[dict]:
    """
    Recent boxing results (completed fights up to 3 days back).
    Quota cost: 2 when daysFrom is set, 1 otherwise.
    """
    return _get(
        f"/sports/{_SPORT}/scores",
        params={"daysFrom": days_from},
    )


def get_participants() -> list[dict]:
    """
    Canonical boxer names and IDs as recognised by bookmakers.
    Useful for fuzzy name-matching against BoxRec records.
    Quota cost: 1.
    """
    return _get(f"/sports/{_SPORT}/participants")


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal."""
    if american > 0:
        return (american / 100) + 1
    return (100 / abs(american)) + 1

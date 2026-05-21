"""
KnockOutIQ — TheSportsDB Client (free event metadata)
"""

from __future__ import annotations

import requests

from config import SPORTS_DB_BASE_URL

_TIMEOUT = 10


def _get(endpoint: str, params: dict | None = None) -> dict:
    url = f"{SPORTS_DB_BASE_URL}{endpoint}"
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def search_events(query: str) -> list[dict]:
    result = _get("/searchevents.php", params={"e": query})
    return result.get("event") or []


def get_events_by_league(league_id: str = "4443") -> list[dict]:
    """Boxing league events. Default 4443 = boxing."""
    result = _get("/eventsnextleague.php", params={"id": league_id})
    return result.get("events") or []


def get_past_events(league_id: str = "4443") -> list[dict]:
    result = _get("/eventspastleague.php", params={"id": league_id})
    return result.get("events") or []

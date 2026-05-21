"""
KnockOutIQ — OddsPapi Client (Pinnacle reference lines)
Sharp book lines used to detect value against DraftKings.
"""

from __future__ import annotations

from typing import Any

import requests

from config import ODDSPAPI_BASE_URL, ODDSPAPI_KEY

_TIMEOUT = 15


def _get(endpoint: str, params: dict | None = None) -> Any:
    url = f"{ODDSPAPI_BASE_URL}{endpoint}"
    params = params or {}
    params["apiKey"] = ODDSPAPI_KEY
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ─── Endpoints ────────────────────────────────────────────────────────────────

def get_fixtures(sport: str = "boxing") -> list[dict]:
    """Upcoming boxing fixtures."""
    result = _get("/fixtures", params={"sport": sport})
    if isinstance(result, list):
        return result
    return result.get("data", [])


def get_odds_for_fixture(fixture_id: str | int) -> dict:
    """All bookmaker odds for a single fixture including Pinnacle."""
    return _get("/odds", params={"fixtureId": fixture_id})


def get_pinnacle_line(fixture_id: str | int) -> dict | None:
    """Return Pinnacle's odds for a fixture, or None if unavailable."""
    odds = get_odds_for_fixture(fixture_id)
    bk = odds.get("bookmakerOdds", {})
    return bk.get("pinnacle") or bk.get("Pinnacle")


def get_dk_line(fixture_id: str | int) -> dict | None:
    """Return DraftKings odds for a fixture."""
    odds = get_odds_for_fixture(fixture_id)
    bk = odds.get("bookmakerOdds", {})
    return bk.get("draftkings") or bk.get("DraftKings")

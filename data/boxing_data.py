"""
KnockOutIQ — boxing-data.com RapidAPI Client
Fighter profiles, fight history, rankings, schedules, and CompuBox stats.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from config import BOXING_DATA_BASE_URL, BOXING_DATA_HOST, RAPID_API_KEY

_HEADERS = {
    "X-RapidAPI-Key": RAPID_API_KEY,
    "X-RapidAPI-Host": BOXING_DATA_HOST,
}

_TIMEOUT = 15
_RETRY_DELAYS = [1, 2, 4]


def _get(endpoint: str, params: dict | None = None) -> Any:
    """GET with retry on 429/5xx."""
    url = f"{BOXING_DATA_BASE_URL}{endpoint}"
    for attempt, delay in enumerate(_RETRY_DELAYS + [None], start=1):
        try:
            resp = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT)
            if resp.status_code == 429 and delay is not None:
                time.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            if delay is None:
                raise
            time.sleep(delay)
    return None


# ─── Endpoints ────────────────────────────────────────────────────────────────

def get_fighter(fighter_id: str | int) -> dict:
    """Full fighter profile including career stats."""
    return _get(f"/fighters/{fighter_id}") or {}


def search_fighters(name: str) -> list[dict]:
    """Search fighters by name."""
    result = _get("/fighters/search/", params={"name": name})
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("data", result.get("results", []))
    return []


def get_fight_schedule(limit: int = 50) -> list[dict]:
    """Upcoming high-profile bouts."""
    result = _get("/fights/schedule/", params={"limit": limit})
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("data", result.get("results", []))
    return []


def get_fight(fight_id: str | int) -> dict:
    """Single fight details."""
    return _get(f"/fights/{fight_id}") or {}


def get_fight_stats(fight_id: str | int) -> dict:
    """CompuBox round-by-round stats for a fight."""
    return _get(f"/fights/{fight_id}/stats/") or {}


def get_title_holders() -> list[dict]:
    """Current title holders by division."""
    result = _get("/titles/")
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("data", [])
    return []


def get_rankings(weight_class: str | None = None) -> list[dict]:
    """Fighter rankings, optionally filtered by weight class."""
    params = {}
    if weight_class:
        params["weight_class"] = weight_class
    result = _get("/rankings/", params=params or None)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("data", [])
    return []


def get_historical_fights(
    year: int | None = None, page: int = 1, limit: int = 100
) -> list[dict]:
    """Historical finished fights (v1 API).  On the free tier, year is ignored."""
    params: dict = {"status": "FINISHED", "page": page, "limit": limit}
    if year is not None:
        params["year"] = year
    result = _get("/v1/fights/", params=params)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("data", result.get("results", []))
    return []


def get_upcoming_fights(limit: int = 50) -> list[dict]:
    """Upcoming fights from the v1 API."""
    result = _get("/v1/fights/", params={"status": "NOT_STARTED", "limit": limit})
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("data", result.get("results", []))
    return []


# ─── Fight parser (v1 response → internal bout dict) ─────────────────────────

_BD_METHOD_MAP = {
    "KO": "KO", "TKO": "TKO", "UD": "UD", "MD": "MD", "SD": "SD",
    "RTD": "RTD", "DQ": "DQ", "NC": "NC", "DRAW": "DRAW",
    "UNANIMOUS DECISION": "UD", "MAJORITY DECISION": "MD",
    "SPLIT DECISION": "SD", "TECHNICAL KNOCKOUT": "TKO",
    "KNOCKOUT": "KO", "NO CONTEST": "NC",
}


def parse_bd_fight(raw: dict) -> dict | None:
    """
    Convert a boxing-data.com v1 fight object into our internal bout dict,
    ready for `_upsert_bout()`.

    Returns None if essential fields (date, fighters) are missing.
    """
    from datetime import datetime

    date_str = raw.get("date") or raw.get("updated_at")
    if not date_str:
        return None

    try:
        fight_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None

    fighters = raw.get("fighters") or {}
    f1 = fighters.get("fighter_1") or {}
    f2 = fighters.get("fighter_2") or {}
    fa_name = (f1.get("full_name") or f1.get("name") or "").strip()
    fb_name = (f2.get("full_name") or f2.get("name") or "").strip()
    if not fa_name or not fb_name:
        return None

    # Result
    result: str | None = None
    if f1.get("winner") is True:
        result = "A"
    elif f2.get("winner") is True:
        result = "B"
    elif raw.get("status") == "FINISHED":
        result = "draw"  # FINISHED with no winner → draw or NC

    # Method
    outcomes = raw.get("results") or {}
    raw_method = (outcomes.get("outcome") or "").upper().strip()
    method = _BD_METHOD_MAP.get(raw_method, raw_method or None)

    # Weight class
    division = raw.get("division") or {}
    weight_class = division.get("name") if isinstance(division, dict) else None

    # Title fight
    titles = raw.get("titles") or []
    title_fight = bool(titles)
    sanctioning_body: str | None = None
    if titles and isinstance(titles, list) and isinstance(titles[0], dict):
        org = titles[0].get("organization") or {}
        sanctioning_body = org.get("abbreviation") or org.get("name") if isinstance(org, dict) else str(org)

    # Event
    event = raw.get("event") or {}
    event_name = event.get("title") or raw.get("title") or ""

    return {
        "ext_id": f"bd_{raw['id']}",
        "fight_date": fight_date,
        "fighter_a": fa_name,
        "fighter_b": fb_name,
        "result": result,
        "method": method,
        "round_ended": outcomes.get("round"),
        "total_rounds": raw.get("scheduled_rounds", 12),
        "weight_class": weight_class,
        "venue": raw.get("venue") or "",
        "location": raw.get("location") or "",
        "event_name": event_name,
        "title_fight": title_fight,
        "sanctioning_body": sanctioning_body,
        "is_upcoming": raw.get("status") != "FINISHED",
    }

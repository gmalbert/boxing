"""
KnockOutIQ — Wikipedia Fighter Enrichment
==========================================
For each fighter in the DB that is missing physical attributes (height, reach,
stance, birth_date, nationality), this script queries the Wikipedia API to
fill in the gaps.

Wikipedia is completely free, no API key required, and very rate-limit tolerant.
We add a 1 s delay between requests to be polite.

Usage
-----
    # Enrich all fighters missing at least one physical attribute:
    python scripts/enrich_fighters_wiki.py

    # Dry-run (print what would be updated, don't write to DB):
    python scripts/enrich_fighters_wiki.py --dry-run

    # Only fighters whose names contain a substring:
    python scripts/enrich_fighters_wiki.py --filter "Crawford"

    # Limit to N fighters per run (useful for incremental enrichment):
    python scripts/enrich_fighters_wiki.py --limit 50
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.db import Fighter, get_engine, get_session
from data.db import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

_WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
_DELAY = 1.0  # seconds between Wikipedia API calls
_HEADERS = {
    "User-Agent": "KnockOutIQ/1.0 (boxing analytics; contact: knockoutiq@example.com)"
}


# ─── Wikipedia helpers ────────────────────────────────────────────────────────

def _names_match(fighter_name: str, page_title: str) -> bool:
    """
    Reject clearly wrong Wikipedia matches.

    Requires BOTH of:
    1. The first significant token (first name) appears in the page title.
    2. The longest significant token (usually last name) appears in the page title.

    This blocks "Sergio de Leon → Sergio Martínez" (first name matches but last
    name "Leon"/"de" don't appear) and "Gvozdyk → Usyk" (first name "Oleksandr"
    matches but last name "Gvozdyk" does not).
    """
    pt_lower = page_title.lower()
    tokens = [t.lower() for t in re.split(r"\W+", fighter_name) if len(t) >= 4]
    if not tokens:
        return False

    longest = max(tokens, key=len)
    first = tokens[0]

    # Both first name and longest token must appear in the page title
    return (first in pt_lower) and (longest in pt_lower)


def _wiki_search(name: str) -> str | None:
    """Return the Wikipedia page title for the most likely boxer match."""
    resp = requests.get(
        _WIKI_SEARCH,
        headers=_HEADERS,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"{name} professional boxer",
            "format": "json",
            "srlimit": 3,
        },
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("query", {}).get("search", [])
    if not results:
        return None
    # Prefer the result whose snippet mentions "boxer" or "boxing"
    for r in results:
        snip = (r.get("snippet") or "").lower()
        if "box" in snip or "heavyweight" in snip or "champion" in snip:
            return r["title"]
    return results[0]["title"]


def _wiki_infobox(page_title: str) -> dict:
    """Fetch raw wikitext for *page_title* and parse the infobox fields."""
    resp = requests.get(
        _WIKI_SEARCH,
        headers=_HEADERS,
        params={
            "action": "query",
            "titles": page_title,
            "prop": "revisions",
            "rvprop": "content",
            "format": "json",
            "rvslots": "main",
        },
        timeout=10,
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    try:
        content = page["revisions"][0]["slots"]["main"]["*"]
    except (KeyError, IndexError):
        return {}

    def _clean(s: str) -> str:
        """Strip wiki markup from a field value."""
        s = re.sub(r"\{\{convert\|([0-9.]+)\|.*?\}\}", r"\1", s, flags=re.I)
        s = re.sub(r"\{\{.*?\}\}", "", s)
        s = re.sub(r"\[\[(?:[^|]*\|)?([^\]]*)\]\]", r"\1", s)
        s = re.sub(r"<.*?>", "", s)
        return s.strip()

    _FIELDS = [
        "birth_date", "birth_place", "nationality",
        "height", "reach", "stance",
    ]
    info: dict = {"_page_title": page_title}
    for field in _FIELDS:
        # Match field value; allow up to ~300 chars before hitting next field or end
        m = re.search(
            rf"\|\s*{field}\s*=\s*(.{{1,300}}?)(?:\n\s*\||\Z)",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            raw_val = m.group(1)
            # Keep raw value for birth_date (needs template content before stripping)
            if field == "birth_date":
                info["_birth_date_raw"] = raw_val
            info[field] = _clean(raw_val)
    return info


def _wiki_is_female(page_title: str) -> bool:
    """Return True if the Wikipedia page's categories indicate a female boxer."""
    resp = requests.get(
        _WIKI_SEARCH,
        headers=_HEADERS,
        params={
            "action": "query",
            "titles": page_title,
            "prop": "categories",
            "cllimit": 30,
            "format": "json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    cats = [c.get("title", "").lower() for c in page.get("categories", [])]
    return any("female" in c or "women" in c for c in cats)


# ─── Unit conversion helpers ──────────────────────────────────────────────────

def _parse_cm(text: str) -> int | None:
    """Try to extract a centimetre value from strings like '180 cm', '5 ft 11 in'."""
    # Direct cm
    m = re.search(r"([\d.]+)\s*cm", text, re.I)
    if m:
        return round(float(m.group(1)))
    # Feet + inches → cm
    m = re.search(r"(\d+)\s*(?:ft|')\s*(\d+)?\s*(?:in|\")?", text, re.I)
    if m:
        ft = int(m.group(1))
        inch = int(m.group(2)) if m.group(2) else 0
        return round((ft * 12 + inch) * 2.54)
    # Bare integer ≥ 150 → probably already cm
    m = re.search(r"\b(1[5-9]\d|2\d\d)\b", text)
    if m:
        return int(m.group(1))
    return None


def _parse_date(text: str):
    """Try to extract a date from wikitext birth_date fields."""
    from datetime import date
    # {{birth date and age|1994|3|15}} or {{birth date|1994|3|15}}
    m = re.search(r"\{\{birth[^|]*\|(\d{4})\|(\d{1,2})\|(\d{1,2})", text, re.I)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # Pipe-separated: |1994|3|15
    m = re.search(r"(\d{4})\|(\d{1,2})\|(\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # ISO: 1994-03-15
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        from datetime import datetime
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def _parse_nationality(text: str) -> str | None:
    """Clean nationality / birth_place into a short country string."""
    # Handle {{plainlist|...}} — extract first bullet item
    m = re.search(r"\{\{plainlist[^}]*\}\}[^*]*\*\s*([^\n*{}|]+)", text, re.I)
    if m:
        return m.group(1).strip() or None
    # Strip flag templates: {{flagcountry|X}} → X
    clean = re.sub(r"\{\{flag(?:country|icon)?\|([^|}]+)[^}]*\}\}", r"\1", text)
    # Strip remaining templates
    clean = re.sub(r"\{\{.*?\}\}", "", clean)
    # Strip wiki links
    clean = re.sub(r"\[\[(?:[^|]*\|)?([^\]]*)\]\]", r"\1", clean)
    # Strip HTML
    clean = re.sub(r"<.*?>", "", clean)
    # Strip stray pipe chars and template remnants
    clean = re.sub(r"\|.*", "", clean)
    clean = clean.strip().strip(",").strip()
    if not clean or len(clean) > 60:
        return None
    return clean or None


# ─── Main enrichment logic ────────────────────────────────────────────────────

def enrich_fighter(fighter: Fighter, dry_run: bool, men_only: bool = False) -> bool:
    """
    Fetch Wikipedia data for *fighter* and fill in missing attributes.
    Returns True if any field was updated.
    If *men_only* is True, female fighters are tagged as sex='F' but their
    physical attributes are not enriched.
    """
    try:
        page_title = _wiki_search(fighter.name)
    except Exception as exc:
        log.warning("Wiki search failed for %s: %s", fighter.name, exc)
        return False

    if not page_title:
        log.debug("No Wikipedia page found for %s", fighter.name)
        return False

    if not _names_match(fighter.name, page_title):
        log.debug("Name mismatch: %s → wiki=%s (skipping)", fighter.name, page_title)
        return False

    time.sleep(_DELAY)

    # Detect gender via Wikipedia categories
    changed = False
    is_female = False
    try:
        is_female = _wiki_is_female(page_title)
        new_sex = 'F' if is_female else 'M'
        if getattr(fighter, 'sex', None) != new_sex:
            fighter.sex = new_sex
            changed = True
    except Exception as exc:
        log.debug("Gender detection failed for %s: %s", fighter.name, exc)

    if men_only and is_female:
        if changed:
            log.info("TAGGED %s as sex=F (skipping attribute enrichment)", fighter.name)
        return changed

    try:
        info = _wiki_infobox(page_title)
    except Exception as exc:
        log.warning("Wiki infobox fetch failed for %s (%s): %s", fighter.name, page_title, exc)
        return changed

    if not info:
        return changed

    if not fighter.height_cm and info.get("height"):
        v = _parse_cm(info["height"])
        if v:
            fighter.height_cm = v
            changed = True

    if not fighter.reach_cm and info.get("reach"):
        v = _parse_cm(info["reach"])
        if v:
            fighter.reach_cm = v
            changed = True

    if not fighter.stance and info.get("stance"):
        s = info["stance"].strip().title()
        if s in ("Orthodox", "Southpaw", "Switch"):
            fighter.stance = s
            changed = True

    if not fighter.birth_date and (info.get("_birth_date_raw") or info.get("birth_date")):
        d = _parse_date(info.get("_birth_date_raw") or info.get("birth_date", ""))
        if d:
            fighter.birth_date = d
            changed = True

    if not fighter.nationality:
        raw_nat = info.get("nationality") or info.get("birth_place")
        if raw_nat:
            nat = _parse_nationality(raw_nat)
            if nat:
                fighter.nationality = nat
                changed = True

    if changed:
        action = "WOULD UPDATE" if dry_run else "UPDATED"
        log.info(
            "%s %s (wiki: %s) — h=%s r=%s stance=%s born=%s nat=%s",
            action, fighter.name, page_title,
            fighter.height_cm, fighter.reach_cm,
            fighter.stance, fighter.birth_date, fighter.nationality,
        )

    return changed


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Enrich fighter profiles with Wikipedia physical attributes"
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Print changes without writing to DB")
    p.add_argument("--filter", metavar="SUBSTR",
                   help="Only process fighters whose name contains SUBSTR")
    p.add_argument("--limit", type=int, default=0, metavar="N",
                   help="Stop after N fighters (0 = all)")
    p.add_argument("--force", action="store_true",
                   help="Re-fetch even fighters that already have all attributes")
    p.add_argument("--men-only", action="store_true",
                   help="Tag female fighters as sex=F but skip attribute enrichment for them")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    engine = get_engine()
    Base.metadata.create_all(engine)
    session = get_session()

    query = session.query(Fighter)

    if args.filter:
        query = query.filter(Fighter.name.ilike(f"%{args.filter}%"))

    if not args.force:
        # Only fighters missing at least one physical attribute
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Fighter.height_cm.is_(None),
                Fighter.reach_cm.is_(None),
                Fighter.stance.is_(None),
                Fighter.birth_date.is_(None),
                Fighter.nationality.is_(None),
            )
        )

    fighters = query.order_by(Fighter.name).all()
    log.info("Found %d fighters to enrich", len(fighters))

    updated = 0
    for i, fighter in enumerate(fighters):
        if args.limit and i >= args.limit:
            log.info("Reached --limit %d, stopping.", args.limit)
            break

        changed = enrich_fighter(fighter, dry_run=args.dry_run, men_only=args.men_only)
        if changed:
            updated += 1
            if not args.dry_run:
                session.commit()

        time.sleep(_DELAY)

    log.info("Done — %d fighters updated.", updated)
    session.close()


if __name__ == "__main__":
    main()

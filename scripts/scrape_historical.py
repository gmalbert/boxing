"""
KnockOutIQ — Historical Data Scraper
======================================
Populates the fight database with real historical data from:
  1. ESPN's unofficial scoreboard API  (no auth, recent/major events)
  2. BoxRec.com                        (requires free account, comprehensive)

Usage
-----
    # ESPN only (no login required):
    python scripts/scrape_historical.py --source=espn

    # BoxRec only (credentials in .env):
    python scripts/scrape_historical.py --source=boxrec

    # Both sources (recommended for first run):
    python scripts/scrape_historical.py --source=both

    # Custom year range:
    python scripts/scrape_historical.py --source=both --start=2018 --end=2026

    # Preview without writing to DB:
    python scripts/scrape_historical.py --source=espn --dry-run

After this script finishes, run:
    python scripts/fetch_historical_data.py weekly
to recalculate Elo ratings across all the new fights.

Notes
-----
- Duplicate fights (same ext_id, or same fighter pair on the same date) are
  silently skipped — safe to re-run.
- BoxRec scraping iterates through all weight divisions and fetches the top 50
  ranked active fighters, then retrieves each fighter's full bout history.
- The --source=both order is ESPN first (fast), then BoxRec (slow). ESPN adds
  ~200–500 events; BoxRec typically adds thousands more across all divisions.
"""

from __future__ import annotations

import argparse
import logging
import re
import random
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from config import BOXREC_USERNAME, BOXREC_PASSWORD, RAPID_API_KEY
from data.db import Fighter, Fight, get_engine, get_session
from data.boxrec import (
    BoxRecSession,
    DIVISIONS,
    fetch_espn_events,
)
from data.boxing_data import get_historical_fights, parse_bd_fight
from models.elo import EloSystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── DB Helpers (mirrors fetch_historical_data.py pattern) ───────────────────

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def _get_or_create_fighter(session: Session, name: str) -> Fighter:
    fighter = session.query(Fighter).filter(Fighter.name.ilike(name)).first()
    if not fighter:
        fighter = Fighter(
            name=name,
            external_id=f"scraped_{_slug(name)}",
            elo_rating=1500.0,
        )
        session.add(fighter)
        session.flush()
    return fighter


def _upsert_bout(session: Session, bout: dict, dry_run: bool = False) -> bool:
    """
    Insert or update one fight record from a scraped bout dict.

    Returns True if a new row was written (or would be in dry-run mode).
    Skips fights with missing dates or fighter names.
    """
    fight_date: Optional[date] = bout.get("fight_date")
    fa_name: str = (bout.get("fighter_a") or "").strip()
    fb_name: str = (bout.get("fighter_b") or "").strip()
    ext_id: str = (bout.get("ext_id") or "").strip()

    if not fight_date or not fa_name or not fb_name:
        return False

    if dry_run:
        log.debug("DRY-RUN: would upsert %s vs %s on %s", fa_name, fb_name, fight_date)
        return True

    # Check for existing fight by ext_id
    if ext_id:
        existing = session.query(Fight).filter_by(external_id=ext_id).first()
        if existing:
            return False  # already in DB

    # Check for duplicate by fighters + date (regardless of ext_id)
    fa = _get_or_create_fighter(session, fa_name)
    fb = _get_or_create_fighter(session, fb_name)

    dup = (
        session.query(Fight)
        .filter(
            Fight.fighter_a_id == fa.id,
            Fight.fighter_b_id == fb.id,
            Fight.fight_date == fight_date,
        )
        .first()
    )
    if dup:
        # Update ext_id if we have a better one now
        if ext_id and not dup.external_id:
            dup.external_id = ext_id
        return False

    # Also check the reverse order (fighter B vs fighter A on same date)
    dup_rev = (
        session.query(Fight)
        .filter(
            Fight.fighter_a_id == fb.id,
            Fight.fighter_b_id == fa.id,
            Fight.fight_date == fight_date,
        )
        .first()
    )
    if dup_rev:
        return False

    fight = Fight(
        external_id=ext_id or f"scraped_{_slug(fa_name)}_{fight_date.isoformat()}",
        fighter_a_id=fa.id,
        fighter_b_id=fb.id,
        fight_date=fight_date,
        weight_class=bout.get("weight_class"),
        result=bout.get("result"),
        method=bout.get("method"),
        round_ended=bout.get("round_ended"),
        total_rounds=bout.get("total_rounds", 12),
        title_fight=bout.get("title_fight", False),
        sanctioning_body=bout.get("sanctioning_body"),
        venue=bout.get("venue", ""),
        location=bout.get("location", ""),
        event_name=bout.get("event_name", ""),
        is_upcoming=bout.get("is_upcoming", False),
    )
    session.add(fight)
    return True


# ─── ESPN Import ──────────────────────────────────────────────────────────────

def import_espn(session: Session, start: int, end: int, dry_run: bool) -> int:
    """
    ESPN boxing import — DISABLED.

    ESPN's unofficial scoreboard API (/apis/site/v2/sports/boxing/scoreboard)
    returns 404 for boxing; the sport is not supported.  ESPN only has API
    coverage for MMA/UFC.  The .md doc was describing ESPN's *website*, not an
    API endpoint.  This function is kept as a stub so the CLI --source=espn
    flag doesn't crash, but it always returns 0.
    """
    log.warning(
        "ESPN source skipped: ESPN's API does not support boxing (404). "
        "Use --source=boxrec for historical data."
    )
    return 0


# ─── boxing-data.com Import ───────────────────────────────────────────────────

_BD_FREE_TIER_CAP = 10  # free tier returns at most 10 results regardless of params


def import_boxing_data(
    session: Session,
    start: int,
    end: int,
    dry_run: bool,
    delay: float = 2.5,  # 2.5 s between requests → stays under 30 req/min free tier
) -> int:
    """
    Import fights from boxing-data.com /v1/fights/.

    NOTE: The free tier ignores all filter parameters (year, status) and always
    returns the same 10 most-recent fights.  Pagination is also locked.  We
    therefore fetch a single page, import whatever is new, and warn the user
    if it looks like a free-tier cap.  Upgrading to a paid plan will
    automatically enable year-based pagination (see _import_boxing_data_full).
    """
    if not RAPID_API_KEY:
        log.error("boxing-data.com: RAPID_API_KEY not set in .env — skipping.")
        return 0

    # --- Try page 1 and page 2; if they are identical we are on the free tier ---
    log.info("boxing-data.com: fetching page 1 …")
    try:
        p1 = get_historical_fights(year=None, page=1, limit=100)  # year=None → no filter
    except Exception as exc:
        log.error("boxing-data.com page 1 error: %s", exc)
        return 0

    if not p1:
        log.warning("boxing-data.com: page 1 returned no fights.")
        return 0

    time.sleep(delay)

    log.info("boxing-data.com: fetching page 2 to detect free-tier lock …")
    try:
        p2 = get_historical_fights(year=None, page=2, limit=100)
    except Exception as exc:
        log.warning("boxing-data.com page 2 error: %s — assuming single page", exc)
        p2 = []

    ids1 = {r.get("id") for r in p1}
    ids2 = {r.get("id") for r in p2}
    free_tier = bool(p2) and ids1 == ids2  # same items on both pages → locked

    if free_tier:
        log.warning(
            "boxing-data.com: FREE TIER DETECTED — API returns the same %d fights "
            "regardless of page/year filters.  Only these %d recent fights can be "
            "imported until you upgrade to a paid plan.",
            len(p1), len(p1),
        )

    total_new = 0
    pages_to_fetch = [p1] if free_tier else None

    if not free_tier:
        # Paid tier: paginate without year filter; stop when date < start year
        # or when a partial page is returned.
        pages_to_fetch = []
        page = 1
        while True:
            raw_page = p1 if page == 1 else get_historical_fights(year=None, page=page, limit=100)
            if not raw_page:
                break
            pages_to_fetch.append(raw_page)
            # If any fight on this page is before start year, we have enough history
            earliest = min(
                (r.get("date") or r.get("updated_at") or "")[:4]
                for r in raw_page
            )
            if earliest and int(earliest) < start:
                break
            if len(raw_page) < 100:
                break
            page += 1
            time.sleep(delay)

    for raw_page in pages_to_fetch:
        for raw in raw_page:
            # Date filter: only import fights within [start, end]
            date_str = (raw.get("date") or raw.get("updated_at") or "")[:4]
            if date_str:
                try:
                    fight_year = int(date_str)
                    if fight_year < start or fight_year > end:
                        continue
                except ValueError:
                    pass

            bout = parse_bd_fight(raw)
            if bout and _upsert_bout(session, bout, dry_run):
                total_new += 1

    if not dry_run and total_new:
        session.commit()

    log.info("boxing-data.com: %d new fights imported.", total_new)
    return total_new


# ─── BoxRec Import ────────────────────────────────────────────────────────────

def import_boxrec(
    session: Session,
    start: int,
    end: int,
    dry_run: bool,
    boxers_per_division: int = 50,
) -> int:
    """
    Authenticate with BoxRec, scrape each division's top fighters, and
    store their full bout histories.

    Strategy:
      For each weight division → top *boxers_per_division* active pros
        → for each boxer → fetch all bouts → upsert those in [start, end]

    This covers nearly every notable pro fight because the top 50 fighters
    in each division collectively have bouts against hundreds of opponents,
    which in turn appear in other fighters' records.
    """
    if not BOXREC_USERNAME or not BOXREC_PASSWORD:
        log.error(
            "BoxRec credentials not set. Add BOXREC_USERNAME and BOXREC_PASSWORD "
            "to your .env file (see .env.example). Skipping BoxRec scrape."
        )
        return 0

    br = BoxRecSession(headless=False)
    if not br.login(BOXREC_USERNAME, BOXREC_PASSWORD):
        br.close()
        log.error("BoxRec: authentication failed. Skipping.")
        return 0

    total_new = 0
    seen_boxer_ids: set[str] = set()

    try:
        for division in DIVISIONS:
            log.info("BoxRec: scraping division '%s' ...", division)
            # Randomised inter-division pause (8–15 s) to reduce rate-limit risk
            pause = random.uniform(8, 15)
            log.debug("BoxRec: pausing %.1f s before next division", pause)
            time.sleep(pause)
            try:
                boxer_ids = br.get_top_boxer_ids(division, limit=boxers_per_division)
            except RuntimeError as exc:
                # Unresolved recaptcha — abort the whole run
                log.error("BoxRec: recaptcha block unresolved, aborting: %s", exc)
                break
            except Exception as exc:
                log.warning("BoxRec: could not get ratings for %s: %s", division, exc)
                continue

            log.info("  -> %d boxers found in %s", len(boxer_ids), division)

            for boxer_id in boxer_ids:
                if boxer_id in seen_boxer_ids:
                    continue
                seen_boxer_ids.add(boxer_id)

                try:
                    bouts = br.get_boxer_bouts(boxer_id)
                except Exception as exc:
                    log.warning("  BoxRec: boxer %s failed: %s", boxer_id, exc)
                    continue

                new_count = 0
                for bout in bouts:
                    fd = bout.get("fight_date")
                    if fd and not (start <= fd.year <= end):
                        continue
                    if _upsert_bout(session, bout, dry_run):
                        new_count += 1

                # Stamp boxrec_id on the primary fighter so we can audit later.
                if not dry_run and bouts:
                    primary_name = (bouts[0].get("fighter_a") or "").strip()
                    if primary_name:
                        fighter = session.query(Fighter).filter(
                            Fighter.name.ilike(primary_name)
                        ).first()
                        if fighter and fighter.boxrec_id is None:
                            fighter.boxrec_id = str(boxer_id)

                if not dry_run and new_count:
                    session.commit()

                total_new += new_count
                log.info(
                    "  BoxRec: boxer %s -> %d bouts, %d new (running total: %d)",
                    boxer_id, len(bouts), new_count, total_new,
                )
    finally:
        br.close()

    return total_new


# ─── Elo Recalculation ────────────────────────────────────────────────────────

def recalculate_elo(session: Session) -> None:
    """Replay all completed fights chronologically to refresh Elo ratings."""
    from data.db import EloHistory

    log.info("Recalculating Elo for all fights …")
    elo = EloSystem()
    session.query(EloHistory).delete()

    fights = (
        session.query(Fight)
        .filter(Fight.is_upcoming == False, Fight.result.isnot(None))  # noqa: E712
        .order_by(Fight.fight_date)
        .all()
    )

    for fight in fights:
        fa = session.get(Fighter, fight.fighter_a_id)
        fb = session.get(Fighter, fight.fighter_b_id)
        if not fa or not fb:
            continue

        winner_name: Optional[str] = None
        if fight.result == "A":
            winner_name = fa.name
        elif fight.result == "B":
            winner_name = fb.name

        result = elo.record_fight(
            fa.name, fb.name,
            winner=winner_name,
            method=fight.method or "UD",
        )
        fa.elo_rating = elo.get_rating(fa.name)
        fb.elo_rating = elo.get_rating(fb.name)

        session.add_all([
            EloHistory(
                fighter_id=fa.id,
                fight_id=fight.id,
                elo_before=(
                    result.winner_before if winner_name == fa.name else result.loser_before
                ),
                elo_after=fa.elo_rating,
            ),
            EloHistory(
                fighter_id=fb.id,
                fight_id=fight.id,
                elo_before=(
                    result.winner_before if winner_name == fb.name else result.loser_before
                ),
                elo_after=fb.elo_rating,
            ),
        ])

    session.commit()
    log.info("Elo recalculated across %d fights.", len(fights))


# ─── Fighter Stats Recalculation ──────────────────────────────────────────────

def recalculate_fighter_stats(session: Session) -> None:
    """
    Recount wins/losses/draws/ko_wins/tko_wins for every fighter from
    the Fight table.  This is the only way BoxRec-scraped opponents get
    accurate career records (the scraper writes Fight rows but never
    directly updates Fighter stat columns).
    """
    log.info("Recalculating fighter career stats from fight records …")

    from collections import defaultdict
    wins = defaultdict(int)
    losses = defaultdict(int)
    draws = defaultdict(int)
    ko_wins = defaultdict(int)
    tko_wins = defaultdict(int)

    fights = (
        session.query(Fight)
        .filter(Fight.is_upcoming == False, Fight.result.isnot(None))  # noqa: E712
        .all()
    )
    for fight in fights:
        a, b = fight.fighter_a_id, fight.fighter_b_id
        r, m = fight.result, (fight.method or "").upper()
        if r == "A":
            wins[a] += 1
            losses[b] += 1
            if m == "KO":
                ko_wins[a] += 1
            elif m == "TKO":
                tko_wins[a] += 1
        elif r == "B":
            wins[b] += 1
            losses[a] += 1
            if m == "KO":
                ko_wins[b] += 1
            elif m == "TKO":
                tko_wins[b] += 1
        elif r in ("draw", "NC"):
            draws[a] += 1
            draws[b] += 1

    all_ids = set(wins) | set(losses) | set(draws)
    for fid in all_ids:
        fighter = session.get(Fighter, fid)
        if fighter:
            fighter.wins = wins[fid]
            fighter.losses = losses[fid]
            fighter.draws = draws[fid]
            fighter.ko_wins = ko_wins[fid]
            fighter.tko_wins = tko_wins[fid]

    session.commit()
    log.info("Fighter stats updated for %d fighters.", len(all_ids))


# ─── BoxRec Import by Specific IDs ────────────────────────────────────────────

def import_boxrec_by_ids(
    session: Session,
    boxer_ids: list[str],
    start: int,
    end: int,
    dry_run: bool,
) -> int:
    """
    Scrape BoxRec profiles for a specific list of boxer IDs (e.g. to backfill
    shell fighter records) and store their bout histories.
    """
    if not BOXREC_USERNAME or not BOXREC_PASSWORD:
        log.error("BoxRec credentials not set. Skipping.")
        return 0

    br = BoxRecSession(headless=False)
    if not br.login(BOXREC_USERNAME, BOXREC_PASSWORD):
        br.close()
        log.error("BoxRec: authentication failed.")
        return 0

    total_new = 0
    try:
        for boxer_id in boxer_ids:
            try:
                bouts = br.get_boxer_bouts(boxer_id)
            except Exception as exc:
                log.warning("BoxRec: boxer %s failed: %s", boxer_id, exc)
                continue

            new_count = 0
            for bout in bouts:
                fd = bout.get("fight_date")
                if fd and not (start <= fd.year <= end):
                    continue
                if _upsert_bout(session, bout, dry_run):
                    new_count += 1

            # Stamp boxrec_id on the primary fighter so we can audit later.
            # All bouts from get_boxer_bouts() are from fighter_a's perspective.
            if not dry_run and bouts:
                primary_name = (bouts[0].get("fighter_a") or "").strip()
                if primary_name:
                    fighter = session.query(Fighter).filter(
                        Fighter.name.ilike(primary_name)
                    ).first()
                    if fighter and fighter.boxrec_id is None:
                        fighter.boxrec_id = str(boxer_id)

            if not dry_run and new_count:
                session.commit()

            total_new += new_count
            log.info("BoxRec: boxer %s -> %d bouts, %d new", boxer_id, len(bouts), new_count)
    finally:
        br.close()

    return total_new


def _resolve_shell_boxer_ids(session: Session) -> dict[str, str]:
    """
    For every male shell fighter in the DB (elo=1500, wins=0, losses=0),
    search BoxRec by name and return a mapping of {boxer_id: fighter_name}.
    Opens a single browser session for all searches.
    """
    from sqlalchemy import or_

    shells = (
        session.query(Fighter)
        .filter(
            Fighter.sex == 'M',
            Fighter.elo_rating == 1500.0,
            or_(Fighter.wins == 0, Fighter.wins.is_(None)),
            or_(Fighter.losses == 0, Fighter.losses.is_(None)),
        )
        .order_by(Fighter.name)
        .all()
    )
    log.info("Resolving BoxRec IDs for %d shell fighters …", len(shells))

    if not BOXREC_USERNAME or not BOXREC_PASSWORD:
        log.error("BoxRec credentials not set. Cannot resolve shell fighters.")
        return {}

    br = BoxRecSession(headless=False)
    if not br.login(BOXREC_USERNAME, BOXREC_PASSWORD):
        br.close()
        log.error("BoxRec: authentication failed.")
        return {}

    resolved: dict[str, str] = {}
    try:
        for fighter in shells:
            boxer_id = br.get_boxer_id_by_name(fighter.name)
            if boxer_id:
                resolved[boxer_id] = fighter.name
            else:
                log.warning("Could not resolve BoxRec ID for %r", fighter.name)
            time.sleep(2)
    finally:
        br.close()

    log.info("Resolved %d / %d shell fighters to BoxRec IDs", len(resolved), len(shells))
    return resolved


def _re_resolve_fighters(
    session: Session, start: int, end: int, dry_run: bool
) -> int:
    """
    Audit every fighter whose boxrec_id was stamped by a previous scrape.

    For each such fighter:
      1. Re-run get_boxer_id_by_name() with the current (fixed) search logic.
      2. If the new ID matches the stored one → no action.
      3. If the new ID differs → mismatch detected:
         - In dry-run mode: log the discrepancy only.
         - Otherwise: delete the fighter's BoxRec-sourced fights, reset their
           stats to shell state, clear the old boxrec_id, and queue the correct
           ID for re-scraping.
    Returns the number of new fights imported after fixing mismatches.
    """
    from sqlalchemy import or_

    enriched = (
        session.query(Fighter)
        .filter(Fighter.boxrec_id.isnot(None))
        .order_by(Fighter.name)
        .all()
    )
    log.info("Auditing %d enriched fighters (those with boxrec_id set) …", len(enriched))

    if not enriched:
        log.info("No enriched fighters to audit.")
        return 0

    if not BOXREC_USERNAME or not BOXREC_PASSWORD:
        log.error("BoxRec credentials not set. Cannot re-resolve.")
        return 0

    br = BoxRecSession(headless=False)
    if not br.login(BOXREC_USERNAME, BOXREC_PASSWORD):
        br.close()
        log.error("BoxRec: authentication failed.")
        return 0

    mismatches: list[tuple[Fighter, str]] = []  # (fighter, correct_new_id)
    try:
        for fighter in enriched:
            new_id = br.get_boxer_id_by_name(fighter.name)
            time.sleep(2)
            if new_id is None:
                log.warning("Re-resolve: could not find BoxRec ID for %r — skipping", fighter.name)
                continue
            if new_id == fighter.boxrec_id:
                log.debug("Re-resolve: %r — ID %s unchanged", fighter.name, new_id)
                continue
            log.warning(
                "Re-resolve MISMATCH: %r had boxrec_id=%s, new search returns %s",
                fighter.name, fighter.boxrec_id, new_id,
            )
            mismatches.append((fighter, new_id))
    finally:
        br.close()

    if not mismatches:
        log.info("Re-resolve: no mismatches found — all boxrec_ids are correct.")
        return 0

    log.info("Re-resolve: %d mismatch(es) found.", len(mismatches))

    if dry_run:
        log.info("DRY-RUN — no changes made. Mismatches:")
        for fighter, new_id in mismatches:
            log.info("  %r: stored=%s  correct=%s", fighter.name, fighter.boxrec_id, new_id)
        return 0

    # Fix each mismatch: delete old fights, reset fighter, queue re-scrape.
    correct_ids: list[str] = []
    for fighter, new_id in mismatches:
        # Delete fights sourced from BoxRec for this fighter.
        # BoxRec-sourced fights have external_id containing "boxrec" (either the
        # full URL or our fallback slug).
        fights_to_delete = (
            session.query(Fight)
            .filter(
                or_(Fight.fighter_a_id == fighter.id, Fight.fighter_b_id == fighter.id),
                Fight.external_id.like("%boxrec%"),
            )
            .all()
        )
        for fight in fights_to_delete:
            session.delete(fight)
        log.info(
            "Re-resolve: deleted %d fights for %r (old boxrec_id=%s)",
            len(fights_to_delete), fighter.name, fighter.boxrec_id,
        )

        # Reset fighter to shell state.
        fighter.wins = 0
        fighter.losses = 0
        fighter.draws = 0
        fighter.ko_wins = 0
        fighter.tko_wins = 0
        fighter.elo_rating = 1500.0
        fighter.boxrec_id = None

        correct_ids.append(new_id)

    session.commit()
    log.info("Re-resolve: reset %d fighters; re-scraping with correct IDs …", len(mismatches))

    total_new = import_boxrec_by_ids(session, correct_ids, start, end, dry_run=False)
    log.info("Re-resolve: %d new fights imported after correction.", total_new)
    return total_new


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scrape ESPN and/or BoxRec fight history into KnockOutIQ DB"
    )
    p.add_argument(
        "--source",
        choices=["espn", "boxing-data", "boxrec", "both", "all"],
        default="boxrec",
        help=(
            "Data source(s) to scrape. "
            "'boxing-data' = boxing-data.com API (free tier: 10 recent fights only). "
            "'boxrec' = full historical scrape via browser (recommended). "
            "'both'/'all' = boxing-data + boxrec. "
            "'espn' = disabled (ESPN has no boxing API). "
            "(default: boxrec)"
        ),
    )
    p.add_argument(
        "--start",
        type=int,
        default=2015,
        metavar="YEAR",
        help="Earliest year to import (default: 2015)",
    )
    p.add_argument(
        "--end",
        type=int,
        default=date.today().year,
        metavar="YEAR",
        help="Latest year to import (default: current year)",
    )
    p.add_argument(
        "--boxers-per-division",
        type=int,
        default=50,
        metavar="N",
        help="BoxRec: how many top-ranked fighters to scrape per division (default: 50)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and log without writing to the database",
    )
    p.add_argument(
        "--skip-elo",
        action="store_true",
        help="Skip Elo recalculation after import (useful for incremental runs)",
    )
    p.add_argument(
        "--boxer-ids",
        metavar="IDS",
        default="",
        help=(
            "Comma-separated BoxRec boxer IDs to scrape directly "
            "(e.g. 983389,628407). Bypasses the division ratings loop."
        ),
    )
    p.add_argument(
        "--enrich-shells",
        action="store_true",
        help=(
            "Search BoxRec by name for every male shell fighter (elo=1500, 0-0) "
            "and scrape their full bout history. One-time backfill."
        ),
    )
    p.add_argument(
        "--re-resolve",
        action="store_true",
        help=(
            "Audit fighters whose boxrec_id was previously set via name search. "
            "Re-runs the search with the current logic; if the resolved ID differs, "
            "deletes their fights and re-scrapes using the correct ID. "
            "Combine with --dry-run to preview mismatches without making changes."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    log.info("=== KnockOutIQ Historical Scraper ===")
    log.info("Source: %s | Years: %d–%d | Dry-run: %s",
             args.source, args.start, args.end, args.dry_run)
    # Validate mutually-exclusive shortcut flags
    if args.boxer_ids and args.enrich_shells:
        log.error("--boxer-ids and --enrich-shells cannot be used together.")
        sys.exit(1)
    if getattr(args, "re_resolve", False) and (args.boxer_ids or args.enrich_shells):
        log.error("--re-resolve cannot be combined with --boxer-ids or --enrich-shells.")
        sys.exit(1)
    # Ensure DB tables exist
    from data.db import Base
    engine = get_engine()
    Base.metadata.create_all(engine)

    session = get_session()
    total_new = 0

    try:
        if args.source in ("espn", "both", "all"):
            n = import_espn(session, args.start, args.end, args.dry_run)
            log.info("ESPN total new fights: %d", n)
            total_new += n

        if args.source in ("boxing-data", "both", "all"):
            n = import_boxing_data(session, args.start, args.end, args.dry_run)
            log.info("boxing-data.com total new fights: %d", n)
            total_new += n

        if args.boxer_ids:
            ids = [i.strip() for i in args.boxer_ids.split(",") if i.strip()]
            log.info("Scraping %d specific BoxRec IDs: %s", len(ids), ids)
            n = import_boxrec_by_ids(session, ids, args.start, args.end, args.dry_run)
            log.info("BoxRec (by ID) total new fights: %d", n)
            total_new += n
        elif args.enrich_shells:
            log.info("Resolving and scraping all male shell fighters …")
            resolved = _resolve_shell_boxer_ids(session)
            if resolved:
                n = import_boxrec_by_ids(
                    session, list(resolved.keys()), args.start, args.end, args.dry_run
                )
                log.info("BoxRec (shell enrich) total new fights: %d", n)
                total_new += n
        elif getattr(args, "re_resolve", False):
            log.info("Auditing and re-resolving fighters with mismatched BoxRec IDs …")
            n = _re_resolve_fighters(session, args.start, args.end, args.dry_run)
            log.info("Re-resolve total new fights: %d", n)
            total_new += n
        elif args.source in ("boxrec", "all"):
            n = import_boxrec(
                session,
                args.start,
                args.end,
                args.dry_run,
                boxers_per_division=args.boxers_per_division,
            )
            log.info("BoxRec total new fights: %d", n)
            total_new += n

        log.info("Grand total new fights inserted: %d", total_new)

        if not args.dry_run and not args.skip_elo and total_new > 0:
            recalculate_elo(session)
            recalculate_fighter_stats(session)

        log.info("[OK] Scrape complete.")

    except KeyboardInterrupt:
        log.info("Interrupted — committing what we have …")
        if not args.dry_run:
            session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()

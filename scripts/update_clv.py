"""
KnockOutIQ — Closing Line Value (CLV) Tracker

Computes CLV for completed bets by comparing the odds obtained at bet time
against the closing line (latest OddsSnapshot before the fight). Positive CLV
indicates the bettor beat the market — a strong validation signal that model
edges are real.

Usage:
    python scripts/update_clv.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.db import BetLog, Fight, OddsSnapshot, get_engine, get_session
from utils.odds_utils import clv as _clv

MAX_PRE_FIGHT_SNAPSHOT_HOURS = 2  # closing line = last snapshot within this window


def update_clv():
    get_engine()
    session = get_session()

    try:
        # Find bets that need CLV: result is known but CLV is still null
        bets = (
            session.query(BetLog)
            .filter(BetLog.result.in_(["win", "loss", "push"]))
            .filter(BetLog.clv.is_(None))
            .all()
        )

        if not bets:
            print("[clv] No unsettled CLV entries found.")
            return

        updated = 0
        for bet in bets:
            if not bet.fight_id or bet.american_odds_obtained is None:
                continue

            fight = session.get(Fight, bet.fight_id)
            if not fight or not fight.fight_date:
                continue

            # Closing line = most recent snapshot within the pre-fight window
            cutoff = datetime(
                fight.fight_date.year,
                fight.fight_date.month,
                fight.fight_date.day,
                tzinfo=timezone.utc,
            )
            snapshots = (
                session.query(OddsSnapshot)
                .filter(OddsSnapshot.fight_id == bet.fight_id)
                .filter(OddsSnapshot.fighter_name == bet.fighter_name)
                .filter(OddsSnapshot.bookmaker == (bet.bookmaker or "draftkings"))
                .filter(OddsSnapshot.snapshot_time <= cutoff)
                .order_by(OddsSnapshot.snapshot_time.desc())
                .limit(1)
                .all()
            )
            if not snapshots:
                continue

            closing_odds = snapshots[0].american_odds
            if closing_odds is None or closing_odds == bet.american_odds_obtained:
                continue

            bet.closing_odds = closing_odds
            bet.clv = round(_clv(bet.american_odds_obtained, closing_odds), 6)
            updated += 1

        session.commit()
        print(f"[clv] Updated CLV for {updated} bet(s).")

        # Summary stats
        all_bets = (
            session.query(BetLog)
            .filter(BetLog.clv.isnot(None))
            .all()
        )
        if all_bets:
            clvs = [b.clv for b in all_bets if b.clv is not None]
            positive = sum(1 for c in clvs if c > 0)
            print(f"  Total CLV-tracked bets: {len(clvs)}")
            print(f"  Positive CLV: {positive}/{len(clvs)} ({positive / len(clvs):.0%})")
            print(f"  Mean CLV: {sum(clvs) / len(clvs):+.4f}")

    finally:
        session.close()


if __name__ == "__main__":
    update_clv()

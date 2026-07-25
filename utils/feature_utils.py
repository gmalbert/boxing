"""
KnockOutIQ — Feature engineering utilities.

Shared by scripts/precache_predictions.py, scripts/train_models.py, and
pages/05_Model_Dashboard.py so that feature construction is consistent
across training, caching, and the UI.
"""

from __future__ import annotations

from datetime import date

import numpy as np


# ─── Per-fighter stat helpers ─────────────────────────────────────────────────

def _win_pct(fighter) -> float:
    total = (fighter.wins or 0) + (fighter.losses or 0)
    return (fighter.wins or 0) / total if total else 0.5


def _ko_pct(fighter) -> float:
    wins = fighter.wins or 1
    ko = (fighter.ko_wins or 0) + (fighter.tko_wins or 0)
    return ko / wins


def _age_diff(fa, fb) -> float:
    """
    Age difference in years: positive means fighter_a is older than fighter_b.
    An older fighter has an earlier (numerically smaller) birth_date.
    """
    if fa.birth_date and fb.birth_date:
        return (fb.birth_date - fa.birth_date).days / 365.25
    return 0.0


def _days_since_last_fight(fighter, before_date: date, session) -> float | None:
    """
    Days since the fighter's most recent completed fight strictly before
    *before_date*.  Returns None if no prior fight is found.
    """
    from data.db import Fight  # local import to avoid circular dependency

    last = (
        session.query(Fight)
        .filter(
            ((Fight.fighter_a_id == fighter.id) | (Fight.fighter_b_id == fighter.id)),
            Fight.is_upcoming == False,   # noqa: E712
            Fight.fight_date < before_date,
            Fight.result.isnot(None),
        )
        .order_by(Fight.fight_date.desc())
        .first()
    )
    if last and last.fight_date:
        return float((before_date - last.fight_date).days)
    return None


def _avg_opponent_elo(fighter, before_date: date, session) -> float | None:
    """
    Average Elo of all opponents faced in completed fights before *before_date*.
    Only includes opponents with a non-default (≠ 1500) Elo rating.
    Returns None if no qualifying opponents are found.
    """
    from data.db import Fight, Fighter  # local import to avoid circular dependency

    past_fights = (
        session.query(Fight)
        .filter(
            ((Fight.fighter_a_id == fighter.id) | (Fight.fighter_b_id == fighter.id)),
            Fight.is_upcoming == False,   # noqa: E712
            Fight.fight_date < before_date,
        )
        .all()
    )
    elos: list[float] = []
    for f in past_fights:
        opp_id = f.fighter_b_id if f.fighter_a_id == fighter.id else f.fighter_a_id
        opp = session.get(Fighter, opp_id)
        if opp and opp.elo_rating and opp.elo_rating != 1500.0:
            elos.append(float(opp.elo_rating))
    return float(np.mean(elos)) if elos else None


# ─── Weight-class encoding ────────────────────────────────────────────────────

_WEIGHT_CLASS_ORDER = [
    "minimumweight", "light flyweight", "flyweight", "super flyweight",
    "bantamweight", "super bantamweight", "featherweight", "super featherweight",
    "lightweight", "super lightweight", "welterweight", "super welterweight",
    "middleweight", "super middleweight", "light heavyweight", "cruiserweight",
    "bridgerweight", "heavyweight",
]

_WEIGHT_CLASS_ENCODING: dict[str, float] = {}
for _i, _wc in enumerate(_WEIGHT_CLASS_ORDER):
    _WEIGHT_CLASS_ENCODING[_wc] = (_i + 1) / len(_WEIGHT_CLASS_ORDER)


def _encode_weight_class(weight_class: str | None) -> float:
    """Ordinal encode a weight class string to [0, 1]."""
    if not weight_class:
        return 0.5
    wc = weight_class.strip().lower()
    return _WEIGHT_CLASS_ENCODING.get(wc, 0.5)


# ─── Rolling / recency feature helpers ─────────────────────────────────────────

def _rolling_win_rate(fighter, before_date: date, n_fights: int, session) -> float | None:
    """Win rate over the fighter's last *n_fights* completed before *before_date*."""
    from data.db import Fight

    past = (
        session.query(Fight)
        .filter(
            ((Fight.fighter_a_id == fighter.id) | (Fight.fighter_b_id == fighter.id)),
            Fight.is_upcoming == False,  # noqa: E712
            Fight.fight_date < before_date,
            Fight.result.in_(["A", "B"]),
        )
        .order_by(Fight.fight_date.desc())
        .limit(n_fights)
        .all()
    )
    if not past:
        return None
    wins = sum(
        1 for f in past
        if (f.fighter_a_id == fighter.id and f.result == "A")
        or (f.fighter_b_id == fighter.id and f.result == "B")
    )
    return wins / len(past)


def _recent_ko_pct(fighter, before_date: date, n_fights: int, session) -> float | None:
    """KO/TKO rate over the fighter's last *n_fights* completed before *before_date*."""
    from data.db import Fight

    past = (
        session.query(Fight)
        .filter(
            ((Fight.fighter_a_id == fighter.id) | (Fight.fighter_b_id == fighter.id)),
            Fight.is_upcoming == False,  # noqa: E712
            Fight.fight_date < before_date,
            Fight.result.in_(["A", "B"]),
        )
        .order_by(Fight.fight_date.desc())
        .limit(n_fights)
        .all()
    )
    if not past:
        return None
    kos = sum(
        1 for f in past
        if ((f.fighter_a_id == fighter.id and f.result == "A")
            or (f.fighter_b_id == fighter.id and f.result == "B"))
        and (f.method or "").upper() in ("KO", "TKO")
    )
    return kos / len(past)


def _avg_rounds_fought(fighter, before_date: date, session) -> float | None:
    """Average number of rounds this fighter goes per completed fight."""
    from data.db import Fight

    past = (
        session.query(Fight)
        .filter(
            ((Fight.fighter_a_id == fighter.id) | (Fight.fighter_b_id == fighter.id)),
            Fight.is_upcoming == False,  # noqa: E712
            Fight.fight_date < before_date,
            Fight.result.isnot(None),
        )
        .all()
    )
    if not past:
        return None
    rounds: list[int] = []
    for f in past:
        if f.round_ended and f.total_rounds:
            rounds.append(f.round_ended)
        elif f.total_rounds:
            rounds.append(f.total_rounds)
    return float(np.mean(rounds)) if rounds else None


# ─── Main feature builder ─────────────────────────────────────────────────────

def build_features(
    fa, fb, fight_date: date | None, session,
    *, title_fight: bool = False, weight_class: str | None = None,
) -> dict:
    """
    Build the full feature dict for a fight between *fa* and *fb*.

    All directional features are from fighter_a's perspective: a positive
    value means fighter_a has the advantage on that dimension.

    Parameters
    ----------
    fa, fb:
        SQLAlchemy Fighter ORM objects.
    fight_date:
        The date of the fight (used to look up prior-fight history correctly).
        Falls back to today if None.
    session:
        Active SQLAlchemy Session.
    title_fight:
        Whether the bout is a title fight.
    weight_class:
        Weight class of the bout (for encoding).

    Returns
    -------
    dict with keys matching models.logistic_model.FEATURE_COLS (9 keys)
    plus 5 XGBoost extended features.
    """
    today = fight_date or date.today()

    age_diff = _age_diff(fa, fb)

    dslf_a = _days_since_last_fight(fa, today, session)
    dslf_b = _days_since_last_fight(fb, today, session)
    days_diff = (dslf_a - dslf_b) if (dslf_a is not None and dslf_b is not None) else 0.0

    oq_a = _avg_opponent_elo(fa, today, session)
    oq_b = _avg_opponent_elo(fb, today, session)
    oq_diff = (oq_a - oq_b) if (oq_a is not None and oq_b is not None) else 0.0

    # XGBoost extended features
    rwr_a = _rolling_win_rate(fa, today, 3, session)
    rwr_b = _rolling_win_rate(fb, today, 3, session)
    rolling_win_rate_diff = (rwr_a - rwr_b) if (rwr_a is not None and rwr_b is not None) else 0.0

    rko_a = _recent_ko_pct(fa, today, 3, session)
    rko_b = _recent_ko_pct(fb, today, 3, session)
    recent_ko_pct_diff = (rko_a - rko_b) if (rko_a is not None and rko_b is not None) else 0.0

    arf_a = _avg_rounds_fought(fa, today, session)
    arf_b = _avg_rounds_fought(fb, today, session)
    avg_rounds_fought_diff = (arf_a - arf_b) if (arf_a is not None and arf_b is not None) else 0.0

    return {
        # Logistic model features (9)
        "reach_diff":                (fa.reach_cm or 0) - (fb.reach_cm or 0),
        "height_diff":               (fa.height_cm or 0) - (fb.height_cm or 0),
        "age_diff":                  age_diff,
        "win_pct_diff":              _win_pct(fa) - _win_pct(fb),
        "ko_pct_diff":               _ko_pct(fa) - _ko_pct(fb),
        "elo_diff":                  (fa.elo_rating or 1500) - (fb.elo_rating or 1500),
        "days_since_last_fight_diff": days_diff,
        "opposition_quality_diff":   oq_diff,
        "is_southpaw_matchup":       int(
            (fa.stance or "Orthodox").lower() != (fb.stance or "Orthodox").lower()
        ),
        # XGBoost extended features (5)
        "rolling_win_rate_diff":     rolling_win_rate_diff,
        "recent_ko_pct_diff":        recent_ko_pct_diff,
        "avg_rounds_fought_diff":    avg_rounds_fought_diff,
        "title_fight":               int(title_fight),
        "weight_class_encoded":      _encode_weight_class(weight_class),
    }

"""
KnockOutIQ — Elo Rating System
Dynamic fighter strength ratings updated after every fight.

Modifications vs. classic Elo:
- KO/TKO wins award a K-factor bonus
- Recency: K-factor tapers for established fighters
- Separate ratings per weight class supported via fighter_id+weight_class key
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EloResult:
    winner_before: float
    loser_before: float
    winner_after: float
    loser_after: float
    delta: float


class EloSystem:
    """
    Manages Elo ratings for a collection of fighters.

    Usage
    -----
    elo = EloSystem()
    result = elo.record_fight("Fighter A", "Fighter B", winner="Fighter A", method="KO")
    print(result.winner_after)   # Fighter A's new rating
    """

    DEFAULT_RATING = 1500.0

    def __init__(
        self,
        k_base: float = 32.0,
        k_novice_threshold: int = 10,
        k_novice: float = 48.0,
        ko_bonus_pct: float = 0.25,
    ):
        self.k_base = k_base
        self.k_novice_threshold = k_novice_threshold
        self.k_novice = k_novice
        self.ko_bonus_pct = ko_bonus_pct
        self._ratings: dict[str, float] = {}
        self._fight_counts: dict[str, int] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def get_rating(self, fighter: str) -> float:
        return self._ratings.get(fighter, self.DEFAULT_RATING)

    def set_rating(self, fighter: str, rating: float) -> None:
        self._ratings[fighter] = rating

    def record_fight(
        self,
        fighter_a: str,
        fighter_b: str,
        *,
        winner: Optional[str] = None,
        method: str = "UD",
    ) -> EloResult:
        """
        Update ratings after a fight.

        Parameters
        ----------
        fighter_a, fighter_b : str  Fighter names
        winner               : str  Name of winner, or None for draw
        method               : str  'KO', 'TKO', 'UD', 'MD', 'SD', 'DQ', 'draw'
        """
        ra = self.get_rating(fighter_a)
        rb = self.get_rating(fighter_b)

        # Expected scores
        exp_a = 1 / (1 + 10 ** ((rb - ra) / 400))
        exp_b = 1 - exp_a

        # Actual scores
        if winner == fighter_a:
            score_a, score_b = 1.0, 0.0
        elif winner == fighter_b:
            score_a, score_b = 0.0, 1.0
        else:  # draw / NC
            score_a, score_b = 0.5, 0.5

        # K-factor — novice fighters get higher K
        k_a = self._k(fighter_a)
        k_b = self._k(fighter_b)

        # KO bonus
        method_upper = (method or "").upper()
        is_finish = method_upper in ("KO", "TKO", "RTD")
        bonus = self.ko_bonus_pct if is_finish else 0.0

        # New ratings
        delta_a = k_a * ((score_a + bonus) - exp_a)
        delta_b = k_b * ((score_b + bonus) - exp_b)
        new_ra = ra + delta_a
        new_rb = rb + delta_b

        self._ratings[fighter_a] = new_ra
        self._ratings[fighter_b] = new_rb
        self._fight_counts[fighter_a] = self._fight_counts.get(fighter_a, 0) + 1
        self._fight_counts[fighter_b] = self._fight_counts.get(fighter_b, 0) + 1

        return EloResult(
            winner_before=ra if winner == fighter_a else rb,
            loser_before=rb if winner == fighter_a else ra,
            winner_after=new_ra if winner == fighter_a else new_rb,
            loser_after=new_rb if winner == fighter_a else new_ra,
            delta=abs(delta_a),
        )

    def win_probability(self, fighter_a: str, fighter_b: str) -> float:
        """Expected win probability for fighter_a vs fighter_b."""
        ra = self.get_rating(fighter_a)
        rb = self.get_rating(fighter_b)
        return 1 / (1 + 10 ** ((rb - ra) / 400))

    def all_ratings(self) -> dict[str, float]:
        return dict(self._ratings)

    # ── Private ───────────────────────────────────────────────────────────────

    def _k(self, fighter: str) -> float:
        fights = self._fight_counts.get(fighter, 0)
        return self.k_novice if fights < self.k_novice_threshold else self.k_base

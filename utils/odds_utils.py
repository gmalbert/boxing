"""
KnockOutIQ — Odds & Edge Calculation Utilities
"""

from __future__ import annotations

import math
from typing import Optional


# ─── Probability Conversions ──────────────────────────────────────────────────

def american_to_implied_prob(american_odds: int) -> float:
    """Convert American odds to raw implied probability (includes vig)."""
    if american_odds is None:
        return 0.5
    if american_odds > 0:
        return 100 / (american_odds + 100)
    return abs(american_odds) / (abs(american_odds) + 100)


def implied_prob_to_american(prob: float) -> int:
    """Convert a probability to American odds (rounded)."""
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return round(-prob / (1 - prob) * 100)
    return round((1 - prob) / prob * 100)


def american_to_decimal(american_odds: int) -> float:
    """Convert American to decimal (European) odds."""
    if american_odds > 0:
        return (american_odds / 100) + 1.0
    return (100 / abs(american_odds)) + 1.0


def decimal_to_american(decimal_odds: float) -> int:
    """Convert decimal to American odds."""
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


# ─── Vig Removal ──────────────────────────────────────────────────────────────

def remove_vig(prob_a: float, prob_b: float) -> tuple[float, float]:
    """
    Remove the bookmaker's overround (vig) from two implied probabilities.
    Returns fair (no-vig) probabilities.
    """
    total = prob_a + prob_b
    if total <= 0:
        return 0.5, 0.5
    return prob_a / total, prob_b / total


def no_vig_prob_from_american(odds_a: int, odds_b: int) -> tuple[float, float]:
    """Return fair probabilities from two American moneyline odds."""
    raw_a = american_to_implied_prob(odds_a)
    raw_b = american_to_implied_prob(odds_b)
    return remove_vig(raw_a, raw_b)


# ─── Edge Detection ───────────────────────────────────────────────────────────

def calculate_edge(model_prob: float, dk_american_odds: int) -> float:
    """
    Edge = model probability − DK implied probability.
    Positive = model thinks the bet is +EV.
    """
    dk_implied = american_to_implied_prob(dk_american_odds)
    return model_prob - dk_implied


def pinnacle_edge(pinnacle_american: int, dk_american: int) -> float:
    """
    How much better is DK's price than Pinnacle's no-vig line?
    Positive = DK is giving better odds than sharp market implies.
    """
    pin_implied_a, _ = no_vig_prob_from_american(
        pinnacle_american, -pinnacle_american - 10  # rough opponent
    )
    dk_implied = american_to_implied_prob(dk_american)
    return pin_implied_a - dk_implied


# ─── CLV ─────────────────────────────────────────────────────────────────────

def clv(obtained_odds: int, closing_odds: int) -> float:
    """
    Closing Line Value: the difference in implied probabilities between
    the price you got and the closing price.
    Positive CLV = you beat the market (long-run +EV signal).
    """
    obtained_prob = american_to_implied_prob(obtained_odds)
    closing_prob = american_to_implied_prob(closing_odds)
    return closing_prob - obtained_prob


# ─── Kelly Criterion ──────────────────────────────────────────────────────────

def kelly_fraction(model_prob: float, american_odds: int, fraction: float = 0.25) -> float:
    """
    Fractional Kelly stake as a proportion of bankroll.
    `fraction` = 0.25 for quarter Kelly (more conservative).
    Returns recommended stake as % of bankroll.
    """
    b = american_to_decimal(american_odds) - 1  # net odds
    p = model_prob
    q = 1 - p
    k = (b * p - q) / b
    return max(0.0, k * fraction)


# ─── Display Helpers ──────────────────────────────────────────────────────────

def fmt_american(odds: int) -> str:
    """Format American odds with sign."""
    if odds is None:
        return "N/A"
    return f"+{odds}" if odds > 0 else str(odds)


def edge_label(edge: float) -> tuple[str, str]:
    """Return (label, color) for a given edge value."""
    from config import EDGE_STRONG_THRESHOLD, EDGE_WEAK_THRESHOLD
    if edge >= EDGE_STRONG_THRESHOLD:
        return "🟢 Strong Edge", "#1a7a3a"
    elif edge >= EDGE_WEAK_THRESHOLD:
        return "🟡 Marginal Edge", "#8a7a00"
    elif edge >= 0:
        return "⚪ Neutral", "#666666"
    else:
        return "🔴 No Edge", "#7a1a1a"

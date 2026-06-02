"""
tests/test_edge_calculation.py — Edge and implied probability calculation tests
for KnockOutIQ boxing app.
"""

import pytest


# ── Helpers mirroring config.py thresholds ────────────────────────────────────

EDGE_STRONG_THRESHOLD = 0.05  # 5%
EDGE_WEAK_THRESHOLD = 0.02    # 2%


def american_to_implied(american_odds: int) -> float:
    """Convert American odds to implied probability."""
    if american_odds > 0:
        return 100.0 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)


def edge_tier(model_prob: float, dk_implied: float) -> str:
    """Return tier label for the edge between model probability and market."""
    edge = model_prob - dk_implied
    if edge >= EDGE_STRONG_THRESHOLD:
        return "strong"
    if edge >= EDGE_WEAK_THRESHOLD:
        return "marginal"
    return "none"


# ── Implied probability tests ─────────────────────────────────────────────────

class TestAmericanToImplied:

    def test_minus_110(self):
        prob = american_to_implied(-110)
        assert abs(prob - 0.5238) < 0.001

    def test_plus_100(self):
        prob = american_to_implied(100)
        assert abs(prob - 0.5) < 0.001

    def test_minus_200(self):
        prob = american_to_implied(-200)
        assert abs(prob - 0.6667) < 0.001

    def test_plus_200(self):
        prob = american_to_implied(200)
        assert abs(prob - 0.3333) < 0.001

    def test_minus_300_heavy_favourite(self):
        prob = american_to_implied(-300)
        assert prob > 0.70

    def test_plus_500_big_underdog(self):
        prob = american_to_implied(500)
        assert prob < 0.20

    def test_result_always_between_0_and_1(self):
        for odds in [-500, -200, -110, 100, 200, 500]:
            prob = american_to_implied(odds)
            assert 0.0 < prob < 1.0, f"Implied prob {prob} for odds {odds} out of (0,1)"


# ── Edge tier classification tests ───────────────────────────────────────────

class TestEdgeTier:

    def test_strong_edge(self):
        assert edge_tier(0.70, 0.60) == "strong"  # 10% edge

    def test_strong_at_threshold(self):
        assert edge_tier(0.60, 0.55) == "strong"  # exactly 5%

    def test_marginal_edge(self):
        assert edge_tier(0.55, 0.52) == "marginal"  # 3% edge

    def test_marginal_at_lower_threshold(self):
        assert edge_tier(0.52, 0.50) == "marginal"  # exactly 2%

    def test_no_edge_positive(self):
        assert edge_tier(0.51, 0.50) == "none"  # 1% — below weak threshold

    def test_no_edge_negative(self):
        assert edge_tier(0.48, 0.52) == "none"  # negative edge

    def test_zero_edge(self):
        assert edge_tier(0.50, 0.50) == "none"


# ── End-to-end edge calculation ───────────────────────────────────────────────

class TestEndToEndEdge:
    """Given real American odds and a model probability, derive the edge tier."""

    def test_favourite_value_bet(self):
        # DK has -150 (implied 60%), model says 68% → strong edge
        dk_implied = american_to_implied(-150)
        tier = edge_tier(0.68, dk_implied)
        assert tier == "strong"

    def test_underdog_no_value(self):
        # DK has +130 (implied 43.5%), model says 44% → near zero edge
        dk_implied = american_to_implied(130)
        tier = edge_tier(0.44, dk_implied)
        assert tier == "none"

    def test_model_loses_to_market(self):
        # Model says 40%, DK implies 55% → model underestimates favourite
        dk_implied = american_to_implied(-120)
        tier = edge_tier(0.40, dk_implied)
        assert tier == "none"

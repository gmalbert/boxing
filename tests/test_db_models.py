"""
tests/test_db_models.py — ORM model tests for KnockOutIQ boxing app.
"""

import pytest
from datetime import date
from data.db import Fighter, Fight, OddsSnapshot, ModelPrediction


class TestFighterModel:
    """Fighter ORM model correctness."""

    def test_create_fighter(self, session, fighter_a):
        assert fighter_a.id is not None
        assert fighter_a.name == "Canelo Alvarez"

    def test_default_elo(self, session):
        f = Fighter(external_id="f999", name="Unknown Boxer", weight_class="Heavyweight")
        session.add(f)
        session.flush()
        assert f.elo_rating == 1500.0

    def test_fighter_record_totals(self, session, fighter_a):
        total = fighter_a.wins + fighter_a.losses + fighter_a.draws + fighter_a.no_contests
        assert total == 64  # 60 + 2 + 2 + 0

    def test_query_by_external_id(self, session, fighter_a):
        result = session.query(Fighter).filter_by(external_id="f001").first()
        assert result is not None
        assert result.name == "Canelo Alvarez"

    def test_unique_external_id(self, session, fighter_a):
        dup = Fighter(external_id="f001", name="Duplicate", weight_class="Heavyweight")
        session.add(dup)
        with pytest.raises(Exception):
            session.flush()


class TestFightModel:
    """Fight ORM model correctness."""

    def test_create_fight(self, session, sample_fight):
        assert sample_fight.id is not None
        assert sample_fight.is_upcoming is True

    def test_fight_links_fighters(self, session, sample_fight, fighter_a, fighter_b):
        assert sample_fight.fighter_a_id == fighter_a.id
        assert sample_fight.fighter_b_id == fighter_b.id

    def test_query_upcoming_fights(self, session, sample_fight):
        upcoming = session.query(Fight).filter_by(is_upcoming=True).all()
        assert len(upcoming) >= 1

    def test_fight_date_is_date(self, session, sample_fight):
        assert isinstance(sample_fight.fight_date, date)


class TestOddsSnapshotModel:
    """OddsSnapshot ORM model correctness."""

    def test_create_odds_snapshot(self, session, sample_fight, fighter_a):
        snap = OddsSnapshot(
            fight_id=sample_fight.id,
            fighter_name=fighter_a.name,
            bookmaker="DraftKings",
            american_odds=-250,
            decimal_odds=1.40,
        )
        session.add(snap)
        session.flush()
        assert snap.id is not None

    def test_odds_query_by_fight(self, session, sample_fight, fighter_a):
        snap = OddsSnapshot(
            fight_id=sample_fight.id,
            fighter_name=fighter_a.name,
            bookmaker="DraftKings",
            american_odds=-250,
            decimal_odds=1.40,
        )
        session.add(snap)
        session.flush()

        results = session.query(OddsSnapshot).filter_by(fight_id=sample_fight.id).all()
        assert len(results) == 1
        assert results[0].bookmaker == "DraftKings"


class TestModelPredictionModel:
    """ModelPrediction ORM model correctness."""

    def test_create_prediction(self, session, sample_fight, fighter_a, fighter_b):
        pred = ModelPrediction(
            fight_id=sample_fight.id,
            model_version="v1.0",
            fighter_a_name=fighter_a.name,
            fighter_b_name=fighter_b.name,
            fighter_a_win_prob=0.62,
            confidence=0.62,
            method_ko_prob=0.35,
            method_dec_prob=0.27,
        )
        session.add(pred)
        session.flush()
        assert pred.id is not None

    def test_win_prob_in_range(self, session, sample_fight, fighter_a, fighter_b):
        pred = ModelPrediction(
            fight_id=sample_fight.id,
            model_version="v1.0",
            fighter_a_name=fighter_a.name,
            fighter_b_name=fighter_b.name,
            fighter_a_win_prob=0.62,
        )
        session.add(pred)
        session.flush()
        assert 0.0 <= pred.fighter_a_win_prob <= 1.0

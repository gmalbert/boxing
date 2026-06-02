"""
conftest.py — shared fixtures for KnockOutIQ boxing tests.
Uses an in-memory SQLite database so tests never touch the real data file.
"""

import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import ORM from the boxing data layer
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.db import Base, Fighter, Fight, OddsSnapshot, ModelPrediction


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite engine — discarded after the test session."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Provide a transactional session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    sess = Session()
    yield sess
    sess.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def fighter_a(session) -> Fighter:
    f = Fighter(
        external_id="f001",
        name="Canelo Alvarez",
        weight_class="Super Middleweight",
        elo_rating=1800.0,
        wins=60,
        losses=2,
        draws=2,
        no_contests=0,
        ko_wins=39,
        tko_wins=0,
    )
    session.add(f)
    session.flush()
    return f


@pytest.fixture
def fighter_b(session) -> Fighter:
    f = Fighter(
        external_id="f002",
        name="Gennady Golovkin",
        weight_class="Super Middleweight",
        elo_rating=1750.0,
        wins=44,
        losses=3,
        draws=1,
        no_contests=0,
        ko_wins=40,
        tko_wins=0,
    )
    session.add(f)
    session.flush()
    return f


@pytest.fixture
def sample_fight(session, fighter_a, fighter_b) -> Fight:
    fight = Fight(
        fighter_a_id=fighter_a.id,
        fighter_b_id=fighter_b.id,
        fight_date=date(2025, 9, 14),
        weight_class="Super Middleweight",
        is_upcoming=True,
        title_fight=True,
        event_name="Canelo vs GGG 4",
    )
    session.add(fight)
    session.flush()
    return fight

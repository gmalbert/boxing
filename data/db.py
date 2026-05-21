"""
KnockOutIQ — Database Layer (SQLite via SQLAlchemy)

Creates the schema on first run. Provides helper functions for common queries.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    create_engine, text
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from config import DB_URL, DB_PATH


# ─── ORM Base ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─── Models ───────────────────────────────────────────────────────────────────

class Fighter(Base):
    __tablename__ = "fighters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(50), unique=True, index=True)  # boxing-data.com id
    name = Column(String(100), nullable=False, index=True)
    stance = Column(String(20))
    height_cm = Column(Integer)
    reach_cm = Column(Integer)
    birth_date = Column(Date)
    nationality = Column(String(50))
    weight_class = Column(String(50))
    sex = Column(String(1), default='M')  # 'M' = male, 'F' = female
    elo_rating = Column(Float, default=1500.0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    no_contests = Column(Integer, default=0)
    ko_wins = Column(Integer, default=0)
    tko_wins = Column(Integer, default=0)
    style_tag = Column(String(30))  # boxer, brawler, counter-puncher, slugger
    image_url = Column(String(255))
    boxrec_id = Column(String(20), unique=True, index=True)  # BoxRec numeric profile ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Fight(Base):
    __tablename__ = "fights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(50), unique=True, index=True)
    fighter_a_id = Column(Integer, ForeignKey("fighters.id"), nullable=False)
    fighter_b_id = Column(Integer, ForeignKey("fighters.id"), nullable=False)
    fight_date = Column(Date, index=True)
    weight_class = Column(String(50))
    result = Column(String(10))      # 'A', 'B', 'draw', 'NC'
    method = Column(String(20))      # 'KO', 'TKO', 'UD', 'MD', 'SD', 'DQ'
    round_ended = Column(Integer)
    total_rounds = Column(Integer, default=12)
    title_fight = Column(Boolean, default=False)
    sanctioning_body = Column(String(50))
    venue = Column(String(150))
    location = Column(String(150))
    is_upcoming = Column(Boolean, default=False)
    event_name = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)


class FightStats(Base):
    __tablename__ = "fight_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fight_id = Column(Integer, ForeignKey("fights.id"), nullable=False)
    fighter_id = Column(Integer, ForeignKey("fighters.id"), nullable=False)
    total_punches_thrown = Column(Integer)
    total_punches_landed = Column(Integer)
    jabs_thrown = Column(Integer)
    jabs_landed = Column(Integer)
    power_thrown = Column(Integer)
    power_landed = Column(Integer)
    knockdowns_scored = Column(Integer, default=0)
    knockdowns_suffered = Column(Integer, default=0)
    rounds_data = Column(Text)  # JSON: list of per-round stats


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fight_id = Column(Integer, ForeignKey("fights.id"))
    external_fight_id = Column(String(100), index=True)  # Odds API event id
    fighter_name = Column(String(100))
    bookmaker = Column(String(30))
    american_odds = Column(Integer)
    decimal_odds = Column(Float)
    snapshot_time = Column(DateTime, default=datetime.utcnow, index=True)


class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fight_id = Column(Integer, ForeignKey("fights.id"))
    model_version = Column(String(20))
    fighter_a_name = Column(String(100))
    fighter_b_name = Column(String(100))
    fighter_a_win_prob = Column(Float)
    confidence = Column(Float)
    method_ko_prob = Column(Float)
    method_dec_prob = Column(Float)
    predicted_at = Column(DateTime, default=datetime.utcnow)


class BetLog(Base):
    __tablename__ = "bet_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fight_id = Column(Integer, ForeignKey("fights.id"))
    fighter_name = Column(String(100))
    bookmaker = Column(String(30), default="draftkings")
    american_odds_obtained = Column(Integer)
    stake_units = Column(Float)
    model_prob_at_time = Column(Float)
    closing_odds = Column(Integer)
    clv = Column(Float)
    result = Column(String(10))  # 'win', 'loss', 'push', 'pending'
    notes = Column(Text)
    placed_at = Column(DateTime, default=datetime.utcnow)


class EloHistory(Base):
    __tablename__ = "elo_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fighter_id = Column(Integer, ForeignKey("fighters.id"), nullable=False)
    fight_id = Column(Integer, ForeignKey("fights.id"))
    elo_before = Column(Float)
    elo_after = Column(Float)
    recorded_at = Column(DateTime, default=datetime.utcnow)


# ─── Engine & Session ─────────────────────────────────────────────────────────

def get_engine():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


# ─── Helper Queries ───────────────────────────────────────────────────────────

def get_all_fighters(session: Session) -> list[Fighter]:
    return session.query(Fighter).order_by(Fighter.name).all()


def get_fighter_by_name(session: Session, name: str) -> Fighter | None:
    return (
        session.query(Fighter)
        .filter(Fighter.name.ilike(f"%{name}%"))
        .first()
    )


def get_upcoming_fights(session: Session) -> list[Fight]:
    today = date.today()
    return (
        session.query(Fight)
        .filter(Fight.fight_date >= today, Fight.is_upcoming == True)
        .order_by(Fight.fight_date)
        .all()
    )


def get_fighter_fights(session: Session, fighter_id: int) -> list[Fight]:
    return (
        session.query(Fight)
        .filter(
            (Fight.fighter_a_id == fighter_id) | (Fight.fighter_b_id == fighter_id),
            Fight.is_upcoming == False,
        )
        .order_by(Fight.fight_date.desc())
        .all()
    )


def get_elo_history(session: Session, fighter_id: int) -> list[EloHistory]:
    return (
        session.query(EloHistory)
        .filter(EloHistory.fighter_id == fighter_id)
        .order_by(EloHistory.recorded_at)
        .all()
    )


def get_odds_history(session: Session, fight_id: int) -> list[OddsSnapshot]:
    return (
        session.query(OddsSnapshot)
        .filter(OddsSnapshot.fight_id == fight_id)
        .order_by(OddsSnapshot.snapshot_time)
        .all()
    )

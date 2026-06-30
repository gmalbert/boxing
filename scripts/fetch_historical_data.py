"""
KnockOutIQ — Data Fetch & Seed Script
======================================
Populates the SQLite database with:
  • ~80 notable historical fights (2016-2026) via embedded seed data
  • 52 upcoming fights pulled live from The Odds API
  • Current moneylines from The Odds API bookmakers
  • Elo ratings recalculated from all historical fights

Usage:
    python scripts/fetch_historical_data.py backfill   # full seed + live data
    python scripts/fetch_historical_data.py daily      # odds refresh only
    python scripts/fetch_historical_data.py weekly     # odds + Elo recalc
"""

from __future__ import annotations

import re
import sys
import time
import logging
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from sqlalchemy.orm import Session

from config import ODDS_API_KEY
from data.db import (
    Fighter, Fight, OddsSnapshot, EloHistory,
    get_engine, get_session,
)
from models.elo import EloSystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Seed Data ────────────────────────────────────────────────────────────────
# Format: (name, weight_class, wins, losses, draws, no_contests, ko_wins,
#          height_cm, reach_cm, stance, birth_year, birth_month, birth_day)

SEED_FIGHTERS: list[tuple] = [
    # Heavyweight
    ("Tyson Fury",           "Heavyweight", 34,  0, 1, 0, 24, 208, 216, "orthodox",  1988,  8, 12),
    ("Oleksandr Usyk",       "Heavyweight", 22,  2, 0, 0, 14, 193, 198, "southpaw",  1987,  1, 17),
    ("Anthony Joshua",       "Heavyweight", 27,  4, 0, 0, 24, 198, 208, "orthodox",  1989, 10, 15),
    ("Deontay Wilder",       "Heavyweight", 43,  3, 1, 0, 42, 206, 211, "orthodox",  1985, 10, 22),
    ("Andy Ruiz Jr",         "Heavyweight", 36,  2, 1, 0, 22, 188, 188, "orthodox",  1989,  9, 11),
    ("Wladimir Klitschko",   "Heavyweight", 64,  5, 0, 0, 53, 198, 198, "orthodox",  1976,  3, 25),
    ("Dillian Whyte",        "Heavyweight", 30,  4, 0, 0, 23, 193, 193, "orthodox",  1988,  4, 11),
    ("Alexander Povetkin",   "Heavyweight", 37,  3, 1, 0, 26, 191, 191, "orthodox",  1979,  9,  2),
    ("Joseph Parker",        "Heavyweight", 34,  4, 0, 0, 23, 198, 203, "orthodox",  1992,  1,  9),
    ("Daniel Dubois",        "Heavyweight", 22,  2, 0, 0, 21, 198, 203, "orthodox",  1997,  7,  5),
    ("Dereck Chisora",       "Heavyweight", 34, 14, 0, 0, 23, 188, 188, "orthodox",  1983, 12, 29),
    ("Kubrat Pulev",         "Heavyweight", 29,  3, 0, 0, 14, 198, 193, "orthodox",  1981,  5,  4),
    ("Luis Ortiz",           "Heavyweight", 33,  3, 0, 0, 28, 193, 196, "southpaw",  1979,  3, 23),
    ("Artur Szpilka",        "Heavyweight", 20,  6, 1, 0,  9, 188, 193, "southpaw",  1987,  9,  8),
    ("Gerald Washington",    "Heavyweight", 19,  4, 1, 0, 12, 196, 198, "orthodox",  1982, 11,  4),
    ("Chazz Witherspoon",    "Heavyweight", 36, 15, 0, 0, 25, 196, 201, "orthodox",  1975,  9, 22),
    ("Zhilei Zhang",         "Heavyweight", 28,  2, 1, 0, 23, 203, 208, "southpaw",  1983,  8, 22),
    ("Filip Hrgovic",        "Heavyweight", 18,  1, 0, 0, 14, 198, 198, "orthodox",  1992,  2, 14),
    ("Francis Ngannou",      "Heavyweight",  1,  1, 0, 0,  1, 193, 196, "orthodox",  1986,  9,  5),
    # Cruiserweight
    ("Mairis Briedis",       "Cruiserweight", 30,  2, 0, 0, 21, 185, 193, "orthodox",  1984,  1, 17),
    ("Murat Gassiev",        "Cruiserweight", 19,  1, 0, 0, 13, 188, 191, "orthodox",  1993,  2,  9),
    ("Yuniel Dorticos",      "Cruiserweight", 25,  2, 0, 0, 23, 185, 183, "orthodox",  1989,  8,  3),
    ("Lawrence Okolie",      "Cruiserweight", 19,  2, 0, 0, 16, 193, 198, "orthodox",  1992, 12, 14),
    # Light Heavyweight
    ("Artur Beterbiev",      "Light Heavyweight", 20,  0, 0, 0, 20, 183, 188, "orthodox",  1985,  1, 22),
    ("Dmitry Bivol",         "Light Heavyweight", 22,  0, 0, 0, 11, 183, 185, "orthodox",  1990, 12, 18),
    ("Sergey Kovalev",       "Light Heavyweight", 35,  5, 1, 0, 29, 183, 183, "orthodox",  1983,  4,  2),
    ("Joe Smith Jr",         "Light Heavyweight", 29,  5, 0, 0, 24, 180, 183, "orthodox",  1989,  6, 16),
    ("Callum Johnson",       "Light Heavyweight", 21,  4, 0, 0, 15, 185, 191, "orthodox",  1987,  5, 29),
    # Super Middleweight
    ("Saul Alvarez",         "Super Middleweight", 62,  2, 2, 0, 39, 175, 179, "orthodox",  1990,  7, 18),
    ("David Benavidez",      "Super Middleweight", 28,  0, 0, 0, 24, 180, 178, "orthodox",  1996, 12, 17),
    ("Caleb Plant",          "Super Middleweight", 24,  2, 0, 0, 14, 183, 188, "orthodox",  1992,  7,  8),
    ("Billy Joe Saunders",   "Super Middleweight", 30,  1, 0, 0, 14, 183, 185, "southpaw",  1989,  9, 30),
    ("Callum Smith",         "Super Middleweight", 30,  2, 0, 0, 22, 196, 201, "orthodox",  1990,  9, 13),
    ("Rocky Fielding",       "Super Middleweight", 28,  4, 0, 0, 20, 188, 188, "orthodox",  1987,  3,  5),
    ("Edgar Berlanga",       "Super Middleweight", 22,  1, 0, 0, 18, 185, 188, "orthodox",  1997,  8, 26),
    ("Chris Eubank Jr",      "Super Middleweight", 34,  5, 0, 0, 25, 183, 185, "orthodox",  1989,  9, 18),
    ("John Ryder",           "Super Middleweight", 32,  6, 0, 0, 18, 175, 180, "orthodox",  1988,  4,  1),
    ("Jaime Munguia",        "Super Middleweight", 43,  1, 0, 0, 34, 183, 183, "orthodox",  1996,  8, 28),
    # Middleweight
    ("Gennady Golovkin",     "Middleweight", 44,  2, 1, 0, 38, 178, 178, "orthodox",  1982,  4,  8),
    ("Jermall Charlo",       "Middleweight", 34,  2, 0, 0, 18, 180, 183, "orthodox",  1990,  5, 22),
    ("Daniel Jacobs",        "Middleweight", 37,  4, 0, 0, 30, 180, 183, "orthodox",  1987,  2, 10),
    ("Demetrius Andrade",    "Middleweight", 32,  0, 0, 0, 19, 183, 185, "southpaw",  1988,  1, 26),
    ("Ryota Murata",         "Middleweight", 16,  2, 0, 0, 13, 180, 180, "orthodox",  1985,  5, 12),
    ("Steve Rolls",          "Middleweight", 19,  2, 0, 0,  9, 183, 183, "orthodox",  1983,  7, 22),
    # Super Welterweight (154)
    ("Jermell Charlo",       "Super Welterweight", 36,  2, 1, 0, 19, 178, 183, "southpaw",  1990,  5, 22),
    ("Brian Castano",        "Super Welterweight", 17,  2, 2, 0, 12, 175, 183, "southpaw",  1989,  9, 23),
    ("Tony Harrison",        "Super Welterweight", 28,  4, 1, 0, 21, 183, 185, "orthodox",  1989,  2, 28),
    ("Tim Tszyu",            "Super Welterweight", 24,  1, 0, 0, 17, 178, 180, "orthodox",  1994,  6,  5),
    ("Sebastian Fundora",    "Super Welterweight", 22,  1, 1, 0, 14, 193, 198, "orthodox",  1998, 12,  6),
    ("Erislandy Lara",       "Super Welterweight", 30,  4, 3, 0, 17, 178, 180, "southpaw",  1982,  9, 30),
    ("Israil Madrimov",      "Super Welterweight", 10,  1, 0, 0,  7, 180, 183, "orthodox",  1997,  1, 27),
    # Welterweight (147)
    ("Terence Crawford",     "Welterweight", 40,  0, 0, 0, 31, 175, 188, "switch",    1987,  9, 28),
    ("Errol Spence Jr",      "Welterweight", 28,  2, 0, 0, 22, 180, 183, "southpaw",  1990,  1,  3),
    ("Manny Pacquiao",       "Welterweight", 62,  8, 2, 0, 39, 168, 170, "southpaw",  1978, 12, 17),
    ("Keith Thurman",        "Welterweight", 22,  2, 1, 0, 11, 180, 185, "orthodox",  1988, 11, 28),
    ("Danny Garcia",         "Welterweight", 36,  4, 0, 0, 21, 178, 178, "orthodox",  1988, 10, 20),
    ("Shawn Porter",         "Welterweight", 31,  4, 1, 0, 17, 175, 173, "orthodox",  1987,  1, 17),
    ("Yordenis Ugas",        "Welterweight", 28,  5, 0, 0, 12, 180, 183, "orthodox",  1986,  1,  3),
    ("Jaron Ennis",          "Welterweight", 31,  0, 0, 0, 28, 183, 185, "southpaw",  1997, 10, 16),
    ("Vergil Ortiz Jr",      "Welterweight", 21,  0, 0, 0, 21, 180, 178, "orthodox",  1998, 11,  8),
    ("Jeff Horn",            "Welterweight", 21,  4, 1, 0, 11, 180, 180, "orthodox",  1988,  4, 25),
    ("Kell Brook",           "Welterweight", 40,  4, 0, 0, 28, 178, 178, "orthodox",  1986,  5,  3),
    ("David Avanesyan",      "Welterweight", 30,  4, 1, 0, 17, 178, 178, "orthodox",  1987,  8,  5),
    # Super Lightweight (140)
    ("Josh Taylor",          "Super Lightweight", 21,  2, 0, 0, 14, 180, 185, "orthodox",  1990,  1,  2),
    ("Jose Ramirez",         "Super Lightweight", 29,  2, 0, 0, 18, 180, 180, "orthodox",  1993,  2,  9),
    ("Ivan Baranchyk",       "Super Lightweight", 21,  5, 0, 0, 20, 178, 173, "orthodox",  1992, 11, 17),
    ("Regis Prograis",       "Super Lightweight", 28,  2, 0, 0, 24, 173, 173, "southpaw",  1989,  4, 24),
    ("Jack Catterall",       "Super Lightweight", 27,  1, 0, 0, 13, 178, 183, "southpaw",  1993, 11, 22),
    ("Arnold Barboza Jr",    "Super Lightweight", 30,  0, 0, 0, 10, 173, 178, "orthodox",  1993,  1,  4),
    # Lightweight (135)
    ("Devin Haney",          "Lightweight", 31,  2, 0, 0, 15, 173, 183, "orthodox",  1998, 11, 17),
    ("Vasyl Lomachenko",     "Lightweight", 20,  4, 0, 0, 14, 168, 170, "southpaw",  1988,  2, 17),
    ("Gervonta Davis",       "Lightweight", 30,  0, 0, 0, 28, 168, 170, "southpaw",  1994, 11, 27),
    ("Ryan Garcia",          "Lightweight", 24,  1, 0, 0, 20, 178, 178, "orthodox",  1998,  8,  8),
    ("George Kambosos Jr",   "Lightweight", 21,  3, 0, 0, 11, 175, 175, "orthodox",  1993,  9,  5),
    ("Teofimo Lopez",        "Lightweight", 18,  2, 0, 0, 13, 173, 173, "orthodox",  1997,  7, 30),
    ("Luke Campbell",        "Lightweight", 20,  4, 0, 0, 16, 175, 175, "orthodox",  1987,  9, 27),
    ("Richard Commey",       "Lightweight", 30,  5, 0, 0, 26, 170, 173, "orthodox",  1986, 11, 25),
    # Super Featherweight (130)
    ("Shakur Stevenson",     "Super Featherweight", 22,  1, 0, 0, 10, 173, 180, "southpaw",  1997,  6, 28),
    ("Oscar Valdez",         "Super Featherweight", 32,  2, 0, 0, 24, 170, 168, "orthodox",  1990, 10,  3),
    # Featherweight (126)
    ("Emanuel Navarrete",    "Featherweight", 38,  2, 1, 0, 32, 180, 180, "orthodox",  1995,  5, 10),
    ("Josh Warrington",      "Featherweight", 33,  2, 1, 0,  7, 168, 165, "orthodox",  1990,  5, 13),
    ("Kid Galahad",          "Featherweight", 28,  4, 0, 0, 17, 170, 170, "orthodox",  1988,  3, 27),
    ("Stephen Fulton Jr",    "Super Bantamweight", 21,  2, 0, 0,  8, 170, 173, "orthodox",  1994,  4,  9),
    # Bantamweight / Super Bantamweight
    ("Naoya Inoue",          "Super Bantamweight", 28,  0, 0, 0, 25, 165, 178, "orthodox",  1993,  9, 10),
    ("Nonito Donaire",       "Bantamweight",       43,  8, 0, 0, 28, 165, 180, "orthodox",  1982, 11, 16),
    ("Emmanuel Rodriguez",   "Bantamweight",       21,  2, 0, 0, 13, 165, 168, "orthodox",  1993,  6, 14),
    ("Marlon Tapales",       "Super Bantamweight", 37,  4, 1, 0, 19, 165, 168, "orthodox",  1990,  6, 18),
    ("Luis Nery",            "Super Bantamweight", 35,  2, 0, 0, 27, 163, 168, "orthodox",  1994,  1, 19),
    ("Paul Butler",          "Bantamweight",       34,  4, 0, 0,  6, 163, 163, "orthodox",  1988,  8, 13),
]

# Format: (ext_id, date, fighter_a_name, fighter_b_name, weight_class,
#           result, method, round_ended, total_rounds, title_fight,
#           sanctioning_body, venue, location, event_name)
# result: 'A' = fighter_a wins, 'B' = fighter_b wins, 'draw' = draw

SEED_FIGHTS: list[tuple] = [
    # ── Heavyweight ──────────────────────────────────────────────────────────
    ("s001","2016-03-19","Deontay Wilder",    "Artur Szpilka",      "Heavyweight","A","KO",  9,12,True, "WBC",          "Barclays Center",          "Brooklyn, NY",        "Wilder vs Szpilka"),
    ("s002","2017-01-14","Deontay Wilder",    "Gerald Washington",  "Heavyweight","A","TKO", 5,12,True, "WBC",          "Legacy Arena",             "Birmingham, AL",      "Wilder vs Washington"),
    ("s003","2017-04-29","Anthony Joshua",    "Wladimir Klitschko", "Heavyweight","A","TKO",11,12,True, "IBF/WBA",      "Wembley Stadium",          "London, England",     "Joshua vs Klitschko"),
    ("s004","2018-01-27","Oleksandr Usyk",    "Mairis Briedis",     "Cruiserweight","A","UD",12,12,True,"WBA/IBF/WBO/WBC","Hamburg Arena",          "Hamburg, Germany",    "WBSS Cruiserweight Final"),
    ("s005","2018-03-03","Deontay Wilder",    "Luis Ortiz",         "Heavyweight","A","TKO",10,12,True, "WBC",          "Barclays Center",          "Brooklyn, NY",        "Wilder vs Ortiz I"),
    ("s006","2018-03-31","Anthony Joshua",    "Joseph Parker",      "Heavyweight","A","UD", 12,12,True, "IBF/WBA/WBO",  "Principality Stadium",     "Cardiff, Wales",      "Joshua vs Parker"),
    ("s007","2018-07-21","Oleksandr Usyk",    "Murat Gassiev",      "Cruiserweight","A","UD",12,12,True,"WBA/IBF/WBO/WBC","Olympic Stadium",         "Moscow, Russia",      "WBSS Cruiserweight Final II"),
    ("s008","2018-09-15","Gennady Golovkin",  "Saul Alvarez",       "Middleweight","B","MD", 12,12,True, "WBC/WBA/IBF",  "T-Mobile Arena",           "Las Vegas, NV",       "GGG vs Canelo II"),
    ("s009","2018-09-22","Anthony Joshua",    "Alexander Povetkin", "Heavyweight","A","KO",  7,12,True, "IBF/WBA/WBO",  "Wembley Stadium",          "London, England",     "Joshua vs Povetkin"),
    ("s010","2018-09-22","Errol Spence Jr",   "Danny Garcia",       "Welterweight","A","UD", 12,12,True, "IBF",          "AT&T Stadium",             "Arlington, TX",       "Spence vs Garcia"),
    ("s011","2018-12-01","Deontay Wilder",    "Tyson Fury",         "Heavyweight","draw","SD",12,12,True,"WBC",          "Staples Center",           "Los Angeles, CA",     "Wilder vs Fury I"),
    ("s012","2018-12-22","Tony Harrison",     "Jermell Charlo",     "Super Welterweight","B","UD",12,12,True,"WBC",      "Barclays Center",          "Brooklyn, NY",        "Harrison vs Charlo I"),
    ("s013","2019-03-16","Keith Thurman",     "Shawn Porter",       "Welterweight","A","MD", 12,12,True, "WBA",          "Barclays Center",          "Brooklyn, NY",        "Thurman vs Porter"),
    ("s014","2019-05-18","Naoya Inoue",       "Emmanuel Rodriguez", "Bantamweight","A","TKO", 3,12,True, "WBC/WBO/IBF",  "SSE Hydro",                "Glasgow, Scotland",   "WBSS Bantam Semifinal"),
    ("s015","2019-06-01","Andy Ruiz Jr",      "Anthony Joshua",     "Heavyweight","A","TKO", 7,12,True, "IBF/WBA/WBO",  "Madison Square Garden",    "New York, NY",        "Ruiz vs Joshua I"),
    ("s016","2019-06-08","Gennady Golovkin",  "Steve Rolls",        "Middleweight","A","KO",  4,12,False,None,          "Madison Square Garden",    "New York, NY",        "GGG vs Rolls"),
    ("s017","2019-06-23","Jermell Charlo",    "Tony Harrison",      "Super Welterweight","A","KO",9,12,True,"WBC",       "NRG Arena",                "Houston, TX",         "Charlo vs Harrison II"),
    ("s018","2019-07-20","Manny Pacquiao",    "Keith Thurman",      "Welterweight","A","SD", 12,12,True, "WBA",          "MGM Grand Garden",         "Las Vegas, NV",       "Pacquiao vs Thurman"),
    ("s019","2019-10-26","Josh Taylor",       "Regis Prograis",     "Super Lightweight","A","MD",12,12,True,"WBC/WBA/IBF/WBO","SSE Hydro",            "Glasgow, Scotland",   "WBSS Super Lightweight Final"),
    ("s020","2019-11-02","Sergey Kovalev",    "Saul Alvarez",       "Light Heavyweight","B","KO",11,12,True,"WBO",        "MGM Grand Garden",         "Las Vegas, NV",       "Kovalev vs Canelo"),
    ("s021","2019-11-07","Naoya Inoue",       "Nonito Donaire",     "Bantamweight","A","MD", 12,12,True, "WBC/WBO/IBF/WBA","Saitama Super Arena",    "Saitama, Japan",      "WBSS Bantam Final"),
    ("s022","2019-11-23","Deontay Wilder",    "Luis Ortiz",         "Heavyweight","A","KO",  7,12,True, "WBC",          "MGM Grand Garden",         "Las Vegas, NV",       "Wilder vs Ortiz II"),
    ("s023","2019-12-07","Anthony Joshua",    "Andy Ruiz Jr",       "Heavyweight","A","UD", 12,12,True, "IBF/WBA/WBO",  "Diriyah Arena",            "Riyadh, Saudi Arabia","Joshua vs Ruiz II"),
    ("s024","2020-02-22","Tyson Fury",        "Deontay Wilder",     "Heavyweight","A","TKO", 7,12,True, "WBC",          "MGM Grand Garden",         "Las Vegas, NV",       "Fury vs Wilder II"),
    ("s025","2020-08-22","Alexander Povetkin","Dillian Whyte",      "Heavyweight","A","KO",  5,12,False,"WBC interim",  "Fight Camp",               "Brentwood, England",  "Povetkin vs Whyte I"),
    ("s026","2020-09-26","Terence Crawford",  "Kell Brook",         "Welterweight","A","TKO", 4,12,True, "WBO",          "MGM Grand Garden",         "Las Vegas, NV",       "Crawford vs Brook"),
    ("s027","2020-12-05","Errol Spence Jr",   "Danny Garcia",       "Welterweight","A","UD", 12,12,True, "IBF/WBC",      "AT&T Stadium",             "Arlington, TX",       "Spence vs Garcia II"),
    ("s028","2020-12-12","Anthony Joshua",    "Kubrat Pulev",       "Heavyweight","A","KO",  9,12,True, "IBF/WBA/WBO",  "SSE Wembley Arena",        "London, England",     "Joshua vs Pulev"),
    ("s029","2020-12-19","Saul Alvarez",      "Callum Smith",       "Super Middleweight","A","UD",12,12,True,"WBA/WBC",  "Alamodome",                "San Antonio, TX",     "Canelo vs Callum Smith"),
    ("s030","2021-03-27","Dillian Whyte",     "Alexander Povetkin", "Heavyweight","A","TKO", 4,12,False,"WBC interim",  "Wembley Arena",            "London, England",     "Whyte vs Povetkin II"),
    ("s031","2021-05-08","Saul Alvarez",      "Billy Joe Saunders", "Super Middleweight","A","TKO",8,12,True,"WBA/WBC/WBO","AT&T Stadium",           "Arlington, TX",       "Canelo vs Saunders"),
    ("s032","2021-05-21","Josh Taylor",       "Jose Ramirez",       "Super Lightweight","A","UD",12,12,True,"WBC/WBA/IBF/WBO","Visa Pavilion",        "Las Vegas, NV",       "Taylor vs Ramirez"),
    ("s033","2021-07-17","Jermell Charlo",    "Brian Castano",      "Super Welterweight","draw","SD",12,12,True,"WBC/WBA/IBF/WBO","AT&T Center","San Antonio, TX",     "Charlo vs Castano I"),
    ("s034","2021-09-25","Anthony Joshua",    "Oleksandr Usyk",     "Heavyweight","B","UD", 12,12,True, "IBF/WBA/WBO",  "Tottenham Hotspur Stadium","London, England",     "Joshua vs Usyk I"),
    ("s035","2021-10-09","Tyson Fury",        "Deontay Wilder",     "Heavyweight","A","KO", 11,12,True, "WBC",          "T-Mobile Arena",           "Las Vegas, NV",       "Fury vs Wilder III"),
    ("s036","2021-11-06","Saul Alvarez",      "Caleb Plant",        "Super Middleweight","A","TKO",11,12,True,"WBA/WBC/IBF","MGM Grand Garden",      "Las Vegas, NV",       "Canelo vs Plant"),
    ("s037","2021-11-27","George Kambosos Jr","Teofimo Lopez",      "Lightweight","A","SD", 12,12,True, "WBA/WBC/IBF/WBO","Madison Square Garden", "New York, NY",        "Kambosos vs Lopez"),
    ("s038","2021-11-20","Terence Crawford",  "Shawn Porter",       "Welterweight","A","TKO",10,12,True, "WBO",          "Michelob Ultra Arena",     "Las Vegas, NV",       "Crawford vs Porter"),
    ("s039","2022-04-09","Gennady Golovkin",  "Ryota Murata",       "Middleweight","A","TKO", 2,12,True, "WBC/WBA/IBF/WBO","Saitama Super Arena",   "Saitama, Japan",      "GGG vs Murata"),
    ("s040","2022-05-07","Dmitry Bivol",      "Saul Alvarez",       "Light Heavyweight","A","UD",12,12,True,"WBA",        "T-Mobile Arena",           "Las Vegas, NV",       "Bivol vs Canelo"),
    ("s041","2022-05-14","Jermell Charlo",    "Brian Castano",      "Super Welterweight","A","UD",12,12,True,"WBC/WBA/IBF/WBO","AT&T Center",         "San Antonio, TX",     "Charlo vs Castano II"),
    ("s042","2022-06-05","Devin Haney",       "George Kambosos Jr", "Lightweight","A","UD", 12,12,True, "WBC/WBA/IBF/WBO","Marvel Stadium",         "Melbourne, Australia","Haney vs Kambosos I"),
    ("s043","2022-06-07","Naoya Inoue",       "Nonito Donaire",     "Bantamweight","A","TKO", 8,12,True, "WBA/IBF",      "Ota-City General Gymnasium","Tokyo, Japan",      "Inoue vs Donaire II"),
    ("s044","2022-06-18","Artur Beterbiev",   "Joe Smith Jr",       "Light Heavyweight","A","TKO",2,12,True,"WBC/IBF/WBO","Madison Square Garden",  "New York, NY",        "Beterbiev vs Smith"),
    ("s045","2022-08-20","Oleksandr Usyk",    "Anthony Joshua",     "Heavyweight","A","SD", 12,12,True, "WBA/WBO/IBF/IBO","Jeddah Superdome",       "Jeddah, Saudi Arabia","Usyk vs Joshua II"),
    ("s046","2022-09-17","Saul Alvarez",      "Gennady Golovkin",   "Super Middleweight","A","UD",12,12,True,"WBA/WBC/IBF","T-Mobile Arena",         "Las Vegas, NV",       "Canelo vs GGG III"),
    ("s047","2022-10-15","Tyson Fury",        "Dereck Chisora",     "Heavyweight","A","TKO",10,12,True, "WBC",          "Principality Stadium",     "Cardiff, Wales",      "Fury vs Chisora III"),
    ("s048","2022-10-15","Devin Haney",       "George Kambosos Jr", "Lightweight","A","UD", 12,12,True, "WBC/WBA/IBF/WBO","Rod Laver Arena",        "Melbourne, Australia","Haney vs Kambosos II"),
    ("s049","2022-10-29","Artur Beterbiev",   "Callum Johnson",     "Light Heavyweight","A","KO",4, 12,True,"WBC/IBF/WBO","Credit Union 1 Arena",   "Chicago, IL",         "Beterbiev vs Johnson"),
    ("s050","2022-12-17","Naoya Inoue",       "Paul Butler",        "Bantamweight","A","TKO", 3,12,True, "WBA/WBC/IBF/WBO","Ariake Arena",          "Tokyo, Japan",        "Inoue vs Butler"),
    ("s051","2023-03-25","David Benavidez",   "Demetrius Andrade",  "Super Middleweight","A","UD",12,12,False,"WBC interim","MGM National Harbor",   "Oxon Hill, MD",       "Benavidez vs Andrade"),
    ("s052","2023-04-22","Gervonta Davis",    "Ryan Garcia",        "Lightweight","A","KO",  7,12,False,None,           "T-Mobile Arena",           "Las Vegas, NV",       "Davis vs Garcia"),
    ("s053","2023-05-06","Saul Alvarez",      "John Ryder",         "Super Middleweight","A","UD",12,12,True,"WBA/WBC/IBF","Estadio Akron",          "Guadalajara, Mexico", "Canelo vs Ryder"),
    ("s054","2023-07-25","Naoya Inoue",       "Stephen Fulton Jr",  "Super Bantamweight","A","TKO",8,12,True,"WBA/WBC/IBF/WBO","Ariake Arena",       "Tokyo, Japan",        "Inoue vs Fulton"),
    ("s055","2023-09-30","Vasyl Lomachenko",  "Devin Haney",        "Lightweight","B","SD", 12,12,True, "WBA/WBC/IBF/WBO","MGM Grand Garden",       "Las Vegas, NV",       "Lomachenko vs Haney"),
    ("s056","2023-09-30","Saul Alvarez",      "Jermell Charlo",     "Super Middleweight","A","UD",12,12,True,"WBA/WBC/IBF","T-Mobile Arena",         "Las Vegas, NV",       "Canelo vs Charlo"),
    ("s057","2023-10-28","Tyson Fury",        "Francis Ngannou",    "Heavyweight","A","SD", 10,10,False,None,           "Boulevard Hall",           "Riyadh, Saudi Arabia","Fury vs Ngannou"),
    ("s058","2023-12-26","Naoya Inoue",       "Marlon Tapales",     "Super Bantamweight","A","KO",10,12,True,"WBA/WBC/IBF/WBO","Ariake Arena",       "Tokyo, Japan",        "Inoue vs Tapales"),
    ("s059","2024-01-27","Jaron Ennis",       "David Avanesyan",    "Welterweight","A","KO",  3,12,False,None,          "Wells Fargo Center",       "Philadelphia, PA",    "Ennis vs Avanesyan"),
    ("s060","2024-05-04","Saul Alvarez",      "Jaime Munguia",      "Super Middleweight","A","UD",12,12,True,"WBA/WBC/IBF","T-Mobile Arena",         "Las Vegas, NV",       "Canelo vs Munguia"),
    ("s061","2024-05-06","Naoya Inoue",       "Luis Nery",          "Super Bantamweight","A","KO",6, 12,True,"WBA/WBC/IBF/WBO","Ariake Arena",       "Tokyo, Japan",        "Inoue vs Nery"),
    ("s062","2024-05-18","Oleksandr Usyk",    "Tyson Fury",         "Heavyweight","A","SD", 12,12,True, "WBA/WBC/IBF/WBO","Kingdom Arena",          "Riyadh, Saudi Arabia","Usyk vs Fury I"),
    ("s063","2024-07-27","Terence Crawford",  "Israil Madrimov",    "Super Welterweight","A","TKO",9,12,True,"WBA",      "Crypto.com Arena",         "Los Angeles, CA",     "Crawford vs Madrimov"),
    ("s064","2024-08-03","Jack Catterall",    "Josh Taylor",        "Super Lightweight","A","UD",12,12,True,"WBC/IBF/WBO","First Direct Arena",     "Leeds, England",      "Catterall vs Taylor II"),
    ("s065","2024-09-14","Saul Alvarez",      "Edgar Berlanga",     "Super Middleweight","A","UD",12,12,True,"WBA/WBC/IBF","T-Mobile Arena",         "Las Vegas, NV",       "Canelo vs Berlanga"),
    ("s066","2024-09-21","Daniel Dubois",     "Anthony Joshua",     "Heavyweight","A","KO",  5,12,True, "IBF",          "Wembley Stadium",          "London, England",     "Dubois vs Joshua"),
    ("s067","2024-10-12","Artur Beterbiev",   "Dmitry Bivol",       "Light Heavyweight","A","MD",12,12,True,"WBC/IBF/WBO/WBA","Kingdom Arena",       "Riyadh, Saudi Arabia","Beterbiev vs Bivol"),
    ("s068","2024-12-21","Tyson Fury",        "Oleksandr Usyk",     "A","MD",     12,12,True, "Heavyweight",  "WBA/WBC/IBF/WBO",          "Kingdom Arena",       "Riyadh, Saudi Arabia"),  # wrong order — fixed below
    # Earlier milestone fights
    ("s069","2017-05-20","Jeff Horn",         "Manny Pacquiao",     "Welterweight","A","UD", 12,12,True, "WBO",          "Suncorp Stadium",          "Brisbane, Australia", "Horn vs Pacquiao"),
    ("s070","2017-09-16","Gennady Golovkin",  "Saul Alvarez",       "Middleweight","draw","SD",12,12,True,"WBC/WBA/IBF",  "T-Mobile Arena",           "Las Vegas, NV",       "GGG vs Canelo I"),
    ("s072","2018-03-03","Keith Thurman",     "Danny Garcia",       "Welterweight","A","SD", 12,12,True, "WBA",          "Barclays Center",          "Brooklyn, NY",        "Thurman vs Garcia"),
    ("s073","2019-09-12","Vasyl Lomachenko",  "Luke Campbell",      "Lightweight","A","UD", 12,12,True, "WBA/WBC/WBO",  "O2 Arena",                 "London, England",     "Lomachenko vs Campbell"),
    ("s074","2020-10-17","Teofimo Lopez",     "Vasyl Lomachenko",   "Lightweight","A","UD", 12,12,True, "WBA/WBC/WBO/IBF","MGM Bubble",             "Las Vegas, NV",       "Lopez vs Lomachenko"),
]

# Fix the accidentally transposed row s068
SEED_FIGHTS = [
    f if f[0] != "s068" else
    ("s068","2024-12-21","Tyson Fury","Oleksandr Usyk","Heavyweight","A","MD",12,12,True,"WBA/WBC/IBF/WBO","Kingdom Arena","Riyadh, Saudi Arabia","Fury vs Usyk II")
    for f in SEED_FIGHTS
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def _safe_int(val) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _is_upcoming(fight_date) -> bool:
    if fight_date is None:
        return False
    return fight_date >= date.today()


# ─── Upsert Helpers ───────────────────────────────────────────────────────────

def _get_or_create_fighter(session: Session, name: str) -> Fighter:
    fighter = session.query(Fighter).filter(Fighter.name.ilike(name)).first()
    if fighter is None:
        ext_id = f"seed_{_slug(name)}"
        fighter = Fighter(name=name, external_id=ext_id, elo_rating=1500.0)
        session.add(fighter)
        session.flush()
    return fighter


def _upsert_fight_record(session: Session, ext_id: str, fa: Fighter, fb: Fighter,
                         raw: dict) -> Fight:
    fight = session.query(Fight).filter_by(external_id=ext_id).first()
    if fight is None:
        fight = Fight(external_id=ext_id)
        session.add(fight)

    fight.fighter_a_id = fa.id
    fight.fighter_b_id = fb.id
    fight.fight_date = raw.get("fight_date")
    fight.weight_class = raw.get("weight_class")
    fight.result = raw.get("result")
    fight.method = raw.get("method")
    fight.round_ended = raw.get("round_ended")
    fight.total_rounds = raw.get("total_rounds", 12)
    fight.title_fight = raw.get("title_fight", False)
    fight.sanctioning_body = raw.get("sanctioning_body")
    fight.venue = raw.get("venue")
    fight.location = raw.get("location")
    fight.event_name = raw.get("event_name")
    fight.is_upcoming = _is_upcoming(raw.get("fight_date"))
    session.flush()
    return fight


# ─── Seed Historical Data ─────────────────────────────────────────────────────

def seed_historical_data(session: Session) -> int:
    log.info("Seeding fighter profiles …")
    for row in SEED_FIGHTERS:
        (name, weight_class, wins, losses, draws, nc, ko_wins,
         height_cm, reach_cm, stance, by, bm, bd) = row
        ext_id = f"seed_{_slug(name)}"
        fighter = session.query(Fighter).filter_by(external_id=ext_id).first()
        if fighter is None:
            fighter = Fighter(external_id=ext_id, elo_rating=1500.0)
            session.add(fighter)
        fighter.name = name
        fighter.weight_class = weight_class
        fighter.wins = wins
        fighter.losses = losses
        fighter.draws = draws
        fighter.no_contests = nc
        fighter.ko_wins = ko_wins
        fighter.height_cm = height_cm
        fighter.reach_cm = reach_cm
        fighter.stance = stance
        try:
            fighter.birth_date = date(by, bm, bd)
        except ValueError:
            pass
    session.commit()
    log.info(f"  {len(SEED_FIGHTERS)} fighters upserted.")

    log.info("Seeding historical fights …")
    count = 0
    for row in SEED_FIGHTS:
        (ext_id, fight_date_str, fa_name, fb_name, weight_class,
         result, method, round_ended, total_rounds, title_fight,
         sanctioning_body, venue, location, event_name) = row

        try:
            fight_date = datetime.strptime(fight_date_str, "%Y-%m-%d").date()
        except ValueError:
            log.warning(f"  Bad date in seed fight {ext_id}: {fight_date_str!r}")
            continue

        fa = _get_or_create_fighter(session, fa_name)
        fb = _get_or_create_fighter(session, fb_name)

        _upsert_fight_record(session, ext_id, fa, fb, {
            "fight_date": fight_date,
            "weight_class": weight_class,
            "result": result,
            "method": method,
            "round_ended": round_ended,
            "total_rounds": total_rounds,
            "title_fight": title_fight,
            "sanctioning_body": sanctioning_body,
            "venue": venue,
            "location": location,
            "event_name": event_name,
        })
        count += 1

    session.commit()
    log.info(f"  {count} historical fights seeded.")
    return count


# ─── Upcoming Fights from The Odds API ───────────────────────────────────────

def fetch_upcoming_fights(session: Session) -> None:
    """Pull upcoming boxing events from The Odds API and populate fights + odds."""
    if not ODDS_API_KEY:
        log.warning("ODDS_API_KEY not set — skipping upcoming fights fetch.")
        return

    try:
        resp = requests.get(
            "https://api.the-odds-api.com/v4/sports/boxing_boxing/odds",
            params={
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": "h2h",
                "oddsFormat": "american",
                "dateFormat": "iso",
            },
            timeout=20,
        )
        resp.raise_for_status()
        events = resp.json()
        current_event_ids = {e.get("id", "") for e in events}
        log.info(f"Fetched {len(events)} upcoming events from The Odds API.")
        log.info(f"  API credits remaining: {resp.headers.get('x-requests-remaining', '?')}")
    except Exception as exc:
        log.error(f"Upcoming fights fetch failed: {exc}")
        return

    for event in events:
        event_id = event.get("id", "")
        ext_id = f"odds_{event_id}"
        home = event.get("home_team", "").strip()
        away = event.get("away_team", "").strip()
        commence_raw = event.get("commence_time", "")

        if not home or not away:
            continue

        try:
            fight_date = datetime.fromisoformat(
                commence_raw.replace("Z", "+00:00")
            ).date()
        except ValueError:
            fight_date = date.today()

        fa = _get_or_create_fighter(session, home)
        fb = _get_or_create_fighter(session, away)

        # Avoid duplicate fight entries for same pair + date
        existing = (
            session.query(Fight)
            .filter(
                Fight.fighter_a_id == fa.id,
                Fight.fighter_b_id == fb.id,
                Fight.fight_date == fight_date,
            )
            .first()
        )
        if existing:
            fight = existing
            fight.external_id = ext_id  # update id so snapshots link correctly
        else:
            fight = session.query(Fight).filter_by(external_id=ext_id).first()
            if fight is None:
                fight = Fight(external_id=ext_id)
                session.add(fight)
            fight.fighter_a_id = fa.id
            fight.fighter_b_id = fb.id
            fight.fight_date = fight_date
            fight.total_rounds = 12

        fight.is_upcoming = True
        session.flush()

        for book in event.get("bookmakers", []):
            bookmaker = book.get("key", "unknown")
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    snap = OddsSnapshot(
                        fight_id=fight.id,
                        external_fight_id=event_id,
                        fighter_name=outcome.get("name"),
                        bookmaker=bookmaker,
                        american_odds=_safe_int(outcome.get("price")),
                    )
                    session.add(snap)

    # Mark Odds API fights that are no longer in the current response as not upcoming.
    # This handles opponent changes, cancellations, and removed events.
    if current_event_ids:
        stale = (
            session.query(Fight)
            .filter(
                Fight.is_upcoming == True,
                Fight.external_id.like("odds_%"),
            )
            .all()
        )
        for fight in stale:
            event_id = fight.external_id.replace("odds_", "", 1)
            if event_id and event_id not in current_event_ids:
                fight.is_upcoming = False
                log.info(f"Marked stale fight as not upcoming: {fight.external_id}")

    session.commit()
    log.info("Upcoming fights and odds snapshots saved.")


# ─── Elo Recalculation ────────────────────────────────────────────────────────

def recalculate_elo(session: Session) -> None:
    """Replay all completed fights chronologically to update Elo ratings."""
    log.info("Recalculating Elo ratings …")
    elo = EloSystem()
    session.query(EloHistory).delete()

    fights = (
        session.query(Fight)
        .filter(Fight.is_upcoming == False, Fight.result.isnot(None))
        .order_by(Fight.fight_date)
        .all()
    )

    for fight in fights:
        fa = session.get(Fighter, fight.fighter_a_id)
        fb = session.get(Fighter, fight.fighter_b_id)
        if not fa or not fb:
            continue

        winner_name: str | None = None
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
                elo_before=result.winner_before if winner_name == fa.name else result.loser_before,
                elo_after=fa.elo_rating,
            ),
            EloHistory(
                fighter_id=fb.id,
                fight_id=fight.id,
                elo_before=result.winner_before if winner_name == fb.name else result.loser_before,
                elo_after=fb.elo_rating,
            ),
        ])

    session.commit()
    log.info(f"Elo recalculated for {len(fights)} fights.")


# ─── Entry Points ─────────────────────────────────────────────────────────────

def backfill_all() -> None:
    """Full backfill: seed historical data + live upcoming + Elo."""
    session = get_session()
    try:
        log.info("=== KnockOutIQ Backfill ===")
        n = seed_historical_data(session)
        log.info(f"Historical seed complete: {n} fights.")
        fetch_upcoming_fights(session)
        recalculate_elo(session)
        log.info("✅ Backfill complete.")
    finally:
        session.close()


def daily_update() -> None:
    """Daily: refresh odds and upcoming fight list."""
    session = get_session()
    try:
        fetch_upcoming_fights(session)
        log.info("✅ Daily update complete.")
    finally:
        session.close()


def weekly_update() -> None:
    """Weekly: refresh odds, upcoming fights, and recalculate Elo."""
    session = get_session()
    try:
        fetch_upcoming_fights(session)
        recalculate_elo(session)
        log.info("✅ Weekly update complete.")
    finally:
        session.close()


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "backfill"
    if cmd == "backfill":
        backfill_all()
    elif cmd == "daily":
        daily_update()
    elif cmd == "weekly":
        weekly_update()
    else:
        print(f"Unknown command: {cmd!r}. Use: backfill | daily | weekly")
        sys.exit(1)

> **AI Onboarding Guide** — See also the project docs folder for architecture and data source documentation.

# KnockOutIQ (Boxing) — Site Summary

## What This App Does

Streamlit multi-page boxing analytics platform covering 90+ fighters. Combines historical fight data (150 fighters, 73+ historical fights), live DraftKings/FanDuel odds via The Odds API, Elo ratings, and ML-based win probability models. Includes a personal bet tracker with CLV (Closed Line Value) tracking and P&L.

## Quick Start

```bash
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1        # Windows
source .venv/bin/activate           # macOS/Linux

# 2. Initialize the database
python -c "from data.db import init_db; init_db()"

# 3. Run the app
streamlit run predictions.py
```

GitHub Actions runs a nightly odds fetch workflow.

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit (multi-page) |
| ML | XGBoost ensemble + Logistic Regression baseline |
| Ratings | Elo system (K=48 for <10 fights, K=32 for 10+, KO bonus +25%) |
| DB | SQLAlchemy 2.0 + SQLite |
| Odds | The Odds API (DraftKings, FanDuel, BetMGM, BetRivers, etc.) |
| Visualization | Plotly 5+ |

## Key Files

| File | Purpose |
|---|---|
| `predictions.py` | Streamlit entry point — page nav setup |
| `config.py` | API keys, DB path, thresholds (`EDGE_STRONG_THRESHOLD=0.05`) |
| `data/db.py` | SQLAlchemy ORM: `Fighter`, `Fight`, `OddsSnapshot` models |
| `models/elo.py` | Elo rating system with KO weight bonus |
| `models/logistic_model.py` | 9-feature logistic regression baseline |
| `models/xgboost_model.py` | Main XGBoost ensemble with rolling stats |
| `data/odds_api.py` | The Odds API client for live moneylines |
| `pages/01_Fight_Card.py` | Upcoming fights with DK/FanDuel odds and model edges |
| `pages/05_Model_Dashboard.py` | All upcoming bets ranked by edge + accuracy metrics |
| `pages/06_Bet_Tracker.py` | Personal bet log, CLV tracking, P&L, Kelly Calculator |

## Data Flow

1. **Seed**: SQLite DB pre-populated with ~150 fighters and 73 historical + 52 upcoming fights
2. **Live odds**: GitHub Actions nightly → `data/odds_api.py` → The Odds API → `OddsSnapshot` written to SQLite
3. **Elo**: All historical fights → `models/elo.py` → current fighter ratings
4. **Predictions**: Elo ratings + rolling stats → Logistic Regression (baseline) + XGBoost (main) → win probabilities
5. **Edge**: Model win% vs DK implied probability → edge per fight
6. **UI**: Streamlit reads SQLite → renders fight card, matchup analysis, bet tracker

## Elo System Details

- K-factor: `48` for fighters with fewer than 10 fights, `32` for 10+ fights
- KO/TKO wins: +25% bonus to the Elo update
- Default rating: 1500

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `ODDS_API_KEY` | The Odds API (theoddsapi.com) — live moneylines | Required |

**Important**: This is `theoddsapi.com` — not `odds-api.io`. Do not confuse the two.

## Critical Conventions

- Preserve all existing public function signatures unless explicitly asked to change them
- Real data only — no demo fallback mode
- Keep edits minimal and scoped to the user request

## Common Gotchas

- Elo does not use fight recency decay — a 2020 fight counts the same as a 2026 fight; this is a known limitation
- Weight class is not used to separate model training — all fighters are in a single model pool
- The XGBoost model fallback calibration is not fully validated; prefer the Logistic Regression for calibrated probabilities

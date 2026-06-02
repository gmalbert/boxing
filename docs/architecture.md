# KnockOutIQ — Architecture

## Overview
Boxing analytics and betting intelligence platform. Tracks fighters, upcoming fights, model predictions, and DraftKings odds via a Streamlit multi-page app backed by SQLite.

## Data Flow
```
boxing-data-api (RapidAPI) / BoxRec / TheSportsDB
        ↓
scripts/fetch_historical_data.py → SQLite (knockoutiq.db)
        ↓
data/db.py ORM layer
        ↓
ML Model (logistic regression / Elo heuristic)
        ↓
model_predictions table
        ↓
Streamlit pages → predictions.py (entry)
        ↓
scripts/export_best_bets.py → data_files/best_bets_today.json
```

## Database Schema (`data_files/knockoutiq.db`)
| Table | Key Columns |
|-------|-------------|
| `fighters` | id, name, elo_rating, wins, losses, weight_class, stance |
| `fights` | id, fighter_a_id, fighter_b_id, fight_date, result, is_upcoming |
| `odds_snapshots` | fight_id, bookmaker, american_odds, snapshot_time |
| `model_predictions` | fight_id, fighter_a_win_prob, confidence, method probs |
| `bet_log` | fight_id, stake_units, clv, result |

## ML Models
- **Primary**: Logistic regression on fight features (elo diff, stance, reach, weight class, recent form)
- **Fallback**: Elo heuristic when ML model unavailable
- Edge = `model_prob - dk_implied_prob`
- Confidence thresholds: STRONG ≥5%, WEAK 2–5% (from `config.py`)

## API Integrations
| Source | Purpose | Key |
|--------|---------|-----|
| boxing-data-api (RapidAPI) | Historical fights, fighter stats | `RAPIDAPI_KEY` |
| BoxRec | Historical scraping | `BOXREC_USERNAME`, `BOXREC_PASSWORD` |
| TheSportsDB | Fighter images/metadata | None (free tier) |
| Wikipedia | Fighter enrichment | None (public) |

## Key Components
- `config.py` — all env vars, DB path, edge thresholds
- `data/db.py` — SQLAlchemy ORM models + session helpers
- `scripts/fetch_historical_data.py` — backfills fighters/fights
- `scripts/precache_predictions.py` — pre-runs model on upcoming fights
- `scripts/export_best_bets.py` — writes `best_bets_today.json`
- `footer.py` — `add_betting_oracle_footer()`

## Deployment
Streamlit Cloud. Entry point: `streamlit run predictions.py`.

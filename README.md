# KnockOutIQ 🥊

**Boxing Data Analysis & Sports Betting Intelligence**

A full-stack Streamlit application that combines historical boxing fight data, live odds, machine-learning win-probability models, and personal bet tracking into a single analytical platform.

---

## Features

| Page | Description |
|------|-------------|
| **Home** | Quick-nav hub, setup status checker |
| **Fight Card** | Upcoming fights with DraftKings/FanDuel odds, model edge signals, Elo ratings |
| **Fighter Profile** | Per-fighter career deep dive — record, Elo history, win-method breakdown, fight log |
| **Matchup Analyzer** | Side-by-side comparison, probability gauge, radar chart, edge vs current odds |
| **Odds Tracker** | Live odds board, DK vs Pinnacle line movement charts, odds converter |
| **Model Dashboard** | All upcoming fights ranked by edge magnitude, accuracy metrics, calibration chart |
| **Bet Tracker** | Log bets, CLV tracking, cumulative P&L, Kelly Calculator |
| **Fight Database** | Searchable historical archive with KO-rate / method-distribution analytics |

---

## Architecture

```
predictions.py          ← Streamlit entry point (st.navigation, st.set_page_config)
pages/
  01_Fight_Card.py
  02_Fighter_Profile.py
  03_Matchup_Analyzer.py
  04_Odds_Tracker.py
  05_Model_Dashboard.py
  06_Bet_Tracker.py
  07_Fight_Database.py
config.py               ← Env vars, app constants
data/
  db.py                 ← SQLAlchemy ORM (SQLite), session management
  boxing_data.py        ← boxing-data.com RapidAPI client
  odds_api.py           ← The Odds API client (primary live source)
  oddspapi.py           ← OddsPapi / Pinnacle reference lines
  sports_db.py          ← TheSportsDB free metadata
models/
  elo.py                ← Dynamic Elo rating system (KO bonus, novice K-factor)
  logistic_model.py     ← Logistic regression baseline (scikit-learn)
  xgboost_model.py      ← XGBoost ensemble primary model
utils/
  odds_utils.py         ← American ↔ implied prob, CLV, Kelly fraction, edge labels
scripts/
  fetch_historical_data.py  ← Seed DB + live odds fetch (backfill / daily / weekly)
data_files/
  knockoutiq.db         ← SQLite database (gitignored, rebuilt from fetch script)
  models/               ← Serialised ML model files (gitignored)
.github/workflows/
  fetch_data.yml        ← GitHub Actions: daily odds, weekly results, manual backfill
```

---

## Tech Stack

- **Python 3.11**
- **Streamlit ≥ 1.51** — multi-page app via `st.navigation()`
- **SQLAlchemy 2.0** — ORM over SQLite
- **Plotly 5+** — all interactive charts
- **scikit-learn + XGBoost** — win-probability models
- **The Odds API** — live boxing moneylines (DraftKings, FanDuel, BetMGM, etc.)
- **python-dotenv** — `.env` key management

---

## Quick Start

### 1. Clone & set up environment

```bash
git clone <your-repo-url>
cd boxing
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env with your actual keys
```

**Required key:**
- `ODDS_API_KEY` — [The Odds API](https://the-odds-api.com) (free tier: 500 req/month)

**Optional (gracefully degraded if missing):**
- `RAPID_API_KEY` — [boxing-data.com on RapidAPI](https://rapidapi.com/bengroves1993/api/boxing-data-api)
- `ODDSPAPI_API_KEY` — [OddsPapi](https://oddspapi.io) for Pinnacle sharp lines

### 3. Seed the database

```bash
python scripts/fetch_historical_data.py backfill
```

This seeds ~90 fighters, ~73 curated historical fights (2016–2026), pulls 52 live upcoming fights with odds from The Odds API, and calculates Elo ratings — all in under 5 seconds.

### 4. Launch the app

```bash
streamlit run predictions.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Data Sources

### Embedded Seed Data (Historical)
~90 fighters and ~73 notable fights from 2016–2026, including every major heavyweight title fight, Canelo/GGG trilogy, Inoue's bantamweight/super-bantamweight run, Crawford/Spence, and more. This seeds the database on first run and provides the basis for Elo calculations.

### The Odds API (Live)
- 52+ upcoming boxing events with real-time moneylines
- Bookmakers: DraftKings, FanDuel, BetMGM, BetRivers, BetUS, LowVig, BetonlineAG
- Refreshed daily via GitHub Actions

---

## ML Models

### Elo Rating System (`models/elo.py`)
Dynamic Elo with KO bonus (25% extra points for stoppages) and adaptive K-factors:
- **Novice K = 48** (fewer than 10 fights)
- **Established K = 32** (10+ fights)

Current top-rated fighters: Naoya Inoue (1698), Canelo Alvarez (1678), Tyson Fury (1635), Oleksandr Usyk (1602), Terence Crawford (1599)

### Logistic Regression (`models/logistic_model.py`)
Interpretable baseline using 9 features: reach differential, height, age, win %, KO %, Elo differential, days-since-last-fight, opposition quality, southpaw matchup flag. Falls back to heuristic if no training data.

### XGBoost (`models/xgboost_model.py`)
Ensemble primary model extending the logistic features with rolling stats. Returns `(win_prob, confidence)` tuple. Falls back to heuristic until trained on sufficient historical data.

### Training Models
Once you have sufficient historical data in the DB:
```python
# (coming soon — training script)
from models.logistic_model import LogisticBoxingModel
from models.xgboost_model import XGBoostBoxingModel
```

---

## GitHub Actions (Automated Data Refresh)

Three jobs in `.github/workflows/fetch_data.yml`:

| Job | Schedule | What it does |
|-----|----------|-------------|
| `daily-odds-update` | 8:00 UTC daily | Fetches 52 upcoming fights + current odds |
| `weekly-results-update` | 6:00 UTC Monday | Odds refresh + Elo recalculation |
| `backfill` | Manual only | Full seed (workflow_dispatch) |

### GitHub Secrets Required

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `ODDS_API_KEY` | The Odds API key |
| `RAPID_API_KEY` | RapidAPI key (optional) |
| `ODDSPAPI_API_KEY` | OddsPapi key (optional) |

The SQLite database is uploaded/downloaded as a GitHub Actions artifact (`knockoutiq-db`) between runs.

---

## Betting Disclaimer

KnockOutIQ is an analytical tool for research purposes. All model outputs, edge signals, and Kelly fractions are estimates based on historical data and should not be treated as financial advice. Bet responsibly and only in jurisdictions where sports betting is legal.

---

## Project Status

- ✅ 7 Streamlit pages with demo data fallback
- ✅ SQLite database with 150 fighters, 73 historical + 52 upcoming fights
- ✅ 188 live odds snapshots from The Odds API
- ✅ Elo ratings calculated for all fighters
- ✅ GitHub Actions for automated daily/weekly refresh
- 🔄 Model training (requires more historical fight-stat data)
- 🔄 Pinnacle sharp-line integration (OddsPapi endpoint TBD)

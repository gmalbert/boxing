# KnockOutIQ — GitHub Copilot Instructions

## Project Overview

**App name:** KnockOutIQ
**Purpose:** Boxing analytics and betting intelligence platform. Tracks fighters, upcoming fights, model predictions, and DraftKings odds.
**Entry point:** `streamlit run predictions.py`
**Part of:** Betting Oracle suite

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit (multi-page via `st.navigation`) |
| Data | SQLite (`data_files/knockoutiq.db`) via SQLAlchemy |
| ML | Logistic regression / Elo heuristic (fight win probability) |
| Odds | The Odds API, oddspapi.io |
| Data Sources | BoxRec (historical), boxing-data-api (RapidAPI), TheSportsDB |
| Config | python-dotenv (`.env` file) |
| Python | 3.9+ |

---

## File Conventions

### Key files
- `predictions.py` — entry point; sets `st.set_page_config` ONCE. Imports from `config.py`.
- `config.py` — all environment variables, DB path, API keys, thresholds. **Import from here.**
- `data/db.py` — SQLAlchemy ORM models: `Fighter`, `Fight`, `OddsSnapshot`, `ModelPrediction`, `BetLog`. All DB session logic here.
- `footer.py` — `add_betting_oracle_footer()` called at page bottom.
- `scripts/export_best_bets.py` — exports `data_files/best_bets_today.json` for Sports Picks Grid.

### Database schema (`data_files/knockoutiq.db`)
- `fighters` — id, external_id, name, stance, height_cm, reach_cm, birth_date, nationality, weight_class, elo_rating, wins, losses, draws, no_contests, ko_wins, tko_wins, style_tag, image_url
- `fights` — id, external_id, fighter_a_id, fighter_b_id, fight_date, weight_class, result, method, round_ended, total_rounds, title_fight, sanctioning_body, venue, location, is_upcoming, event_name
- `odds_snapshots` — id, fight_id, external_fight_id, fighter_name, bookmaker, american_odds, decimal_odds, snapshot_time
- `model_predictions` — id, fight_id, model_version, fighter_a_name, fighter_b_name, fighter_a_win_prob, confidence, method_ko_prob, method_dec_prob, predicted_at
- `bet_log` — id, fight_id, fighter_name, bookmaker, american_odds_obtained, stake_units, model_prob_at_time, closing_odds, clv, result, notes, placed_at

### Data scripts
- `scripts/fetch_historical_data.py` — backfills fighters and fights from boxing-data-api
- `scripts/scrape_historical.py` — BoxRec scraper (requires BOXREC_USERNAME/PASSWORD)
- `scripts/enrich_fighters_wiki.py` — adds fighter images/metadata from Wikipedia/TheSportsDB
- `scripts/precache_predictions.py` — pre-runs model on all upcoming fights

---

## Domain Knowledge

### Confidence thresholds (from `config.py`)
- `EDGE_STRONG_THRESHOLD = 0.05` — 5%+ edge → strong (green)
- `EDGE_WEAK_THRESHOLD = 0.02` — 2–5% edge → marginal (yellow)
- Edge = model_prob - dk_implied_prob

### Model logic
- Primary: logistic regression trained on historical fight features
- Fallback: Elo rating heuristic when ML model unavailable
- `fighter_a_win_prob` is the probability fighter A wins (0–1)

---

## Coding Conventions

### Streamlit patterns
```python
@st.cache_data(ttl=3600)
def load_upcoming_fights() -> list[dict]: ...

@st.cache_resource
def get_db_session(): ...
```
- `st.set_page_config()` called ONCE in `predictions.py` only
- Use `width='stretch'` for dataframes/charts (not `use_container_width`)
- Never call DB directly in page files — use `data/db.py` helpers

### Security
- API keys in `.env` loaded via `config.py`; never hardcode
- BoxRec credentials: `BOXREC_USERNAME`, `BOXREC_PASSWORD` in `.env` only
- `.env` is gitignored
- Use parameterized SQLAlchemy queries — no raw string SQL with user input

### Error handling
- Wrap all external API calls in try/except; return empty list/dict on failure
- Check `is_upcoming=1` before processing fights
- Guard all numeric formatting against None/NaN

---

## Export for Sports Picks Grid

`scripts/export_best_bets.py` queries `model_predictions JOIN fights JOIN odds_snapshots` for upcoming fights, computes edge, and writes `data_files/best_bets_today.json`.

Run: `python scripts/export_best_bets.py`

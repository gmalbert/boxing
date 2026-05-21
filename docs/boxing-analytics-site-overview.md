# Boxing Analytics & Betting Intelligence Site
## Project Overview & Research Findings

> **Goal:** Build a data-driven boxing analysis site to gain a statistical edge over DraftKings NH lines — finding mispriced odds before they correct.

---

## Table of Contents
1. [Data Sources & APIs](#data-sources--apis)
2. [What Data Is Available](#what-data-is-available)
3. [Site Architecture](#site-architecture)
4. [Predictive Models](#predictive-models)
5. [DraftKings Edge Strategy](#draftkings-edge-strategy)
6. [Build Roadmap](#build-roadmap)

---

## Data Sources & APIs

### Tier 1 — Free, Start Here

| Source | What You Get | Free Limit | Notes |
|---|---|---|---|
| **boxing-data.com** (RapidAPI) | Fighter profiles, fight history, round-by-round stats, punch accuracy, schedules, title belts | Free tier available | Best all-in-one boxing stats API; covers major promotions |
| **The Odds API** (the-odds-api.com) | Live + historical boxing moneylines from DraftKings, FanDuel, BetMGM, 40+ books | 500 credits/month free | Historical odds back to 2023 on paid ($30/mo); direct DraftKings line access |
| **OddsPapi.io** | 350+ bookmakers including Pinnacle (sharp), DraftKings, Betfair Exchange; historical odds | 250 req/month free, no credit card | Pinnacle access is the crown jewel — use for CLV analysis |
| **TheSportsDB** | Fight schedules, event artwork, results | Free (open data) | Good for event metadata and scheduling |
| **Wikipedia API** | Fighter bios, nationality, career history | Unlimited, free | Useful for biographical features |

### Tier 2 — Low Cost, High Value

| Source | What You Get | Cost | Notes |
|---|---|---|---|
| **The Odds API** (paid) | Historical odds snapshots back to 2020, line movement | $30/month | Essential for backtesting your models |
| **OddsPapi** (paid) | WebSocket real-time odds, all 350+ books | Paid tiers | Best if you want live arb detection |
| **boxing-data.com** (paid) | Punch-by-punch live data, full archive | Check RapidAPI | Upgrade when you need live fight tracking |

### Tier 3 — Scraping (Proceed with Caution)

| Source | What's There | Feasibility | Legal Status |
|---|---|---|---|
| **BoxRec.com** | Most comprehensive boxing database on the planet — every pro fight ever recorded, trainer info, gym, promoter | Hard — strong anti-scrape; existing npm package mostly broken as of 2022 | ToS explicitly prohibits scraping since 2018; enforceability unclear |
| **Box.Live** | Boxer profiles, stats, stance, reach, win rates | Moderate — Python scraping demonstrated in public tutorials | Not explicitly prohibited; still use respectfully |
| **Tapology.com** | Fighter records, rankings, community picks (boxing & MMA) | Hard — strong anti-scraping defenses, IP bans common | ToS discourages it |
| **ESPN Boxing** | Fight cards, results, odds context | Moderate | ToS prohibits; use for manual enrichment |

**Recommendation:** Don't rely on scraping as a primary pipeline. BoxRec is too risky for production use. Use the paid APIs — at $30-60/month they are cheap relative to any meaningful betting edge.

---

## What Data Is Available

### Fighter Profile Data
- Win/loss/draw record, KO percentage
- Stance (Orthodox vs. Southpaw)
- Height, reach, weight class
- Age, nationality, gym/trainer
- Active/inactive status
- Ranking by sanctioning body (WBC, WBA, IBF, WBO, IBO, The Ring)
- Career earnings (limited public data)

### Fight-Level Data
- Date, venue, location
- Result (KO, TKO, UD, MD, SD, DQ, NC)
- Round of stoppage
- Judges' scorecards (partial availability)
- Referee
- Title(s) on the line

### In-Fight Stats (CompuBox-style, available via boxing-data.com)
- Total punches thrown vs. landed
- Jabs thrown vs. landed
- Power punches thrown vs. landed
- Punch accuracy percentages
- Round-by-round breakdown

### Odds Data
- Opening lines (from multiple books)
- Line movement over time (how odds shift from open to close)
- Closing line (most efficient price)
- Over/under total rounds
- Method of victory props (KO/TKO, decision, etc.)

### What's NOT Easily Available (Gaps)
- Training camp intel (injuries, sparring) — Twitter/X and boxing media only
- Judge tendencies and scoring patterns — manual research required
- Cornermen strategies — qualitative, no structured data
- Live CompuBox during fights — requires premium TV data partnerships

---

## Site Architecture

See [`site-features.md`](./site-features.md) for full feature breakdown.

**Core Stack: Streamlit**

This project is being developed in **Streamlit** — an ideal choice for a data-heavy, solo-built analytics tool. Streamlit lets you build the full UI directly in Python, keeping the entire stack in one language with no separate frontend framework needed.

- **UI Framework:** Streamlit — pages, charts, tables, and widgets all in Python
- **Data & ML:** Pandas, scikit-learn, XGBoost, Plotly — all first-class in Streamlit
- **Database:** PostgreSQL (via psycopg2 or SQLAlchemy) + `st.cache_data` for performance
- **Scheduler:** APScheduler or a separate cron script for odds polling every 30-60 seconds
- **Hosting:** Streamlit Community Cloud (free) or Railway/Render (~$5-20/month for always-on)

**Streamlit advantages for this use case:**
- Zero frontend code — charts, tables, filters, and metrics are all Python calls
- `st.cache_data` and `st.cache_resource` make API-heavy pages fast without a separate caching layer
- Plotly charts render natively and are interactive out of the box
- Rapid iteration — change a model, refresh the page, see results immediately
- Multi-page apps supported via `pages/` directory structure

**Streamlit limitations to plan around:**
- Not ideal for real-time push updates (workaround: `st.rerun()` on a timer or `st.fragment`)
- Session state is per-user, per-session — shared data lives in the database
- Mobile experience is functional but not as polished as a native React app

---

## DraftKings Edge Strategy

The core concept: **DraftKings is a "soft" book.** They accept recreational bettors, limit winners slowly, and their lines are not as sharp as Pinnacle. This creates exploitable windows.

### How to Find +EV Bets Against DraftKings

1. **Pinnacle vs. DraftKings Spread**
   Use OddsPapi to pull both Pinnacle (sharp) and DraftKings (soft) lines simultaneously. When DraftKings offers significantly better odds than Pinnacle's implied probability, that's a potential +EV spot.

2. **Line Movement Fade/Follow**
   Track when DraftKings' lines move. If a line moves from -200 to -160 on the favorite, sharp money hit the underdog. Act before DK corrects.

3. **Closing Line Value (CLV)**
   If you consistently beat the closing line (the final odds before a fight), you are making +EV bets regardless of short-term results. Track your CLV to validate your model.

4. **Early Lines / Opening Lines**
   DraftKings often posts soft opening lines before the market has been sharpened. Your model needs to be faster than the public.

5. **Prop Bets (Method of Victory, Round Totals)**
   Props are harder for books to price than moneylines — more opportunity for error on their end.

### NH-Specific Notes
- DraftKings is fully legal and operational in New Hampshire
- NH has relatively favorable sports betting regulations
- DraftKings is one of the primary books available in NH
- No Pinnacle access in NH (US-only restriction) — use OddsPapi to *observe* Pinnacle lines as a reference, not to bet them

---

## Build Roadmap

### Phase 1 — Data Foundation (2-4 weeks)
- [ ] Set up boxing-data.com API integration
- [ ] Set up The Odds API (free tier) for DraftKings line tracking
- [ ] Set up OddsPapi (free tier) for Pinnacle reference lines
- [ ] Build PostgreSQL schema for fighters, fights, odds
- [ ] Build historical data backfill pipeline

### Phase 2 — Core Streamlit Pages (4-6 weeks)
- [ ] `pages/01_fight_card.py` — upcoming fights with current DK odds
- [ ] `pages/02_fighter_profile.py` — per-fighter stat deep dive
- [ ] `pages/03_odds_tracker.py` — DK vs. Pinnacle comparison table + line movement charts
- [ ] `pages/04_matchup_analyzer.py` — head-to-head fighter comparison tool
- [ ] Basic model: win probability from fighter stats, displayed inline

### Phase 3 — Edge Models (4-8 weeks)
- [ ] Logistic regression baseline model (displayed via `st.metric` and Plotly gauges)
- [ ] XGBoost model with full feature set
- [ ] `pages/05_model_dashboard.py` — model prob vs. DK implied prob, ranked by edge
- [ ] CLV tracker for your own bets (`pages/06_bet_tracker.py`)
- [ ] Alert system: `st.toast` notifications + optional email when DK line diverges from model

### Phase 4 — Polish & Scale
- [ ] `pages/07_backtesting.py` — historical model accuracy dashboard
- [ ] Bankroll management calculator widget
- [ ] Deploy to Streamlit Community Cloud (free) or Railway for always-on access
- [ ] Potentially: community picks / leaderboard (requires auth — use `streamlit-authenticator`)

---

*See also:*
- [`data-sources-detail.md`](./data-sources-detail.md) — API setup guides, endpoints, code samples
- [`models-and-features.md`](./models-and-features.md) — full ML model specs and feature engineering

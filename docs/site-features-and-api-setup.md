# Boxing Analytics Site: Features & API Setup Guide

---

## Site Features

> Built in **Streamlit** — each section below corresponds to a page in the `pages/` directory. All charts use Plotly for interactivity; data is loaded via `@st.cache_data` to minimize API calls.

### Core Pages

#### 1. Dashboard / Fight Card Hub (`app.py`)
The landing page. Shows upcoming fights with:
- Fighter photos and records
- Current DraftKings moneyline
- Your model's win probability
- **Edge indicator:** if model disagrees with DK by >3%, show a colored flag
- Line movement sparkline (last 48 hours)
- Days until fight

#### 2. Fighter Profile Page (`pages/02_fighter_profile.py`)
Per-fighter deep dive:
- Career record with breakdown (KO/TKO/UD/MD/SD wins)
- Physical stats (height, reach, stance, weight class)
- Punch stats (career average if available)
- Recent fights timeline with outcomes
- Elo rating chart over career
- Style classification (boxer, brawler, counter-puncher, etc.)
- Opponent quality score

#### 3. Fight Matchup Analyzer (`pages/03_matchup_analyzer.py`)
Head-to-head comparison for any two fighters:
- Side-by-side physical stats with advantage indicators
- Style matchup analysis (stance, reach, pressure vs. counter)
- Historical results against similar opponents
- Model win probability with confidence interval
- Current odds from multiple books

#### 4. Odds Tracker / Line Movement (`pages/04_odds_tracker.py`)
Per-fight odds history:
- Chart of DK line from open to current
- Chart of Pinnacle line (reference)
- Key movement timestamps with "sharp money" annotations
- Current DK vs. Pinnacle gap (the value indicator)
- Over/under movement for total rounds

#### 5. Model Dashboard (`pages/05_model_dashboard.py`)
Your prediction engine's output:
- All upcoming fights with model probability vs. DK implied probability
- Ranked by edge magnitude (biggest edge at the top)
- Filter by: weight class, confidence level, fight type
- Historical accuracy metrics for your model

#### 6. Bet Tracker & CLV Logger (`pages/06_bet_tracker.py`)
Personal betting performance tool:
- Log bets: fight, pick, odds obtained, stake
- Auto-fetch closing line for each fight
- CLV per bet (your odds vs. closing odds)
- Cumulative CLV chart (flat-bet unit tracking)
- ROI, win rate, and average edge statistics
- "Am I actually good at this?" honest assessment

#### 7. Historical Fight Database (`pages/07_fight_database.py`)
Searchable archive:
- Filter by weight class, year, sanctioning body, method of result
- Individual fight pages with full stats
- Trend views: KO rates by weight class, average fight length, etc.

#### 8. Alerts / Watchlist
- Set alerts on specific fights
- Notify when DK line moves more than X% from opening
- Notify when your model detects edge > threshold
- Morning digest email: today's best model signals

---

## API Setup Guide

### Step 1: boxing-data.com (RapidAPI)

Sign up at [RapidAPI](https://rapidapi.com) — free account gets you access.

**Subscribe to:** Boxing Data API by bengroves1993

**Key endpoints:**
```
GET /fighters/{id}           - Fighter profile + career stats
GET /fights/schedule/        - Upcoming high-profile bouts
GET /fights/{id}/stats/      - Round-by-round CompuBox stats
GET /titles/                 - Current title holders by division
GET /rankings/               - Fighter rankings
```

**Python example:**
```python
import requests

headers = {
    "X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY",
    "X-RapidAPI-Host": "boxing-data-api.p.rapidapi.com"
}

# Get upcoming fight schedule
response = requests.get(
    "https://boxing-data-api.p.rapidapi.com/fights/schedule/",
    headers=headers
)
fights = response.json()
```

---

### Step 2: The Odds API (DraftKings Lines)

Sign up at [the-odds-api.com](https://the-odds-api.com) — 500 free credits/month.

**DraftKings boxing moneylines:**
```
GET https://api.the-odds-api.com/v4/sports/boxing_boxing/odds
    ?regions=us
    &markets=h2h
    &bookmakers=draftkings,fanduel,betmgm
    &oddsFormat=american
    &apiKey=YOUR_KEY
```

**Python example:**
```python
import requests

API_KEY = "YOUR_ODDS_API_KEY"

response = requests.get(
    "https://api.the-odds-api.com/v4/sports/boxing_boxing/odds",
    params={
        "apiKey": API_KEY,
        "regions": "us",
        "markets": "h2h,totals",  # moneyline + over/under rounds
        "bookmakers": "draftkings,fanduel,betmgm",
        "oddsFormat": "american"
    }
)

fights = response.json()
for fight in fights:
    print(f"{fight['home_team']} vs {fight['away_team']} - {fight['commence_time']}")
    for book in fight.get('bookmakers', []):
        if book['key'] == 'draftkings':
            for market in book['markets']:
                if market['key'] == 'h2h':
                    for outcome in market['outcomes']:
                        print(f"  DK: {outcome['name']} {outcome['price']}")
```

---

### Step 3: OddsPapi (Pinnacle Reference Lines)

Sign up at [oddspapi.io](https://oddspapi.io) — free tier, no credit card.

**Why Pinnacle:** Pinnacle is the sharpest book globally — lowest vig, accepts big bets from winners. Their lines are the market's "truth." When DK diverges from Pinnacle, that's your signal.

```python
import requests

API_KEY = "YOUR_ODDSPAPI_KEY"

# Get upcoming boxing fixtures
fixtures = requests.get(
    "https://api.oddspapi.io/v4/fixtures",
    params={"apiKey": API_KEY, "sport": "boxing"}
).json()

# Get odds for a specific fixture (includes Pinnacle + DK)
for fixture in fixtures.get('data', []):
    odds = requests.get(
        "https://api.oddspapi.io/v4/odds",
        params={
            "apiKey": API_KEY,
            "fixtureId": fixture['id']
        }
    ).json()
    
    bookmakers = odds.get('bookmakerOdds', {})
    pinnacle = bookmakers.get('pinnacle', {})
    dk = bookmakers.get('draftkings', {})
    
    # Compare lines, detect edge
```

---

### Step 4: Implied Probability & Edge Calculation

```python
def american_to_implied_prob(american_odds: int) -> float:
    """Convert American odds to implied probability."""
    if american_odds > 0:
        return 100 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)

def remove_vig(prob_a: float, prob_b: float) -> tuple[float, float]:
    """Remove the bookmaker's vig to get fair probabilities."""
    total = prob_a + prob_b
    return prob_a / total, prob_b / total

def calculate_edge(model_prob: float, dk_american_odds: int) -> float:
    """
    Returns the edge your model has vs. DraftKings.
    Positive = model thinks this bet is +EV.
    """
    dk_implied = american_to_implied_prob(dk_american_odds)
    return model_prob - dk_implied

# Example
model_says_fighter_a_wins = 0.62  # 62% from your model
dk_odds_fighter_a = -150          # DK has them at -150

edge = calculate_edge(model_says_fighter_a_wins, dk_odds_fighter_a)
print(f"Edge: {edge:.1%}")  # If positive, consider betting
```

---

### Step 5: Database Schema (PostgreSQL)

```sql
-- Fighters
CREATE TABLE fighters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    boxrec_id INTEGER,
    stance VARCHAR(20),
    height_cm INTEGER,
    reach_cm INTEGER,
    birth_date DATE,
    nationality VARCHAR(50),
    weight_class VARCHAR(50),
    elo_rating FLOAT DEFAULT 1500,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fights
CREATE TABLE fights (
    id SERIAL PRIMARY KEY,
    fighter_a_id INTEGER REFERENCES fighters(id),
    fighter_b_id INTEGER REFERENCES fighters(id),
    fight_date DATE,
    weight_class VARCHAR(50),
    result VARCHAR(10),  -- 'A', 'B', 'draw', 'NC'
    method VARCHAR(20),  -- 'KO', 'TKO', 'UD', 'MD', 'SD', 'DQ'
    round_ended INTEGER,
    title_fight BOOLEAN,
    sanctioning_body VARCHAR(20),
    venue VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fight Stats (CompuBox)
CREATE TABLE fight_stats (
    id SERIAL PRIMARY KEY,
    fight_id INTEGER REFERENCES fights(id),
    fighter_id INTEGER REFERENCES fighters(id),
    total_punches_thrown INTEGER,
    total_punches_landed INTEGER,
    jabs_thrown INTEGER,
    jabs_landed INTEGER,
    power_thrown INTEGER,
    power_landed INTEGER,
    knockdowns_scored INTEGER,
    knockdowns_suffered INTEGER
);

-- Odds snapshots
CREATE TABLE odds_snapshots (
    id SERIAL PRIMARY KEY,
    fight_id INTEGER REFERENCES fights(id),
    bookmaker VARCHAR(30),
    fighter_id INTEGER REFERENCES fighters(id),
    american_odds INTEGER,
    snapshot_time TIMESTAMPTZ DEFAULT NOW()
);

-- Model predictions
CREATE TABLE model_predictions (
    id SERIAL PRIMARY KEY,
    fight_id INTEGER REFERENCES fights(id),
    model_version VARCHAR(20),
    fighter_a_win_prob FLOAT,
    confidence FLOAT,
    predicted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bet log (personal)
CREATE TABLE bet_log (
    id SERIAL PRIMARY KEY,
    fight_id INTEGER REFERENCES fights(id),
    fighter_id INTEGER REFERENCES fighters(id),
    bookmaker VARCHAR(30) DEFAULT 'draftkings',
    american_odds_obtained INTEGER,
    stake_units FLOAT,
    model_prob_at_time FLOAT,
    closing_odds INTEGER,  -- fill in after fight
    clv FLOAT,  -- closing_prob - obtained_prob
    result VARCHAR(10),  -- 'win', 'loss', 'push'
    placed_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Tech Stack: Streamlit

This project is built entirely in **Streamlit**, keeping the full stack in Python with no separate frontend framework.

### Why Streamlit for This Project
- Everything — data fetching, ML models, charts, tables, filters — is written in Python
- `st.cache_data` replaces the need for Redis; cached API responses stay fast without extra infrastructure
- Plotly and Altair charts are interactive out of the box (hover, zoom, filter)
- Multi-page structure via the `pages/` directory maps cleanly to the site's features
- Streamlit Community Cloud offers free hosting for personal/small projects

### Project Structure
```
boxing-analytics/
├── app.py                    # Home / Dashboard page
├── pages/
│   ├── 01_fight_card.py      # Upcoming fights + DK odds
│   ├── 02_fighter_profile.py # Per-fighter deep dive
│   ├── 03_odds_tracker.py    # DK vs Pinnacle line comparison
│   ├── 04_matchup_analyzer.py # Head-to-head tool
│   ├── 05_model_dashboard.py  # Model prob vs DK implied prob
│   ├── 06_bet_tracker.py      # Personal CLV + bet log
│   └── 07_backtesting.py      # Historical model accuracy
├── data/
│   ├── db.py                 # SQLAlchemy / psycopg2 connection
│   ├── odds_api.py           # The Odds API client
│   ├── oddspapi.py           # OddsPapi (Pinnacle) client
│   └── boxing_data.py        # boxing-data.com client
├── models/
│   ├── elo.py                # Elo rating system
│   ├── logistic_model.py     # Baseline model
│   └── xgboost_model.py      # Primary prediction model
├── scheduler.py              # APScheduler: polls odds every 30-60s
└── requirements.txt
```

### Key Streamlit Patterns for This App

**Caching API calls** (avoid hitting rate limits on every page load):
```python
import streamlit as st
import requests

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_dk_boxing_odds(api_key: str) -> list:
    response = requests.get(
        "https://api.the-odds-api.com/v4/sports/boxing_boxing/odds",
        params={
            "apiKey": api_key,
            "regions": "us",
            "markets": "h2h,totals",
            "bookmakers": "draftkings,fanduel,betmgm",
            "oddsFormat": "american"
        }
    )
    return response.json()
```

**Edge detection display:**
```python
import streamlit as st
import pandas as pd

def show_edge_table(fights_with_model_probs: pd.DataFrame):
    # Color-code rows by edge magnitude
    def highlight_edge(row):
        if row['edge'] > 0.05:
            return ['background-color: #1a4a1a'] * len(row)  # green
        elif row['edge'] > 0.02:
            return ['background-color: #3a3a1a'] * len(row)  # yellow
        return [''] * len(row)
    
    st.dataframe(
        fights_with_model_probs.style.apply(highlight_edge, axis=1),
        width="stretch"
    )
```

**Line movement chart:**
```python
import plotly.graph_objects as go
import streamlit as st

def show_line_movement(odds_history: pd.DataFrame, fighter_name: str):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=odds_history['snapshot_time'],
        y=odds_history['american_odds'],
        mode='lines+markers',
        name=fighter_name,
        line=dict(color='#e63946', width=2)
    ))
    fig.update_layout(
        title=f"DraftKings Line Movement — {fighter_name}",
        xaxis_title="Time",
        yaxis_title="American Odds",
        template="plotly_dark"
    )
    st.plotly_chart(fig, width="stretch")
```

**Auto-refresh for live odds** (during fight night):
```python
import streamlit as st
import time

# At top of the fight card page:
auto_refresh = st.sidebar.toggle("Live Mode (refresh every 60s)", value=False)

if auto_refresh:
    time.sleep(60)
    st.rerun()
```

### Hosting Options

| Option | Cost | Pros | Cons |
|---|---|---|---|
| **Streamlit Community Cloud** | Free | Zero setup, GitHub deploy | Always-on requires activity; limited resources |
| **Railway** | ~$5-10/month | Always-on, easy deploy, supports scheduler | Small cost |
| **Render** | ~$7/month | Similar to Railway | Cold starts on free tier |
| **Local (personal use)** | $0 | Full control | Only accessible on your machine |

For a personal betting tool with no public users, **start with Streamlit Community Cloud** (free) or just run it locally. Upgrade to Railway if you want it always-on and running the odds-polling scheduler in the background.

### Full Requirements
```
# requirements.txt
streamlit>=1.35.0
pandas>=2.0.0
plotly>=5.18.0
requests>=2.31.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
scikit-learn>=1.4.0
xgboost>=2.0.0
apscheduler>=3.10.0
python-dotenv>=1.0.0
streamlit-authenticator>=0.3.0  # if you add login
```

---

## NH Sports Betting Context

- DraftKings is legal and dominant in NH
- NH launched legal sports betting in December 2019
- DraftKings has been the primary/exclusive partner for NH lottery
- NH bettors can only access US-licensed books
- **You cannot bet Pinnacle from NH** — but you can *use* their lines as reference data via OddsPapi
- Limits: DraftKings does limit winning accounts over time — this is a known risk. Build your edge fast.
- NH has no state income tax, but gambling winnings are federally taxable above thresholds

---

## Responsible Gambling Note

Building a betting model is a legitimate analytical pursuit. A few ground rules for sustainable operation:

1. **Never bet more than 1-3% of bankroll on any single fight** — even with high model confidence
2. **Track CLV, not just wins/losses** — variance in boxing is brutal; CLV tells you if your process is sound
3. **Set a monthly loss limit and honor it** — treat it like a budget
4. **The edge is small** — boxing analytics won't make you rich quickly; it's a long-term EV game
5. **DK will notice winning accounts** — diversify to FanDuel, BetMGM once proven profitable

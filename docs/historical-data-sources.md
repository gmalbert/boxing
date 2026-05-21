# Historical Boxing Data Sources (2015–Present)
## APIs, Scrapers, & Datasets for Streamlit Analytics App

> **Goal:** Build a historical fight database going back to 2015 to train models and backtest predictions against DraftKings lines.

---

## Quick Reference: What to Use and When

| Source | Type | Historical Depth | Free? | Reliability | Best For |
|---|---|---|---|---|---|
| **boxing-data.com** | API | ~2015+ (major bouts) | Free tier | ⭐⭐⭐⭐⭐ | Punch stats, fighter profiles, fight archive |
| **TheSportsDB** | API | Full archive | Free (v1) | ⭐⭐⭐⭐ | Event results, fight metadata |
| **Wikipedia API** | API | All time | Free | ⭐⭐⭐⭐ | Fighter bios, title lineages, career records |
| **Kaggle Datasets** | Static CSV | Varies (2015+ for most) | Free | ⭐⭐⭐ | Cold start / training data |
| **Box.Live** | Scraper | ~2010+ | Free | ⭐⭐⭐ | Fighter profiles, stats, stance/reach |
| **ESPN Boxing** | Scraper | ~2005+ | Free | ⭐⭐ | Fight results, cards, rankings |
| **BoxRec** | Scraper | Complete pro history | Free (w/ account) | ⭐ (broken) | Best data, worst access |

---

## Source 1: boxing-data.com (RapidAPI) ✅ Start Here

**Historical depth:** Major professional bouts going back to approximately 2015, with ongoing expansion per their May 2025 announcement of wider coverage.

**What's available historically:**
- Fighter career records (all past fights in their system)
- Round-by-round punch stats for recorded fights
- Fight results (method, round, date)
- Event history with full fight cards

**Free tier limits:** Limited requests/month — good for initial backfill, may need paid tier for bulk historical pulls.

**Sign up:** https://rapidapi.com/bengroves1993/api/boxing-data-api

```python
# data/boxing_data_client.py
import requests
import time
import streamlit as st

RAPIDAPI_KEY = st.secrets["RAPIDAPI_KEY"]
BASE_URL = "https://boxing-data-api.p.rapidapi.com/v1"
HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "boxing-data-api.p.rapidapi.com"
}

@st.cache_data(ttl=3600)
def get_fighter(fighter_id: int) -> dict:
    """Get full fighter profile including career record."""
    resp = requests.get(f"{BASE_URL}/fighters/{fighter_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

@st.cache_data(ttl=3600)
def get_fight_stats(fight_id: int) -> dict:
    """Get round-by-round CompuBox stats for a specific fight."""
    resp = requests.get(f"{BASE_URL}/fights/{fight_id}/stats/", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

@st.cache_data(ttl=86400)
def get_all_fights(page: int = 1) -> dict:
    """
    Pull from the complete fights database (not just schedule).
    Use pagination to backfill historical data.
    Endpoint: /fights/ — returns full archive, paginated.
    """
    resp = requests.get(
        f"{BASE_URL}/fights/",
        headers=HEADERS,
        params={"page": page}
    )
    resp.raise_for_status()
    return resp.json()

def backfill_historical_fights(db_conn, start_page: int = 1, max_pages: int = 50):
    """
    Paginate through the full fights archive and store in PostgreSQL.
    Run once to populate your DB; after that, use incremental updates.
    """
    for page in range(start_page, max_pages + 1):
        try:
            data = get_all_fights(page)
            fights = data.get("results", [])
            if not fights:
                print(f"No more fights at page {page}. Done.")
                break
            
            for fight in fights:
                # Insert into your fights table
                db_conn.execute("""
                    INSERT INTO fights (external_id, fighter_a_name, fighter_b_name,
                        fight_date, result, method, round_ended, weight_class)
                    VALUES (%(id)s, %(fighter_a)s, %(fighter_b)s,
                        %(date)s, %(result)s, %(method)s, %(round)s, %(weight_class)s)
                    ON CONFLICT (external_id) DO NOTHING
                """, fight)
            
            print(f"Page {page}: stored {len(fights)} fights")
            time.sleep(0.5)  # respect rate limits
            
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
```

---

## Source 2: TheSportsDB ✅ Reliable & Truly Free

**Historical depth:** Full archive — results going back decades, with boxing leagues/events searchable by season.

**Free tier:** Uses API key `123` for v1 — genuinely free, no credit card, no rate limit on basic calls. Premium ($3/mo Patreon) unlocks faster calls.

**Limitations:** Metadata-focused (results, dates, venues). No punch stats. Good as a supplementary results database and for event lookups.

**Docs:** https://www.thesportsdb.com/documentation

```python
# data/thesportsdb_client.py
import requests
import streamlit as st

# Free key is literally "123" - no signup needed for basic use
FREE_API_KEY = "123"
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{FREE_API_KEY}"

# Boxing league IDs in TheSportsDB
# Search for your league: /search_all_leagues.php?s=Boxing
BOXING_LEAGUE_IDS = {
    "WBC": "4479",      # find via search endpoint
    "IBF": "4480",
    "WBO": "4481",
}

@st.cache_data(ttl=86400)
def search_boxer(name: str) -> list:
    """Search for a boxer by name."""
    resp = requests.get(
        f"{BASE_URL}/searchplayers.php",
        params={"p": name}
    )
    return resp.json().get("player", []) or []

@st.cache_data(ttl=86400)
def get_past_events_by_league(league_id: str) -> list:
    """Get the last 15 events in a boxing league/series."""
    resp = requests.get(
        f"{BASE_URL}/eventspastleague.php",
        params={"id": league_id}
    )
    return resp.json().get("events", []) or []

@st.cache_data(ttl=86400)
def get_events_by_season(league_id: str, season: str) -> list:
    """
    Get all events in a season.
    season format: "2019-2020" or just "2019"
    Great for historical backfill year by year from 2015.
    """
    resp = requests.get(
        f"{BASE_URL}/eventsseason.php",
        params={"id": league_id, "s": season}
    )
    return resp.json().get("events", []) or []

@st.cache_data(ttl=86400)
def get_event_details(event_id: str) -> dict:
    """Get full details for a specific event including result."""
    resp = requests.get(
        f"{BASE_URL}/lookupevent.php",
        params={"id": event_id}
    )
    events = resp.json().get("events", [])
    return events[0] if events else {}

def backfill_from_2015(league_id: str, db_conn):
    """Pull all events from 2015 to present and store results."""
    seasons = [str(y) for y in range(2015, 2027)]
    all_events = []
    
    for season in seasons:
        events = get_events_by_season(league_id, season)
        print(f"Season {season}: {len(events)} events")
        all_events.extend(events)
    
    for event in all_events:
        db_conn.execute("""
            INSERT INTO events_raw (external_id, name, date, home_team, away_team,
                home_score, away_score, source)
            VALUES (%(idEvent)s, %(strEvent)s, %(dateEvent)s, %(strHomeTeam)s,
                %(strAwayTeam)s, %(intHomeScore)s, %(intAwayScore)s, 'thesportsdb')
            ON CONFLICT (external_id) DO NOTHING
        """, event)
    
    return len(all_events)

# Example: Search for Canelo Alvarez's fight history
if __name__ == "__main__":
    results = search_boxer("Canelo Alvarez")
    if results:
        boxer = results[0]
        print(f"Found: {boxer['strPlayer']} (ID: {boxer['idPlayer']})")
        # Then look up their events/career with player ID
```

---

## Source 3: Wikipedia API ✅ Excellent for Supplemental Data

**Historical depth:** All time — complete title lineages, fight records, biographical data.

**What it's uniquely good for:**
- Complete fighter biographical data (birth date, nationality, height, reach, stance)
- Title reign timelines — who held WBC/WBA/IBF/WBO from 2015 to now
- Fighter career records when boxing-data.com doesn't have them
- Judge and referee names (useful for later model features)

**Free:** Completely free, no API key, extremely generous rate limits.

```python
# data/wikipedia_client.py
import requests
import streamlit as st
import re

WIKI_API = "https://en.wikipedia.org/api/rest_v1"
WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"

@st.cache_data(ttl=604800)  # cache for 1 week - Wikipedia doesn't change often
def get_fighter_wiki_summary(name: str) -> dict:
    """
    Get Wikipedia summary for a boxer.
    Returns intro paragraph + infobox data.
    """
    # Search for the page
    search_resp = requests.get(
        WIKI_SEARCH,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"{name} boxer",
            "format": "json",
            "srlimit": 3
        }
    )
    results = search_resp.json().get("query", {}).get("search", [])
    if not results:
        return {}
    
    # Get the top result
    page_title = results[0]["title"]
    
    # Fetch the full summary
    summary_resp = requests.get(f"{WIKI_API}/page/summary/{page_title.replace(' ', '_')}")
    if summary_resp.status_code == 200:
        return summary_resp.json()
    return {}

@st.cache_data(ttl=604800)
def get_fighter_infobox(name: str) -> dict:
    """
    Scrape the Wikipedia infobox for structured fighter data.
    Returns dict with height, reach, stance, nationality, birth_date etc.
    """
    search_resp = requests.get(
        WIKI_SEARCH,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"{name} professional boxer",
            "format": "json",
            "srlimit": 1
        }
    )
    results = search_resp.json().get("query", {}).get("search", [])
    if not results:
        return {}
    
    page_title = results[0]["title"]
    
    # Get raw wikitext to parse infobox
    wikitext_resp = requests.get(
        WIKI_SEARCH,
        params={
            "action": "query",
            "titles": page_title,
            "prop": "revisions",
            "rvprop": "content",
            "format": "json",
            "rvslots": "main"
        }
    )
    
    pages = wikitext_resp.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()))
    
    try:
        content = page["revisions"][0]["slots"]["main"]["*"]
    except (KeyError, IndexError):
        return {}
    
    # Parse key fields from infobox using regex
    info = {}
    patterns = {
        "height": r"\|\s*height\s*=\s*(.+?)(?:\n|\|)",
        "reach": r"\|\s*reach\s*=\s*(.+?)(?:\n|\|)",
        "stance": r"\|\s*stance\s*=\s*(.+?)(?:\n|\|)",
        "birth_date": r"\|\s*birth_date\s*=\s*(.+?)(?:\n|\|)",
        "nationality": r"\|\s*nationality\s*=\s*(.+?)(?:\n|\|)",
        "birth_place": r"\|\s*birth_place\s*=\s*(.+?)(?:\n|\|)",
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            # Clean wiki markup
            val = re.sub(r'\{\{.*?\}\}', '', match.group(1)).strip()
            val = re.sub(r'\[\[.*?\]\]', '', val).strip()
            info[key] = val
    
    info["name"] = name
    info["wiki_title"] = page_title
    return info

@st.cache_data(ttl=604800)
def get_title_holders_by_division(division: str) -> list:
    """
    Scrape Wikipedia's list of world champions for a division.
    Useful to build title lineage from 2015 onward.
    
    Example divisions: 'heavyweight', 'welterweight', 'lightweight'
    """
    page_title = f"List_of_world_{division.lower()}_boxing_champions"
    
    resp = requests.get(
        WIKI_SEARCH,
        params={
            "action": "query",
            "titles": page_title,
            "prop": "revisions",
            "rvprop": "content",
            "format": "json",
            "rvslots": "main"
        }
    )
    
    pages = resp.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()))
    
    try:
        content = page["revisions"][0]["slots"]["main"]["*"]
        # Content has table rows with champion name, dates, etc.
        # Further parsing needed based on division's table format
        return [{"raw_content": content[:500], "division": division}]
    except (KeyError, IndexError):
        return []

# Usage example in Streamlit
def enrich_fighter_from_wiki(fighter_name: str) -> dict:
    """Combine wiki summary + infobox into one enriched fighter dict."""
    summary = get_fighter_wiki_summary(fighter_name)
    infobox = get_fighter_infobox(fighter_name)
    
    return {
        "name": fighter_name,
        "wiki_description": summary.get("extract", "")[:500],
        "thumbnail": summary.get("thumbnail", {}).get("source"),
        "wiki_url": summary.get("content_urls", {}).get("desktop", {}).get("page"),
        **infobox
    }
```

---

## Source 4: Kaggle Datasets ✅ Best Cold-Start Option

Download these once to seed your database. They're static but cover 2015+ well and are perfect for training early model versions before your live pipeline is built.

### Dataset 1: Boxing Matches (mexwell)
**URL:** https://www.kaggle.com/datasets/mexwell/boxing-matches
**Contains:** Fight results, fighters, dates, methods

### Dataset 2: BoxByNumbers Boxing Data (CompuBox stats)
**URL:** https://www.kaggle.com/datasets/omarrojasnguyen/boxbynumbers-boxing-data
**Contains:** Punch stats for major fighters including Canelo, Inoue, Usyk, Crawford

### Dataset 3: Boxing Matches - Predict the Winner
**URL:** https://www.kaggle.com/datasets/iyadelwy/boxing-matches-dataset-predict-winner
**Contains:** Historical matchup data formatted for ML

```python
# data/load_kaggle_data.py
"""
Run this script ONCE to load Kaggle CSV files into your PostgreSQL DB.
Download CSVs manually from Kaggle and place in ./data/raw/
"""
import pandas as pd
import psycopg2
import os

def load_boxing_matches_csv(csv_path: str, db_conn):
    """Load the boxing-matches Kaggle dataset into fights table."""
    df = pd.read_csv(csv_path)
    
    # Normalize column names (vary by dataset)
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    
    print(f"Loaded {len(df)} rows from {csv_path}")
    print(f"Columns: {df.columns.tolist()}")
    print(df.head(2))
    
    # Insert into DB — adjust column mapping based on actual CSV structure
    for _, row in df.iterrows():
        try:
            db_conn.execute("""
                INSERT INTO fights_kaggle (
                    fighter_a, fighter_b, fight_date, result, method,
                    round_ended, weight_class, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                row.get("fighter_a") or row.get("boxer_a") or row.get("home"),
                row.get("fighter_b") or row.get("boxer_b") or row.get("away"),
                row.get("date") or row.get("fight_date"),
                row.get("result") or row.get("winner"),
                row.get("method") or row.get("decision"),
                row.get("round") or row.get("rounds"),
                row.get("weight_class") or row.get("division"),
                os.path.basename(csv_path)
            ))
        except Exception as e:
            pass  # Skip malformed rows
    
    db_conn.commit()
    print("Done loading CSV.")

def load_compubox_csv(csv_path: str, db_conn):
    """Load BoxByNumbers CompuBox stats CSV."""
    df = pd.read_csv(csv_path)
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    
    for _, row in df.iterrows():
        try:
            db_conn.execute("""
                INSERT INTO fight_stats_kaggle (
                    fighter, opponent, fight_date,
                    total_thrown, total_landed, jabs_thrown, jabs_landed,
                    power_thrown, power_landed, source
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'kaggle_boxbynumbers')
                ON CONFLICT DO NOTHING
            """, (
                row.get("fighter"),
                row.get("opponent"),
                row.get("date"),
                row.get("total_thrown") or row.get("total_punches_thrown"),
                row.get("total_landed") or row.get("total_punches_landed"),
                row.get("jabs_thrown"),
                row.get("jabs_landed"),
                row.get("power_thrown"),
                row.get("power_landed"),
            ))
        except Exception:
            pass
    
    db_conn.commit()

# Run once:
# conn = psycopg2.connect(os.environ["DATABASE_URL"])
# load_boxing_matches_csv("data/raw/boxing_matches.csv", conn)
# load_compubox_csv("data/raw/boxbynumbers.csv", conn)
```

---

## Source 5: Box.Live Scraper ⚠️ Moderate Risk

**Historical depth:** ~2010+, active fighters primarily. Fighter profiles with stats, stance, reach, win rates.

**Feasibility:** Public tutorials (as recently as December 2024) demonstrate successful scraping using `requests` + `BeautifulSoup`. No explicit ToS ban found. Use respectfully with delays.

**What it has:** Height, reach, stance, win/loss/draw record, KO %, debut year, weight class, rankings.

```python
# data/boxlive_scraper.py
"""
Scraper for Box.Live fighter profiles.
Use with delays and respect robots.txt.
This is supplemental data only — don't hammer the site.
"""
import requests
from bs4 import BeautifulSoup
import time
import re
import streamlit as st

BOXLIVE_BASE = "https://box.live"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BoxingResearchBot/1.0; +personal-project)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def search_boxer_boxlive(name: str) -> list:
    """Search Box.Live for a boxer and return profile URLs."""
    query = name.replace(" ", "+")
    resp = requests.get(
        f"{BOXLIVE_BASE}/en/boxers",
        params={"q": query},
        headers=HEADERS,
        timeout=10
    )
    
    if resp.status_code != 200:
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Find boxer links — inspect Box.Live HTML to confirm selector
    results = []
    for link in soup.select("a[href*='/en/boxer/']"):
        results.append({
            "name": link.get_text(strip=True),
            "url": BOXLIVE_BASE + link["href"]
        })
    
    return results[:5]  # top 5 results

def scrape_boxer_profile(profile_url: str) -> dict:
    """
    Scrape a boxer's profile page from Box.Live.
    Returns structured dict with stats.
    """
    time.sleep(1.5)  # polite delay between requests
    
    resp = requests.get(profile_url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}", "url": profile_url}
    
    soup = BeautifulSoup(resp.text, "html.parser")
    data = {"url": profile_url}
    
    # Extract name
    name_el = soup.select_one("h1.boxer-name, .fighter-name, h1")
    if name_el:
        data["name"] = name_el.get_text(strip=True)
    
    # Extract record (e.g. "30-1-0")
    record_el = soup.select_one(".boxer-record, .record, [class*='record']")
    if record_el:
        record_text = record_el.get_text(strip=True)
        match = re.search(r"(\d+)-(\d+)-(\d+)", record_text)
        if match:
            data["wins"] = int(match.group(1))
            data["losses"] = int(match.group(2))
            data["draws"] = int(match.group(3))
    
    # Extract physical stats from a stats table
    stats_els = soup.select(".stat-row, .boxer-stat, [class*='stat']")
    for el in stats_els:
        text = el.get_text(strip=True).lower()
        if "height" in text:
            data["height"] = re.search(r"[\d.]+\s*cm", text, re.I)
            if data["height"]:
                data["height"] = data["height"].group()
        elif "reach" in text:
            data["reach"] = re.search(r"[\d.]+\s*cm", text, re.I)
            if data["reach"]:
                data["reach"] = data["reach"].group()
        elif "stance" in text:
            if "orthodox" in text:
                data["stance"] = "Orthodox"
            elif "southpaw" in text:
                data["stance"] = "Southpaw"
    
    # Extract recent fights table
    fights = []
    fight_rows = soup.select("table.fights tbody tr, .fight-row")
    for row in fight_rows[:20]:  # last 20 fights
        cells = row.select("td")
        if len(cells) >= 4:
            fights.append({
                "date": cells[0].get_text(strip=True) if len(cells) > 0 else "",
                "opponent": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                "result": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                "method": cells[3].get_text(strip=True) if len(cells) > 3 else "",
            })
    
    data["recent_fights"] = fights
    return data

def batch_scrape_fighters(fighter_names: list, delay: float = 2.0) -> list:
    """
    Scrape multiple fighters with polite delays.
    Only run this for a targeted list, not a broad crawl.
    """
    results = []
    for name in fighter_names:
        print(f"Scraping: {name}")
        profiles = search_boxer_boxlive(name)
        if profiles:
            data = scrape_boxer_profile(profiles[0]["url"])
            data["search_name"] = name
            results.append(data)
        else:
            results.append({"search_name": name, "error": "Not found"})
        time.sleep(delay)
    return results

# Usage:
# fighters = ["Canelo Alvarez", "Errol Spence Jr", "Terence Crawford", "Naoya Inoue"]
# profiles = batch_scrape_fighters(fighters)
```

---

## Source 6: ESPN Boxing Results Scraper ⚠️ Higher Risk

**Historical depth:** ~2005+, major fights. ESPN has comprehensive result archives.

**Risk level:** ESPN's ToS prohibits scraping, but the results data itself is widely public. Use sparingly — this is for one-time historical backfill only, not a production pipeline.

**What it has:** Fight results, cards, basic fighter records. **No punch stats.**

```python
# data/espn_scraper.py
"""
ONE-TIME USE ONLY for historical backfill.
Do not use this as a recurring production scraper.
ESPN ToS prohibits scraping — use this only to seed your DB.
"""
import requests
from bs4 import BeautifulSoup
import time
import re

ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

def scrape_espn_boxing_results(year: int, month: int) -> list:
    """
    Scrape ESPN boxing results for a given month/year.
    Returns list of fight result dicts.
    
    Use for 2015-2020 historical backfill only.
    """
    url = f"https://www.espn.com/boxing/schedule/_/year/{year}/month/{month}"
    
    time.sleep(2)
    resp = requests.get(url, headers=ESPN_HEADERS, timeout=15)
    
    if resp.status_code != 200:
        print(f"ESPN returned {resp.status_code} for {year}/{month}")
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    fights = []
    
    # ESPN uses table or card layouts for schedules/results
    # Inspect the actual page HTML to confirm these selectors
    event_rows = soup.select(".Schedule__Table tbody tr, .event__row")
    
    for row in event_rows:
        cells = row.select("td")
        if len(cells) < 3:
            continue
        
        fight = {
            "date": cells[0].get_text(strip=True) if cells else "",
            "fighters": cells[1].get_text(strip=True) if len(cells) > 1 else "",
            "result": cells[2].get_text(strip=True) if len(cells) > 2 else "",
            "source": "espn"
        }
        fights.append(fight)
    
    return fights

def backfill_espn_2015_to_2020(db_conn):
    """
    Run ONCE to pull ESPN results from 2015–2020.
    After this, use boxing-data.com API for ongoing data.
    """
    from itertools import product
    
    years = range(2015, 2021)
    months = range(1, 13)
    
    all_fights = []
    for year, month in product(years, months):
        print(f"Fetching ESPN: {year}/{month}")
        fights = scrape_espn_boxing_results(year, month)
        all_fights.extend(fights)
        time.sleep(3)  # very polite delay
    
    print(f"Total fights found: {len(all_fights)}")
    
    for fight in all_fights:
        try:
            db_conn.execute("""
                INSERT INTO fights_raw (fighters_text, fight_date, result_text, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (fight["fighters"], fight["date"], fight["result"], "espn"))
        except Exception:
            pass
    
    db_conn.commit()
```

---

## Source 7: BoxRec ❌ Do Not Use for Production

BoxRec has the most comprehensive boxing data in the world — every pro fight ever recorded, going back to the 1800s. However:

- Their ToS **explicitly** prohibits scraping since 2018
- The primary Node.js scraper package (`boxing/boxrec`) is **officially broken** as of 2022+ due to captchas
- All Python wrappers are outdated and unmaintained
- The maintainer of the main package has stated: *"Do not expect this package to continuously work"*

**Bottom line:** BoxRec is not viable for a production pipeline. The APIs above give you sufficient data for major fights. Use BoxRec manually via browser for one-off research on obscure fighters.

```python
# REFERENCE ONLY — do not use for production

# The official boxing/boxrec npm package (Node.js) status as of 2025:
# - Requires BoxRec account credentials
# - Captchas frequently block automated access
# - Puppeteer headless workaround is not reliably working
# - From the repo README: "not working, or working very poorly"

# If you want to attempt it manually for a one-time data pull:
# 1. Create a BoxRec account at boxrec.com (free)
# 2. Use Playwright (Python) to log in and scrape specific fighter pages
# 3. Expect IP blocks after ~50-100 requests without proxies
# 4. Never automate this against their ToS at scale

# Playwright login skeleton (use with extreme caution):
"""
from playwright.async_api import async_playwright

async def boxrec_login_attempt(username, password):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # not headless - needs captcha solve
        page = await browser.new_page()
        await page.goto("https://boxrec.com/en/login")
        await page.fill("#username", username)
        await page.fill("#password", password)
        # MUST solve captcha manually or via service
        # ...
"""
```

---

## Putting It All Together: Data Pipeline for Streamlit

### Recommended Layered Strategy

```
Layer 1 (Cold Start — do once):
  → Download Kaggle CSVs and load into PostgreSQL
  → Pull Wikipedia infobox data for all known fighters

Layer 2 (Historical Backfill — do once):
  → Paginate boxing-data.com /fights/ endpoint for full archive
  → Pull TheSportsDB season-by-season from 2015 to 2024
  → Use Box.Live scraper for any fighter profiles not in APIs

Layer 3 (Ongoing Updates — weekly cron):
  → boxing-data.com /fights/schedule/ for new results
  → The Odds API for upcoming fight odds
  → OddsPapi for Pinnacle reference lines

Layer 4 (On-Demand — per fight):
  → boxing-data.com /fights/{id}/stats/ for punch data after each fight
  → Wikipedia for new fighter enrichment
```

### Pipeline Script for Streamlit App

```python
# scheduler.py — run via APScheduler in the background
"""
Runs alongside the Streamlit app. Polls for new data and updates DB.
Start with: python scheduler.py &
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from data.boxing_data_client import get_all_fights
from data.thesportsdb_client import get_past_events_by_league
import psycopg2
import os

scheduler = BlockingScheduler()

@scheduler.scheduled_job("cron", hour=6, minute=0)  # 6 AM daily
def daily_fight_results_update():
    """Pull any new fight results from the past 7 days."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    # Fetch latest page from boxing-data.com
    data = get_all_fights(page=1)
    fights = data.get("results", [])
    for fight in fights:
        # Only insert if fight_date > 7 days ago and not already stored
        conn.execute("""
            INSERT INTO fights (external_id, fight_date, ...)
            VALUES (%s, %s, ...)
            ON CONFLICT (external_id) DO NOTHING
        """, ...)
    conn.commit()
    conn.close()
    print(f"Daily update: {len(fights)} fights checked")

@scheduler.scheduled_job("interval", minutes=60)  # every hour
def hourly_odds_update():
    """Poll The Odds API for fresh DK lines."""
    from data.odds_api_client import get_dk_boxing_odds
    # Refresh odds for upcoming fights
    odds = get_dk_boxing_odds(os.environ["ODDS_API_KEY"])
    # Store snapshots...
    print(f"Odds updated: {len(odds)} fights")

if __name__ == "__main__":
    print("Starting boxing data scheduler...")
    scheduler.start()
```

---

## Estimated Data Volume After Full Backfill

| Source | Fights (2015–2025) | Fighters | Punch Stats |
|---|---|---|---|
| boxing-data.com (paid tier) | ~3,000–5,000 major bouts | ~5,000+ profiles | Yes (major fights) |
| TheSportsDB | ~2,000–4,000 results | ~2,000 profiles | No |
| Kaggle CSVs | ~5,000–15,000 (all levels) | ~8,000 | Partial (BoxByNumbers) |
| Box.Live scraper | N/A (fighter profiles) | ~3,000 active | No |
| **Combined** | **~10,000–20,000 fights** | **~10,000 fighters** | **~500–2,000 fights** |

Note: CompuBox punch data is the scarcest resource — it exists primarily for major televised fights. Expect full punch stats for ~10–20% of all fights in your database.

---

## Required Packages

```
# requirements.txt additions for data pipeline
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=5.0.0            # faster HTML parser for BeautifulSoup
playwright>=1.40.0     # only if using Box.Live or BoxRec scraping
apscheduler>=3.10.0    # background scheduler
pandas>=2.0.0
psycopg2-binary>=2.9.0
python-dotenv>=1.0.0
```

Install Playwright browsers (one-time):
```bash
playwright install chromium
```

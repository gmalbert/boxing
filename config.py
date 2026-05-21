"""
KnockOutIQ — Configuration & Environment Variable Management
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from repo root
_ROOT = Path(__file__).parent
load_dotenv(_ROOT / ".env")

# ─── API Keys ────────────────────────────────────────────────────────────────
RAPID_API_KEY: str = os.getenv("RAPID_API_KEY", "")
ODDS_API_KEY: str = os.getenv("ODDS_API_KEY", "")
ODDSPAPI_KEY: str = os.getenv("ODDSPAPI_API_KEY", "")

# BoxRec credentials (for historical fight scraping)
BOXREC_USERNAME: str = os.getenv("BOXREC_USERNAME", "")
BOXREC_PASSWORD: str = os.getenv("BOXREC_PASSWORD", "")

# ─── API Hosts ────────────────────────────────────────────────────────────────
BOXING_DATA_HOST = "boxing-data-api.p.rapidapi.com"
BOXING_DATA_BASE_URL = f"https://{BOXING_DATA_HOST}"
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
ODDSPAPI_BASE_URL = "https://api.oddspapi.io/v1"
SPORTS_DB_BASE_URL = "https://www.thesportsdb.com/api/v1/json/3"

# ─── Database ─────────────────────────────────────────────────────────────────
DB_PATH = _ROOT / "data_files" / "knockoutiq.db"
DB_URL = f"sqlite:///{DB_PATH}"

# ─── Thresholds ───────────────────────────────────────────────────────────────
# Minimum edge (model_prob - dk_implied_prob) to flag as a potential bet
EDGE_STRONG_THRESHOLD = 0.05   # 5%+ → strong edge (green)
EDGE_WEAK_THRESHOLD = 0.02     # 2-5% → marginal edge (yellow)

# ─── App Branding ─────────────────────────────────────────────────────────────
APP_TITLE = "KnockOutIQ"
APP_ICON = "🥊"
APP_SUBTITLE = "Boxing Analytics & Betting Intelligence"

# ─── Historical Data ──────────────────────────────────────────────────────────
HISTORY_YEARS = 10   # how many years back to pull on initial backfill

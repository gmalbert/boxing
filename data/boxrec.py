"""
KnockOutIQ — BoxRec Scraper
============================
Scrapes fight results and fighter profiles from boxrec.com.

Requires a free BoxRec account. Set BOXREC_USERNAME and BOXREC_PASSWORD
in your .env file (see .env.example).

BoxRec requires login to view any useful data. This module implements:
  - BoxRecSession.login()                  — authenticate with CSRF-token POST
  - BoxRecSession.get_top_boxer_ids()      — top-rated active pros per division
  - BoxRecSession.get_boxer_bouts()        — full bout history for one fighter
  - BoxRecSession.get_event_ids_for_year() — event IDs from the schedule page
  - BoxRecSession.get_event_bouts()        — all fights on one event card

Rate limiting: 2 s between every request. BoxRec will temporarily block IPs
that hammer them, so be polite.
"""

from __future__ import annotations

import logging
import pathlib
import re
import time
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlencode, quote

import requests
from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)

BOXREC_BASE = "https://boxrec.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": BOXREC_BASE,
}

_RATE_SECONDS = 4.0  # polite minimum gap between HTTP requests

# All professional weight divisions recognised by BoxRec
DIVISIONS = [
    "Heavyweight",
    "Cruiserweight",
    "Light Heavyweight",
    "Super Middleweight",
    "Middleweight",
    "Super Welterweight",
    "Welterweight",
    "Super Lightweight",
    "Lightweight",
    "Super Featherweight",
    "Featherweight",
    "Super Bantamweight",
    "Bantamweight",
    "Super Flyweight",
    "Flyweight",
    "Super Minimumweight",
    "Minimumweight",
]

# Canonical method abbreviations
_VALID_METHODS = {"KO", "TKO", "UD", "MD", "SD", "RTD", "DQ", "NC", "DRAW", "TD"}

# Map BoxRec's "outcome" text to our method codes
_METHOD_MAP = {
    "ko": "KO",
    "tko": "TKO",
    "pts": "UD",
    "ud": "UD",
    "md": "MD",
    "sd": "SD",
    "rtd": "RTD",
    "ret": "RTD",
    "dq": "DQ",
    "disq": "DQ",
    "nc": "NC",
    "draw": "DRAW",
    "td": "TD",
    # spelled-out variants
    "knockout": "KO",
    "technical knockout": "TKO",
    "unanimous decision": "UD",
    "majority decision": "MD",
    "split decision": "SD",
    "retired": "RTD",
    "disqualification": "DQ",
    "no contest": "NC",
    "technical decision": "TD",
}

# Map BoxRec result text to our result codes ('A'=boxer A won, 'B'=boxer B won)
_RESULT_MAP = {
    "win": "A",
    "w": "A",
    "loss": "B",
    "l": "B",
    "lose": "B",
    "draw": "draw",
    "d": "draw",
    "nc": "NC",
    "no contest": "NC",
}


# ─── Session ──────────────────────────────────────────────────────────────────

def _chrome_major_version() -> int | None:
    """
    Detect the major version of the installed Google Chrome on Windows/Mac/Linux.
    Returns an int like 148, or None if detection fails.
    """
    import subprocess, re as _re, sys as _sys

    candidates: list[list[str]] = []

    if _sys.platform == "win32":
        # 1. Windows registry (most reliable)
        try:
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for sub in (
                    r"Software\Google\Chrome\BLBeacon",
                    r"Software\Wow6432Node\Google\Chrome\BLBeacon",
                ):
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            ver, _ = winreg.QueryValueEx(k, "version")
                            m = _re.match(r"(\d+)", ver)
                            if m:
                                return int(m.group(1))
                    except OSError:
                        pass
        except ImportError:
            pass
        # 2. Try the standard install paths
        import os
        for p in (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ):
            if os.path.exists(p):
                candidates.append([p, "--version"])
    elif _sys.platform == "darwin":
        candidates.append([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "--version",
        ])
    else:
        candidates.append(["google-chrome", "--version"])
        candidates.append(["chromium-browser", "--version"])
        candidates.append(["chromium", "--version"])

    for cmd in candidates:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=5).decode()
            m = _re.search(r"(\d+)\.", out)
            if m:
                return int(m.group(1))
        except Exception:
            pass

    return None


def _extract_browser_major_from_error(message: str) -> int | None:
    """Extract installed browser major version from Selenium mismatch errors."""
    m = re.search(r"Current browser version is\s+(\d+)\.", message)
    if m:
        return int(m.group(1))
    return None


class BoxRecSession:
    """
    Browser-based BoxRec session using undetected-chromedriver.

    BoxRec sits behind Cloudflare's JS challenge which blocks all plain HTTP
    clients (requests, httpx, curl-cffi).  undetected-chromedriver patches
    ChromeDriver so Chrome's automation flag is hidden from CF's bot detection,
    then we navigate the real browser to execute the CF challenge and log in.

    Usage::

        with BoxRecSession() as br:
            if br.login(username, password):
                ids = br.get_top_boxer_ids("Heavyweight")
                bouts = br.get_boxer_bouts(ids[0])

    Requires Chrome to be installed on the system.
    For GitHub Actions use 'headless=True' (default).
    """

    def __init__(self, headless: bool = False) -> None:
        import undetected_chromedriver as uc
        from selenium.common.exceptions import SessionNotCreatedException

        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=en-US")
        if headless:
            options.add_argument("--headless=new")

        # Pin ChromeDriver to match the installed Chrome version to avoid
        # "session not created: This version of ChromeDriver only supports
        # Chrome version N" mismatches.
        chrome_ver = _chrome_major_version()
        if chrome_ver:
            log.info("Detected Chrome %d — using matching ChromeDriver.", chrome_ver)
        else:
            log.warning(
                "Could not detect Chrome version — "
                "undetected_chromedriver will pick the latest ChromeDriver "
                "(may mismatch if Chrome is not current)."
            )

        try:
            self.driver = uc.Chrome(
                options=options,
                headless=headless,
                version_main=chrome_ver,
            )
        except SessionNotCreatedException as exc:
            detected_from_error = _extract_browser_major_from_error(str(exc))
            if detected_from_error and detected_from_error != chrome_ver:
                log.warning(
                    "ChromeDriver mismatch detected. Retrying with browser major "
                    "version %d.",
                    detected_from_error,
                )
                self.driver = uc.Chrome(
                    options=options,
                    headless=headless,
                    version_main=detected_from_error,
                )
            else:
                raise
        self._last_req: float = 0.0
        self.logged_in: bool = False
        # Let the browser finish initialising before the first navigation
        time.sleep(3)

    # ── Context-manager support ───────────────────────────────────────────────

    def __enter__(self) -> "BoxRecSession":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_req
        if elapsed < _RATE_SECONDS:
            time.sleep(_RATE_SECONDS - elapsed)
        self._last_req = time.monotonic()

    # CF challenge phrases — any of these means a challenge is still in progress
    _CF_PHRASES = (
        "just a moment",
        "checking your browser",
        "verifying you are human",
        "please wait",
        "enable javascript and cookies",
        "ddos-guard",
    )

    def _cf_active(self) -> bool:
        """Return True if the current page looks like an active CF challenge."""
        src = self.driver.page_source.lower()
        return any(phrase in src for phrase in self._CF_PHRASES)

    def _recaptcha_active(self) -> bool:
        """Return True if we've been redirected to BoxRec's rate-limit/recaptcha page."""
        return "recaptcha" in self.driver.current_url.lower()

    def _wait_for_recaptcha_clear(self, timeout: int = 300) -> bool:
        """
        If the browser is on BoxRec's /recaptcha page (Too many requests),
        pause and wait for the user to solve it in the visible browser window.

        timeout: seconds to wait before giving up (default 5 min).
        Returns True if the page cleared, False on timeout.
        """
        if not self._recaptcha_active():
            return True

        log.warning(
            "\n"
            "=" * 60 + "\n"
            "BoxRec CAPTCHA / rate-limit detected!\n"
            "Please solve the CAPTCHA in the browser window.\n"
            "The script will continue automatically once it's cleared.\n"
            "You have %d seconds.\n"
            "=" * 60,
            timeout,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(3)
            if not self._recaptcha_active():
                log.info("BoxRec: CAPTCHA cleared — resuming.")
                time.sleep(2)  # brief settle
                return True
        log.error("BoxRec: CAPTCHA not solved within %d s — giving up.", timeout)
        return False

    def _navigate(self, url: str) -> BeautifulSoup:
        """
        Navigate to *url* with the browser, wait for any Cloudflare challenge
        to clear (up to 60 s), then return a BeautifulSoup of the final page.
        Raises RuntimeError if a BoxRec recaptcha/rate-limit page blocks us.
        """
        self._throttle()
        self.driver.get(url)
        # Poll until all known CF challenge phrases are gone, or timeout
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if not self._cf_active():
                break
            time.sleep(1)
        # Check for BoxRec rate-limit / recaptcha redirect
        if self._recaptcha_active():
            if not self._wait_for_recaptcha_clear():
                raise RuntimeError("BoxRec rate-limited (recaptcha not solved)")
        # Give JS an extra moment to finish rendering dynamic content
        time.sleep(2)
        return BeautifulSoup(self.driver.page_source, "lxml")

    # ── Public API ────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> bool:
        """
        Log in to BoxRec by filling and submitting the login form in the browser.
        Returns True if the session appears authenticated.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        self._throttle()
        self.driver.get(f"{BOXREC_BASE}/en/login")

        # If BoxRec immediately redirects to recaptcha (rate-limited), pause for human solve
        if self._recaptcha_active():
            if not self._wait_for_recaptcha_clear():
                log.error("BoxRec: rate-limited at login — recaptcha not solved")
                return False

        # Wait up to 90 s for the login form to appear — this implicitly
        # waits for any CF challenge to clear regardless of its exact text.
        try:
            wait = WebDriverWait(self.driver, 90)
            ufield = wait.until(
                EC.presence_of_element_located((By.NAME, "_username"))
            )
        except Exception:
            log.error("BoxRec: login form not found after 90 s (CF challenge / IP block?)")
            return False

        try:
            ufield.clear()
            ufield.send_keys(username)

            pfield = self.driver.find_element(By.NAME, "_password")
            pfield.clear()
            pfield.send_keys(password)
            pfield.submit()

            time.sleep(3)

            # BoxRec may redirect to recaptcha after login (still rate-limited)
            if self._recaptcha_active():
                if not self._wait_for_recaptcha_clear():
                    log.error("BoxRec: rate-limited after login submit — recaptcha not solved")
                    return False

            # BoxRec may redirect to a GDPR consent gate after login
            if "gdpr_consent" in self.driver.current_url:
                log.info("BoxRec: GDPR consent required — accepting...")
                self.driver.get(f"{BOXREC_BASE}/en/gdpr_accept")
                time.sleep(2)

        except Exception as exc:
            log.error("BoxRec: login form interaction failed: %s", exc)
            return False

        src_lower = self.driver.page_source.lower()
        current_url = self.driver.current_url
        # Must NOT be on the recaptcha page; must have logout link or username visible
        if self._recaptcha_active():
            log.error("BoxRec: still on recaptcha page after login (url=%s)", current_url)
            return False
        self.logged_in = (
            "logout" in src_lower
            or "/en/logout" in src_lower
            or (username.lower() in src_lower)
        )
        if self.logged_in:
            log.info("BoxRec: login OK (user=%s, url=%s)", username, current_url)
        else:
            # Save the page so we can inspect what BoxRec returned
            debug_path = pathlib.Path("data_files") / "debug_login_fail.html"
            try:
                debug_path.write_text(self.driver.page_source, encoding="utf-8")
                log.error(
                    "BoxRec: login failed — page saved to %s  (url=%s)",
                    debug_path, current_url,
                )
            except Exception:
                log.error("BoxRec: login failed (url=%s)", current_url)
        return self.logged_in

    def get_top_boxer_ids(
        self, division: str, limit: int = 50, status: str = "a"
    ) -> list[str]:
        """
        Return BoxRec fighter IDs for the top-ranked active pros in *division*.

        status='a' → active; status='all' → include inactive/retired.
        Paginates automatically until *limit* is reached.
        """
        ids: list[str] = []
        page = 1

        while len(ids) < limit:
            params = {
                "division": division,
                "status": status,
                "sex": "M",
                "country": "",
                "stance": "",
                "page": page,
            }
            url = f"{BOXREC_BASE}/en/ratings?{urlencode(params)}"
            log.debug("BoxRec ratings URL: %s", url)
            try:
                soup = self._navigate(url)
            except Exception as exc:
                log.warning("BoxRec ratings (div=%s, p=%d) failed: %s", division, page, exc)
                break

            # Log the actual URL BoxRec settled on (detects redirects / param changes)
            actual_url = self.driver.current_url
            if page == 1:
                log.info("BoxRec ratings actual URL (div=%s): %s", division, actual_url)
                # Save first-page HTML for offline analysis (first division only, once)
                _debug_ratings = pathlib.Path("data_files") / f"debug_ratings_{division.replace(' ', '_')}.html"
                if not _debug_ratings.exists():
                    try:
                        _debug_ratings.write_text(self.driver.page_source, encoding="utf-8")
                        log.info("BoxRec: saved ratings debug HTML → %s", _debug_ratings)
                    except Exception:
                        pass

            rows = (
                soup.select("table.dataTable tbody tr")
                or soup.select("#ratingsList tbody tr")
                or soup.select("table tbody tr")
            )
            if not rows:
                title_tag = soup.find("title")
                log.warning(
                    "BoxRec ratings (div=%s, p=%d): 0 rows found — page title=%r",
                    division, page, title_tag.get_text(strip=True) if title_tag else "n/a",
                )
                break

            found_this_page = 0
            for row in rows:
                link = row.find("a", href=re.compile(r"/en/box-pro/\d+"))
                if not link:
                    continue
                m = re.search(r"/en/box-pro/(\d+)", link["href"])
                if m and m.group(1) not in ids:
                    ids.append(m.group(1))
                    found_this_page += 1

            if found_this_page == 0:
                break

            next_link = soup.find(
                "a", string=re.compile(r"next\s*>*", re.I)
            ) or soup.find("a", {"rel": "next"})
            if not next_link or len(ids) >= limit:
                break
            page += 1

        return ids[:limit]

    def get_boxer_bouts(self, boxer_id: str | int) -> list[dict]:
        """
        Scrape the full bout history for one boxer.

        Returns a list of dicts with keys:
          fight_date, fighter_a (boxer's name), fighter_b (opponent),
          result ('A'/'B'/'draw'/'NC'), method, round_ended,
          total_rounds, weight_class, location, event_name, ext_id
        """
        try:
            soup = self._navigate(f"{BOXREC_BASE}/en/box-pro/{boxer_id}")
        except Exception as exc:
            log.warning("BoxRec: box-pro/%s failed: %s", boxer_id, exc)
            return []

        # Quick early check: if the page has no boxer name it's a login
        # redirect, paywall, or empty profile — don't burn 20 s waiting.
        boxer_name = _extract_boxer_name(soup)
        if not boxer_name:
            log.warning("BoxRec: no profile name for boxer %s — skipping", boxer_id)
            return []

        # BoxRec now uses a randomised table ID; the stable selector is class="dataTable".
        # Wait explicitly for that element before re-parsing.
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable"))
            )
            soup = BeautifulSoup(self.driver.page_source, "lxml")
        except Exception:
            # Table didn't appear within 20 s — use whatever we have
            pass

        # Refresh name from re-parsed soup; fall back to the one extracted earlier.
        boxer_name = _extract_boxer_name(soup) or boxer_name

        # BoxRec uses class="dataTable" with a per-page randomised id attribute.
        table = (
            soup.find("table", {"class": "dataTable"})
            or soup.find("table", {"id": "listBouts"})
            or soup.find("table", {"class": re.compile(r"bout", re.I)})
            or soup.find("table", {"class": re.compile(r"result", re.I)})
        )
        if not table:
            all_tables = soup.find_all("table")
            log.warning(
                "BoxRec: no bout table for boxer %s (%s) — "
                "%d tables on page, ids=%s classes=%s",
                boxer_id, boxer_name, len(all_tables),
                [t.get("id") for t in all_tables[:8]],
                [t.get("class") for t in all_tables[:8]],
            )
            return []

        bouts: list[dict] = []
        skipped = 0
        for row in table.select("tbody tr"):
            bout = _parse_boxer_bout_row(row, boxer_name, str(boxer_id))
            if bout:
                bouts.append(bout)
            else:
                skipped += 1

        log.info(
            "BoxRec: %s -> %d bouts parsed, %d rows skipped",
            boxer_name, len(bouts), skipped,
        )
        return bouts

    def get_boxer_id_by_name(self, name: str) -> str | None:
        """
        Search BoxRec for a boxer by name and return their numeric profile ID.

        Uses BoxRec's /en/search endpoint.  Returns the first result whose
        profile link matches the name, or None if no confident match is found.
        """
        parts = name.strip().split()
        first = parts[0] if parts else ""
        last = " ".join(parts[1:]) if len(parts) > 1 else ""
        tokens = [t.lower() for t in parts if len(t) >= 3]

        def _search_soup(status: str) -> "BeautifulSoup | None":
            qs = (
                f"p[first_name]={quote(first)}"
                f"&p[last_name]={quote(last)}"
                f"&p[role]=box-pro"
                f"&p[status]={status}"
            )
            url = f"{BOXREC_BASE}/en/search?{qs}"
            try:
                return self._navigate(url)
            except Exception as exc:
                log.warning("BoxRec search failed for %r: %s", name, exc)
                return None

        def _best_match(soup: "BeautifulSoup") -> str | None:
            """
            From a search results page, return the BoxRec ID of the best match:
            - Exact name match required (all tokens present in link text, ignoring '*').
            - BoxRec marks the currently-active boxer with a '*' suffix — prefer that.
            - Among inactive namesakes, prefer the one with the most recent activity:
              * 'Last Bout' column: YYYY-MM-DD  (full date, used as-is for sorting)
              * 'career' column:    YYYY-YYYY   (year range; end year used for sorting)
            """
            candidates: list[tuple[str, str]] = []  # (boxer_id, sortable_recency)

            for row in soup.select("table tr"):
                link = row.find("a", href=re.compile(r"/en/box-pro/\d+"))
                if not link:
                    continue
                # Strip the active-marker '*' before name matching
                link_text = link.get_text(strip=True).rstrip("*").lower()
                if not all(t in link_text for t in tokens):
                    continue
                m = re.search(r"/en/box-pro/(\d+)", link["href"])
                if not m:
                    continue
                boxer_id = m.group(1)
                is_active = link.get_text(strip=True).endswith("*")

                # Active boxer wins immediately
                if is_active:
                    log.info(
                        "BoxRec search: %r -> ID %s (active, marked with *)",
                        name, boxer_id,
                    )
                    return boxer_id

                # Extract recency from row cells
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                recency = ""
                for cell in cells:
                    # Full date: YYYY-MM-DD → sort directly (lexicographic works)
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", cell):
                        if cell > recency:
                            recency = cell
                    # Year range: YYYY-YYYY → use end year as YYYY-12-31
                    yr = re.search(r"-(\d{4})$", cell)
                    if yr:
                        proxy = f"{yr.group(1)}-12-31"
                        if proxy > recency:
                            recency = proxy

                candidates.append((boxer_id, recency))

            if not candidates:
                return None
            if len(candidates) == 1:
                return candidates[0][0]

            candidates.sort(key=lambda c: c[1], reverse=True)
            log.debug(
                "BoxRec search: %d candidates for %r — picking %s (recency %s)",
                len(candidates), name, candidates[0][0], candidates[0][1],
            )
            return candidates[0][0]

        # First pass: active-only (no duplicates, no stale namesakes).
        soup = _search_soup("a")
        if soup:
            boxer_id = _best_match(soup)
            if boxer_id:
                log.info("BoxRec search (active): %r -> ID %s", name, boxer_id)
                return boxer_id

        # Second pass: all statuses — pick the one with the most recent last bout.
        soup = _search_soup("")
        if soup:
            boxer_id = _best_match(soup)
            if boxer_id:
                log.info("BoxRec search (any status, most recent): %r -> ID %s", name, boxer_id)
                return boxer_id

        log.debug("BoxRec search: no match for %r", name)
        return None

    def get_event_ids_for_year(self, year: int) -> list[str]:
        """Return all BoxRec event IDs on the schedule/results page for *year*."""
        ids: list[str] = []
        url = (
            f"{BOXREC_BASE}/en/schedule?"
            f"sport=pro&status=results&year={year}"
        )
        try:
            soup = self._navigate(url)
        except Exception as exc:
            log.warning("BoxRec schedule/%d failed: %s", year, exc)
            return []

        for link in soup.find_all("a", href=re.compile(r"/en/event/\d+")):
            m = re.search(r"/en/event/(\d+)", link["href"])
            if m and m.group(1) not in ids:
                ids.append(m.group(1))

        log.info("BoxRec: found %d events for %d", len(ids), year)
        return ids

    def get_event_bouts(self, event_id: str | int) -> dict:
        """
        Scrape one event page and return all fight results.

        Returns::
          {event_id, name, date, venue, location, fights: [list of bout dicts]}
        """
        result: dict = {
            "event_id": str(event_id),
            "name": "",
            "date": None,
            "venue": "",
            "location": "",
            "fights": [],
        }

        try:
            soup = self._navigate(f"{BOXREC_BASE}/en/event/{event_id}")
        except Exception as exc:
            log.warning("BoxRec: event/%s failed: %s", event_id, exc)
            return result

        h1 = soup.find("h1")
        if h1:
            result["name"] = h1.get_text(strip=True)

        result["date"] = _find_date_in_soup(soup)

        for selector in ("td.venue", "span.venue", "div.venue",
                         "td.location", "span.location"):
            tag = soup.select_one(selector)
            if tag:
                result["venue"] = tag.get_text(strip=True)
                break

        fight_table = (
            soup.find("table", {"class": re.compile(r"result", re.I)})
            or soup.find("table", {"id": re.compile(r"event", re.I)})
            or soup.find("table", {"class": re.compile(r"bout", re.I)})
        )
        if fight_table:
            for row in fight_table.select("tbody tr"):
                bout = _parse_event_fight_row(
                    row,
                    event_name=result["name"],
                    event_date=result["date"],
                    venue=result["venue"],
                    location=result["location"],
                    event_id=str(event_id),
                )
                if bout:
                    result["fights"].append(bout)

        log.info(
            "BoxRec: event %s (%s) -> %d fights",
            event_id, result["name"], len(result["fights"])
        )
        return result


# ─── ESPN Unofficial API ──────────────────────────────────────────────────────

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/boxing/scoreboard"
)


def fetch_espn_events(year: int) -> list[dict]:
    """
    Pull boxing events from ESPN's unofficial scoreboard API for *year*.

    Returns a list of normalised bout dicts (same schema as BoxRec bouts).
    ESPN coverage is limited to major US-broadcast events but requires no auth.
    """
    start = f"{year}0101"
    end = f"{year}1231"
    bouts: list[dict] = []

    try:
        resp = requests.get(
            ESPN_SCOREBOARD,
            params={"dates": f"{start}-{end}", "limit": 200},
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("ESPN API (%d) failed: %s", year, exc)
        return []

    for event in data.get("events", []):
        bout = _parse_espn_event(event)
        if bout:
            bouts.append(bout)

    log.info("ESPN: %d events found for %d", len(bouts), year)
    return bouts


def _parse_espn_event(event: dict) -> dict | None:
    """Normalise one ESPN event dict into a standard bout dict."""
    try:
        competitions = event.get("competitions", [])
        if not competitions:
            return None
        comp = competitions[0]

        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        # Extract fighters — ESPN labels them home/away
        fa_data = next(
            (c for c in competitors if c.get("homeAway") == "home"), competitors[0]
        )
        fb_data = next(
            (c for c in competitors if c.get("homeAway") == "away"), competitors[1]
        )

        fa_name = (
            fa_data.get("athlete", {}).get("fullName")
            or fa_data.get("athlete", {}).get("displayName", "")
        ).strip()
        fb_name = (
            fb_data.get("athlete", {}).get("fullName")
            or fb_data.get("athlete", {}).get("displayName", "")
        ).strip()

        if not fa_name or not fb_name:
            return None

        # Date
        date_str = comp.get("startDate") or event.get("date", "")
        fight_date: date | None = None
        if date_str:
            try:
                fight_date = datetime.fromisoformat(
                    date_str.replace("Z", "+00:00")
                ).date()
            except ValueError:
                pass

        # Result
        status = comp.get("status", {}).get("type", {})
        completed = status.get("completed", False)
        result: str | None = None
        if completed:
            if fa_data.get("winner"):
                result = "A"
            elif fb_data.get("winner"):
                result = "B"
            else:
                result = "draw"

        # Venue
        venue_data = comp.get("venue", {})
        venue = venue_data.get("fullName", "")
        addr = venue_data.get("address", {})
        city = addr.get("city", "")
        state = addr.get("state", "")
        country = addr.get("country", "")
        location = ", ".join(filter(None, [city, state or country]))

        # Method — ESPN sometimes includes it in notes or score
        method = None
        for c in competitors:
            score_text = str(c.get("score", "")).upper()
            for abbr in ("KO", "TKO", "UD", "MD", "SD", "RTD", "DQ"):
                if abbr in score_text:
                    method = abbr
                    break

        event_id = f"espn_{event.get('id', '')}"
        return {
            "ext_id": event_id,
            "fight_date": fight_date,
            "fighter_a": fa_name,
            "fighter_b": fb_name,
            "result": result,
            "method": method,
            "round_ended": None,
            "total_rounds": 12,
            "weight_class": None,
            "venue": venue,
            "location": location,
            "event_name": event.get("name", ""),
            "title_fight": False,
            "sanctioning_body": None,
            "is_upcoming": not completed,
        }
    except Exception as exc:
        log.debug("ESPN event parse error: %s", exc)
        return None


# ─── HTML Parsing Helpers ─────────────────────────────────────────────────────

def _extract_boxer_name(soup: BeautifulSoup) -> str:
    """Try several selectors to find the fighter's name on their profile page."""
    for selector in (
        "span.fn",
        "h1",
        "div.personSectionBio_name",
        "div.title",
        ".boxerName",
    ):
        tag = soup.select_one(selector)
        if tag:
            name = tag.get_text(strip=True)
            if name:
                return name
    return ""


def _find_date_in_soup(soup: BeautifulSoup) -> Optional[date]:
    """Search the whole page for the first ISO date string."""
    for text in soup.find_all(string=re.compile(r"\b\d{4}-\d{2}-\d{2}\b")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", str(text))
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                pass
    return None


def _normalise_method(raw: str) -> Optional[str]:
    """Convert freeform method text to a canonical abbreviation."""
    key = raw.strip().lower()
    return _METHOD_MAP.get(key) or _METHOD_MAP.get(key.split()[0])


def _parse_cell_texts(row: Tag) -> list[str]:
    """Return stripped text content of every <td> in *row*."""
    return [td.get_text(strip=True) for td in row.find_all("td")]


def _parse_boxer_bout_row(row: Tag, boxer_name: str, boxer_id: str) -> Optional[dict]:
    """
    Parse one <tr> from the bout-history table on a BoxRec fighter profile page.

    Current BoxRec column layout (class="dataTable", 13 cells):
      td[0]  : empty / checkbox
      td[1]  : date YYYY-MM-DD  (link href /en/date?date=YYYY-MM-DD)
      td[2]  : boxer weight (lbs)
      td[3]  : empty
      td[4]  : opponent name  (link href /en/box-pro/<id>)
      td[5]  : opponent weight (lbs)
      td[6]  : opponent record (spans textWon/textLost/textDraw)
      td[7]  : empty
      td[8]  : venue / location
      td[9]  : result+method  e.g. "W-UD", "W-KO", "L-TKO", "D", "NC"
      td[10] : rounds  e.g. "12/12", "8/12"
      td[11] : empty
      td[12] : icon links (event / bout / score / wiki)

    "second" rows (id starts with "second") hold referee/judge details and
    must be skipped.
    """
    # Skip referee/judge detail rows
    row_id = str(row.get("id", ""))
    if row_id.startswith("second"):
        return None

    cells = row.find_all("td")
    if len(cells) < 10:  # main rows have 13 cells
        return None

    texts = [c.get_text(strip=True) for c in cells]

    # ── Date ──────────────────────────────────────────────────────────────────
    # td[1] is bare text YYYY-MM-DD; scan all texts for the pattern.
    fight_date: Optional[date] = None
    for text in texts:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            try:
                fight_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                pass
            break
    if fight_date is None:
        return None  # date is mandatory

    # ── Result + Method ───────────────────────────────────────────────────────
    # td[9] carries the compound result string: "W-UD", "W-KO", "L-TKO",
    # "W-MD", "D", "NC", etc.  Parse prefix for win/loss/draw, suffix for method.
    result_code: Optional[str] = None
    method: Optional[str] = None
    for text in texts:
        t = text.strip().upper()
        if not t:
            continue
        # Compound format: W-UD, L-KO, W-TKO, etc.
        cm = re.match(r'^([WLD])[-\s](\w+)$', t)
        if cm:
            prefix, meth_raw = cm.group(1), cm.group(2)
            result_code = "A" if prefix == "W" else ("B" if prefix == "L" else "draw")
            method = _METHOD_MAP.get(meth_raw.lower()) or meth_raw
            break
        # No-contest with suffix: NC-ND etc.
        if re.match(r'^NC', t):
            result_code = "NC"
            break
        # Bare single letter or word
        simple = _RESULT_MAP.get(t.lower())
        if simple:
            result_code = simple
            break
    # Fallback: scan span elements for class-based hints
    if result_code is None:
        for cell in cells:
            for span in cell.find_all("span"):
                cls = " ".join(span.get("class") or []).lower()
                if any(c in cls for c in ("win", "textwin")):
                    result_code = "A"
                    break
                if any(c in cls for c in ("loss", "textloss")):
                    result_code = "B"
                    break
                if "draw" in cls:
                    result_code = "draw"
                    break
            if result_code:
                break
    if result_code is None:
        return None  # can't use a fight without a result

    # ── Opponent ──────────────────────────────────────────────────────────────
    # td[4] has <a href="/en/box-pro/<id>">Name</a>
    opponent: Optional[str] = None
    for cell in cells:
        link = cell.find("a", href=re.compile(r"/en/box-pro/\d+"))
        if link:
            name = link.get_text(strip=True)
            # Strip trailing asterisk (title fight indicator) and whitespace
            name = name.rstrip("*").strip()
            if name and name != boxer_name:
                opponent = name
                break
    if not opponent:
        return None

    # ── Rounds ────────────────────────────────────────────────────────────────
    # td[10] format: "12/12", "8/12", "6/12"
    round_ended: Optional[int] = None
    total_rounds: int = 12
    for text in texts:
        rm = re.match(r'^(\d{1,2})/(\d{1,2})$', text.strip())
        if rm:
            round_ended = int(rm.group(1))
            total_rounds = int(rm.group(2))
            break
    # Fallback: bare integer for round
    if round_ended is None:
        for text in texts[5:]:
            if re.match(r'^\d{1,2}$', text.strip()):
                val = int(text.strip())
                if 1 <= val <= 15:
                    round_ended = val
                    break

    # ── Weight class ──────────────────────────────────────────────────────────
    weight_class: Optional[str] = None
    for text in texts:
        for div in DIVISIONS:
            if div.lower() in text.lower():
                weight_class = div
                break
        if weight_class:
            break

    # ── Location ──────────────────────────────────────────────────────────────
    # td[8] is the venue; it's the longest non-numeric, non-result text.
    location = ""
    skip_patterns = re.compile(
        r'^(\d+|\d+/\d+|\d{4}-\d{2}-\d{2}|[WLD][-\s]\w+|eventboutscorewiki)$',
        re.I,
    )
    for text in texts:
        t = text.strip()
        if t and len(t) > 4 and not skip_patterns.match(t):
            location = t
            break

    # ── External ID ───────────────────────────────────────────────────────────
    # BoxRec bout row IDs are numeric (e.g. "3571858") — use them directly.
    if re.match(r'^\d+$', row_id):
        ext_id = f"br_bout_{row_id}"
    else:
        ext_id = f"br_{boxer_id}_{fight_date.isoformat()}_{_slug(opponent)}"

    return {
        "ext_id": ext_id,
        "fight_date": fight_date,
        "fighter_a": boxer_name,
        "fighter_b": opponent,
        "result": result_code,
        "method": method,
        "round_ended": round_ended,
        "total_rounds": total_rounds,
        "weight_class": weight_class,
        "venue": "",
        "location": location,
        "event_name": "",
        "title_fight": False,
        "sanctioning_body": None,
        "is_upcoming": False,
    }


def _parse_event_fight_row(
    row: Tag,
    event_name: str,
    event_date: Optional[date],
    venue: str,
    location: str,
    event_id: str,
) -> Optional[dict]:
    """
    Parse one <tr> from a BoxRec event page fight card table.

    Event tables typically list:
      fighter_a | fighter_b | method | round | weight_class | scheduled
    or
      result | fighter_a | vs | fighter_b | method | round
    """
    cells = row.find_all("td")
    if len(cells) < 3:
        return None

    # Collect all <a href="/en/box-pro/..."> links → these are the fighters
    fighter_links = []
    for cell in cells:
        for link in cell.find_all("a", href=re.compile(r"/en/box-pro/\d+")):
            name = link.get_text(strip=True)
            if name:
                fighter_links.append(name)

    if len(fighter_links) < 2:
        return None

    fighter_a = fighter_links[0]
    fighter_b = fighter_links[1]

    texts = [c.get_text(strip=True) for c in cells]

    # ── Result ────────────────────────────────────────────────────────────────
    # On event pages BoxRec marks the winner with a CSS class or "W"/"L" text
    result_code: Optional[str] = None

    # Check for winner/loser CSS classes on cells containing fighter names
    for cell in cells:
        link = cell.find("a", href=re.compile(r"/en/box-pro/\d+"))
        if not link:
            continue
        name = link.get_text(strip=True)
        classes = " ".join(cell.get("class", []))
        if "winner" in classes or "win" in classes:
            result_code = "A" if name == fighter_a else "B"
            break
        if "loser" in classes or "loss" in classes:
            result_code = "B" if name == fighter_a else "A"
            break

    # Fall back to text parsing if CSS class approach failed
    if result_code is None:
        for text in texts:
            key = text.strip().lower()
            if key in _RESULT_MAP:
                result_code = _RESULT_MAP[key]
                break

    if result_code is None:
        return None

    # ── Method ────────────────────────────────────────────────────────────────
    method: Optional[str] = None
    for text in texts:
        m = _normalise_method(text)
        if m:
            method = m
            break

    # ── Round ended ───────────────────────────────────────────────────────────
    round_ended: Optional[int] = None
    for text in texts:
        if re.match(r"^\d{1,2}$", text.strip()):
            val = int(text.strip())
            if 1 <= val <= 15:
                round_ended = val
                break

    # ── Weight class ──────────────────────────────────────────────────────────
    weight_class: Optional[str] = None
    for text in texts:
        for div in DIVISIONS:
            if div.lower() in text.lower():
                weight_class = div
                break
        if weight_class:
            break

    ext_id = f"br_evt_{event_id}_{_slug(fighter_a)}_{_slug(fighter_b)}"

    return {
        "ext_id": ext_id,
        "fight_date": event_date,
        "fighter_a": fighter_a,
        "fighter_b": fighter_b,
        "result": result_code,
        "method": method,
        "round_ended": round_ended,
        "total_rounds": 12,
        "weight_class": weight_class,
        "venue": venue,
        "location": location,
        "event_name": event_name,
        "title_fight": False,
        "sanctioning_body": None,
        "is_upcoming": False,
    }


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())[:30]

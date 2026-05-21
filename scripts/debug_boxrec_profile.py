"""
Debug script: log into BoxRec, navigate to a boxer profile, and save the
raw page HTML + a structured table summary to data_files/.

Usage (from the project root):
    python scripts/debug_boxrec_profile.py [boxer_id]

Defaults to Naoya Inoue (628407).  Output files:
    data_files/debug_boxer_<id>.html   -- full page source
    data_files/debug_boxer_<id>_tables.txt  -- table summary
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path so `data.*` imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BOXREC_PASSWORD, BOXREC_USERNAME  # noqa: E402
from data.boxrec import BoxRecSession  # noqa: E402

BOXER_ID = sys.argv[1] if len(sys.argv) > 1 else "628407"
OUT_DIR = Path(__file__).parent.parent / "data_files"
OUT_DIR.mkdir(exist_ok=True)

HTML_FILE = OUT_DIR / f"debug_boxer_{BOXER_ID}.html"
TABLE_FILE = OUT_DIR / f"debug_boxer_{BOXER_ID}_tables.txt"


def main() -> None:
    if not BOXREC_USERNAME or not BOXREC_PASSWORD:
        print("ERROR: BOXREC_USERNAME / BOXREC_PASSWORD not set in .env")
        sys.exit(1)

    print(f"Starting BoxRec session (headless=False) …")
    br = BoxRecSession(headless=False)

    try:
        print("Logging in …")
        ok = br.login(BOXREC_USERNAME, BOXREC_PASSWORD)
        if not ok:
            print("ERROR: BoxRec login failed")
            sys.exit(1)
        print("Login OK")

        url = f"https://boxrec.com/en/box-pro/{BOXER_ID}"
        print(f"Navigating to {url} …")
        br.driver.get(url)

        # Wait for Cloudflare
        print("Waiting for Cloudflare check to clear …")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            src = br.driver.page_source
            if "just a moment" not in src.lower():
                break
            time.sleep(1)

        # Wait for listBouts table
        print("Waiting for #listBouts element …")
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(br.driver, 20).until(
                EC.presence_of_element_located((By.ID, "listBouts"))
            )
            print("#listBouts found via WebDriverWait")
        except Exception as e:
            print(f"WARNING: WebDriverWait timed out or failed: {e}")
            time.sleep(5)

        page_source = br.driver.page_source

        # Save raw HTML
        HTML_FILE.write_text(page_source, encoding="utf-8")
        print(f"Saved HTML ({len(page_source):,} bytes) -> {HTML_FILE}")

        # Parse and summarise tables
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_source, "lxml")

        lines = []
        all_tables = soup.find_all("table")
        lines.append(f"Total tables on page: {len(all_tables)}\n")

        for i, tbl in enumerate(all_tables):
            tid = tbl.get("id", "<no id>")
            tcls = " ".join(tbl.get("class", []))
            rows = tbl.find_all("tr")
            lines.append(f"Table {i}: id={tid!r}  class={tcls!r}  rows={len(rows)}")
            # Show first 3 rows of each table
            for j, row in enumerate(rows[:3]):
                cells = row.find_all(["td", "th"])
                cell_texts = [c.get_text(strip=True)[:40] for c in cells]
                lines.append(f"  Row {j}: {cell_texts}")
            if len(rows) > 3:
                lines.append(f"  ... ({len(rows) - 3} more rows)")
            lines.append("")

        # Also show full text of the listBouts table if present
        bout_table = soup.find("table", {"id": "listBouts"})
        if bout_table:
            bout_rows = bout_table.select("tbody tr")
            lines.append(f"\n#listBouts tbody rows: {len(bout_rows)}")
            for j, row in enumerate(bout_rows[:5]):
                cells = row.find_all("td")
                lines.append(f"  Bout row {j}:")
                for k, cell in enumerate(cells):
                    # Show text AND any hrefs inside
                    txt = cell.get_text(strip=True)
                    hrefs = [a["href"] for a in cell.find_all("a", href=True)]
                    spans = [(s.get("class"), s.get_text(strip=True))
                             for s in cell.find_all("span")]
                    lines.append(f"    td[{k}]: text={txt!r}  hrefs={hrefs}  spans={spans}")
        else:
            lines.append("\nWARNING: #listBouts table NOT FOUND in page source")
            # Show h1 / title for context
            h1 = soup.find("h1")
            lines.append(f"  Page h1: {h1.get_text(strip=True) if h1 else 'none'}")
            title = soup.find("title")
            lines.append(f"  Page title: {title.get_text(strip=True) if title else 'none'}")

        summary = "\n".join(lines)
        TABLE_FILE.write_text(summary, encoding="utf-8")
        print(f"Saved table summary -> {TABLE_FILE}")
        print("\n--- Table summary ---")
        print(summary[:4000])

    finally:
        br.close()
        print("Driver closed.")


if __name__ == "__main__":
    main()

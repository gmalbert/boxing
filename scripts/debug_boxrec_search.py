"""
Debug script: navigate to BoxRec search for a known fighter and dump the HTML.
Usage:
    .\venv\Scripts\python.exe scripts\debug_boxrec_search.py "Jared Anderson"
"""
import sys, pathlib, os, time
from urllib.parse import urlencode
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from data.boxrec import BoxRecSession

BOXREC_USERNAME = os.getenv("BOXREC_USERNAME", "")
BOXREC_PASSWORD = os.getenv("BOXREC_PASSWORD", "")
BOXREC_BASE = "https://boxrec.com"

name = sys.argv[1] if len(sys.argv) > 1 else "Jared Anderson"
parts = name.strip().split()
first = parts[0]
last = " ".join(parts[1:]) if len(parts) > 1 else ""

from urllib.parse import quote
# BoxRec form params use p[field] notation; role value is 'box-pro' for pro boxers
qs = f"p[first_name]={quote(first)}&p[last_name]={quote(last)}&p[role]=box-pro&p[status]="
url = f"{BOXREC_BASE}/en/search?{qs}"
print(f"Search URL: {url}")

br = BoxRecSession(headless=False)
try:
    if not br.login(BOXREC_USERNAME, BOXREC_PASSWORD):
        print("Login failed!")
        sys.exit(1)
    print("Logged in. Navigating to search…")
    time.sleep(2)
    soup = br._navigate(url)
    
    # Print current URL after navigation
    actual_url = br.driver.current_url
    print(f"Actual URL after navigation: {actual_url}")
    
    # Print page title
    title = soup.find("title")
    print(f"Page title: {title.get_text(strip=True) if title else 'n/a'}")
    
    # Find all links containing a number
    import re
    links = soup.find_all("a", href=re.compile(r"/\d+"))
    print(f"\nAll links containing a number ({len(links)} total):")
    for link in links[:30]:
        print(f"  href={link['href']!r:50s}  text={link.get_text(strip=True)!r}")

    # Dump table rows so we can see all columns
    print("\nAll table rows:")
    for row in soup.select("table tr"):
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if cells:
            print("  |", " | ".join(cells[:10]))
    
    # Save full HTML for manual inspection
    out = pathlib.Path("data_files") / "debug_search_result.html"
    out.write_text(br.driver.page_source, encoding="utf-8")
    print(f"\nFull HTML saved to: {out}")
finally:
    br.close()

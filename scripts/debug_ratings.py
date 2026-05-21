"""Debug: log in, accept GDPR, then inspect BoxRec Heavyweight ratings page."""
import os, time, re
from dotenv import load_dotenv
load_dotenv()

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

options = uc.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--window-size=1280,800")
driver = uc.Chrome(options=options, headless=False)

try:
    driver.get("https://boxrec.com/en/login")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if "just a moment" not in driver.page_source.lower():
            break
        time.sleep(1)

    wait = WebDriverWait(driver, 20)
    u = wait.until(EC.presence_of_element_located((By.NAME, "_username")))
    u.send_keys(os.getenv("BOXREC_USERNAME", ""))
    p = driver.find_element(By.NAME, "_password")
    p.send_keys(os.getenv("BOXREC_PASSWORD", ""))
    p.submit()
    time.sleep(4)

    if "gdpr_consent" in driver.current_url:
        print("Accepting GDPR...")
        driver.get("https://boxrec.com/en/gdpr_accept")
        time.sleep(3)

    print("Logged in:", "logout" in driver.page_source.lower())

    # Navigate to ratings page
    driver.get("https://boxrec.com/en/ratings?division=Heavyweight&status=a&sex=M&country=&stance=&page=1")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if "just a moment" not in driver.page_source.lower():
            break
        time.sleep(1)
    time.sleep(4)  # extra wait for JS render

    print("Ratings URL:", driver.current_url)
    print("Page title:", driver.title)
    src = driver.page_source
    soup = BeautifulSoup(src, "lxml")

    print(f"\nTotal tables: {len(soup.find_all('table'))}")
    table = soup.find("table", {"id": "ratingsResults"}) or soup.find("table", {"class": "dataTable"})
    if table:
        rows = table.find_all("tr")
        print(f"Table rows: {len(rows)}")
        # Print HTML of first few tbody rows
        tbody_rows = table.select("tbody tr")
        for i, row in enumerate(tbody_rows[:3]):
            print(f"\n--- Row {i} HTML ---")
            print(row.prettify()[:600])
        print("\nAll links in table:")
        for a in table.find_all("a")[:10]:
            print(f"  href={a.get('href')!r} text={a.get_text(strip=True)!r}")
    else:
        print("ratingsResults table NOT found")
finally:
    driver.quit()

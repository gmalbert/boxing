"""Debug: log in and inspect boxer profile page structure."""
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
    time.sleep(3)
    driver.get("https://boxrec.com/en/login")
    deadline = time.monotonic() + 45
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
        driver.get("https://boxrec.com/en/gdpr_accept")
        time.sleep(3)

    print("Logged in:", "logout" in driver.page_source.lower())

    # Navigate to Naoya Inoue's profile (boxer 628407)
    driver.get("https://boxrec.com/en/box-pro/628407")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if "just a moment" not in driver.page_source.lower():
            break
        time.sleep(1)
    time.sleep(3)

    src = driver.page_source
    soup = BeautifulSoup(src, "lxml")
    print("Page title:", driver.title)
    print(f"\nAll tables:")
    for i, t in enumerate(soup.find_all("table")):
        rows = t.find_all("tr")
        print(f"  Table {i}: id={t.get('id')!r} class={t.get('class')} rows={len(rows)}")
    
    # Check for boxer name
    h1 = soup.find("h1")
    print(f"\nh1 text: {h1.get_text(strip=True) if h1 else 'None'}")
    for sel in ["#listBouts", ".boutTable", "table.results"]:
        found = soup.select(sel)
        print(f"select({sel!r}): {len(found)} results")
finally:
    driver.quit()

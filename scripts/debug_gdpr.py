"""One-off script: log in to BoxRec and dump the GDPR consent page HTML."""
import os, time
from dotenv import load_dotenv
load_dotenv()

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

    print("URL after login:", driver.current_url)
    
    # If redirected to GDPR, check that page; otherwise navigate there directly
    if "gdpr" not in driver.current_url:
        driver.get("https://boxrec.com/en/gdpr_consent")
        deadline2 = time.monotonic() + 15
        while time.monotonic() < deadline2:
            if "just a moment" not in driver.page_source.lower():
                break
            time.sleep(1)
        time.sleep(2)

    print("URL (GDPR):", driver.current_url)
    src = driver.page_source

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(src, "lxml")
    for form in soup.find_all("form"):
        print("FORM action=%r method=%r" % (form.get("action"), form.get("method")))
        for inp in form.find_all(["input", "button", "select", "textarea"]):
            print("  FIELD tag=%s name=%r type=%r value=%r text=%r" % (
                inp.name, inp.get("name"), inp.get("type"),
                inp.get("value", "")[:60], inp.get_text(strip=True)[:60]))
    print("---ALL BUTTONS---")
    for b in soup.find_all("button"):
        print("  BUTTON:", b)
    print("---CONSENT/AGREE LINKS---")
    import re
    for m in re.finditer(r'.{0,80}(accept|agree|i understand|consent).{0,80}', src, re.IGNORECASE):
        print("  RAW:", m.group()[:200])
finally:
    driver.quit()

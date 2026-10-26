"""Capture the price-estimate view for the report (needs Playwright + Chrome and the app running).

    python scripts/screenshot_prices.py [base_url]     # default http://localhost:8000
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1.25)
    page.goto(BASE)
    page.wait_for_timeout(800)
    page.click('[data-example="storefront"]')
    page.click("#findBtn")
    t0 = time.time()
    page.wait_for_timeout(2000)
    while time.time() - t0 < 120 and not page.evaluate("typeof last !== 'undefined' && last && !last.running && last.items.length > 0"):
        page.wait_for_timeout(700)
    est = page.evaluate("last.estimate")
    print("estimate:", est)
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(SHOTS / "11_prices.jpg"), type="jpeg", quality=82)
    bar = page.locator("#exportBar")
    bar.scroll_into_view_if_needed()
    bar.screenshot(path=str(SHOTS / "11b_price_note.jpg"), type="jpeg", quality=82)
    print("saved 11_prices.jpg, 11b_price_note.jpg")
    browser.close()

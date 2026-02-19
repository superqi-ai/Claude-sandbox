"""
inspect_portal.py
-----------------
One-time diagnostic: logs into the portal, navigates to /calls,
saves a screenshot and the full page HTML so we can identify
the real CSS selectors needed by portal_scraper.py.

Usage:
    cd transcript_agent
    python3 -m src.inspect_portal
"""

import os
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from src.gmail_reader import GmailReader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

email    = os.environ["PORTAL_EMAIL"]
password = os.environ["PORTAL_PASSWORD"]
url      = config["portal"]["url"]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context()
    page    = context.new_page()

    # --- Login ---
    logger.info("Navigating to %s", url)
    page.goto(url, wait_until="networkidle")

    page.wait_for_selector('input[type="email"], input[name="email"]', timeout=15_000)
    page.fill('input[type="email"], input[name="email"]', email)

    if page.is_visible('input[type="password"]'):
        page.fill('input[type="password"]', password)
        page.click('button[type="submit"]')
    else:
        page.click('button[type="submit"]')
        page.wait_for_selector('input[type="password"]', timeout=10_000)
        page.fill('input[type="password"]', password)
        page.click('button[type="submit"]')

    # 2FA
    page.wait_for_selector(
        'input[placeholder*="code"], input[name*="code"], input[name*="otp"]',
        timeout=30_000,
    )
    gmail = GmailReader(config)
    code  = gmail.fetch_two_fa_code(timeout=60)
    logger.info("2FA code: %s", code)
    page.fill('input[placeholder*="code"], input[name*="code"], input[name*="otp"]', code)
    page.click('button[type="submit"]')

    page.wait_for_load_state("networkidle", timeout=20_000)
    if "/calls" not in page.url:
        page.goto(url, wait_until="networkidle")

    logger.info("Current URL: %s", page.url)

    # --- Dump ---
    out_dir = Path("downloads/inspect")
    out_dir.mkdir(parents=True, exist_ok=True)

    screenshot_path = out_dir / "calls_page.png"
    html_path       = out_dir / "calls_page.html"

    page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(page.content())

    logger.info("Screenshot saved → %s", screenshot_path)
    logger.info("HTML saved       → %s", html_path)

    context.close()
    browser.close()

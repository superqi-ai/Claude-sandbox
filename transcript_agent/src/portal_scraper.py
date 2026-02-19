"""
portal_scraper.py
-----------------
Uses Playwright to log into https://app.marblehealth.com/calls,
apply the configured filters, and bulk-download transcripts.

The download returns a ZIP or a set of files that land in the
`downloads/` directory.  The caller is responsible for unzipping
and parsing them.

Because Marble Health is a homegrown portal, the CSS selectors below
are best-guess placeholders that you will likely need to tweak after
inspecting the actual HTML with your browser's DevTools.
"""

import os
import time
import logging
import zipfile
import glob
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class PortalScraper:
    """Logs into Marble Health portal and downloads transcripts."""

    # ------------------------------------------------------------------ #
    # Selectors — update these by inspecting the live page in DevTools    #
    # ------------------------------------------------------------------ #
    SEL_EMAIL_INPUT       = 'input[type="email"], input[name="email"]'
    SEL_PASSWORD_INPUT    = 'input[type="password"], input[name="password"]'
    SEL_SUBMIT_BTN        = 'button[type="submit"]'
    SEL_2FA_INPUT         = 'input[placeholder*="code"], input[name*="code"], input[name*="otp"]'
    SEL_CALL_TYPE_FILTER  = '[data-testid="call-type-filter"], select[name="callType"]'
    SEL_INTAKE_FILTER     = '[data-testid="intake-status-filter"], select[name="intakeStatus"]'
    SEL_DATE_RANGE_START  = 'input[name="startDate"], [data-testid="date-start"]'
    SEL_DATE_RANGE_END    = 'input[name="endDate"], [data-testid="date-end"]'
    SEL_SELECT_ALL        = 'input[type="checkbox"][data-testid="select-all"], th input[type="checkbox"]'
    SEL_BULK_DOWNLOAD_BTN = 'button:has-text("Download"), button:has-text("Export"), [data-testid="bulk-download"]'

    def __init__(self, config: dict, gmail_reader, download_dir: Path):
        self.portal_url    = config["portal"]["url"]
        self.email         = os.environ["PORTAL_EMAIL"]
        self.password      = os.environ["PORTAL_PASSWORD"]
        self.filters       = config["portal"]["filters"]
        self.gmail_reader  = gmail_reader
        self.download_dir  = download_dir
        self.two_fa_timeout = config["gmail"]["two_fa_timeout_seconds"]

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def download_transcripts(self) -> list[Path]:
        """
        Full flow: login → apply filters → select all → bulk download.
        Returns a list of Path objects pointing at the downloaded
        transcript files (plain text, CSV, or extracted from a ZIP).
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            try:
                self._login(page)
                self._apply_filters(page)
                files = self._bulk_download(page)
            finally:
                context.close()
                browser.close()

        return files

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _login(self, page) -> None:
        """Navigate to portal and complete email + 2FA login."""
        logger.info("Navigating to portal: %s", self.portal_url)
        page.goto(self.portal_url, wait_until="networkidle")

        # --- Step 1: email / password ---
        logger.info("Filling in credentials…")
        page.wait_for_selector(self.SEL_EMAIL_INPUT, timeout=15_000)
        page.fill(self.SEL_EMAIL_INPUT, self.email)

        # Some portals show the password field only after you submit email
        if page.is_visible(self.SEL_PASSWORD_INPUT):
            page.fill(self.SEL_PASSWORD_INPUT, self.password)
            page.click(self.SEL_SUBMIT_BTN)
        else:
            # Click "Next" / "Continue" to reveal the password field
            page.click(self.SEL_SUBMIT_BTN)
            page.wait_for_selector(self.SEL_PASSWORD_INPUT, timeout=10_000)
            page.fill(self.SEL_PASSWORD_INPUT, self.password)
            page.click(self.SEL_SUBMIT_BTN)

        # --- Step 2: 2FA code sent to email ---
        logger.info("Waiting for 2FA email code…")
        page.wait_for_selector(self.SEL_2FA_INPUT, timeout=30_000)

        code = self.gmail_reader.fetch_two_fa_code(timeout=self.two_fa_timeout)
        logger.info("Got 2FA code, submitting…")
        page.fill(self.SEL_2FA_INPUT, code)
        page.click(self.SEL_SUBMIT_BTN)

        # Portal redirects to home after 2FA — wait for navigation then go to /calls
        page.wait_for_load_state("networkidle", timeout=20_000)
        if "/calls" not in page.url:
            page.goto(self.portal_url, wait_until="networkidle")
        logger.info("Login successful.")

    def _apply_filters(self, page) -> None:
        """Set call type, intake status, and date range filters."""
        end_date   = datetime.today()
        start_date = end_date - timedelta(days=self.filters["date_range_days"])

        logger.info(
            "Applying filters: call_type=%s, intake_status=%s, date_range=%s → %s",
            self.filters["call_type"],
            self.filters["intake_status"],
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )

        # --- Call type ---
        self._select_filter(page, self.SEL_CALL_TYPE_FILTER, self.filters["call_type"])

        # --- Intake status ---
        self._select_filter(page, self.SEL_INTAKE_FILTER, self.filters["intake_status"])

        # --- Date range ---
        self._set_date(page, self.SEL_DATE_RANGE_START, start_date)
        self._set_date(page, self.SEL_DATE_RANGE_END, end_date)

        # Wait for the table to refresh
        page.wait_for_load_state("networkidle")
        logger.info("Filters applied.")

    def _select_filter(self, page, selector: str, value: str) -> None:
        """
        Try to set a filter: works for <select> elements and for
        custom dropdown components that reveal options on click.
        """
        try:
            el = page.locator(selector).first
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                el.select_option(label=value)
            else:
                # Custom dropdown: click to open, then click the matching option
                el.click()
                page.locator(f'[role="option"]:has-text("{value}"), li:has-text("{value}")').first.click()
        except PlaywrightTimeoutError:
            logger.warning("Could not find filter selector '%s' — skipping.", selector)

    def _set_date(self, page, selector: str, date: datetime) -> None:
        """Fill a date input field."""
        try:
            page.fill(selector, date.strftime("%Y-%m-%d"))
        except PlaywrightTimeoutError:
            logger.warning("Could not find date selector '%s' — skipping.", selector)

    def _bulk_download(self, page) -> list[Path]:
        """Select all rows and trigger the bulk download."""
        logger.info("Selecting all transcripts…")
        try:
            page.click(self.SEL_SELECT_ALL)
        except PlaywrightTimeoutError:
            raise RuntimeError(
                "Could not find 'select all' checkbox. "
                "Check SEL_SELECT_ALL selector in portal_scraper.py."
            )

        logger.info("Triggering bulk download…")
        with page.expect_download(timeout=120_000) as download_info:
            page.click(self.SEL_BULK_DOWNLOAD_BTN)
        download = download_info.value

        # Save the file to our downloads directory
        dest = self.download_dir / download.suggested_filename
        download.save_as(dest)
        logger.info("Downloaded: %s", dest)

        # If it's a ZIP, extract it
        if dest.suffix.lower() == ".zip":
            return self._extract_zip(dest)

        return [dest]

    def _extract_zip(self, zip_path: Path) -> list[Path]:
        """Unzip a downloaded archive and return the extracted file paths."""
        extract_dir = zip_path.parent / zip_path.stem
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        files = list(extract_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        logger.info("Extracted %d file(s) from %s", len(files), zip_path.name)
        zip_path.unlink()  # clean up the zip
        return files

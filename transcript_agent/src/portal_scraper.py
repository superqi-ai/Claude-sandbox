"""
portal_scraper.py
-----------------
Uses Playwright to log into https://app.marblehealth.com/calls,
open the "Bulk Download Transcripts" modal, set filters, and
download a CSV of transcripts for the configured date range.
"""

import os
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class PortalScraper:
    """Logs into Marble Health portal and bulk-downloads transcripts as CSV."""

    SEL_EMAIL_INPUT = 'input[type="email"], input[name="email"]'
    SEL_PASSWORD_INPUT = 'input[type="password"], input[name="password"]'
    SEL_SUBMIT_BTN = 'button[type="submit"]'
    SEL_2FA_INPUT = 'input[data-input-otp="true"], input[name="code"], input[autocomplete="one-time-code"]'

    def __init__(self, config: dict, gmail_reader, download_dir: Path):
        self.portal_url     = config["portal"]["url"]
        self.email          = os.environ["PORTAL_EMAIL"]
        self.password       = os.environ["PORTAL_PASSWORD"]
        self.filters        = config["portal"]["filters"]
        self.gmail_reader   = gmail_reader
        self.download_dir   = download_dir
        self.two_fa_timeout = config["gmail"]["two_fa_timeout_seconds"]

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def download_transcripts(self) -> list[Path]:
        """
        Full flow: login → click Bulk Download → fill modal → Download CSV.
        Returns a list of Path objects pointing at the downloaded files.
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
                files = self._bulk_download_via_modal(page)
            finally:
                context.close()
                browser.close()

        return files

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _login(self, page) -> None:
        """Navigate to portal and complete email + password + 2FA login."""
        logger.info("Navigating to portal: %s", self.portal_url)
        page.goto(self.portal_url, wait_until="networkidle")

        logger.info("Filling in credentials…")
        page.wait_for_selector(self.SEL_EMAIL_INPUT, timeout=15_000)
        page.fill(self.SEL_EMAIL_INPUT, self.email)

        if page.is_visible(self.SEL_PASSWORD_INPUT):
            page.fill(self.SEL_PASSWORD_INPUT, self.password)
            page.click(self.SEL_SUBMIT_BTN)
        else:
            page.click(self.SEL_SUBMIT_BTN)
            page.wait_for_selector(self.SEL_PASSWORD_INPUT, timeout=10_000)
            page.fill(self.SEL_PASSWORD_INPUT, self.password)
            page.click(self.SEL_SUBMIT_BTN)

        logger.info("Waiting for 2FA email code…")
        page.wait_for_selector(self.SEL_2FA_INPUT, timeout=30_000)

        code = self.gmail_reader.fetch_two_fa_code(timeout=self.two_fa_timeout)
        logger.info("Got 2FA code, submitting…")
        page.fill(self.SEL_2FA_INPUT, code)
        page.click(self.SEL_SUBMIT_BTN)

        # Portal redirects to home after 2FA — navigate to /calls
        page.wait_for_load_state("networkidle", timeout=20_000)
        if "/calls" not in page.url:
            page.goto(self.portal_url, wait_until="networkidle")
        logger.info("Login successful.")

    def _bulk_download_via_modal(self, page) -> list[Path]:
        """
        Click the 'Bulk Download Transcripts' button, fill the modal,
        and trigger the CSV download.
        """
        end_date   = datetime.today()
        start_date = end_date - timedelta(days=self.filters["date_range_days"])

        logger.info(
            "Opening bulk-download modal (date_range=%s → %s, call_type=%s, intake_status=%s)",
            start_date.strftime("%m/%d/%Y"),
            end_date.strftime("%m/%d/%Y"),
            self.filters["call_type"],
            self.filters["intake_status"],
        )

        # --- Open the modal ---
        page.get_by_role("button", name="Bulk Download Transcripts").click()
        page.wait_for_selector('button:has-text("Download CSV")', timeout=15_000)
        logger.info("Modal open.")

        # --- Date range ---
        # The modal has two date inputs; find them by their label text
        self._fill_date_input(page, "Start Date", start_date)
        self._fill_date_input(page, "End Date", end_date)

        # --- Dropdowns ---
        call_type     = self.filters.get("call_type", "")
        intake_status = self.filters.get("intake_status", "")

        if call_type:
            self._select_dropdown(page, "Call Type", call_type)
        if intake_status:
            self._select_dropdown(page, "Intake Status", intake_status)

        # --- Trigger download ---
        logger.info("Clicking Download CSV…")
        with page.expect_download(timeout=120_000) as dl_info:
            page.get_by_role("button", name="Download CSV").click()
        download = dl_info.value

        dest = self.download_dir / download.suggested_filename
        download.save_as(dest)
        logger.info("Downloaded: %s", dest)

        if dest.suffix.lower() == ".zip":
            return self._extract_zip(dest)

        return [dest]

    def _fill_date_input(self, page, label: str, date: datetime) -> None:
        """Fill a date input identified by its nearby label text."""
        date_str = date.strftime("%m/%d/%Y")
        try:
            # Try Playwright label association first
            page.get_by_label(label, exact=False).first.fill(date_str)
        except Exception:
            # Fallback: find input next to a div/label containing the label text
            try:
                page.locator(
                    f'xpath=//label[contains(text(),"{label}")]/following::input[1]'
                ).first.fill(date_str)
            except Exception:
                logger.warning("Could not fill date input for '%s' — skipping.", label)

    def _select_dropdown(self, page, label: str, value: str) -> None:
        """
        Open a custom dropdown identified by its nearby label text and
        click the option matching `value` (case-insensitive substring).
        """
        try:
            # Click the dropdown trigger near the label
            trigger = page.locator(
                f'xpath=//label[contains(translate(text(),"abcdefghijklmnopqrstuvwxyz","ABCDEFGHIJKLMNOPQRSTUVWXYZ"),"{label.upper()}")]/following::button[1]'
            ).first
            trigger.click()

            # Click the matching option
            page.locator(
                f'[role="option"]:has-text("{value}"), li:has-text("{value}")'
            ).first.click(timeout=5_000)

            logger.info("Set '%s' → '%s'", label, value)
        except PlaywrightTimeoutError:
            logger.warning("Could not set dropdown '%s' to '%s' — skipping.", label, value)

    def _extract_zip(self, zip_path: Path) -> list[Path]:
        """Unzip a downloaded archive and return extracted file paths."""
        extract_dir = zip_path.parent / zip_path.stem
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        files = [f for f in extract_dir.rglob("*") if f.is_file()]
        logger.info("Extracted %d file(s) from %s", len(files), zip_path.name)
        zip_path.unlink()
        return files

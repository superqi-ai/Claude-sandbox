"""
main.py
-------
Orchestrates the weekly transcript-analysis pipeline:

  1. Log into Marble Health portal (with email 2FA via Gmail API)
  2. Apply filters and bulk-download transcripts for the past 7 days
  3. Parse files and group transcripts by associate name
  4. Analyse each associate's transcripts with Claude
  5. Write one row per associate to their Notion database

Run manually:
    cd transcript_agent
    python -m src.main

Or it is triggered automatically by the GitHub Actions workflow
every Monday at 8:00 AM ET.
"""

import logging
import os
import shutil
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.gmail_reader       import GmailReader
from src.portal_scraper     import PortalScraper
from src.transcript_parser  import TranscriptParser
from src.claude_analyzer    import ClaudeAnalyzer
from src.notion_writer      import NotionWriter

# ------------------------------------------------------------------ #
# Logging setup                                                        #
# ------------------------------------------------------------------ #

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

def run() -> None:
    """Execute the full weekly pipeline."""

    # --- Load environment variables from .env (local runs only) ---
    load_dotenv()
    _check_env_vars()

    # --- Load config ---
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(config_path) as fh:
        config = yaml.safe_load(fh)

    # --- Prepare downloads directory ---
    download_dir = Path(__file__).parent.parent / config["downloads"]["directory"]
    download_dir.mkdir(exist_ok=True)

    # ---- Step 1 & 2: Login + download ----
    logger.info("=" * 60)
    logger.info("STEP 1/4  Downloading transcripts from Marble Health…")
    logger.info("=" * 60)

    gmail_reader = GmailReader(config)
    scraper      = PortalScraper(config, gmail_reader, download_dir)

    try:
        downloaded_files = scraper.download_transcripts()
    except Exception as exc:
        logger.exception("Failed to download transcripts: %s", exc)
        sys.exit(1)

    if not downloaded_files:
        logger.warning("No transcript files were downloaded. Exiting.")
        sys.exit(0)

    logger.info("Downloaded %d file(s).", len(downloaded_files))

    # ---- Step 3: Parse and group by associate ----
    logger.info("=" * 60)
    logger.info("STEP 2/4  Parsing and grouping transcripts…")
    logger.info("=" * 60)

    parser = TranscriptParser(config["associates"])
    grouped = parser.parse_and_group(downloaded_files)

    total = sum(len(v) for k, v in grouped.items() if k != "unknown")
    logger.info("Grouped %d transcript(s) across %d associate(s).", total, len(config["associates"]))

    # ---- Step 4: Analyse with Claude ----
    logger.info("=" * 60)
    logger.info("STEP 3/4  Running Claude analysis…")
    logger.info("=" * 60)

    analyzer = ClaudeAnalyzer(config)
    try:
        analyses = analyzer.analyze_all(grouped)
    except Exception as exc:
        logger.exception("Claude analysis failed: %s", exc)
        sys.exit(1)

    logger.info("Analysis complete for %d associate(s).", len(analyses))

    # ---- Step 5: Write to Notion ----
    logger.info("=" * 60)
    logger.info("STEP 4/4  Writing results to Notion…")
    logger.info("=" * 60)

    writer = NotionWriter(config)
    try:
        writer.write_results(analyses)
    except Exception as exc:
        logger.exception("Notion write failed: %s", exc)
        sys.exit(1)

    # ---- Cleanup ----
    if not config["downloads"]["keep_after_processing"]:
        shutil.rmtree(download_dir, ignore_errors=True)
        download_dir.mkdir(exist_ok=True)
        logger.info("Downloads directory cleared.")

    logger.info("=" * 60)
    logger.info("Pipeline complete. All results written to Notion.")
    logger.info("=" * 60)


def _check_env_vars() -> None:
    """Fail fast if required secrets are missing."""
    required = ["PORTAL_EMAIL", "PORTAL_PASSWORD", "ANTHROPIC_API_KEY", "NOTION_API_KEY"]
    missing  = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        logger.error("Set them in your .env file or as GitHub Actions secrets.")
        sys.exit(1)


if __name__ == "__main__":
    run()

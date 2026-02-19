"""
notion_writer.py
----------------
Appends one row per associate to their respective Notion database
every time the weekly agent runs.

Setup:
1. Create a Notion Integration at https://www.notion.so/my-integrations
   - Give it "Insert content" and "Read content" capabilities
2. Share each associate's Notion page / database with the integration
3. Copy the integration's secret → NOTION_API_KEY in .env
4. Find each database's ID (the 32-char hex in the page URL)
   → add to config.yaml under associates[*].notion_database_id

Each row inserted has these properties (adjust in config.yaml):
  - Week         (date)       — Monday of the current run week
  - Associate    (title)      — associate's name
  - Calls Analyzed (number)   — how many transcripts were reviewed
  - Key Opportunities (text)  — first ~1500 chars of Claude's analysis
  - Raw Analysis  (text)      — full Claude response
  - Run Status    (select)    — "Success" | "Partial" | "Failed"
"""

import logging
import os
from datetime import datetime, date, timedelta

import httpx

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"


class NotionWriter:
    def __init__(self, config: dict):
        self.api_key        = os.environ["NOTION_API_KEY"]
        self.api_version    = config["notion"]["api_version"]
        self.global_db_id   = config["notion"].get("database_id", "")
        self.associates     = {a["name"]: a for a in config["associates"]}
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def write_results(self, analyses: list, week_date: "date | None" = None) -> None:
        """
        Insert one Notion database row for each AssociateAnalysis.

        Args:
            analyses:   list of AssociateAnalysis objects from ClaudeAnalyzer
            week_date:  the Monday of the reporting week (defaults to today's Monday)
        """
        if week_date is None:
            today     = date.today()
            week_date = today - timedelta(days=today.weekday())  # most recent Monday

        for analysis in analyses:
            db_id = self._get_database_id(analysis.associate_name)
            if not db_id:
                logger.error(
                    "No Notion database ID configured for '%s' — skipping.",
                    analysis.associate_name,
                )
                continue

            logger.info(
                "Writing Notion row for '%s' (week of %s)…",
                analysis.associate_name,
                week_date.isoformat(),
            )
            self._insert_row(db_id, analysis, week_date)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get_database_id(self, name: str) -> "str | None":
        associate = self.associates.get(name)
        # Per-associate ID takes priority; fall back to the global shared database
        db_id = (associate or {}).get("notion_database_id", "") or self.global_db_id
        # Strip hyphens in case the user copied the UUID-formatted ID
        return db_id.replace("-", "") or None

    def _insert_row(self, database_id: str, analysis, week_date: date) -> None:
        """POST a new page (row) to the Notion database."""
        payload = {
            "parent": {"database_id": database_id},
            "properties": self._build_properties(analysis, week_date),
        }

        with httpx.Client() as client:
            response = client.post(
                f"{NOTION_API_BASE}/pages",
                headers=self.headers,
                json=payload,
                timeout=30,
            )

        if response.status_code == 200:
            page_id = response.json().get("id", "?")
            logger.info(
                "  Created Notion page %s for '%s'.", page_id, analysis.associate_name
            )
        else:
            logger.error(
                "  Failed to create Notion page for '%s': %s — %s",
                analysis.associate_name,
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError(f"Notion API error: {response.status_code}")

    def _build_properties(self, analysis, week_date: date) -> dict:
        """
        Build the Notion page properties payload.

        Notion property types reference:
          title      → {"title": [{"text": {"content": "…"}}]}
          date       → {"date": {"start": "YYYY-MM-DD"}}
          number     → {"number": 42}
          rich_text  → {"rich_text": [{"text": {"content": "…"}}]}
          select     → {"select": {"name": "…"}}
        """
        # Truncate rich_text to Notion's 2000-char limit per block
        key_ops  = _truncate(analysis.key_opportunities, 2000)
        raw_text = _truncate(analysis.analysis, 2000)

        return {
            "Associate": {
                "title": [{"text": {"content": analysis.associate_name}}]
            },
            "Week": {
                "rich_text": [{"text": {"content": week_date.isoformat()}}]
            },
            "Calls Analyzed": {
                "rich_text": [{"text": {"content": str(analysis.call_count)}}]
            },
            "Key Opportunities": {
                "rich_text": [{"text": {"content": key_ops}}]
            },
            "Raw Analysis": {
                "rich_text": [{"text": {"content": raw_text}}]
            },
            "Run Status": {
                "status": {"name": "Success"}
            },
        }


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to fit within Notion's per-block character limit."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "…"

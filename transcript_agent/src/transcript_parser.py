"""
transcript_parser.py
--------------------
Reads the downloaded transcript files, detects which associate each
transcript belongs to, and groups them.

Marble Health can export transcripts in several formats.  We support:
  - Plain text / Markdown (.txt, .md)
  - CSV with a "transcript" column (.csv)
  - JSON with a "transcript" field (.json)

Associate attribution:
  The associate's full name is searched in each transcript text.
  If a transcript contains none of the configured names it is placed
  in an "unknown" bucket so nothing is silently dropped.
"""

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TranscriptParser:
    def __init__(self, associates: list[dict]):
        """
        Args:
            associates: list of dicts from config.yaml, each with a "name" key.
        """
        self.associate_names = [a["name"] for a in associates]

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def parse_and_group(self, files: list[Path]) -> dict[str, list[str]]:
        """
        Parse all downloaded files and group transcript texts by associate name.

        Returns:
            {
                "Associate Name 1": ["full transcript text …", …],
                "Associate Name 2": […],
                "unknown": […],   # transcripts with no matching name
            }
        """
        groups: dict[str, list[str]] = {name: [] for name in self.associate_names}
        groups["unknown"] = []

        for path in files:
            transcripts = self._extract_transcripts(path)
            for text in transcripts:
                owner = self._detect_associate(text)
                groups[owner].append(text)

        for name, texts in groups.items():
            logger.info("Associate '%s': %d transcript(s)", name, len(texts))

        return groups

    # ------------------------------------------------------------------ #
    # File parsers                                                         #
    # ------------------------------------------------------------------ #

    def _extract_transcripts(self, path: Path) -> list[str]:
        """Dispatch to the right parser based on file extension."""
        suffix = path.suffix.lower()
        try:
            if suffix in {".txt", ".md", ".text"}:
                return self._parse_text(path)
            elif suffix == ".csv":
                return self._parse_csv(path)
            elif suffix == ".json":
                return self._parse_json(path)
            else:
                logger.warning("Unsupported file type '%s' — trying plain text.", suffix)
                return self._parse_text(path)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", path, exc)
            return []

    def _parse_text(self, path: Path) -> list[str]:
        """
        Read the file as plain text.
        If multiple transcripts are concatenated in one file they are
        often separated by a line of dashes or '==='; we split on those.
        """
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Split on common separator lines
        import re
        chunks = re.split(r"\n[-=]{10,}\n", raw)
        return [c.strip() for c in chunks if c.strip()]

    def _parse_csv(self, path: Path) -> list[str]:
        """
        Expect a CSV where one column contains the transcript text.
        We look for columns named 'transcript', 'text', or 'body'.
        """
        transcripts = []
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            text_col = self._find_text_column(reader.fieldnames or [])
            for row in reader:
                text = row.get(text_col, "").strip()
                if text:
                    transcripts.append(text)
        return transcripts

    def _parse_json(self, path: Path) -> list[str]:
        """
        Handle either a single JSON object or a JSON array.
        Looks for a 'transcript', 'text', or 'body' key.
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [self._extract_text_field(item) for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            return [self._extract_text_field(data)]
        return []

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _find_text_column(self, fieldnames: list[str]) -> str:
        """Pick the most likely column name that contains transcript text."""
        priority = ["transcript", "text", "body", "content", "call_text"]
        lower_map = {f.lower(): f for f in fieldnames}
        for candidate in priority:
            if candidate in lower_map:
                return lower_map[candidate]
        # Fallback: return the last column (often the longest one)
        return fieldnames[-1] if fieldnames else "transcript"

    def _extract_text_field(self, obj: dict) -> str:
        """Extract the transcript text from a JSON object."""
        for key in ("transcript", "text", "body", "content", "call_text"):
            if key in obj:
                return str(obj[key])
        # Fallback: concatenate all string values
        return " ".join(str(v) for v in obj.values() if isinstance(v, str))

    def _detect_associate(self, text: str) -> str:
        """
        Return the name of the associate mentioned in the transcript text,
        or 'unknown' if none of the configured names is found.
        """
        text_lower = text.lower()
        for name in self.associate_names:
            if name.lower() in text_lower:
                return name
        return "unknown"

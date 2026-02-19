"""
claude_analyzer.py
------------------
Sends each associate's transcripts to the Claude API for analysis,
using the prompt defined in config.yaml.

For associates with many transcripts, all texts are concatenated into
a single API call (with a separator between them).  If the combined
text would exceed a safe limit, transcripts are batched and the
results are merged.
"""

import logging
import os
from dataclasses import dataclass

import anthropic

logger = logging.getLogger(__name__)

# Rough character limit per API call (well below the 200k-token context window,
# chosen conservatively to leave room for the prompt and response).
_MAX_CHARS_PER_CALL = 150_000


@dataclass
class AssociateAnalysis:
    associate_name:   str
    call_count:       int
    analysis:         str   # Full Claude response
    key_opportunities: str  # Extracted summary (first paragraph / bullet list)


class ClaudeAnalyzer:
    def __init__(self, config: dict):
        self.model      = config["claude"]["model"]
        self.max_tokens = config["claude"]["max_tokens"]
        self.prompt_tpl = config["claude"]["analysis_prompt"]
        self.client     = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def analyze_all(
        self, grouped_transcripts: dict[str, list[str]]
    ) -> list[AssociateAnalysis]:
        """
        Analyze transcripts for every associate (skips 'unknown').

        Args:
            grouped_transcripts: output of TranscriptParser.parse_and_group()

        Returns:
            One AssociateAnalysis per associate.
        """
        results = []
        for name, transcripts in grouped_transcripts.items():
            if name == "unknown":
                if transcripts:
                    logger.warning(
                        "%d transcript(s) could not be attributed to any associate.",
                        len(transcripts),
                    )
                continue

            if not transcripts:
                logger.info("No transcripts for associate '%s' — skipping.", name)
                continue

            logger.info(
                "Analyzing %d transcript(s) for '%s'…", len(transcripts), name
            )
            analysis = self._analyze_associate(name, transcripts)
            results.append(analysis)

        return results

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _analyze_associate(
        self, name: str, transcripts: list[str]
    ) -> AssociateAnalysis:
        """Run Claude analysis for a single associate."""
        # Batch transcripts if the combined text is very long
        batches   = self._make_batches(transcripts)
        all_parts = []

        for i, batch in enumerate(batches, start=1):
            logger.debug("  Sending batch %d/%d to Claude…", i, len(batches))
            combined = self._format_transcripts(batch)
            prompt   = self.prompt_tpl.format(transcript_text=combined)
            response = self._call_claude(prompt)
            all_parts.append(response)

        # If there were multiple batches, ask Claude to synthesise them
        if len(all_parts) > 1:
            synthesis_prompt = (
                "Below are analysis notes from multiple batches of calls for the "
                f"same care operations associate ({name}). Please synthesise them "
                "into a single, coherent analysis, removing any repetition.\n\n"
                + "\n\n---\n\n".join(all_parts)
            )
            final_analysis = self._call_claude(synthesis_prompt)
        else:
            final_analysis = all_parts[0]

        return AssociateAnalysis(
            associate_name    = name,
            call_count        = len(transcripts),
            analysis          = final_analysis,
            key_opportunities = self._extract_key_opportunities(final_analysis),
        )

    def _call_claude(self, prompt: str) -> str:
        """Make a single Claude API call and return the text response."""
        message = self.client.messages.create(
            model      = self.model,
            max_tokens = self.max_tokens,
            messages   = [{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _format_transcripts(self, transcripts: list[str]) -> str:
        """Combine multiple transcripts with clear separators."""
        parts = []
        for i, text in enumerate(transcripts, start=1):
            parts.append(f"=== CALL {i} ===\n{text}")
        return "\n\n".join(parts)

    def _make_batches(self, transcripts: list[str]) -> list[list[str]]:
        """
        Split transcripts into batches that each fit within _MAX_CHARS_PER_CALL.
        """
        batches: list[list[str]] = []
        current_batch: list[str] = []
        current_chars = 0

        for text in transcripts:
            if current_chars + len(text) > _MAX_CHARS_PER_CALL and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_chars = 0
            current_batch.append(text)
            current_chars += len(text)

        if current_batch:
            batches.append(current_batch)

        return batches

    def _extract_key_opportunities(self, full_analysis: str) -> str:
        """
        Pull out a concise summary from the full analysis.
        Grabs the first 1500 characters (roughly 3–5 bullet points).
        """
        return full_analysis[:1500].strip()

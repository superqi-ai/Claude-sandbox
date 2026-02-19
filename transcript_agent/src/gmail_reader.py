"""
gmail_reader.py
---------------
Uses the Gmail API to read the 2FA code that Marble Health emails
after the first login step.

Setup (one-time):
1. Go to https://console.cloud.google.com/
2. Create a project → enable the Gmail API
3. Create OAuth 2.0 credentials (Desktop app type)
4. Download the JSON file → save as config/gmail_credentials.json
5. Run this file directly once (`python -m src.gmail_reader`) to
   authorise the app; it will open a browser and save a token to
   config/gmail_token.json.  After that, the token auto-refreshes.
"""

import base64
import logging
import os
import re
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Read-only access to Gmail messages is all we need.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailReader:
    """Polls Gmail for a 2FA code from the Marble Health portal."""

    def __init__(self, config: dict):
        self.credentials_file = Path(config["gmail"]["credentials_file"])
        self.token_file       = Path(config["gmail"]["token_file"])
        self.sender           = config["gmail"]["two_fa_sender"]
        self._service         = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def fetch_two_fa_code(self, timeout: int = 60) -> str:
        """
        Poll Gmail until a 2FA email from Marble Health arrives, then
        extract and return the numeric code.

        Args:
            timeout: Maximum seconds to wait before raising TimeoutError.

        Returns:
            The 2FA code as a string (e.g. "483921").
        """
        service   = self._get_service()
        deadline  = time.time() + timeout
        poll_interval = 5  # seconds between Gmail API calls

        # Record the time *before* we initiated login so we only look at
        # emails that arrived after this point.
        after_epoch = int(time.time()) - 30  # 30-s buffer for clock skew

        logger.info("Polling Gmail for 2FA code from <%s> …", self.sender)
        while time.time() < deadline:
            messages = self._search_messages(service, after_epoch)
            if messages:
                code = self._extract_code_from_message(service, messages[0]["id"])
                if code:
                    logger.info("2FA code found.")
                    return code
            time.sleep(poll_interval)

        raise TimeoutError(
            f"2FA email from {self.sender!r} did not arrive within {timeout}s."
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get_service(self):
        """Return an authenticated Gmail API service, refreshing tokens as needed."""
        if self._service:
            return self._service

        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials file not found: {self.credentials_file}\n"
                        "Download it from Google Cloud Console and place it at that path."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), SCOPES
                )
                # In headless / CI environments use --noauth_local_webserver
                creds = flow.run_local_server(port=0)

            # Persist the token so we don't have to re-authorise each run
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w") as fh:
                fh.write(creds.to_json())

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def _search_messages(self, service, after_epoch: int) -> list:
        """Search the inbox for 2FA emails received after `after_epoch`."""
        query = f"from:{self.sender} after:{after_epoch}"
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=5)
            .execute()
        )
        return result.get("messages", [])

    def _extract_code_from_message(self, service, message_id: str) -> str | None:
        """
        Fetch the full message and extract the 2FA code.
        Looks for a 4–8 digit number in the email body.
        """
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        body_text = self._decode_body(msg)
        if not body_text:
            return None

        # Most 2FA codes are 4–8 consecutive digits, often on their own line
        match = re.search(r"\b(\d{4,8})\b", body_text)
        if match:
            return match.group(1)

        logger.debug("No numeric code found in message body:\n%s", body_text[:500])
        return None

    def _decode_body(self, message: dict) -> str:
        """Walk the MIME tree and return decoded plain-text body."""
        payload = message.get("payload", {})
        return self._walk_parts(payload)

    def _walk_parts(self, payload: dict) -> str:
        """Recursively extract text/plain content from a MIME payload."""
        mime_type = payload.get("mimeType", "")
        parts     = payload.get("parts", [])
        body_data = payload.get("body", {}).get("data", "")

        if mime_type == "text/plain" and body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

        for part in parts:
            result = self._walk_parts(part)
            if result:
                return result

        # Fallback: try decoding whatever body data exists
        if body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

        return ""


# ------------------------------------------------------------------ #
# One-time authorisation helper                                        #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    """
    Run once manually to authorise the Gmail app and save the token:
        cd transcript_agent
        python -m src.gmail_reader
    """
    import yaml

    logging.basicConfig(level=logging.INFO)
    with open("config/config.yaml") as f:
        cfg = yaml.safe_load(f)

    reader = GmailReader(cfg)
    reader._get_service()
    print("✓ Gmail authorisation complete.  Token saved to", cfg["gmail"]["token_file"])

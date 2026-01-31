"""Configuration management for the apartment listing agent."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration settings for the apartment agent."""

    # API Keys
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

    # Google Sheets
    GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1ARSI4ejhl_1pnjUdn9XpduaR9Zbxl3kR_0qJ_AjvDT0/edit"
    SPREADSHEET_ID = "1ARSI4ejhl_1pnjUdn9XpduaR9Zbxl3kR_0qJ_AjvDT0"

    # Target location for distance calculation
    TARGET_ADDRESS = os.getenv("TARGET_ADDRESS", "2303 14th St NW, DC 20009")

    @classmethod
    def validate(cls):
        """Validate that required configuration is present."""
        missing = []

        if not cls.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        if not cls.GOOGLE_MAPS_API_KEY:
            missing.append("GOOGLE_MAPS_API_KEY")
        if not os.path.exists(cls.GOOGLE_CREDENTIALS_PATH):
            missing.append(f"Google credentials file at {cls.GOOGLE_CREDENTIALS_PATH}")

        if missing:
            print("Missing configuration:")
            for item in missing:
                print(f"  - {item}")
            return False
        return True

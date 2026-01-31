"""Google Sheets integration for writing listing data."""

import gspread
from google.oauth2.service_account import Credentials
from typing import List, Optional
from config import Config


class SheetsWriter:
    """Write apartment listing data to Google Sheets."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self):
        """Initialize Google Sheets client."""
        self.credentials = Credentials.from_service_account_file(
            Config.GOOGLE_CREDENTIALS_PATH, scopes=self.SCOPES
        )
        self.client = gspread.authorize(self.credentials)
        self.spreadsheet = self.client.open_by_key(Config.SPREADSHEET_ID)
        self.worksheet = self.spreadsheet.sheet1

    def add_listing(
        self,
        url: str,
        address: str,
        walking_time: int,
        rent: Optional[int],
        sqft: Optional[int],
        availability: Optional[str],
        has_modern_appliances: bool,
        has_big_windows: bool,
    ) -> int:
        """
        Add a new listing row to the spreadsheet.

        Args:
            url: Zillow listing URL (Column A)
            address: Property address (Column B)
            walking_time: Walking time in minutes (Column C)
            rent: Monthly rent in dollars (Column D)
            sqft: Square footage (Column E)
            availability: Earliest availability date (Column F)
            has_modern_appliances: Whether listing has modern appliances (Column G)
            has_big_windows: Whether listing has big windows (Column H)

        Returns:
            Row number where data was inserted
        """
        # Prepare the row data
        row_data = [
            url,
            address,
            f"{walking_time} min" if walking_time > 0 else "N/A",
            f"${rent:,}" if rent else "N/A",
            f"{sqft:,} sqft" if sqft else "N/A",
            availability or "N/A",
            "Yes" if has_modern_appliances else "No",
            "Yes" if has_big_windows else "No",
        ]

        # Find the next empty row
        next_row = self._find_next_empty_row()

        # Insert the data
        self.worksheet.update(f"A{next_row}:H{next_row}", [row_data])

        print(f"Added listing to row {next_row}")
        return next_row

    def _find_next_empty_row(self) -> int:
        """Find the next empty row in the spreadsheet."""
        # Get all values in column A
        col_a = self.worksheet.col_values(1)

        # Return the next row after the last non-empty cell
        # Add 1 because row indices are 1-based, and 1 more for the next empty row
        return len(col_a) + 1

    def ensure_headers(self):
        """Ensure the spreadsheet has proper headers."""
        headers = [
            "Listing URL",
            "Address",
            "Walking Time",
            "Monthly Rent",
            "Square Footage",
            "Availability",
            "Modern Appliances?",
            "Big Windows?",
        ]

        # Check if row 1 has headers
        current_row_1 = self.worksheet.row_values(1)

        if not current_row_1 or current_row_1[0] != headers[0]:
            # Insert headers
            self.worksheet.update("A1:H1", [headers])
            print("Added headers to spreadsheet")

    def get_existing_urls(self) -> List[str]:
        """Get list of URLs already in the spreadsheet to avoid duplicates."""
        col_a = self.worksheet.col_values(1)
        # Skip header row if it exists
        if col_a and col_a[0] == "Listing URL":
            return col_a[1:]
        return col_a

    def is_duplicate(self, url: str) -> bool:
        """Check if a URL already exists in the spreadsheet."""
        existing = self.get_existing_urls()
        return url in existing


def test_sheets_writer():
    """Test the sheets writer."""
    writer = SheetsWriter()

    # Ensure headers exist
    writer.ensure_headers()

    # Test adding a sample row
    row = writer.add_listing(
        url="https://example.com/test",
        address="123 Test St, Washington, DC",
        walking_time=15,
        rent=2500,
        sqft=750,
        availability="Feb 1, 2025",
        has_modern_appliances=True,
        has_big_windows=False,
    )
    print(f"Test row added at row {row}")


if __name__ == "__main__":
    test_sheets_writer()

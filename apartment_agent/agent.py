#!/usr/bin/env python3
"""
Apartment Listing Agent

An AI agent that processes Zillow listings and adds them to a Google Sheets tracker.
"""

import sys
import argparse
from typing import Optional

from config import Config
from zillow_scraper import ZillowScraper, ListingDetails
from distance_calculator import DistanceCalculator
from image_analyzer import ImageAnalyzer, ImageAnalysisResult
from sheets_writer import SheetsWriter


class ApartmentListingAgent:
    """
    Main agent class that orchestrates the apartment listing process.

    Flow:
    1. Takes a Zillow URL as input
    2. Scrapes listing details (address, rent, sqft, availability, images)
    3. Calculates walking distance to target location
    4. Analyzes images for modern appliances and big windows
    5. Adds all data to Google Sheets tracker
    """

    def __init__(self):
        """Initialize all component modules."""
        print("Initializing Apartment Listing Agent...")

        # Validate configuration
        if not Config.validate():
            print("\nPlease set up your .env file with the required API keys.")
            print("See .env.example for the required variables.")
            sys.exit(1)

        self.scraper = ZillowScraper()
        self.distance_calc = DistanceCalculator()
        self.image_analyzer = ImageAnalyzer()
        self.sheets_writer = SheetsWriter()

        # Ensure spreadsheet has headers
        self.sheets_writer.ensure_headers()

        print("Agent initialized successfully!\n")

    def process_listing(self, url: str) -> bool:
        """
        Process a single Zillow listing URL.

        Args:
            url: The Zillow listing URL to process

        Returns:
            True if successful, False otherwise
        """
        print(f"{'='*60}")
        print(f"Processing: {url}")
        print(f"{'='*60}\n")

        # Check for duplicate
        if self.sheets_writer.is_duplicate(url):
            print("⚠️  This listing is already in your tracker. Skipping.")
            return False

        # Step 1: Scrape listing details
        print("Step 1/4: Fetching listing details...")
        try:
            listing = self.scraper.fetch_listing(url)
            print(f"  ✓ Address: {listing.address}")
            print(f"  ✓ Rent: ${listing.rent}" if listing.rent else "  ✓ Rent: N/A")
            print(f"  ✓ Sqft: {listing.sqft}" if listing.sqft else "  ✓ Sqft: N/A")
            print(
                f"  ✓ Availability: {listing.availability}"
                if listing.availability
                else "  ✓ Availability: N/A"
            )
            print(f"  ✓ Found {len(listing.image_urls)} images\n")
        except Exception as e:
            print(f"  ✗ Failed to fetch listing: {e}")
            return False

        # Step 2: Calculate walking distance
        print("Step 2/4: Calculating walking distance...")
        try:
            walking_time = self.distance_calc.get_walking_time(listing.address)
            if walking_time > 0:
                print(f"  ✓ Walking time to {Config.TARGET_ADDRESS}: {walking_time} minutes\n")
            else:
                print(f"  ✓ Could not calculate walking time\n")
                walking_time = -1
        except Exception as e:
            print(f"  ✗ Distance calculation error: {e}")
            walking_time = -1

        # Step 3: Analyze images
        print("Step 3/4: Analyzing listing images...")
        try:
            analysis = self.image_analyzer.analyze_listing_images(listing.image_urls)
            print(f"  ✓ Modern Appliances: {'Yes' if analysis.has_modern_appliances else 'No'}")
            print(f"    Details: {analysis.appliances_details}")
            print(f"  ✓ Big Windows: {'Yes' if analysis.has_big_windows else 'No'}")
            print(f"    Details: {analysis.windows_details}\n")
        except Exception as e:
            print(f"  ✗ Image analysis error: {e}")
            analysis = ImageAnalysisResult(
                has_modern_appliances=False,
                has_big_windows=False,
                appliances_details="Analysis failed",
                windows_details="Analysis failed",
            )

        # Step 4: Add to Google Sheets
        print("Step 4/4: Adding to Google Sheets tracker...")
        try:
            row_num = self.sheets_writer.add_listing(
                url=url,
                address=listing.address,
                walking_time=walking_time,
                rent=listing.rent,
                sqft=listing.sqft,
                availability=listing.availability,
                has_modern_appliances=analysis.has_modern_appliances,
                has_big_windows=analysis.has_big_windows,
            )
            print(f"  ✓ Added to row {row_num}\n")
        except Exception as e:
            print(f"  ✗ Failed to add to spreadsheet: {e}")
            return False

        print(f"{'='*60}")
        print("✓ Listing processed successfully!")
        print(f"{'='*60}\n")

        return True

    def run_interactive(self):
        """Run the agent in interactive mode."""
        print("\n" + "="*60)
        print("  APARTMENT LISTING AGENT - Interactive Mode")
        print("="*60)
        print(f"\nTarget location: {Config.TARGET_ADDRESS}")
        print(f"Spreadsheet: {Config.SPREADSHEET_URL}")
        print("\nPaste Zillow URLs to add them to your tracker.")
        print("Type 'quit' or 'exit' to stop.\n")

        while True:
            try:
                url = input("Enter Zillow URL: ").strip()

                if url.lower() in ["quit", "exit", "q"]:
                    print("\nGoodbye! Happy apartment hunting!")
                    break

                if not url:
                    continue

                if "zillow.com" not in url.lower():
                    print("Please enter a valid Zillow URL.\n")
                    continue

                self.process_listing(url)

            except KeyboardInterrupt:
                print("\n\nGoodbye! Happy apartment hunting!")
                break
            except Exception as e:
                print(f"Error: {e}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apartment Listing Agent - Process Zillow listings into a tracker"
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Zillow listing URL to process (optional, runs interactive mode if not provided)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive mode",
    )

    args = parser.parse_args()

    agent = ApartmentListingAgent()

    if args.url:
        # Process single URL
        success = agent.process_listing(args.url)
        sys.exit(0 if success else 1)
    else:
        # Interactive mode
        agent.run_interactive()


if __name__ == "__main__":
    main()

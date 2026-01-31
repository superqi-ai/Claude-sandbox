"""Zillow listing scraper module."""

import re
import json
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional, List
from playwright.sync_api import sync_playwright


@dataclass
class ListingDetails:
    """Data class for apartment listing details."""

    url: str
    address: str
    rent: Optional[int] = None
    sqft: Optional[int] = None
    availability: Optional[str] = None
    image_urls: List[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None

    def __post_init__(self):
        if self.image_urls is None:
            self.image_urls = []


class ZillowScraper:
    """Scraper for Zillow rental listings."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def fetch_listing(self, url: str) -> ListingDetails:
        """
        Fetch listing details from a Zillow URL.

        Args:
            url: The Zillow listing URL

        Returns:
            ListingDetails object with scraped information
        """
        print(f"Fetching listing from: {url}")

        # Try with playwright for better JavaScript rendering
        return self._fetch_with_playwright(url)

    def _fetch_with_playwright(self, url: str) -> ListingDetails:
        """Fetch listing using Playwright for JavaScript-rendered content."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=self.HEADERS["User-Agent"],
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)  # Wait for dynamic content

                # Get the page content
                content = page.content()

                # Parse with BeautifulSoup
                soup = BeautifulSoup(content, "html.parser")

                # Extract listing details
                details = self._parse_listing_page(soup, url)

                # Try to get additional data from embedded JSON
                json_details = self._extract_json_data(content)
                if json_details:
                    details = self._merge_details(details, json_details)

                # Extract image URLs
                details.image_urls = self._extract_image_urls(page, soup)

                return details

            finally:
                browser.close()

    def _parse_listing_page(self, soup: BeautifulSoup, url: str) -> ListingDetails:
        """Parse the listing page HTML."""
        details = ListingDetails(url=url, address="")

        # Extract address - try multiple selectors
        address_selectors = [
            "h1[class*='Text-c11n']",
            "[data-testid='bdp-building-address']",
            ".summary-container h1",
            "h1",
        ]

        for selector in address_selectors:
            addr_elem = soup.select_one(selector)
            if addr_elem:
                details.address = addr_elem.get_text(strip=True)
                break

        # Extract rent
        rent_selectors = [
            "[data-testid='price']",
            "span[class*='Price']",
            ".list-card-price",
            "[class*='price']",
        ]

        for selector in rent_selectors:
            rent_elem = soup.select_one(selector)
            if rent_elem:
                rent_text = rent_elem.get_text(strip=True)
                rent_match = re.search(r"\$?([\d,]+)", rent_text)
                if rent_match:
                    details.rent = int(rent_match.group(1).replace(",", ""))
                    break

        # Extract square footage
        sqft_patterns = [
            r"([\d,]+)\s*(?:sq\.?\s*ft|sqft|square feet)",
            r"([\d,]+)\s*SF",
        ]

        page_text = soup.get_text()
        for pattern in sqft_patterns:
            sqft_match = re.search(pattern, page_text, re.IGNORECASE)
            if sqft_match:
                details.sqft = int(sqft_match.group(1).replace(",", ""))
                break

        # Extract availability
        avail_selectors = [
            "[class*='available']",
            "[class*='Avail']",
            "[data-testid*='available']",
        ]

        for selector in avail_selectors:
            avail_elem = soup.select_one(selector)
            if avail_elem:
                details.availability = avail_elem.get_text(strip=True)
                break

        # Try to find availability in text
        if not details.availability:
            avail_patterns = [
                r"Available\s+(?:from\s+)?(\w+\s+\d+(?:,?\s*\d+)?)",
                r"Move.in\s+(?:date|ready)[:\s]+(\w+\s+\d+(?:,?\s*\d+)?)",
                r"Available\s+(now|immediately)",
            ]
            for pattern in avail_patterns:
                avail_match = re.search(pattern, page_text, re.IGNORECASE)
                if avail_match:
                    details.availability = avail_match.group(1)
                    break

        return details

    def _extract_json_data(self, content: str) -> Optional[dict]:
        """Extract listing data from embedded JSON-LD or Next.js data."""
        try:
            # Try to find JSON-LD data
            json_ld_match = re.search(
                r'<script type="application/ld\+json">(.*?)</script>',
                content,
                re.DOTALL,
            )
            if json_ld_match:
                data = json.loads(json_ld_match.group(1))
                return data
        except (json.JSONDecodeError, AttributeError):
            pass

        try:
            # Try to find Next.js or React hydration data
            next_data_match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                content,
                re.DOTALL,
            )
            if next_data_match:
                data = json.loads(next_data_match.group(1))
                return data
        except (json.JSONDecodeError, AttributeError):
            pass

        return None

    def _merge_details(
        self, details: ListingDetails, json_data: dict
    ) -> ListingDetails:
        """Merge JSON data into listing details."""
        # This is a simplified merge - actual implementation would depend on Zillow's JSON structure
        if isinstance(json_data, dict):
            if not details.address and "address" in json_data:
                addr = json_data["address"]
                if isinstance(addr, dict):
                    details.address = f"{addr.get('streetAddress', '')}, {addr.get('addressLocality', '')}, {addr.get('addressRegion', '')} {addr.get('postalCode', '')}"
                else:
                    details.address = str(addr)

        return details

    def _extract_image_urls(self, page, soup: BeautifulSoup) -> List[str]:
        """Extract image URLs from the listing."""
        image_urls = []

        # Try to find carousel/gallery images
        img_selectors = [
            "img[src*='photos']",
            "img[src*='zillowstatic']",
            "[class*='carousel'] img",
            "[class*='gallery'] img",
            "picture img",
        ]

        for selector in img_selectors:
            images = soup.select(selector)
            for img in images:
                src = img.get("src") or img.get("data-src")
                if src and "http" in src:
                    # Get higher resolution version if possible
                    src = re.sub(r"_\d+x\d+", "_1200x800", src)
                    if src not in image_urls:
                        image_urls.append(src)

        # Limit to first 10 images for analysis
        return image_urls[:10]


def test_scraper():
    """Test the scraper with a sample URL."""
    scraper = ZillowScraper()
    # This is a test - replace with an actual Zillow URL
    test_url = "https://www.zillow.com/homedetails/123-Main-St/12345_zpid/"
    try:
        details = scraper.fetch_listing(test_url)
        print(f"Address: {details.address}")
        print(f"Rent: ${details.rent}")
        print(f"Sqft: {details.sqft}")
        print(f"Available: {details.availability}")
        print(f"Images found: {len(details.image_urls)}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_scraper()

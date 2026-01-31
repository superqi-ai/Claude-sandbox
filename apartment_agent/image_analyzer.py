"""Image analysis module using Claude Vision API."""

import base64
import requests
import anthropic
from typing import List, Tuple
from dataclasses import dataclass
from config import Config


@dataclass
class ImageAnalysisResult:
    """Results from analyzing listing images."""

    has_modern_appliances: bool
    has_big_windows: bool
    appliances_details: str
    windows_details: str


class ImageAnalyzer:
    """Analyze apartment listing images using Claude Vision."""

    def __init__(self):
        """Initialize the Anthropic client."""
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def analyze_listing_images(self, image_urls: List[str]) -> ImageAnalysisResult:
        """
        Analyze apartment images for modern appliances and big windows.

        Args:
            image_urls: List of image URLs from the listing

        Returns:
            ImageAnalysisResult with analysis findings
        """
        if not image_urls:
            return ImageAnalysisResult(
                has_modern_appliances=False,
                has_big_windows=False,
                appliances_details="No images available to analyze",
                windows_details="No images available to analyze",
            )

        # Prepare images for Claude
        image_content = []
        for url in image_urls[:8]:  # Limit to 8 images to stay within limits
            try:
                image_data = self._fetch_image_as_base64(url)
                if image_data:
                    media_type = self._get_media_type(url)
                    image_content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        }
                    )
            except Exception as e:
                print(f"Failed to fetch image {url}: {e}")
                continue

        if not image_content:
            return ImageAnalysisResult(
                has_modern_appliances=False,
                has_big_windows=False,
                appliances_details="Could not load any images",
                windows_details="Could not load any images",
            )

        # Add the analysis prompt
        image_content.append(
            {
                "type": "text",
                "text": """Analyze these apartment listing images and answer the following questions:

1. MODERN APPLIANCES: Look for the kitchen and any visible appliances. Does this apartment appear to have modern appliances? Consider:
   - Stainless steel or modern finishes
   - Recent/contemporary style refrigerator, stove, dishwasher
   - Modern washer/dryer if visible
   - Updated fixtures
   Answer YES or NO, then briefly explain what you observed.

2. BIG WINDOWS: Does this apartment appear to have big windows that let in significant natural light? Consider:
   - Window size relative to the rooms
   - Number of windows visible
   - Natural light in the photos
   Answer YES or NO, then briefly explain what you observed.

Please respond in this exact format:
MODERN_APPLIANCES: [YES/NO]
APPLIANCES_DETAILS: [Your brief explanation]
BIG_WINDOWS: [YES/NO]
WINDOWS_DETAILS: [Your brief explanation]""",
            }
        )

        try:
            # Call Claude Vision API
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": image_content}],
            )

            # Parse the response
            return self._parse_analysis_response(response.content[0].text)

        except Exception as e:
            print(f"Error analyzing images: {e}")
            return ImageAnalysisResult(
                has_modern_appliances=False,
                has_big_windows=False,
                appliances_details=f"Analysis error: {str(e)}",
                windows_details=f"Analysis error: {str(e)}",
            )

    def _fetch_image_as_base64(self, url: str) -> str:
        """Fetch an image and convert to base64."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return base64.standard_b64encode(response.content).decode("utf-8")

    def _get_media_type(self, url: str) -> str:
        """Determine media type from URL."""
        url_lower = url.lower()
        if ".png" in url_lower:
            return "image/png"
        elif ".gif" in url_lower:
            return "image/gif"
        elif ".webp" in url_lower:
            return "image/webp"
        else:
            return "image/jpeg"

    def _parse_analysis_response(self, response_text: str) -> ImageAnalysisResult:
        """Parse Claude's response into structured result."""
        lines = response_text.strip().split("\n")

        has_modern_appliances = False
        has_big_windows = False
        appliances_details = ""
        windows_details = ""

        for line in lines:
            line = line.strip()
            if line.startswith("MODERN_APPLIANCES:"):
                has_modern_appliances = "YES" in line.upper()
            elif line.startswith("APPLIANCES_DETAILS:"):
                appliances_details = line.replace("APPLIANCES_DETAILS:", "").strip()
            elif line.startswith("BIG_WINDOWS:"):
                has_big_windows = "YES" in line.upper()
            elif line.startswith("WINDOWS_DETAILS:"):
                windows_details = line.replace("WINDOWS_DETAILS:", "").strip()

        return ImageAnalysisResult(
            has_modern_appliances=has_modern_appliances,
            has_big_windows=has_big_windows,
            appliances_details=appliances_details or "No details provided",
            windows_details=windows_details or "No details provided",
        )


def test_image_analyzer():
    """Test the image analyzer."""
    analyzer = ImageAnalyzer()

    # Test with sample images (these would be real listing images)
    test_urls = [
        "https://example.com/kitchen.jpg",
        "https://example.com/living-room.jpg",
    ]

    result = analyzer.analyze_listing_images(test_urls)
    print(f"Modern Appliances: {result.has_modern_appliances}")
    print(f"  Details: {result.appliances_details}")
    print(f"Big Windows: {result.has_big_windows}")
    print(f"  Details: {result.windows_details}")


if __name__ == "__main__":
    test_image_analyzer()

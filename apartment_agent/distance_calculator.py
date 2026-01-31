"""Walking distance calculator using Google Maps API."""

import googlemaps
from config import Config


class DistanceCalculator:
    """Calculate walking distance between two addresses."""

    def __init__(self):
        """Initialize the Google Maps client."""
        self.client = googlemaps.Client(key=Config.GOOGLE_MAPS_API_KEY)
        self.target_address = Config.TARGET_ADDRESS

    def get_walking_time(self, origin_address: str) -> int:
        """
        Calculate walking time from origin to target address.

        Args:
            origin_address: The starting address (listing address)

        Returns:
            Walking time in minutes, or -1 if calculation fails
        """
        try:
            # Get distance matrix for walking
            result = self.client.distance_matrix(
                origins=[origin_address],
                destinations=[self.target_address],
                mode="walking",
                units="imperial",
            )

            # Parse the result
            if result["status"] == "OK":
                element = result["rows"][0]["elements"][0]
                if element["status"] == "OK":
                    # Duration is in seconds, convert to minutes
                    duration_seconds = element["duration"]["value"]
                    duration_minutes = round(duration_seconds / 60)
                    return duration_minutes
                else:
                    print(f"Route calculation failed: {element['status']}")
                    return -1
            else:
                print(f"Distance Matrix API error: {result['status']}")
                return -1

        except Exception as e:
            print(f"Error calculating walking time: {e}")
            return -1

    def get_walking_details(self, origin_address: str) -> dict:
        """
        Get detailed walking information.

        Args:
            origin_address: The starting address

        Returns:
            Dictionary with distance and duration information
        """
        try:
            result = self.client.distance_matrix(
                origins=[origin_address],
                destinations=[self.target_address],
                mode="walking",
                units="imperial",
            )

            if result["status"] == "OK":
                element = result["rows"][0]["elements"][0]
                if element["status"] == "OK":
                    return {
                        "duration_minutes": round(element["duration"]["value"] / 60),
                        "duration_text": element["duration"]["text"],
                        "distance_text": element["distance"]["text"],
                        "origin": origin_address,
                        "destination": self.target_address,
                    }

            return {"error": "Could not calculate route"}

        except Exception as e:
            return {"error": str(e)}


def test_distance_calculator():
    """Test the distance calculator."""
    calc = DistanceCalculator()

    # Test with a sample DC address
    test_address = "1600 Pennsylvania Ave NW, Washington, DC 20500"
    minutes = calc.get_walking_time(test_address)
    print(f"Walking time from {test_address}: {minutes} minutes")

    details = calc.get_walking_details(test_address)
    print(f"Details: {details}")


if __name__ == "__main__":
    test_distance_calculator()

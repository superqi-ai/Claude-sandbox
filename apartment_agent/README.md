# Apartment Listing Agent

An AI-powered agent that processes Zillow rental listings and automatically tracks them in a Google Sheets spreadsheet.

## Features

- **Zillow Scraping**: Extracts listing details (address, rent, square footage, availability) from Zillow URLs
- **Walking Distance**: Calculates walking time from each listing to your target location (default: 2303 14th St NW, DC 20009)
- **Image Analysis**: Uses Claude Vision to analyze listing photos for modern appliances and big windows
- **Google Sheets Integration**: Automatically adds listings to your tracking spreadsheet

## Spreadsheet Columns

| Column | Content |
|--------|---------|
| A | Listing URL |
| B | Address |
| C | Walking time (minutes) |
| D | Monthly rent |
| E | Square footage |
| F | Earliest availability |
| G | Modern appliances? (Yes/No) |
| H | Big windows? (Yes/No) |

## Setup

### 1. Install Dependencies

```bash
cd apartment_agent
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure API Keys

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required keys:
- **ANTHROPIC_API_KEY**: Get from [Anthropic Console](https://console.anthropic.com/)
- **GOOGLE_MAPS_API_KEY**: Get from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
  - Enable "Distance Matrix API" in your project

### 3. Set Up Google Sheets Access

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the Google Sheets API and Google Drive API
4. Create a Service Account:
   - Go to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Download the JSON key file
5. Save the JSON file as `credentials.json` in the `apartment_agent` directory
6. Share your Google Spreadsheet with the service account email (found in the JSON file)

### 4. Share Your Spreadsheet

Share your tracking spreadsheet with the service account email address (it looks like `name@project.iam.gserviceaccount.com`). Give it "Editor" access.

## Usage

### Interactive Mode

Run without arguments to enter interactive mode:

```bash
python agent.py
```

Then paste Zillow URLs when prompted.

### Single URL Mode

Process a single listing directly:

```bash
python agent.py "https://www.zillow.com/homedetails/..."
```

## Example Output

```
============================================================
Processing: https://www.zillow.com/homedetails/...
============================================================

Step 1/4: Fetching listing details...
  ✓ Address: 1234 Example St NW, Washington, DC 20001
  ✓ Rent: $2,500
  ✓ Sqft: 750
  ✓ Availability: Feb 1, 2025
  ✓ Found 8 images

Step 2/4: Calculating walking distance...
  ✓ Walking time to 2303 14th St NW, DC 20009: 12 minutes

Step 3/4: Analyzing listing images...
  ✓ Modern Appliances: Yes
    Details: Stainless steel refrigerator and modern gas range visible
  ✓ Big Windows: Yes
    Details: Large floor-to-ceiling windows in living room

Step 4/4: Adding to Google Sheets tracker...
  ✓ Added to row 5

============================================================
✓ Listing processed successfully!
============================================================
```

## Configuration

You can customize the target location by setting `TARGET_ADDRESS` in your `.env` file:

```
TARGET_ADDRESS=1600 Pennsylvania Ave NW, Washington, DC 20500
```

## Troubleshooting

### Zillow Blocking Requests
Zillow may block automated requests. The agent uses Playwright with a headless browser to mimic real browser behavior. If you still encounter issues, try adding delays between requests.

### Google Sheets Permission Errors
Ensure you've shared the spreadsheet with your service account email and that the service account has "Editor" access.

### Missing Dependencies
If you get import errors, make sure you've installed all dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

## Project Structure

```
apartment_agent/
├── agent.py              # Main orchestrator
├── zillow_scraper.py     # Zillow listing scraper
├── distance_calculator.py # Google Maps walking distance
├── image_analyzer.py     # Claude Vision image analysis
├── sheets_writer.py      # Google Sheets integration
├── config.py             # Configuration management
├── requirements.txt      # Python dependencies
├── .env.example          # Example environment variables
└── README.md             # This file
```

## License

MIT License

# Transcript Analysis Agent

Automated weekly agent that:
1. Logs into the Marble Health portal every Monday
2. Bulk-downloads outbound / pre-intake call transcripts for the past 7 days
3. Groups transcripts by care operations associate
4. Analyses each associate's calls with Claude (Anthropic API)
5. Writes one row per associate to their Notion database

---

## Quickstart

### 1. Clone & install

```bash
cd transcript_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Fill in config

**`config/config.yaml`** — open this file and update:
- `associates[*].name` — exact names as they appear in transcripts
- `associates[*].notion_database_id` — 32-char ID from each Notion database URL
- `gmail.two_fa_sender` — the "From" address Marble Health uses for 2FA emails
- `claude.analysis_prompt` — customise the analysis instructions for Claude

**`.env`** — copy `.env.example` → `.env` and fill in secrets:
```
PORTAL_EMAIL=you@yourcompany.com
PORTAL_PASSWORD=...
ANTHROPIC_API_KEY=sk-ant-...
NOTION_API_KEY=secret_...
```

### 3. Authorise Gmail (one-time)

```bash
# Downloads gmail_credentials.json from Google Cloud Console first, then:
python -m src.gmail_reader
# Opens a browser → log in with the Gmail account that receives 2FA codes
# Saves a refresh token to config/gmail_token.json
```

See **Gmail Setup** below for step-by-step instructions.

### 4. Run manually

```bash
python -m src.main
```

---

## Automated scheduling (GitHub Actions)

The workflow in `.github/workflows/weekly-analysis.yml` runs every
**Monday at 8:00 AM ET** automatically once you push this repo to GitHub
and add the required secrets.

### GitHub Secrets to add

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name            | Value                                              |
|------------------------|----------------------------------------------------|
| `PORTAL_EMAIL`         | Your Marble Health login email                     |
| `PORTAL_PASSWORD`      | Your Marble Health password                        |
| `ANTHROPIC_API_KEY`    | From https://console.anthropic.com/                |
| `NOTION_API_KEY`       | From https://www.notion.so/my-integrations         |
| `GMAIL_CREDENTIALS_JSON` | Full contents of `config/gmail_credentials.json` |
| `GMAIL_TOKEN_JSON`     | Full contents of `config/gmail_token.json`         |

---

## Gmail Setup (step-by-step)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g. "Transcript Agent")
3. Enable **Gmail API**: APIs & Services → Enable APIs → search "Gmail API"
4. Create credentials: APIs & Services → Credentials → **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON → save as `config/gmail_credentials.json`
5. On the OAuth consent screen, add your Gmail address as a **test user**
6. Run `python -m src.gmail_reader` — it opens a browser for you to authorise
7. After authorising, `config/gmail_token.json` is created automatically
8. Copy the *contents* of both files into the corresponding GitHub secrets

---

## Notion Setup (step-by-step)

1. Go to [Notion Integrations](https://www.notion.so/my-integrations) → **New integration**
2. Give it a name (e.g. "Transcript Agent"), workspace: your workspace
3. Capabilities: check **Insert content** and **Read content**
4. Copy the **Internal Integration Secret** → `NOTION_API_KEY`
5. For each associate:
   a. Open their Notion page in the browser
   b. Create a database (or use an existing one) with these columns:

      | Column name        | Type       |
      |--------------------|------------|
      | Associate          | Title      |
      | Week               | Date       |
      | Calls Analyzed     | Number     |
      | Key Opportunities  | Text       |
      | Raw Analysis       | Text       |
      | Run Status         | Select     |

   c. Click **Share** (top right) → **Invite** → search for your integration name → **Invite**
   d. Copy the database ID from the URL:
      `https://www.notion.so/yourworkspace/**<DATABASE_ID>**?v=...`
      (the 32-char hex string before `?v=`)
   e. Paste into `config/config.yaml` under `associates[*].notion_database_id`

---

## Updating the analysis prompt

Edit `claude.analysis_prompt` in `config/config.yaml`.
Use `{transcript_text}` as the placeholder where transcript content is injected.

---

## Selector adjustments (important!)

Because Marble Health is a custom portal, the CSS selectors in
`src/portal_scraper.py` (the `SEL_*` constants at the top of the class)
may not exactly match the live HTML. If the agent fails at the login or
filter step:

1. Open `https://app.marblehealth.com/calls` in Chrome
2. Right-click the relevant element → **Inspect**
3. Copy a selector that uniquely identifies it
4. Update the matching `SEL_*` constant in `portal_scraper.py`

---

## Project layout

```
transcript_agent/
├── .github/workflows/weekly-analysis.yml   # GitHub Actions schedule
├── config/
│   └── config.yaml                         # All non-secret configuration
├── src/
│   ├── main.py                             # Pipeline orchestrator
│   ├── portal_scraper.py                   # Playwright login + download
│   ├── gmail_reader.py                     # Gmail API 2FA handler
│   ├── transcript_parser.py                # File parsing + grouping
│   ├── claude_analyzer.py                  # Anthropic API analysis
│   └── notion_writer.py                    # Notion API writer
├── downloads/                              # Temp directory (auto-cleaned)
├── requirements.txt
├── .env.example
└── README.md
```

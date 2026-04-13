# ABS Recap Dashboard

Flask dashboard that sends MLB ABS totals from Baseball Savant to Discord.

## What it does
- **Daily recap button**: sends ABS total challenges for **yesterday** by default.
- **Optional date picker**: choose any specific day and send that day’s Savant total.
- **Season total button**: sends the selected season’s Savant total challenges.
- Uses Baseball Savant pages as the data source.
- **Daily recap button**: posts **yesterday's** ABS recap by default, or a selected date using Baseball Savant totals.
- **Season total button**: posts a Baseball Savant season total for the selected year.
- Uses MLB Stats API for full recap parsing and Baseball Savant scraping for selected-date/season totals.
- Filters to pitch-call ABS challenges only (ball/strike/zone), excluding hit-by-pitch plays.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: `http://localhost:8080`

## Fly.io deployment (bare-bones)
1. Create the Fly app (one-time):

```bash
fly apps create abs-recap
```

2. Set required secrets:

```bash
fly secrets set DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
fly secrets set FLASK_SECRET_KEY="$(openssl rand -hex 32)"
```

3. Deploy:

```bash
fly deploy
```

4. Validate runtime:

```bash
fly status
fly logs
fly checks list
```

# ABS Recap Dashboard

Flask dashboard that sends MLB ABS pitch-challenge recaps to Discord.

## What it does
- **Daily recap button**: always posts **yesterday's** ABS results.
- **Season leaderboard button**: posts top hitters and fielders by challenge success rate.
- Uses MLB Stats API schedule + live feed endpoints.
- Filters to pitch-call ABS challenges only (ball/strike/zone), excluding hit-by-pitch plays.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open: `http://localhost:8080`

## Fly.io deployment notes
This repository includes a `Dockerfile` and `fly.toml` configured to run Gunicorn on `0.0.0.0:8080`.

1. Set required secrets:

```bash
fly secrets set DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
fly secrets set FLASK_SECRET_KEY="$(openssl rand -hex 32)"
```

2. Deploy using the included config:

```bash
fly deploy
```

3. If you see "app is not listening on 0.0.0.0:8080", verify the running image was built from this repo and check logs:

```bash
fly logs
fly ssh console -C "ps aux"
```
- App binds to `PORT` (default `8080`) for Fly runtime compatibility.
- Recommended process command:

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

- Required secret:
  - `DISCORD_WEBHOOK_URL`

## Parsing approach
Because ABS feed fields are still evolving, challenge detection is rule-based:
1. Must include ABS/challenge markers.
2. Must include pitch-call indicators (strike/ball/zone).
3. Must have pitch event evidence (`pitchData` on at least one play event).
4. Must not include HBP markers.

Role split (`hitter` vs `fielder`) is inferred from:
- explicit role markers in text when available,
- otherwise call-direction hints (`to ball` => hitter challenge, `to strike` => fielder challenge),
- then confirmed-call hints.

This keeps hitter and fielder leaderboards separate so the same player can appear independently in each role.

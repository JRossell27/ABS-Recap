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
python app.py
```

Open: `http://localhost:8080`

## Fly.io deployment (bare-bones)
This repository is now intentionally minimal for Fly deploy stability:
- Python 3.12 slim image
- production web process via Gunicorn (`gunicorn --bind 0.0.0.0:$PORT app:app`)
- internal port `8080`
- one always-on machine (`min_machines_running = 1`)

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

Notes:
- App binds to `PORT` (default `8080`) in `app.py`.
- Health endpoint is `GET /healthz`.
- Keep infra simple first; scale memory/count only after stable deploys.

## Parsing approach
Because ABS feed fields are still evolving, challenge detection is rule-based:
1. Must include ABS/challenge markers.
2. Must include pitch-call indicators (ball/strike/zone).
3. Must have pitch event evidence (`pitchData` on at least one play event).
4. Must not include HBP markers.

Role split (`hitter` vs `fielder`) is inferred from:
- explicit role markers in text when available,
- otherwise call-direction hints (`to ball` => hitter challenge, `to strike` => fielder challenge),
- then confirmed-call hints.

This keeps hitter and fielder leaderboards separate so the same player can appear independently in each role.

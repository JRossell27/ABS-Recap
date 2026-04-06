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

## Fly.io deployment (GitHub + Fly)
This repository includes a `Dockerfile` and `fly.toml` configured to run Gunicorn on `0.0.0.0:8080` with a `/healthz` check.

1. Create or verify the Fly app (one-time):

```bash
fly apps create abs-recap
```

2. Set required secrets:

```bash
fly secrets set DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
fly secrets set FLASK_SECRET_KEY="$(openssl rand -hex 32)"
```

3. Deploy from GitHub or local:

```bash
fly deploy
```

4. Ensure at least one machine is running:

```bash
fly machines list
fly scale count 1
```

5. Debug checks/logs if needed:

```bash
fly logs
fly status
```

Notes:
- App binds to `PORT` (default `8080`) for Fly runtime compatibility.
- `fly.toml` is set to `min_machines_running = 1` and `auto_stop_machines = "off"` to avoid ending up with zero machines.

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

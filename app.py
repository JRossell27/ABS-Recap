import os
from datetime import date

import requests
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for

from abs_service import ABSService

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

service = ABSService()


def _post_to_discord(message: str) -> None:
    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")

    response = requests.post(webhook, json={"content": message}, timeout=15)
    response.raise_for_status()


@app.get("/")
def index():
    return render_template("index.html")




@app.get("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.post("/send/daily")
def send_daily():
    try:
        recap = service.get_daily_recap()
        _post_to_discord(service.format_daily_discord_message(recap))
        flash(f"Daily recap sent for {recap['date'].isoformat()}.", "success")
    except Exception as exc:
        flash(f"Failed to send daily recap: {exc}", "error")
    return redirect(url_for("index"))


@app.post("/send/season")
def send_season():
    season_raw = request.form.get("season", "").strip()
    season = int(season_raw) if season_raw else date.today().year

    try:
        recap = service.get_season_leaderboard(season=season)
        _post_to_discord(service.format_season_discord_message(recap))
        flash(f"Season leaderboard sent for {season}.", "success")
    except Exception as exc:
        flash(f"Failed to send season leaderboard: {exc}", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

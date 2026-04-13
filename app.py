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
    target_date_raw = request.form.get("target_date", "").strip()
    target_date = date.fromisoformat(target_date_raw) if target_date_raw else None

    try:
        recap = service.get_daily_total(target_date=target_date)
        _post_to_discord(service.format_daily_discord_message(recap))
        flash(f"Daily Savant total sent for {recap['date'].isoformat()}.", "success")
        if target_date is None:
            recap = service.get_daily_recap()
            _post_to_discord(service.format_daily_discord_message(recap))
            flash(f"Daily recap sent for {recap['date'].isoformat()}.", "success")
        else:
            recap = service.get_savant_daily_total(target_date=target_date)
            message = "\n".join([
                "ABS Daily Recap ⚾️",
                recap["date"].strftime("%B %-d, %Y"),
                f"Total Challenges: {recap['total']}",
                "Source: Baseball Savant",
            ])
            _post_to_discord(message)
            flash(f"Daily Savant total sent for {recap['date'].isoformat()}.", "success")
    except Exception as exc:
        flash(f"Failed to send daily recap: {exc}", "error")
    return redirect(url_for("index"))


@app.post("/send/season")
def send_season():
    season_raw = request.form.get("season", "").strip()
    season = int(season_raw) if season_raw else date.today().year

    try:
        recap = service.get_season_total(season=season)
        _post_to_discord(service.format_season_discord_message(recap))
        recap = service.get_savant_season_total(season=season)
        message = "\n".join([
            f"ABS Season Summary {recap['season']} ⚾️",
            f"Total Challenges: {recap['total']}",
            "Source: Baseball Savant",
        ])
        _post_to_discord(message)
        flash(f"Season Savant total sent for {season}.", "success")
    except Exception as exc:
        flash(f"Failed to send season total: {exc}", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

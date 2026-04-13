from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any, Dict, Optional

import requests
from zoneinfo import ZoneInfo

SAVANT_ABS_DASHBOARD_URL = "https://baseballsavant.mlb.com/abs"
SAVANT_ABS_LEADERBOARD_URL = "https://baseballsavant.mlb.com/leaderboard/abs-challenges"
EASTERN = ZoneInfo("America/New_York")


class ABSService:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    def get_daily_total(self, target_date: Optional[date] = None, run_date: Optional[date] = None) -> Dict[str, Any]:
        use_date = target_date or ((run_date or self._today_eastern()) - timedelta(days=1))
        params = {
            "year": use_date.year,
            "level": "mlb",
            "gameType": "regular",
            "startDate": use_date.isoformat(),
            "endDate": use_date.isoformat(),
        }
        page = self._fetch_savant_page(SAVANT_ABS_LEADERBOARD_URL, params=params)
        return {
            "date": use_date,
            "total": self._parse_attempt_total(page),
            "source": "Baseball Savant",
        }

    def get_season_total(self, season: Optional[int] = None, run_date: Optional[date] = None) -> Dict[str, Any]:
        today = run_date or self._today_eastern()
        use_season = season or today.year
        params = {
            "year": use_season,
            "level": "mlb",
            "gameType": "regular",
        }
        page = self._fetch_savant_page(SAVANT_ABS_DASHBOARD_URL, params=params)
        return {
            "season": use_season,
            "total": self._parse_attempt_total(page),
            "source": "Baseball Savant",
        }

    def get_savant_daily_total(self, target_date: date) -> Dict[str, Any]:
        return self.get_daily_total(target_date=target_date)

    def get_savant_season_total(self, season: Optional[int] = None, run_date: Optional[date] = None) -> Dict[str, Any]:
        return self.get_season_total(season=season, run_date=run_date)

    def format_daily_discord_message(self, recap: Dict[str, Any]) -> str:
        return "\n".join(
            [
                "ABS Daily Recap ⚾️",
                recap["date"].strftime("%B %-d, %Y"),
                f"Total Challenges: {recap['total']}",
                f"Source: {recap.get('source', 'Baseball Savant')}",
            ]
        )

    def format_season_discord_message(self, recap: Dict[str, Any]) -> str:
        lines = [
            f"ABS Season Summary {recap['season']} ⚾️",
            f"Total Challenges: {recap['total']}",
        ]

        if "source" in recap:
            lines.append(f"Source: {recap.get('source', 'Baseball Savant')}")
        if "hitter_total" in recap:
            lines.append(f"Hitters: {recap['hitter_total']}")
        if "fielder_total" in recap:
            lines.append(f"Fielders: {recap['fielder_total']}")
        if "unknown_total" in recap:
            lines.append(f"Unclassified: {recap['unknown_total']}")

        return "\n".join(lines)

    def _fetch_savant_page(self, url: str, params: Dict[str, Any]) -> str:
        response = self.session.get(url, params=params, timeout=45)
        response.raise_for_status()
        return response.text

    def _parse_attempt_total(self, html: str) -> int:
        patterns = [
            r"\b([\d,]+)\s+(?:attempts?|challenges?)\b",
            r'"(?:totalChallenges|attemptTotal|totalAttempts|total)"\s*:\s*"?([\d,]+)"?',
            r'(?:totalChallenges|attemptTotal|totalAttempts|total)\s*=\s*"?([\d,]+)"?',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return int(match.group(1).replace(",", ""))

        raise ValueError("Could not find total ABS attempts on Baseball Savant page")

    def _today_eastern(self) -> date:
        return datetime.now(tz=EASTERN).date()

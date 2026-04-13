from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any, Dict, Optional

import requests
from zoneinfo import ZoneInfo

SAVANT_ABS_DASHBOARD_URL = "https://baseballsavant.mlb.com/abs"
SAVANT_ABS_LEADERBOARD_URL = "https://baseballsavant.mlb.com/leaderboard/abs-challenges"
MLB_BASE_URL = "https://statsapi.mlb.com/api/v1"
MLB_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
SAVANT_ABS_DASHBOARD_URL = "https://baseballsavant.mlb.com/abs"
SAVANT_ABS_LEADERBOARD_URL = "https://baseballsavant.mlb.com/leaderboard/abs-challenges"

CHALLENGE_EVENT_KEYWORDS = {
    "pitch challenge",
    "abs challenge",
    "manager challenge",
    "challenge",
    "replay review",
    "video review",
}
REVIEW_PRESENCE_KEYS = {"review", "reviews", "reviewDetails", "challenge", "challenged"}
ABS_REVIEW_TYPE_CODES = {"mj"}
EXCLUDED_KEYWORDS = {"hit by pitch", "hbp"}
OVERTURNED_KEYWORDS = {"overturned", "reversed", "changed", "flipped"}
CONFIRMED_KEYWORDS = {"confirmed", "upheld", "stands", "call stands"}
NON_ABS_REVIEW_TYPES = {"manager challenge", "replay review", "umpire review"}
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

    def get_savant_daily_total(self, target_date: date) -> Dict[str, Any]:
        params = {
            "year": target_date.year,
            "level": "mlb",
            "gameType": "regular",
            "startDate": target_date.isoformat(),
            "endDate": target_date.isoformat(),
        }
        page = self._fetch_savant_page(SAVANT_ABS_LEADERBOARD_URL, params=params)
        return {
            "date": target_date,
            "total": self._parse_attempt_total(page),
            "source": "baseballsavant",
        }

    def get_savant_season_total(self, season: Optional[int] = None, run_date: Optional[date] = None) -> Dict[str, Any]:
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
            "source": "baseballsavant",
        }

    def _fetch_savant_page(self, url: str, params: Dict[str, Any]) -> str:
        response = self.session.get(url, params=params, timeout=45)
        response.raise_for_status()
        return response.text

    def _parse_attempt_total(self, html: str) -> int:
        match = re.search(r"\b([\d,]+)\s+attempts\b", html, re.IGNORECASE)
        if not match:
            raise ValueError("Could not find total ABS attempts on Baseball Savant page")
        return int(match.group(1).replace(",", ""))

    def get_season_leaderboard(
        self,
        season: Optional[int] = None,
        top_n: int = 3,
        run_date: Optional[date] = None,
    ) -> Dict[str, Any]:
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

    def format_daily_discord_message(self, recap: Dict[str, Any]) -> str:
        return "\n".join([
            "ABS Daily Recap ⚾️",
            recap["date"].strftime("%B %-d, %Y"),
            f"Total Challenges: {recap['total']}",
            f"Source: {recap.get('source', 'Baseball Savant')}",
        ])

    def format_season_discord_message(self, recap: Dict[str, Any]) -> str:
        return "\n".join([
            f"ABS Season Summary {recap['season']} ⚾️",
            f"Total Challenges: {recap['total']}",
            f"Source: {recap.get('source', 'Baseball Savant')}",
        ])

    def _fetch_savant_page(self, url: str, params: Dict[str, Any]) -> str:
        response = self.session.get(url, params=params, timeout=45)
        response.raise_for_status()
        return response.text

    def _parse_attempt_total(self, html: str) -> int:
        match = re.search(r"\b([\d,]+)\s+attempts\b", html, re.IGNORECASE)
        if not match:
            raise ValueError("Could not find total ABS attempts on Baseball Savant page")
        return int(match.group(1).replace(",", ""))

    def _today_eastern(self) -> date:
        return datetime.now(tz=EASTERN).date()

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
        page = self._fetch_daily_page(use_date)
        return {
            "date": use_date,
            "total": self._parse_attempt_total(page),
            "source": "Baseball Savant",
        }

    def get_season_total(self, season: Optional[int] = None, run_date: Optional[date] = None) -> Dict[str, Any]:
        today = run_date or self._today_eastern()
        use_season = season or today.year
        page = self._fetch_season_page(use_season)
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
        response = self.session.get(url, params=params, headers=self._request_headers(), timeout=45)
        response.raise_for_status()
        return response.text

    def _fetch_daily_page(self, target_date: date) -> str:
        params = {
            "year": target_date.year,
            "level": "mlb",
            "gameType": "regular",
            "startDate": target_date.isoformat(),
            "endDate": target_date.isoformat(),
        }
        errors = []
        for url in (SAVANT_ABS_LEADERBOARD_URL, SAVANT_ABS_DASHBOARD_URL):
            try:
                return self._fetch_savant_page(url, params=params)
            except requests.RequestException as exc:
                errors.append(f"{url}: {exc}")
        raise RuntimeError("Failed to fetch Baseball Savant daily ABS page. " + " | ".join(errors))

    def _fetch_season_page(self, season: int) -> str:
        params = {
            "year": season,
            "level": "mlb",
            "gameType": "regular",
        }
        errors = []
        for url in (SAVANT_ABS_DASHBOARD_URL, SAVANT_ABS_LEADERBOARD_URL):
            try:
                return self._fetch_savant_page(url, params=params)
            except requests.RequestException as exc:
                errors.append(f"{url}: {exc}")
        raise RuntimeError("Failed to fetch Baseball Savant season ABS page. " + " | ".join(errors))

    def _request_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://baseballsavant.mlb.com/",
        }

    def _parse_attempt_total(self, html: str) -> int:
        pattern_priorities = [
            (
                r"\b(?:total|abs)\s*(?:challenges|attempts)\D+([\d,]+)\b",
                3,
            ),
            (
                r'"(?:totalChallenges|attemptTotal|totalAttempts|challengesTotal|challengeTotal|challenge_count|total)"\s*:\s*"?([\d,]+)"?',
                3,
            ),
            (
                r"(?:totalChallenges|attemptTotal|totalAttempts|challengesTotal|challengeTotal|challenge_count|total)\s*=\s*\"?([\d,]+)\"?",
                3,
            ),
            (
                r'data-(?:total-)?(?:challenges|attempts)\s*=\s*"([\d,]+)"',
                2,
            ),
            (
                r"\b([\d,]+)\s+(?:attempts?|challenges?)\b",
                1,
            ),
        ]

        candidates = []
        for pattern, priority in pattern_priorities:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                candidates.append((priority, int(match.group(1).replace(",", ""))))

        if candidates:
            return max(candidates, key=lambda item: (item[0], item[1]))[1]

        raise ValueError("Could not find total ABS attempts on Baseball Savant page")

    def _today_eastern(self) -> date:
        return datetime.now(tz=EASTERN).date()

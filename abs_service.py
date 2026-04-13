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
        overturn_breakdown = self._parse_daily_overturn_breakdown(page)
        return {
            "date": use_date,
            "total": overturn_breakdown.get("overall_total")
            or self._parse_daily_attempt_total(page, use_date),
            "overall_overturn_pct": overturn_breakdown.get("overall_pct"),
            "overall_overturns": overturn_breakdown.get("overall_overturns"),
            "batters_total": overturn_breakdown.get("batters_total"),
            "batters_overturn_pct": overturn_breakdown.get("batters_pct"),
            "batters_overturns": overturn_breakdown.get("batters_overturns"),
            "fielders_total": overturn_breakdown.get("fielders_total"),
            "fielders_overturn_pct": overturn_breakdown.get("fielders_pct"),
            "fielders_overturns": overturn_breakdown.get("fielders_overturns"),
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
        lines = [
            "ABS Daily Recap ⚾️",
            recap["date"].strftime("%B %-d, %Y"),
            f"Total Challenges: {recap['total']}",
        ]

        if recap.get("overall_overturn_pct") is not None and recap.get("overall_overturns") is not None:
            lines.append(
                f"Daily Overturn%: {recap['overall_overturn_pct']}% "
                f"({recap['overall_overturns']}/{recap['total']})"
            )

        if recap.get("batters_overturn_pct") is not None and recap.get("batters_overturns") is not None:
            lines.append(
                f"Batters Daily Overturn%: {recap['batters_overturn_pct']}% "
                f"({recap['batters_overturns']}/{recap.get('batters_total', '?')})"
            )

        if recap.get("fielders_overturn_pct") is not None and recap.get("fielders_overturns") is not None:
            lines.append(
                f"Fielders Daily Overturn%: {recap['fielders_overturn_pct']}% "
                f"({recap['fielders_overturns']}/{recap.get('fielders_total', '?')})"
            )

        lines.append(f"Source: {recap.get('source', 'Baseball Savant')}")
        return "\n".join(lines)

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
                r'"(?:totalChallenges|attemptTotal|totalAttempts|challengesTotal|challengeTotal|challenge_count)"\s*:\s*"?([\d,]+)"?',
                3,
            ),
            (
                r"(?:totalChallenges|attemptTotal|totalAttempts|challengesTotal|challengeTotal|challenge_count)\s*=\s*\"?([\d,]+)\"?",
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
            highest_priority = max(priority for priority, _ in candidates)
            for priority, value in candidates:
                if priority == highest_priority:
                    return value

        raise ValueError("Could not find total ABS attempts on Baseball Savant page")

    def _parse_daily_attempt_total(self, html: str, target_date: date) -> int:
        date_tokens = self._daily_date_tokens(target_date)
        date_pattern = "|".join(re.escape(token) for token in date_tokens)
        challenge_key_pattern = (
            r'"?(?:totalChallenges|attemptTotal|totalAttempts|challengesTotal|challengeTotal)"?'
            r"\s*[:=]\s*\"?([\d,]+)\"?"
        )

        date_scoped_candidates = []

        object_pattern = re.compile(r"\{[^{}]{0,1200}\}", re.IGNORECASE | re.DOTALL)
        for match in object_pattern.finditer(html):
            snippet = match.group(0)
            if not re.search(date_pattern, snippet, re.IGNORECASE):
                continue

            challenge_match = re.search(challenge_key_pattern, snippet, re.IGNORECASE)
            if challenge_match:
                date_scoped_candidates.append(int(challenge_match.group(1).replace(",", "")))

        if not date_scoped_candidates:
            forward_pattern = re.compile(
                rf"(?:{date_pattern}).{{0,200}}?(?:total\s*)?(?:challenges|attempts)\D{{0,20}}([\d,]+)",
                re.IGNORECASE | re.DOTALL,
            )
            reverse_pattern = re.compile(
                rf"(?:total\s*)?(?:challenges|attempts)\D{{0,20}}([\d,]+).{{0,200}}?(?:{date_pattern})",
                re.IGNORECASE | re.DOTALL,
            )

            for pattern in (forward_pattern, reverse_pattern):
                for match in pattern.finditer(html):
                    date_scoped_candidates.append(int(match.group(1).replace(",", "")))

        if date_scoped_candidates:
            return max(date_scoped_candidates)

        raise ValueError(f"Could not find total ABS attempts for selected date {target_date.isoformat()}")

    def _parse_daily_overturn_breakdown(self, html: str) -> Dict[str, Optional[int]]:
        matches = list(
            re.finditer(
                r"Daily\s+Overturn%\s*:?\s*(\d+)%\s*\((\d+)\s*/\s*(\d+)\)",
                html,
                re.IGNORECASE,
            )
        )
        if not matches:
            return {}

        sections = ["overall", "batters", "fielders"]
        breakdown: Dict[str, Optional[int]] = {}

        for idx, match in enumerate(matches[:3]):
            section = sections[idx]
            breakdown[f"{section}_pct"] = int(match.group(1))
            breakdown[f"{section}_overturns"] = int(match.group(2))
            breakdown[f"{section}_total"] = int(match.group(3))

        return breakdown

    def _daily_date_tokens(self, target_date: date) -> list[str]:
        return [
            target_date.isoformat(),
            f"{target_date.month}/{target_date.day}/{target_date.year}",
            f"{target_date.month:02d}/{target_date.day:02d}/{target_date.year}",
            f"{target_date.month}/{target_date.day}/{target_date.year % 100:02d}",
            f"{target_date.month:02d}/{target_date.day:02d}/{target_date.year % 100:02d}",
        ]

    def _today_eastern(self) -> date:
        return datetime.now(tz=EASTERN).date()

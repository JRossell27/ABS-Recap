from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from zoneinfo import ZoneInfo

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
ABS_CHALLENGE_WORDING_RE = re.compile(
    r"\b(?P<family>Ball|Strike)\s+(?P<number>\d+)\s+call\s+"
    r"(?P<status>overturned|confirmed|upheld|stands|call stands)\s+after\s+ABS\s+challenge\b",
    re.IGNORECASE,
)
ABS_CHALLENGE_RESULT_RE = re.compile(
    r"\bABS\s+challenge\b.*\bcall\s+(?P<status>overturned|confirmed|upheld|stands|call stands)\b",
    re.IGNORECASE,
)
PLAY_CALL_BALL_CODES = {"B"}
PLAY_CALL_STRIKE_CODES = {"C", "S"}


@dataclass
class ChallengeEvent:
    game_pk: int
    game_label: str
    inning_label: str
    description: str
    overturned: bool
    confirmed: bool
    win_probability_delta: float
    challenger_id: Optional[int]
    challenger_name: str
    role: Optional[str]  # hitter | fielder


class ABSService:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    def get_daily_recap(self, run_date: Optional[date] = None, debug: bool = False) -> Dict[str, Any]:
        today = run_date or self._today_eastern()
        target_date = today - timedelta(days=1)

        games = self._fetch_schedule_for_date(target_date)
        per_game_log: List[Dict[str, Any]] = []
        events, failed_games = self._collect_events_from_games(
            games,
            target_date=target_date,
            target_uses_start_date=False,
            per_game_log=per_game_log if debug else None,
        )

        result: Dict[str, Any] = {
            "date": target_date,
            "total": len(events),
            "failed_games": failed_games,
            "games_scanned": len(games),
        }
        if debug:
            result["per_game"] = per_game_log
        return result


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

        start_date = date(use_season, 3, 25)
        end_date = today - timedelta(days=1)
        if end_date < start_date:
            end_date = start_date

        games = self._fetch_schedule_date_range(start_date, end_date)
        events, failed_games = self._collect_events_from_games(games, start_date=start_date, end_date=end_date)

        hitter_total = sum(1 for event in events if event.role == "hitter")
        fielder_total = sum(1 for event in events if event.role == "fielder")

        return {
            "season": use_season,
            "total": len(events),
            "hitter_total": hitter_total,
            "fielder_total": fielder_total,
            "unknown_total": len(events) - hitter_total - fielder_total,
            "failed_games": failed_games,
            "games_scanned": len(games),
            "hitters": self._build_player_rows(events, role="hitter", top_n=top_n),
            "fielders": self._build_player_rows(events, role="fielder", top_n=top_n),
        }

    def format_daily_discord_message(self, recap: Dict[str, Any]) -> str:
        lines = [
            "ABS Daily Recap ⚾️",
            recap["date"].strftime("%B %-d, %Y"),
            f"Total Challenges: {recap['total']}",
        ]

        return "\n".join(lines)

    def format_season_discord_message(self, recap: Dict[str, Any]) -> str:
        lines = [
            f"ABS Leaderboard {recap.get('season', '')} ⚾️",
            f"Total Challenges: {recap.get('total', 0)}",
            f"Hitters: {recap.get('hitter_total', 0)}",
            f"Fielders: {recap.get('fielder_total', 0)}",
        ]

        unknown_total = recap.get("unknown_total", 0)
        if unknown_total:
            lines.append(f"Unclassified: {unknown_total}")

        failed_games = recap.get("failed_games", 0)
        games_scanned = recap.get("games_scanned", 0)
        if failed_games:
            lines.append(f"⚠️ Data fetch issues: {failed_games}/{games_scanned} games unavailable")

        lines.append("Hitters (Success Rate)")
        hitters = recap.get("hitters", [])
        if hitters:
            for row in hitters:
                lines.append(f"{row['name']} — [{row['wins']}/{row['total']}] ({row['success_rate']:.1f}%)")
        else:
            lines.append("No hitter challenges yet")

        lines.append("Fielders (Success Rate)")
        fielders = recap.get("fielders", [])
        if fielders:
            for row in fielders:
                lines.append(f"{row['name']} — [{row['wins']}/{row['total']}] ({row['success_rate']:.1f}%)")
        else:
            lines.append("No fielder challenges yet")

        return "\n".join(lines)

    def _fetch_schedule_for_date(self, target: date) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{MLB_BASE_URL}/schedule",
            params={"sportId": 1, "date": target.isoformat()},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        games: List[Dict[str, Any]] = []
        for day in payload.get("dates", []):
            games.extend(day.get("games", []))
        return games

    def _fetch_schedule_date_range(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{MLB_BASE_URL}/schedule",
            params={"sportId": 1, "startDate": start_date.isoformat(), "endDate": end_date.isoformat()},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        games: List[Dict[str, Any]] = []
        for day in payload.get("dates", []):
            games.extend(day.get("games", []))
        return games

    def _collect_events_from_games(
        self,
        games: Iterable[Dict[str, Any]],
        target_date: Optional[date] = None,
        target_uses_start_date: bool = False,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        per_game_log: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[ChallengeEvent], int]:
        events: List[ChallengeEvent] = []
        failed_games = 0

        for game in games:
            game_pk = game.get("gamePk")
            if not game_pk:
                continue
            game_date = (
                self._game_start_date_eastern(game) if target_uses_start_date else self._game_official_date(game)
            )
            if target_date and game_date != target_date:
                if per_game_log is not None:
                    per_game_log.append({
                        "gamePk": game_pk,
                        "officialDate": game.get("officialDate"),
                        "gameDate": game.get("gameDate"),
                        "resolved_date": str(game_date),
                        "status": "skipped_date_mismatch",
                        "challenges": 0,
                    })
                continue
            if start_date and game_date and game_date < start_date:
                continue
            if end_date and game_date and game_date > end_date:
                continue
            try:
                feed = self._fetch_game_feed(game_pk)
            except requests.RequestException:
                failed_games += 1
                if per_game_log is not None:
                    per_game_log.append({
                        "gamePk": game_pk,
                        "officialDate": game.get("officialDate"),
                        "gameDate": game.get("gameDate"),
                        "resolved_date": str(game_date),
                        "status": "fetch_failed",
                        "challenges": 0,
                    })
                continue
            game_events = self._parse_game_events(feed, game_pk)
            events.extend(game_events)
            if per_game_log is not None:
                teams = feed.get("gameData", {}).get("teams", {})
                away = teams.get("away", {}).get("abbreviation", "AWY")
                home = teams.get("home", {}).get("abbreviation", "HME")
                per_game_log.append({
                    "gamePk": game_pk,
                    "matchup": f"{away}@{home}",
                    "officialDate": game.get("officialDate"),
                    "gameDate": game.get("gameDate"),
                    "resolved_date": str(game_date),
                    "status": "ok",
                    "challenges": len(game_events),
                })

        return events, failed_games

    def _fetch_game_feed(self, game_pk: int) -> Dict[str, Any]:
        response = self.session.get(MLB_FEED_URL.format(game_pk=game_pk), timeout=30)
        response.raise_for_status()
        return response.json()

    def _today_eastern(self) -> date:
        return datetime.now(tz=EASTERN).date()

    def _game_start_date_eastern(self, game: Dict[str, Any]) -> Optional[date]:
        game_date = game.get("gameDate")
        if not isinstance(game_date, str) or not game_date.strip():
            return None
        normalized = game_date.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(EASTERN).date()

    def _game_official_date(self, game: Dict[str, Any]) -> Optional[date]:
        """
        Prefer MLB's official game date (schedule day) to align with Baseball Savant daily splits.
        Fall back to ET-converted game start date when officialDate is unavailable.
        """
        official_date = game.get("officialDate")
        if isinstance(official_date, str):
            text = official_date.strip()
            if text:
                try:
                    return date.fromisoformat(text)
                except ValueError:
                    pass
        return self._game_start_date_eastern(game)

    def _parse_game_events(self, feed: Dict[str, Any], game_pk: int) -> List[ChallengeEvent]:
        plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        teams = feed.get("gameData", {}).get("teams", {})
        away = teams.get("away", {}).get("abbreviation", "AWY")
        home = teams.get("home", {}).get("abbreviation", "HME")
        game_label = f"{away}–{home}"

        output: List[ChallengeEvent] = []
        seen_challenges: set[str] = set()
        away_id = teams.get("away", {}).get("id")
        home_id = teams.get("home", {}).get("id")
        for play in plays:
            play["_teams_context"] = {"away_id": away_id, "home_id": home_id}
            for challenge_context in self._extract_all_abs_challenge_contexts(play):
                challenge_uid = challenge_context["uid"]
                if challenge_uid in seen_challenges:
                    continue
                seen_challenges.add(challenge_uid)

                overturned = challenge_context["overturned"]
                confirmed = not overturned
                description = challenge_context["description"]
                subject_pitch = challenge_context["pitch_event"]

                inning = play.get("about", {}).get("inning")
                half = play.get("about", {}).get("halfInning", "").capitalize()
                inning_label = f"{half} {inning}" if inning else half

                challenger_id, challenger_name, role = self._infer_challenger(
                    play=play,
                    subject_pitch_event=subject_pitch,
                    challenge_team_id=challenge_context.get("challenge_team_id"),
                )

                output.append(
                    ChallengeEvent(
                        game_pk=game_pk,
                        game_label=game_label,
                        inning_label=inning_label,
                        description=description,
                        overturned=overturned,
                        confirmed=confirmed,
                        win_probability_delta=self._win_probability_delta(play),
                        challenger_id=challenger_id,
                        challenger_name=challenger_name,
                        role=role,
                    )
                )

        return output

    def _extract_all_abs_challenge_contexts(self, play: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract all ABS challenge contexts from a single at-bat play.

        An at-bat can have multiple challenged pitches (e.g., a batter challenges
        pitch 2, then the catcher challenges pitch 5 in the same at-bat). The
        original _extract_abs_challenge_context only finds the first challenge event,
        causing subsequent challenges in the same at-bat to be silently dropped.

        When multiple play events are each explicitly tagged with reviewType='mj',
        each is treated as an independent challenge and a context is built for it.
        Otherwise this falls back to the existing single-challenge logic so behaviour
        is unchanged for the common case.
        """
        text = self._collect_play_text(play).lower()
        if any(k in text for k in EXCLUDED_KEYWORDS):
            return []

        play_events = play.get("playEvents", [])

        # Find every event that carries its own ABS review tag.
        mj_indices = [
            idx for idx, event in enumerate(play_events)
            if str(
                (self._review_dict(event.get("reviewDetails")) or {}).get("reviewType", "")
            ).strip().lower() in ABS_REVIEW_TYPE_CODES
        ]

        if len(mj_indices) > 1:
            # Multiple distinct ABS challenges within this at-bat.
            contexts = []
            for event_idx in mj_indices:
                ctx = self._build_abs_context_for_event(play, play_events, event_idx)
                if ctx is not None:
                    contexts.append(ctx)
            return contexts

        # Single tagged event (or none) — use the existing play-level logic so
        # all existing detection paths (text-based, play-level reviewDetails, etc.)
        # continue to work exactly as before.
        single = self._extract_abs_challenge_context(play)
        return [single] if single is not None else []

    def _build_abs_context_for_event(
        self,
        play: Dict[str, Any],
        play_events: List[Dict[str, Any]],
        event_idx: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a challenge context dict for a specific ABS challenge event index.
        Used by _extract_all_abs_challenge_contexts for multi-challenge at-bats.
        """
        event = play_events[event_idx] if event_idx < len(play_events) else None
        event_review = self._review_dict((event or {}).get("reviewDetails")) or {}

        review_type = str(event_review.get("reviewType", "")).strip().lower()
        if review_type and any(t in review_type for t in NON_ABS_REVIEW_TYPES):
            return None
        if review_type not in ABS_REVIEW_TYPE_CODES:
            return None
        if event_review.get("inProgress") is True:
            return None

        # Prefer the explicit boolean stored on the event-level review; fall back
        # to play-level text inference only if the boolean is absent.
        overturned: Optional[bool] = None
        for key in ("isOverturned", "overturned"):
            value = event_review.get(key)
            if isinstance(value, bool):
                overturned = value
                break

        if overturned is None:
            overturned, _ = self._infer_review_outcome_with_context(play, event_review)

        if overturned is None:
            # reviewType="mj" was already confirmed; the outcome boolean is simply
            # missing from this event's data.  Count it as confirmed rather than drop.
            overturned = False

        pitch_event = self._find_challenged_pitch_event(play_events, event_idx)
        uid_parts = [
            str(play.get("about", {}).get("atBatIndex", "")),
            str((pitch_event or {}).get("playId") or (event or {}).get("playId") or event_idx or ""),
            "abs",
        ]
        return {
            "uid": "_".join(uid_parts),
            "overturned": overturned,
            "description": self._challenge_description(play, event),
            "pitch_event": pitch_event,
            "challenge_team_id": event_review.get("challengeTeamId"),
        }

    def _is_abs_pitch_challenge(self, play: Dict[str, Any]) -> bool:
        return self._extract_abs_challenge_context(play) is not None

    def _extract_abs_challenge_context(self, play: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build a canonical ABS challenge from one at-bat play.
        Returns None when the play is not a resolved ABS challenge.
        """
        text = self._collect_play_text(play).lower()
        if any(k in text for k in EXCLUDED_KEYWORDS):
            return None

        play_events = play.get("playEvents", [])
        play_review = play.get("reviewDetails")
        if play_review is None:
            play_review = play.get("review")
        play_review = play_review if isinstance(play_review, dict) else {}
        event_idx = self._find_challenge_event_index(play, play_events, play_review)
        event = play_events[event_idx] if event_idx is not None and event_idx < len(play_events) else None

        review = self._merged_review_details(play, event)
        review_type = str(review.get("reviewType", "")).strip().lower()
        if review_type and any(t in review_type for t in NON_ABS_REVIEW_TYPES):
            return None

        if review_type not in ABS_REVIEW_TYPE_CODES:
            if not (self._extract_abs_call_phrase(play) or self._extract_abs_result_phrase(play)):
                return None

        if review.get("inProgress") is True:
            return None

        overturned, _confirmed = self._infer_review_outcome_with_context(play, review)
        if overturned is None:
            if review_type in ABS_REVIEW_TYPE_CODES:
                # The reviewType confirms this is a resolved ABS challenge, but the
                # outcome field is absent from the API response.  Default to confirmed
                # (overturned=False) so the challenge is counted rather than silently
                # dropped, which would undercount the day's total.
                overturned = False
            else:
                return None

        pitch_event = self._find_challenged_pitch_event(play_events, event_idx)
        uid_parts = [
            str(play.get("about", {}).get("atBatIndex", "")),
            str((pitch_event or {}).get("playId") or (event or {}).get("playId") or event_idx or ""),
            "abs",
        ]
        uid = "_".join(uid_parts)

        description = self._challenge_description(play, event)
        return {
            "uid": uid,
            "overturned": overturned,
            "description": description,
            "pitch_event": pitch_event,
            "challenge_team_id": review.get("challengeTeamId"),
        }

    def _extract_abs_call_phrase(self, play: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        text = self._collect_play_text(play)
        match = ABS_CHALLENGE_WORDING_RE.search(text)
        if not match:
            return None

        family = match.group("family").strip().lower()
        status = self._normalize_abs_status(match.group("status"))
        try:
            number = int(match.group("number"))
        except (TypeError, ValueError):
            number = None

        return {"family": family, "number": number, "status": status}

    def _extract_abs_result_phrase(self, play: Dict[str, Any]) -> Optional[str]:
        text = self._collect_play_text(play)
        match = ABS_CHALLENGE_RESULT_RE.search(text)
        if not match:
            return None
        return self._normalize_abs_status(match.group("status"))

    def _normalize_abs_status(self, status: Any) -> str:
        normalized = str(status or "").strip().lower()
        if normalized in {"upheld", "stands", "call stands"}:
            return "confirmed"
        return normalized

    def _collect_play_text(self, play: Dict[str, Any]) -> str:
        chunks: List[str] = []

        result = play.get("result", {})
        if isinstance(result, dict):
            for key in ("description", "event", "eventType"):
                value = result.get(key)
                if isinstance(value, str):
                    chunks.append(value)

        for event in play.get("playEvents", []):
            if not isinstance(event, dict):
                continue
            details = event.get("details")
            if isinstance(details, dict):
                for value in details.values():
                    if isinstance(value, str):
                        chunks.append(value)
            for key in ("description", "event", "type"):
                value = event.get(key)
                if isinstance(value, str):
                    chunks.append(value)

        chunks.extend(self._recursive_strings(play))
        return " | ".join(chunks)

    def _challenge_description(self, play: Dict[str, Any], event: Optional[Dict[str, Any]] = None) -> str:
        if isinstance(event, dict):
            details = event.get("details", {})
            if isinstance(details, dict):
                event_description = details.get("description")
                if isinstance(event_description, str) and event_description.strip():
                    return event_description.strip()
            direct_description = event.get("description")
            if isinstance(direct_description, str) and direct_description.strip():
                return direct_description.strip()

        result_description = play.get("result", {}).get("description")
        if isinstance(result_description, str) and result_description.strip():
            return result_description.strip()

        for event in play.get("playEvents", []):
            if not isinstance(event, dict):
                continue
            details = event.get("details", {})
            if not isinstance(details, dict):
                continue
            description = details.get("description")
            if isinstance(description, str) and description.strip():
                return description.strip()

        return "ABS challenge"

    def _extract_review_type(self, play: Dict[str, Any]) -> str:
        for review in self._review_nodes(play):
            for key in ("reviewType", "type", "description", "details"):
                value = review.get(key)
                if isinstance(value, str) and value.strip():
                    return value
                if isinstance(value, dict):
                    for nested_value in value.values():
                        if isinstance(nested_value, str) and nested_value.strip():
                            return nested_value
        return ""

    def _has_abs_review_metadata(self, play: Dict[str, Any]) -> bool:
        for review in self._review_nodes(play):
            review_blob = self._recursive_strings(review)
            if any("ball" in chunk.lower() and "strike" in chunk.lower() for chunk in review_blob if isinstance(chunk, str)):
                return True
            if any("abs" in chunk.lower() for chunk in review_blob if isinstance(chunk, str)):
                return True
            if str(review.get("reviewType", "")).lower() in ABS_REVIEW_TYPE_CODES:
                return True

            for key in ("isOverturned", "overturned"):
                if isinstance(review.get(key), bool):
                    return True
        return False

    def _has_review_marker(self, play: Dict[str, Any]) -> bool:
        if isinstance(play.get("review"), dict):
            return True
        if isinstance(play.get("reviewDetails"), dict):
            return True

        for key in REVIEW_PRESENCE_KEYS:
            if self._has_meaningful_review_value(play.get(key)):
                return True

        text = self._collect_play_text(play).lower()
        return "review" in text

    def _has_meaningful_review_value(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        return True

    def _infer_review_outcome(self, play: Dict[str, Any]) -> Tuple[Optional[bool], Optional[bool]]:
        return self._infer_review_outcome_with_context(play, {})

    def _infer_review_outcome_with_context(
        self, play: Dict[str, Any], merged_review: Dict[str, Any]
    ) -> Tuple[Optional[bool], Optional[bool]]:
        text = self._collect_play_text(play).lower()
        abs_result_status = self._extract_abs_result_phrase(play)
        if abs_result_status == "overturned":
            return True, False
        if abs_result_status == "confirmed":
            return False, True

        if any(k in text for k in OVERTURNED_KEYWORDS):
            return True, False
        if any(k in text for k in CONFIRMED_KEYWORDS):
            return False, True

        for key in ("isOverturned", "overturned"):
            value = merged_review.get(key)
            if isinstance(value, bool):
                return value, not value

        for key in ("decision", "result", "reviewResult", "description"):
            value = merged_review.get(key)
            if isinstance(value, str):
                normalized = value.lower()
                if any(k in normalized for k in OVERTURNED_KEYWORDS):
                    return True, False
                if any(k in normalized for k in CONFIRMED_KEYWORDS):
                    return False, True

        for review in self._review_nodes(play):
            for key in ("isOverturned", "overturned"):
                value = review.get(key)
                if isinstance(value, bool):
                    return value, not value

            for key in ("decision", "result", "reviewResult", "description"):
                value = review.get(key)
                if isinstance(value, str):
                    normalized = value.lower()
                    if any(k in normalized for k in OVERTURNED_KEYWORDS):
                        return True, False
                    if any(k in normalized for k in CONFIRMED_KEYWORDS):
                        return False, True

        return None, None

    def _review_nodes(self, play: Dict[str, Any]) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        for key in ("review", "reviewDetails"):
            node = play.get(key)
            if isinstance(node, dict):
                nodes.append(node)

        for event in play.get("playEvents", []):
            if not isinstance(event, dict):
                continue
            event_review = event.get("reviewDetails")
            if isinstance(event_review, dict):
                nodes.append(event_review)

            details = event.get("details")
            if isinstance(details, dict):
                details_review = details.get("reviewDetails")
                if isinstance(details_review, dict):
                    nodes.append(details_review)

        return nodes

    def _infer_challenger(
        self,
        play: Dict[str, Any],
        subject_pitch_event: Optional[Dict[str, Any]] = None,
        challenge_team_id: Optional[Any] = None,
    ) -> Tuple[Optional[int], str, Optional[str]]:
        text = self._collect_play_text(play).lower()
        batter = play.get("matchup", {}).get("batter", {})
        pitcher = play.get("matchup", {}).get("pitcher", {})
        is_top = play.get("about", {}).get("isTopInning", True)
        teams = play.get("_teams_context", {})
        away_id = teams.get("away_id")
        home_id = teams.get("home_id")
        batting_side = "away" if is_top else "home"
        fielding_side = "home" if is_top else "away"

        if challenge_team_id is not None and away_id is not None and home_id is not None:
            if str(challenge_team_id) == str(away_id):
                return (
                    batter.get("id"),
                    batter.get("fullName", "Unknown Hitter"),
                    "hitter" if batting_side == "away" else "fielder",
                )
            if str(challenge_team_id) == str(home_id):
                return (
                    batter.get("id"),
                    batter.get("fullName", "Unknown Hitter"),
                    "hitter" if batting_side == "home" else "fielder",
                )

        pitch_code = self._pitch_call_code(subject_pitch_event)
        if pitch_code in PLAY_CALL_STRIKE_CODES:
            return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
        if pitch_code in PLAY_CALL_BALL_CODES:
            return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"

        overturned = any(k in text for k in OVERTURNED_KEYWORDS)
        abs_phrase = self._extract_abs_call_phrase(play)
        final_call = self._infer_final_call(play)

        if any(marker in text for marker in ("batter challenge", "hitter challenge", "challenged by batter")):
            return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
        if any(marker in text for marker in ("catcher challenge", "pitcher challenge", "challenged by defense")):
            return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"

        if "to ball" in text or "changed to ball" in text or "overturned to ball" in text:
            return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
        if "to strike" in text or "changed to strike" in text or "overturned to strike" in text:
            return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"

        if "confirmed called strike" in text or "call stands as strike" in text:
            return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
        if "confirmed called ball" in text or "call stands as ball" in text:
            return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"

        if abs_phrase:
            original_family = abs_phrase.get("family")
            status = abs_phrase.get("status")
            if status == "overturned":
                if original_family == "strike":
                    return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
                if original_family == "ball":
                    return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"
            if status == "confirmed":
                if original_family == "strike":
                    return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
                if original_family == "ball":
                    return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"

        if final_call == "ball":
            if overturned:
                return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
            return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"
        if final_call == "strike":
            if overturned:
                return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"
            return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"

        return None, "Unknown Challenger", None

    def _find_challenge_event_index(
        self,
        play: Dict[str, Any],
        play_events: List[Dict[str, Any]],
        play_review: Dict[str, Any],
    ) -> Optional[int]:
        if not play_events:
            return None

        if play_review:
            for idx, event in enumerate(play_events):
                event_review = self._review_dict(event.get("reviewDetails")) or {}
                event_review_type = str(event_review.get("reviewType", "")).lower()
                if event_review_type in ABS_REVIEW_TYPE_CODES:
                    return idx

            for idx, event in enumerate(play_events):
                if event.get("isPitch"):
                    continue
                details = event.get("details", {})
                if self._has_challenge_keyword(
                    details.get("event", ""),
                    details.get("eventType", ""),
                    details.get("description", ""),
                    event.get("description", ""),
                ):
                    return idx

            for idx, event in enumerate(play_events):
                details = event.get("details", {})
                if isinstance(details, dict) and details.get("hasReview"):
                    return idx

            return len(play_events) - 1

        for idx, event in enumerate(play_events):
            details = event.get("details", {})
            if self._has_challenge_keyword(
                details.get("event", ""),
                details.get("eventType", ""),
                details.get("description", ""),
                event.get("description", ""),
            ):
                return idx

            review = self._merged_review_details(play, event)
            if review.get("reviewType") or review.get("inProgress") is not None:
                return idx

        return None

    def _find_challenged_pitch_event(
        self, play_events: List[Dict[str, Any]], challenge_event_idx: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        if challenge_event_idx is None or not play_events:
            return None

        event = play_events[challenge_event_idx]
        if event.get("isPitch"):
            return event

        for idx in range(challenge_event_idx - 1, -1, -1):
            candidate = play_events[idx]
            if candidate.get("isPitch"):
                return candidate

        return None

    def _merged_review_details(
        self, play: Dict[str, Any], play_event: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        play_review = self._review_dict(play.get("reviewDetails")) or self._review_dict(play.get("review")) or {}
        event_review = {}
        if isinstance(play_event, dict):
            details = play_event.get("details", {})
            if isinstance(details, dict):
                event_review = self._review_dict(details.get("reviewDetails")) or {}
            if not event_review:
                event_review = self._review_dict(play_event.get("reviewDetails")) or {}
        merged = dict(play_review)
        for key, value in event_review.items():
            if value is not None:
                merged[key] = value
        return merged

    def _review_dict(self, value: Any) -> Optional[Dict[str, Any]]:
        return value if isinstance(value, dict) else None

    def _has_challenge_keyword(self, *parts: Any) -> bool:
        text = " ".join(str(p or "") for p in parts).lower()
        return any(keyword in text for keyword in CHALLENGE_EVENT_KEYWORDS)

    def _pitch_call_code(self, pitch_event: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(pitch_event, dict):
            return None
        details = pitch_event.get("details", {})
        if not isinstance(details, dict):
            return None
        call = details.get("call", {})
        if isinstance(call, dict):
            code = call.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip().upper()
        code = details.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip().upper()
        return None

    def _infer_final_call(self, play: Dict[str, Any]) -> Optional[str]:
        text = self._collect_play_text(play).lower()
        abs_phrase = self._extract_abs_call_phrase(play)

        if "called strike" in text or "to strike" in text or "as strike" in text:
            return "strike"
        if "called ball" in text or "to ball" in text or "as ball" in text:
            return "ball"

        if abs_phrase:
            original_family = abs_phrase.get("family")
            status = abs_phrase.get("status")
            if original_family in {"ball", "strike"} and status in {"overturned", "confirmed"}:
                if status == "confirmed":
                    return original_family
                return "ball" if original_family == "strike" else "strike"

        for event in reversed(play.get("playEvents", [])):
            if not isinstance(event, dict):
                continue
            details = event.get("details", {})
            if not isinstance(details, dict):
                continue

            description = details.get("description")
            if isinstance(description, str):
                lower_description = description.lower()
                if "called strike" in lower_description:
                    return "strike"
                if "called ball" in lower_description:
                    return "ball"

            code = details.get("code")
            if isinstance(code, str):
                normalized = code.upper()
                if normalized in {"C", "S"}:
                    return "strike"
                if normalized in {"B", "I", "P", "V"}:
                    return "ball"

        return None

    def _win_probability_delta(self, play: Dict[str, Any]) -> float:
        about = play.get("about", {})
        added = about.get("homeWinProbabilityAdded")
        if isinstance(added, (int, float)):
            return abs(float(added))

        candidates: List[float] = []
        for key in ("homeWinProbability", "awayWinProbability", "winProbability"):
            value = about.get(key)
            if isinstance(value, (int, float)):
                candidates.append(abs(float(value)))

        return max(candidates) if candidates else 0.0

    def _build_player_rows(self, events: List[ChallengeEvent], role: str, top_n: int) -> List[Dict[str, Any]]:
        rows: Dict[Tuple[Optional[int], str], Dict[str, Any]] = {}

        for event in events:
            if event.role != role:
                continue

            key = (event.challenger_id, event.challenger_name)
            current = rows.setdefault(key, {"name": event.challenger_name, "wins": 0, "total": 0, "success_rate": 0.0})
            current["total"] += 1
            if event.overturned:
                current["wins"] += 1

        values = list(rows.values())
        for row in values:
            row["success_rate"] = (row["wins"] / row["total"] * 100.0) if row["total"] else 0.0

        values.sort(key=lambda row: (row["success_rate"], row["total"]), reverse=True)
        return values[:top_n]

    def _recursive_strings(self, value: Any) -> List[str]:
        output: List[str] = []
        if isinstance(value, dict):
            for nested in value.values():
                output.extend(self._recursive_strings(nested))
        elif isinstance(value, list):
            for nested in value:
                output.extend(self._recursive_strings(nested))
        elif isinstance(value, str):
            output.append(value)
        return output

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

MLB_BASE_URL = "https://statsapi.mlb.com/api/v1"
MLB_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"

ABS_CONTEXT_KEYWORDS = {
    "abs",
    "automatic balls and strikes",
    "automatic ball strike",
    "automatic ball-strike",
    "ball-strike challenge",
    "ball/strike",
    "strike zone",
    "pitch challenge",
}
CHALLENGE_KEYWORDS = {"challenge", "challenged"}
REVIEW_PRESENCE_KEYS = {"review", "reviews", "reviewDetails", "challenge", "challenged"}
PITCH_CALL_KEYWORDS = {"called strike", "called ball", "to strike", "to ball", "strike", "ball", "zone"}
ABS_REVIEW_TYPE_CODES = {"mj"}
EXCLUDED_KEYWORDS = {"hit by pitch", "hbp"}
OVERTURNED_KEYWORDS = {"overturned", "reversed", "changed", "flipped"}
CONFIRMED_KEYWORDS = {"confirmed", "upheld", "stands", "call stands"}
NON_ABS_REVIEW_TYPES = {"manager challenge", "replay review", "umpire review"}


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

    def get_daily_recap(self, run_date: Optional[date] = None) -> Dict[str, Any]:
        today = run_date or date.today()
        target_date = today - timedelta(days=1)

        games = self._fetch_schedule_for_date(target_date)
        events, failed_games = self._collect_events_from_games(games)

        overturned = sum(1 for event in events if event.overturned)
        confirmed = sum(1 for event in events if event.confirmed)
        total = len(events)
        hitter_total = sum(1 for event in events if event.role == "hitter")
        fielder_total = sum(1 for event in events if event.role == "fielder")

        return {
            "date": target_date,
            "total": total,
            "hitter_total": hitter_total,
            "fielder_total": fielder_total,
            "overturned": overturned,
            "confirmed": confirmed,
            "success_rate": (overturned / total * 100.0) if total else 0.0,
            "failed_games": failed_games,
            "games_scanned": len(games),
        }

    def get_season_leaderboard(
        self,
        season: Optional[int] = None,
        top_n: int = 3,
        run_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        today = run_date or date.today()
        use_season = season or today.year

        start_date = date(use_season, 3, 25)
        end_date = today - timedelta(days=1)
        if end_date < start_date:
            end_date = start_date

        games = self._fetch_schedule_date_range(start_date, end_date)
        events, failed_games = self._collect_events_from_games(games)

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
            f"ABS Daily Recap For {recap['date'].isoformat()} ⚾️",
            f"Total Challenges: {recap['total']}",
            f"Hitters: {recap.get('hitter_total', 0)}",
            f"Fielders: {recap.get('fielder_total', 0)}",
            f"Overturned: {recap['overturned']}",
            f"Confirmed: {recap['confirmed']}",
            f"Success Rate: {recap['success_rate']:.1f}%",
        ]

        failed_games = recap.get("failed_games", 0)
        games_scanned = recap.get("games_scanned", 0)
        if failed_games:
            lines.append(f"⚠️ Data fetch issues: {failed_games}/{games_scanned} games unavailable")

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

    def _collect_events_from_games(self, games: Iterable[Dict[str, Any]]) -> Tuple[List[ChallengeEvent], int]:
        events: List[ChallengeEvent] = []
        failed_games = 0

        for game in games:
            game_pk = game.get("gamePk")
            if not game_pk:
                continue
            try:
                feed = self._fetch_game_feed(game_pk)
            except requests.RequestException:
                failed_games += 1
                continue
            events.extend(self._parse_game_events(feed, game_pk))

        return events, failed_games

    def _fetch_game_feed(self, game_pk: int) -> Dict[str, Any]:
        response = self.session.get(MLB_FEED_URL.format(game_pk=game_pk), timeout=30)
        response.raise_for_status()
        return response.json()

    def _parse_game_events(self, feed: Dict[str, Any], game_pk: int) -> List[ChallengeEvent]:
        plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        teams = feed.get("gameData", {}).get("teams", {})
        away = teams.get("away", {}).get("abbreviation", "AWY")
        home = teams.get("home", {}).get("abbreviation", "HME")
        game_label = f"{away}–{home}"

        output: List[ChallengeEvent] = []
        for play in plays:
            if not self._is_abs_pitch_challenge(play):
                continue

            description = self._challenge_description(play)
            overturned, confirmed = self._infer_review_outcome(play)
            if overturned is None:
                continue

            inning = play.get("about", {}).get("inning")
            half = play.get("about", {}).get("halfInning", "").capitalize()
            inning_label = f"{half} {inning}" if inning else half

            challenger_id, challenger_name, role = self._infer_challenger(play)

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

    def _is_abs_pitch_challenge(self, play: Dict[str, Any]) -> bool:
        text = self._collect_play_text(play).lower()
        if any(k in text for k in EXCLUDED_KEYWORDS):
            return False

        review_type = self._extract_review_type(play).lower()
        has_mj_review_type = review_type in ABS_REVIEW_TYPE_CODES
        if any(t in review_type for t in NON_ABS_REVIEW_TYPES):
            return False

        has_challenge_marker = any(k in text for k in CHALLENGE_KEYWORDS)
        has_abs_context = any(k in text for k in ABS_CONTEXT_KEYWORDS) or any(
            k in review_type for k in ABS_CONTEXT_KEYWORDS
        )
        has_pitch_call = any(k in text for k in PITCH_CALL_KEYWORDS)
        has_pitch_event = any("pitchData" in event for event in play.get("playEvents", []) if isinstance(event, dict))
        final_call = self._infer_final_call(play)
        has_abs_review_metadata = self._has_abs_review_metadata(play)
        has_review_marker = self._has_review_marker(play)
        has_pitch_evidence = has_pitch_call or has_pitch_event or final_call is not None

        if has_mj_review_type:
            return True

        has_challenge_or_review = has_challenge_marker or has_review_marker
        has_abs_signal = has_abs_context or has_abs_review_metadata or has_review_marker
        return has_challenge_or_review and has_abs_signal and has_pitch_evidence
        return has_mj_review_type or (
        return (
            (has_challenge_marker or has_review_marker)
            and (has_abs_context or has_abs_review_metadata or has_review_marker)
            and has_pitch_evidence
        )

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

    def _challenge_description(self, play: Dict[str, Any]) -> str:
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
            if key in play:
                return True

        text = self._collect_play_text(play).lower()
        return "review" in text

    def _has_review_marker(self, play: Dict[str, Any]) -> bool:
        if isinstance(play.get("review"), dict):
            return True

        for key in REVIEW_PRESENCE_KEYS:
            if key in play:
                return True

        text = self._collect_play_text(play).lower()
        return "review" in text

    def _infer_review_outcome(self, play: Dict[str, Any]) -> Tuple[Optional[bool], Optional[bool]]:
        text = self._collect_play_text(play).lower()
        if any(k in text for k in OVERTURNED_KEYWORDS):
            return True, False
        if any(k in text for k in CONFIRMED_KEYWORDS):
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

        # Feed payloads sometimes provide review metadata without explicit
        # "confirmed/overturned" wording. If the play is already identified
        # as an ABS challenge and review data is present, treat it as confirmed.
        if self._has_abs_review_metadata(play):
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

    def _infer_challenger(self, play: Dict[str, Any]) -> Tuple[Optional[int], str, Optional[str]]:
        text = self._collect_play_text(play).lower()
        batter = play.get("matchup", {}).get("batter", {})
        pitcher = play.get("matchup", {}).get("pitcher", {})
        overturned = any(k in text for k in OVERTURNED_KEYWORDS)
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

        if final_call == "ball":
            if overturned:
                return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"
            return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"
        if final_call == "strike":
            if overturned:
                return pitcher.get("id"), pitcher.get("fullName", "Unknown Fielder"), "fielder"
            return batter.get("id"), batter.get("fullName", "Unknown Hitter"), "hitter"

        return None, "Unknown Challenger", None

    def _infer_final_call(self, play: Dict[str, Any]) -> Optional[str]:
        text = self._collect_play_text(play).lower()

        if "called strike" in text or "to strike" in text or "as strike" in text:
            return "strike"
        if "called ball" in text or "to ball" in text or "as ball" in text:
            return "ball"

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

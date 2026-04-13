from datetime import date
import requests

from abs_service import ABSService


class _DummyResponse:
    def __init__(self, text: str):
        self.text = text
        self._json = None

    def raise_for_status(self):
        return None

    def json(self):
        if self._json is None:
            raise ValueError("No JSON payload configured for dummy response")
        return self._json


class _DummySession:
    def __init__(self, text: str, json_payload=None):
        self.text = text
        self.json_payload = json_payload
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        response = _DummyResponse(self.text)
        response._json = self.json_payload
        return response


def test_parse_attempt_total_from_savant_markup():
    svc = ABSService()
    assert svc._parse_attempt_total("<div><span>932 attempts</span></div>") == 932


def test_get_daily_total_uses_selected_date_in_params():
    session = _DummySession(
        """
        {"game_date":"2026-04-10","totalChallenges":"17"}
        <div>Daily Overturn%: 54% (9/17)</div>
        <div>BATTERS Daily Overturn%: 50% (4/8)</div>
        <div>FIELDERS Daily Overturn%: 56% (5/9)</div>
        """
    )
    svc = ABSService(session=session)

    recap = svc.get_daily_total(target_date=date(2026, 4, 10))

    assert recap["total"] == 17
    assert recap["overall_overturn_pct"] == 54
    assert recap["overall_overturns"] == 9
    assert recap["batters_total"] == 8
    assert recap["fielders_total"] == 9
    assert recap["date"] == date(2026, 4, 10)
    savant_call = next(call for call in session.calls if call["params"] and "startDate" in call["params"])
    assert savant_call["params"]["startDate"] == "2026-04-10"
    assert savant_call["params"]["endDate"] == "2026-04-10"
    assert "User-Agent" in savant_call["headers"]


def test_get_season_total_uses_dashboard_and_year():
    session = _DummySession("<div>1,002 attempts</div>")
    svc = ABSService(session=session)

    recap = svc.get_season_total(season=2026)

    assert recap["total"] == 1002
    assert recap["season"] == 2026
    assert session.calls[0]["params"]["year"] == 2026
    assert session.calls[0]["params"]["gameType"] == "regular"


def test_format_daily_discord_message_contains_source_and_total():
    svc = ABSService()
    message = svc.format_daily_discord_message(
        {
            "date": date(2026, 4, 10),
            "total": 22,
            "overall_overturn_pct": 50,
            "overall_overturns": 11,
            "batters_overturn_pct": 45,
            "batters_overturns": 5,
            "batters_total": 11,
            "fielders_overturn_pct": 55,
            "fielders_overturns": 6,
            "fielders_total": 11,
            "source": "Baseball Savant",
        }
    )
    assert "April" in message
    assert "Total Challenges: 22" in message
    assert "Daily Overturn%: 50% (11/22)" in message
    assert "Batters Daily Overturn%: 45% (5/11)" in message
    assert "Fielders Daily Overturn%: 55% (6/11)" in message
    assert "Source: Baseball Savant" in message


def test_format_season_discord_message_contains_source_and_total():
    svc = ABSService()
    message = svc.format_season_discord_message({"season": 2026, "total": 910, "source": "Baseball Savant"})
    assert "ABS Season Summary 2026" in message
    assert "Total Challenges: 910" in message
    assert "Source: Baseball Savant" in message
    message = svc.format_season_discord_message(
        {
            "season": 2026,
            "total": 542,
            "hitter_total": 271,
            "fielder_total": 269,
            "unknown_total": 2,
            "failed_games": 0,
            "games_scanned": 100,
            "hitters": [],
            "fielders": [],
        }
    )

    assert "Total Challenges: 542" in message
    assert "Hitters: 271" in message
    assert "Fielders: 269" in message
    assert "Unclassified: 2" in message


class _DummyResponse:
    def __init__(self, text: str):
        self.text = text
        self._json = None

    def raise_for_status(self):
        return None

    def json(self):
        if self._json is None:
            raise ValueError("No JSON payload configured for dummy response")
        return self._json


class _DummySession:
    def __init__(self, text: str, json_payload=None):
        self.text = text
        self.json_payload = json_payload
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        response = _DummyResponse(self.text)
        response._json = self.json_payload
        return response


def test_parse_attempt_total_from_savant_markup():
    svc = ABSService()
    html = "<div><span>932 attempts</span></div>"
    assert svc._parse_attempt_total(html) == 932


def test_get_savant_daily_total_uses_selected_date_in_params():
    session = _DummySession('{"game_date":"2026-04-10","totalChallenges":"17"}')
    svc = ABSService(session=session)

    recap = svc.get_savant_daily_total(target_date=__import__("datetime").date(2026, 4, 10))

    assert recap["total"] == 17
    savant_call = next(call for call in session.calls if call["params"] and "startDate" in call["params"])
    assert savant_call["params"]["startDate"] == "2026-04-10"
    assert savant_call["params"]["endDate"] == "2026-04-10"


def test_get_savant_season_total_uses_dashboard_and_year():
    session = _DummySession("<div>1,002 attempts</div>")
    svc = ABSService(session=session)

    recap = svc.get_savant_season_total(season=2026)

    assert recap["total"] == 1002
    assert session.calls[0]["params"]["year"] == 2026
    assert session.calls[0]["params"]["gameType"] == "regular"

def test_parse_attempt_total_supports_challenges_wording():
    svc = ABSService()
    assert svc._parse_attempt_total('<div><span>245 challenges</span></div>') == 245


def test_parse_attempt_total_supports_json_total_challenges_key():
    svc = ABSService()
    assert svc._parse_attempt_total('{"totalChallenges": "1,234"}') == 1234


def test_parse_attempt_total_supports_data_attribute_fallback():
    svc = ABSService()
    assert svc._parse_attempt_total('<div data-total-challenges="333"></div>') == 333


def test_parse_attempt_total_prefers_total_over_per_game_value():
    svc = ABSService()
    html = """
    <div>Game A: 8 challenges</div>
    <div>Total Challenges: 143</div>
    """
    assert svc._parse_attempt_total(html) == 143


def test_parse_attempt_total_ignores_non_challenge_total_values():
    svc = ABSService()
    html = '{"season":"2025","total":"2025","totalChallenges":"144"}'
    assert svc._parse_attempt_total(html) == 144


def test_parse_attempt_total_prefers_first_high_priority_daily_total():
    svc = ABSService()
    html = """
    <div>Total Challenges: 59</div>
    <script>window.payload = {"totalChallenges":"144"};</script>
    """
    assert svc._parse_attempt_total(html) == 59


def test_parse_daily_attempt_total_uses_requested_date_match():
    svc = ABSService()
    html = """
    [{"game_date":"2026-04-11","totalChallenges":"44"},
     {"game_date":"2026-04-12","totalChallenges":"59"}]
    """
    assert svc._parse_daily_attempt_total(html, date(2026, 4, 12)) == 59


def test_parse_daily_attempt_total_ignores_per_game_challenge_count_rows():
    svc = ABSService()
    html = """
    {
      "rows": [{"game_date":"2026-04-12","challenge_count":"3"}],
      "totals": [{"game_date":"2026-04-12","totalChallenges":"59"}]
    }
    """
    assert svc._parse_daily_attempt_total(html, date(2026, 4, 12)) == 59


def test_parse_daily_overturn_breakdown_reads_overall_batters_fielders():
    svc = ABSService()
    html = """
    Daily Overturn%: 54% (32/59)
    BATTERS Daily Overturn%: 52% (13/25)
    FIELDERS Daily Overturn%: 56% (19/34)
    7-Day Rolling Overturn%: 53%
    """
    breakdown = svc._parse_daily_overturn_breakdown(html)
    assert breakdown["overall_total"] == 59
    assert breakdown["overall_overturns"] == 32
    assert breakdown["batters_total"] == 25
    assert breakdown["fielders_total"] == 34


class _FallbackSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(url)
        if "leaderboard" in url:
            raise requests.RequestException("leaderboard blocked")
        return _DummyResponse('{"game_date":"2026-04-10","totalChallenges":"44"}')


def test_get_daily_total_falls_back_to_dashboard_when_leaderboard_fails():
    svc = ABSService(session=_FallbackSession())
    recap = svc.get_daily_total(target_date=date(2026, 4, 10))
    assert recap["total"] == 44


def test_count_abs_challenges_in_feed_counts_reviewed_pitch_calls():
    svc = ABSService()
    payload = {
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "atBatIndex": 1,
                        "playEvents": [
                            {
                                "isPitch": True,
                                "pitchNumber": 1,
                                "playId": "a",
                                "details": {
                                    "hasReview": True,
                                    "description": "Called Strike",
                                    "call": {"description": "Called Strike"},
                                },
                            },
                            {
                                "isPitch": True,
                                "pitchNumber": 2,
                                "playId": "b",
                                "details": {
                                    "hasReview": False,
                                    "description": "Ball",
                                    "call": {"description": "Ball"},
                                },
                            },
                        ],
                    }
                ]
            }
        }
    }
    assert svc._count_abs_challenges_in_feed(payload) == 1


def test_get_daily_total_uses_statsapi_total_when_savant_daily_total_missing():
    class _CombinedSession:
        def get(self, url, params=None, headers=None, timeout=None):
            if "statsapi.mlb.com/api/v1/schedule" in url:
                resp = _DummyResponse("")
                resp._json = {"dates": [{"games": [{"gamePk": 1}]}]}
                return resp
            if "statsapi.mlb.com/api/v1.1/game/1/feed/live" in url:
                resp = _DummyResponse("")
                resp._json = {
                    "liveData": {
                        "plays": {
                            "allPlays": [
                                {
                                    "atBatIndex": 1,
                                    "playEvents": [
                                        {
                                            "isPitch": True,
                                            "pitchNumber": 1,
                                            "playId": "a",
                                            "details": {
                                                "hasReview": True,
                                                "description": "Ball",
                                                "call": {"description": "Ball"},
                                            },
                                        },
                                        {
                                            "isPitch": True,
                                            "pitchNumber": 2,
                                            "playId": "b",
                                            "details": {
                                                "hasReview": True,
                                                "description": "Called Strike",
                                                "call": {"description": "Called Strike"},
                                            },
                                        },
                                    ],
                                }
                            ]
                        }
                    }
                }
                return resp
            return _DummyResponse("<html>no daily totals here</html>")

    svc = ABSService(session=_CombinedSession())
    recap = svc.get_daily_total(target_date=date(2026, 4, 10))
    assert recap["total"] == 2

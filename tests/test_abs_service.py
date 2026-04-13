from datetime import date
import requests

from abs_service import ABSService


class _DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class _DummySession:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return _DummyResponse(self.text)


def test_parse_attempt_total_from_savant_markup():
    svc = ABSService()
    assert svc._parse_attempt_total("<div><span>932 attempts</span></div>") == 932


def test_get_daily_total_uses_selected_date_in_params():
    session = _DummySession("<div>17 attempts</div>")
    svc = ABSService(session=session)

    recap = svc.get_daily_total(target_date=date(2026, 4, 10))

    assert recap["total"] == 17
    assert recap["date"] == date(2026, 4, 10)
    assert session.calls[0]["params"]["startDate"] == "2026-04-10"
    assert session.calls[0]["params"]["endDate"] == "2026-04-10"
    assert "User-Agent" in session.calls[0]["headers"]


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
    message = svc.format_daily_discord_message({"date": date(2026, 4, 10), "total": 22, "source": "Baseball Savant"})
    assert "April" in message
    assert "Total Challenges: 22" in message
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

    def raise_for_status(self):
        return None


class _DummySession:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return _DummyResponse(self.text)


def test_parse_attempt_total_from_savant_markup():
    svc = ABSService()
    html = "<div><span>932 attempts</span></div>"
    assert svc._parse_attempt_total(html) == 932


def test_get_savant_daily_total_uses_selected_date_in_params():
    session = _DummySession("<div>17 attempts</div>")
    svc = ABSService(session=session)

    recap = svc.get_savant_daily_total(target_date=__import__("datetime").date(2026, 4, 10))

    assert recap["total"] == 17
    assert session.calls[0]["params"]["startDate"] == "2026-04-10"
    assert session.calls[0]["params"]["endDate"] == "2026-04-10"


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


class _FallbackSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(url)
        if "leaderboard" in url:
            raise requests.RequestException("leaderboard blocked")
        return _DummyResponse("<div>44 attempts</div>")


def test_get_daily_total_falls_back_to_dashboard_when_leaderboard_fails():
    svc = ABSService(session=_FallbackSession())
    recap = svc.get_daily_total(target_date=date(2026, 4, 10))
    assert recap["total"] == 44

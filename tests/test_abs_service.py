from abs_service import ABSService


def _play(description: str, include_pitch=True):
    play_event = {"details": {"description": description}}
    if include_pitch:
        play_event["pitchData"] = {"startSpeed": 95.0}

    return {
        "result": {"description": description},
        "playEvents": [play_event],
        "matchup": {
            "batter": {"id": 1, "fullName": "Batter One"},
            "pitcher": {"id": 2, "fullName": "Pitcher Two"},
        },
        "about": {"inning": 7, "halfInning": "Top", "homeWinProbabilityAdded": 0.123},
    }


def test_excludes_hbp_challenges():
    svc = ABSService()
    play = _play("ABS challenge confirmed called strike after hit by pitch discussion")
    assert svc._is_abs_pitch_challenge(play) is False


def test_detects_pitch_challenge_with_mj_review_type():
    svc = ABSService()
    play = _play("ABS challenge overturned to ball")
    play["reviewDetails"] = {"reviewType": "MJ", "inProgress": False, "isOverturned": True}
    assert svc._is_abs_pitch_challenge(play) is True


def test_requires_mj_review_type_not_just_text():
    svc = ABSService()
    play = _play("ABS challenge confirmed called strike", include_pitch=False)
    assert svc._is_abs_pitch_challenge(play) is False


def test_excludes_non_abs_review_types():
    svc = ABSService()
    play = _play("Manager challenge confirmed called strike")
    play["review"] = {"reviewType": "Manager Challenge"}
    assert svc._is_abs_pitch_challenge(play) is False


def test_non_mj_review_types_do_not_count_as_abs_challenges():
    svc = ABSService()
    play = _play("Challenge confirmed called strike")
    play["review"] = {"reviewType": "Ball/Strike Review", "isOverturned": False}
    assert svc._is_abs_pitch_challenge(play) is False


def test_excludes_mj_review_while_in_progress():
    svc = ABSService()
    play = _play("Challenge in progress", include_pitch=True)
    play["reviewDetails"] = {"reviewType": "MJ", "inProgress": True}
    assert svc._is_abs_pitch_challenge(play) is False


def test_detects_mj_reviewtype_without_abs_text_or_pitchdata():
    svc = ABSService()
    play = _play("Review in progress", include_pitch=False)
    play["reviewDetails"] = {"reviewType": "MJ", "inProgress": False, "isOverturned": True}
    assert svc._is_abs_pitch_challenge(play) is True


def test_detects_public_abs_wording_without_review_nodes():
    svc = ABSService()
    play = _play("Strike 1 call overturned after ABS challenge", include_pitch=False)
    play.pop("playEvents")
    play["playEvents"] = [{"details": {"description": "Strike 1 call overturned after ABS challenge"}}]
    assert svc._is_abs_pitch_challenge(play) is True


def test_detects_generic_abs_result_wording():
    svc = ABSService()
    play = _play("ABS Challenge - Successful, call overturned", include_pitch=False)
    assert svc._is_abs_pitch_challenge(play) is True
    assert svc._infer_review_outcome(play) == (True, False)


def test_detects_abs_result_wording_when_call_stands():
    svc = ABSService()
    play = _play("ABS challenge complete, call stands", include_pitch=False)
    assert svc._is_abs_pitch_challenge(play) is True
    assert svc._infer_review_outcome(play) == (False, True)


def test_excludes_generic_non_pitch_reviews():
    svc = ABSService()
    play = _play("Safe/out challenge at first base", include_pitch=False)
    play["review"] = {"reviewType": "Replay Review"}
    assert svc._is_abs_pitch_challenge(play) is False


def test_excludes_generic_pitch_review_without_abs_signal():
    svc = ABSService()
    play = _play("Challenge on called strike, call stands", include_pitch=True)
    play["review"] = {"decision": "call stands"}
    assert svc._is_abs_pitch_challenge(play) is False


def test_empty_review_keys_do_not_count_as_review_marker():
    svc = ABSService()
    play = _play("Called strike in the strike zone", include_pitch=True)
    play["reviews"] = []
    play["challenge"] = False
    assert svc._is_abs_pitch_challenge(play) is False


def test_role_split_hitter_vs_fielder():
    svc = ABSService()

    hitter_play = _play("ABS challenge overturned to ball")
    _, hitter_name, hitter_role = svc._infer_challenger(hitter_play)
    assert hitter_name == "Batter One"
    assert hitter_role == "hitter"

    fielder_play = _play("ABS challenge overturned to strike")
    _, fielder_name, fielder_role = svc._infer_challenger(fielder_play)
    assert fielder_name == "Pitcher Two"
    assert fielder_role == "fielder"


def test_role_inference_from_final_call_and_overturn_status():
    svc = ABSService()

    confirmed_strike = _play("ABS challenge confirmed called strike")
    _, _, role_confirmed_strike = svc._infer_challenger(confirmed_strike)
    assert role_confirmed_strike == "hitter"

    confirmed_ball = _play("ABS challenge confirmed called ball")
    _, _, role_confirmed_ball = svc._infer_challenger(confirmed_ball)
    assert role_confirmed_ball == "fielder"

    overturned_to_strike = _play("ABS challenge overturned called ball to strike")
    _, _, role_overturned_to_strike = svc._infer_challenger(overturned_to_strike)
    assert role_overturned_to_strike == "fielder"

    overturned_to_ball = _play("ABS challenge overturned called strike to ball")
    _, _, role_overturned_to_ball = svc._infer_challenger(overturned_to_ball)
    assert role_overturned_to_ball == "hitter"


def test_role_inference_from_public_abs_phrase():
    svc = ABSService()

    strike_overturned = _play("Strike 1 call overturned after ABS challenge", include_pitch=False)
    _, _, strike_overturned_role = svc._infer_challenger(strike_overturned)
    assert strike_overturned_role == "hitter"

    ball_overturned = _play("Ball 3 call overturned after ABS challenge", include_pitch=False)
    _, _, ball_overturned_role = svc._infer_challenger(ball_overturned)
    assert ball_overturned_role == "fielder"

    strike_confirmed = _play("Strike 3 call confirmed after ABS challenge", include_pitch=False)
    _, _, strike_confirmed_role = svc._infer_challenger(strike_confirmed)
    assert strike_confirmed_role == "hitter"

    strike_stands = _play("Strike 2 call stands after ABS challenge", include_pitch=False)
    _, _, strike_stands_role = svc._infer_challenger(strike_stands)
    assert strike_stands_role == "hitter"


def test_parse_game_events_skips_challenges_without_outcome():
    svc = ABSService()
    feed = {
        "liveData": {"plays": {"allPlays": [_play("ABS challenge on called strike")]}},
        "gameData": {"teams": {"away": {"abbreviation": "A"}, "home": {"abbreviation": "H"}}},
    }
    events = svc._parse_game_events(feed, game_pk=123)
    assert events == []


def test_parse_game_events_emits_single_abs_event_for_play_level_review():
    svc = ABSService()
    play = {
        "about": {"inning": 5, "halfInning": "Top", "atBatIndex": 33, "isTopInning": True},
        "matchup": {
            "batter": {"id": 1, "fullName": "Batter One"},
            "pitcher": {"id": 2, "fullName": "Pitcher Two"},
        },
        "result": {"description": "ABS challenge complete, call stands"},
        "reviewDetails": {"reviewType": "MJ", "inProgress": False, "isOverturned": False},
        "playEvents": [
            {"isPitch": True, "playId": "p1", "details": {"call": {"code": "B"}, "description": "Ball"}},
            {"isPitch": True, "playId": "p2", "details": {"call": {"code": "C"}, "description": "Called Strike"}},
            {"isPitch": False, "playId": "rv1", "details": {"eventType": "pitch_challenge", "description": "Pitch Challenge"}},
        ],
    }
    feed = {
        "liveData": {"plays": {"allPlays": [play]}},
        "gameData": {"teams": {"away": {"abbreviation": "A"}, "home": {"abbreviation": "H"}}},
    }

    events = svc._parse_game_events(feed, game_pk=123)
    assert len(events) == 1


def test_parse_game_events_deduplicates_same_reviewed_pitch():
    svc = ABSService()
    play = {
        "about": {"inning": 5, "halfInning": "Top", "atBatIndex": 33, "isTopInning": True},
        "matchup": {
            "batter": {"id": 1, "fullName": "Batter One"},
            "pitcher": {"id": 2, "fullName": "Pitcher Two"},
        },
        "result": {"description": "ABS challenge complete, call overturned"},
        "reviewDetails": {"reviewType": "MJ", "inProgress": False, "isOverturned": True},
        "playEvents": [
            {"isPitch": True, "playId": "same-pitch", "details": {"call": {"code": "C"}}},
            {"isPitch": False, "playId": "challenge-a", "details": {"eventType": "pitch_challenge", "description": "Pitch Challenge"}},
            {"isPitch": False, "playId": "challenge-b", "details": {"eventType": "pitch_challenge", "description": "Pitch Challenge"}},
        ],
    }
    feed = {
        "liveData": {"plays": {"allPlays": [play, play]}},
        "gameData": {"teams": {"away": {"abbreviation": "A"}, "home": {"abbreviation": "H"}}},
    }

    events = svc._parse_game_events(feed, game_pk=123)
    assert len(events) == 1


def test_parse_game_events_counts_multiple_challenges_in_same_at_bat():
    """Two different pitches challenged in the same at-bat must both be counted."""
    svc = ABSService()
    play = {
        "about": {"inning": 3, "halfInning": "Bottom", "atBatIndex": 12, "isTopInning": False},
        "matchup": {
            "batter": {"id": 10, "fullName": "Hitter A"},
            "pitcher": {"id": 20, "fullName": "Pitcher B"},
        },
        "result": {"description": "At bat complete"},
        # Play-level reviewDetails reflects only one review; the other is event-level only.
        "reviewDetails": {"reviewType": "MJ", "inProgress": False, "isOverturned": True},
        "playEvents": [
            # pitch 1: called strike, challenged by batter → overturned (ball)
            {"isPitch": True, "playId": "pitch-1", "details": {"call": {"code": "C"}, "description": "Called Strike"}},
            {
                "isPitch": False,
                "playId": "challenge-1",
                "details": {"eventType": "pitch_challenge", "description": "Pitch Challenge"},
                "reviewDetails": {"reviewType": "MJ", "inProgress": False, "isOverturned": True},
            },
            # pitch 2: regular pitch after overturned call
            {"isPitch": True, "playId": "pitch-2", "details": {"call": {"code": "B"}, "description": "Ball"}},
            # pitch 3: called ball, challenged by fielder → confirmed
            {"isPitch": True, "playId": "pitch-3", "details": {"call": {"code": "B"}, "description": "Ball"}},
            {
                "isPitch": False,
                "playId": "challenge-2",
                "details": {"eventType": "pitch_challenge", "description": "Pitch Challenge"},
                "reviewDetails": {"reviewType": "MJ", "inProgress": False, "isOverturned": False},
            },
        ],
    }
    feed = {
        "liveData": {"plays": {"allPlays": [play]}},
        "gameData": {"teams": {"away": {"abbreviation": "A"}, "home": {"abbreviation": "H"}}},
    }

    events = svc._parse_game_events(feed, game_pk=999)
    assert len(events) == 2, f"Expected 2 challenges, got {len(events)}"
    overturned_flags = {e.overturned for e in events}
    assert True in overturned_flags, "Expected one overturned challenge"
    assert False in overturned_flags, "Expected one confirmed challenge"


def test_missing_outcome_returns_unknown():
    svc = ABSService()
    play = _play("Challenge", include_pitch=True)
    play["reviewDetails"] = {"reviewType": "MJ", "inProgress": False}
    assert svc._infer_review_outcome(play) == (None, None)


def test_infers_outcome_from_playevent_reviewdetails():
    svc = ABSService()
    play = _play("Challenge under review", include_pitch=True)
    play["playEvents"][0]["reviewDetails"] = {"reviewType": "MJ", "isOverturned": True}
    assert svc._infer_review_outcome(play) == (True, False)


def test_season_starts_on_march_25():
    svc = ABSService()
    start, end = {}, {}

    def fake_fetch(start_date, end_date):
        start["value"] = start_date
        end["value"] = end_date
        return []

    svc._fetch_schedule_date_range = fake_fetch
    svc._collect_events_from_games = lambda games, **kwargs: ([], 0)
    svc.get_season_leaderboard(season=2026, run_date=__import__("datetime").date(2026, 4, 6))
    assert start["value"] == __import__("datetime").date(2026, 3, 25)
    assert end["value"] == __import__("datetime").date(2026, 4, 5)


def test_build_player_rows_keeps_roles_separate():
    svc = ABSService()

    class E:
        def __init__(self, role, overturned):
            self.role = role
            self.challenger_id = 7
            self.challenger_name = "Two-Way Player"
            self.overturned = overturned

    events = [E("hitter", True), E("hitter", False), E("fielder", True)]

    hitters = svc._build_player_rows(events, role="hitter", top_n=3)
    fielders = svc._build_player_rows(events, role="fielder", top_n=3)

    assert hitters[0]["total"] == 2
    assert fielders[0]["total"] == 1


def test_daily_recap_filters_by_official_date_not_et_start():
    """Daily recap must use officialDate, not ET start time.

    A West Coast game starting at 10:05 PM PT on Apr 6 has:
      officialDate = "2026-04-06"   (local Pacific date — correct schedule day)
      gameDate     = "2026-04-07T05:05:00Z"  (UTC, past midnight ET → Apr 7 ET)

    The old code used ET start time, so it wrongly dropped this game from the
    Apr 6 recap and assigned it to Apr 7.  The fix is target_uses_start_date=False
    so _game_official_date is used instead.
    """
    svc = ABSService()
    captured = {}

    games = [
        # Normal evening East Coast game — officialDate and ET start both Apr 6
        {"gamePk": 1, "officialDate": "2026-04-06", "gameDate": "2026-04-06T23:10:00Z"},
        # Late West Coast game: officialDate Apr 6 (Pacific), but ET start = Apr 7 01:05
        # Old code would DROP this; new code must INCLUDE it via officialDate.
        {"gamePk": 2, "officialDate": "2026-04-06", "gameDate": "2026-04-07T05:05:00Z"},
        # Game whose officialDate is Apr 7 — must be excluded from Apr 6 recap
        {"gamePk": 3, "officialDate": "2026-04-07", "gameDate": "2026-04-07T18:05:00Z"},
    ]

    svc._fetch_schedule_for_date = lambda _target: games

    def fake_collect(found_games, **kwargs):
        captured["target"] = kwargs.get("target_date")
        captured["target_uses_start_date"] = kwargs.get("target_uses_start_date")
        # Simulate what _collect_events_from_games does with officialDate filtering
        captured["games"] = [
            g["gamePk"]
            for g in found_games
            if svc._game_official_date(g) == kwargs.get("target_date")
        ]
        return [], 0

    svc._collect_events_from_games = fake_collect
    svc.get_daily_recap(run_date=__import__("datetime").date(2026, 4, 7))

    assert captured["target"] == __import__("datetime").date(2026, 4, 6)
    assert captured["target_uses_start_date"] is False, (
        "Daily recap must use officialDate (target_uses_start_date=False) "
        "so late West Coast games are not dropped"
    )
    assert captured["games"] == [1, 2], (
        "Game 2 (late West Coast start) must be included via officialDate; "
        "Game 3 (officialDate Apr 7) must be excluded"
    )


def test_collect_events_filters_to_season_date_window_by_official_date():
    svc = ABSService()
    scanned = []

    games = [
        {"gamePk": 10, "officialDate": "2026-03-25", "gameDate": "2026-03-25T17:05:00Z"},
        {"gamePk": 11, "officialDate": "2026-03-24", "gameDate": "2026-03-25T03:55:00Z"},  # outside start window
        {"gamePk": 12, "officialDate": "2026-04-06", "gameDate": "2026-04-07T03:59:00Z"},
        {"gamePk": 13, "officialDate": "2026-04-07", "gameDate": "2026-04-07T01:01:00Z"},  # outside end window
    ]

    svc._fetch_game_feed = lambda game_pk: scanned.append(game_pk) or {
        "liveData": {"plays": {"allPlays": []}},
        "gameData": {"teams": {"away": {"abbreviation": "A"}, "home": {"abbreviation": "H"}}},
    }
    svc._parse_game_events = lambda _feed, _pk: []

    svc._collect_events_from_games(
        games,
        start_date=__import__("datetime").date(2026, 3, 25),
        end_date=__import__("datetime").date(2026, 4, 6),
    )

    assert scanned == [10, 12]


def test_game_official_date_falls_back_to_eastern_start_date():
    svc = ABSService()
    game = {"gameDate": "2026-04-07T01:10:00Z"}
    assert svc._game_official_date(game) == __import__("datetime").date(2026, 4, 6)


def test_daily_message_has_role_breakout_and_no_key_moments():
    svc = ABSService()
    message = svc.format_daily_discord_message(
        {
            "date": __import__("datetime").date(2026, 4, 5),
            "total": 72,
        }
    )

    assert "ABS Daily Recap ⚾️" in message
    assert "April 5, 2026" in message
    assert "Total Challenges: 72" in message
    assert "Hitters:" not in message
    assert "Overturned:" not in message


def test_season_message_shows_totals_even_without_leader_rows():
    svc = ABSService()
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

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
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

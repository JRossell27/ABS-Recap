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


def test_parse_game_events_skips_challenges_without_outcome():
    svc = ABSService()
    feed = {
        "liveData": {"plays": {"allPlays": [_play("ABS challenge on called strike")]}},
        "gameData": {"teams": {"away": {"abbreviation": "A"}, "home": {"abbreviation": "H"}}},
    }
    events = svc._parse_game_events(feed, game_pk=123)
    assert events == []


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


def test_daily_recap_only_uses_games_starting_on_target_eastern_date():
    svc = ABSService()
    captured = {}

    games = [
        {"gamePk": 1, "gameDate": "2026-04-06T23:10:00Z"},  # Apr 6 ET
        {"gamePk": 2, "gameDate": "2026-04-07T01:10:00Z"},  # Apr 6 ET
        {"gamePk": 3, "gameDate": "2026-04-07T05:10:00Z"},  # Apr 7 ET (exclude)
    ]

    svc._fetch_schedule_for_date = lambda _target: games

    def fake_collect(found_games, **kwargs):
        captured["games"] = [g["gamePk"] for g in found_games if svc._game_start_date_eastern(g) == kwargs.get("target_date")]
        captured["target"] = kwargs.get("target_date")
        return [], 0

    svc._collect_events_from_games = fake_collect
    svc.get_daily_recap(run_date=__import__("datetime").date(2026, 4, 7))

    assert captured["target"] == __import__("datetime").date(2026, 4, 6)
    assert captured["games"] == [1, 2]


def test_collect_events_filters_to_season_date_window_by_eastern_start():
    svc = ABSService()
    scanned = []

    games = [
        {"gamePk": 10, "gameDate": "2026-03-25T17:05:00Z"},
        {"gamePk": 11, "gameDate": "2026-03-24T23:55:00Z"},  # outside start window
        {"gamePk": 12, "gameDate": "2026-04-07T03:59:00Z"},  # Apr 6 ET
        {"gamePk": 13, "gameDate": "2026-04-07T04:01:00Z"},  # Apr 7 ET outside end window
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


def test_daily_message_has_role_breakout_and_no_key_moments():
    svc = ABSService()
    message = svc.format_daily_discord_message(
        {
            "date": __import__("datetime").date(2026, 4, 5),
            "total": 72,
            "hitter_total": 31,
            "fielder_total": 41,
            "overturned": 20,
            "confirmed": 52,
            "success_rate": 27.8,
        }
    )

    assert "ABS Daily Recap ⚾️" in message
    assert "April 5, 2026" in message
    assert "72 Challenges" in message
    assert "Hitters: 31 | Fielders: 41" in message
    assert "Biggest Moments" not in message


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

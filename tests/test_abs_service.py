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


def test_detects_pitch_challenge():
    svc = ABSService()
    play = _play("ABS challenge overturned to ball")
    assert svc._is_abs_pitch_challenge(play) is True


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

from ai.analyzer import _format_form, _format_h2h
from api.models import FixtureEvent, MatchResult, Team

MEX = Team(id=16, name="Mexico")
RSA = Team(id=1531, name="South Africa")


def _match(fid, home, away, hg, ag, date="2026-06-11T19:00:00+00:00"):
    return MatchResult(
        fixture_id=fid, date=date, league="World Cup", round="Group A",
        home_team=home, away_team=away, home_goals=hg, away_goals=ag, status="FT",
    )


def test_h2h_record_tally():
    matches = [
        _match(1, MEX, RSA, 2, 0),   # Mexico win at home
        _match(2, RSA, MEX, 0, 1),   # Mexico win away
        _match(3, RSA, MEX, 2, 2),   # draw
        _match(4, RSA, MEX, 3, 1),   # South Africa win
    ]
    out = _format_h2h(MEX, RSA, matches)
    assert "Mexico 2W / 1D / 1W South Africa" in out


def test_h2h_empty():
    assert "No historical data" in _format_h2h(MEX, RSA, [])


def test_form_includes_scorers_and_excludes_own_goals():
    m = _match(10, MEX, RSA, 2, 1)
    events = {
        10: [
            FixtureEvent(minute=12, extra_minute=None, team=MEX, player="Jimenez",
                         assist=None, type="Goal", detail="Normal Goal", comments=None),
            FixtureEvent(minute=55, extra_minute=None, team=MEX, player="Alvarez",
                         assist=None, type="Goal", detail="Penalty", comments=None),
            FixtureEvent(minute=80, extra_minute=None, team=RSA, player="Defender",
                         assist=None, type="Goal", detail="Own Goal", comments=None),
            FixtureEvent(minute=88, extra_minute=None, team=RSA, player="Foster",
                         assist=None, type="Card", detail="Red Card", comments=None),
        ]
    }
    out = _format_form(MEX, [m], events)
    assert "Jimenez 12'" in out
    assert "Alvarez 55' pen" in out
    assert "Defender" not in out  # own goals filtered from scorer lists
    assert "Red cards: South Africa: Foster 88'" in out


def test_form_no_matches():
    assert "No recent match data" in _format_form(MEX, [])

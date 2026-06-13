import pytest

from api.models import BookmakerOdds, MatchResult, Team, TeamStats
from model import LINES, _market_probs, forecast_match, prob_for_bet

HOME = Team(id=1, name="Home")
AWAY = Team(id=2, name="Away")


def played(home, away, hg, ag):
    return MatchResult(
        fixture_id=0, date="2026-01-01T00:00:00+00:00", league="Friendlies", round="",
        home_team=home, away_team=away, home_goals=hg, away_goals=ag, status="FT",
    )


def team_stats(team, gf, ga, played_n=4):
    return TeamStats(
        team=team, form="WWWW", played=played_n, wins=played_n, draws=0, losses=0,
        goals_for_avg=str(gf), goals_against_avg=str(ga), clean_sheets=0,
        biggest_win=None, biggest_loss=None, win_streak=0, preferred_formation=None,
    )


def test_probabilities_normalize():
    f = forecast_match(HOME, AWAY, [], [], None, None, [])
    assert f.p_home + f.p_draw + f.p_away == pytest.approx(1.0, abs=1e-6)
    assert 0 < f.p_home < 1 and 0 < f.p_draw < 1 and 0 < f.p_away < 1


def test_home_advantage_with_no_data():
    # With no data both teams sit at the league average; home edge should tilt it.
    f = forecast_match(HOME, AWAY, [], [], None, None, [])
    assert f.p_home > f.p_away
    assert f.exp_goals_home > f.exp_goals_away


def test_stronger_attacker_favoured():
    strong = team_stats(HOME, gf=3.0, ga=0.5)
    weak = team_stats(AWAY, gf=0.5, ga=3.0)
    f = forecast_match(HOME, AWAY, [], [], strong, weak, [])
    assert f.p_home > 0.6
    assert f.exp_goals_home > f.exp_goals_away
    assert f.basis.startswith("home:")


def test_over_probs_monotonic():
    f = forecast_match(HOME, AWAY, [], [], team_stats(HOME, 2, 1), team_stats(AWAY, 2, 1), [])
    probs = [f.over_probs[line] for line in sorted(LINES)]
    assert probs == sorted(probs, reverse=True)  # higher line -> lower P(over)
    assert all(0 <= p <= 1 for p in probs)


def test_fair_odds_are_reciprocals():
    f = forecast_match(HOME, AWAY, [], [], team_stats(HOME, 2, 1), team_stats(AWAY, 1, 2), [])
    odds = f.fair_odds()
    assert odds["home"] == pytest.approx(round(1 / f.p_home, 2))
    assert odds["under_2.5"] == pytest.approx(round(1 / (1 - f.over_probs[2.5]), 2))


def test_form_blended_when_no_stats():
    home_form = [played(HOME, AWAY, 4, 0), played(HOME, AWAY, 3, 0)]
    away_form = [played(AWAY, HOME, 0, 3), played(AWAY, HOME, 0, 2)]
    f = forecast_match(HOME, AWAY, home_form, away_form, None, None, [])
    assert "form" in f.basis
    assert f.p_home > f.p_away


def test_prob_for_bet_markets():
    f = forecast_match(HOME, AWAY, [], [], team_stats(HOME, 2, 1), team_stats(AWAY, 1, 2), [])

    # Over and under of the same line are complementary.
    over = prob_for_bet(f, "Over 2.5 goals", "Home", "Away")
    under = prob_for_bet(f, "Under 2.5 goals", "Home", "Away")
    assert over + under == pytest.approx(1.0, abs=1e-6)

    # BTTS yes/no complementary.
    yes = prob_for_bet(f, "Both teams to score: Yes", "Home", "Away")
    no = prob_for_bet(f, "BTTS no", "Home", "Away")
    assert yes + no == pytest.approx(1.0, abs=1e-6)

    # Moneyline maps to the 1X2 probability.
    assert prob_for_bet(f, "Home to win", "Home", "Away") == pytest.approx(f.p_home)
    assert prob_for_bet(f, "Draw", "Home", "Away") == pytest.approx(f.p_draw)

    # Double chance is win-or-draw.
    dc = prob_for_bet(f, "Home or draw (double chance)", "Home", "Away")
    assert dc == pytest.approx(f.p_home + f.p_draw)

    # Unknown market -> None.
    assert prob_for_bet(f, "First goalscorer: Smith", "Home", "Away") is None
    assert prob_for_bet(f, None, "Home", "Away") is None


def test_handicap_prob_between_zero_and_one():
    f = forecast_match(HOME, AWAY, [], [], team_stats(HOME, 2.5, 0.8), team_stats(AWAY, 0.8, 2.5), [])
    p = prob_for_bet(f, "Home -1 Asian handicap", "Home", "Away")
    assert p is not None and 0 < p < 1
    # Winning by 2+ is less likely than winning by 1+ (plain moneyline).
    assert p < f.p_home


def test_market_probs_devig():
    # 2.0 / 3.5 / 4.0 has an overround; de-vigged probs must sum to 1.
    probs = _market_probs([BookmakerOdds("Book", "2.0", "3.5", "4.0")])
    assert probs is not None
    assert sum(probs) == pytest.approx(1.0)
    assert probs[0] > probs[2]  # shorter price -> higher probability

    # Unusable odds -> None.
    assert _market_probs([BookmakerOdds("Book", "?", "?", "?")]) is None
    assert _market_probs([]) is None


def test_blowout_cap_limits_minnow_inflation():
    minnow = Team(id=10, name="Minnow")
    weak = Team(id=11, name="Weak")
    # Five 7-0 thrashings would imply attack 7.0/game without a cap.
    form = [
        MatchResult(0, "2026-01-01T00:00:00+00:00", "Quali", "", minnow, weak, 7, 0, "FT")
        for _ in range(5)
    ]
    f = forecast_match(minnow, weak, form, [], None, None, [])
    # Capped + shrunk toward the league mean, the home xG must stay well below 7.
    assert f.exp_goals_home < 5.0


def test_market_anchor_overrides_misleading_form():
    # Away side looks elite on (schedule-blind) form, so the raw model favours it.
    fav = Team(id=20, name="Fav")
    pretender = Team(id=21, name="Pretender")
    fav_form = [MatchResult(0, "2026-01-01T00:00:00+00:00", "L", "", fav, pretender, 2, 1, "FT")]
    pretender_form = [
        MatchResult(0, "2026-01-01T00:00:00+00:00", "L", "", pretender, fav, 5, 0, "FT"),
        MatchResult(0, "2026-01-01T00:00:00+00:00", "L", "", pretender, fav, 4, 0, "FT"),
    ]
    raw = forecast_match(fav, pretender, fav_form, pretender_form, None, None, [])
    assert raw.p_away > raw.p_home  # form alone makes the pretender favourite
    assert raw.anchored is False

    # The market strongly favours the home side; anchoring must flip it back.
    odds = [BookmakerOdds("Book", "1.40", "4.50", "8.00")]
    anchored = forecast_match(fav, pretender, fav_form, pretender_form, None, None, [], odds=odds)
    assert anchored.anchored is True
    assert anchored.p_home > anchored.p_away
    assert "market-anchored" in anchored.basis


def test_h2h_nudges_estimate():
    base = forecast_match(HOME, AWAY, [], [], team_stats(HOME, 1.5, 1.5), team_stats(AWAY, 1.5, 1.5), [])
    h2h = [played(HOME, AWAY, 4, 0), played(HOME, AWAY, 3, 0)]
    nudged = forecast_match(HOME, AWAY, [], [], team_stats(HOME, 1.5, 1.5), team_stats(AWAY, 1.5, 1.5), h2h)
    assert nudged.exp_goals_home > base.exp_goals_home
    assert "h2h" in nudged.basis

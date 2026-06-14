import pytest

import ledger
from api.models import Team, WCFixture
from ledger import (
    best_value_bet,
    brier_score,
    extract_best_bet,
    grade_bet,
    kelly_fraction,
    load_predictions,
    price_bet,
    record_prediction,
    suggest_stake,
    value_board,
)

MARKETS = {
    "Match Winner": {"Home": 1.65, "Draw": 3.80, "Away": 5.50},
    "Goals Over/Under": {"Over 2.5": 2.10, "Under 2.5": 1.78},
    "Both Teams Score": {"Yes": 1.95, "No": 1.85},
    "Asian Handicap": {"Home -1": 2.45, "Away +1": 1.55},
    "Double Chance": {"Home/Draw": 1.22, "Draw/Away": 2.30},
    "Draw No Bet": {"Home": 1.30, "Away": 3.40},
}


@pytest.mark.parametrize(
    "bet,expected",
    [
        ("Under 2.5 goals", 1.78),
        ("Over 2.5 goals", 2.10),
        ("Both teams to score: No", 1.85),
        ("BTTS yes", 1.95),
        ("Mexico to win", 1.65),
        ("South Africa moneyline", 5.50),
        ("Mexico -1 Asian handicap", 2.45),
        ("South Africa +1", 1.55),
        ("Mexico or draw (double chance)", 1.22),
        ("Mexico draw no bet", 1.30),
        ("Draw", 3.80),
        ("Over 3.5 goals", None),       # line not offered
        ("First goalscorer: Jimenez", None),  # unrecognized market
        (None, None),
    ],
)
def test_price_bet(bet, expected):
    assert price_bet(MARKETS, bet, "Mexico", "South Africa") == expected


def test_price_bet_no_markets():
    assert price_bet({}, "Under 2.5 goals", "Mexico", "South Africa") is None


def test_price_bet_rejects_degenerate_odds():
    # An exotic line the feed lists at 1.0 (no real payout) must not be priced.
    junk = {"Asian Handicap": {"Home -1.5": 1.0}}
    assert price_bet(junk, "Mexico -1.5 Asian handicap", "Mexico", "South Africa") is None


def test_extract_best_bet_with_confidence():
    text = (
        "## Prediction\n"
        "Mexico should control the game.\n\n"
        "**Best Bet:** Under 2.5 goals\n"
        "Confidence: 7/10. Both sides are defensively sound.\n"
    )
    bet, conf = extract_best_bet(text)
    assert bet == "Under 2.5 goals"
    assert conf == "7"


def test_extract_best_bet_missing():
    assert extract_best_bet("No structured prediction here.") == (None, None)


@pytest.mark.parametrize(
    "bet,hg,ag,expected",
    [
        ("Under 2.5 goals", 1, 1, True),
        ("Under 2.5 goals", 2, 1, False),
        ("Over 1.5 goals", 2, 1, True),
        ("Over 2 goals", 1, 1, None),  # push on the whole-number line
        ("Both teams to score: Yes", 1, 1, True),
        ("Both teams to score: No", 1, 0, True),
        ("BTTS yes", 2, 0, False),
        ("Mexico to win", 2, 0, True),
        ("Mexico to win", 1, 1, False),
        ("South Africa moneyline", 0, 1, True),
        ("Mexico -1 Asian handicap", 2, 0, True),
        ("Mexico -1 Asian handicap", 1, 0, None),  # push
        ("Mexico -1.5", 1, 0, False),
        ("South Africa +1.5", 0, 1, True),
        ("Mexico or draw (double chance)", 1, 1, True),
        ("Mexico draw no bet", 1, 1, None),  # push
        ("Draw", 1, 1, True),
        ("Draw", 2, 1, False),
        ("First goal before 30 minutes", 2, 1, None),  # unrecognized market
        (None, 2, 1, None),
        ("Mexico to win", None, None, None),  # unplayed
    ],
)
def test_grade_bet(bet, hg, ag, expected):
    assert grade_bet(bet, "Mexico", "South Africa", hg, ag) is expected


def test_record_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "results" / "predictions.jsonl")
    fixture = WCFixture(
        fixture_id=42, date="2026-06-11T19:00:00+00:00", round="Group A", venue="Azteca",
        home_team=Team(id=16, name="Mexico"), away_team=Team(id=1531, name="South Africa"),
        status="NS",
    )
    analysis = "## Prediction\n**Best Bet:** Mexico -1 Asian handicap\nConfidence: 6/10."
    record_prediction(
        Team(id=16, name="Mexico"), Team(id=1531, name="South Africa"),
        fixture, analysis, "test-model",
        odds_markets=MARKETS,
    )

    preds = load_predictions()
    assert len(preds) == 1
    entry = preds[0]
    assert entry["fixture_id"] == 42
    assert entry["best_bet"] == "Mexico -1 Asian handicap"
    assert entry["confidence"] == "6"
    assert entry["home"] == "Mexico"
    assert entry["odds"] == 2.45
    assert entry["model_prob"] is None  # no forecast supplied
    assert "report" not in entry


def test_load_predictions_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
    assert load_predictions() == []


@pytest.mark.parametrize(
    "prob,odds,expected",
    [
        (0.60, 2.0, 0.20),     # edge present: f* = (0.6*1 - 0.4)/1 = 0.2
        (0.50, 2.0, 0.0),      # fair odds, no edge
        (0.40, 2.0, 0.0),      # negative edge clamps to 0
        (None, 2.0, 0.0),      # missing model prob
        (0.60, None, 0.0),     # missing odds
        (0.60, 1.0, 0.0),      # degenerate odds
    ],
)
def test_kelly_fraction(prob, odds, expected):
    assert kelly_fraction(prob, odds) == pytest.approx(expected)


def test_brier_score():
    # Confident and correct both times -> near 0.
    assert brier_score([(0.9, True), (0.1, False)]) == pytest.approx((0.01 + 0.01) / 2)
    # Confident and wrong -> near 1.
    assert brier_score([(0.0, True)]) == pytest.approx(1.0)
    # None probs are skipped; all-None -> None.
    assert brier_score([(None, True), (None, False)]) is None
    assert brier_score([]) is None


def test_record_prediction_with_forecast(tmp_path, monkeypatch):
    from model import forecast_match
    from api.models import MatchResult

    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "results" / "predictions.jsonl")
    home = Team(id=16, name="Mexico")
    away = Team(id=1531, name="South Africa")

    def played(h, a, hg, ag):
        return MatchResult(
            fixture_id=1, date="2026-01-01T00:00:00+00:00", league="Friendlies", round="",
            home_team=h, away_team=a, home_goals=hg, away_goals=ag, status="FT",
        )

    home_form = [played(home, away, 3, 0), played(home, away, 2, 1)]
    away_form = [played(away, home, 0, 2), played(away, home, 1, 1)]
    forecast = forecast_match(home, away, home_form, away_form, None, None, [])

    analysis = "## Prediction\n**Best Bet:** Mexico to win\nConfidence: 7/10."
    record_prediction(home, away, None, analysis, "test-model", forecast=forecast)

    entry = load_predictions()[0]
    assert entry["model_prob"] is not None
    assert 0.0 < entry["model_prob"] <= 1.0
    # Edge and a (possibly zero) EUR stake are recorded alongside.
    assert "edge" in entry and "stake_eur" in entry


def _toy_forecast():
    from model import forecast_match
    from api.models import TeamStats
    home, away = Team(id=1, name="Alpha"), Team(id=2, name="Beta")
    ts = lambda t, gf, ga: TeamStats(
        team=t, form="WWWW", played=4, wins=4, draws=0, losses=0,
        goals_for_avg=str(gf), goals_against_avg=str(ga), clean_sheets=0,
        biggest_win=None, biggest_loss=None, win_streak=0, preferred_formation=None,
    )
    return forecast_match(home, away, [], [], ts(home, 2.2, 0.8), ts(away, 0.8, 2.2), [])


def test_value_board_is_sorted_and_priced():
    f = _toy_forecast()
    markets = {
        "Match Winner": {"Home": 1.5, "Draw": 4.0, "Away": 7.0},
        "Goals Over/Under": {"Over 2.5": 2.0, "Under 2.5": 1.8},
        "Both Teams Score": {"Yes": 2.0, "No": 1.8},
    }
    board = value_board(f, markets, "Alpha", "Beta")
    assert board, "expected at least one priceable bet"
    edges = [r["edge"] for r in board]
    assert edges == sorted(edges, reverse=True)  # most favourable first
    for r in board:
        assert r["edge"] == pytest.approx(r["model_prob"] - r["implied"], abs=1e-3)
        assert r["odds"] > 1.0


def test_best_value_bet_threshold():
    board = [
        {"bet": "X", "odds": 2.0, "model_prob": 0.55, "implied": 0.50, "edge": 0.05},
        {"bet": "Y", "odds": 2.0, "model_prob": 0.51, "implied": 0.50, "edge": 0.01},
    ]
    assert best_value_bet(board, min_edge=0.03)["bet"] == "X"   # clears bar
    assert best_value_bet(board, min_edge=0.10) is None         # nothing qualifies
    assert best_value_bet([], min_edge=0.03) is None


@pytest.mark.parametrize(
    "prob,odds,bankroll,expected",
    [
        (0.60, 2.0, 100.0, 5.0),   # f*=0.2, quarter-Kelly=0.05 -> 5% of 100
        (0.50, 2.0, 100.0, 0.0),   # no edge -> no stake
        (0.95, 2.0, 100.0, 5.0),   # huge edge clamped to the 5% cap
    ],
)
def test_suggest_stake(prob, odds, bankroll, expected):
    assert suggest_stake(prob, odds, bankroll=bankroll, kelly_mult=0.25) == pytest.approx(expected)

import pytest

import ledger
from api.models import Team, WCFixture
from ledger import extract_best_bet, grade_bet, load_predictions, record_prediction


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
        fixture, analysis, "test-model", "results/report.html",
    )

    preds = load_predictions()
    assert len(preds) == 1
    entry = preds[0]
    assert entry["fixture_id"] == 42
    assert entry["best_bet"] == "Mexico -1 Asian handicap"
    assert entry["confidence"] == "6"
    assert entry["home"] == "Mexico"


def test_load_predictions_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "nope.jsonl")
    assert load_predictions() == []

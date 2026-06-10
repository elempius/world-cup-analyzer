"""Prediction ledger: records each analysis' Best Bet and grades it against results."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LEDGER_PATH = Path("results/predictions.jsonl")


def extract_best_bet(analysis: str) -> tuple[Optional[str], Optional[str]]:
    """Pull the Best Bet line and X/10 confidence out of the AI analysis text."""
    m = re.search(r"best bet[^:\n]*:\s*(.+)", analysis, re.IGNORECASE)
    if not m:
        return None, None
    bet = m.group(1).strip().strip("*\"'").strip()
    cm = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", analysis[m.start():])
    confidence = cm.group(1) if cm else None
    return bet, confidence


def record_prediction(team1, team2, fixture, analysis: str, model: str, report_path) -> None:
    bet, confidence = extract_best_bet(analysis)
    entry = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fixture_id": fixture.fixture_id if fixture else None,
        "fixture_date": fixture.date if fixture else None,
        "home": fixture.home_team.name if fixture else team1.name,
        "away": fixture.away_team.name if fixture else team2.name,
        "model": model,
        "best_bet": bet,
        "confidence": confidence,
        "report": str(report_path),
    }
    LEDGER_PATH.parent.mkdir(exist_ok=True)
    with LEDGER_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def load_predictions() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return [json.loads(line) for line in LEDGER_PATH.read_text().splitlines() if line.strip()]


def grade_bet(
    bet: Optional[str],
    home: str,
    away: str,
    home_goals: Optional[int],
    away_goals: Optional[int],
) -> Optional[bool]:
    """Best-effort grading of common bet types.

    Returns True (win), False (loss), or None (push or unrecognized market).
    Scores are full-time; knockout bets settled after extra time may grade
    differently than the 90-minute market.
    """
    if not bet or home_goals is None or away_goals is None:
        return None
    b = bet.lower()
    total = home_goals + away_goals

    m = re.search(r"\b(over|under)\s+(\d+(?:\.\d+)?)", b)
    if m:
        line = float(m.group(2))
        if total == line:
            return None  # push
        return (total > line) == (m.group(1) == "over")

    if "both teams to score" in b or "btts" in b:
        btts = home_goals > 0 and away_goals > 0
        return (not btts) if re.search(r"\bno\b", b) else btts

    side = None
    if home.lower() in b:
        side = "home"
    elif away.lower() in b:
        side = "away"

    m = re.search(r"([+-]\d+(?:\.\d+)?)", b)
    if m and side:
        handicap = float(m.group(1))
        diff = (home_goals - away_goals) if side == "home" else (away_goals - home_goals)
        adjusted = diff + handicap
        if adjusted == 0:
            return None  # push
        return adjusted > 0

    if "draw no bet" in b and side:
        if home_goals == away_goals:
            return None  # push
        return (home_goals > away_goals) == (side == "home")

    if ("or draw" in b or "double chance" in b) and side:
        if home_goals == away_goals:
            return True
        return (home_goals > away_goals) == (side == "home")

    if "draw" in b and not side:
        return home_goals == away_goals

    if side and re.search(r"\b(win|wins|victory|moneyline|ml)\b", b):
        if home_goals == away_goals:
            return False
        return (home_goals > away_goals) == (side == "home")

    return None

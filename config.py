"""Central configuration: tunable constants and env-overridable settings.

Anything that used to be a magic number scattered across the codebase lives here.
Settings a user may reasonably want to change can be overridden via environment
variables (read once at import time, after dotenv has loaded).
"""

import os


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# --- HTTP / API client ---
HTTP_TIMEOUT = _float("WCA_HTTP_TIMEOUT", 30.0)
FETCH_ATTEMPTS = _int("WCA_FETCH_ATTEMPTS", 3)
RATE_LIMIT_SLEEP = _float("WCA_RATE_LIMIT_SLEEP", 8.0)
ODDS_BOOKMAKER_LIMIT = _int("WCA_ODDS_BOOKMAKERS", 5)
MAX_WORKERS = _int("WCA_MAX_WORKERS", 4)

# --- LLM / reasoning ---
# Reasoning effort for thinking models on OpenRouter: "low" | "medium" | "high".
REASONING_EFFORT = os.getenv("WCA_REASONING_EFFORT", "high")
# Token budget for the model's response (reasoning models need headroom).
MAX_TOKENS = _int("WCA_MAX_TOKENS", 8000)

# --- Statistical model ---
# Baseline goals for an average team in an average match (Poisson rate anchor).
LEAGUE_AVG_GOALS = _float("WCA_LEAGUE_AVG_GOALS", 1.35)
# Multiplicative bump applied to the home side's expected goals.
HOME_ADVANTAGE = _float("WCA_HOME_ADVANTAGE", 1.10)
# Weight given to recent form vs. tournament season averages when blending (0..1).
FORM_WEIGHT = _float("WCA_FORM_WEIGHT", 0.5)
# How strongly the head-to-head record nudges the rate parameters (0 disables).
H2H_WEIGHT = _float("WCA_H2H_WEIGHT", 0.15)
# Largest goal tally considered when summing the Poisson score grid.
MAX_GOALS_GRID = _int("WCA_MAX_GOALS_GRID", 10)
# Opponent-strength mitigation: cap one match's contribution to a team's goal
# rates so thrashing a minnow 6-0 doesn't read as elite attack/defense.
MAX_MATCH_GOALS = _float("WCA_MAX_MATCH_GOALS", 4.0)
# Small-sample shrinkage: a team's rates are pulled toward the league average,
# with this many "phantom average games" added. Bigger -> more conservative.
SHRINK_GAMES = _float("WCA_SHRINK_GAMES", 4.0)
# Market anchoring: how much weight to give the de-vigged bookmaker odds when
# they're available (0..1). The market already prices strength-of-schedule and
# squad quality, so it corrects the raw goals model's blind spots.
MARKET_WEIGHT = _float("WCA_MARKET_WEIGHT", 0.65)

# --- Ledger ---
# Fraction of full Kelly to stake (0.25 = quarter Kelly, the usual conservative choice).
KELLY_FRACTION = _float("WCA_KELLY_FRACTION", 0.25)
# Your betting bankroll in EUR. Stake suggestions are sized as a fraction of this.
BANKROLL_EUR = _float("WCA_BANKROLL_EUR", 100.0)
# Hard cap on any single stake suggestion, as a fraction of the bankroll, so an
# extreme edge can't suggest betting the farm. 0.05 = at most 5% on one bet.
MAX_STAKE_FRACTION = _float("WCA_MAX_STAKE_FRACTION", 0.05)
# Minimum edge (model probability minus market-implied probability, 1/odds) for a
# bet to count as "value" and be eligible as a Best Bet. Below this the market is
# treated as efficient and the tool recommends no bet. 0.03 = 3 percentage points.
MIN_EDGE = _float("WCA_MIN_EDGE", 0.03)

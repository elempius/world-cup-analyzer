"""In-house statistical match forecast.

The API-Football /predictions endpoint returns mostly empty placeholders for
these fixtures, so we compute our own quantitative forecast from data we *can*
fetch reliably: each team's recent form, its tournament goal averages, and the
head-to-head record.

The model is a deliberately transparent bivariate-Poisson goals model:

1. Estimate each team's attacking rate (goals scored per game) and defensive
   rate (goals conceded per game) by blending recent form with season averages.
2. Turn those into expected goals for this specific matchup, adjusting for home
   advantage and nudging toward the head-to-head goal pattern.
3. Build the Poisson score grid and read every market off it (1X2, totals, BTTS,
   correct scores, Asian handicaps).

No opaque magic — every number traces back to the inputs and the constants in
config.py.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Optional

import config
from api.models import BookmakerOdds, MatchResult, Team, TeamStats

LINES = (0.5, 1.5, 2.5, 3.5, 4.5)


@dataclass
class MatchForecast:
    home_name: str
    away_name: str
    lambda_home: float
    lambda_away: float
    p_home: float
    p_draw: float
    p_away: float
    exp_goals_home: float
    exp_goals_away: float
    p_btts: float
    over_probs: dict[float, float]          # line -> P(total goals > line)
    top_scorelines: list[tuple[str, float]]  # ["2-1", prob], most likely first
    basis: str                               # what data fed the estimate
    anchored: bool = False                    # blended toward bookmaker odds?
    # Full home/away score-probability grid; kept for exact market pricing.
    grid: list[list[float]] = field(default_factory=list, repr=False)

    def fair_odds(self) -> dict[str, float]:
        """Model-implied fair decimal odds for the headline markets."""
        out: dict[str, float] = {}
        for label, p in (
            ("home", self.p_home),
            ("draw", self.p_draw),
            ("away", self.p_away),
            ("over_2.5", self.over_probs.get(2.5, 0.0)),
            ("under_2.5", 1 - self.over_probs.get(2.5, 0.0)),
            ("btts_yes", self.p_btts),
            ("btts_no", 1 - self.p_btts),
        ):
            out[label] = round(1 / p, 2) if p > 0 else float("inf")
        return out


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _form_rates(team_id: int, form: list[MatchResult]) -> Optional[tuple[float, float, int]]:
    """Goals scored/conceded per game from a team's finished recent matches.

    Each match's goals are capped (config.MAX_MATCH_GOALS) so a blowout against a
    minnow doesn't read as elite attack/defense — a light opponent-strength guard
    for data that carries no opponent rating.
    """
    cap = config.MAX_MATCH_GOALS
    gf = ga = 0.0
    n = 0
    for m in form:
        if m.home_goals is None or m.away_goals is None:
            continue
        if m.home_team.id == team_id:
            scored, conceded = m.home_goals, m.away_goals
        elif m.away_team.id == team_id:
            scored, conceded = m.away_goals, m.home_goals
        else:
            continue
        gf += min(scored, cap)
        ga += min(conceded, cap)
        n += 1
    if n == 0:
        return None
    return gf / n, ga / n, n


def _season_rates(stats: Optional[TeamStats]) -> Optional[tuple[float, float]]:
    if not stats:
        return None
    gf = _safe_float(stats.goals_for_avg, -1.0)
    ga = _safe_float(stats.goals_against_avg, -1.0)
    if gf < 0 or ga < 0 or (gf == 0 and ga == 0 and stats.played == 0):
        return None
    return gf, ga


def _shrink(rate: float, n: float) -> float:
    """Pull a rate toward the league average, weighted by sample size.

    With few games the estimate is noisy, so it leans on the league baseline;
    with many games it trusts the observed rate. config.SHRINK_GAMES sets how
    many 'phantom average games' are mixed in.
    """
    k = config.SHRINK_GAMES
    avg = config.LEAGUE_AVG_GOALS
    return (n * rate + k * avg) / (n + k)


def _team_rates(team_id: int, form: list[MatchResult], stats: Optional[TeamStats]) -> tuple[float, float, str]:
    """Blended, shrunk (attack, defense) goal rates plus a source label."""
    season = _season_rates(stats)
    form_r = _form_rates(team_id, form)
    w = config.FORM_WEIGHT
    if season and form_r:
        gf = w * form_r[0] + (1 - w) * season[0]
        ga = w * form_r[1] + (1 - w) * season[1]
        n = form_r[2] + (stats.played if stats else 0)
        basis = "form+season"
    elif form_r:
        gf, ga, n, basis = form_r[0], form_r[1], form_r[2], f"form({form_r[2]})"
    elif season:
        gf, ga = season[0], season[1]
        n = stats.played if stats else 0
        basis = "season"
    else:
        avg = config.LEAGUE_AVG_GOALS
        return avg, avg, "league-average (no data)"
    return _shrink(gf, n), _shrink(ga, n), basis


def _h2h_rates(team_id: int, h2h: list[MatchResult]) -> Optional[tuple[float, float, int]]:
    """Goals scored/conceded per game by `team_id` across head-to-head meetings."""
    gf = ga = n = 0
    for m in h2h:
        if m.home_goals is None or m.away_goals is None:
            continue
        if m.home_team.id == team_id:
            gf += m.home_goals
            ga += m.away_goals
        elif m.away_team.id == team_id:
            gf += m.away_goals
            ga += m.home_goals
        else:
            continue
        n += 1
    if n == 0:
        return None
    return gf / n, ga / n, n


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _score_grid(lam_home: float, lam_away: float, n: int) -> list[list[float]]:
    home_pmf = [_poisson_pmf(i, lam_home) for i in range(n + 1)]
    away_pmf = [_poisson_pmf(j, lam_away) for j in range(n + 1)]
    return [[home_pmf[i] * away_pmf[j] for j in range(n + 1)] for i in range(n + 1)]


def _win_probs(grid: list[list[float]]) -> tuple[float, float, float]:
    n = len(grid) - 1
    ph = pd = pa = 0.0
    for i in range(n + 1):
        for j in range(n + 1):
            if i > j:
                ph += grid[i][j]
            elif i == j:
                pd += grid[i][j]
            else:
                pa += grid[i][j]
    return ph, pd, pa


def _market_probs(odds: list[BookmakerOdds]) -> Optional[tuple[float, float, float]]:
    """De-vigged 1X2 probabilities, averaged across bookmakers. None if no usable
    odds. Removing the overround turns prices into a fair probability estimate."""
    samples = []
    for o in odds:
        try:
            h, d, a = float(o.home), float(o.draw), float(o.away)
        except (TypeError, ValueError):
            continue
        if h <= 1 or d <= 1 or a <= 1:
            continue
        inv = (1 / h, 1 / d, 1 / a)
        s = sum(inv)
        samples.append((inv[0] / s, inv[1] / s, inv[2] / s))
    if not samples:
        return None
    k = len(samples)
    return tuple(sum(x[i] for x in samples) / k for i in range(3))  # type: ignore[return-value]


def _fit_lambdas(target_home: float, target_away: float, n: int) -> tuple[float, float]:
    """Find the (lam_home, lam_away) whose Poisson 1X2 best matches the target
    home/away win probabilities, so the whole score grid stays consistent with
    the market-anchored probabilities."""
    best = (config.LEAGUE_AVG_GOALS, config.LEAGUE_AVG_GOALS)
    best_err = float("inf")
    lo, hi, step = 0.2, 4.0, 0.1
    lh = lo
    while lh <= hi + 1e-9:
        la = lo
        while la <= hi + 1e-9:
            ph, _pd, pa = _win_probs(_score_grid(lh, la, n))
            err = (ph - target_home) ** 2 + (pa - target_away) ** 2
            if err < best_err:
                best_err = err
                best = (lh, la)
            la += step
        lh += step
    return best


def forecast_match(
    home_team: Team,
    away_team: Team,
    home_form: list[MatchResult],
    away_form: list[MatchResult],
    home_stats: Optional[TeamStats],
    away_stats: Optional[TeamStats],
    h2h: Optional[list[MatchResult]] = None,
    odds: Optional[list[BookmakerOdds]] = None,
) -> MatchForecast:
    league_avg = config.LEAGUE_AVG_GOALS
    n = config.MAX_GOALS_GRID

    h_attack, h_defense, h_basis = _team_rates(home_team.id, home_form, home_stats)
    a_attack, a_defense, a_basis = _team_rates(away_team.id, away_form, away_stats)

    # Expected goals: a team's attack scaled by the opponent's (normalized) leak.
    lam_home = h_attack * (a_defense / league_avg) * config.HOME_ADVANTAGE
    lam_away = a_attack * (h_defense / league_avg)

    # Nudge toward the head-to-head goal pattern, if any meetings exist.
    h2h_basis = ""
    h2h_rates = _h2h_rates(home_team.id, h2h or [])
    if h2h_rates:
        h2h_gf, h2h_ga, h2h_n = h2h_rates
        k = config.H2H_WEIGHT
        lam_home = (1 - k) * lam_home + k * h2h_gf
        lam_away = (1 - k) * lam_away + k * h2h_ga
        h2h_basis = f" +h2h({h2h_n})"

    lam_home = min(max(lam_home, 0.2), 5.0)
    lam_away = min(max(lam_away, 0.2), 5.0)

    # Market anchoring: blend the raw goals model with the de-vigged bookmaker
    # odds (which encode strength-of-schedule and squad quality the goals model
    # can't see), then refit the lambdas so every market stays consistent.
    anchored = False
    market = _market_probs(odds or [])
    if market:
        m_home, _m_draw, m_away = market
        ph, _pd, pa = _win_probs(_score_grid(lam_home, lam_away, n))
        w = config.MARKET_WEIGHT
        blended_home = w * m_home + (1 - w) * ph
        blended_away = w * m_away + (1 - w) * pa
        lam_home, lam_away = _fit_lambdas(blended_home, blended_away, n)
        anchored = True

    grid = _score_grid(lam_home, lam_away, n)
    p_home = p_draw = p_away = p_btts = 0.0
    over = {line: 0.0 for line in LINES}
    for i in range(n + 1):
        for j in range(n + 1):
            p = grid[i][j]
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if i >= 1 and j >= 1:
                p_btts += p
            for line in LINES:
                if i + j > line:
                    over[line] += p

    scorelines = sorted(
        ((f"{i}-{j}", grid[i][j]) for i in range(n + 1) for j in range(n + 1)),
        key=lambda kv: kv[1],
        reverse=True,
    )[:5]

    basis = f"home: {h_basis}, away: {a_basis}{h2h_basis}"
    if anchored:
        basis += f"; market-anchored (w={config.MARKET_WEIGHT:g})"
    else:
        basis += "; no market odds — wide prior, treat with caution"
    return MatchForecast(
        home_name=home_team.name,
        away_name=away_team.name,
        lambda_home=round(lam_home, 2),
        lambda_away=round(lam_away, 2),
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        exp_goals_home=round(lam_home, 2),
        exp_goals_away=round(lam_away, 2),
        p_btts=p_btts,
        over_probs=over,
        top_scorelines=scorelines,
        basis=basis,
        anchored=anchored,
        grid=grid,
    )


def prob_for_bet(
    forecast: MatchForecast,
    bet: Optional[str],
    home: str,
    away: str,
) -> Optional[float]:
    """Model-estimated probability that `bet` wins, mirroring ledger.grade_bet's
    market coverage. Returns None when the market isn't understood.

    Probabilities are unconditional (pushes are not removed), which is a fine
    approximation for stake sizing.
    """
    if not bet or not forecast.grid:
        return None
    b = bet.lower()
    grid = forecast.grid
    n = len(grid) - 1

    def total_over(line: float) -> float:
        return sum(grid[i][j] for i in range(n + 1) for j in range(n + 1) if i + j > line)

    m = re.search(r"\b(over|under)\s+(\d+(?:\.\d+)?)", b)
    if m:
        line = float(m.group(2))
        p_over = total_over(line)
        return p_over if m.group(1) == "over" else 1 - p_over

    if "both teams to score" in b or "btts" in b:
        return (1 - forecast.p_btts) if re.search(r"\bno\b", b) else forecast.p_btts

    side = None
    if home.lower() in b:
        side = "home"
    elif away.lower() in b:
        side = "away"

    m = re.search(r"([+-]\d+(?:\.\d+)?)", b)
    if m and side:
        handicap = float(m.group(1))
        p = sum(
            grid[i][j]
            for i in range(n + 1)
            for j in range(n + 1)
            if ((i - j) if side == "home" else (j - i)) + handicap > 0
        )
        return p

    if "draw no bet" in b and side:
        denom = 1 - forecast.p_draw
        if denom <= 0:
            return None
        win = forecast.p_home if side == "home" else forecast.p_away
        return win / denom

    if ("or draw" in b or "double chance" in b) and side:
        win = forecast.p_home if side == "home" else forecast.p_away
        return win + forecast.p_draw

    if "draw" in b and not side:
        return forecast.p_draw

    if side and re.search(r"\b(win|wins|victory|moneyline|ml)\b", b):
        return forecast.p_home if side == "home" else forecast.p_away

    return None

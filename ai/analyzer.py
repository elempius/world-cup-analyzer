from typing import Optional

from openai import OpenAI
from rich.console import Console
from rich.rule import Rule

import config
from api.models import ApiPrediction, BookmakerOdds, FixtureEvent, FixturePlayerStat, FixtureTeamStat, Injury, Last5, MatchResult, PlayerStat, StandingsEntry, Team, TeamLineup, TeamStats, WCFixture
from model import MatchForecast

console = Console()

SYSTEM_PROMPT = """\
You are a football analyst who reasons strictly from a supplied data dossier. You produce
match predictions for the FIFA World Cup 2026.

CRITICAL — data grounding:
- Use ONLY the data provided in the user message. Do not rely on your own prior knowledge of
  squads, transfers, recent results, rankings, or form. Your training data predates this
  tournament and is unreliable for it; treating it as fact will produce wrong predictions.
- Every factual claim you make must trace back to a specific line in the dossier. Do not invent
  scorelines, player names, injuries, or statistics that are not present.
- If something needed for a judgement is not in the dossier, say so explicitly
  ("not available in the provided data") rather than filling the gap from memory or guessing.
- The "Statistical Model (in-house)" section is your primary quantitative anchor — it is computed
  from the form and goal data in this dossier and, when bookmaker odds are present, blended toward
  the market. Build your prediction around it, but treat it as a rough estimate, not gospel.
- Treat any "API-Football Prediction" section as a secondary input only; it is often sparse.
- Treat the pre-match odds as the market's best probability estimate; it already accounts for squad
  quality and strength of schedule that the raw form numbers do not. Do NOT reflexively back the
  underdog or the higher-priced outcome — a longer price is not "value" by itself. Only favour an
  outcome the market rates unlikely if the dossier gives a concrete, stated reason (injuries,
  lineups, a clear stylistic mismatch). When the model and market broadly agree, backing the
  favourite is a perfectly legitimate Best Bet.

Style rules:
- Do not use emoji anywhere in your response.
- Be direct and specific — cite the actual scorelines, rates, and probabilities provided.
- Identify the single key tactical battle that will decide the match (from the data given).
- Acknowledge genuine uncertainty; do not manufacture false confidence.
- Keep each section concise — no padding or filler.

Structure your response with exactly these sections:
## Form & Momentum
## Head-to-Head
## Key Tactical Battle
## Players to Watch
## Injury Impact
## Prediction

The Prediction section must end with a single "Best Bet" — one specific recommendation \
(e.g. "Argentina -1 Asian handicap", "Under 2.5 goals", "Both teams to score: No") \
that you have the highest conviction in given all available data, followed by your \
confidence rating (X/10) and 2-3 sentences explaining your reasoning. Ground the pick in the \
model probabilities and the dossier; note whether it agrees with the market. Do not force a \
contrarian angle — if the data does not support disagreeing with the odds, pick the bet you are \
most confident is correct, even if it is the favourite at a short price.
"""


def _format_form(team: Team, matches: list[MatchResult], events: Optional[dict[int, list[FixtureEvent]]] = None) -> str:
    if not matches:
        return f"{team.name}: No recent match data available.\n"
    lines = [f"{team.name} — Last {len(matches)} matches:"]
    for m in matches:
        lines.append(f"  {m.format_for_team(team.id)}")
        if not events or m.fixture_id not in events:
            continue
        fevents = events[m.fixture_id]
        team_goals = [e for e in fevents if e.type == "Goal" and e.team.id == team.id and "Own" not in e.detail]
        opp_goals  = [e for e in fevents if e.type == "Goal" and e.team.id != team.id and "Own" not in e.detail]
        reds       = [e for e in fevents if e.type == "Card" and "Red" in e.detail]
        goal_parts = []
        if team_goals:
            g = [f"{e.player} {e.minute}'" + (" pen" if "Penalty" in e.detail else "") for e in team_goals]
            goal_parts.append(f"{team.name}: {', '.join(g)}")
        if opp_goals:
            opp = m.away_team.name if m.home_team.id == team.id else m.home_team.name
            g = [f"{e.player} {e.minute}'" + (" pen" if "Penalty" in e.detail else "") for e in opp_goals]
            goal_parts.append(f"{opp}: {', '.join(g)}")
        if goal_parts:
            lines.append(f"    Goals: {' | '.join(goal_parts)}")
        if reds:
            red_strs = [f"{e.team.name}: {e.player} {e.minute}'" for e in reds]
            lines.append(f"    Red cards: {', '.join(red_strs)}")
    return "\n".join(lines)


def _format_h2h(team1: Team, team2: Team, matches: list[MatchResult]) -> str:
    if not matches:
        return "Head-to-Head: No historical data available.\n"

    t1_wins = t2_wins = draws = 0
    lines = [f"H2H — Last {len(matches)} meetings:"]
    for m in matches:
        score = f"{m.home_goals}-{m.away_goals}" if m.home_goals is not None else "?"
        lines.append(f"  {m.home_team.name} {score} {m.away_team.name} — {m.league} ({m.date[:10]})")
        if m.home_goals is not None and m.away_goals is not None:
            home_win = m.home_goals > m.away_goals
            away_win = m.away_goals > m.home_goals
            is_t1_home = m.home_team.id == team1.id
            if home_win:
                if is_t1_home:
                    t1_wins += 1
                else:
                    t2_wins += 1
            elif away_win:
                if is_t1_home:
                    t2_wins += 1
                else:
                    t1_wins += 1
            else:
                draws += 1

    lines.append(f"  Record: {team1.name} {t1_wins}W / {draws}D / {t2_wins}W {team2.name}")
    return "\n".join(lines)


def _format_injuries(injuries: list[Injury], team1_name: str, team2_name: str) -> str:
    t1 = [i for i in injuries if i.team_name == team1_name]
    t2 = [i for i in injuries if i.team_name == team2_name]
    if not t1 and not t2:
        return ""
    lines = ["Injury Report:"]
    for team_name, team_injuries in [(team1_name, t1), (team2_name, t2)]:
        if team_injuries:
            lines.append(f"  {team_name}:")
            for inj in team_injuries:
                lines.append(f"    - {inj.player} ({inj.injury_type}: {inj.reason})")
    return "\n".join(lines)


def _format_lineups(lineups: list[TeamLineup]) -> str:
    if not lineups:
        return ""
    lines = ["Confirmed Lineups:"]
    for lu in lineups:
        lines.append(f"  {lu.team.name} [{lu.formation}] — Coach: {lu.coach}")
        starters = ", ".join(
            f"{p.number}.{p.name}" for p in sorted(lu.starting_xi, key=lambda x: x.number)
        )
        lines.append(f"    XI: {starters}")
        bench = ", ".join(p.name for p in lu.substitutes[:7])
        lines.append(f"    Bench: {bench}")
    return "\n".join(lines)


def _format_team_stats(stats: Optional[TeamStats]) -> str:
    if not stats:
        return ""
    lines = [
        f"{stats.team.name} — Tournament Stats:",
        f"  Record: {stats.wins}W / {stats.draws}D / {stats.losses}L ({stats.played} played)",
        f"  Form: {stats.form or 'N/A'}",
        f"  Goals: {stats.goals_for_avg} scored / {stats.goals_against_avg} conceded per game",
        f"  Clean sheets: {stats.clean_sheets}",
    ]
    if stats.biggest_win:
        lines.append(f"  Biggest win: {stats.biggest_win}  |  Biggest loss: {stats.biggest_loss or 'N/A'}")
    if stats.win_streak:
        lines.append(f"  Best win streak: {stats.win_streak}")
    if stats.preferred_formation:
        lines.append(f"  Preferred formation: {stats.preferred_formation}")
    return "\n".join(lines)


def _format_standings(team: Team, entries: list[StandingsEntry]) -> str:
    team_entry = next((e for e in entries if e.team.id == team.id), None)
    if not team_entry:
        return f"{team.name}: Not found in standings.\n"

    group_entries = sorted(
        [e for e in entries if e.group == team_entry.group],
        key=lambda e: e.rank,
    )
    lines = [f"Group standings — {team_entry.group}:"]
    for e in group_entries:
        marker = " ◀" if e.team.id == team.id else ""
        lines.append(
            f"  {e.rank}. {e.team.name:<22} {e.points}pts  "
            f"{e.played}G {e.won}W {e.drawn}D {e.lost}L  "
            f"GD:{e.goal_diff:+d}  Form:{e.form or '-'}"
            f"{marker}"
        )
    return "\n".join(lines)


def _fmt_last5(l5: Optional[Last5], name: str) -> str:
    if not l5:
        return ""
    return (
        f"{name} last-5 ratings: form {l5.form_pct} / attack {l5.att_pct} / defense {l5.def_pct} | "
        f"goals scored {l5.goals_for_avg}/game ({l5.goals_for_total} total) | "
        f"goals conceded {l5.goals_against_avg}/game ({l5.goals_against_total} total)"
    )


def _format_forecast(f: Optional[MatchForecast]) -> str:
    if not f:
        return ""
    odds = f.fair_odds()
    scores = ", ".join(f"{s} ({p:.0%})" for s, p in f.top_scorelines[:4])
    lines = [
        "Statistical Model (in-house, computed from the form and goal data above):",
        f"  Method: bivariate-Poisson goals model. Data basis — {f.basis}.",
        f"  Expected goals: {f.home_name} {f.exp_goals_home} / {f.away_name} {f.exp_goals_away}",
        f"  Win probability: {f.home_name} {f.p_home:.0%} / Draw {f.p_draw:.0%} / {f.away_name} {f.p_away:.0%}",
        f"  Fair 1X2 odds: {odds['home']} / {odds['draw']} / {odds['away']}",
        f"  Over 2.5 goals: {f.over_probs.get(2.5, 0):.0%} (fair {odds['over_2.5']})  |  "
        f"Under 2.5: {1 - f.over_probs.get(2.5, 0):.0%} (fair {odds['under_2.5']})",
        f"  Both teams to score: {f.p_btts:.0%} (fair {odds['btts_yes']})",
        f"  Most likely scorelines: {scores}",
    ]
    return "\n".join(lines)


def _format_prediction(pred: Optional[ApiPrediction], home_name: str, away_name: str) -> str:
    if not pred or not pred.is_populated:
        return ""
    lines = [
        "API-Football Prediction:",
        f"  Advice: {pred.advice}",
        f"  Winner: {pred.winner_name or '?'} ({pred.winner_comment or ''})"
        + (" — win or draw" if pred.win_or_draw else ""),
        f"  1X2 probabilities: {home_name} {pred.home_percent} / Draw {pred.draw_percent} / {away_name} {pred.away_percent}",
    ]
    if pred.goals_home or pred.goals_away:
        lines.append(f"  Expected goals: home {pred.goals_home or '?'} / away {pred.goals_away or '?'}"
                     + (f" (line: {pred.under_over})" if pred.under_over else ""))

    if pred.home_under_over:
        uo = pred.home_under_over
        lines.append(
            f"  {home_name} games over/under (this season): "
            f"o0.5={uo.over_0_5} o1.5={uo.over_1_5} o2.5={uo.over_2_5} o3.5={uo.over_3_5} o4.5={uo.over_4_5}"
        )
    if pred.away_under_over:
        uo = pred.away_under_over
        lines.append(
            f"  {away_name} games over/under (this season): "
            f"o0.5={uo.over_0_5} o1.5={uo.over_1_5} o2.5={uo.over_2_5} o3.5={uo.over_3_5} o4.5={uo.over_4_5}"
        )

    lines.append(
        f"  Comparison — Form: {pred.form_home}/{pred.form_away} | "
        f"Attack: {pred.att_home}/{pred.att_away} | "
        f"Defense: {pred.def_home}/{pred.def_away} | "
        f"Poisson: {pred.poisson_home}/{pred.poisson_away} | "
        f"H2H: {pred.h2h_home}/{pred.h2h_away} | "
        f"Goals: {pred.goals_comp_home}/{pred.goals_comp_away} | "
        f"Overall: {pred.total_home}/{pred.total_away}"
    )
    if pred.last_5_home:
        lines.append(f"  {_fmt_last5(pred.last_5_home, home_name)}")
    if pred.last_5_away:
        lines.append(f"  {_fmt_last5(pred.last_5_away, away_name)}")

    return "\n".join(lines)


def _format_player_stats(players: list[PlayerStat], team: Team) -> str:
    if not players:
        return ""
    lines = [f"{team.name} — Top contributors (tournament):"]
    lines.append(f"  {'Name':<25} {'Apps':>4} {'Min':>5} {'Gls':>4} {'Ast':>4} {'SoT':>4} {'KP':>4} {'Rating':>7}")
    lines.append(f"  {'-'*25} {'----':>4} {'-----':>5} {'---':>4} {'---':>4} {'---':>4} {'--':>4} {'------':>7}")
    for p in players[:8]:
        rating = p.rating or "—"
        lines.append(
            f"  {p.name:<25} {p.appearances:>4} {p.minutes:>5} "
            f"{p.goals:>4} {p.assists:>4} {p.shots_on:>4} {p.key_passes:>4} {rating:>7}"
        )
    return "\n".join(lines)


def _format_top_scorers(players: list[PlayerStat]) -> str:
    if not players:
        return ""
    lines = ["Tournament top scorers:"]
    for i, p in enumerate(players[:10], 1):
        lines.append(f"  {i:>2}. {p.name:<25} {p.goals}G {p.assists}A")
    return "\n".join(lines)


def _format_fixture_stats(stats: list[FixtureTeamStat]) -> str:
    if not stats or len(stats) < 2:
        return ""
    a, b = stats[0], stats[1]
    lines = [f"Match statistics — {a.team.name} vs {b.team.name}:"]
    def row(label, va, vb):
        return f"  {label:<20} {str(va or '—'):>8}   {str(vb or '—'):>8}"
    lines.append(row("Possession", a.possession, b.possession))
    lines.append(row("Shots (total)", a.shots_total, b.shots_total))
    lines.append(row("Shots on target", a.shots_on, b.shots_on))
    lines.append(row("Corners", a.corners, b.corners))
    lines.append(row("Passes", a.passes_total, b.passes_total))
    lines.append(row("Pass accuracy", a.pass_accuracy, b.pass_accuracy))
    lines.append(row("Fouls", a.fouls, b.fouls))
    lines.append(row("Offsides", a.offsides, b.offsides))
    lines.append(row("Saves", a.saves, b.saves))
    return "\n".join(lines)


def _format_odds(odds: list[BookmakerOdds], home_name: str, away_name: str) -> str:
    if not odds:
        return ""
    lines = [f"Pre-match odds — {home_name} / Draw / {away_name}:"]
    for o in odds[:4]:
        lines.append(f"  {o.bookmaker}: {o.home} / {o.draw} / {o.away}")
    return "\n".join(lines)


def _format_topassists(players: list[PlayerStat]) -> str:
    if not players:
        return ""
    lines = ["Tournament top assists:"]
    for i, p in enumerate(players[:8], 1):
        lines.append(f"  {i:>2}. {p.name:<25} {p.assists}A {p.goals}G")
    return "\n".join(lines)


def _format_top_yellowcards(players: list[PlayerStat]) -> str:
    if not players:
        return ""
    lines = ["Yellow card leaders (suspension risk):"]
    for i, p in enumerate(players[:8], 1):
        lines.append(f"  {i:>2}. {p.name:<25} {p.yellow_cards}Y {p.red_cards}R  ({p.appearances} apps)")
    return "\n".join(lines)


def _format_wc_events(events: list[FixtureEvent]) -> str:
    goals = [e for e in events if e.type == "Goal"]
    reds  = [e for e in events if e.type == "Card" and "Red" in e.detail]
    if not goals and not reds:
        return ""
    lines = ["Match events (chronological):"]
    for e in sorted(goals + reds, key=lambda x: x.minute):
        mins = f"{e.minute}'" + (f"+{e.extra_minute}" if e.extra_minute else "")
        if e.type == "Goal":
            own = " (OG)" if "Own" in e.detail else ""
            pen = " (pen)" if "Penalty" in e.detail else ""
            assist = f", assist: {e.assist}" if e.assist else ""
            lines.append(f"  {mins}  GOAL  {e.player}{own}{pen}{assist}  [{e.team.name}]")
        else:
            card = "Red card" if e.detail == "Red Card" else "2nd Yellow→Red"
            lines.append(f"  {mins}  {card}  {e.player}  [{e.team.name}]")
    return "\n".join(lines)


def _format_fixture_players(players: list[FixturePlayerStat], team1: Team, team2: Team) -> str:
    t1 = sorted([p for p in players if p.team.id == team1.id and p.minutes > 0],
                key=lambda p: float(p.rating or 0), reverse=True)
    t2 = sorted([p for p in players if p.team.id == team2.id and p.minutes > 0],
                key=lambda p: float(p.rating or 0), reverse=True)
    if not t1 and not t2:
        return ""
    lines = ["Player ratings from this fixture:"]
    for team, tplayers in [(team1, t1[:6]), (team2, t2[:6])]:
        if tplayers:
            lines.append(f"  {team.name}:")
            for p in tplayers:
                rating = p.rating or "—"
                lines.append(
                    f"    {p.name:<25} {rating:>5} | {p.minutes}' | "
                    f"{p.goals}G {p.assists}A {p.shots_on}SoT {p.tackles}tkl"
                )
    return "\n".join(lines)


def build_prompt(
    team1: Team,
    team2: Team,
    team1_form: list[MatchResult],
    team2_form: list[MatchResult],
    h2h: list[MatchResult],
    injuries: list[Injury],
    lineups: list[TeamLineup],
    fixture: Optional[WCFixture],
    team1_stats: Optional[TeamStats] = None,
    team2_stats: Optional[TeamStats] = None,
    standings: Optional[list[StandingsEntry]] = None,
    api_prediction: Optional[ApiPrediction] = None,
    team1_players: Optional[list[PlayerStat]] = None,
    team2_players: Optional[list[PlayerStat]] = None,
    top_scorers: Optional[list[PlayerStat]] = None,
    fixture_stats: Optional[list[FixtureTeamStat]] = None,
    form_events: Optional[dict[int, list[FixtureEvent]]] = None,
    odds: Optional[list[BookmakerOdds]] = None,
    top_assists: Optional[list[PlayerStat]] = None,
    top_yellowcards: Optional[list[PlayerStat]] = None,
    wc_events: Optional[list[FixtureEvent]] = None,
    fixture_players: Optional[list[FixturePlayerStat]] = None,
    forecast: Optional[MatchForecast] = None,
) -> str:
    if fixture:
        context = (
            f"Match: {fixture.home_team.name} vs {fixture.away_team.name}\n"
            f"Competition: FIFA World Cup 2026 — {fixture.round}\n"
            f"Date: {fixture.date[:16].replace('T', ' ')} UTC\n"
            f"Venue: {fixture.venue}\n"
        )
    else:
        context = (
            f"Hypothetical / upcoming match: {team1.name} vs {team2.name}\n"
            f"Competition: FIFA World Cup 2026\n"
            "(No scheduled fixture found — analyzing based on available data)\n"
        )

    home_name = fixture.home_team.name if fixture else team1.name
    away_name = fixture.away_team.name if fixture else team2.name

    sections = [
        "Please analyze this World Cup 2026 match and provide your prediction.\n",
        "## Match Context",
        context,
    ]

    # Tournament stats — only include teams that have data
    t1_stats_str = _format_team_stats(team1_stats)
    t2_stats_str = _format_team_stats(team2_stats)
    if t1_stats_str or t2_stats_str:
        sections.append("## Tournament Statistics")
        if t1_stats_str:
            sections += [t1_stats_str, ""]
        if t2_stats_str:
            sections += [t2_stats_str, ""]

    # Player stats — only include teams that have data
    t1_p_str = _format_player_stats(team1_players or [], team1)
    t2_p_str = _format_player_stats(team2_players or [], team2)
    if t1_p_str or t2_p_str:
        sections.append("## Player Statistics (Tournament)")
        if t1_p_str:
            sections += [t1_p_str, ""]
        if t2_p_str:
            sections += [t2_p_str, ""]

    ts_str = _format_top_scorers(top_scorers or [])
    if ts_str:
        sections += ["## " + ts_str, ""]

    ta_str = _format_topassists(top_assists or [])
    if ta_str:
        sections += ["## " + ta_str, ""]

    ty_str = _format_top_yellowcards(top_yellowcards or [])
    if ty_str:
        sections += ["## " + ty_str, ""]

    sections += [
        "## Recent Form (last matches across all competitions)",
        _format_form(team1, team1_form, form_events),
        "",
        _format_form(team2, team2_form, form_events),
        "",
        "## Head-to-Head",
        _format_h2h(team1, team2, h2h),
        "",
    ]

    if standings:
        sections += [
            "## Group Standings",
            _format_standings(team1, standings),
            "",
            _format_standings(team2, standings),
            "",
        ]

    fixture_stats_str = _format_fixture_stats(fixture_stats or [])
    if fixture_stats_str:
        sections += ["## Match Statistics", fixture_stats_str, ""]

    if wc_events:
        wc_events_str = _format_wc_events(wc_events)
        if wc_events_str:
            sections += ["## " + wc_events_str, ""]

    if fixture_players:
        fp_str = _format_fixture_players(fixture_players, team1, team2)
        if fp_str:
            sections += ["## " + fp_str, ""]

    inj_str = _format_injuries(injuries, team1.name, team2.name)
    if inj_str:
        sections += ["## " + inj_str, ""]

    lu_str = _format_lineups(lineups)
    if lu_str:
        sections += ["## Lineups", lu_str, ""]

    odds_str = _format_odds(odds or [], home_name, away_name)
    if odds_str:
        sections += ["## " + odds_str, ""]

    forecast_str = _format_forecast(forecast)
    if forecast_str:
        sections += ["## Statistical Model (in-house)", forecast_str, ""]

    pred_str = _format_prediction(api_prediction, home_name, away_name)
    if pred_str:
        sections += ["## API-Football Prediction", pred_str, ""]

    return "\n".join(sections)


def _client(openrouter_key: str) -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_key,
        default_headers={"X-Title": "World Cup Analyzer"},
    )


def _stream_completion(client: OpenAI, messages: list[dict], model: str) -> str:
    """Stream one completion, rendering the model's reasoning (dimmed) ahead of
    its answer. Returns only the answer text (reasoning is not persisted)."""
    extra_body = {}
    if config.REASONING_EFFORT:
        extra_body["reasoning"] = {"effort": config.REASONING_EFFORT}

    stream = client.chat.completions.create(
        model=model,
        max_tokens=config.MAX_TOKENS,
        messages=messages,
        stream=True,
        extra_body=extra_body,
    )

    reasoning_open = False
    answer_open = False
    chunks: list[str] = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
        if reasoning:
            if not reasoning_open:
                console.print("[dim italic]thinking…[/dim italic]")
                reasoning_open = True
            console.print(reasoning, end="", style="dim", markup=False, highlight=False)
        content = getattr(delta, "content", None)
        if content:
            if not answer_open:
                if reasoning_open:
                    console.print()
                    console.print(Rule("[bold cyan]Answer[/bold cyan]"))
                answer_open = True
            console.print(content, end="", markup=False, highlight=False)
            chunks.append(content)

    console.print()
    return "".join(chunks)


def stream_analysis(openrouter_key: str, prompt: str, model: str) -> tuple[str, OpenAI, list[dict]]:
    """Run the initial analysis. Returns (answer, client, messages) so the caller
    can continue the same conversation in an interactive session."""
    client = _client(openrouter_key)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    console.print(Rule("[bold cyan]AI Analysis[/bold cyan]"))
    console.print()
    answer = _stream_completion(client, messages, model)
    console.print(Rule())
    messages.append({"role": "assistant", "content": answer})
    return answer, client, messages


def interactive_session(client: OpenAI, messages: list[dict], model: str) -> None:
    """Drop into a follow-up Q&A loop over the same conversation. Ends on a blank
    line, 'exit'/'quit', or EOF/Ctrl-C."""
    console.print()
    console.print("[dim]Ask follow-up questions about this match. Press Enter on an empty line (or type 'exit') to finish.[/dim]")
    while True:
        try:
            question = console.input("\n[bold cyan]you ▸[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not question or question.lower() in {"exit", "quit", "q"}:
            break
        messages.append({"role": "user", "content": question})
        console.print()
        answer = _stream_completion(client, messages, model)
        messages.append({"role": "assistant", "content": answer})

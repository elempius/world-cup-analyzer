from typing import Optional

from openai import OpenAI
from rich.console import Console
from rich.rule import Rule

from api.models import ApiPrediction, Injury, MatchResult, StandingsEntry, Team, TeamLineup, TeamStats, WCFixture

console = Console()

SYSTEM_PROMPT = """\
You are an expert football analyst specializing in international tournament match prediction.
You have deep knowledge of team tactics, player form, set pieces, historical patterns, and \
psychological factors in knockout and group stage football.

Rules:
- Do not use emoji anywhere in your response.
- Be direct and specific — reference the actual scorelines and statistics provided.
- Identify the single key tactical battle that will decide the match.
- Acknowledge genuine uncertainty; do not manufacture false confidence.
- Keep each section concise — no padding or filler.

Structure your response with exactly these sections:
## Form & Momentum
## Head-to-Head
## Key Tactical Battle
## Players to Watch
## Injury Impact
## Prediction
The Prediction section must include: winner (or draw), scoreline, confidence 1-10, and 2-3 sentences of reasoning.
"""


def _format_form(team: Team, matches: list[MatchResult]) -> str:
    if not matches:
        return f"{team.name}: No recent match data available.\n"
    lines = [f"{team.name} — Last {len(matches)} matches:"]
    for m in matches:
        lines.append(f"  {m.format_for_team(team.id)}")
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
        return "Injuries: None reported for this fixture.\n"
    lines = ["Injury Report:"]
    for team_name, team_injuries in [(team1_name, t1), (team2_name, t2)]:
        if team_injuries:
            lines.append(f"  {team_name}:")
            for inj in team_injuries:
                lines.append(f"    - {inj.player} ({inj.injury_type}: {inj.reason})")
    return "\n".join(lines)


def _format_lineups(lineups: list[TeamLineup]) -> str:
    if not lineups:
        return "Lineups: Not yet announced.\n"
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
        return "Tournament stats: Not yet available.\n"
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


def _format_prediction(pred: Optional[ApiPrediction], home_name: str, away_name: str) -> str:
    if not pred:
        return "API Prediction: Not available for this fixture.\n"
    lines = [
        "API-Football Prediction:",
        f"  Advice: {pred.advice}",
        f"  Win probabilities: {home_name} {pred.home_percent} / Draw {pred.draw_percent} / {away_name} {pred.away_percent}",
    ]
    if pred.under_over:
        lines.append(f"  Expected goals: {pred.under_over}  (home {pred.goals_home}, away {pred.goals_away})")
    lines.append(
        f"  Comparison: Form {pred.form_home}/{pred.form_away} | "
        f"Attack {pred.att_home}/{pred.att_away} | "
        f"Defense {pred.def_home}/{pred.def_away} | "
        f"Overall {pred.total_home}/{pred.total_away}"
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

    sections = [
        "Please analyze this World Cup 2026 match and provide your prediction.\n",
        "## Match Context",
        context,
        "## Tournament Statistics",
        _format_team_stats(team1_stats),
        "",
        _format_team_stats(team2_stats),
        "",
        "## Recent Form (last matches across all competitions)",
        _format_form(team1, team1_form),
        "",
        _format_form(team2, team2_form),
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

    sections += [
        "## " + _format_injuries(injuries, team1.name, team2.name),
        "",
        "## Lineups",
        _format_lineups(lineups),
        "",
        "## " + _format_prediction(api_prediction, fixture.home_team.name if fixture else team1.name, fixture.away_team.name if fixture else team2.name),
    ]
    return "\n".join(sections)


def stream_analysis(openrouter_key: str, prompt: str, model: str) -> str:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_key,
        default_headers={"X-Title": "World Cup Analyzer"},
    )
    console.print(Rule("[bold cyan]AI Analysis[/bold cyan]"))
    console.print()

    stream = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        stream=True,
    )
    chunks = []
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            console.print(delta, end="", markup=False, highlight=False)
            chunks.append(delta)

    console.print()
    console.print(Rule())
    return "".join(chunks)

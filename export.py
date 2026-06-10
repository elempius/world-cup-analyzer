from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import markdown as md

from api.models import (
    ApiPrediction,
    BookmakerOdds,
    FixtureEvent,
    FixturePlayerStat,
    FixtureTeamStat,
    Injury,
    Last5,
    MatchResult,
    PlayerStat,
    StandingsEntry,
    Team,
    TeamLineup,
    TeamStats,
    WCFixture,
)

RESULTS_DIR = Path("results")

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:       #000;
    --surface:  #0d0d0d;
    --line:     #1c1c1c;
    --line2:    #111;
    --text:     #fff;
    --secondary:#888;
    --muted:    #444;
  }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.55;
    padding: 48px 16px 80px;
  }}

  .wrap {{ max-width: 860px; margin: 0 auto; }}

  /* ── Section label ── */
  .label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 12px;
  }}

  /* ── Divider ── */
  hr {{
    border: none;
    border-top: 1px solid var(--line);
    margin: 32px 0;
  }}

  /* ── Match header ── */
  .header {{
    border-top: 1px solid var(--text);
    border-bottom: 1px solid var(--line);
    padding: 28px 0 24px;
    margin-bottom: 40px;
  }}
  .header-teams {{
    font-size: 36px;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.1;
    margin-bottom: 10px;
  }}
  .header-meta {{
    font-size: 13px;
    color: var(--secondary);
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
  }}
  .header-meta span {{ white-space: nowrap; }}

  /* ── Two column ── */
  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: var(--line);
  }}
  .two-col > * {{
    background: var(--bg);
    padding: 20px;
  }}
  @media (max-width: 560px) {{
    .two-col {{ grid-template-columns: 1fr; }}
    .header-teams {{ font-size: 24px; }}
  }}

  /* ── Team name in column ── */
  .col-team {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--secondary);
    margin-bottom: 14px;
  }}

  /* ── Stat rows ── */
  .stat-row {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid var(--line2);
    font-size: 13px;
    gap: 12px;
  }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-key {{ color: var(--secondary); }}
  .stat-val {{ font-weight: 600; text-align: right; }}

  /* ── Form badges ── */
  .form-badges {{ display: flex; gap: 3px; flex-wrap: wrap; }}
  .badge {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px; height: 20px;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0;
  }}
  .badge-W {{ background: var(--text); color: var(--bg); }}
  .badge-D {{ background: #333; color: #aaa; }}
  .badge-L {{ background: var(--line); color: var(--muted); }}

  /* ── Match list ── */
  .match-list {{ display: flex; flex-direction: column; gap: 0; }}
  .match-row {{
    display: grid;
    grid-template-columns: 22px auto 1fr;
    align-items: baseline;
    gap: 8px;
    padding: 7px 0;
    border-bottom: 1px solid var(--line2);
    font-size: 13px;
  }}
  .match-row:last-child {{ border-bottom: none; }}
  .match-result {{
    font-weight: 800;
    font-size: 11px;
    text-align: center;
  }}
  .res-W {{ color: var(--text); }}
  .res-D {{ color: #666; }}
  .res-L {{ color: var(--muted); }}
  .match-score {{ font-weight: 600; }}
  .match-detail {{ color: var(--secondary); font-size: 12px; }}
  .match-competition {{ color: var(--muted); font-size: 11px; }}

  /* ── H2H record bar ── */
  .h2h-record {{
    display: flex;
    margin-bottom: 16px;
    height: 4px;
    gap: 2px;
  }}
  .h2h-t1 {{ background: var(--text); }}
  .h2h-draw {{ background: #333; }}
  .h2h-t2 {{ background: #555; }}
  .h2h-labels {{
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--secondary);
    margin-bottom: 14px;
  }}
  .h2h-labels strong {{ color: var(--text); }}

  /* ── Standings table ── */
  .standings-group-title {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
    margin-top: 20px;
  }}
  .standings-group-title:first-child {{ margin-top: 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{
    text-align: left;
    padding: 4px 8px;
    color: var(--muted);
    font-weight: 600;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--line);
  }}
  td {{ padding: 7px 8px; border-bottom: 1px solid var(--line2); }}
  tr:last-child td {{ border-bottom: none; }}
  tr.hl td {{ color: var(--text); font-weight: 600; }}
  tr:not(.hl) td {{ color: var(--secondary); }}
  td:first-child, th:first-child {{ color: var(--muted); }}

  /* ── Injuries ── */
  .injury-row {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid var(--line2);
    font-size: 13px;
    gap: 12px;
  }}
  .injury-row:last-child {{ border-bottom: none; }}
  .injury-player {{ font-weight: 600; }}
  .injury-type {{ font-size: 11px; color: var(--secondary); text-align: right; }}

  /* ── Lineups ── */
  .lineup-header {{
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 6px;
  }}
  .lineup-formation {{
    font-size: 11px;
    color: var(--secondary);
    margin-bottom: 10px;
  }}
  .lineup-players {{
    font-size: 13px;
    line-height: 1.9;
    color: var(--secondary);
  }}
  .lineup-bench-title {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-top: 10px;
    margin-bottom: 4px;
  }}

  /* ── Prediction bar ── */
  .pred-advice {{
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 16px;
  }}
  .pred-bar-wrap {{ margin-bottom: 6px; }}
  .pred-bar {{
    display: flex;
    height: 6px;
    gap: 2px;
    margin-bottom: 8px;
  }}
  .pred-t1   {{ background: var(--text); }}
  .pred-draw {{ background: #333; }}
  .pred-t2   {{ background: #666; }}
  .pred-bar-labels {{
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--secondary);
  }}
  .pred-comparison {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--line);
    margin-top: 16px;
  }}
  .pred-comp-cell {{
    background: var(--bg);
    padding: 10px;
    text-align: center;
  }}
  .pred-comp-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 6px;
  }}
  .pred-comp-values {{
    font-size: 12px;
    color: var(--secondary);
  }}
  .pred-comp-values strong {{ color: var(--text); display: block; }}

  /* ── AI Analysis ── */
  .ai-body h2 {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 28px 0 10px;
    padding-top: 28px;
    border-top: 1px solid var(--line);
  }}
  .ai-body h2:first-child {{ margin-top: 0; padding-top: 0; border-top: none; }}
  .ai-body h3 {{ font-size: 13px; font-weight: 700; margin: 14px 0 6px; }}
  .ai-body p {{ font-size: 14px; margin-bottom: 10px; color: #ddd; }}
  .ai-body strong {{ color: var(--text); }}
  .ai-body ul, .ai-body ol {{ padding-left: 18px; margin-bottom: 10px; }}
  .ai-body li {{ font-size: 14px; margin-bottom: 4px; color: #ddd; }}

  /* ── Player table ── */
  .player-table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 4px; }}
  .player-table th {{
    text-align: right; padding: 4px 8px;
    color: var(--muted); font-weight: 600; font-size: 10px;
    letter-spacing: 0.07em; text-transform: uppercase;
    border-bottom: 1px solid var(--line);
  }}
  .player-table th:first-child {{ text-align: left; }}
  .player-table td {{ padding: 6px 8px; border-bottom: 1px solid var(--line2); text-align: right; color: var(--secondary); }}
  .player-table td:first-child {{ text-align: left; color: var(--text); font-weight: 500; }}
  .player-table tr:last-child td {{ border-bottom: none; }}

  /* ── Fixture stats ── */
  .fixture-stat-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .fixture-stat-table td {{ padding: 7px 0; border-bottom: 1px solid var(--line2); }}
  .fixture-stat-table tr:last-child td {{ border-bottom: none; }}
  .fst-label {{ color: var(--muted); text-align: center; font-size: 11px; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; width: 40%; }}
  .fst-val {{ font-weight: 600; width: 30%; }}
  .fst-val-home {{ text-align: right; color: var(--text); }}
  .fst-val-away {{ text-align: left; color: var(--secondary); }}

  /* ── Top scorers ── */
  .scorer-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--line2); font-size: 13px; }}
  .scorer-row:last-child {{ border-bottom: none; }}
  .scorer-rank {{ color: var(--muted); width: 24px; }}
  .scorer-name {{ flex: 1; }}
  .scorer-stat {{ color: var(--secondary); font-size: 12px; }}

  /* ── Footer ── */
  .footer {{
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid var(--line);
    font-size: 11px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }}
</style>
</head>
<body>
<div class="wrap">
{body}
<div class="footer">
  <span>FIFA World Cup 2026 · Match Analysis</span>
  <span>{generated_at} · {model}</span>
</div>
</div>
</body>
</html>
"""


def _form_badges(form_str: str) -> str:
    badges = []
    for ch in (form_str or ""):
        if ch in "WDL":
            badges.append(f'<span class="badge badge-{ch}">{ch}</span>')
    return f'<div class="form-badges">{"".join(badges)}</div>' if badges else "<span style='color:#444'>—</span>"


def _pct(s: str) -> float:
    try:
        return max(0.0, float(s.strip("%")) / 100)
    except (ValueError, AttributeError):
        return 0.33


def _player_table(players: list[PlayerStat], team: Team) -> str:
    if not players:
        return ""
    rows = "".join(f"""
    <tr>
      <td>{p.name}</td>
      <td>{p.appearances}</td>
      <td>{p.minutes}'</td>
      <td>{p.goals}</td>
      <td>{p.assists}</td>
      <td>{p.shots_on}</td>
      <td>{p.key_passes}</td>
      <td>{p.rating or '—'}</td>
    </tr>""" for p in players[:8])
    return f"""
<div>
  <div class="col-team">{team.name}</div>
  <table class="player-table">
    <thead><tr>
      <th>Player</th><th>Apps</th><th>Min</th><th>Gls</th><th>Ast</th><th>SoT</th><th>KP</th><th>Rtg</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _fixture_stat_table(stats: list[FixtureTeamStat]) -> str:
    if not stats or len(stats) < 2:
        return ""
    a, b = stats[0], stats[1]
    def row(label, va, vb):
        return f"""
    <tr>
      <td class="fst-val fst-val-home">{va or '—'}</td>
      <td class="fst-label">{label}</td>
      <td class="fst-val fst-val-away">{vb or '—'}</td>
    </tr>"""
    return f"""
<div style="margin-bottom:8px;font-size:12px;color:var(--muted)">
  <span style="float:left;font-weight:600;color:var(--text)">{a.team.name}</span>
  <span style="float:right;color:var(--secondary)">{b.team.name}</span>
  <div style="clear:both"></div>
</div>
<table class="fixture-stat-table">
  <tbody>
    {row("Possession", a.possession, b.possession)}
    {row("Total Shots", a.shots_total, b.shots_total)}
    {row("Shots on Target", a.shots_on, b.shots_on)}
    {row("Corner Kicks", a.corners, b.corners)}
    {row("Passes", a.passes_total, b.passes_total)}
    {row("Pass Accuracy", a.pass_accuracy, b.pass_accuracy)}
    {row("Fouls", a.fouls, b.fouls)}
    {row("Offsides", a.offsides, b.offsides)}
    {row("Saves", a.saves, b.saves)}
  </tbody>
</table>"""


def _form_event_detail(fevents: list[FixtureEvent], team: Team, m_home_id: int) -> str:
    team_goals = [e for e in fevents if e.type == "Goal" and e.team.id == team.id and "Own" not in e.detail]
    opp_goals  = [e for e in fevents if e.type == "Goal" and e.team.id != team.id and "Own" not in e.detail]
    reds       = [e for e in fevents if e.type == "Card" and "Red" in e.detail]
    if not team_goals and not opp_goals and not reds:
        return ""
    parts = []
    if team_goals:
        g = [f"{e.player.split()[-1]} {e.minute}'" + (" pen" if "Penalty" in e.detail else "") for e in team_goals]
        parts.append(f'<span style="color:#888">{" · ".join(g)}</span>')
    if opp_goals:
        g = [f"{e.player.split()[-1]} {e.minute}'" + (" pen" if "Penalty" in e.detail else "") for e in opp_goals]
        parts.append(f'<span style="color:#555">Opp: {" · ".join(g)}</span>')
    if reds:
        r = [f"{e.player.split()[-1]} {e.minute}' RC" for e in reds]
        parts.append(f'<span style="color:#a00">{" · ".join(r)}</span>')
    return (
        f'<div style="font-size:11px;padding:2px 8px 5px 30px;display:flex;gap:14px;flex-wrap:wrap">'
        f'{"".join(parts)}</div>'
    )


def _odds_table(odds: list[BookmakerOdds], home_name: str, away_name: str) -> str:
    if not odds:
        return ""
    rows = "".join(f"""
    <tr>
      <td style="color:var(--secondary)">{o.bookmaker}</td>
      <td style="font-weight:600;color:var(--text)">{o.home}</td>
      <td style="color:var(--secondary)">{o.draw}</td>
      <td style="color:var(--secondary)">{o.away}</td>
    </tr>""" for o in odds)
    return f"""
<div class="label">Pre-match Odds</div>
<table>
  <thead><tr>
    <th>Bookmaker</th>
    <th>{home_name}</th>
    <th>Draw</th>
    <th>{away_name}</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
<hr>"""


def _wc_events_timeline(events: list[FixtureEvent]) -> str:
    goals = [e for e in events if e.type == "Goal"]
    reds  = [e for e in events if e.type == "Card" and "Red" in e.detail]
    if not goals and not reds:
        return ""
    rows = []
    for e in sorted(goals + reds, key=lambda x: x.minute):
        mins = f"{e.minute}'" + (f"+{e.extra_minute}" if e.extra_minute else "")
        if e.type == "Goal":
            own = " <span style='color:#555'>(OG)</span>" if "Own" in e.detail else ""
            pen = " <span style='color:#777'>(pen)</span>" if "Penalty" in e.detail else ""
            assist = f"<span style='color:#555;font-size:11px'> assist: {e.assist}</span>" if e.assist else ""
            icon = '<span style="color:var(--text);font-size:10px;font-weight:800">GOAL</span>'
            rows.append(f"""
      <div class="match-row">
        <span style="color:var(--muted);font-size:12px;min-width:36px">{mins}</span>
        <span>{icon} {e.player}{own}{pen}{assist}</span>
        <span class="match-detail" style="text-align:right">{e.team.name}</span>
      </div>""")
        else:
            card_label = "RED" if e.detail == "Red Card" else "2Y→R"
            rows.append(f"""
      <div class="match-row">
        <span style="color:var(--muted);font-size:12px;min-width:36px">{mins}</span>
        <span><span style="color:#c00;font-size:10px;font-weight:800">{card_label}</span> {e.player}</span>
        <span class="match-detail" style="text-align:right">{e.team.name}</span>
      </div>""")
    return f"""
<div class="label">Match Events</div>
<div class="match-list">{"".join(rows)}</div>
<hr>"""


def _fixture_players_table(players: list[FixturePlayerStat], team1: Team, team2: Team) -> str:
    t1 = sorted([p for p in players if p.team.id == team1.id and p.minutes > 0],
                key=lambda p: float(p.rating or 0), reverse=True)
    t2 = sorted([p for p in players if p.team.id == team2.id and p.minutes > 0],
                key=lambda p: float(p.rating or 0), reverse=True)
    if not t1 and not t2:
        return ""

    def col(team: Team, tplayers: list[FixturePlayerStat]) -> str:
        if not tplayers:
            return f'<div><div class="col-team">{team.name}</div><div style="color:#444;font-size:13px">No data.</div></div>'
        rows = "".join(f"""
      <tr>
        <td>{p.name}</td>
        <td>{p.rating or '—'}</td>
        <td>{p.minutes}'</td>
        <td>{p.goals}</td>
        <td>{p.assists}</td>
        <td>{p.shots_on}</td>
        <td>{p.tackles}</td>
      </tr>""" for p in tplayers[:11])
        return f"""
<div>
  <div class="col-team">{team.name}</div>
  <table class="player-table">
    <thead><tr>
      <th>Player</th><th>Rtg</th><th>Min</th><th>G</th><th>A</th><th>SoT</th><th>Tkl</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""

    return f"""
<div class="label">Player Ratings — This Match</div>
<div class="two-col">
  {col(team1, t1)}
  {col(team2, t2)}
</div>
<hr>"""


def _build_body(
    team1: Team,
    team2: Team,
    team1_form: list[MatchResult],
    team2_form: list[MatchResult],
    h2h: list[MatchResult],
    injuries: list[Injury],
    lineups: list[TeamLineup],
    fixture: Optional[WCFixture],
    team1_stats: Optional[TeamStats],
    team2_stats: Optional[TeamStats],
    standings: Optional[list[StandingsEntry]],
    api_prediction: Optional[ApiPrediction],
    ai_analysis: str,
    model: str,
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
) -> str:
    parts = []

    # ── Header ──────────────────────────────────────────────────────────────
    if fixture:
        teams_str = f"{fixture.home_team.name} vs {fixture.away_team.name}"
        meta_items = [
            fixture.round,
            fixture.date[:16].replace("T", " ") + " UTC",
            fixture.venue,
        ]
    else:
        teams_str = f"{team1.name} vs {team2.name}"
        meta_items = ["FIFA World Cup 2026"]

    meta_html = " ".join(f"<span>{m}</span>" for m in meta_items if m)
    parts.append(f"""
<div class="header">
  <div class="header-teams">{teams_str}</div>
  <div class="header-meta">{meta_html}</div>
</div>""")

    # ── Tournament Statistics ────────────────────────────────────────────────
    def stats_col(stats: Optional[TeamStats], team: Team) -> str:
        if not stats:
            return ""
        rows = []
        rows.append(f'<div class="stat-row"><span class="stat-key">Record</span><span class="stat-val">{stats.wins}W &nbsp;{stats.draws}D &nbsp;{stats.losses}L</span></div>')
        rows.append(f'<div class="stat-row"><span class="stat-key">Goals scored / conceded</span><span class="stat-val">{stats.goals_for_avg} &nbsp;/&nbsp; {stats.goals_against_avg} per game</span></div>')
        rows.append(f'<div class="stat-row"><span class="stat-key">Clean sheets</span><span class="stat-val">{stats.clean_sheets}</span></div>')
        if stats.biggest_win:
            rows.append(f'<div class="stat-row"><span class="stat-key">Biggest win</span><span class="stat-val">{stats.biggest_win}</span></div>')
        if stats.win_streak:
            rows.append(f'<div class="stat-row"><span class="stat-key">Best win streak</span><span class="stat-val">{stats.win_streak}</span></div>')
        if stats.preferred_formation:
            rows.append(f'<div class="stat-row"><span class="stat-key">Preferred formation</span><span class="stat-val">{stats.preferred_formation}</span></div>')
        rows.append(f'<div class="stat-row"><span class="stat-key">Form</span><span class="stat-val">{_form_badges(stats.form)}</span></div>')
        return f'<div><div class="col-team">{team.name}</div>{"".join(rows)}</div>'

    s1, s2 = stats_col(team1_stats, team1), stats_col(team2_stats, team2)
    if s1 or s2:
        inner = f'<div class="two-col">{s1}{s2}</div>' if (s1 and s2) else (s1 or s2)
        parts.append(f'<div class="label">Tournament Statistics</div>{inner}<hr>')

    # ── Player Statistics ────────────────────────────────────────────────────
    p1, p2 = _player_table(team1_players or [], team1), _player_table(team2_players or [], team2)
    if p1 or p2:
        inner = f'<div class="two-col">{p1}{p2}</div>' if (p1 and p2) else (p1 or p2)
        parts.append(f'<div class="label">Player Statistics — Tournament</div>{inner}<hr>')

    # ── Top Scorers ──────────────────────────────────────────────────────────
    if top_scorers:
        rows = "".join(f"""
    <div class="scorer-row">
      <span class="scorer-rank">{i}.</span>
      <span class="scorer-name">{p.name}</span>
      <span class="scorer-stat">{p.goals}G &nbsp;{p.assists}A &nbsp;{p.appearances} apps</span>
    </div>""" for i, p in enumerate(top_scorers[:10], 1))
        parts.append(f"""
<div class="label">Top Scorers — Tournament</div>
{rows}
<hr>""")

    # ── Top Assists ───────────────────────────────────────────────────────────
    if top_assists:
        rows = "".join(f"""
    <div class="scorer-row">
      <span class="scorer-rank">{i}.</span>
      <span class="scorer-name">{p.name}</span>
      <span class="scorer-stat">{p.assists}A &nbsp;{p.goals}G &nbsp;{p.appearances} apps</span>
    </div>""" for i, p in enumerate(top_assists[:10], 1))
        parts.append(f"""
<div class="label">Top Assists — Tournament</div>
{rows}
<hr>""")

    # ── Yellow Card Leaders ───────────────────────────────────────────────────
    if top_yellowcards:
        rows = "".join(f"""
    <div class="scorer-row">
      <span class="scorer-rank">{i}.</span>
      <span class="scorer-name">{p.name}</span>
      <span class="scorer-stat" style="color:#aa8800">{p.yellow_cards}Y &nbsp;{p.red_cards}R &nbsp;{p.appearances} apps</span>
    </div>""" for i, p in enumerate(top_yellowcards[:10], 1))
        parts.append(f"""
<div class="label">Disciplinary Leaders — Tournament</div>
{rows}
<hr>""")

    # ── Recent Form ──────────────────────────────────────────────────────────
    def form_col(matches: list[MatchResult], team: Team) -> str:
        if not matches:
            return f'<div><div class="col-team">{team.name}</div><div style="color:#444;font-size:13px">No recent data available.</div></div>'
        rows = []
        for m in matches:
            is_home = m.home_team.id == team.id
            opp = m.away_team.name if is_home else m.home_team.name
            gf = m.home_goals if is_home else m.away_goals
            ga = m.away_goals if is_home else m.home_goals
            venue = "H" if is_home else "A"
            if gf is None:
                res, score, cls = "—", "—", "res-D"
            elif gf > ga:
                res, score, cls = "W", f"{gf}–{ga}", "res-W"
            elif gf < ga:
                res, score, cls = "L", f"{gf}–{ga}", "res-L"
            else:
                res, score, cls = "D", f"{gf}–{ga}", "res-D"
            rows.append(f"""
        <div class="match-row">
          <span class="match-result {cls}">{res}</span>
          <span class="match-score">{score} vs {opp} <span style="color:#444">({venue})</span></span>
          <span class="match-detail" style="text-align:right">
            <span class="match-competition">{m.league}</span><br>{m.date[:10]}
          </span>
        </div>""")
            if form_events and m.fixture_id in form_events:
                detail = _form_event_detail(form_events[m.fixture_id], team, m.home_team.id)
                if detail:
                    rows.append(detail)
        return f'<div><div class="col-team">{team.name}</div><div class="match-list">{"".join(rows)}</div></div>'

    parts.append(f"""
<div class="label">Recent Form</div>
<div class="two-col">
  {form_col(team1_form, team1)}
  {form_col(team2_form, team2)}
</div>
<hr>""")

    # ── Head-to-Head ─────────────────────────────────────────────────────────
    if h2h:
        t1w = t2w = draws = 0
        rows = []
        for m in h2h:
            score = f"{m.home_goals}–{m.away_goals}" if m.home_goals is not None else "—"
            rows.append(f"""
      <div class="match-row">
        <span></span>
        <span class="match-score">{m.home_team.name} &nbsp;{score}&nbsp; {m.away_team.name}</span>
        <span class="match-detail" style="text-align:right">
          <span class="match-competition">{m.league}</span><br>{m.date[:10]}
        </span>
      </div>""")
            if m.home_goals is not None and m.away_goals is not None:
                is_t1_home = m.home_team.id == team1.id
                if m.home_goals > m.away_goals:
                    if is_t1_home:
                        t1w += 1
                    else:
                        t2w += 1
                elif m.away_goals > m.home_goals:
                    if is_t1_home:
                        t2w += 1
                    else:
                        t1w += 1
                else:
                    draws += 1

        total = max(t1w + draws + t2w, 1)
        parts.append(f"""
<div class="label">Head-to-Head</div>
<div class="h2h-labels">
  <span><strong>{team1.name}</strong> &nbsp;{t1w} wins</span>
  <span>{draws} draws</span>
  <span>{t2w} wins&nbsp; <strong>{team2.name}</strong></span>
</div>
<div class="h2h-record">
  <div class="h2h-t1" style="flex:{t1w or 0.5}"></div>
  <div class="h2h-draw" style="flex:{draws or 0.5}"></div>
  <div class="h2h-t2" style="flex:{t2w or 0.5}"></div>
</div>
<div class="match-list">{"".join(rows)}</div>
<hr>""")

    # ── Standings ────────────────────────────────────────────────────────────
    if standings:
        def standing_section(team: Team) -> str:
            entry = next((e for e in standings if e.team.id == team.id), None)
            if not entry:
                return ""
            group_entries = sorted(
                [e for e in standings if e.group == entry.group], key=lambda e: e.rank
            )
            rows = []
            for e in group_entries:
                hl = ' class="hl"' if e.team.id == team.id else ""
                rows.append(f"""
          <tr{hl}>
            <td>{e.rank}</td>
            <td>{e.team.name}</td>
            <td>{e.points}</td>
            <td>{e.played}</td>
            <td>{e.won}/{e.drawn}/{e.lost}</td>
            <td>{e.goal_diff:+d}</td>
            <td>{_form_badges(e.form)}</td>
          </tr>""")
            return f"""
        <div class="standings-group-title">{entry.group}</div>
        <table>
          <thead><tr>
            <th>#</th><th>Team</th><th>Pts</th><th>P</th><th>W/D/L</th><th>GD</th><th>Form</th>
          </tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""

        entry1 = next((e for e in standings if e.team.id == team1.id), None)
        entry2 = next((e for e in standings if e.team.id == team2.id), None)
        same_group = entry1 and entry2 and entry1.group == entry2.group
        s1 = standing_section(team1)
        s2 = "" if same_group else standing_section(team2)
        content = s1 + s2
        if content.strip():
            parts.append(f"""
<div class="label">Group Standings</div>
{content}
<hr>""")

    # ── Injuries ─────────────────────────────────────────────────────────────
    t1_inj = [i for i in injuries if i.team_name == team1.name]
    t2_inj = [i for i in injuries if i.team_name == team2.name]
    if t1_inj or t2_inj:
        def inj_col(injs: list[Injury], team: Team) -> str:
            if not injs:
                return ""
            rows = "".join(
                f'<div class="injury-row"><span class="injury-player">{i.player}</span><span class="injury-type">{i.injury_type} — {i.reason}</span></div>'
                for i in injs
            )
            return f'<div><div class="col-team">{team.name}</div>{rows}</div>'

        i1, i2 = inj_col(t1_inj, team1), inj_col(t2_inj, team2)
        inner = f'<div class="two-col">{i1}{i2}</div>' if (i1 and i2) else (i1 or i2)
        parts.append(f'<div class="label">Injuries</div>{inner}<hr>')

    # ── Lineups ───────────────────────────────────────────────────────────────
    if lineups:
        def lineup_col(lu: TeamLineup) -> str:
            starters = "<br>".join(
                f"{p.number}. {p.name}"
                for p in sorted(lu.starting_xi, key=lambda x: x.number)
            )
            bench = ", ".join(p.name for p in lu.substitutes[:7])
            return f"""
      <div>
        <div class="lineup-header">{lu.team.name}</div>
        <div class="lineup-formation">{lu.formation} &mdash; {lu.coach}</div>
        <div class="lineup-players">{starters}</div>
        <div class="lineup-bench-title">Bench</div>
        <div class="lineup-players" style="color:#555">{bench}</div>
      </div>"""

        parts.append(f"""
<div class="label">Lineups</div>
<div class="two-col">
  {"".join(lineup_col(lu) for lu in lineups)}
</div>
<hr>""")

    # ── Fixture Statistics ────────────────────────────────────────────────────
    if fixture_stats:
        stat_html = _fixture_stat_table(fixture_stats)
        if stat_html:
            parts.append(f"""
<div class="label">Match Statistics</div>
{stat_html}
<hr>""")

    # ── Fixture Events Timeline ───────────────────────────────────────────────
    if wc_events:
        timeline = _wc_events_timeline(wc_events)
        if timeline:
            parts.append(timeline)

    # ── Fixture Player Ratings ────────────────────────────────────────────────
    if fixture_players:
        fp_html = _fixture_players_table(fixture_players, team1, team2)
        if fp_html:
            parts.append(fp_html)

    # ── Pre-match Odds ────────────────────────────────────────────────────────
    if odds:
        home_name = fixture.home_team.name if fixture else team1.name
        away_name = fixture.away_team.name if fixture else team2.name
        odds_html = _odds_table(odds, home_name, away_name)
        if odds_html:
            parts.append(odds_html)

    # ── API Prediction ────────────────────────────────────────────────────────
    if api_prediction:
        home_name = fixture.home_team.name if fixture else team1.name
        away_name = fixture.away_team.name if fixture else team2.name
        hp = _pct(api_prediction.home_percent)
        dp = _pct(api_prediction.draw_percent)
        ap = _pct(api_prediction.away_percent)

        def comp_row(label, home_val, away_val):
            return f"""
    <div class="stat-row">
      <span class="stat-key">{label}</span>
      <span class="stat-val" style="font-size:12px;color:var(--secondary)">{home_val} <span style="color:var(--muted)">/</span> {away_val}</span>
    </div>"""

        def last5_block(l5: Optional[Last5], name: str) -> str:
            if not l5:
                return ""
            return f"""
<div>
  <div class="col-team">{name}</div>
  <div class="stat-row"><span class="stat-key">Form rating</span><span class="stat-val">{l5.form_pct}</span></div>
  <div class="stat-row"><span class="stat-key">Attack rating</span><span class="stat-val">{l5.att_pct}</span></div>
  <div class="stat-row"><span class="stat-key">Defense rating</span><span class="stat-val">{l5.def_pct}</span></div>
  <div class="stat-row"><span class="stat-key">Goals scored</span><span class="stat-val">{l5.goals_for_avg}/game ({l5.goals_for_total} total)</span></div>
  <div class="stat-row"><span class="stat-key">Goals conceded</span><span class="stat-val">{l5.goals_against_avg}/game ({l5.goals_against_total} total)</span></div>
</div>"""

        def uo_block(uo, name: str) -> str:
            if not uo:
                return ""
            total = max(uo.over_0_5 + uo.under_0_5, 1)
            def bar(over, under):
                op = over / max(over + under, 1)
                return (f'<div style="display:flex;height:4px;gap:1px;margin-top:2px">'
                        f'<div style="flex:{op};background:var(--text)"></div>'
                        f'<div style="flex:{1-op};background:var(--line)"></div></div>')
            rows = ""
            for line, over, under in [
                ("0.5", uo.over_0_5, uo.under_0_5),
                ("1.5", uo.over_1_5, uo.under_1_5),
                ("2.5", uo.over_2_5, uo.under_2_5),
                ("3.5", uo.over_3_5, uo.under_3_5),
                ("4.5", uo.over_4_5, uo.under_4_5),
            ]:
                rows += f"""
      <div style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted)">
          <span>Over {line}</span><span style="color:var(--secondary)">{over}W / {under}L</span>
        </div>
        {bar(over, under)}
      </div>"""
            return f'<div><div class="col-team">{name}</div>{rows}</div>'

        parts.append(f"""
<div class="label">API-Football Prediction</div>
<div class="pred-advice">{api_prediction.advice}</div>
<div class="pred-bar">
  <div class="pred-t1"   style="flex:{hp}"></div>
  <div class="pred-draw" style="flex:{dp}"></div>
  <div class="pred-t2"   style="flex:{ap}"></div>
</div>
<div class="pred-bar-labels">
  <span>{home_name} &nbsp;{api_prediction.home_percent}</span>
  <span>Draw &nbsp;{api_prediction.draw_percent}</span>
  <span>{api_prediction.away_percent}&nbsp; {away_name}</span>
</div>

<div style="margin-top:20px;margin-bottom:6px" class="label">Comparison &nbsp;<span style="font-size:9px;color:var(--muted);letter-spacing:0">{home_name} / {away_name}</span></div>
{comp_row("Form", api_prediction.form_home, api_prediction.form_away)}
{comp_row("Attack", api_prediction.att_home, api_prediction.att_away)}
{comp_row("Defense", api_prediction.def_home, api_prediction.def_away)}
{comp_row("Poisson model", api_prediction.poisson_home, api_prediction.poisson_away)}
{comp_row("H2H advantage", api_prediction.h2h_home, api_prediction.h2h_away)}
{comp_row("Goals", api_prediction.goals_comp_home, api_prediction.goals_comp_away)}
{comp_row("Overall", api_prediction.total_home, api_prediction.total_away)}

{f'<div style="margin-top:20px;margin-bottom:6px" class="label">Last 5 Ratings</div><div class="two-col">{last5_block(api_prediction.last_5_home, home_name)}{last5_block(api_prediction.last_5_away, away_name)}</div>' if (api_prediction.last_5_home or api_prediction.last_5_away) else ""}

{f'<div style="margin-top:20px;margin-bottom:6px" class="label">Goals Over/Under (season)</div><div class="two-col">{uo_block(api_prediction.home_under_over, home_name)}{uo_block(api_prediction.away_under_over, away_name)}</div>' if (api_prediction.home_under_over or api_prediction.away_under_over) else ""}
<hr>""")

    # ── AI Analysis ───────────────────────────────────────────────────────────
    analysis_html = md.markdown(ai_analysis, extensions=["nl2br"])
    parts.append(f"""
<div class="label">AI Analysis</div>
<div class="ai-body">{analysis_html}</div>""")

    return "\n".join(parts)


def save_report(
    team1: Team,
    team2: Team,
    team1_form: list[MatchResult],
    team2_form: list[MatchResult],
    h2h: list[MatchResult],
    injuries: list[Injury],
    lineups: list[TeamLineup],
    fixture: Optional[WCFixture],
    team1_stats: Optional[TeamStats],
    team2_stats: Optional[TeamStats],
    standings: Optional[list[StandingsEntry]],
    api_prediction: Optional[ApiPrediction],
    ai_analysis: str,
    model: str,
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
) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)

    t1_slug = team1.name.lower().replace(" ", "_")
    t2_slug = team2.name.lower().replace(" ", "_")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    filename = RESULTS_DIR / f"{t1_slug}_vs_{t2_slug}_{date_str}.html"

    title = (
        f"{fixture.home_team.name} vs {fixture.away_team.name} — WC 2026"
        if fixture else
        f"{team1.name} vs {team2.name} — WC 2026"
    )

    body = _build_body(
        team1, team2, team1_form, team2_form, h2h, injuries, lineups, fixture,
        team1_stats, team2_stats, standings, api_prediction, ai_analysis, model,
        team1_players=team1_players,
        team2_players=team2_players,
        top_scorers=top_scorers,
        fixture_stats=fixture_stats,
        form_events=form_events,
        odds=odds,
        top_assists=top_assists,
        top_yellowcards=top_yellowcards,
        wc_events=wc_events,
        fixture_players=fixture_players,
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = HTML_TEMPLATE.format(
        title=title, body=body, generated_at=generated_at, model=model
    )
    filename.write_text(html, encoding="utf-8")
    return filename

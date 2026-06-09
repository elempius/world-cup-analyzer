from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import markdown as md

from api.models import (
    ApiPrediction,
    Injury,
    MatchResult,
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
        rows = []
        if not stats:
            return f'<div><div class="col-team">{team.name}</div><div style="color:#444;font-size:13px">No tournament data yet.</div></div>'
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

    parts.append(f"""
<div class="label">Tournament Statistics</div>
<div class="two-col">
  {stats_col(team1_stats, team1)}
  {stats_col(team2_stats, team2)}
</div>
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
                    t1w += 1 if is_t1_home else 0
                    t2w += 0 if is_t1_home else 1
                elif m.away_goals > m.home_goals:
                    t2w += 0 if is_t1_home else 1
                    t1w += 1 if not is_t1_home else 0
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
                return f'<div><div class="col-team">{team.name}</div><div style="color:#444;font-size:13px">None reported.</div></div>'
            rows = "".join(
                f'<div class="injury-row"><span class="injury-player">{i.player}</span><span class="injury-type">{i.injury_type} — {i.reason}</span></div>'
                for i in injs
            )
            return f'<div><div class="col-team">{team.name}</div>{rows}</div>'

        parts.append(f"""
<div class="label">Injuries</div>
<div class="two-col">
  {inj_col(t1_inj, team1)}
  {inj_col(t2_inj, team2)}
</div>
<hr>""")

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

    # ── API Prediction ────────────────────────────────────────────────────────
    if api_prediction:
        home_name = fixture.home_team.name if fixture else team1.name
        away_name = fixture.away_team.name if fixture else team2.name
        hp = _pct(api_prediction.home_percent)
        dp = _pct(api_prediction.draw_percent)
        ap = _pct(api_prediction.away_percent)
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
<div class="pred-comparison">
  <div class="pred-comp-cell"><div class="pred-comp-label">Form</div><div class="pred-comp-values"><strong>{api_prediction.form_home}</strong>{api_prediction.form_away}</div></div>
  <div class="pred-comp-cell"><div class="pred-comp-label">Attack</div><div class="pred-comp-values"><strong>{api_prediction.att_home}</strong>{api_prediction.att_away}</div></div>
  <div class="pred-comp-cell"><div class="pred-comp-label">Defense</div><div class="pred-comp-values"><strong>{api_prediction.def_home}</strong>{api_prediction.def_away}</div></div>
  <div class="pred-comp-cell"><div class="pred-comp-label">Overall</div><div class="pred-comp-values"><strong>{api_prediction.total_home}</strong>{api_prediction.total_away}</div></div>
</div>
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
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = HTML_TEMPLATE.format(
        title=title, body=body, generated_at=generated_at, model=model
    )
    filename.write_text(html, encoding="utf-8")
    return filename
